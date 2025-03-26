from PIL import Image, ImageDraw
import math
import os

def create_icon(size):
    # Create a square image with transparency
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Colors
    PURPLE = (128, 0, 128, 255)
    DARK_PURPLE = (64, 0, 64, 255)
    LIGHT_PURPLE = (192, 0, 192, 255)
    GREEN = (0, 255, 0, 255)
    DARK_GREEN = (0, 100, 0, 255)
    LIGHT_GREEN = (100, 255, 100, 255)
    BLACK = (0, 0, 0, 255)

    # Draw the main head shape (octopus-like)
    center_x = size // 2
    center_y = size // 2
    radius = size // 3

    # Draw the main head circle with gradient effect
    for i in range(radius, 0, -1):
        color = (
            int(128 + (i/radius) * 64),  # R
            0,                            # G
            int(128 + (i/radius) * 64),  # B
            255                          # A
        )
        draw.ellipse([center_x - i, center_y - i, 
                     center_x + i, center_y + i], 
                    outline=color)

    # Draw tentacles with more detail
    tentacle_points = [
        (center_x - radius//2, center_y - radius//2),
        (center_x + radius//2, center_y - radius//2),
        (center_x - radius//2, center_y + radius//2),
        (center_x + radius//2, center_y + radius//2)
    ]

    for x, y in tentacle_points:
        # Draw main tentacle
        points = []
        for i in range(5):
            points.append((x + (i-2)*20, y + (i-2)*20))
        draw.line(points, fill=DARK_PURPLE, width=15)
        
        # Draw tentacle suckers
        for i in range(4):
            sucker_x = x + (i-1.5)*20
            sucker_y = y + (i-1.5)*20
            draw.ellipse([sucker_x - 5, sucker_y - 5,
                         sucker_x + 5, sucker_y + 5],
                        fill=LIGHT_PURPLE, outline=DARK_PURPLE)

    # Draw eyes with more detail
    eye_radius = radius // 4
    # Main eye
    draw.ellipse([center_x - eye_radius, center_y - eye_radius,
                  center_x + eye_radius, center_y + eye_radius],
                 fill=GREEN, outline=DARK_GREEN)

    # Eye pupil
    pupil_radius = eye_radius // 2
    draw.ellipse([center_x - pupil_radius, center_y - pupil_radius,
                  center_x + pupil_radius, center_y + pupil_radius],
                 fill=DARK_GREEN)

    # Eye highlight
    highlight_radius = pupil_radius // 3
    highlight_x = center_x - pupil_radius // 2
    highlight_y = center_y - pupil_radius // 2
    draw.ellipse([highlight_x - highlight_radius, highlight_y - highlight_radius,
                  highlight_x + highlight_radius, highlight_y + highlight_radius],
                 fill=LIGHT_GREEN)

    # Draw some wrinkle details
    for i in range(3):
        wrinkle_y = center_y - radius//2 + (i+1)*radius//3
        wrinkle_points = []
        for x in range(center_x - radius//2, center_x + radius//2, 10):
            wrinkle_points.append((x, wrinkle_y + math.sin(x/20)*5))
        draw.line(wrinkle_points, fill=DARK_PURPLE, width=2)

    # Add some ambient glow
    glow_radius = radius + 10
    draw.ellipse([center_x - glow_radius, center_y - glow_radius,
                  center_x + glow_radius, center_y + glow_radius],
                 outline=(128, 0, 128, 100), width=2)

    return img

def main():
    # Create icons of different sizes
    sizes = [16, 32, 64, 128, 256, 512, 1024]
    icons = []
    
    for size in sizes:
        icons.append(create_icon(size))
    
    # Save as ICO (Windows)
    icons[0].save('icon.ico', format='ICO', sizes=[(s, s) for s in sizes])
    
    # Save individual PNG files for macOS
    if not os.path.exists('icon.iconset'):
        os.makedirs('icon.iconset')
    
    for i, size in enumerate(sizes):
        icons[i].save(f'icon.iconset/icon_{size}x{size}.png')
        if size <= 512:  # Also create @2x versions for retina displays
            icons[i].save(f'icon.iconset/icon_{size//2}x{size//2}@2x.png')
    
    # Convert to icns using iconutil (macOS only)
    if os.name != 'nt':  # Only on macOS
        os.system('iconutil -c icns icon.iconset')
        # Clean up the iconset directory
        os.system('rm -rf icon.iconset')

if __name__ == '__main__':
    main() 