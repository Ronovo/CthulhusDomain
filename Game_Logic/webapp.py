import os
import secrets
import time
from typing import Dict, Optional

from flask import Flask, abort, jsonify, render_template, request, session

from accounts import AccountError, Accounts
from achievements import ACHIEVEMENTS, PlayerRecord, new_achievements
from main import DEFAULT_DIFFICULTY, DIFFICULTIES, Game
from menu import GREAT_OLD_ONES, MAX_NAME_LENGTH, random_name

# A cycle shorter than this is too fast to animate, so its bar is drawn solid
SOLID_BAR_SECONDS = 0.25

DATA_DIR = os.environ.get("DATA_DIR", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data"))


def load_secret_key() -> str:
    """The session key from the environment, or one generated once and kept in the data folder.
    It is linked into place so two gunicorn workers starting together can't each make their own."""
    key = os.environ.get("DEAD_BUT_DREAMING_SECRET_KEY")
    if key:
        return key
    path = os.path.join(DATA_DIR, "secret_key")
    if not os.path.exists(path):
        temp = f"{path}.{os.getpid()}"
        with open(temp, "w") as f:
            f.write(secrets.token_hex(32))
        try:
            os.link(temp, path)
        except FileExistsError:
            pass
        finally:
            os.remove(temp)
    with open(path) as f:
        return f.read().strip()


def read_player_record(body: Dict) -> PlayerRecord:
    """The achievements and devour tally the browser sent, keeping only valid entries"""
    earned = body.get("achievements", [])
    if not isinstance(earned, list):
        earned = []
    devoured = body.get("devoured", {})
    if not isinstance(devoured, dict):
        devoured = {}
    return PlayerRecord(
        earned={achievement_id for achievement_id in earned
                if isinstance(achievement_id, str) and achievement_id in ACHIEVEMENTS},
        devoured={difficulty: count for difficulty, count in devoured.items()
                  if difficulty in DIFFICULTIES and isinstance(count, int) and not isinstance(count, bool)
                  and count >= 0},
    )


def format_duration(seconds: float) -> str:
    minutes, secs = divmod(int(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    days, hours = divmod(hours, 24)
    if days:
        return f"{days}d {hours:02d}h {minutes:02d}m {secs:02d}s"
    if hours:
        return f"{hours}h {minutes:02d}m {secs:02d}s"
    return f"{minutes}m {secs:02d}s"


def build_view(game: Game) -> Dict:
    """Everything the page shows, worked out here so the browser only has to display it"""
    resources = []
    for key, resource in game.resources.items():
        cycle_seconds = game.cycle_time(resource)
        resources.append({
            "key": key,
            "name": resource.name,
            "unlocked": resource.is_unlocked,
            "rate": int(game.production_rate(resource)),
            "processing": resource.is_processing,
            "progress": min(1.0, resource.progress / resource.production_time),
            "cycle_seconds": cycle_seconds,
            "solid_bar": resource.is_processing and resource.has_manager and cycle_seconds < SOLID_BAR_SECONDS,
            "unlock_cost": int(resource.unlock_cost),
            "can_unlock": game.sanity >= resource.unlock_cost,
            "manager_name": resource.manager_name,
            "manager_cost": int(resource.manager_cost),
            "has_manager": resource.has_manager,
            "can_hire": game.sanity >= resource.manager_cost,
        })

    upgrades = []
    for upgrade_id, upgrade in game.next_upgrades():
        upgrades.append({
            "id": upgrade_id,
            "name": upgrade.name,
            "description": upgrade.description,
            "type": upgrade.upgrade_type,
            "resource": upgrade.resource,
            "resource_name": game.resources[upgrade.resource].name,
            "cost": int(upgrade.cost),
            "affordable": game.sanity >= upgrade.cost,
        })

    return {
        "player_name": game.player_name,
        "sanity": int(game.sanity),
        "resources": resources,
        "upgrades": upgrades,
        "difficulty_name": DIFFICULTIES[game.difficulty].name,
        "difficulty": f"{DIFFICULTIES[game.difficulty].name} ({DIFFICULTIES[game.difficulty].estimate})",
        "dream_time": format_duration(game.dream_seconds),
        "ending": game.devoured_seconds is not None and not game.endless,
        "endless": game.endless,
        "worlds_devoured": game.worlds_destroyed,
        "devoured_time": None if game.devoured_seconds is None else format_duration(game.devoured_seconds),
    }


def create_app() -> Flask:
    app = Flask(__name__)
    os.makedirs(DATA_DIR, exist_ok=True)
    app.config.update(
        SECRET_KEY=load_secret_key(),
        # Every portfolio app shares one host name and browsers don't separate cookies by port,
        # so this app's login cookie needs a name of its own.
        SESSION_COOKIE_NAME="dead_but_dreaming_session",
        SESSION_COOKIE_SAMESITE="Lax",
        MAX_CONTENT_LENGTH=1024 * 1024,
    )
    accounts = Accounts(os.path.join(DATA_DIR, "accounts.db"))

    def current_user() -> Optional[int]:
        user_id = session.get("user_id")
        if user_id is not None and accounts.username(user_id) is None:
            session.clear()
            return None
        return user_id

    def log_in(user_id: int, username: str):
        session.clear()
        session.permanent = True
        session["user_id"] = user_id
        session["username"] = username

    def credentials():
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            abort(400)
        return str(body.get("username", "")).strip(), str(body.get("password", ""))

    @app.get("/")
    def index():
        return render_template("index.html", max_name_length=MAX_NAME_LENGTH, great_old_ones=GREAT_OLD_ONES,
                               difficulties=DIFFICULTIES, default_difficulty=DEFAULT_DIFFICULTY,
                               achievements=ACHIEVEMENTS)

    @app.get("/api/random-name")
    def api_random_name():
        return jsonify(name=random_name())

    @app.post("/api/new-game")
    def api_new_game():
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            abort(400)
        name = str(body.get("name", "")).strip()
        difficulty = body.get("difficulty", DEFAULT_DIFFICULTY)
        if not name or len(name) > MAX_NAME_LENGTH or not isinstance(difficulty, str) or difficulty not in DIFFICULTIES:
            abort(400)
        return jsonify(save=Game(name, difficulty=difficulty).save_game_state())

    # The browser sends its save and any clicks since the last call; the game catches up to now,
    # applies the clicks in order, and sends back the new save for the browser to keep.
    @app.post("/api/play")
    def api_play():
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            abort(400)
        try:
            game = Game(load_data=body["save"])
        except (KeyError, TypeError, ValueError, AttributeError):
            abort(400)
        game.advance(time.time())
        worlds_before = game.worlds_destroyed

        actions = {
            "resource": game.click_resource,
            "manager": game.hire_manager,
            "upgrade": game.buy_upgrade,
            "reset": lambda _target: game.reset_game(),
            "endless": lambda _target: game.enter_endless(),
        }
        for action in body.get("actions", []):
            if isinstance(action, dict) and action.get("type") in actions:
                actions[action["type"]](str(action.get("target", "")))

        player = read_player_record(body)
        player.devoured[game.difficulty] = (player.devoured.get(game.difficulty, 0)
                                            + game.worlds_destroyed - worlds_before)
        new = [{"id": achievement_id,
                "name": ACHIEVEMENTS[achievement_id].name,
                "description": ACHIEVEMENTS[achievement_id].description}
               for achievement_id in new_achievements(game, player)]

        save = game.save_game_state()
        user_id = current_user()
        if user_id is not None:
            accounts.store_save(user_id, save)
            accounts.store_record(user_id, player.earned, player.devoured)

        return jsonify(save=save, view=build_view(game), new_achievements=new, devoured=player.devoured)

    @app.get("/api/account")
    def api_account():
        return jsonify(username=session.get("username") if current_user() is not None else None)

    @app.post("/api/register")
    def api_register():
        username, password = credentials()
        try:
            user_id = accounts.register(username, password)
        except AccountError as error:
            return jsonify(error=str(error)), 400
        log_in(user_id, username)
        return jsonify(username=username)

    @app.post("/api/login")
    def api_login():
        username, password = credentials()
        try:
            user_id = accounts.check_login(username, password)
        except AccountError as error:
            return jsonify(error=str(error)), 401
        username = accounts.username(user_id)
        log_in(user_id, username)
        return jsonify(username=username)

    @app.post("/api/logout")
    def api_logout():
        session.clear()
        return jsonify(username=None)

    # Merges this browser's saves, achievements and devour tally into the account, and sends back
    # everything the account now holds. For saves with the same name the newer one wins.
    @app.post("/api/sync")
    def api_sync():
        user_id = current_user()
        if user_id is None:
            return jsonify(error="Not logged in"), 401
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            abort(400)
        saves = body.get("saves", {})
        if isinstance(saves, dict):
            for save in saves.values():
                try:
                    accounts.store_save(user_id, Game(load_data=save).save_game_state())
                except (KeyError, TypeError, ValueError, AttributeError):
                    continue
        player = read_player_record(body)
        accounts.store_record(user_id, player.earned, player.devoured)
        return jsonify(accounts.load(user_id))

    @app.post("/api/delete-save")
    def api_delete_save():
        user_id = current_user()
        if user_id is None:
            return jsonify(error="Not logged in"), 401
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            abort(400)
        accounts.delete_save(user_id, str(body.get("name", "")))
        return jsonify(deleted=True)

    return app


if __name__ == "__main__":
    create_app().run(debug=True)
