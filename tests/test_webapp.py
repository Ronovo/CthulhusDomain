import json
import time

import pytest

import accounts
import webapp
from achievements import ACHIEVEMENTS, PlayerRecord
from helpers import ANSWER, PASSWORD, new_game, play, register, signer, sync
from main import DIFFICULTIES, Game, new_resources
from signing import Signer


def almost_devoured(name="Dagon"):
    """A signed quick world one upgrade short of being devoured, with the sanity to buy it."""
    game = Game(name, difficulty="quick")
    for resource in game.resources.values():
        resource.is_unlocked = resource.has_manager = True
    upgrades = list(game.upgrade_manager.upgrades.values())
    for upgrade in upgrades[:-1]:
        upgrade.purchased = True
    game.sanity = upgrades[-1].cost
    return signer.sign(game.save_game_state()), list(game.upgrade_manager.upgrades)[-1]


def test_signatures_survive_the_browser_re_encoding_numbers():
    key = Signer("key")
    signed = key.sign({"sanity": 5.0, "big": 1e16, "flag": True, "name": "x"})
    # JSON.stringify writes 5.0 as 5 and 1e16 as 10000000000000000.
    from_browser = json.loads(json.dumps(signed).replace("5.0", "5").replace("1e+16", "10000000000000000"))
    assert key.verify(from_browser) is not None
    assert key.verify({**from_browser, "sanity": 6}) is None
    assert key.verify({"sanity": 5}) is None


def test_a_new_game_plays_and_comes_back_signed(client):
    save = new_game(client)
    reply = play(client, save, actions=[{"type": "resource", "target": "cultists"}]).get_json()
    assert reply["save"]["signature"] != save["signature"]
    assert reply["view"]
    assert set(reply["record"]) == {"achievements", "devours", "signature"}


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
    data = Game("x").save_game_state()
    data["last_saved"] = time.time() + 10 ** 6
    assert Game(load_data=data).last_saved <= time.time()


def test_a_manager_keeps_producing_while_the_game_is_closed():
    game = Game("x")
    cultists = game.resources["cultists"]
    cultists.has_manager = cultists.is_processing = True
    game.advance(game.last_saved + 10 * cultists.production_time + 0.5)
    assert game.sanity == 10 * game.production_rate(cultists)


def test_a_hand_click_finishes_one_cycle_however_long_the_game_was_closed():
    game = Game("x")
    game.click_resource("cultists")
    game.advance(game.last_saved + 3600)
    assert game.sanity == game.production_rate(game.resources["cultists"])
    assert not game.resources["cultists"].is_processing


def test_harder_difficulties_cost_more_from_the_second_tier():
    quick, eternal = Game("x", difficulty="quick"), Game("x", difficulty="eternal")
    assert quick.resources["cultists"].unlock_cost == eternal.resources["cultists"].unlock_cost
    assert quick.resources["ancient_tomes"].unlock_cost < eternal.resources["ancient_tomes"].unlock_cost
    assert quick.upgrade_manager.upgrades["great_old_ones_prod_5x"].cost < \
        eternal.upgrade_manager.upgrades["great_old_ones_prod_5x"].cost


def test_next_upgrades_are_the_cheapest_speed_and_production_of_each_unlocked_resource():
    game = Game("x")
    assert [upgrade_id for upgrade_id, _ in game.next_upgrades()] == ["cultists_speed_2x", "cultists_prod_2x"]
    game.upgrade_manager.upgrades["cultists_speed_2x"].purchased = True
    game.resources["ancient_tomes"].is_unlocked = True
    assert [upgrade_id for upgrade_id, _ in game.next_upgrades()] == [
        "cultists_speed_3x", "cultists_prod_2x", "ancient_tomes_speed_2x", "ancient_tomes_prod_2x"]


def test_buying_the_last_upgrade_devours_the_world_once():
    save, last = almost_devoured()
    game = Game(load_data=signer.verify(save))
    game.buy_upgrade(last)
    assert game.worlds_destroyed == 1
    assert game.devoured_now == [(game.world_id, 1, "quick")]


def test_a_new_world_is_only_begun_after_a_devour():
    game = Game("x")
    world_id = game.world_id
    game.sanity = 50
    game.reset_game()
    assert (game.world_id, game.sanity) == (world_id, 50)


def test_replaying_a_save_counts_its_devour_once(client):
    save, last = almost_devoured()
    record = None
    for _ in range(3):
        record = play(client, save, record, [{"type": "upgrade", "target": last}]).get_json()["record"]
    assert len(record["devours"]) == 1


def test_two_browsers_devours_add_up_on_the_account(client):
    register(client)
    records = []
    for name in ("Dagon", "Hydra"):
        save, last = almost_devoured(name)
        records.append(play(client, save, None, [{"type": "upgrade", "target": last}]).get_json()["record"])
    for record in records:
        merged = sync(client, record=record)["record"]
    assert len(merged["devours"]) == 2


def test_the_copy_with_more_progress_wins_over_a_newer_one(client):
    register(client)
    save = signer.verify(new_game(client))
    ahead = Game(load_data=save)
    ahead.worlds_destroyed = 2
    stale = Game(load_data=save)
    stale.last_saved = time.time()
    sync(client, signer.sign(ahead.save_game_state()))
    reply = sync(client, signer.sign(stale.save_game_state()))
    assert reply["saves"]["Azathoth"]["worlds_destroyed"] == 2


def test_beginning_a_new_world_after_a_devour_reaches_the_account(client):
    register(client)
    save, last = almost_devoured()
    devoured = play(client, save, None, [{"type": "upgrade", "target": last}]).get_json()["save"]
    sync(client, devoured)
    reply = play(client, devoured, actions=[{"type": "reset"}]).get_json()
    stored = sync(client)["saves"]["Dagon"]
    assert stored["world_id"] == reply["save"]["world_id"] != devoured["world_id"]
    assert stored["worlds_destroyed"] == 1
    assert sync(client, devoured)["saves"]["Dagon"]["world_id"] == stored["world_id"]


def test_a_new_game_under_a_taken_name_overwrites_the_old_world(client):
    register(client)
    old = new_game(client, "Dagon")
    ahead = Game(load_data=signer.verify(old))
    ahead.worlds_destroyed = 3
    sync(client, signer.sign(ahead.save_game_state()))
    new = new_game(client, "Dagon")
    reply = sync(client, new)
    assert reply["saves"]["Dagon"]["world_id"] == new["world_id"]
    assert old["world_id"] in reply["deleted"]


def test_a_deleted_world_stays_deleted(client):
    register(client)
    old = new_game(client, "Dagon")
    sync(client, old)
    reply = sync(client, deleted=[old["world_id"]])
    assert "Dagon" not in reply["saves"]
    assert reply["deleted"] == [old["world_id"]]

    play(client, old, backup=True)
    assert "Dagon" not in sync(client, old)["saves"]
    assert "Dagon" in sync(client, new_game(client, "Dagon"))["saves"]


def test_deletes_keep_only_valid_ids_and_the_newest_few(client, monkeypatch):
    monkeypatch.setattr(accounts, "MAX_DELETED", 2)
    register(client)
    sync(client, deleted=["x" * 900_000, "not-an-id"])
    assert sync(client)["deleted"] == []
    ids = [f"{n:016x}" for n in range(3)]
    for world_id in ids:
        sync(client, deleted=[world_id])
    assert sorted(sync(client)["deleted"]) == ids[1:]


def test_sync_needs_a_login_and_skips_edited_saves(client):
    assert client.post("/api/sync", json={}).status_code == 401
    register(client)
    kept = new_game(client, name="Kept")
    edited = {**new_game(client, name="Edited"), "sanity": 99.0}
    reply = sync(client, kept, edited)
    assert set(reply["saves"]) == {"Kept"}
    assert all("signature" in save for save in reply["saves"].values())


def test_a_closing_page_gets_no_reply(client):
    register(client)
    response = client.post("/api/sync", json={"saves": {"a": new_game(client)}, "reply": False})
    assert response.status_code == 204
    assert "Azathoth" in sync(client)["saves"]


def test_an_account_holds_at_most_max_saves(client, monkeypatch):
    monkeypatch.setattr(accounts, "MAX_SAVES", 2)
    register(client)
    reply = sync(client, *(new_game(client, name=name) for name in ("One", "Two", "Three")))
    assert len(reply["saves"]) == 2


def test_register_log_out_and_log_back_in(client):
    register(client, "pilot")
    assert client.get("/api/account").get_json()["username"] == "pilot"
    client.post("/api/logout")
    assert client.get("/api/account").get_json()["username"] is None
    response = client.post("/api/login", json={"username": "pilot", "password": PASSWORD})
    assert response.get_json() == {"username": "pilot"}


def test_wrong_passwords_lock_the_login(client):
    register(client, "pilot")
    for _ in range(5):
        assert client.post("/api/login", json={"username": "pilot", "password": "wrong password"}).status_code == 401
    response = client.post("/api/login", json={"username": "pilot", "password": PASSWORD})
    assert response.status_code == 401


def test_a_password_reset_needs_the_right_answer(client):
    register(client, "pilot")
    client.post("/api/logout")
    question = client.post("/api/reset-question", json={"username": "pilot"}).get_json()["question"]
    assert question
    wrong = client.post("/api/reset-password", json={"username": "pilot", "answer": "red", "password": "newpassword"})
    assert wrong.get_json()["error"] == "That answer is wrong"
    right = client.post("/api/reset-password", json={"username": "pilot", "answer": ANSWER, "password": "newpassword"})
    assert right.get_json() == {"reset": True}
    assert client.post("/api/login", json={"username": "pilot", "password": "newpassword"}).status_code == 200


def test_resetting_an_unknown_username_says_there_is_no_account(client):
    response = client.post("/api/reset-question", json={"username": "ghost"})
    assert response.get_json()["error"] == accounts.NO_ACCOUNT


@pytest.mark.parametrize("url", ["/api/portfolio/link", "/api/portfolio/new"])
def test_portfolio_choices_need_a_waiting_portfolio_login(client, url):
    response = client.post(url, json={"username": "pilot", "password": PASSWORD})
    assert response.get_json()["error"] == webapp.PORTFOLIO_LOGIN_EXPIRED


def test_every_difficulty_means_a_devour_on_each_one():
    game = Game("Hastur", difficulty="eternal")
    every = ACHIEVEMENTS["all_difficulties"].earned
    world = "0" * 16
    assert not every(game, PlayerRecord(earned={f"devour_{d}" for d in DIFFICULTIES}, devours={(world, 1, "eternal")}))
    assert every(game, PlayerRecord(earned=set(), devours={(world, n, d) for n, d in enumerate(DIFFICULTIES, 1)}))


def test_every_resource_has_a_full_set_of_upgrades():
    upgrades = Game("x").upgrade_manager
    assert {upgrade.resource for upgrade in upgrades.upgrades.values()} == set(new_resources())
    assert upgrades.upgrades["star_spawn_speed_3x"].description == "3x Speed for Star Spawn"
