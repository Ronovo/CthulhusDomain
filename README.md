# Cthulhu's Dominion

A Lovecraftian idle game where you play as a Great Old One, commanding cultists to gather eldritch resources and expand your influence across multiple worlds.

## Features
- Choose from 9 different Great Old Ones to play as (or create your own name)
- 10 different eldritch resources to collect and manage
- Animated progress bars for resource gathering
- Intelligent UI that adapts to resource speed (solid bars for fast resources)
- Manager upgrades to automate resource collection
- Two types of upgrades per resource:
  - Speed upgrades (2x, 3x, 5x)
  - Production upgrades (2x, 5x)
- Multiple world system:
  - Complete all upgrades to devour the current world
  - Choose to let Azathoth reset the world for a new run
  - Track how many worlds you've destroyed
- Automatic save system
- Load previous games

## Project Structure
```
Idle Vibes/
├── Game_Logic/           # Main game source code
│   ├── main.py          # Main game entry point
│   ├── menu.py          # Menu system
│   └── upgrades.py      # Upgrade management
└── Install_Files/       # Build and setup files
    ├── build.bat        # Windows build script
    ├── build_mac.command # Mac build script
    ├── build.spec       # PyInstaller spec file
    ├── generate_icon.bat # Icon generation script
    ├── icon.py          # Icon generation code
    ├── setup_fonts.py   # Font setup script
    └── requirements.txt # Python dependencies
```

## Requirements
- Python 3.8+
- Pygame 2.5.2
- PyInstaller (for building executables)
- Xcode Command Line Tools (for Mac builds)
- Pillow (for icon generation)

## Installation

### Running from Source
1. Clone this repository
2. Install Pygame:
```bash
python -m pip install --index-url https://pypi.org/simple/ --no-deps pygame
```
3. Run the game:
```bash
python Game_Logic/main.py
```

### Building Executables

#### Windows
1. Navigate to the Install_Files directory
2. Run the build script:
```bash
build.bat
```
3. The executable will be created in the `dist` folder as `CthulhusDominion.exe`

#### Mac
1. Install Xcode Command Line Tools if not already installed:
```bash
xcode-select --install
```

2. Navigate to the Install_Files directory:
```bash
cd Install_Files
```

3. Make the build script executable:
```bash
chmod +x build_mac.command
```

4. Run the build script:
```bash
./build_mac.command
```

5. The DMG will be created in the `dist` folder as `CthulhusDominion.dmg`

Note: The build process will automatically:
- Install required packages (Pillow, PyInstaller, Pygame)
- Download the required Crimson Text font
- Generate the game icon
- Create the executable/DMG

### Troubleshooting
If you encounter any issues:

1. Make sure all prerequisites are installed
2. For Mac builds, verify Xcode Command Line Tools are installed:
```bash
xcode-select --install
```
3. Check that you have write permissions in the directory
4. If the build fails, try cleaning the build directories:
   - Windows: Delete the `build` and `dist` folders
   - Mac: Run `rm -rf build dist` before rebuilding

## How to Play
- Click on resources to start gathering them
- Purchase managers to automate resource collection
- Buy upgrades to increase speed and production
- Complete all upgrades to devour the world
- Choose to continue in infinite mode or reset for a new world
- Track your progress with the Worlds Destroyed counter

## Game Mechanics
- Resources with managers automatically start producing when loaded
- Fast resources (first 5) show solid progress bars when speed exceeds 6x
- Each resource has 5 upgrades to discover
- Managers continue production automatically
- Auto-save every 60 seconds 