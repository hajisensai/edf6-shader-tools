"""List, inspect, extract, decompile and repack EDF6 DX11 shader SGOs.

Reading from a CPK first checks that it is the official Steam file (verify_install.py); add --allow-unofficial to
use another copy anyway. The game files are only read; outputs go to the paths you give and never overwrite a file."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from edf6shader import dxbc  # noqa: E402
from edf6shader.rootcpk import Game  # noqa: E402
from edf6shader.shader_sgo import Shader, ShaderSgo  # noqa: E402
import verify_install  # noqa: E402


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _list(archive: Path) -> None:
    game = Game(str(archive.parent), archive.name)
    for folder, name in sorted(game.cpk.index):
        if name.upper().endswith('.SGO') and folder.upper() in ('SHADER/DX11', 'MAP/SHADER/DX11'):
            print(f'{folder}/{name}')


def _read(source: str, archive: Path | None) -> bytes:
    if archive is None:
        return Path(source).read_bytes()
    folder, separator, name = source.replace('\\', '/').rpartition('/')
    if not separator or not name:
        raise ValueError('an archive member needs the full path from the list command')
    return Game(str(archive.parent), archive.name).read(folder, name)


def _info(shader: Shader) -> dict:
    return dict(id=shader.id, path=shader.path, offset=shader.offset, profile=shader.profile,
                size=len(shader.data), sha256=_sha(shader.data))


def _resolve_tool(name: str) -> str:
    executable = shutil.which(name)
    if executable is None:
        raise ValueError(f'cannot find shader tool: {name}')
    return str(Path(executable).resolve())


def _run_tool(executable: str, flags: list[str], source: Path, output: Path) -> None:
    result = subprocess.run([executable, *flags, str(source.resolve())],
                            cwd=source.parent, capture_output=True, text=True, errors='replace',
                            timeout=60)
    if result.returncode or not output.is_file() or not output.stat().st_size:
        raise ValueError((result.stderr or result.stdout).strip() or f'no {output.suffix} written')


def _assemble(executable: str, path: Path, original: bytes) -> bytes:
    with tempfile.TemporaryDirectory(prefix='edf6-shader-') as directory:
        work = Path(directory)
        source = work / 'edit.asm'
        reference = work / 'original.dxbc'
        output = work / 'edit.shdr'
        shutil.copyfile(path, source)
        reference.write_bytes(original)
        flags = ['--assemble', '--stop-on-failure', '--copy-reflection', str(reference)]
        _run_tool(executable, flags, source, output)
        compiled = output.read_bytes()

    def declarations(data: bytes) -> list[str]:
        return [line.strip() for line in dxbc.disassemble(data).splitlines()
                if line.startswith('dcl_') and not line.startswith(('dcl_temps ', 'dcl_indexableTemp '))]

    if declarations(original) != declarations(compiled):
        raise ValueError('assembly changed shader declarations')
    return compiled


def _gate(parser: argparse.ArgumentParser, args: argparse.Namespace) -> dict | None:
    """Check the archive is the official Steam file; None for a loose SGO (its SHA-256 is still recorded)."""
    archive = getattr(args, 'archive', None)
    if archive is None:
        print('note: loose SGO, its origin is not checked; only its SHA-256 is recorded', file=sys.stderr)
        return None
    archive = archive.resolve()
    if not archive.is_file():
        parser.exit(1, f'{parser.prog}: archive not found: {archive}\n')
    return verify_install.gate_or_exit(parser, archive.parent, (archive.name,), args.allow_unofficial,
                                       'shader_sgo.py', progress=False)


def _extract(args: argparse.Namespace, document: ShaderSgo, provenance: dict | None) -> int:
    shaders = [document.shader(i) for i in dict.fromkeys(args.id)] if args.id else document.shaders
    decompiler = _resolve_tool(args.decompiler) if args.decompiler else None

    args.output.mkdir(parents=True)
    entries = []
    failed = False
    for shader in shaders:
        binary = args.output / f'{shader.id:04d}.{shader.profile}.dxbc'
        binary.write_bytes(shader.data)
        entry = _info(shader)
        entry['dxbc'] = binary.name
        if args.asm:
            asm = binary.with_suffix('.asm')
            asm.write_text(dxbc.disassemble(shader.data), encoding='utf-8')
            entry['asm'] = asm.name
        if decompiler:
            hlsl = binary.with_suffix('.hlsl')
            flags = (['-o', str(hlsl.resolve())] if args.decompiler_kind == 'hlsl-decompiler'
                     else ['--decompile', '--stop-on-failure'])
            try:
                _run_tool(decompiler, flags, binary, hlsl)
                entry['hlsl'] = hlsl.name
            except (OSError, ValueError, subprocess.TimeoutExpired) as error:
                failed = True
                entry['decompile_error'] = str(error)
                print(f'shader {shader.id}: {error}', file=sys.stderr)
        entries.append(entry)
    manifest = dict(source=args.source, archive=str(args.archive) if args.archive else None,
                    sha256=_sha(document.data),
                    archive_verdict=provenance['verdict'] if provenance else 'loose file, not checked',
                    unofficial_allowed=bool(provenance and provenance.get('unofficial_allowed')),
                    shaders=entries)
    if provenance:
        verify_install.write_provenance(args.output, provenance)
    (args.output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    print(f'Extracted {len(entries)} shader slots to {args.output}')
    return int(failed)


def _repack(args: argparse.Namespace, document: ShaderSgo) -> None:
    if args.asm and not args.assembler:
        raise ValueError('--asm needs --assembler pointing to 3Dmigoto cmd_Decompiler.exe')
    assembler = _resolve_tool(args.assembler) if args.asm else None
    replacements = {}
    for kind, inputs in (('DXBC', args.dxbc), ('HLSL', args.hlsl), ('ASM', args.asm)):
        for raw_id, filename in inputs:
            shader = document.shader(int(raw_id))
            if shader.id in replacements:
                raise ValueError(f'duplicate replacement for shader {shader.id}')
            path = Path(filename)
            if kind == 'HLSL':
                program = dxbc.compile_hlsl(path, shader.profile, args.entry)
            elif kind == 'ASM':
                program = _assemble(assembler, path, shader.data)
            else:
                program = path.read_bytes()
            replacements[shader.id] = program
    output = document.repack(replacements)
    with args.output.open('xb') as file:
        file.write(output)
    print(f'Wrote {args.output} ({len(output)} bytes)')


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    listing = commands.add_parser('list', help='list shader SGO paths in a CPK')
    listing.add_argument('archive', type=Path)
    listing.add_argument('--allow-unofficial', action='store_true',
                         help='read the CPK even if it is not the official Steam file')
    for command, help_text in (
            ('inspect', 'print the shader slots and profiles as JSON'),
            ('extract', 'export DXBC and optionally assembly or HLSL'),
            ('repack', 'write a new SGO with explicitly selected shader replacements')):
        sub = commands.add_parser(command, help=help_text)
        sub.add_argument('source', help='a loose SGO, or the full member path with --archive')
        sub.add_argument('--archive', type=Path, help='read the source from DX11.cpk')
        sub.add_argument('--allow-unofficial', action='store_true',
                         help='read the CPK even if it is not the official Steam file (recorded in the output)')
        if command != 'inspect':
            sub.add_argument('output', type=Path, help='new output directory or SGO file')
        if command == 'extract':
            sub.add_argument('--id', type=int, action='append', help='extract only this ID, repeatable')
            sub.add_argument('--asm', action='store_true', help='include Microsoft DXBC disassembly')
            sub.add_argument('--decompiler', help='path to the executable used for HLSL export')
            sub.add_argument('--decompiler-kind', choices=('3dmigoto', 'hlsl-decompiler'), default='3dmigoto',
                             help='HLSL export backend (default 3dmigoto)')
        if command == 'repack':
            sub.add_argument('--dxbc', nargs=2, action='append', default=[], metavar=('ID', 'FILE'))
            sub.add_argument('--hlsl', nargs=2, action='append', default=[], metavar=('ID', 'FILE'))
            sub.add_argument('--asm', nargs=2, action='append', default=[], metavar=('ID', 'FILE'))
            sub.add_argument('--assembler', help='path to 3Dmigoto cmd_Decompiler.exe for assembly input')
            sub.add_argument('--entry', default='main', help='HLSL entry point (default main)')

    args = parser.parse_args()
    provenance = _gate(parser, args)
    try:
        if args.command == 'list':
            _list(args.archive)
            return 0
        document = ShaderSgo(_read(args.source, args.archive))
        if args.command == 'inspect':
            print(json.dumps(dict(sha256=_sha(document.data), shaders=[_info(s) for s in document.shaders]),
                             indent=2))
        elif args.command == 'extract':
            return _extract(args, document, provenance)
        else:
            _repack(args, document)
    except (OSError, ValueError, KeyError, RecursionError, struct.error, subprocess.TimeoutExpired) as error:
        parser.exit(1, f'{parser.prog}: {error}\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
