import pytest

from main import DIFFICULTIES, MAX_TAPS_PER_TICK, TAP_BOOST, Game, world_cost
from menu import GREAT_OLD_ONES, great_old_one, random_name
from upgrades import UpgradeManager


def test_an_unknown_difficulty_is_refused():
    with pytest.raises(ValueError, match="Unknown difficulty"):
        Game("Azathoth", difficulty="nightmare")


def test_clicking_a_resource_that_does_not_exist_does_nothing():
    game = Game("Azathoth")
    before = game.save_game_state()
    game.click_resource("shoggoths")
    assert game.save_game_state() == before


def test_a_locked_resource_unlocks_only_once_affordable():
    game = Game("Azathoth")
    tomes = game.resources["ancient_tomes"]
    game.sanity = tomes.unlock_cost - 1
    game.click_resource("ancient_tomes")
    assert not tomes.is_unlocked
    game.sanity = tomes.unlock_cost + 2
    game.click_resource("ancient_tomes")
    assert tomes.is_unlocked
    assert game.sanity == 2
    assert not tomes.is_processing


def test_clicking_a_running_resource_does_not_restart_it():
    game = Game("Azathoth")
    cultists = game.resources["cultists"]
    game.click_resource("cultists")
    cultists.progress = 1.5
    game.click_resource("cultists")
    assert cultists.progress == 1.5


@pytest.mark.parametrize("key", ["shoggoths", "ancient_tomes"])
def test_a_manager_needs_an_unlocked_resource(key):
    game = Game("Azathoth")
    game.sanity = 1e12
    game.hire_manager(key)
    assert game.sanity == 1e12


def test_hiring_a_manager_costs_once_and_starts_production():
    game = Game("Azathoth")
    cultists = game.resources["cultists"]
    game.sanity = cultists.manager_cost - 1
    game.hire_manager("cultists")
    assert not cultists.has_manager
    game.sanity = cultists.manager_cost * 2
    game.hire_manager("cultists")
    game.hire_manager("cultists")
    assert cultists.has_manager and cultists.is_processing
    assert game.sanity == cultists.manager_cost


@pytest.mark.parametrize("upgrade_id, sanity", [("no_such_upgrade", 1e12), ("cultists_speed_2x", 0)])
def test_an_upgrade_that_cannot_be_bought_costs_nothing(upgrade_id, sanity):
    manager = UpgradeManager()
    assert manager.purchase(upgrade_id, sanity) == (False, sanity)


def test_an_upgrade_is_bought_once():
    manager = UpgradeManager()
    cost = manager.upgrades["cultists_speed_2x"].cost
    assert manager.purchase("cultists_speed_2x", cost + 5) == (True, 5)
    assert manager.purchase("cultists_speed_2x", cost + 5) == (False, cost + 5)


def test_a_game_that_cannot_afford_an_upgrade_keeps_its_sanity():
    game = Game("Azathoth")
    game.sanity = 1
    game.buy_upgrade("cultists_speed_2x")
    assert game.sanity == 1
    assert not game.upgrade_manager.upgrades["cultists_speed_2x"].purchased


def test_endless_mode_waits_for_a_devour():
    game = Game("Azathoth")
    game.enter_endless()
    assert not game.endless
    game.devoured_seconds = 60.0
    game.enter_endless()
    assert game.endless


def test_a_tap_hurries_a_working_resource_only_in_clicker_mode():
    for mode, taps in (("clicker", 1), ("idle", 0)):
        game = Game("Azathoth", mode=mode)
        cultists = game.resources["cultists"]
        game.click_resource("cultists")
        game.click_resource("cultists")
        assert cultists.progress == pytest.approx(cultists.production_time * TAP_BOOST * taps)
        assert cultists.is_processing


def test_taps_on_one_resource_are_capped_per_request():
    game = Game("Azathoth", mode="clicker")
    cultists = game.resources["cultists"]
    game.click_resource("cultists")
    for _ in range(MAX_TAPS_PER_TICK + 2):
        game.click_resource("cultists")
    assert cultists.progress == pytest.approx(cultists.production_time * TAP_BOOST * MAX_TAPS_PER_TICK)


def test_a_tap_that_completes_a_cycle_pays_out_at_once():
    game = Game("Azathoth", mode="clicker")
    cultists = game.resources["cultists"]
    game.click_resource("cultists")
    cultists.progress = cultists.production_time * (1 - TAP_BOOST / 2)
    game.click_resource("cultists")
    assert game.sanity == game.production_rate(cultists)
    assert not cultists.is_processing and cultists.progress == 0

    managed = Game("Azathoth", mode="clicker")
    cultists = managed.resources["cultists"]
    cultists.has_manager = cultists.is_processing = True
    cultists.progress = cultists.production_time * (1 - TAP_BOOST / 2)
    managed.click_resource("cultists")
    assert managed.sanity == managed.production_rate(cultists)
    assert cultists.is_processing
    assert cultists.progress == pytest.approx(cultists.production_time * TAP_BOOST / 2)


def test_an_unknown_mode_is_refused():
    with pytest.raises(ValueError, match="Unknown mode"):
        Game("Azathoth", mode="frantic")


def test_a_save_without_a_mode_plays_in_idle_mode():
    data = Game("Azathoth").save_game_state()
    del data["mode"]
    loaded = Game(load_data=data)
    assert loaded.mode == "idle"
    assert loaded.save_game_state()["mode"] == "idle"
    assert Game(load_data=Game("Azathoth", mode="clicker").save_game_state()).mode == "clicker"


def test_a_random_name_is_one_of_the_great_old_ones():
    assert {random_name() for _ in range(50)} <= set(GREAT_OLD_ONES)


def test_a_player_name_matches_a_great_old_one_in_any_case():
    assert great_old_one("yog-sothoth") == "Yog-Sothoth"
    assert great_old_one("Azathoth") is None


def test_sanity_gathered_is_what_is_held_plus_what_was_spent():
    game = Game("Azathoth")
    assert game.sanity_gathered() == 0
    game.sanity = 100
    game.click_resource("ancient_tomes")
    game.hire_manager("cultists")
    game.buy_upgrade("cultists_prod_2x")
    assert game.sanity == 45
    assert game.sanity_gathered() == 100


def test_a_worlds_cost_grows_with_the_difficulty():
    costs = [world_cost(difficulty) for difficulty in DIFFICULTIES]
    assert costs == sorted(costs) and len(set(costs)) == len(costs)
    game = Game("Azathoth", difficulty="quick")
    expected = sum(resource.unlock_cost + resource.manager_cost for resource in game.resources.values())
    expected -= game.resources["cultists"].unlock_cost
    expected += sum(upgrade.cost for upgrade in game.upgrade_manager.upgrades.values())
    assert world_cost("quick") == expected
