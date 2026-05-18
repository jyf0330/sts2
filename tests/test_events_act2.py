"""Focused tests for Act 2 event state changes."""

import sts2_env.events.act2  # noqa: F401

from sts2_env.cards.factory import create_card
from sts2_env.cards.factory import create_card
from sts2_env.cards.ironclad import create_ironclad_starter_deck
from sts2_env.cards.status import make_spore_mind
from sts2_env.core.enums import CardId
from sts2_env.events.act2 import (
    CrystalSphere,
    DollRoom,
    EndlessConveyor,
    FieldOfManSizedHoles,
    JungleMazeAdventure,
    LuminousChoir,
    MorphicGrove,
    PotionCourier,
    RanwidTheElder,
    RelicTrader,
    Symbiote,
    WhisperingHollow,
)
from sts2_env.run.reward_objects import EnchantCardsReward, RemoveCardReward, TransformCardsReward
from sts2_env.potions.base import create_potion
from sts2_env.run.run_manager import RunManager
from sts2_env.run.run_state import RunState


class _ExclusiveHighRng:
    def next_int(self, low: int, high: int) -> int:
        raise AssertionError(f"expected exclusive RNG call, got inclusive {low}, {high}")

    def next_int_exclusive(self, low: int, high: int) -> int:
        return high - 1

    def next_float_range(self, low: float, high: float) -> float:
        return high - 0.5


def test_act2_event_random_values_use_exclusive_upper_bounds():
    run_state = RunState(seed=28, character_id="Ironclad")
    run_state.initialize_run()
    run_state.rng.up_front = _ExclusiveHighRng()

    sphere = CrystalSphere()
    sphere.rng = _ExclusiveHighRng()
    sphere.calculate_vars(run_state)
    assert sphere._cost == 99

    maze = JungleMazeAdventure()
    maze.rng = _ExclusiveHighRng()
    maze.calculate_vars(run_state)
    assert maze._solo_gold == 164.5
    assert maze._join_gold == 64.5

    choir = LuminousChoir()
    choir.rng = _ExclusiveHighRng()
    choir.calculate_vars(run_state)
    assert choir._cost == 100


def test_luminous_choir_and_morphic_grove_apply_real_deck_changes():
    run_state = RunState(seed=29, character_id="Ironclad")
    run_state.initialize_run()
    run_state.player.deck = create_ironclad_starter_deck()
    run_state.player.gold = 200
    starting_deck = len(run_state.player.deck)

    choir = LuminousChoir()
    choir.ensure_vars_calculated(run_state)
    assert choir.is_allowed(run_state) is True
    choir_options = choir.generate_initial_options(run_state)
    assert [option.option_id for option in choir_options] == ["reach", "tribute"]
    assert all(option.enabled for option in choir_options)
    result = choir.choose(run_state, "reach")
    assert not result.finished
    choir.resolve_pending_choice(0)
    choir.resolve_pending_choice(1)
    result = choir.resolve_pending_choice(None)
    assert result.finished
    assert len(run_state.player.deck) == starting_deck - 1
    assert any(card.card_id == make_spore_mind().card_id for card in run_state.player.deck)

    grove = MorphicGrove()
    before_ids = [card.card_id for card in run_state.player.deck]
    result = grove.choose(run_state, "group")
    assert not result.finished
    grove.resolve_pending_choice(0)
    grove.resolve_pending_choice(1)
    result = grove.resolve_pending_choice(None)
    assert result.finished
    after_ids = [card.card_id for card in run_state.player.deck]
    assert before_ids != after_ids


def test_potion_courier_ranwid_and_whispering_hollow_change_inventory():
    run_state = RunState(seed=31, character_id="Ironclad")
    run_state.initialize_run()
    run_state.player.deck = create_ironclad_starter_deck()
    run_state.current_act_index = 1
    run_state.player.gold = 200
    run_state.player.add_potion(create_potion("FirePotion"))
    run_state.player.obtain_relic("BURNING_BLOOD")
    run_state.player.obtain_relic("ANCHOR")

    courier = PotionCourier()
    grab = courier.choose(run_state, "grab")
    assert grab.finished
    assert [reward.reward_type.name for reward in grab.rewards["reward_objects"]] == ["POTION", "POTION", "POTION"]

    ranwid = RanwidTheElder()
    run_state.rng.up_front.choice = lambda seq: seq[-1]
    ranwid_options = ranwid.generate_initial_options(run_state)
    assert [option.enabled for option in ranwid_options] == [True, True, True]
    chosen_potion_slot = ranwid._potion_slot
    starting_relics = len(run_state.player.relics)
    ranwid.choose(run_state, "gold")
    assert len(run_state.player.relics) == starting_relics + 1
    assert any(potion.slot_index == chosen_potion_slot for potion in run_state.player.held_potions())

    hollow = WhisperingHollow()
    starting_hp = run_state.player.current_hp
    before_ids = [card.card_id for card in run_state.player.deck]
    gold = hollow.choose(run_state, "gold")
    assert gold.finished
    assert [reward.reward_type.name for reward in gold.rewards["reward_objects"]] == ["POTION", "POTION"]
    result = hollow.choose(run_state, "hug")
    assert not result.finished
    hollow.resolve_pending_choice(0)
    after_ids = [card.card_id for card in run_state.player.deck]
    assert run_state.player.current_hp == starting_hp - 9
    assert before_ids != after_ids


def test_event_lifecycle_toggles_can_remove_potions_for_ranwid():
    mgr = RunManager(seed=3103, character_id="Ironclad")
    mgr.run_state.current_act_index = 1
    mgr.run_state.player.gold = 200
    mgr.run_state.player.add_potion(create_potion("FirePotion"))
    mgr.run_state.player.obtain_relic("ANCHOR")
    mgr.run_state.current_act.event_ids = ["RanwidTheElder"]

    mgr._enter_event()
    assert mgr.run_state.player.can_remove_potions is False

    result = mgr._do_event_choice({"option_id": "leave"})
    assert result["phase"] == RunManager.PHASE_MAP_CHOICE
    assert mgr.run_state.player.can_remove_potions is True


def test_ranwid_uses_the_randomly_selected_potion_and_relic_targets():
    potion_state = RunState(seed=3101, character_id="Ironclad")
    potion_state.initialize_run()
    potion_state.current_act_index = 1
    potion_state.player.gold = 200
    potion_state.player.add_potion(create_potion("FirePotion"))
    potion_state.player.add_potion(create_potion("FlexPotion"))
    potion_state.player.obtain_relic("ANCHOR")
    potion_state.player.obtain_relic("VAJRA")
    potion_event = RanwidTheElder()
    potion_state.rng.up_front.choice = lambda seq: seq[-1]

    potion_event.generate_initial_options(potion_state)
    assert potion_event._potion_slot == 1
    potion_event.choose(potion_state, "potion")
    assert all(potion.potion_id != "FlexPotion" for potion in potion_state.player.held_potions())

    relic_state = RunState(seed=3102, character_id="Ironclad")
    relic_state.initialize_run()
    relic_state.current_act_index = 1
    relic_state.player.gold = 200
    relic_state.player.add_potion(create_potion("FirePotion"))
    relic_state.player.obtain_relic("ANCHOR")
    relic_state.player.obtain_relic("VAJRA")
    relic_event = RanwidTheElder()
    relic_state.rng.up_front.choice = lambda seq: seq[-1]

    relic_event.generate_initial_options(relic_state)
    assert relic_event._relic_id == "VAJRA"
    relic_event.choose(relic_state, "relic")
    assert "VAJRA" not in relic_state.player.relics


def test_event_added_card_triggers_run_level_relic_hook():
    run_state = RunState(seed=33, character_id="Ironclad")
    run_state.initialize_run()
    run_state.player.deck = create_ironclad_starter_deck()
    run_state.player.obtain_relic("LUCKY_FYSH")
    starting_gold = run_state.player.gold

    choir = LuminousChoir()
    choir.calculate_vars(run_state)
    result = choir.choose(run_state, "reach")
    assert not result.finished
    choir.resolve_pending_choice(0)
    choir.resolve_pending_choice(1)
    result = choir.resolve_pending_choice(None)

    assert result.finished
    assert run_state.player.gold == starting_gold + 15


def test_luminous_choir_blocks_event_entry_and_tribute_when_gold_is_too_low():
    blocked = RunState(seed=2901, character_id="Ironclad")
    blocked.initialize_run()
    blocked.player.deck = create_ironclad_starter_deck()
    blocked.player.gold = 148
    choir = LuminousChoir()

    assert choir.is_allowed(blocked) is False

    blocked.player.gold = 149
    blocked.rng.up_front.next_int = lambda low, high: 0
    options = choir.generate_initial_options(blocked)
    assert [option.option_id for option in options] == ["reach", "tribute"]
    assert [option.enabled for option in options] == [True, True]

    exhausted = RunState(seed=2902, character_id="Ironclad")
    exhausted.initialize_run()
    exhausted.player.deck = create_ironclad_starter_deck()
    exhausted.player.gold = 200
    exhausted.player.relic_grab_bag_by_rarity = {
        rarity: []
        for rarity in exhausted.player.relic_grab_bag_by_rarity
    }
    exhausted.player.relic_grab_bag = []
    exhausted.player.relic_grab_bag_fallback = []
    exhausted_choir = LuminousChoir()
    assert exhausted_choir.is_allowed(exhausted) is False


def test_event_gold_gain_triggers_run_level_relic_hook():
    run_state = RunState(seed=34, character_id="Ironclad")
    run_state.initialize_run()
    run_state.player.obtain_relic("DRAGON_FRUIT")
    starting_max_hp = run_state.player.max_hp

    event = JungleMazeAdventure()
    event.calculate_vars(run_state)
    event.choose(run_state, "join")

    assert run_state.player.max_hp == starting_max_hp + 1


def test_whispering_hollow_hug_uses_run_level_transform_reward_in_run_manager():
    mgr = RunManager(seed=43, character_id="Ironclad")
    mgr.run_state.player.deck = create_ironclad_starter_deck()
    mgr._phase = RunManager.PHASE_EVENT
    event = WhisperingHollow()
    mgr._event_model = event
    mgr._event_options = event.generate_initial_options(mgr.run_state)
    mgr.run_state.player.gold = 200

    result = mgr._do_event_choice({"option_id": "hug"})
    assert result["phase"] == RunManager.PHASE_CARD_REWARD
    assert isinstance(mgr._current_reward, TransformCardsReward)

    actions = mgr.get_available_actions()
    assert any(action["action"] == "choose" for action in actions)

    final = mgr.take_action({"action": "choose", "index": 0})
    assert final["phase"] == RunManager.PHASE_MAP_CHOICE


def test_transform_events_only_offer_transformable_cards():
    run_state = RunState(seed=4301, character_id="Ironclad")
    run_state.initialize_run()
    run_state.player.deck = [create_card(CardId.SPOILS_MAP), create_card(CardId.SPOILS_MAP)]
    run_state.player.gold = 200
    run_state.current_act_index = 1

    grove = MorphicGrove()
    group = grove.choose(run_state, "group")
    assert group.finished is True
    assert group.description.startswith("Choose")
    assert grove.pending_choice is None

    hollow = WhisperingHollow()
    hug = hollow.choose(run_state, "hug")
    assert hug.finished is True
    assert hug.description.startswith("Choose")
    assert hollow.pending_choice is None


def test_luminous_choir_reach_uses_run_level_remove_reward_in_run_manager():
    mgr = RunManager(seed=44, character_id="Ironclad")
    mgr.run_state.player.deck = create_ironclad_starter_deck()
    mgr._phase = RunManager.PHASE_EVENT
    event = LuminousChoir()
    mgr._event_model = event
    mgr._event_options = event.generate_initial_options(mgr.run_state)
    starting_deck = len(mgr.run_state.player.deck)

    result = mgr._do_event_choice({"option_id": "reach"})
    assert result["phase"] == RunManager.PHASE_CARD_REWARD
    assert isinstance(mgr._current_reward, RemoveCardReward)
    assert any(action["action"] == "choose" for action in mgr.get_available_actions())

    mgr.take_action({"action": "choose", "index": 0})
    mgr.take_action({"action": "choose", "index": 1})
    final = mgr.take_action({"action": "confirm_choice"})
    assert final["phase"] == RunManager.PHASE_MAP_CHOICE
    assert len(mgr.run_state.player.deck) == starting_deck - 1
    assert any(card.card_id == make_spore_mind().card_id for card in mgr.run_state.player.deck)


def test_act2_enchant_events_use_run_level_enchant_rewards_in_run_manager():
    mgr = RunManager(seed=45, character_id="Ironclad")
    mgr.run_state.player.deck = create_ironclad_starter_deck()
    mgr._phase = RunManager.PHASE_EVENT

    field = FieldOfManSizedHoles()
    mgr._event_model = field
    mgr._event_options = field.generate_initial_options(mgr.run_state)
    result = mgr._do_event_choice({"option_id": "enter"})
    assert result["phase"] == RunManager.PHASE_CARD_REWARD
    assert isinstance(mgr._current_reward, EnchantCardsReward)
    mgr.take_action({"action": "choose", "index": 0})
    final = mgr.take_action({"action": "confirm_choice"})
    assert final["phase"] == RunManager.PHASE_MAP_CHOICE

    mgr._phase = RunManager.PHASE_EVENT
    symbiote = Symbiote()
    mgr._event_model = symbiote
    mgr._event_options = symbiote.generate_initial_options(mgr.run_state)
    result = mgr._do_event_choice({"option_id": "approach"})
    assert result["phase"] == RunManager.PHASE_CARD_REWARD
    assert isinstance(mgr._current_reward, EnchantCardsReward)


def test_doll_room_and_relic_trader_apply_real_relic_changes():
    run_state = RunState(seed=51, character_id="Ironclad")
    run_state.initialize_run()
    run_state.current_act_index = 1
    starting_relics = len(run_state.player.relics)

    doll = DollRoom()
    result = doll.choose(run_state, "random")
    assert result.finished
    assert len(run_state.player.relics) == starting_relics + 1

    for relic_id in ("ANCHOR", "VAJRA", "PEAR", "JUZU_BRACELET", "LANTERN"):
        run_state.player.obtain_relic(relic_id)
    trader = RelicTrader()
    options = trader.generate_initial_options(run_state)
    result = trader.choose(run_state, options[0].option_id)
    assert result.finished
    assert len(run_state.player.relics) >= starting_relics + 5

    blocked = RunState(seed=5101, character_id="Ironclad")
    blocked.initialize_run()
    blocked.current_act_index = 1
    blocked.player.obtain_relic("BURNING_BLOOD")
    blocked.player.obtain_relic("BLACK_BLOOD")
    blocked.player.obtain_relic("RING_OF_THE_SNAKE")
    blocked.player.obtain_relic("RING_OF_THE_DRAKE")
    blocked.player.obtain_relic("CRACKED_CORE")
    blocked_trader = RelicTrader()
    assert blocked_trader.is_allowed(blocked) is False


def test_endless_conveyor_observe_and_grab_apply_real_state_changes():
    run_state = RunState(seed=52, character_id="Ironclad")
    run_state.initialize_run()
    run_state.player.deck = create_ironclad_starter_deck()
    run_state.player.gold = 200

    conveyor = EndlessConveyor()
    conveyor.generate_initial_options(run_state)
    observe = conveyor.choose(run_state, "observe")
    assert observe.finished
    assert any(card.upgraded for card in run_state.player.deck)

    before_gold = run_state.player.gold
    grab = conveyor.choose(run_state, "grab")
    assert not grab.finished
    assert run_state.player.gold <= before_gold
