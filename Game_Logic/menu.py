import random
from typing import Optional

MAX_NAME_LENGTH = 20

GREAT_OLD_ONES = [
    "Cthulhu",
    "Nyarlathotep",
    "Yog-Sothoth",
    "Shub-Niggurath",
    "Hastur",
    "Dagon",
    "Yig",
    "Tsathoggua",
    "Ghatanothoa"
]

def random_name() -> str:
    return random.choice(GREAT_OLD_ONES)


def great_old_one(name: str) -> Optional[str]:
    """The named Great Old One a player name matches, ignoring case, or None"""
    return next((old_one for old_one in GREAT_OLD_ONES if old_one.lower() == name.lower()), None)
