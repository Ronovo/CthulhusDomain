import time
from typing import Dict

from flask import Flask, abort, jsonify, render_template, request

from main import DEFAULT_DIFFICULTY, DIFFICULTIES, Game
from menu import GREAT_OLD_ONES, MAX_NAME_LENGTH, random_name

# A cycle shorter than this is too fast to animate, so its bar is drawn solid
SOLID_BAR_SECONDS = 0.25


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
        "world_end": game.show_world_end,
        "difficulty": f"{DIFFICULTIES[game.difficulty].name} ({DIFFICULTIES[game.difficulty].estimate})",
        "dream_time": format_duration(game.dream_seconds),
    }


def create_app() -> Flask:
    app = Flask(__name__)

    @app.get("/")
    def index():
        return render_template("index.html", max_name_length=MAX_NAME_LENGTH, great_old_ones=GREAT_OLD_ONES,
                               difficulties=DIFFICULTIES, default_difficulty=DEFAULT_DIFFICULTY)

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

        actions = {
            "resource": game.click_resource,
            "manager": game.hire_manager,
            "upgrade": game.buy_upgrade,
            "reset": lambda _target: game.reset_game(),
        }
        for action in body.get("actions", []):
            if isinstance(action, dict) and action.get("type") in actions:
                actions[action["type"]](str(action.get("target", "")))

        return jsonify(save=game.save_game_state(), view=build_view(game))

    return app


if __name__ == "__main__":
    create_app().run(debug=True)
