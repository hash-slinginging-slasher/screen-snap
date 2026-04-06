#!/usr/bin/env python3
"""
Simple ICO creator - Creates proper Windows ICO file from PNG
"""

from PIL import Image
import struct
import os

def create_ico_from_png(png_path, ico_path, sizes=[16, 32, 48, 64, 128, 256]):
    """Create multi-size ICO file from PNG."""
    # Load and resize images
    images = []
    for size in sizes:
        img = Image.open(png_path)
        img = img.resize((size, size), Image.LANCZOS)
        img = img.convert('RGBA')
        images.append(img)
    
    # Build ICO file
    ico_data = bytearray()
    
    # Header: reserved(2) + type(2) + count(2)
    ico_data.extend(struct.pack('<HHH', 0, 1, len(images)))
    
    # Calculate offset (header + directory entries)
    offset = 6 + (16 * len(images))
    
    # Directory entries and image data
    for img in images:
        width, height = img.size
        
        # Create BMP data (without file header)
        # ICO uses BITMAPINFO format stored bottom-to-top
        bmp_data = bytearray()
        
        # Get pixels
        pixels = img.load()
        
        # BMP stores rows bottom-to-top
        for y in range(height - 1, -1, -1):
            row = bytearray()
            for x in range(width):
                r, g, b, a = pixels[x, y]
                # BMP format: BGRA
                row.extend([b, g, r, a])
            # Pad to 4-byte boundary
            while len(row) % 4 != 0:
                row.append(0)
            bmp_data.extend(row)
        
        # AND mask (1 bit per pixel, rounded to 4 bytes per row)
        and_mask_row_size = ((width + 31) // 32) * 4
        and_mask = b'\x00' * (and_mask_row_size * height)
        
        # Directory entry
        ico_data.extend(struct.pack('<BBBBHHII',
            width if width < 256 else 0,      # Width
            height if height < 256 else 0,    # Height  
            0,                                 # Color count (0 for >= 8bpp)
            0,                                 # Reserved
            1,                                 # Color planes
            32,                                # Bits per pixel
            len(bmp_data) + len(and_mask),    # Size in bytes
            offset                             # File offset
        ))
        
        # Image data
        ico_data.extend(bmp_data)
        ico_data.extend(and_mask)
        offset += len(bmp_data) + len(and_mask)
    
    # Write file
    with open(ico_path, 'wb') as f:
        f.write(ico_data)
    
    return os.path.getsize(ico_path)

if __name__ == '__main__':
    png = 'screensnap-icon-preview.png'
    ico = 'screensnap.ico'
    
    if not os.path.exists(png):
        print(f"Error: {png} not found!")
        exit(1)
    
    size = create_ico_from_png(png, ico)
    print(f"Created {ico} ({size:,} bytes)")
    
    # Verify it can be opened
    try:
        from PIL import Image
        img = Image.open(ico)
        print(f"Verified: {img.format} format, first size: {img.size}")
    except Exception as e:
        print(f"Warning: Could not verify ICO: {e}")
