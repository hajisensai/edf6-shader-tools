"""Inspect and repack the shader SGO 0x102 layout used by EDF6 DX11.cpk."""
from __future__ import annotations

from dataclasses import dataclass
import struct

from . import dxbc
from . import sgo


@dataclass(frozen=True)
class Shader:
    id: int
    path: tuple[str | int, ...]
    node: int
    offset: int
    data: bytes
    profile: str


class ShaderSgo:
    def __init__(self, data: bytes) -> None:
        if len(data) < 32 or data[:8] != b'SGO\0\x02\x01\0\0':
            raise ValueError('expected an EDF6 little-endian Shader SGO v0x102')
        names, names_at, reserved, self.raw_at = struct.unpack_from('<4I', data, 16)
        names_end = names_at + names * 8
        if reserved or not 32 <= names_at <= names_end <= self.raw_at <= len(data):
            raise ValueError('unexpected EDF6 shader SGO header layout')
        self.data = data
        self.shaders: list[Shader] = []
        self.strings: list[tuple[int, str]] = []
        self.groups: dict[int, list[Shader]] = {}
        offsets = {}
        sgo.read(data, node_offsets=offsets)
        for path, pos in offsets.items():
            if not 32 <= pos or pos + 12 > self.raw_at:
                raise ValueError('SGO node overlaps the shader data')
            kind, size, relative = struct.unpack_from('<iiI', data, pos)
            target = pos + relative
            if kind == 3 and relative:
                self.strings.append((pos + 8, '<I'))
            if kind != 4:
                continue
            if not self.raw_at <= target <= target + size <= len(data) or target % 16:
                raise ValueError(f'{path}: invalid shader blob range/alignment')
            program = data[target:target + size]
            shader = Shader(len(self.shaders), path, pos, target, program, dxbc.profile(program))
            self.shaders.append(shader)
            self.groups.setdefault(target, []).append(shader)

        end = self.raw_at
        for start, shaders in sorted(self.groups.items()):
            size = len(shaders[0].data)
            if start < end or any(len(shader.data) != size for shader in shaders):
                raise ValueError('SGO shader blobs overlap')
            end = start + size
        self.strings.extend((entry, '<i') for entry in range(names_at, names_end, 8))
        for field, fmt in self.strings:
            base = field - 8 if fmt == '<I' else field
            target = base + struct.unpack_from(fmt, data, field)[0]
            if not end <= target <= len(data) - 2:
                raise ValueError('SGO string overlaps the shader data or is out of bounds')

    def shader(self, shader_id: int) -> Shader:
        if not 0 <= shader_id < len(self.shaders):
            raise ValueError(f'no shader with ID {shader_id}')
        return self.shaders[shader_id]

    def repack(self, replacements: dict[int, bytes]) -> bytes:
        programs = {}
        for shader_id, replacement in replacements.items():
            shader = self.shader(shader_id)
            try:
                program = dxbc.replace_program(shader.data, replacement)
            except (ValueError, struct.error) as error:
                raise ValueError(f'shader {shader_id} {shader.path}: {error}') from error
            if program != shader.data:
                programs[shader_id] = program
        if not programs:
            return self.data

        out = bytearray(self.data[:self.raw_at])
        cursor = self.raw_at
        for start, shaders in sorted(self.groups.items()):
            out += self.data[cursor:start]
            original = shaders[0].data
            cursor = start + len(original)
            offsets = {}
            for shader in shaders:
                data = programs.get(shader.id, original)
                if data not in offsets:
                    out += bytes(-len(out) % 16)
                    offsets[data] = len(out)
                    out += data
                struct.pack_into('<iI', out, shader.node + 4, len(data), offsets[data] - shader.node)
            # Keep the following raw blocks aligned and preserve the original gaps.
            out += bytes((cursor - len(out)) % 16)

        shift = len(out) - cursor
        out += self.data[cursor:]
        for field, fmt in self.strings:
            relative = struct.unpack_from(fmt, out, field)[0]
            struct.pack_into(fmt, out, field, relative + shift)
        return bytes(out)
