"""Minimal PNG-only Pillow compatibility for the test environment."""

from __future__ import annotations

import struct
import builtins
import zlib
from pathlib import Path


_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_CACHE: dict[str, "Image"] = {}


def _paeth_predictor(a: int, b: int, c: int) -> int:
    p = a + b - c
    pa = abs(p - a)
    pb = abs(p - b)
    pc = abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    if pb <= pc:
        return b
    return c


class Image:
    def __init__(self, width: int, height: int, pixels: list[list[tuple[int, int, int, int]]]):
        self.width = width
        self.height = height
        self.pixels = pixels

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def convert(self, mode: str):
        if mode != "RGBA":
            raise ValueError(f"Unsupported mode conversion: {mode}")
        return self

    def crop(self, box):
        left, top, right, bottom = box
        cropped_rows = [row[left:right] for row in self.pixels[top:bottom]]
        return Image(right - left, bottom - top, cropped_rows)

    def getbbox(self):
        min_x = min_y = None
        max_x = max_y = None
        for y, row in enumerate(self.pixels):
            for x, pixel in enumerate(row):
                if any(channel != 0 for channel in pixel):
                    min_x = x if min_x is None else min(min_x, x)
                    min_y = y if min_y is None else min(min_y, y)
                    max_x = x if max_x is None else max(max_x, x)
                    max_y = y if max_y is None else max(max_y, y)
        if min_x is None:
            return None
        return (min_x, min_y, max_x + 1, max_y + 1)


def _decode_png(path: str) -> Image:
    with builtins.open(path, "rb") as handle:
        if handle.read(8) != _PNG_SIGNATURE:
            raise ValueError("Unsupported image format: expected PNG")

        width = height = None
        bit_depth = color_type = interlace = None
        compressed = bytearray()

        while True:
            length_bytes = handle.read(4)
            if not length_bytes:
                break
            length = struct.unpack(">I", length_bytes)[0]
            chunk_type = handle.read(4)
            chunk_data = handle.read(length)
            handle.read(4)  # CRC

            if chunk_type == b"IHDR":
                width, height, bit_depth, color_type, _comp, _flt, interlace = struct.unpack(
                    ">IIBBBBB", chunk_data
                )
            elif chunk_type == b"IDAT":
                compressed.extend(chunk_data)
            elif chunk_type == b"IEND":
                break

        if bit_depth != 8 or color_type != 6 or interlace != 0:
            raise ValueError("Only non-interlaced 8-bit RGBA PNGs are supported")

        raw = zlib.decompress(bytes(compressed))
        bytes_per_pixel = 4
        stride = width * bytes_per_pixel
        rows = []
        prev = bytearray(stride)
        offset = 0

        for _ in range(height):
            filter_type = raw[offset]
            offset += 1
            row = bytearray(raw[offset:offset + stride])
            offset += stride

            if filter_type == 1:  # Sub
                for i in range(stride):
                    left = row[i - bytes_per_pixel] if i >= bytes_per_pixel else 0
                    row[i] = (row[i] + left) & 0xFF
            elif filter_type == 2:  # Up
                for i in range(stride):
                    row[i] = (row[i] + prev[i]) & 0xFF
            elif filter_type == 3:  # Average
                for i in range(stride):
                    left = row[i - bytes_per_pixel] if i >= bytes_per_pixel else 0
                    up = prev[i]
                    row[i] = (row[i] + ((left + up) // 2)) & 0xFF
            elif filter_type == 4:  # Paeth
                for i in range(stride):
                    left = row[i - bytes_per_pixel] if i >= bytes_per_pixel else 0
                    up = prev[i]
                    up_left = prev[i - bytes_per_pixel] if i >= bytes_per_pixel else 0
                    row[i] = (row[i] + _paeth_predictor(left, up, up_left)) & 0xFF
            elif filter_type != 0:
                raise ValueError(f"Unsupported PNG filter type: {filter_type}")

            pixels = []
            for i in range(0, stride, bytes_per_pixel):
                pixels.append((row[i], row[i + 1], row[i + 2], row[i + 3]))
            rows.append(pixels)
            prev = row

        return Image(width, height, rows)


def open(path) -> Image:
    resolved = str(Path(path).resolve())
    if resolved not in _CACHE:
        _CACHE[resolved] = _decode_png(resolved)
    return _CACHE[resolved]
