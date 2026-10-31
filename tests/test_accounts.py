import sqlite3
import time

import pytest
from ronovo_portfolio_auth.security_questions import MAX_RESET_FAILURES, QUESTIONS

from accounts import AccountError, Accounts
from helpers import ANSWER, PASSWORD
from main import Game


@pytest.fixture
def accounts(tmp_path):
    return Accounts(str(tmp_path / "accounts.db"))


def register(accounts, username="pilot"):
    return accounts.register(username, PASSWORD, QUESTIONS[0], ANSWER)


@pytest.mark.parametrize("username, password, question, message", [
    ("pi", PASSWORD, QUESTIONS[0], "Usernames are 3-20"),
    ("pilot", "short", QUESTIONS[0], "Passwords need at least 8 characters"),
    ("pilot", PASSWORD, "Favorite color?", "Pick a security question."),
])
def test_registration_checks_the_details(accounts, username, password, question, message):
    with pytest.raises(AccountError, match=message):
        accounts.register(username, password, question, ANSWER)


def test_usernames_are_taken_whatever_their_case(accounts):
    register(accounts)
    with pytest.raises(AccountError, match="That username is taken"):
        register(accounts, "PILOT")


def test_an_account_links_to_one_portfolio_account(accounts):
    user_id = register(accounts)
    assert accounts.linked_user("sub-1") is None
    accounts.link_portfolio(user_id, "sub-1")
    assert accounts.linked_user("sub-1") == user_id
    with pytest.raises(AccountError, match="already linked to another portfolio account"):
        accounts.link_portfolio(user_id, "sub-2")
    other = register(accounts, "copilot")
    with pytest.raises(AccountError, match="already linked to another account here"):
        accounts.link_portfolio(other, "sub-1")


def test_a_portfolio_account_gets_its_own_name_with_a_number_when_taken(accounts):
    register(accounts, "Gambler")
    user_id = accounts.portfolio_user("sub-1", "gambler")
    assert accounts.username(user_id) == "gambler2"
    assert accounts.portfolio_user("sub-1", "gambler") == user_id
    assert accounts.username(accounts.portfolio_user("sub-2", "not a valid name!")) == "player"


def test_a_portfolio_account_has_no_security_question(accounts):
    accounts.portfolio_user("sub-1", "Gambler")
    with pytest.raises(AccountError, match="no security question"):
        accounts.security_question("Gambler")


def test_resets_stay_locked_after_too_many_wrong_answers(accounts):
    register(accounts)
    for _ in range(MAX_RESET_FAILURES):
        with pytest.raises(AccountError, match="That answer is wrong"):
            accounts.reset_password("pilot", "red", "newpassword")
    with pytest.raises(AccountError, match="Too many wrong answers"):
        accounts.reset_password("pilot", ANSWER, "newpassword")


def test_a_failed_write_is_rolled_back(accounts):
    user_id = register(accounts)
    first = Game("Azathoth").save_game_state()
    accounts.store_save(user_id, first, rank=lambda save: (save["sanity"],), started=lambda save: 0)

    def broken_rank(save):
        raise RuntimeError("disk full")

    second = {**first, "sanity": 5}
    with pytest.raises(RuntimeError):
        accounts.store_save(user_id, second, rank=broken_rank, started=lambda save: 0)
    assert accounts.load(user_id)["saves"]["Azathoth"]["sanity"] == 0
    with sqlite3.connect(accounts.path) as db:
        assert db.execute("SELECT COUNT(*) FROM saves").fetchone()[0] == 1


def test_names_devoured_as_merge_into_the_record_once(accounts):
    user_id = register(accounts)
    accounts.store_record(user_id, [], [], ["Cthulhu"])
    accounts.store_record(user_id, ["cult_leader"], [], ["Dagon", "Cthulhu"])
    accounts.store_record(user_id, ["cult_leader"], [], ["Cthulhu"])
    assert accounts.record(user_id) == {"achievements": ["cult_leader"], "devours": [], "names": ["Cthulhu", "Dagon"]}
    assert accounts.load(user_id)["names"] == ["Cthulhu", "Dagon"]


def test_an_older_world_under_a_taken_name_is_forgotten(accounts):
    user_id = register(accounts)
    newer = Game("Azathoth").save_game_state()
    older = {**Game("Azathoth").save_game_state(), "last_saved": time.time() - 3600}
    accounts.store_save(user_id, newer, rank=lambda save: (0,), started=lambda save: save["last_saved"])
    accounts.store_save(user_id, older, rank=lambda save: (0,), started=lambda save: save["last_saved"])
    stored = accounts.load(user_id)
    assert stored["saves"]["Azathoth"]["world_id"] == newer["world_id"]
    assert stored["deleted"] == [older["world_id"]]
