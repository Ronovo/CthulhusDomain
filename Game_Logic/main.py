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
    def __init__(self, player_name: str = None, load_data: Dict = None):
        # Game state
        self.player_name = player_name
        self.sanity = 0
        self.upgrade_manager = UpgradeManager()
        self.worlds_destroyed = 0  # Counter for worlds destroyed
        self.show_world_end = False  # Flag for showing the world end popup
        self.last_saved = time.time()

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

        if load_data:
            self.load_game_state(load_data)

    def load_game_state(self, data: Dict):
        self.player_name = str(data["player_name"])
        self.sanity = float(data["sanity"])
        self.worlds_destroyed = int(data.get("worlds_destroyed", 0))  # Load worlds destroyed count
        self.last_saved = float(data.get("last_saved", time.time()))

        # Load resources
        for resource_name, resource_data in data.get("resources", {}).items():
            if resource_name in self.resources:
                resource = self.resources[resource_name]
                for key, field_type in SAVED_RESOURCE_FIELDS.items():
                    if key in resource_data:
                        setattr(resource, key, field_type(resource_data[key]))
                # Start processing if resource has a manager
                if resource.has_manager and resource.is_unlocked:
                    resource.is_processing = True

        # Load purchased upgrades
        for upgrade_id in data.get("upgrades", {}):
            if upgrade_id in self.upgrade_manager.upgrades:
                self.upgrade_manager.upgrades[upgrade_id].purchased = True

    def save_game_state(self) -> Dict:
        game_data = {
            "player_name": self.player_name,
            "sanity": self.sanity,
            "worlds_destroyed": self.worlds_destroyed,  # Save worlds destroyed count
            "last_saved": self.last_saved,
            "resources": {},
            "upgrades": {}
        }

        # Save resources
        for name, resource in self.resources.items():
            game_data["resources"][name] = {
                "count": resource.count,
                "level": resource.level,
                "has_manager": resource.has_manager,
                "is_unlocked": resource.is_unlocked,
                "is_processing": resource.is_processing,
                "progress": resource.progress
            }

        # Save purchased upgrades
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
            # Apply speed multiplier to dt
            production_multiplier, speed_multiplier = self.upgrade_manager.get_multiplier(resource.name)

            # For very high speeds, we'll process multiple cycles at once
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

    def buy_upgrade(self, upgrade_id: str):
        success, self.sanity = self.upgrade_manager.purchase(upgrade_id, self.sanity)
        if success and self.check_all_upgrades_purchased():
            self.show_world_end = True

    def next_upgrades(self) -> List[Tuple[str, Upgrade]]:
        """The next speed and next production upgrade for each unlocked resource"""
        available_upgrades = []
        resource_next_upgrades = {}

        # First, group upgrades by resource
        for upgrade_id, upgrade in self.upgrade_manager.upgrades.items():
            if not upgrade.purchased:
                # Find the resource key that matches the upgrade's resource name
                for resource_key, resource in self.resources.items():
                    if resource_key.lower() == upgrade.resource and resource.is_unlocked:
                        if resource_key not in resource_next_upgrades:
                            resource_next_upgrades[resource_key] = []
                        resource_next_upgrades[resource_key].append((upgrade_id, upgrade))
                        break

        # Then, select only the next upgrade for each resource
        for resource_key, upgrades in resource_next_upgrades.items():
            # Sort upgrades by type (speed first, then production)
            speed_upgrades = [u for u in upgrades if "speed" in u[1].upgrade_type.lower()]
            prod_upgrades = [u for u in upgrades if "production" in u[1].upgrade_type.lower()]

            # Add next speed upgrade if available
            if speed_upgrades:
                available_upgrades.append(speed_upgrades[0])
            # Add next production upgrade if available
            if prod_upgrades:
                available_upgrades.append(prod_upgrades[0])

        return available_upgrades

    def check_all_upgrades_purchased(self):
        """Check if all upgrades have been purchased"""
        return all(upgrade.purchased for upgrade in self.upgrade_manager.upgrades.values())

    def reset_game(self):
        """Reset the game state while keeping worlds_destroyed counter"""
        self.sanity = 0
        self.worlds_destroyed += 1
        self.show_world_end = False

        # Reset resources
        for resource in self.resources.values():
            resource.count = 0
            resource.progress = 0
            resource.is_processing = False
            resource.has_manager = False
            resource.level = 1
            resource.is_unlocked = resource.name.lower().replace(" ", "_") == "cultists"

        # Reset upgrades
        self.upgrade_manager = UpgradeManager()
