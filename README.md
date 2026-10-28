# Dead But Dreaming

*In his house at R'lyeh dead Cthulhu waits dreaming.*

You are an Old One, inert and buried deep beneath the earth. You cannot move and you cannot wake, but you can dream, and your dreams reach the surface. Cultists answer them. Tomes are written, sacrifices are made, rituals are performed and gates are opened, and every scrap of sanity the world loses flows down to you. Gather enough and you will devour the world and be reborn. Then Azathoth spins up a fresh worldline, and the dreaming begins again.

It runs in the browser on a Python/Flask server.

## Features
- Choose from 9 different Great Old Ones to play as (or create your own name)
- 10 different eldritch resources to collect and manage
- Animated progress bars for resource gathering
- Manager upgrades to automate resource collection
- Two types of upgrades per resource:
  - Speed upgrades (2x, 3x, 5x)
  - Production upgrades (2x, 5x)
- Multiple world system:
  - Complete all upgrades to devour the current world
  - Choose to let Azathoth reset the world for a new run
  - Your save counts how many worlds you've destroyed
- Saves are kept in your browser, and the game catches up on the time it was closed

## How it works
The game logic is Python. The browser keeps the save and shows the game; it doesn't run any of the rules.

1. The browser stores each save as JSON in `localStorage`, including when it was last saved.
2. About four times a second, and whenever you click, the browser sends its save and your clicks to `POST /api/play`.
3. Flask rebuilds the `Game` from the save, advances it by the time since `last_saved`, applies the clicks, and sends back the new save plus what to display. Time spent with the game closed is covered by that same step: resources with a manager keep producing, and a resource you clicked by hand finishes its one cycle.

## Project Structure
```
Dead-But-Dreaming/
├── Game_Logic/
│   ├── main.py          # Game state, resources, production and saves
│   ├── upgrades.py      # Upgrade management
│   ├── menu.py          # Great Old One names
│   ├── webapp.py        # Flask app and API
│   ├── templates/       # Page markup
│   └── static/          # CSS, display script, font, icon
├── docker/git-sync.sh   # Pulls the latest code when the container starts
├── Dockerfile
├── docker-compose.yml   # Local testing
└── requirements.txt
```

## Running

### From source
Requires Python 3.10+.
```bash
pip install -r requirements.txt
python Game_Logic/webapp.py
```
Then open http://localhost:5000.

### With Docker
```bash
docker compose up -d --build
```
Then open http://localhost:8005. The local compose file runs your working copy as-is.

When `REPO_URL` is set (the image sets it to this repository), the container updates itself from GitHub every time it starts: the first start fetches `main` over the code baked into the image, and later starts pull again. If GitHub can't be reached it starts with the code it already has. To pick up new commits on a running container, restart it.

## How to Play
- Click on resources to start gathering them
- Purchase managers to automate resource collection
- Buy upgrades to increase speed and production
- Complete all upgrades to devour the world
- Choose to continue in infinite mode or reset for a new world

## Game Mechanics
- Resources with managers produce automatically, including while the game is closed
- Each resource has 5 upgrades to discover
- The game saves to your browser continuously while you play
