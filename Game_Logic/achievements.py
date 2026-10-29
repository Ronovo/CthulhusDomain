from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Set, Tuple

from main import DIFFICULTIES, Game

# Achievements belong to the player, not to one save, so the browser keeps the player's record and
# sends it with every request. That is what lets achievements count across saves.

# One devour: (world_id, worlds_destroyed after it, difficulty). The same devour reported twice, by a replayed
# save or by two browsers, is still one entry.
Devour = Tuple[str, int, str]


@dataclass
class PlayerRecord:
    earned: Set[str]
    devours: Set[Devour]

    def devoured(self, difficulty: Optional[str] = None) -> int:
        """Worlds devoured across every save, on one difficulty or, without one, in total"""
        return sum(1 for _, _, devoured_on in self.devours if difficulty is None or devoured_on == difficulty)


@dataclass
class Achievement:
    name: str
    description: str
    earned: Callable[[Game, PlayerRecord], bool]


def fully_upgraded(game: Game, resource_key: str) -> bool:
    return all(upgrade.purchased for upgrade in game.upgrade_manager.upgrades.values()
               if upgrade.resource == resource_key)


def devoured_on(difficulty: str) -> Achievement:
    """Devouring a world on a difficulty also counts for every easier one, in DIFFICULTIES order"""
    names = {
        "quick": "A Light Snack",
        "recommended": "The Dreamer Wakes",
        "long_haul": "Strange Aeons",
        "eternal": "That Is Not Dead Which Can Eternal Lie",
    }
    ladder = list(DIFFICULTIES)
    hardest = difficulty == ladder[-1]
    description = f"Devour a world on {DIFFICULTIES[difficulty].name}" + ("" if hardest else " or higher")
    return Achievement(names[difficulty], description,
                       lambda game, player: (game.devoured_seconds is not None
                                             and ladder.index(game.difficulty) >= ladder.index(difficulty)))


def devoured_count(name: str, count: int, difficulty: Optional[str] = None) -> Achievement:
    """Worlds devoured across every save, on one difficulty or, without one, in total"""
    where = f" on {DIFFICULTIES[difficulty].name}" if difficulty else " in total"
    return Achievement(name, f"Devour {count} worlds{where}",
                       lambda game, player: player.devoured(difficulty) >= count)


ACHIEVEMENTS: Dict[str, Achievement] = {
    "cult_leader": Achievement("The First Disciple", "Hire the Cult Leader",
                               lambda game, player: game.resources["cultists"].has_manager),
    "cultists_maxed": Achievement("A Congregation of Madness", "Buy every Cultists upgrade",
                                  lambda game, player: fully_upgraded(game, "cultists")),
    "cosmic_unlocked": Achievement("Beyond the Veil of Stars", "Unlock Cosmic Energy",
                                   lambda game, player: game.resources["cosmic_energy"].is_unlocked),
    "cosmic_maxed": Achievement("The Colour Out of Space", "Buy every Cosmic Energy upgrade",
                                lambda game, player: fully_upgraded(game, "cosmic_energy")),
    "goo_unlocked": Achievement("The Stars Are Right", "Unlock Great Old Ones",
                                lambda game, player: game.resources["great_old_ones"].is_unlocked),
    "goo_manager": Achievement("Whispers of the Elder Priest", "Hire the Elder Priest",
                               lambda game, player: game.resources["great_old_ones"].has_manager),
    **{f"devour_{difficulty}": devoured_on(difficulty) for difficulty in DIFFICULTIES},
    "all_difficulties": Achievement("Ph'nglui Mglw'nafh Fhtagn", "Devour a world on every difficulty",
                                    lambda game, player: all(player.devoured(d) > 0 for d in DIFFICULTIES)),
    "eternal_2": devoured_count("Even Death May Die", 2, "eternal"),
    "quick_20": devoured_count("An Insatiable Appetite", 20, "quick"),
    "recommended_5": devoured_count("A Feast of Worlds", 5, "recommended"),
    "total_25": devoured_count("Devourer of Worlds", 25),
    "total_50": devoured_count("The Daemon Sultan", 50),
}


def new_achievements(game: Game, player: PlayerRecord) -> List[str]:
    """Achievements the game and player now qualify for that the player hasn't earned yet"""
    new = []
    for achievement_id, achievement in ACHIEVEMENTS.items():
        if achievement_id not in player.earned and achievement.earned(game, player):
            player.earned.add(achievement_id)
            new.append(achievement_id)
    return new
