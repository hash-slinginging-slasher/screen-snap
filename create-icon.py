#!/usr/bin/env python3
"""
Create ScreenSnap icon - Monitor with lightning bolt (proper ICO format)
"""

from PIL import Image, ImageDraw
import io
import struct

def create_icon_image(size):
    """Create icon at given size."""
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    # Calculate dimensions
    margin = size // 8
    screen_left = margin
    screen_top = margin
    screen_right = size - margin
    screen_bottom = size - margin - (size // 6)
    
    # Draw monitor screen (gradient blue background)
    screen_color = (40, 60, 100, 255)
    draw.rectangle(
        [screen_left, screen_top, screen_right, screen_bottom],
        fill=screen_color
    )
    
    # Draw screen border (brighter blue)
    border_color = (100, 160, 220, 255)
    border_width = max(2, size // 32)
    draw.rectangle(
        [screen_left, screen_top, screen_right, screen_bottom],
        outline=border_color,
        width=border_width
    )
    
    # Draw monitor stand
    stand_width = size // 4
    stand_height = size // 6
    stand_left = (size - stand_width) // 2
    stand_top = screen_bottom
    stand_right = stand_left + stand_width
    stand_bottom = stand_top + stand_height
    
    stand_color = (90, 120, 150, 255)
    draw.rectangle(
        [stand_left, stand_top, stand_right, stand_bottom],
        fill=stand_color
    )
    
    # Draw stand base
    base_width = int(stand_width * 1.6)
    base_height = stand_height // 2
    base_left = (size - base_width) // 2
    base_top = stand_bottom
    base_right = base_left + base_width
    base_bottom = base_top + base_height
    
    draw.rectangle(
        [base_left, base_top, base_right, base_bottom],
        fill=stand_color
    )
    
    # Draw lightning bolt (bright yellow)
    center_x = size // 2
    bolt_width = size // 4
    bolt_height = size // 2
    bolt_top = screen_top + (screen_bottom - screen_top) // 4
    bolt_bottom = bolt_top + bolt_height
    
    # Lightning bolt points
    bolt_points = [
        (center_x, bolt_top),                                    # Top point
        (center_x - bolt_width // 2, bolt_top + bolt_height // 3), # Left upper
        (center_x - bolt_width // 6, bolt_top + bolt_height // 3), # Inner left
        (center_x - bolt_width // 3, bolt_bottom),               # Bottom point
        (center_x + bolt_width // 2, bolt_top + bolt_height * 2 // 3), # Right lower
        (center_x + bolt_width // 6, bolt_top + bolt_height * 2 // 3), # Inner right
    ]
    
    # Draw lightning bolt
    bolt_color = (255, 220, 50, 255)
    bolt_outline = (255, 180, 0, 255)
    draw.polygon(bolt_points, fill=bolt_color, outline=bolt_outline)
    
    return img


def create_proper_ico(images, output_path):
    """Create a proper Windows ICO file with BMP-encoded images."""
    # ICO header
    header = struct.pack('<HHH', 0, 1, len(images))
    
    directory = b''
    image_data = b''
    offset = 6 + (16 * len(images))
    
    for img in images:
        width = img.width
        height = img.height
        
        # Create BMP data for the icon (XOR mask)
        # ICO expects bottom-up BMP format
        img_bmp = img.copy()
        
        # Convert to 32-bit with proper alpha
        img_rgba = img_bmp.convert('RGBA')
        pixels = img_rgba.load()
        
        # Create BMP data (without header)
        # BMP row size must be multiple of 4 bytes
        row_size = ((width * 4 + 3) // 4) * 4
        
        # BMP data is stored bottom-to-top
        bmp_data = bytearray()
        for y in range(height - 1, -1, -1):
            row = bytearray()
            for x in range(width):
                r, g, b, a = pixels[x, y]
                # BMP format: BGRA
                row.extend([b, g, r, a])
            # Pad row to 4-byte boundary
            while len(row) % 4 != 0:
                row.append(0)
            bmp_data.extend(row)
        
        # AND mask (1 bit per pixel, all 0 for fully opaque)
        and_mask_row_size = ((width + 31) // 32) * 4
        and_mask = b'\x00' * (and_mask_row_size * height)
        
        xor_mask_size = len(bmp_data)
        total_size = xor_mask_size + len(and_mask)
        
        # Directory entry
        directory += struct.pack('<BBBBHHII',
            width if width < 256 else 0,
            height if height < 256 else 0,
            0,  # Color palette (0 for 32-bit)
            0,  # Reserved
            1,  # Color planes
            32,  # Bits per pixel
            total_size,
            offset
        )
        
        image_data += bytes(bmp_data) + and_mask
        offset += total_size
    
    # Write ICO file
    with open(output_path, 'wb') as f:
        f.write(header + directory + image_data)
    
    return offset  # Return file size


def main():
    """Create icon at multiple sizes and save as .ico."""
    # Standard icon sizes
    sizes = [16, 32, 48, 64, 128, 256]
    
    images = []
    for size in sizes:
        img = create_icon_image(size)
        images.append(img)
        print(f"Created {size}x{size} icon")
    
    # Save as multi-size .ico file
    ico_path = 'screensnap.ico'
    file_size = create_proper_ico(images, ico_path)
    
    # Get actual file size
    import os
    actual_size = os.path.getsize(ico_path)
    print(f"\nIcon saved to: {ico_path} ({actual_size:,} bytes)")
    
    # Also save a PNG preview
    preview = create_icon_image(256)
    preview_path = 'screensnap-icon-preview.png'
    preview.save(preview_path)
    preview_size = os.path.getsize(preview_path)
    print(f"Preview saved to: {preview_path} ({preview_size:,} bytes)")


if __name__ == '__main__':
    main()
