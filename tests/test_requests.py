import os
import time

import pytest
from ronovo_portfolio_auth import portfolio_sso
from ronovo_portfolio_auth.security_questions import QUESTIONS

import webapp
from helpers import ANSWER, PASSWORD, new_game, play, register, signer, sync
from main import DIFFICULTIES, MODES, new_world_id
from menu import GREAT_OLD_ONES

KEY, PUBLIC_KEY = portfolio_sso.new_key_pair()


@pytest.fixture
def portfolio(monkeypatch):
    monkeypatch.setenv("PORTFOLIO_SSO_URL", "http://portfolio.test")
    monkeypatch.setenv("PORTFOLIO_SSO_PUBLIC_KEY", PUBLIC_KEY)


def portfolio_login(client, sub="7", username="Gambler"):
    client.get("/sso/login")
    with client.session_transaction() as session:
        state = session["portfolio_state"]
    token = portfolio_sso.issue(KEY, "dead-but-dreaming", sub, username)
    return client.post("/sso/callback", data={"state": state, "token": token})


def account(client):
    return client.get("/api/account").get_json()


def test_the_page_offers_every_difficulty_and_name(client):
    page = client.get("/").get_data(as_text=True)
    for difficulty in DIFFICULTIES.values():
        assert difficulty.name in page
    for mode in MODES.values():
        assert mode.name in page and mode.reason in page
    assert all(name in page for name in GREAT_OLD_ONES)
    assert "portfolio.test" not in page


def test_the_page_offers_the_portfolio_login_when_it_is_on(client, portfolio):
    assert "http://portfolio.test" in client.get("/").get_data(as_text=True)


def test_a_random_name_is_a_great_old_one(client):
    assert client.get("/api/random-name").get_json()["name"] in GREAT_OLD_ONES


@pytest.mark.parametrize("body", [{"name": "  "}, {"name": "x" * 21}, {"name": "Azathoth", "difficulty": "nightmare"},
                                  {"name": "Azathoth", "difficulty": 3}])
def test_a_new_game_needs_a_name_and_a_known_difficulty(client, body):
    assert client.post("/api/new-game", json=body).status_code == 400


@pytest.mark.parametrize("data", [b"[1, 2]", b"not json", b'"a string"'])
def test_requests_must_be_json_objects(client, data):
    assert client.post("/api/play", data=data, content_type="application/json").status_code == 400


def test_deeply_nested_json_is_refused(client):
    nested = b"[" * 50_000 + b"]" * 50_000
    assert client.post("/api/play", data=nested, content_type="application/json").status_code == 400


def test_a_signed_save_with_missing_fields_is_refused(client):
    assert play(client, signer.sign({"player_name": "Azathoth"})).status_code == 400


def test_actions_the_game_does_not_know_are_skipped(client):
    actions = [{"type": "summon", "target": "cultists"}, "resource", {"type": "resource", "target": "cultists"}]
    view = play(client, new_game(client), actions=actions).get_json()["view"]
    assert [r["processing"] for r in view["resources"] if r["key"] == "cultists"] == [True]


def test_only_valid_devours_and_achievements_are_kept_from_a_record(client):
    world = new_world_id()
    record = signer.sign({"achievements": ["cult_leader", "made_up", 7],
                          "devours": [[world, 1, "quick"], [world, 0, "quick"], [world, True, "quick"],
                                      ["not-an-id", 1, "quick"], [world, 2, "nightmare"], [world, 3], "x"],
                          "names": ["Dagon", "dagon", "Azathoth", 7]})
    returned = play(client, new_game(client), record).get_json()["record"]
    assert returned["achievements"] == ["cult_leader"]
    assert returned["devours"] == [[world, 1, "quick"]]
    assert returned["names"] == ["Dagon"]
    without = signer.sign({"achievements": [], "devours": "none", "names": "none"})
    assert play(client, new_game(client), without).get_json()["record"]["names"] == []


@pytest.mark.parametrize("seconds, shown", [(61, "1m 01s"), (3661, "1h 01m 01s"), (90061, "1d 01h 01m 01s")])
def test_the_dream_time_reads_in_minutes_hours_and_days(seconds, shown):
    assert webapp.format_duration(seconds) == shown


def test_a_new_password_logs_out_other_browsers(client):
    register(client)
    other = client.application.test_client()
    other.post("/api/reset-password", json={"username": "pilot", "answer": ANSWER, "password": "anotherpassword"})
    assert account(client)["username"] is None


def test_account_requests_explain_what_is_wrong(client):
    response = client.post("/api/register", json={"username": "pilot", "password": "short", "question": QUESTIONS[0],
                                                  "answer": ANSWER})
    assert (response.status_code, response.get_json()["error"]) == (400, "Passwords need at least 8 characters")
    assert client.post("/api/reset-question", json={"username": " "}).get_json() == {"error": "Enter your username"}
    response = client.post("/api/reset-question", json={"username": "ghost"})
    assert response.get_json() == {"error": "There is no account with that username"}


def test_the_first_portfolio_login_waits_for_a_choice(client, portfolio):
    assert portfolio_login(client).status_code == 302
    assert account(client) == {"username": None, "portfolio_pending": "Gambler"}


def test_a_new_account_for_a_portfolio_login_opens_on_every_device(client, portfolio):
    portfolio_login(client)
    assert client.post("/api/portfolio/new").get_json() == {"username": "Gambler"}
    laptop = client.application.test_client()
    portfolio_login(laptop)
    assert account(laptop) == {"username": "Gambler", "portfolio_pending": None}


def test_a_portfolio_login_links_an_existing_account(client, portfolio):
    register(client.application.test_client())
    portfolio_login(client)
    wrong = client.post("/api/portfolio/link", json={"username": "pilot", "password": "wrong password"})
    assert wrong.status_code == 400
    assert client.post("/api/portfolio/link", json={"username": "pilot", "password": PASSWORD}).get_json() == {
        "username": "pilot"}


def test_a_waiting_portfolio_login_expires(client, portfolio, monkeypatch):
    portfolio_login(client)
    later = time.time() + webapp.PORTFOLIO_CHOICE_SECONDS + 1
    monkeypatch.setattr(webapp.time, "time", lambda: later)
    assert account(client)["portfolio_pending"] is None


def test_sync_skips_parts_it_cannot_use(client):
    register(client)
    good = new_game(client)
    response = client.post("/api/sync", json={"saves": "all of them", "deleted": "everything", "record": None})
    assert response.status_code == 200
    stored = sync(client, good, signer.sign({"player_name": "Broken"}))
    assert list(stored["saves"]) == ["Azathoth"]


def test_the_secret_key_is_made_once_and_kept(tmp_path, monkeypatch):
    monkeypatch.delenv("DEAD_BUT_DREAMING_SECRET_KEY", raising=False)
    monkeypatch.setattr(webapp, "DATA_DIR", str(tmp_path))
    key = webapp.load_secret_key()
    assert len(key) == 64
    assert webapp.load_secret_key() == key
    assert os.listdir(tmp_path) == ["secret_key"]


def test_a_worker_starting_second_uses_the_first_workers_key(tmp_path, monkeypatch):
    monkeypatch.delenv("DEAD_BUT_DREAMING_SECRET_KEY", raising=False)
    monkeypatch.setattr(webapp, "DATA_DIR", str(tmp_path))
    path = tmp_path / "secret_key"

    def first_worker_got_there(_source, _target):
        path.write_text("first worker's key")
        raise FileExistsError

    monkeypatch.setattr(webapp.os, "link", first_worker_got_there)
    assert webapp.load_secret_key() == "first worker's key"
    assert os.listdir(tmp_path) == ["secret_key"]


def test_the_coverage_reports_are_served_from_their_folder(client, monkeypatch, tmp_path):
    reports = tmp_path / "coverage"
    (reports / "python").mkdir(parents=True)
    (reports / "index.html").write_text("landing page", encoding="utf-8")
    (reports / "python" / "index.html").write_text("python report", encoding="utf-8")
    (tmp_path / "secret.txt").write_text("secret", encoding="utf-8")
    monkeypatch.setattr(webapp, "COVERAGE_DIR", str(reports))
    assert client.get("/coverage").status_code == 308
    assert client.get("/coverage/").data == b"landing page"
    assert client.get("/coverage/python/").data == b"python report"
    for path in ("/coverage/js/", "/coverage/../secret.txt", "/coverage/%2e%2e/secret.txt"):
        assert client.get(path).status_code == 404, path
