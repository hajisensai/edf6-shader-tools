"""Direct3D 11 tokenized shader containers and their retail checksum."""
from __future__ import annotations

import ctypes
import math
import os
from pathlib import Path
import struct


_MASK = 0xFFFFFFFF
_MD5_K = tuple(int(abs(math.sin(i + 1)) * 2**32) for i in range(64))
_MD5_S = (7, 12, 17, 22) * 4 + (5, 9, 14, 20) * 4 + (4, 11, 16, 23) * 4 + (6, 10, 15, 21) * 4


def _compress(state: tuple[int, ...], block: bytes) -> tuple[int, ...]:
    """RFC1321 MD5 compression; DXBC has a different final-block layout."""
    words = struct.unpack('<16I', block)
    a, b, c, d = state
    for i in range(64):
        if i < 16:
            f, at = (b & c) | (~b & d), i
        elif i < 32:
            f, at = (d & b) | (~d & c), (5 * i + 1) % 16
        elif i < 48:
            f, at = b ^ c ^ d, (3 * i + 5) % 16
        else:
            f, at = c ^ (b | ~d), (7 * i) % 16
        value = (a + f + _MD5_K[i] + words[at]) & _MASK
        shift = _MD5_S[i]
        value = ((value << shift) | (value >> (32 - shift))) & _MASK
        a, b, c, d = d, (b + value) & _MASK, b, c
    return tuple((x + y) & _MASK for x, y in zip(state, (a, b, c, d)))


def dxbc_checksum(data: bytes) -> bytes:
    """DXBC checksum of bytes after the 20-byte magic/checksum prefix.

    Independent MD5 compression implementation; the DXBC final-block layout is
    documented by AMD's DXBCChecksum and corroborated against stock containers.
    This is an integrity checksum, not a security primitive.
    """
    if len(data) < 32 or data[:4] != b'DXBC':
        raise ValueError('not a DXBC container')
    payload = data[20:]
    length = len(payload) * 8
    if length > _MASK:
        raise ValueError('DXBC exceeds the checksum length range')
    end = len(payload) // 64 * 64
    blocks = bytearray(payload[:end])
    tail = payload[end:]
    if len(tail) >= 56:
        blocks += tail + b'\x80' + bytes(63 - len(tail))
        final = bytearray(64)
        struct.pack_into('<I', final, 0, length)
    else:
        final = bytearray(struct.pack('<I', length) + tail + b'\x80')
        final += bytes(64 - len(final))
    struct.pack_into('<I', final, 60, (length >> 2) | 1)
    blocks += final
    state = (0x67452301, 0xEFCDAB89, 0x98BADCFE, 0x10325476)
    for offset in range(0, len(blocks), 64):
        state = _compress(state, blocks[offset:offset + 64])
    return struct.pack('<4I', *state)


def chunks(data: bytes) -> dict[bytes, tuple[int, int]]:
    """Chunk tag to (payload offset, payload length)."""
    if (len(data) < 36 or data[:4] != b'DXBC' or
            struct.unpack_from('<I', data, 24)[0] != len(data)):
        raise ValueError('invalid DXBC header/size')
    count = struct.unpack_from('<I', data, 28)[0]
    table_end = 32 + count * 4
    if not count or table_end > len(data):
        raise ValueError('invalid DXBC chunk table')
    result = {}
    ranges = []
    for offset in struct.unpack_from(f'<{count}I', data, 32):
        if offset < table_end or offset + 8 > len(data):
            raise ValueError('DXBC chunk outside container')
        tag, length = struct.unpack_from('<4sI', data, offset)
        end = offset + 8 + length
        if end > len(data) or tag in result:
            raise ValueError('truncated or duplicate DXBC chunk')
        result[tag] = offset + 8, length
        ranges.append((offset, end))
    ranges.sort()
    if any(a[1] > b[0] for a, b in zip(ranges, ranges[1:])):
        raise ValueError('overlapping DXBC chunks')
    return result


def _program(parts: dict[bytes, tuple[int, int]]) -> bytes:
    tags = parts.keys() & {b'SHDR', b'SHEX'}
    if len(tags) != 1:
        raise ValueError('DXBC must have one tokenized DX11 program')
    return tags.pop()


def code(data: bytes) -> tuple[int, int]:
    parts = chunks(data)
    return parts[_program(parts)]


def profile(data: bytes) -> str:
    offset, size = code(data)
    if size < 8 or size % 4:
        raise ValueError('invalid DXBC program size')
    version, length = struct.unpack_from('<II', data, offset)
    if length * 4 != size:
        raise ValueError('DXBC token count differs from program size')
    stage = version >> 16
    if stage not in (0, 1) or version & 0xffff != 0x50:
        raise ValueError(f'expected an EDF6 vertex or pixel shader (token {version:#x})')
    return 'vs_5_0' if stage else 'ps_5_0'


def _name(data: bytes, offset: int) -> bytes:
    end = data.find(b'\0', offset)
    if end <= offset:
        raise ValueError('invalid DXBC metadata name')
    return data[offset:end]


def _signature(data: bytes) -> set[tuple]:
    count, offset = struct.unpack_from('<II', data)
    if offset < 8 or offset + count * 24 > len(data):
        raise ValueError('invalid DXBC signature table')
    rows = set()
    for index in range(count):
        name, semantic, system, component, register, mask = struct.unpack_from(
            '<5IB', data, offset + index * 24)
        rows.add((_name(data, name).upper(), semantic, system, component, register, mask))
    return rows


def _bindings(data: bytes) -> dict[tuple, int]:
    buffer_count, buffers, count, offset = struct.unpack_from('<4I', data)
    if buffers + buffer_count * 24 > len(data) or offset + count * 32 > len(data):
        raise ValueError('invalid DXBC reflection table')
    sizes = {}
    for index in range(buffer_count):
        name, _, _, size = struct.unpack_from('<4I', data, buffers + index * 24)
        sizes[_name(data, name)] = size
    result = {}
    for index in range(count):
        name, kind, returned, dimension, samples, slot, slots, flags = struct.unpack_from(
            '<8I', data, offset + index * 32)
        # Comparison samplers affect the binding. Names and usage hints can
        # differ because the engine receives the original reflection.
        key = kind, returned, dimension, samples, slot, slots, flags & 2
        result[key] = sizes.get(_name(data, name), 0)
    return result


def replace_program(original: bytes, replacement: bytes) -> bytes:
    """Use the replacement code and statistics under the original engine metadata."""
    if replacement == original:
        return original
    if profile(original) != profile(replacement):
        raise ValueError('replacement shader profile differs from the original')
    if replacement[4:20] != dxbc_checksum(replacement):
        raise ValueError('replacement DXBC checksum is invalid')

    def payloads(data: bytes) -> dict[bytes, bytes]:
        return {tag: data[at:at + size] for tag, (at, size) in chunks(data).items()}

    before, after = payloads(original), payloads(replacement)
    for tag in (b'ISGN', b'OSGN'):
        if tag not in after or _signature(before[tag]) != _signature(after[tag]):
            raise ValueError(f'{tag.decode()}: replacement signature differs from the original')
    if b'RDEF' not in after or b'STAT' not in after:
        raise ValueError('replacement requires unstripped DXBC reflection and statistics')
    original_bindings = _bindings(before[b'RDEF'])
    for binding, size in _bindings(after[b'RDEF']).items():
        if binding not in original_bindings or size > original_bindings[binding]:
            raise ValueError(f'replacement resource binding differs (type {binding[0]}, slot {binding[4]})')
    program = _program(chunks(original))
    before[program] = after[_program(chunks(replacement))]
    before[b'STAT'] = after[b'STAT']
    out = bytearray(original[:32]) + bytes(4 * len(before))
    for index, (tag, payload) in enumerate(before.items()):
        struct.pack_into('<I', out, 32 + index * 4, len(out))
        out += struct.pack('<4sI', tag, len(payload)) + payload
    struct.pack_into('<I', out, 24, len(out))
    out[4:20] = dxbc_checksum(out)
    return bytes(out)


def _compiler():
    if os.name != 'nt':
        raise ValueError('compilation and disassembly require Windows d3dcompiler_47.dll')
    return ctypes.WinDLL('d3dcompiler_47.dll', winmode=0x800)  # System32


def _take_blob(blob: ctypes.c_void_p) -> bytes:
    if not blob.value:
        return b''
    table = ctypes.cast(blob, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
    release = ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)(table[2])
    try:
        pointer = ctypes.WINFUNCTYPE(ctypes.c_void_p, ctypes.c_void_p)(table[3])
        size = ctypes.WINFUNCTYPE(ctypes.c_size_t, ctypes.c_void_p)(table[4])
        return ctypes.string_at(pointer(blob), size(blob))
    finally:
        release(blob)


def disassemble(data: bytes) -> str:
    call = _compiler().D3DDisassemble
    call.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_uint,
                     ctypes.c_char_p, ctypes.POINTER(ctypes.c_void_p)]
    call.restype = ctypes.c_long
    blob = ctypes.c_void_p()
    result = call(ctypes.create_string_buffer(data), len(data), 0, None, ctypes.byref(blob))
    output = _take_blob(blob)
    if result < 0 or not output:
        raise ValueError(f'D3DDisassemble failed: HRESULT {result & 0xffffffff:#x}')
    return output.decode('utf-8').rstrip('\0')


def compile_hlsl(path: Path, target: str, entry: str = 'main') -> bytes:
    call = _compiler().D3DCompileFromFile
    blob_ptr = ctypes.POINTER(ctypes.c_void_p)
    call.argtypes = [ctypes.c_wchar_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_char_p,
                     ctypes.c_char_p, ctypes.c_uint, ctypes.c_uint, blob_ptr, blob_ptr]
    call.restype = ctypes.c_long
    code_blob, errors = ctypes.c_void_p(), ctypes.c_void_p()
    # D3D_COMPILE_STANDARD_FILE_INCLUDE resolves includes from the source file.
    result = call(str(path.resolve()), None, 1, entry.encode('ascii'), target.encode('ascii'),
                  0, 0, ctypes.byref(code_blob), ctypes.byref(errors))
    output = _take_blob(code_blob)
    diagnostics = _take_blob(errors).rstrip(b'\0').decode('utf-8', errors='replace').strip()
    if result < 0 or not output:
        raise ValueError(diagnostics or f'D3DCompileFromFile failed: HRESULT {result & 0xffffffff:#x}')
    return output


