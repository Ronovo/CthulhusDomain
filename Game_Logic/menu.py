import random

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
