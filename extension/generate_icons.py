import struct
import zlib
from pathlib import Path

def create_png(width, height, color_rgb):
    # Minimal valid PNG generator
    def chunk(tag, data):
        return struct.pack("!I", len(data)) + tag + data + struct.pack("!I", zlib.crc32(tag + data) & 0xffffffff)

    raw_data = bytearray()
    r, g, b = color_rgb
    for _ in range(height):
        raw_data.append(0) # filter type none
        for _ in range(width):
            raw_data.extend([r, g, b])

    compressed = zlib.compress(bytes(raw_data))
    png = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack("!IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", compressed)
        + chunk(b"IEND", b"")
    )
    return png

icons_dir = Path(__file__).resolve().parent / "icons"
icons_dir.mkdir(parents=True, exist_ok=True)

# Indigo color: (99, 102, 241)
for size in [16, 48, 128]:
    png_bytes = create_png(size, size, (99, 102, 241))
    (icons_dir / f"icon{size}.png").write_bytes(png_bytes)

print("Icons created successfully.")

