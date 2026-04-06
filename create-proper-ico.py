#!/usr/bin/env python3
"""
Create proper Windows ICO file - Following exact ICO/DIB specification
"""

from PIL import Image
import struct
import os

def create_dib(img):
    """Create a proper DIB (Device Independent Bitmap) for ICO."""
    width, height = img.size
    pixels = img.load()
    
    # BITMAPINFOHEADER (40 bytes)
    header = struct.pack('<IiiHHIIiiII',
        40,        # Header size
        width,     # Width
        height,    # Height (just the image height)
        1,         # Planes
        32,        # Bits per pixel
        0,         # Compression (BI_RGB)
        0,         # Image size (can be 0 for BI_RGB)
        0,         # X pixels per meter
        0,         # Y pixels per meter
        0,         # Colors used
        0          # Important colors
    )
    
    # Pixel data (BGRA, bottom-to-top)
    pixel_data = bytearray()
    for y in range(height - 1, -1, -1):
        for x in range(width):
            r, g, b, a = pixels[x, y]
            pixel_data.extend([b, g, r, a])
    
    return header + pixel_data

def create_ico(png_path, ico_path):
    """Create multi-size ICO file."""
    sizes = [16, 32, 48, 64, 128, 256]
    
    # Create DIBs for each size
    dibs = []
    for size in sizes:
        img = Image.open(png_path).resize((size, size), Image.LANCZOS)
        img = img.convert('RGBA')
        dibs.append(create_dib(img))
    
    # Build ICO file
    ico_data = bytearray()
    
    # Header
    ico_data.extend(struct.pack('<HHH', 0, 1, len(sizes)))
    
    # Calculate offset
    offset = 6 + (16 * len(sizes))
    
    # Directory and data
    for i, dib in enumerate(dibs):
        size = sizes[i]
        
        # Directory entry
        ico_data.extend(struct.pack('<BBBBHHII',
            size if size < 256 else 0,  # Width
            size if size < 256 else 0,  # Height
            0,                           # Colors (0 = >= 8bpp)
            0,                           # Reserved
            1,                           # Planes
            32,                          # BPP
            len(dib),                    # Size
            offset                       # Offset
        ))
        
        # DIB data
        ico_data.extend(dib)
        offset += len(dib)
    
    # Write
    with open(ico_path, 'wb') as f:
        f.write(ico_data)
    
    return os.path.getsize(ico_path)

if __name__ == '__main__':
    png = 'screensnap-icon-preview.png'
    ico = 'screensnap.ico'
    
    if not os.path.exists(png):
        print(f"Error: {png} not found!")
        exit(1)
    
    size = create_ico(png, ico)
    print(f"Created {ico} ({size:,} bytes)")
    
    # Test it
    try:
        from PIL import Image
        img = Image.open(ico)
        print(f"SUCCESS: Valid ICO, format={img.format}, size={img.size}")
    except Exception as e:
        print(f"Still invalid: {e}")
