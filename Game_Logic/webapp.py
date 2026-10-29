import os
import secrets
import time
from typing import Dict, Optional

from flask import Flask, abort, jsonify, redirect, render_template, request, session, url_for

from ronovo_portfolio_auth import portfolio_sso
from ronovo_portfolio_auth.security_questions import QUESTIONS

from accounts import MAX_DELETED, AccountError, Accounts
from achievements import ACHIEVEMENTS, PlayerRecord, new_achievements
from main import DEFAULT_DIFFICULTY, DIFFICULTIES, WORLD_ID_PATTERN, Game
from menu import GREAT_OLD_ONES, MAX_NAME_LENGTH, random_name
from signing import Signer

# A cycle shorter than this is too fast to animate, so its bar is drawn solid
SOLID_BAR_SECONDS = 0.25

PORTFOLIO_CHOICE_SECONDS = 10 * 60
# A tick carries the clicks since the last one, four times a second, so this is far more than a person can click.
MAX_ACTIONS_PER_REQUEST = 200
EDITED_SAVE = "This save was changed outside the game, so it can't be loaded."
# What building a Game from a signed save that is missing fields or has the wrong types raises
BAD_SAVE_ERRORS = (KeyError, TypeError, ValueError, AttributeError, OverflowError)
PORTFOLIO_LOGIN_EXPIRED = "Log in with your portfolio account again."

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


def is_world_id(value) -> bool:
    return isinstance(value, str) and WORLD_ID_PATTERN.match(value) is not None


def is_devour(entry) -> bool:
    return (isinstance(entry, list) and len(entry) == 3 and is_world_id(entry[0])
            and isinstance(entry[1], int) and not isinstance(entry[1], bool) and entry[1] > 0
            and entry[2] in DIFFICULTIES)


def read_player_record(record: Optional[Dict]) -> PlayerRecord:
    """The achievements and devours from a verified record, keeping only valid entries. An unsigned or edited
    record counts as empty."""
    record = record or {}
    earned = record.get("achievements")
    devours = record.get("devours")
    return PlayerRecord(
        earned={achievement_id for achievement_id in earned if isinstance(achievement_id, str)
                and achievement_id in ACHIEVEMENTS} if isinstance(earned, list) else set(),
        devours={tuple(entry) for entry in devours if is_devour(entry)} if isinstance(devours, list) else set(),
    )


def save_rank(save: Dict) -> tuple:
    """How a stored copy of a world compares with another: more progress wins, then the newer one."""
    return Game(load_data=save).progress() + (save["last_saved"],)


def save_started(save: Dict) -> float:
    return Game(load_data=save).started_at()


def progress_marker(game: Game) -> tuple:
    """Changes only when something is unlocked, hired, bought or devoured, which is when a
    logged-in player's progress is written to their account straight away"""
    return (
        tuple(resource.is_unlocked for resource in game.resources.values()),
        tuple(resource.has_manager for resource in game.resources.values()),
        tuple(upgrade.purchased for upgrade in game.upgrade_manager.upgrades.values()),
        game.devoured_seconds is not None,
        game.endless,
        game.worlds_destroyed,
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
        SESSION_COOKIE_SECURE=os.environ.get("SECURE_COOKIES") == "1",
        MAX_CONTENT_LENGTH=1024 * 1024,
    )
    accounts = Accounts(os.path.join(DATA_DIR, "accounts.db"))

    def current_user() -> Optional[int]:
        user_id = session.get("user_id")
        if user_id is None:
            return None
        key = accounts.session_key(user_id)
        if key is None or not secrets.compare_digest(session.get("session_key", ""), key):
            session.clear()
            return None
        return user_id

    def log_in(user_id: int, username: str):
        session.clear()
        session.permanent = True
        session["user_id"] = user_id
        session["username"] = username
        session["session_key"] = accounts.session_key(user_id)

    signer = Signer(app.config["SECRET_KEY"])

    def json_body() -> Dict:
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            abort(400)
        return body

    def signed_record(player: PlayerRecord) -> Dict:
        return signer.sign({"achievements": sorted(player.earned), "devours": sorted(player.devours)})

    def credentials():
        body = json_body()
        return str(body.get("username", "")).strip(), str(body.get("password", ""))

    # The first portfolio login here asks whether to link an account the player already has or make a new one,
    # so it waits in the session until they choose.
    def portfolio_login(account: Dict):
        user_id = accounts.linked_user(account["sub"])
        if user_id is None:
            session.clear()
            session["portfolio_pending"] = {"sub": account["sub"], "username": account["username"],
                                         "expires": time.time() + PORTFOLIO_CHOICE_SECONDS}
        else:
            log_in(user_id, accounts.username(user_id))
        return redirect(url_for("index"))

    def portfolio_pending() -> Optional[Dict]:
        pending = session.get("portfolio_pending")
        return pending if pending and pending["expires"] > time.time() else None

    def logged_in(user_id: int) -> Dict:
        username = accounts.username(user_id)
        log_in(user_id, username)
        return jsonify(username=username)

    portfolio_sso.add_flask_routes(app, "dead-but-dreaming", portfolio_login)

    @app.get("/")
    def index():
        return render_template("index.html", max_name_length=MAX_NAME_LENGTH, great_old_ones=GREAT_OLD_ONES,
                               difficulties=DIFFICULTIES, default_difficulty=DEFAULT_DIFFICULTY,
                               achievements=ACHIEVEMENTS, portfolio=portfolio_sso.enabled(), questions=QUESTIONS,
                               portfolio_url=portfolio_sso.portfolio_url() if portfolio_sso.enabled() else "")

    @app.post("/api/portfolio/link")
    def api_portfolio_link():
        pending = portfolio_pending()
        if pending is None:
            return jsonify(error=PORTFOLIO_LOGIN_EXPIRED), 400
        username, password = credentials()
        try:
            user_id = accounts.check_login(username, password)
            accounts.link_portfolio(user_id, pending["sub"])
        except AccountError as error:
            return jsonify(error=str(error)), 400
        return logged_in(user_id)

    @app.post("/api/portfolio/new")
    def api_portfolio_new():
        pending = portfolio_pending()
        if pending is None:
            return jsonify(error=PORTFOLIO_LOGIN_EXPIRED), 400
        return logged_in(accounts.portfolio_user(pending["sub"], pending["username"]))

    @app.get("/api/random-name")
    def api_random_name():
        return jsonify(name=random_name())

    @app.post("/api/new-game")
    def api_new_game():
        body = json_body()
        name = str(body.get("name", "")).strip()
        difficulty = body.get("difficulty", DEFAULT_DIFFICULTY)
        if not name or len(name) > MAX_NAME_LENGTH or not isinstance(difficulty, str) or difficulty not in DIFFICULTIES:
            abort(400)
        return jsonify(save=signer.sign(Game(name, difficulty=difficulty).save_game_state()))

    # The browser sends its save and any clicks since the last call; the game catches up to now,
    # applies the clicks in order, and sends back the new save for the browser to keep.
    @app.post("/api/play")
    def api_play():
        body = json_body()
        save = signer.verify(body.get("save"))
        if save is None:
            return jsonify(error=EDITED_SAVE), 400
        try:
            game = Game(load_data=save)
        except BAD_SAVE_ERRORS:
            abort(400)
        game.advance(time.time())
        progress_before = progress_marker(game)

        actions = {
            "resource": game.click_resource,
            "manager": game.hire_manager,
            "upgrade": game.buy_upgrade,
            "reset": lambda _target: game.reset_game(),
            "endless": lambda _target: game.enter_endless(),
        }
        requested = body.get("actions", [])
        for action in requested[:MAX_ACTIONS_PER_REQUEST] if isinstance(requested, list) else []:
            if isinstance(action, dict) and action.get("type") in actions:
                actions[action["type"]](str(action.get("target", "")))

        player = read_player_record(signer.verify(body.get("record")))
        player.devours.update(game.devoured_now)
        new = [{"id": achievement_id,
                "name": ACHIEVEMENTS[achievement_id].name,
                "description": ACHIEVEMENTS[achievement_id].description}
               for achievement_id in new_achievements(game, player)]

        # A logged-in account is written on the browser's 30 second backup and on real progress;
        # every other tick leaves the database alone.
        save = game.save_game_state()
        if body.get("backup") is True or new or progress_marker(game) != progress_before:
            user_id = current_user()
            if user_id is not None:
                accounts.store_save(user_id, save, save_rank, save_started)
                accounts.store_record(user_id, player.earned, player.devours)

        return jsonify(save=signer.sign(save), view=build_view(game), new_achievements=new,
                       record=signed_record(player))

    @app.get("/api/account")
    def api_account():
        pending = portfolio_pending()
        return jsonify(username=session.get("username") if current_user() is not None else None,
                       portfolio_pending=pending["username"] if pending else None)

    @app.post("/api/register")
    def api_register():
        username, password = credentials()
        body = json_body()
        try:
            user_id = accounts.register(username, password, str(body.get("question", "")), str(body.get("answer", "")))
        except AccountError as error:
            return jsonify(error=str(error)), 400
        return logged_in(user_id)

    @app.post("/api/login")
    def api_login():
        username, password = credentials()
        try:
            user_id = accounts.check_login(username, password)
        except AccountError as error:
            return jsonify(error=str(error)), 401
        return logged_in(user_id)

    @app.post("/api/reset-question")
    def api_reset_question():
        username = str(json_body().get("username", "")).strip()
        if not username:
            return jsonify(error="Enter your username"), 400
        try:
            return jsonify(question=accounts.security_question(username))
        except AccountError as error:
            return jsonify(error=str(error)), 400

    @app.post("/api/reset-password")
    def api_reset_password():
        username, password = credentials()
        try:
            accounts.reset_password(username, str(json_body().get("answer", "")), password)
        except AccountError as error:
            return jsonify(error=str(error)), 400
        return jsonify(reset=True)

    @app.post("/api/logout")
    def api_logout():
        session.clear()
        return jsonify(username=None)

    # Applies the worlds this browser deleted, merges its saves, achievements and devours into the account, and
    # sends back everything the account now holds, plus the ids of deleted worlds so the browser drops its copies.
    # A browser that is closing asks for no reply.
    @app.post("/api/sync")
    def api_sync():
        user_id = current_user()
        if user_id is None:
            return jsonify(error="Not logged in"), 401
        body = json_body()
        deleted = body.get("deleted", [])
        if isinstance(deleted, list):
            accounts.delete_worlds(user_id, [world_id for world_id in deleted[:MAX_DELETED] if is_world_id(world_id)])
        saves = body.get("saves", {})
        if isinstance(saves, dict):
            for save in saves.values():
                save = signer.verify(save)
                if save is None:
                    continue
                try:
                    accounts.store_save(user_id, Game(load_data=save).save_game_state(), save_rank, save_started)
                except BAD_SAVE_ERRORS:
                    continue
        player = read_player_record(signer.verify(body.get("record")))
        accounts.store_record(user_id, player.earned, player.devours)
        if body.get("reply") is False:
            return "", 204
        stored = accounts.load(user_id)
        record = PlayerRecord(earned=set(stored["achievements"]), devours=set(stored["devours"]))
        return jsonify(saves={name: signer.sign(save) for name, save in stored["saves"].items()},
                       deleted=stored["deleted"], record=signed_record(record))

    return app


if __name__ == "__main__":
    create_app().run()
