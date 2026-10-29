import itertools
import json
import time

import webapp
from conftest import new_game, register
from achievements import ACHIEVEMENTS, PlayerRecord
from main import DIFFICULTIES, Game
from signing import Signer

_names = itertools.count()


def username():
    return f"player{next(_names)}"


def play(client, save, record=None, actions=()):
    return client.post("/api/play", json={"save": save, "record": record, "actions": list(actions)})


def test_signatures_survive_the_browser_re_encoding_numbers():
    signer = Signer("key")
    signed = signer.sign({"sanity": 5.0, "big": 1e16, "flag": True, "name": "x"})
    # JSON.stringify writes 5.0 as 5 and 1e16 as 10000000000000000.
    from_browser = json.loads(json.dumps(signed).replace("5.0", "5").replace("1e+16", "10000000000000000"))
    assert signer.verify(from_browser) is not None
    assert signer.verify({**from_browser, "sanity": 6}) is None
    assert signer.verify({"sanity": 5}) is None


def test_a_new_game_plays_and_comes_back_signed(client):
    save = new_game(client)
    reply = play(client, save, actions=[{"type": "resource", "target": "cultists"}]).get_json()
    assert reply["save"]["signature"] != save["signature"]
    assert reply["view"]
    assert set(reply["record"]) == {"achievements", "devoured", "signature"}


def test_an_edited_save_is_refused(client):
    save = new_game(client)
    response = play(client, {**save, "sanity": 1e12})
    assert response.status_code == 400
    assert response.get_json()["error"] == webapp.EDITED_SAVE


def test_an_edited_record_counts_as_empty(client):
    save = new_game(client)
    record = play(client, save).get_json()["record"]
    forged = {**record, "achievements": ["devour_eternal"]}
    assert "devour_eternal" not in play(client, save, forged).get_json()["record"]["achievements"]


def test_only_the_first_actions_of_a_request_run(client, monkeypatch):
    clicks = []
    monkeypatch.setattr(Game, "click_resource", lambda self, target: clicks.append(target))
    play(client, new_game(client), actions=[{"type": "resource", "target": "cultists"}] * 5000)
    assert len(clicks) == webapp.MAX_ACTIONS_PER_REQUEST


def test_a_save_from_the_future_is_clamped_to_now():
    game = Game("x")
    data = game.save_game_state()
    data["last_saved"] = time.time() + 10 ** 6
    assert Game(load_data=data).last_saved <= time.time()


def test_the_copy_with_more_progress_wins_over_a_newer_one(client):
    register(client, username())
    save = new_game(client)
    ahead = Game(load_data=Signer("test").verify(save))
    ahead.worlds_destroyed = 2
    stale = Game(load_data=Signer("test").verify(save))
    stale.last_saved = time.time()
    signer = webapp.Signer("test")
    client.post("/api/sync", json={"saves": {"a": signer.sign(ahead.save_game_state())}})
    reply = client.post("/api/sync", json={"saves": {"a": signer.sign(stale.save_game_state())}}).get_json()
    assert reply["saves"]["Azathoth"]["worlds_destroyed"] == 2


def test_sync_needs_a_login_and_skips_edited_saves(client):
    assert client.post("/api/sync", json={}).status_code == 401
    register(client, username())
    save = new_game(client, name="Kept")
    edited = {**new_game(client, name="Edited"), "sanity": 99.0}
    reply = client.post("/api/sync", json={"saves": {"Kept": save, "Edited": edited}}).get_json()
    assert set(reply["saves"]) == {"Kept"}
    assert all("signature" in save for save in reply["saves"].values())


def test_an_account_holds_at_most_max_saves(client, monkeypatch):
    import accounts

    monkeypatch.setattr(accounts, "MAX_SAVES", 2)
    register(client, username())
    saves = {name: new_game(client, name=name) for name in ("One", "Two", "Three")}
    reply = client.post("/api/sync", json={"saves": saves}).get_json()
    assert len(reply["saves"]) == 2


def test_register_log_out_and_log_back_in(client):
    name = username()
    register(client, name)
    assert client.get("/api/account").get_json()["username"] == name
    client.post("/api/logout")
    assert client.get("/api/account").get_json()["username"] is None
    response = client.post("/api/login", json={"username": name, "password": "longpassword"})
    assert response.get_json() == {"username": name}


def test_wrong_passwords_lock_the_login(client):
    name = username()
    register(client, name)
    for _ in range(5):
        assert client.post("/api/login", json={"username": name, "password": "wrong password"}).status_code == 401
    response = client.post("/api/login", json={"username": name, "password": "longpassword"})
    assert response.status_code == 401


def test_a_deleted_world_stays_deleted_until_a_new_one_takes_its_name(client):
    register(client, username())
    old = new_game(client, "Dagon")
    client.post("/api/sync", json={"saves": {"Dagon": old}})
    time.sleep(0.02)
    client.post("/api/delete-save", json={"name": "Dagon"})

    reply = client.post("/api/sync", json={"saves": {"Dagon": old}}).get_json()
    assert "Dagon" not in reply["saves"]
    assert reply["deleted"] == ["Dagon"]

    time.sleep(0.02)
    reply = client.post("/api/sync", json={"saves": {"Dagon": new_game(client, "Dagon")}}).get_json()
    assert "Dagon" in reply["saves"]
    assert reply["deleted"] == []


def test_every_difficulty_means_a_devour_on_each_one():
    game = Game("Hastur", difficulty="eternal")
    every = ACHIEVEMENTS["all_difficulties"].earned
    assert not every(game, PlayerRecord(earned={f"devour_{d}" for d in DIFFICULTIES}, devoured={"eternal": 1}))
    assert every(game, PlayerRecord(earned=set(), devoured={d: 1 for d in DIFFICULTIES}))
