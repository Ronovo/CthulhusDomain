#!/bin/bash

# Make the script executable
chmod +x "$0"

# Install required packages
echo "Installing required packages..."
pip3 install Pillow
pip3 install pyinstaller
pip3 install pygame

# Check for fonts and download if needed
echo "Checking for fonts..."
if [ ! -f "fonts/CrimsonText-Regular.ttf" ]; then
    echo "Fonts not found. Downloading..."
    python3 setup_fonts.py
fi

# Generate icon
echo "Generating icon..."
python3 icon.py

# Create the spec file if it doesn't exist
if [ ! -f "build.spec" ]; then
    echo "Creating build.spec..."
    pyinstaller --name "CthulhusDominion" \
                --windowed \
                --add-data "fonts:fonts" \
                --icon "icon.icns" \
                --clean \
                --noconfirm \
                --onefile \
                "../Game_Logic/main.py"
fi

# Build the executable
echo "Building executable..."
pyinstaller --clean build.spec

# Create DMG
echo "Creating DMG..."
hdiutil create -volname "Cthulhu's Dominion" -srcfolder "dist/CthulhusDominion.app" -ov -format UDZO "dist/CthulhusDominion.dmg"

echo "Build complete!"
echo "The DMG can be found in the dist folder." 