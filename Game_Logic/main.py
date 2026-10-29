import re
import secrets
import time
from dataclasses import dataclass
from typing import Dict, List, Tuple
from upgrades import Upgrade, UpgradeManager

# Fields a save sets on a resource; the save comes from the browser, so nothing else is accepted
SAVED_RESOURCE_FIELDS = {
    "has_manager": bool,
    "is_unlocked": bool,
    "is_processing": bool,
    "progress": float,
}

# Every new world gets its own id, so two worlds with the same name are never mistaken for one another
WORLD_ID_PATTERN = re.compile(r"^[0-9a-f]{16}$")


def new_world_id() -> str:
    return secrets.token_hex(8)


@dataclass
class Difficulty:
    name: str
    estimate: str
    growth: float  # Costs on tier n are multiplied by growth ** n, so tier 1 is the same on every difficulty

DIFFICULTIES = {
    "quick": Difficulty("Quick and Easy", "about 15-20 min", 0.62),
    "recommended": Difficulty("Recommended", "about 4-5 hours", 1.0),
    "long_haul": Difficulty("Long Haul", "about 20 hours", 1.23),
    "eternal": Difficulty("Eternal", "about 60-80 hours", 1.45),
}
DEFAULT_DIFFICULTY = "recommended"

def round_cost(cost: float) -> float:
    """Round to 2 significant figures so scaled prices stay readable"""
    return float(f"{cost:.2g}")

@dataclass
class Resource:
    key: str
    name: str
    base_production: float
    production_time: float
    manager_name: str
    unlock_cost: float
    manager_cost: float
    progress: float = 0
    is_processing: bool = False
    has_manager: bool = False
    is_unlocked: bool = False

def new_resources() -> Dict[str, Resource]:
    """A world's resources before any difficulty scaling, with only Cultists unlocked."""
    resources = [
        Resource("cultists", "Cultists", 1, 2.0, "Cult Leader", 5, 10, is_unlocked=True),
        Resource("ancient_tomes", "Ancient Tomes", 5, 3.0, "Mad Librarian", 30, 60),
        Resource("eldritch_artifacts", "Eldritch Artifacts", 15, 4.0, "Relic Hunter", 200, 400),
        Resource("sacrifices", "Sacrifices", 50, 5.0, "High Priest", 1500, 3000),
        Resource("dark_rituals", "Dark Rituals", 200, 6.0, "Ritual Master", 10000, 20000),
        Resource("cosmic_energy", "Cosmic Energy", 750, 7.0, "Star Priest", 75000, 150000),
        Resource("elder_signs", "Elder Signs", 3000, 8.0, "Sign Keeper", 500000, 1000000),
        Resource("dimensional_gates", "Dimensional Gates", 10000, 9.0, "Gate Keeper", 3000000, 6000000),
        Resource("star_spawn", "Star Spawn", 50000, 10.0, "Spawn Master", 15000000, 30000000),
        Resource("great_old_ones", "Great Old Ones", 200000, 12.0, "Elder Priest", 60000000, 120000000),
    ]
    return {resource.key: resource for resource in resources}

class Game:
    def __init__(self, player_name: str = None, load_data: Dict = None, difficulty: str = DEFAULT_DIFFICULTY):
        self.player_name = player_name
        self.difficulty = load_data["difficulty"] if load_data else difficulty
        if self.difficulty not in DIFFICULTIES:
            raise ValueError(f"Unknown difficulty {self.difficulty!r}")
        self.world_id = new_world_id()
        self.sanity = 0
        self.worlds_destroyed = 0
        self.devoured_seconds = None  # Dream time when the world was devoured; None until then
        self.endless = False  # Chose to keep feeding on the devoured world
        self.last_saved = time.time()
        self.dream_seconds = 0.0  # Time spent on the current world, including time the game was closed
        self.devoured_now = []  # (world_id, worlds_destroyed, difficulty) of devours since this Game was built
        self.new_world()

        if load_data:
            self.load_game_state(load_data)

    def new_world(self):
        self.resources = new_resources()
        self.upgrade_manager = UpgradeManager()
        self.apply_difficulty()

    def load_game_state(self, data: Dict):
        self.player_name = str(data["player_name"])
        self.world_id = str(data["world_id"])
        self.sanity = float(data["sanity"])
        self.worlds_destroyed = int(data["worlds_destroyed"])
        # A save can't be from the future: catching up to a later time would freeze the game until then.
        self.last_saved = min(float(data["last_saved"]), time.time())
        self.dream_seconds = float(data["dream_seconds"])
        devoured_seconds = data["devoured_seconds"]
        self.devoured_seconds = None if devoured_seconds is None else float(devoured_seconds)
        self.endless = bool(data["endless"])

        for key, resource in self.resources.items():
            saved = data["resources"][key]
            for field, field_type in SAVED_RESOURCE_FIELDS.items():
                setattr(resource, field, field_type(saved[field]))
            if resource.has_manager and resource.is_unlocked:
                resource.is_processing = True

        for upgrade_id in data["upgrades"]:
            self.upgrade_manager.upgrades[upgrade_id].purchased = True

    def progress(self) -> Tuple:
        """Orders two copies of a world by how far along they are."""
        purchases = sum(upgrade.purchased for upgrade in self.upgrade_manager.upgrades.values())
        purchases += sum(resource.is_unlocked + resource.has_manager for resource in self.resources.values())
        return self.worlds_destroyed, self.devoured_seconds is not None, purchases, self.sanity

    def started_at(self) -> float:
        """When this world began, which tells an older world from a newer one with the same name."""
        return self.last_saved - self.dream_seconds

    def save_game_state(self) -> Dict:
        return {
            "player_name": self.player_name,
            "world_id": self.world_id,
            "difficulty": self.difficulty,
            "sanity": self.sanity,
            "worlds_destroyed": self.worlds_destroyed,
            "last_saved": self.last_saved,
            "dream_seconds": self.dream_seconds,
            "devoured_seconds": self.devoured_seconds,
            "endless": self.endless,
            "resources": {key: {field: getattr(resource, field) for field in SAVED_RESOURCE_FIELDS}
                          for key, resource in self.resources.items()},
            "upgrades": {upgrade_id: True for upgrade_id, upgrade in self.upgrade_manager.upgrades.items()
                         if upgrade.purchased},
        }

    def production_rate(self, resource: Resource) -> float:
        production_multiplier, _ = self.upgrade_manager.get_multiplier(resource.key)
        return resource.base_production * production_multiplier

    def cycle_time(self, resource: Resource) -> float:
        _, speed_multiplier = self.upgrade_manager.get_multiplier(resource.key)
        return resource.production_time / speed_multiplier

    def update_resource(self, resource: Resource, dt: float):
        if resource.is_processing:
            _, speed_multiplier = self.upgrade_manager.get_multiplier(resource.key)

            resource.progress += dt * speed_multiplier
            cycles_completed = int(resource.progress / resource.production_time)

            if cycles_completed > 0:
                # Without a manager, one click is one cycle, however long the game was closed
                if not resource.has_manager:
                    cycles_completed = 1
                self.sanity += self.production_rate(resource) * cycles_completed
                resource.progress = resource.progress % resource.production_time

                if not resource.has_manager:
                    resource.is_processing = False
                    resource.progress = 0

    def advance(self, now: float):
        """Run the game from the last save up to now, including any time the game was closed"""
        dt = max(0.0, now - self.last_saved)
        self.dream_seconds += dt
        for resource in self.resources.values():
            if resource.is_unlocked:
                self.update_resource(resource, dt)
        self.last_saved = now

    def click_resource(self, resource_key: str):
        resource = self.resources.get(resource_key)
        if resource is None:
            return
        if not resource.is_unlocked:
            if self.sanity >= resource.unlock_cost:
                resource.is_unlocked = True
                self.sanity -= resource.unlock_cost
        elif not resource.is_processing:
            resource.is_processing = True
            resource.progress = 0

    def hire_manager(self, resource_key: str):
        resource = self.resources.get(resource_key)
        if resource is None or not resource.is_unlocked:
            return
        if not resource.has_manager and self.sanity >= resource.manager_cost:
            resource.has_manager = True
            self.sanity -= resource.manager_cost
            resource.is_processing = True
            self.record_devoured()

    def buy_upgrade(self, upgrade_id: str):
        success, self.sanity = self.upgrade_manager.purchase(upgrade_id, self.sanity)
        if success:
            self.record_devoured()

    def record_devoured(self):
        """Count the world and remember how long the dream took, the first time it is devoured"""
        if self.devoured_seconds is None and self.check_world_devoured():
            self.devoured_seconds = self.dream_seconds
            self.worlds_destroyed += 1
            self.devoured_now.append((self.world_id, self.worlds_destroyed, self.difficulty))

    def enter_endless(self):
        if self.devoured_seconds is not None:
            self.endless = True

    def next_upgrades(self) -> List[Tuple[str, Upgrade]]:
        """The next speed and next production upgrade for each unlocked resource"""
        upgrades = self.upgrade_manager.upgrades
        found = []
        for key, resource in self.resources.items():
            if not resource.is_unlocked:
                continue
            for upgrade_type in ("speed", "production"):
                upgrade_id = next((upgrade_id for upgrade_id, upgrade in upgrades.items()
                                   if upgrade.resource == key and upgrade.upgrade_type == upgrade_type
                                   and not upgrade.purchased), None)
                if upgrade_id is not None:
                    found.append((upgrade_id, upgrades[upgrade_id]))
        return found

    def check_world_devoured(self):
        """The world is devoured once every upgrade is bought and every manager is hired"""
        return (all(upgrade.purchased for upgrade in self.upgrade_manager.upgrades.values())
                and all(resource.has_manager for resource in self.resources.values()))

    def reset_game(self):
        """After a devour, start a new world under the same name, keeping the worlds_destroyed counter"""
        if self.devoured_seconds is None:
            return
        self.world_id = new_world_id()
        self.sanity = 0
        self.dream_seconds = 0.0
        self.devoured_seconds = None
        self.endless = False
        self.new_world()

    def apply_difficulty(self):
        """Scale each tier's costs for the difficulty."""
        growth = DIFFICULTIES[self.difficulty].growth
        for tier, (resource_key, resource) in enumerate(self.resources.items()):
            multiplier = growth ** tier
            resource.unlock_cost = round_cost(resource.unlock_cost * multiplier)
            resource.manager_cost = round_cost(resource.manager_cost * multiplier)
            for upgrade in self.upgrade_manager.for_resource(resource_key):
                upgrade.cost = round_cost(upgrade.cost * multiplier)
