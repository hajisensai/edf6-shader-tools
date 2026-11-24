English | [简体中文](README.zh-CN.md)

# EDF6 Shader Tools (edf6-shader-tools)

Export, edit and repack the DX11 shaders of **your own** Steam copy of EARTH DEFENSE FORCE 6.

The game keeps its shaders as compiled Direct3D 11 bytecode (DXBC) inside SGO files in `DX11.cpk`, under `SHADER/DX11` and `MAP/SHADER/DX11`. The stock package has 485 such files with 2,237 `vs_5_0` and 2,237 `ps_5_0` slots. This tool lists them, exports any slot as DXBC, disassembly or decompiled HLSL, and writes a new SGO with the slots you edited, checking that each replacement still fits what the game expects.

## What this repository contains, and what it does not

- **Contains**: the tool (`shader_sgo.py`), its library (`edf6shader/`), the install check (`verify_install.py`) and tests.
- **Does not contain**: anything from the game. No SGO files, no shader bytecode, no disassembly, no decompiled or edited game shaders. Everyone exports from their own copy, and the results stay on their own machine.

If you want to share an edited shader, release it yourself the way mods are released. CI runs `tools/lint_repo.py` to keep game-derived files out of this repository; see [CONTRIBUTING.md](CONTRIBUTING.md).

## Requirements

- **System**: Windows. HLSL compilation and disassembly use the system's `d3dcompiler_47.dll`.
- **Python**: 3.12 or newer. Only the standard library is used; there is nothing to `pip install`.
- **For HLSL export and assembly input**: the 3Dmigoto command-line package [`cmd_Decompiler-1.3.16.zip`](https://github.com/bo3b/3Dmigoto/releases/tag/1.3.16). Keep its EXE and DLLs in the same folder. Plain DXBC export and HLSL compilation work without it.

## Your game files must be official

Shader slot numbers and the checks below are tied to one specific build of `DX11.cpk`. Whenever the tool reads a CPK, it first checks that file against Steam's own depot manifest (`steamapps/appmanifest_2291060.acf` and `depotcache/*.manifest`). When there is no Steam manifest, for example because the folder was copied, it falls back to the SHA-256 values in [known-builds.tsv](known-builds.tsv).

If the check fails, the tool refuses to continue unless you add `--allow-unofficial`. The extract output records the verdict in `manifest.json` and `provenance.json`. You can also run the check on its own:

```powershell
python -B verify_install.py "D:/steam/steamapps/common/EARTH DEFENSE FORCE 6" --module DX11.cpk
```

The currently known official build is Steam buildid `17055427`.

## Export and repack

```powershell
$cpk = 'D:/steam/steamapps/common/EARTH DEFENSE FORCE 6/DX11.cpk'
$member = 'SHADER/DX11/SND_MECH.SGO'
$decompiler = 'D:/Tools/3Dmigoto/cmd_Decompiler.exe'

python -B shader_sgo.py list $cpk
python -B shader_sgo.py inspect $member --archive $cpk
python -B shader_sgo.py extract $member work/mech-shader --archive $cpk --id 1 --asm --decompiler $decompiler
# edit work/mech-shader/0001.ps_5_0.hlsl
python -B shader_sgo.py repack $member work/SND_MECH.SGO --archive $cpk --hlsl 1 work/mech-shader/0001.ps_5_0.hlsl
```

- **`list`** prints the archive paths of all shader SGOs.
- **`inspect`** prints each slot as JSON: its ID, array path, stage, bytecode offset and SHA-256. A path such as `["Deferred", 0, 4]` is the pixel shader of the first pass of the `Deferred` technique. IDs follow the member order of the source file, so look again after switching to another file.
- **`extract`** writes `<ID>.<profile>.dxbc` for every slot, or only the ones given with `--id`, which can be repeated.
  - Add `--asm` for Microsoft's disassembly, and `--decompiler` for HLSL.
  - `manifest.json` records the source hash and the exported files.
  - If a slot cannot be decompiled, its DXBC and requested assembly are still exported, the failure is recorded in the manifest, and the exit code is non-zero.
- **`repack`** writes a new SGO.
  - Replace a slot with `--hlsl ID FILE`, `--asm ID FILE` (needs `--assembler`, the 3Dmigoto `cmd_Decompiler.exe`) or `--dxbc ID FILE`. Each option can be repeated for different IDs in one run.
  - HLSL is compiled for the slot's profile with the entry point `main`; use `--entry` to change it.
  - With no replacements, the output is byte-identical to the source.
  - The tool never overwrites an existing file; give an output path outside the game directory.
- **Loose files**: to work on a loose SGO file, leave out `--archive` and give the file's path as the source. Its origin cannot be checked, so only its SHA-256 is recorded.
- **Another decompiler**: to try [HlslDecompiler](https://github.com/AndresTraks/HlslDecompiler) instead of 3Dmigoto, add `--decompiler PATH --decompiler-kind hlsl-decompiler`.

Putting the new SGO into the game (a CPK patch or a mod loader) is up to you. This tool only produces the file.

## What repacking checks

The engine finds shaders by the SGO's techniques and passes. Several slots in a stock SGO can point at the same DXBC. When you edit one of them, the repack splits that shared reference so the others keep the original.

- **Layout**: the original node order, string pool and padding are kept. Raw-node and string offsets are recomputed, and the raw area stays 16-byte aligned.
- **Bytecode**: the new program keeps the original reflection data and input / output signatures, takes the new program and statistics, and gets a recomputed checksum.
- **Compatibility checks**: the stage, signatures, resource bindings and constant-buffer sizes must match the original. For assembly input, the declarations must match too. Texture and constant-buffer binding slots are decided by the game, so keep the data layout and meaning of the constants.

Passing these offline checks does not prove the shader looks right. Always look at the affected pass in the game.

## Reliability and limitations

- Decompiled HLSL is reconstructed from bytecode. Names, structure and some expressions will not match the original source. Check it against the disassembly when something looks wrong.
- Only the little-endian SGO version 0x102 used by the Steam `DX11.cpk` is supported.

## License

The tool code is under the MIT license; see [LICENSE](LICENSE). The CPK / CRILAYLA readers in `edf6shader/` keep their original license (Unlicense, see `edf6shader/LICENSE.edf6-cpk`). The SGO layout follows the format as documented by edf-tools. This project is not affiliated with SANDLOT or D3 PUBLISHER.
