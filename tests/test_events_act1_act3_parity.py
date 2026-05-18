"""Focused parity coverage for selected Act 1 / Act 3 events."""

import sts2_env.events.act1  # noqa: F401
import sts2_env.events.act3  # noqa: F401

from sts2_env.cards.factory import create_card
from sts2_env.cards.ironclad import create_ironclad_starter_deck
from sts2_env.events.act1 import BrainLeech, RoomFullOfCheese, TeaMaster
from sts2_env.characters.all import get_character
from sts2_env.core.enums import CardId, CardRarity, CardType, MapPointType, PowerId, RoomType
from sts2_env.core.rng import Rng
from sts2_env.events.act3 import (
    DeprecatedAncientEvent,
    DeprecatedEvent,
    Neow,
    WarHistorianRepy,
)
from sts2_env.monsters.act1_weak import create_twig_slime_s
from sts2_env.relics.base import RelicId
from sts2_env.run.modifiers import (
    AllStarModifier,
    BigGameHunterModifier,
    CharacterCardsModifier,
    CursedRunModifier,
    DeadlyEventsModifier,
    DraftModifier,
    MidasModifier,
    MurderousModifier,
    NightTerrorsModifier,
    SealedDeckModifier,
    TerminalModifier,
    VintageModifier,
)
from sts2_env.run.rest_site import generate_rest_site_options
from sts2_env.run.reward_objects import CardReward, GoldReward, PotionReward, RelicReward, RewardsSet
from sts2_env.run.rewards import CardRewardGenerationOptions
from sts2_env.run.rooms import RoomVisitContext, create_room
from sts2_env.run.run_manager import RunManager
from sts2_env.run.run_state import RunState
from sts2_env.run.shop import _create_character_shop_card


def test_brain_leech_rip_loses_hp_while_share_knowledge_is_safe():
    run_state = RunState(seed=801, character_id="Ironclad")
    run_state.initialize_run()
    event = BrainLeech()
    start_hp = run_state.player.current_hp

    share = event.choose(run_state, "share_knowledge")
    assert share.finished
    assert run_state.player.current_hp == start_hp
    assert isinstance(share.rewards["reward_objects"][0], CardReward)
    assert len(share.rewards["reward_objects"][0].cards) in {0, 5}

    rip = event.choose(run_state, "rip")
    assert rip.finished
    assert run_state.player.current_hp == start_hp - 5
    assert isinstance(rip.rewards["reward_objects"][0], CardReward)


def test_room_full_of_cheese_search_loses_hp_but_gorge_does_not():
    run_state = RunState(seed=802, character_id="Ironclad")
    run_state.initialize_run()
    event = RoomFullOfCheese()
    start_hp = run_state.player.current_hp

    gorge = event.choose(run_state, "gorge")
    assert gorge.finished
    assert run_state.player.current_hp == start_hp
    reward = gorge.rewards["reward_objects"][0]
    assert isinstance(reward, CardReward)
    assert reward.cards_to_pick == 2

    search = event.choose(run_state, "search")
    assert search.finished
    assert run_state.player.current_hp == start_hp - 14
    assert "CHOSEN_CHEESE" in run_state.player.relics


def test_room_full_of_cheese_multi_pick_card_reward_stays_on_same_reward_until_two_picks():
    mgr = RunManager(seed=8021, character_id="Ironclad")
    mgr._phase = RunManager.PHASE_EVENT
    event = RoomFullOfCheese()
    mgr._event_model = event
    mgr._event_options = event.generate_initial_options(mgr.run_state)

    result = mgr._do_event_choice({"option_id": "gorge"})
    assert result["phase"] == RunManager.PHASE_CARD_REWARD
    assert isinstance(mgr._current_reward, CardReward)
    assert mgr._current_reward.cards_to_pick == 2
    assert not any(action["action"] == "skip" for action in mgr.get_available_actions())

    first = mgr.take_action({"action": "pick_card", "index": 0})
    assert first["phase"] == RunManager.PHASE_CARD_REWARD
    assert first["pending_more_picks"] is True

    second = mgr.take_action({"action": "pick_card", "index": 0})
    assert second["phase"] == RunManager.PHASE_MAP_CHOICE


def test_brain_leech_share_knowledge_card_reward_is_not_skippable():
    mgr = RunManager(seed=8011, character_id="Ironclad")
    mgr._phase = RunManager.PHASE_EVENT
    event = BrainLeech()
    mgr._event_model = event
    mgr._event_options = event.generate_initial_options(mgr.run_state)

    result = mgr._do_event_choice({"option_id": "share_knowledge"})
    assert result["phase"] == RunManager.PHASE_CARD_REWARD
    assert isinstance(mgr._current_reward, CardReward)
    assert not any(action["action"] == "skip" for action in mgr.get_available_actions())


def test_tea_master_options_and_gold_costs_match_thresholds():
    run_state = RunState(seed=803, character_id="Ironclad")
    run_state.initialize_run()
    event = TeaMaster()

    run_state.player.gold = 40
    options = event.generate_initial_options(run_state)
    assert [option.option_id for option in options] == ["bone_tea", "ember_tea", "discourtesy"]
    assert [option.enabled for option in options] == [False, False, True]

    run_state.player.gold = 60
    options = event.generate_initial_options(run_state)
    assert [option.option_id for option in options] == ["bone_tea", "ember_tea", "discourtesy"]
    assert [option.enabled for option in options] == [True, False, True]

    run_state.player.gold = 160
    options = event.generate_initial_options(run_state)
    assert [option.option_id for option in options] == ["bone_tea", "ember_tea", "discourtesy"]
    assert [option.enabled for option in options] == [True, True, True]

    before = run_state.player.gold
    relics_before = len(run_state.player.relics)
    bone = event.choose(run_state, "bone_tea")
    assert bone.finished
    assert run_state.player.gold == before - 50
    assert len(run_state.player.relics) == relics_before + 1

    before = run_state.player.gold
    relics_before = len(run_state.player.relics)
    ember = event.choose(run_state, "ember_tea")
    assert ember.finished
    assert run_state.player.gold == before - min(before, 150)
    assert len(run_state.player.relics) == relics_before + 1

    relics_before = len(run_state.player.relics)
    before = run_state.player.gold
    discourtesy = event.choose(run_state, "discourtesy")
    assert discourtesy.finished
    assert run_state.player.gold == before
    assert len(run_state.player.relics) == relics_before + 1


def test_neow_is_not_pool_allowed_but_exposes_three_choices():
    run_state = RunState(seed=804, character_id="Ironclad")
    run_state.initialize_run()
    event = Neow()

    assert event.is_allowed(run_state) is False
    options = event.generate_initial_options(run_state)
    assert [option.option_id for option in options] == ["positive_1", "positive_2", "cursed"]

    relics_before = len(run_state.player.relics)
    cursed = event.choose(run_state, "cursed")
    assert cursed.finished
    assert "cursed relic" in cursed.description.lower()
    assert len(run_state.player.relics) == relics_before + 1

    relics_before = len(run_state.player.relics)
    positive = event.choose(run_state, "positive_1")
    assert positive.finished
    assert "positive relic" in positive.description.lower()
    assert len(run_state.player.relics) == relics_before + 1


def test_neow_positive_pool_respects_cursed_choice_conflicts():
    run_state = RunState(seed=807, character_id="Ironclad")
    run_state.initialize_run()
    event = Neow()

    run_state.rng.up_front.choice = lambda seq: RelicId.LEAFY_POULTICE.name if RelicId.LEAFY_POULTICE.name in seq else seq[0]
    run_state.rng.up_front.shuffle = lambda seq: None
    options = event.generate_initial_options(run_state)

    labels = {option.label for option in options}
    assert any("LEAFY POULTICE" in label.upper() for label in labels)
    assert not any("NEW LEAF" in option.label.upper() for option in options if option.option_id != "cursed")


def test_neow_cursed_pool_adds_scroll_boxes_when_bundles_are_possible_and_skips_silver_crucible_in_multiplayer():
    run_state = RunState(seed=809, character_id="Ironclad")
    run_state.initialize_run()
    event = Neow()

    run_state.rng.up_front.choice = lambda seq: RelicId.SCROLL_BOXES.name if RelicId.SCROLL_BOXES.name in seq else seq[0]
    run_state.rng.up_front.shuffle = lambda seq: None
    options = event.generate_initial_options(run_state)
    assert any("SCROLL BOXES" in option.label.upper() for option in options)

    multiplayer = RunState(seed=810, character_id="Ironclad")
    multiplayer.initialize_run()
    multiplayer.players.append(multiplayer.player)
    multiplayer_event = Neow()
    multiplayer.rng.up_front.choice = lambda seq: RelicId.SILVER_CRUCIBLE.name if RelicId.SILVER_CRUCIBLE.name in seq else seq[0]
    multiplayer.rng.up_front.shuffle = lambda seq: None
    multiplayer_options = multiplayer_event.generate_initial_options(multiplayer)
    assert not any("SILVER CRUCIBLE" in option.label.upper() for option in multiplayer_options)


def test_neow_modifier_path_exposes_sequential_modifier_options():
    run_state = RunState(seed=811, character_id="Ironclad")
    run_state.player.deck = create_ironclad_starter_deck()
    run_state.modifiers = [AllStarModifier(), DraftModifier()]
    run_state.initialize_run()
    event = Neow()

    options = event.generate_initial_options(run_state)
    assert [option.option_id for option in options] == ["modifier_0"]

    first = event.choose(run_state, "modifier_0")
    assert first.finished is False
    assert [option.option_id for option in first.next_options] == ["modifier_1"]
    assert len(run_state.player.deck) == 5

    second = event.choose(run_state, "modifier_1")
    rewards = second.rewards["reward_objects"]
    assert len(rewards) == 10
    assert all(isinstance(reward, CardReward) and reward.skippable is False for reward in rewards)


def test_neow_sealed_deck_modifier_requests_ten_of_thirty_cards():
    run_state = RunState(seed=812, character_id="Ironclad")
    run_state.player.deck = create_ironclad_starter_deck()
    run_state.modifiers = [SealedDeckModifier()]
    run_state.initialize_run()
    event = Neow()

    options = event.generate_initial_options(run_state)
    assert [option.option_id for option in options] == ["modifier_0"]

    result = event.choose(run_state, "modifier_0")
    assert result.finished is False
    assert run_state.pending_choice is not None
    assert len(run_state.pending_choice.options) == 30
    assert run_state.pending_choice.min_choices == 10
    assert run_state.pending_choice.max_choices == 10


def test_neow_all_star_modifier_adds_five_colorless_cards():
    run_state = RunState(seed=815, character_id="Ironclad")
    run_state.player.deck = create_ironclad_starter_deck()
    modifier = AllStarModifier()
    modifier.on_run_created(run_state)

    result = modifier.generate_neow_event_result(run_state)
    assert result.finished
    assert len(run_state.player.deck) == 15
    assert all(card.card_id not in {CardId.BASH, CardId.STRIKE_IRONCLAD, CardId.DEFEND_IRONCLAD} for card in run_state.player.deck[-5:])


def test_murderous_modifier_applies_strength_to_combat_creatures_and_added_enemies():
    mgr = RunManager(seed=2401, character_id="Ironclad")
    mgr.run_state.modifiers = [MurderousModifier()]

    mgr._enter_combat(RoomType.MONSTER)

    combat = mgr.get_combat_state()
    assert combat is not None
    assert combat.player.get_power_amount(PowerId.STRENGTH) == 3
    assert all(enemy.get_power_amount(PowerId.STRENGTH) == 3 for enemy in combat.enemies)

    added_enemy, ai = create_twig_slime_s(Rng(2402))
    combat.add_enemy(added_enemy, ai)

    assert added_enemy.get_power_amount(PowerId.STRENGTH) == 3


def test_terminal_modifier_adds_player_plating_in_combat_and_drains_base_room_hp():
    mgr = RunManager(seed=2403, character_id="Ironclad")
    mgr.run_state.modifiers = [TerminalModifier()]

    mgr._enter_combat(RoomType.MONSTER)

    combat = mgr.get_combat_state()
    assert combat is not None
    assert combat.player.get_power_amount(PowerId.PLATING) == 5

    run_state = RunState(seed=2404, character_id="Ironclad")
    modifier = TerminalModifier()
    base_room = RoomVisitContext(RoomType.EVENT)
    run_state.base_room = base_room
    modifier.after_room_entered(run_state, base_room)

    assert run_state.player.max_hp == 79
    assert run_state.player.current_hp == 79


def test_midas_modifier_doubles_gold_rewards_and_removes_smith():
    run_state = RunState(seed=2405, character_id="Ironclad")
    run_state.modifiers = [MidasModifier()]
    rewards = RewardsSet(run_state.player.player_id).with_rewards_from_room(create_room(RoomType.MONSTER), run_state)

    generated = rewards.generate_without_offering(run_state)

    gold = next(reward for reward in generated if isinstance(reward, GoldReward))
    assert 20 <= gold.amount <= 40
    assert gold.min_gold == gold.max_gold == gold.amount
    assert not any(option.option_id == "SMITH" for option in generate_rest_site_options(run_state.player))


def test_night_terrors_modifier_full_rests_then_loses_max_hp():
    run_state = RunState(seed=2406, character_id="Ironclad")
    run_state.modifiers = [NightTerrorsModifier()]
    run_state.player.current_hp = 10

    heal = next(option for option in generate_rest_site_options(run_state.player) if option.option_id == "HEAL")
    result = heal.execute(run_state.player)

    assert result == "Healed 70 HP"
    assert run_state.player.max_hp == 75
    assert run_state.player.current_hp == 75


def test_vintage_modifier_replaces_regular_combat_card_reward_with_relic_reward():
    run_state = RunState(seed=2407, character_id="Ironclad")
    run_state.modifiers = [VintageModifier()]

    monster_rewards = RewardsSet(run_state.player.player_id).with_rewards_from_room(
        create_room(RoomType.MONSTER),
        run_state,
    ).generate_without_offering(run_state)
    elite_rewards = RewardsSet(run_state.player.player_id).with_rewards_from_room(
        create_room(RoomType.ELITE),
        run_state,
    ).generate_without_offering(run_state)

    assert not any(isinstance(reward, CardReward) for reward in monster_rewards)
    assert any(isinstance(reward, RelicReward) for reward in monster_rewards)
    assert any(isinstance(reward, CardReward) for reward in elite_rewards)


def test_big_game_hunter_modifier_increases_map_elites():
    base = RunState(seed=2408, character_id="Ironclad")
    base.initialize_run()
    hunter = RunState(seed=2408, character_id="Ironclad")
    hunter.modifiers = [BigGameHunterModifier()]
    hunter.initialize_run()

    base_elites = sum(1 for point in base.map.room_points() if point.point_type == MapPointType.ELITE)
    hunter_elites = sum(1 for point in hunter.map.room_points() if point.point_type == MapPointType.ELITE)

    assert hunter_elites > base_elites


def test_big_game_hunter_modifier_makes_elite_card_rewards_rare():
    run_state = RunState(seed=2409, character_id="Ironclad")
    run_state.modifiers = [BigGameHunterModifier()]
    reward = CardReward(run_state.player.player_id, context="elite")

    reward.populate(run_state, create_room(RoomType.ELITE))

    assert reward.cards
    assert all(card.rarity == CardRarity.RARE for card in reward.cards)


def test_big_game_hunter_modifier_falls_back_to_character_rare_pool_when_candidates_have_no_rares():
    run_state = RunState(seed=2412, character_id="Ironclad")
    run_state.modifiers = [BigGameHunterModifier()]
    reward = CardReward(
        run_state.player.player_id,
        context="elite",
        custom_card_ids=(CardId.ANGER,),
        has_custom_card_pool=True,
    )

    reward.populate(run_state, create_room(RoomType.ELITE))

    assert reward.cards
    assert all(card.rarity == CardRarity.RARE for card in reward.cards)
    assert all(card.card_id != CardId.ANGER for card in reward.cards)


def test_big_game_hunter_modifier_keeps_colorless_rare_candidates():
    run_state = RunState(seed=2413, character_id="Ironclad")
    run_state.modifiers = [BigGameHunterModifier()]
    assert run_state.player.obtain_relic("DINGY_RUG")
    reward = CardReward(run_state.player.player_id, context="elite")

    reward.populate(run_state, create_room(RoomType.ELITE))

    ironclad_pool = set(get_character("Ironclad").card_pool)
    assert any(card_id not in ironclad_pool for card_id in reward.custom_card_ids)
    assert all(card.rarity == CardRarity.RARE for card in reward.cards)


def test_big_game_hunter_modifier_respects_locked_reward_rarities():
    run_state = RunState(seed=2410, character_id="Ironclad")
    run_state.modifiers = [BigGameHunterModifier()]
    reward = CardReward(
        run_state.player.player_id,
        context="elite",
        forced_rarities=(CardRarity.COMMON, CardRarity.COMMON, CardRarity.COMMON),
    )

    reward.populate(run_state, create_room(RoomType.ELITE))

    assert reward.cards
    assert all(card.rarity == CardRarity.COMMON for card in reward.cards)


def test_character_cards_modifier_expands_card_reward_pool():
    run_state = RunState(seed=2411, character_id="Ironclad")
    modifier = CharacterCardsModifier("Silent")
    options = CardRewardGenerationOptions()

    modified = modifier.modify_card_reward_creation_options(run_state.player, options, None, None, run_state)

    assert modified.character_ids == ("Ironclad", "Silent")
    assert modified.use_default_character_pool is False

    locked = CardRewardGenerationOptions(allow_card_pool_modifications=False)
    assert modifier.modify_card_reward_creation_options(run_state.player, locked, None, None, run_state) is locked


def test_character_cards_modifier_expands_merchant_card_pool():
    class LastChoiceRng:
        def choice(self, values):
            return list(values)[-1]

        def next_float_range(self, low, high):
            return 1.0

    run_state = RunState(seed=2412, character_id="Ironclad")
    run_state.modifiers = [CharacterCardsModifier("Silent")]

    entry = _create_character_shop_card(
        run_state,
        LastChoiceRng(),
        "Skill",
        CardRarity.RARE,
    )

    assert entry.card.card_id in get_character("Silent").card_pool
    assert entry.card.card_type == CardType.SKILL
    assert entry.rarity == CardRarity.RARE


def test_cursed_run_modifier_adds_random_curse_after_each_act_entered():
    run_state = RunState(seed=2413, character_id="Ironclad")
    run_state.modifiers = [CursedRunModifier()]

    run_state.initialize_run()

    first_act_curses = [card for card in run_state.player.deck if card.card_type == CardType.CURSE]
    assert len(first_act_curses) == 1
    assert first_act_curses[0].can_be_generated_by_modifiers

    run_state.enter_act(1)

    assert len([card for card in run_state.player.deck if card.card_type == CardType.CURSE]) == 2


def test_deadly_events_modifier_updates_unknown_odds_and_removes_juzu():
    run_state = RunState(seed=2414, character_id="Ironclad")
    run_state.modifiers = [DeadlyEventsModifier()]

    run_state.initialize_run()

    assert "JUZU_BRACELET" not in run_state.player.relic_grab_bag
    assert run_state.unknown_odds._base[RoomType.ELITE] == 0.1
    assert run_state.unknown_odds._current[RoomType.ELITE] == 0.1

    run_state.unknown_odds._current = {
        RoomType.MONSTER: 0.0,
        RoomType.ELITE: 0.0,
        RoomType.TREASURE: 0.0,
        RoomType.SHOP: 0.0,
    }
    run_state.unknown_odds.roll(run_state.rng.unknown_map_point, run_state)

    assert run_state.unknown_odds._current[RoomType.TREASURE] == 0.04


def test_neow_draft_modifier_clears_deck_and_queues_ten_non_skippable_rewards():
    run_state = RunState(seed=816, character_id="Ironclad")
    run_state.player.deck = create_ironclad_starter_deck()
    modifier = DraftModifier()
    modifier.on_run_created(run_state)

    assert run_state.player.deck == []
    result = modifier.generate_neow_event_result(run_state)
    rewards = result.rewards["reward_objects"]
    assert len(rewards) == 10
    assert all(isinstance(reward, CardReward) and reward.skippable is False for reward in rewards)


def test_neow_specialized_modifier_adds_five_copies_of_same_card():
    from sts2_env.run.modifiers import SpecializedModifier

    run_state = RunState(seed=817, character_id="Ironclad")
    run_state.player.deck = create_ironclad_starter_deck()
    modifier = SpecializedModifier()

    result = modifier.generate_neow_event_result(run_state)
    assert result.finished
    assert len(run_state.player.deck) == 15
    added_ids = {card.card_id for card in run_state.player.deck[-5:]}
    assert len(added_ids) == 1


def test_neow_modifier_pending_choice_resumes_to_next_modifier_in_run_manager():
    mgr = RunManager(seed=813, character_id="Ironclad")
    mgr.run_state.player.deck = create_ironclad_starter_deck()
    mgr.run_state.modifiers = [SealedDeckModifier(), AllStarModifier()]
    for modifier in mgr.run_state.modifiers:
        modifier.on_run_created(mgr.run_state)
    mgr._phase = RunManager.PHASE_EVENT
    mgr._event_model = Neow()
    mgr._event_options = mgr._event_model.generate_initial_options(mgr.run_state)

    first = mgr._do_event_choice({"option_id": "modifier_0"})
    assert first["phase"] == RunManager.PHASE_EVENT
    assert mgr.run_state.pending_choice is not None

    for index in range(10):
        mgr.take_action({"action": "choose", "index": index})
    resolved = mgr.take_action({"action": "confirm_choice"})
    assert resolved["phase"] == RunManager.PHASE_EVENT
    assert [option.option_id for option in mgr._event_options] == ["modifier_1"]

    second = mgr._do_event_choice({"option_id": "modifier_1"})
    assert second["phase"] == RunManager.PHASE_MAP_CHOICE
    assert len(mgr.run_state.player.deck) == 15


def test_neow_modifier_reward_chain_resumes_to_next_modifier_in_run_manager():
    mgr = RunManager(seed=814, character_id="Ironclad")
    mgr.run_state.player.deck = create_ironclad_starter_deck()
    mgr.run_state.modifiers = [DraftModifier(), AllStarModifier()]
    for modifier in mgr.run_state.modifiers:
        modifier.on_run_created(mgr.run_state)
    mgr._phase = RunManager.PHASE_EVENT
    mgr._event_model = Neow()
    mgr._event_options = mgr._event_model.generate_initial_options(mgr.run_state)

    first = mgr._do_event_choice({"option_id": "modifier_0"})
    assert first["phase"] == RunManager.PHASE_CARD_REWARD
    assert isinstance(mgr._current_reward, CardReward)
    assert mgr._current_reward.skippable is False

    for _ in range(10):
        result = mgr.take_action({"action": "pick_card", "index": 0})

    assert result["phase"] == RunManager.PHASE_EVENT
    assert [option.option_id for option in mgr._event_options] == ["modifier_1"]


def test_war_historian_repy_is_disabled_but_choice_results_are_stable():
    run_state = RunState(seed=805, character_id="Ironclad")
    run_state.initialize_run()
    run_state.player.deck.append(create_card(CardId.LANTERN_KEY))
    event = WarHistorianRepy()

    assert event.is_allowed(run_state) is False
    options = event.generate_initial_options(run_state)
    assert [option.option_id for option in options] == ["unlock_cage", "unlock_chest"]

    unlock_cage = event.choose(run_state, "unlock_cage")
    assert unlock_cage.finished
    assert "history course" in unlock_cage.description.lower()
    assert run_state.extra_fields.get("freed_repy") is True
    assert CardId.LANTERN_KEY not in [card.card_id for card in run_state.player.deck]
    assert "HISTORY_COURSE" in run_state.player.relics

    run_state.player.deck.append(create_card(CardId.LANTERN_KEY))
    unlock_chest = event.choose(run_state, "unlock_chest")
    assert unlock_chest.finished
    assert "2 potions" in unlock_chest.description.lower()
    rewards = unlock_chest.rewards["reward_objects"]
    assert len([reward for reward in rewards if isinstance(reward, PotionReward)]) == 2
    assert len([reward for reward in rewards if isinstance(reward, RelicReward)]) == 2


def test_lantern_key_forces_act3_unknown_rooms_into_war_historian_repy():
    mgr = RunManager(seed=809, character_id="Ironclad")
    mgr.run_state.initialize_run()
    mgr.run_state.current_act_index = 2
    mgr.run_state.player.deck.append(create_card(CardId.LANTERN_KEY))

    assert mgr.run_state.resolve_room_type(MapPointType.UNKNOWN) is RoomType.EVENT

    mgr._enter_event()

    assert isinstance(mgr._event_model, WarHistorianRepy)


def test_war_historian_repy_removes_lantern_key_on_both_paths():
    run_state = RunState(seed=808, character_id="Ironclad")
    run_state.initialize_run()
    run_state.player.deck.extend([create_card(CardId.LANTERN_KEY), create_card(CardId.LANTERN_KEY)])
    event = WarHistorianRepy()

    event.choose(run_state, "unlock_cage")
    assert CardId.LANTERN_KEY not in [card.card_id for card in run_state.player.deck]


def test_deprecated_act3_events_are_unreachable_and_optionless():
    run_state = RunState(seed=806, character_id="Ironclad")
    run_state.initialize_run()

    for event in (DeprecatedEvent(), DeprecatedAncientEvent()):
        assert event.is_allowed(run_state) is False
        assert event.generate_initial_options(run_state) == []
        result = event.choose(run_state, "anything")
        assert result.finished
        assert result.next_options == []
