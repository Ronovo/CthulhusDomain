@echo off
echo Installing Pillow...
pip install Pillow

echo Installing required packages...
pip install pyinstaller
pip install pygame

echo Checking for fonts...
if not exist "fonts\CrimsonText-Regular.ttf" (
    echo Fonts not found. Downloading...
    python setup_fonts.py
)

echo Generating icon...
python icon.py

echo Cleaning previous build...
rmdir /s /q build 2>nul
rmdir /s /q dist 2>nul

echo Building executable...
pyinstaller --clean build.spec

echo Build complete!
echo The executable can be found in the dist folder.
pause 