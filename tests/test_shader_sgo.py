"""Regression tests for compiled shader contracts and shared SGO payloads."""
from __future__ import annotations

import os
from pathlib import Path
import struct
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from edf6shader import dxbc, sgo  # noqa: E402
from edf6shader.shader_sgo import ShaderSgo  # noqa: E402


@unittest.skipUnless(os.name == 'nt', 'requires Windows D3DCompiler')
class ShaderRoundTrip(unittest.TestCase):
    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.temp = Path(temp.name)
        self.vertex = self.compile('float4 main(float3 p: POSITION): SV_Position {return float4(p, 1);}',
                                   'vs_5_0')
        self.pixel = self.compile('float4 main(float4 p: SV_Position): SV_Target {return p * 0.5;}')
        self.document = self.fixture()

    def compile(self, source: str, profile: str = 'ps_5_0') -> bytes:
        hlsl = self.temp / 'shader.hlsl'
        hlsl.write_text(source, encoding='ascii')
        return dxbc.compile_hlsl(hlsl, profile)

    def fixture(self) -> ShaderSgo:
        members = {'Deferred': [[self.vertex, 0, 0, 0, self.pixel]],
                   'Skinned': [[self.vertex, 0, 0, 0, self.pixel]],
                   'Instancing': [['float', 4, 1, 'instance', 'INSTANCING_instance']]}
        data = bytearray(sgo.write(0x102, members))
        offsets = {}
        sgo.read(data, node_offsets=offsets)
        first = offsets['Deferred', 0, 0]
        pixel = offsets['Deferred', 0, 4]
        other = offsets['Skinned', 0, 4]
        struct.pack_into('<I', data, 28, first + struct.unpack_from('<I', data, first + 8)[0])
        struct.pack_into('<I', data, other + 8, pixel + struct.unpack_from('<I', data, pixel + 8)[0] - other)
        return ShaderSgo(bytes(data))

    def test_noop_is_byte_identical(self) -> None:
        self.assertEqual(self.document.repack({}), self.document.data)
        self.assertEqual(self.document.repack({1: self.pixel}), self.document.data)

    def test_resized_program_separates_one_shared_slot(self) -> None:
        replacement = self.compile('''
            float4 main(float4 p: SV_Position): SV_Target {
                return (p.x > 3) ? p * 0.7 : p / (p.y + 1);
            }''')
        before = self.document
        self.assertEqual(before.shaders[1].offset, before.shaders[3].offset)
        after = ShaderSgo(before.repack({1: replacement}))
        program = after.shaders[1].data
        self.assertNotEqual(len(program), len(self.pixel))
        self.assertNotEqual(after.shaders[1].offset, after.shaders[3].offset)
        self.assertEqual([s.data for s in after.shaders if s.id != 1],
                         [s.data for s in before.shaders if s.id != 1])
        self.assertEqual(after.shaders[1].path, before.shaders[1].path)
        version, values = sgo.read(before.data)
        values['Deferred'][0][4] = program
        self.assertEqual(sgo.read(after.data), (version, values))
        for tag in (b'RDEF', b'ISGN', b'OSGN'):
            old_offset, old_size = dxbc.chunks(self.pixel)[tag]
            new_offset, new_size = dxbc.chunks(program)[tag]
            self.assertEqual(program[new_offset:new_offset + new_size],
                             self.pixel[old_offset:old_offset + old_size])
        self.assertEqual(program[4:20], dxbc.dxbc_checksum(program))
        self.assertIn('ps_5_0', dxbc.disassemble(program))

    def test_rejects_incompatible_program(self) -> None:
        wrong_signature = self.compile('float4 main(): SV_Target {return 0;}')
        new_resource = self.compile('''
            Texture2D<float4> source : register(t3);
            float4 main(float4 p: SV_Position): SV_Target {
                return source.Load(int3(p.xy, 0)) + p;
            }''')
        damaged = bytearray(self.pixel)
        damaged[4] ^= 1
        for replacement, message in ((self.vertex, 'profile'), (wrong_signature, 'ISGN'),
                                     (new_resource, 'binding'), (bytes(damaged), 'checksum')):
            with self.subTest(message=message), self.assertRaisesRegex(ValueError, message):
                self.document.repack({1: replacement})


if __name__ == '__main__':
    unittest.main()
