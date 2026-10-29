from dataclasses import dataclass

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

class UpgradeManager:
    def __init__(self):
        self.upgrades = {}
        self._initialize_upgrades()
    
    def _initialize_upgrades(self):
        # Base costs for each resource; they grow faster than production, so later tiers take longer
        resource_base_costs = {
            "cultists": 50,
            "ancient_tomes": 600,
            "eldritch_artifacts": 4000,
            "sacrifices": 30000,
            "dark_rituals": 150000,
            "cosmic_energy": 800000,
            "elder_signs": 5000000,
            "dimensional_gates": 25000000,
            "star_spawn": 120000000,
            "great_old_ones": 250000000,
        }

        resource_upgrades = {
            "cultists": {
                "speed_2x": ("Chants of R'lyeh", "2x Speed for Cultists"),
                "speed_3x": ("Nyarlathotep's Blessing", "3x Speed for Cultists"),
                "speed_5x": ("Time Fracture Ritual", "5x Speed for Cultists"),
                "prod_2x": ("Blood Sacrifice Pact", "2x Production for Cultists"),
                "prod_5x": ("Elder God's Awakening", "5x Production for Cultists")
            },
            "ancient_tomes": {
                "speed_2x": ("Accelerated Translation", "2x Speed for Ancient Tomes"),
                "speed_3x": ("Mind-Bending Reading", "3x Speed for Ancient Tomes"),
                "speed_5x": ("Aklo Language Mastery", "5x Speed for Ancient Tomes"),
                "prod_2x": ("Necronomicon Insights", "2x Production for Ancient Tomes"),
                "prod_5x": ("Pnakotic Manuscripts", "5x Production for Ancient Tomes")
            },
            "eldritch_artifacts": {
                "speed_2x": ("Resonating Crystals", "2x Speed for Eldritch Artifacts"),
                "speed_3x": ("Non-Euclidean Crafting", "3x Speed for Eldritch Artifacts"),
                "speed_5x": ("Y'ha-nthlei Forging", "5x Speed for Eldritch Artifacts"),
                "prod_2x": ("Shub-Niggurath's Touch", "2x Production for Eldritch Artifacts"),
                "prod_5x": ("Elder Thing Technology", "5x Production for Eldritch Artifacts")
            },
            "sacrifices": {
                "speed_2x": ("Efficient Bloodletting", "2x Speed for Sacrifices"),
                "speed_3x": ("Mass Ceremony", "3x Speed for Sacrifices"),
                "speed_5x": ("Grand Harvest", "5x Speed for Sacrifices"),
                "prod_2x": ("Willing Offerings", "2x Production for Sacrifices"),
                "prod_5x": ("Heart of Darkness", "5x Production for Sacrifices")
            },
            "dark_rituals": {
                "speed_2x": ("Synchronized Chanting", "2x Speed for Dark Rituals"),
                "speed_3x": ("Moonless Night Rites", "3x Speed for Dark Rituals"),
                "speed_5x": ("Reality-Rending Ritual", "5x Speed for Dark Rituals"),
                "prod_2x": ("Blood Moon Ceremony", "2x Production for Dark Rituals"),
                "prod_5x": ("Yog-Sothoth's Gate", "5x Production for Dark Rituals")
            },
            "cosmic_energy": {
                "speed_2x": ("Star Alignment", "2x Speed for Cosmic Energy"),
                "speed_3x": ("Void Channeling", "3x Speed for Cosmic Energy"),
                "speed_5x": ("Azathoth's Dance", "5x Speed for Cosmic Energy"),
                "prod_2x": ("Dark Matter Infusion", "2x Production for Cosmic Energy"),
                "prod_5x": ("Stellar Obliteration", "5x Production for Cosmic Energy")
            },
            "elder_signs": {
                "speed_2x": ("Swift Carving", "2x Speed for Elder Signs"),
                "speed_3x": ("Reality Etching", "3x Speed for Elder Signs"),
                "speed_5x": ("Timeless Inscription", "5x Speed for Elder Signs"),
                "prod_2x": ("Deep Carvings", "2x Production for Elder Signs"),
                "prod_5x": ("Elder Seal Mastery", "5x Production for Elder Signs")
            },
            "dimensional_gates": {
                "speed_2x": ("Spatial Warping", "2x Speed for Dimensional Gates"),
                "speed_3x": ("Void Tunneling", "3x Speed for Dimensional Gates"),
                "speed_5x": ("Quantum Tunneling", "5x Speed for Dimensional Gates"),
                "prod_2x": ("Gate Expansion", "2x Production for Dimensional Gates"),
                "prod_5x": ("Reality Breach", "5x Production for Dimensional Gates")
            },
            "star_spawn": {
                "speed_2x": ("Rapid Incubation", "2x Speed for Star Spawn"),
                "speed_3x": ("Accelerated Growth", "3x Speed for Star Spawn"),
                "speed_5x": ("Temporal Gestation", "5x Speed for Star Spawn"),
                "prod_2x": ("Enhanced Breeding", "2x Production for Star Spawn"),
                "prod_5x": ("Perfect Specimens", "5x Production for Star Spawn")
            },
            "great_old_ones": {
                "speed_2x": ("Dreams of Madness", "2x Speed for Great Old Ones"),
                "speed_3x": ("Cosmic Awakening", "3x Speed for Great Old Ones"),
                "speed_5x": ("Reality Consumption", "5x Speed for Great Old Ones"),
                "prod_2x": ("World Reshaping", "2x Production for Great Old Ones"),
                "prod_5x": ("Universal Horror", "5x Production for Great Old Ones")
            }
        }

        for resource, base_cost in resource_base_costs.items():
            for step, (upgrade_type, multiplier, cost_factor) in UPGRADE_STEPS.items():
                name, description = resource_upgrades[resource][step]
                self.upgrades[f"{resource}_{step}"] = Upgrade(name, description, base_cost * cost_factor, multiplier,
                                                              upgrade_type, resource)

    def can_purchase(self, upgrade_id: str, sanity: float) -> bool:
        upgrade = self.upgrades.get(upgrade_id)
        if not upgrade:
            return False
        return not upgrade.purchased and sanity >= upgrade.cost
    
    def purchase(self, upgrade_id: str, sanity: float) -> tuple[bool, float]:
        """Returns (success, new_sanity)"""
        if not self.can_purchase(upgrade_id, sanity):
            return False, sanity
            
        upgrade = self.upgrades[upgrade_id]
        upgrade.purchased = True
        return True, sanity - upgrade.cost
    
    def get_multiplier(self, resource_name: str) -> tuple[float, float]:
        """Calculate total multipliers for a resource based on purchased upgrades
        Returns (production_multiplier, speed_multiplier)"""
        production_multiplier = 1.0
        speed_multiplier = 1.0
        
        # Convert display name to internal name format (lowercase, spaces to underscores)
        resource_name = resource_name.lower().replace(" ", "_")
        
        for upgrade in self.upgrades.values():
            if upgrade.purchased and upgrade.resource == resource_name:
                if upgrade.upgrade_type == 'speed':
                    speed_multiplier *= upgrade.multiplier
                elif upgrade.upgrade_type == 'production':
                    production_multiplier *= upgrade.multiplier
                
        return production_multiplier, speed_multiplier 