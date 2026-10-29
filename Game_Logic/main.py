import time
from dataclasses import dataclass
from typing import Dict, List, Tuple
from upgrades import Upgrade, UpgradeManager

# Fields a save may set on a resource; the save comes from the browser, so nothing else is accepted
SAVED_RESOURCE_FIELDS = {
    "count": float,
    "level": int,
    "has_manager": bool,
    "is_unlocked": bool,
    "is_processing": bool,
    "progress": float,
}

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
    name: str
    base_cost: float
    base_production: float
    production_time: float
    manager_name: str
    unlock_cost: float
    count: int = 0
    progress: float = 0
    is_processing: bool = False
    has_manager: bool = False
    level: int = 1
    manager_cost: float = 1000
    is_unlocked: bool = False

class Game:
    def __init__(self, player_name: str = None, load_data: Dict = None, difficulty: str = DEFAULT_DIFFICULTY):
        self.player_name = player_name
        self.difficulty = (load_data or {}).get("difficulty", difficulty)
        if self.difficulty not in DIFFICULTIES:
            self.difficulty = DEFAULT_DIFFICULTY
        self.sanity = 0
        self.upgrade_manager = UpgradeManager()
        self.worlds_destroyed = 0
        self.devoured_seconds = None  # Dream time when the world was devoured; None until then
        self.endless = False  # Chose to keep feeding on the devoured world
        self.last_saved = time.time()
        self.dream_seconds = 0.0  # Time spent on the current world, including time the game was closed

        self.resources = {
            "cultists": Resource("Cultists", 10, 1, 2.0, "Cult Leader", unlock_cost=5, manager_cost=10, is_unlocked=True),
            "ancient_tomes": Resource("Ancient Tomes", 50, 5, 3.0, "Mad Librarian", unlock_cost=30, manager_cost=60),
            "eldritch_artifacts": Resource("Eldritch Artifacts", 200, 15, 4.0, "Relic Hunter", unlock_cost=200, manager_cost=400),
            "sacrifices": Resource("Sacrifices", 1000, 50, 5.0, "High Priest", unlock_cost=1500, manager_cost=3000),
            "dark_rituals": Resource("Dark Rituals", 5000, 200, 6.0, "Ritual Master", unlock_cost=10000, manager_cost=20000),
            "cosmic_energy": Resource("Cosmic Energy", 20000, 750, 7.0, "Star Priest", unlock_cost=75000, manager_cost=150000),
            "elder_signs": Resource("Elder Signs", 100000, 3000, 8.0, "Sign Keeper", unlock_cost=500000, manager_cost=1000000),
            "dimensional_gates": Resource("Dimensional Gates", 500000, 10000, 9.0, "Gate Keeper", unlock_cost=3000000, manager_cost=6000000),
            "star_spawn": Resource("Star Spawn", 2000000, 50000, 10.0, "Spawn Master", unlock_cost=15000000, manager_cost=30000000),
            "great_old_ones": Resource("Great Old Ones", 10000000, 200000, 12.0, "Elder Priest", unlock_cost=60000000, manager_cost=120000000)
        }
        self.apply_difficulty()

        if load_data:
            self.load_game_state(load_data)

    def load_game_state(self, data: Dict):
        self.player_name = str(data["player_name"])
        self.sanity = float(data["sanity"])
        self.worlds_destroyed = int(data.get("worlds_destroyed", 0))
        self.last_saved = float(data.get("last_saved", time.time()))
        self.dream_seconds = float(data.get("dream_seconds", 0.0))
        devoured_seconds = data.get("devoured_seconds")
        self.devoured_seconds = None if devoured_seconds is None else float(devoured_seconds)
        self.endless = bool(data.get("endless", False))

        for resource_name, resource_data in data.get("resources", {}).items():
            if resource_name in self.resources:
                resource = self.resources[resource_name]
                for key, field_type in SAVED_RESOURCE_FIELDS.items():
                    if key in resource_data:
                        setattr(resource, key, field_type(resource_data[key]))
                if resource.has_manager and resource.is_unlocked:
                    resource.is_processing = True

        for upgrade_id in data.get("upgrades", {}):
            if upgrade_id in self.upgrade_manager.upgrades:
                self.upgrade_manager.upgrades[upgrade_id].purchased = True

    def save_game_state(self) -> Dict:
        game_data = {
            "player_name": self.player_name,
            "difficulty": self.difficulty,
            "sanity": self.sanity,
            "worlds_destroyed": self.worlds_destroyed,
            "last_saved": self.last_saved,
            "dream_seconds": self.dream_seconds,
            "devoured_seconds": self.devoured_seconds,
            "endless": self.endless,
            "resources": {},
            "upgrades": {}
        }

        for name, resource in self.resources.items():
            game_data["resources"][name] = {
                "count": resource.count,
                "level": resource.level,
                "has_manager": resource.has_manager,
                "is_unlocked": resource.is_unlocked,
                "is_processing": resource.is_processing,
                "progress": resource.progress
            }

        for upgrade_id, upgrade in self.upgrade_manager.upgrades.items():
            if upgrade.purchased:
                game_data["upgrades"][upgrade_id] = True

        return game_data

    def production_rate(self, resource: Resource) -> float:
        production_multiplier, speed_multiplier = self.upgrade_manager.get_multiplier(resource.name)
        return resource.base_production * resource.level * production_multiplier

    def cycle_time(self, resource: Resource) -> float:
        production_multiplier, speed_multiplier = self.upgrade_manager.get_multiplier(resource.name)
        return resource.production_time / speed_multiplier

    def update_resource(self, resource: Resource, dt: float):
        if resource.is_processing:
            production_multiplier, speed_multiplier = self.upgrade_manager.get_multiplier(resource.name)

            resource.progress += dt * speed_multiplier
            cycles_completed = int(resource.progress / resource.production_time)

            if cycles_completed > 0:
                # Without a manager, one click is one cycle, however long the game was closed
                if not resource.has_manager:
                    cycles_completed = 1
                production = resource.base_production * resource.level * production_multiplier * cycles_completed
                resource.count += production
                self.sanity += production
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

    def enter_endless(self):
        if self.devoured_seconds is not None:
            self.endless = True

    def next_upgrades(self) -> List[Tuple[str, Upgrade]]:
        """The next speed and next production upgrade for each unlocked resource"""
        available_upgrades = []
        resource_next_upgrades = {}

        for upgrade_id, upgrade in self.upgrade_manager.upgrades.items():
            if not upgrade.purchased:
                for resource_key, resource in self.resources.items():
                    if resource_key.lower() == upgrade.resource and resource.is_unlocked:
                        if resource_key not in resource_next_upgrades:
                            resource_next_upgrades[resource_key] = []
                        resource_next_upgrades[resource_key].append((upgrade_id, upgrade))
                        break

        for resource_key, upgrades in resource_next_upgrades.items():
            speed_upgrades = [u for u in upgrades if "speed" in u[1].upgrade_type.lower()]
            prod_upgrades = [u for u in upgrades if "production" in u[1].upgrade_type.lower()]

            if speed_upgrades:
                available_upgrades.append(speed_upgrades[0])
            if prod_upgrades:
                available_upgrades.append(prod_upgrades[0])

        return available_upgrades

    def check_world_devoured(self):
        """The world is devoured once every upgrade is bought and every manager is hired"""
        return (all(upgrade.purchased for upgrade in self.upgrade_manager.upgrades.values())
                and all(resource.has_manager for resource in self.resources.values()))

    def reset_game(self):
        """Reset the game state while keeping worlds_destroyed counter"""
        self.sanity = 0
        self.dream_seconds = 0.0
        self.devoured_seconds = None
        self.endless = False

        for resource in self.resources.values():
            resource.count = 0
            resource.progress = 0
            resource.is_processing = False
            resource.has_manager = False
            resource.level = 1
            resource.is_unlocked = resource.name.lower().replace(" ", "_") == "cultists"

        self.upgrade_manager = UpgradeManager()
        self.apply_difficulty(include_resources=False)

    def apply_difficulty(self, include_resources: bool = True):
        """Scale each tier's costs for the difficulty. A new world rebuilds only the upgrades, so it
        skips the resources, whose costs were already scaled."""
        growth = DIFFICULTIES[self.difficulty].growth
        for tier, (resource_key, resource) in enumerate(self.resources.items()):
            multiplier = growth ** tier
            if include_resources:
                resource.unlock_cost = round_cost(resource.unlock_cost * multiplier)
                resource.manager_cost = round_cost(resource.manager_cost * multiplier)
            for upgrade in self.upgrade_manager.upgrades.values():
                if upgrade.resource == resource_key:
                    upgrade.cost = round_cost(upgrade.cost * multiplier)
