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
- Four difficulties, from Quick and Easy (about 15-20 minutes) to an eternal run
- Multiple world system:
  - Buy every upgrade and hire every manager to devour the current world
  - Then keep going in Endless Mode, or let Azathoth reset the world for a new run
  - Your save counts how many worlds you've destroyed
- Achievements, and nine style themes for the page
- Saves are kept in your browser, and the game catches up on the time it was closed
- Optional accounts, so progress follows you to other browsers

## How it works
The game logic is Python. The browser keeps the save and shows the game; it doesn't run any of the rules.

1. The browser stores each save as JSON in `localStorage`, including when it was last saved.
2. About four times a second, and whenever you click, the browser sends its save and your clicks to `POST /api/play`.
3. Flask rebuilds the `Game` from the save, advances it by the time since `last_saved`, applies the clicks, and sends back the new save plus what to display. Time spent with the game closed is covered by that same step: resources with a manager keep producing, and a resource you clicked by hand finishes its one cycle.

## Accounts
Logging in is optional. Without it, everything stays in the browser. With it, progress follows you to any browser you log in from:

- Logging in merges this browser's saves, achievements and devour counts with the account's. For saves with the same name the one played most recently wins, by when it was last open, not by how far along it is; devour counts keep the higher number for each difficulty.
- While logged in, saves are copied to the account whenever progress changes, every 30 seconds, and when you leave the page. Deleting a world deletes it from the account too, though another browser that still holds a copy uploads it again the next time it logs in.
- Logging out keeps this browser's copy. On a shared browser, the next account to log in doesn't get it: saves that came from one account are cleared from the browser when a different account logs in, and stay in their own account. Saves made while logged out join whichever account logs in next.
- Five wrong passwords in a row lock a username's logins for a minute, and a password reset logs the account out of every other browser.
- Creating an account asks for a security question. **Forgot Password** resets the password with its answer, and
  five wrong answers lock resets for 15 minutes.

With `PORTFOLIO_SSO_URL` (the portfolio's address) and `PORTFOLIO_SSO_PUBLIC_KEY`
(printed by the portfolio's `python sso.py`) set, the top bar offers to log in with a portfolio account. It reads
**Log In as** and the portfolio username when this browser is logged in to the portfolio. The first portfolio
login here asks whether to link a Dead But Dreaming account the player already has, by logging in to it once,
or to make a new one named after the portfolio username, with a number added if that name is taken. Every later
portfolio login from any device opens the linked account. A new account has no password of its own, so the
portfolio is the only way into it. Without those two settings the app runs on its own.

Accounts are kept in a SQLite database in the data folder (`DATA_DIR`, `/app/data` in the container). Passwords are stored as salted hashes.

### Security caveats
- **Unencrypted connections:** unless the site is served over HTTPS, passwords cross the network in plain text. The login screen warns about this whenever the page isn't on HTTPS. Use a password you don't use anywhere else.
- **Saves come from the browser:** the server rebuilds the game from the save the browser sends and doesn't check it, so a player can edit their own save, progress and achievements.
- **Security answers:** anyone who knows or can guess your answer can reset your password, so pick an answer that isn't public.

## Project Structure
```
Dead-But-Dreaming/
├── Game_Logic/
│   ├── main.py          # Game state, resources, production and saves
│   ├── upgrades.py      # Upgrade management
│   ├── menu.py          # Great Old One names
│   ├── achievements.py  # Achievement definitions and checks
│   ├── accounts.py      # Optional logins and account storage
│   ├── webapp.py        # Flask app and API
│   ├── templates/       # Page markup
│   └── static/          # CSS, display script, font, icon
├── docker/git-sync.sh   # Pulls the latest code when the container starts
├── Dockerfile
├── docker-compose.yml   # Local testing
└── requirements.txt     # Flask, PyJWT and ronovo-portfolio-auth (portfolio login, security questions, login lock)
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
Then open http://localhost:8005. The local compose file runs your working copy as-is, and keeps accounts in the `dead-but-dreaming-data` volume.

Logins are signed with `DEAD_BUT_DREAMING_SECRET_KEY`. If it isn't set, a key is generated once and kept in the data folder, so set it explicitly when the data folder isn't kept between runs.

When `REPO_URL` is set (the image sets it to this repository), the container updates itself from GitHub every time it starts: the first start fetches `main` over the code baked into the image, and later starts pull again. When that commit hasn't been built yet it reinstalls `requirements.txt` first, and a failed install is tried again on the next start. If GitHub can't be reached it starts with the code it already has. To pick up new commits on a running container, restart it.

| Variable | What it does | Default in the image |
| --- | --- | --- |
| `REPO_URL` | The repo to pull. Set it empty to run exactly what is in the image. | This repo on GitHub |
| `REPO_BRANCH` | Branch to pull | `main` |
| `SYNC_DIR` | Folder the code is pulled into | The app folder |
| `BUILD_CMD` | Runs after pulling a commit that hasn't been built yet | `pip install -r requirements.txt` |

## How to Play
- Click on resources to start gathering them
- Purchase managers to automate resource collection
- Buy upgrades to increase speed and production
- Buy every upgrade and hire every manager to devour the world
- Choose to continue in Endless Mode or reset for a new world

## Game Mechanics
- Resources with managers produce automatically, including while the game is closed
- Each resource has 5 upgrades to discover
- The game saves to your browser continuously while you play
