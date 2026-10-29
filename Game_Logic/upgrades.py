from dataclasses import dataclass
from typing import Dict, List, Tuple


@dataclass
class Upgrade:
    name: str
    description: str
    cost: float
    multiplier: float
    upgrade_type: str  # 'speed' or 'production'
    resource: str
    purchased: bool = False


# Each resource's upgrades: (type, multiplier, cost as a multiple of the resource's base upgrade cost)
UPGRADE_STEPS = {
    "speed_2x": ("speed", 2.0, 1.0),
    "speed_3x": ("speed", 3.0, 3.0),
    "speed_5x": ("speed", 5.0, 10.0),
    "prod_2x": ("production", 2.0, 0.3),
    "prod_5x": ("production", 5.0, 6.0),
}

# Each resource's base upgrade cost and its upgrade names, in UPGRADE_STEPS order. Base costs grow faster than
# production, so later tiers take longer.
RESOURCE_UPGRADES = {
    "cultists": (50, ("Chants of R'lyeh", "Nyarlathotep's Blessing", "Time Fracture Ritual",
                      "Blood Sacrifice Pact", "Elder God's Awakening")),
    "ancient_tomes": (600, ("Accelerated Translation", "Mind-Bending Reading", "Aklo Language Mastery",
                            "Necronomicon Insights", "Pnakotic Manuscripts")),
    "eldritch_artifacts": (4000, ("Resonating Crystals", "Non-Euclidean Crafting", "Y'ha-nthlei Forging",
                                  "Shub-Niggurath's Touch", "Elder Thing Technology")),
    "sacrifices": (30000, ("Efficient Bloodletting", "Mass Ceremony", "Grand Harvest",
                           "Willing Offerings", "Heart of Darkness")),
    "dark_rituals": (150000, ("Synchronized Chanting", "Moonless Night Rites", "Reality-Rending Ritual",
                              "Blood Moon Ceremony", "Yog-Sothoth's Gate")),
    "cosmic_energy": (800000, ("Star Alignment", "Void Channeling", "Azathoth's Dance",
                               "Dark Matter Infusion", "Stellar Obliteration")),
    "elder_signs": (5000000, ("Swift Carving", "Reality Etching", "Timeless Inscription",
                              "Deep Carvings", "Elder Seal Mastery")),
    "dimensional_gates": (25000000, ("Spatial Warping", "Void Tunneling", "Quantum Tunneling",
                                     "Gate Expansion", "Reality Breach")),
    "star_spawn": (120000000, ("Rapid Incubation", "Accelerated Growth", "Temporal Gestation",
                               "Enhanced Breeding", "Perfect Specimens")),
    "great_old_ones": (250000000, ("Dreams of Madness", "Cosmic Awakening", "Reality Consumption",
                                   "World Reshaping", "Universal Horror")),
}


def resource_title(resource_key: str) -> str:
    return resource_key.replace("_", " ").title()


class UpgradeManager:
    def __init__(self):
        self.upgrades: Dict[str, Upgrade] = {}
        for resource, (base_cost, names) in RESOURCE_UPGRADES.items():
            for (step, (upgrade_type, multiplier, cost_factor)), name in zip(UPGRADE_STEPS.items(), names, strict=True):
                description = f"{multiplier:g}x {upgrade_type.title()} for {resource_title(resource)}"
                self.upgrades[f"{resource}_{step}"] = Upgrade(name, description, base_cost * cost_factor, multiplier,
                                                              upgrade_type, resource)

    def purchase(self, upgrade_id: str, sanity: float) -> Tuple[bool, float]:
        """Returns (success, new_sanity)"""
        upgrade = self.upgrades.get(upgrade_id)
        if upgrade is None or upgrade.purchased or sanity < upgrade.cost:
            return False, sanity
        upgrade.purchased = True
        return True, sanity - upgrade.cost

    def for_resource(self, resource_key: str) -> List[Upgrade]:
        return [upgrade for upgrade in self.upgrades.values() if upgrade.resource == resource_key]

    def get_multiplier(self, resource_key: str) -> Tuple[float, float]:
        """(production_multiplier, speed_multiplier) from a resource's purchased upgrades"""
        multipliers = {"production": 1.0, "speed": 1.0}
        for upgrade in self.for_resource(resource_key):
            if upgrade.purchased:
                multipliers[upgrade.upgrade_type] *= upgrade.multiplier
        return multipliers["production"], multipliers["speed"]