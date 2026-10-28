"""Security questions for password resets. The same file is in every Python portfolio app."""
import hashlib
import hmac
from typing import Optional

QUESTIONS = [
    "What is your mother's maiden name?",
    "What was the name of your first pet?",
    "In what city were you born?",
    "What was the make and model of your first car?",
    "What was the name of your elementary school?",
    "What was the name of your childhood best friend?",
    "Who was your favorite teacher?",
    "What street did you grow up on?",
    "What is your father's middle name?",
    "What was your childhood nickname?",
    "In what city did your parents meet?",
    "What was the first concert you went to?",
    "What was the name of your first employer?",
    "In what hospital were you born?",
    "What was your favorite food as a child?",
    "What was the first video game you played?",
    "What is your oldest sibling's middle name?",
    "What was the name of your first stuffed animal?",
    "What was your high school mascot?",
    "In what city or town was your first job?",
    "What was the last name of your third grade teacher?",
    "What is your maternal grandmother's first name?",
    "What was your dream job as a child?",
    "What was your favorite book as a child?",
    "What is your favorite movie?",
    "Where did you go on your first vacation?",
    "What was the name of your first roommate?",
    "What was the first album you bought?",
    "What is your paternal grandfather's first name?",
    "What sport did you play most as a child?",
]
MAX_ANSWER_LENGTH = 100
MAX_RESET_FAILURES = 5
RESET_LOCK_SECONDS = 15 * 60


def normalize_answer(answer) -> str:
    """Answers match ignoring capitals and extra spaces"""
    return " ".join(str(answer or "").lower().split())


def problem(question, answer) -> Optional[str]:
    """What is wrong with a question and answer being set, or None when they are fine"""
    if question not in QUESTIONS:
        return "Pick a security question."
    normalized = normalize_answer(answer)
    if not normalized:
        return "Answer your security question."
    if len(normalized) > MAX_ANSWER_LENGTH:
        return f"Keep the security answer to {MAX_ANSWER_LENGTH} characters or fewer."
    return None


def stand_in_question(username: str, key: bytes) -> str:
    """The question shown for a username with no account. It is the same one every time, so the reset page
    doesn't reveal which usernames exist."""
    digest = hmac.new(key, username.lower().encode("utf-8"), hashlib.sha256).digest()
    return QUESTIONS[int.from_bytes(digest[:4], "big") % len(QUESTIONS)]
