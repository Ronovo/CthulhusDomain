from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Set, Tuple

from main import DIFFICULTIES, MODES, Game
from menu import GREAT_OLD_ONES

# Achievements belong to the player, not to one save, so the browser keeps the player's record and
# sends it with every request. That is what lets achievements count across saves.

# One devour: (world_id, worlds_destroyed after it, difficulty). The same devour reported twice, by a replayed
# save or by two browsers, is still one entry.
Devour = Tuple[str, int, str]


@dataclass
class PlayerRecord:
    earned: Set[str]
    devours: Set[Devour]
    names: Set[str] = field(default_factory=set)  # Named Great Old Ones a world has been devoured as

    def devoured(self, difficulty: Optional[str] = None) -> int:
        """Worlds devoured across every save, on one difficulty or, without one, in total"""
        return sum(1 for _, _, devoured_on in self.devours if difficulty is None or devoured_on == difficulty)

    def merge(self, other: "PlayerRecord"):
        self.earned |= other.earned
        self.devours |= other.devours
        self.names |= other.names


@dataclass
class Achievement:
    name: str
    description: str
    earned: Callable[[Game, PlayerRecord], bool]
    difficulty: Optional[str] = None  # Set when the achievement is about one difficulty
    mode: Optional[str] = None  # Set when the achievement is about one mode


def fully_upgraded(game: Game, resource_key: str) -> bool:
    return all(upgrade.purchased for upgrade in game.upgrade_manager.upgrades.values()
               if upgrade.resource == resource_key)


def devoured_on(difficulty: str) -> Achievement:
    """Devouring a world on a difficulty also counts for every easier one, in DIFFICULTIES order"""
    names = {
        "quick": "A Light Snack",
        "short": "An Appetite Whetted",
        "recommended": "The Dreamer Wakes",
        "long_haul": "Strange Aeons",
        "eternal": "That Is Not Dead Which Can Eternal Lie",
    }
    ladder = list(DIFFICULTIES)
    hardest = difficulty == ladder[-1]
    description = f"Devour a world on {DIFFICULTIES[difficulty].name}" + ("" if hardest else " or higher")
    return Achievement(names[difficulty], description,
                       lambda game, player: (game.devoured_seconds is not None
                                             and ladder.index(game.difficulty) >= ladder.index(difficulty)),
                       difficulty)


def within_text(minutes: int) -> str:
    hours, rest = divmod(minutes, 60)
    if hours and not rest:
        return f"{hours} hour" + ("s" if hours > 1 else "")
    return f"{minutes} minutes"


def devoured_within(name: str, difficulty: str, minutes: int, mode: str) -> Achievement:
    description = (f"Devour a world on {DIFFICULTIES[difficulty].name} in under {within_text(minutes)} "
                   f"in {MODES[mode].name}")
    return Achievement(name, description,
                       lambda game, player: (game.difficulty == difficulty and game.mode == mode
                                             and game.devoured_seconds is not None
                                             and game.devoured_seconds < minutes * 60),
                       difficulty, mode)


def devoured_count(name: str, count: int, difficulty: Optional[str] = None) -> Achievement:
    """Worlds devoured across every save, on one difficulty or, without one, in total"""
    where = f" on {DIFFICULTIES[difficulty].name}" if difficulty else " in total"
    return Achievement(name, f"Devour {count} worlds{where}",
                       lambda game, player: player.devoured(difficulty) >= count, difficulty)


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
    "all_managers": Achievement("A Choir of Mad Priests", "Hire every manager on one world",
                                lambda game, player: all(resource.has_manager for resource in game.resources.values())),
    "endless": Achievement("The Feast Never Ends", "Enter Endless Mode", lambda game, player: game.endless),
    "sanity_million": Achievement("A Million Screaming Minds", "Hold 1,000,000 Sanity at once",
                                  lambda game, player: game.sanity >= 1_000_000),
    "all_difficulties": Achievement("Ph'nglui Mglw'nafh Fhtagn", "Devour a world on every difficulty",
                                    lambda game, player: all(player.devoured(d) > 0 for d in DIFFICULTIES)),
    "total_10": devoured_count("Harbinger of the End", 10),
    "total_25": devoured_count("Devourer of Worlds", 25),
    "total_50": devoured_count("The Daemon Sultan", 50),
    "all_names": Achievement("The Whole Pantheon Dreams", "Devour a world as each of the nine named Great Old Ones",
                             lambda game, player: set(GREAT_OLD_ONES) <= player.names),
    "devour_quick": devoured_on("quick"),
    "quick_fast": devoured_within("Hounds of Tindalos", "quick", 20, "idle"),
    "quick_fast_clicker": devoured_within("The Hounds Are Loosed", "quick", 15, "clicker"),
    "quick_20": devoured_count("An Insatiable Appetite", 20, "quick"),
    "devour_short": devoured_on("short"),
    "short_fast": devoured_within("Up Before Dawn", "short", 80, "idle"),
    "short_fast_clicker": devoured_within("Roused by Drums", "short", 60, "clicker"),
    "short_10": devoured_count("Ten Restless Nights", 10, "short"),
    "short_streak": Achievement("A Recurring Dream", f"Devour 3 worlds in a row under one name on {DIFFICULTIES['short'].name}",
                                lambda game, player: game.difficulty == "short" and game.worlds_destroyed >= 3, "short"),
    "devour_recommended": devoured_on("recommended"),
    "recommended_fast": devoured_within("The Dreamer Stirs Early", "recommended", 5 * 60, "idle"),
    "recommended_fast_clicker": devoured_within("The Dreamer Thrashes", "recommended", 4 * 60, "clicker"),
    "recommended_5": devoured_count("A Feast of Worlds", 5, "recommended"),
    "devour_long_haul": devoured_on("long_haul"),
    "long_haul_fast": devoured_within("The Long Night Cut Short", "long_haul", 22 * 60, "idle"),
    "long_haul_fast_clicker": devoured_within("No Rest for the Dreamer", "long_haul", 18 * 60, "clicker"),
    "long_haul_3": devoured_count("The Shadow Out of Time", 3, "long_haul"),
    "devour_eternal": devoured_on("eternal"),
    "eternal_fast": devoured_within("Even Death Hurries", "eternal", 75 * 60, "idle"),
    "eternal_fast_clicker": devoured_within("Even Death Runs", "eternal", 60 * 60, "clicker"),
    "eternal_2": devoured_count("Even Death May Die", 2, "eternal"),
}

# The achievements page: the ones not tied to a difficulty first, then each difficulty in ladder order
ACHIEVEMENT_GROUPS: Dict[str, Tuple[str, Dict[str, Achievement]]] = {
    "all": ("All", {key: achievement for key, achievement in ACHIEVEMENTS.items() if achievement.difficulty is None}),
    **{difficulty: (DIFFICULTIES[difficulty].name,
                    {key: achievement for key, achievement in ACHIEVEMENTS.items() if achievement.difficulty == difficulty})
       for difficulty in DIFFICULTIES},
}


def pending_achievements(game: Game, player: PlayerRecord) -> List[str]:
    """Achievements the game and player now qualify for that the player hasn't earned yet"""
    return [achievement_id for achievement_id, achievement in ACHIEVEMENTS.items()
            if achievement_id not in player.earned and achievement.earned(game, player)]


def new_achievements(game: Game, player: PlayerRecord) -> List[str]:
    """Pending achievements, marked as earned"""
    new = pending_achievements(game, player)
    player.earned.update(new)
    return new
