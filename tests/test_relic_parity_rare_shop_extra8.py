"""Additional focused parity tests for rare/shop/event relics."""

import sts2_env.powers  # noqa: F401

from sts2_env.cards.ironclad import create_ironclad_starter_deck, make_inflame
from sts2_env.cards.ironclad_basic import make_strike_ironclad
from sts2_env.cards.necrobinder import create_necrobinder_starter_deck
from sts2_env.cards.status import make_sweeping_gaze
from sts2_env.core.combat import CombatState
from sts2_env.core.enums import CardId, PowerId
from sts2_env.powers.base import PowerInstance
from sts2_env.core.rng import Rng
from sts2_env.monsters.act1_weak import create_shrinker_beetle


class _CannotHitPower(PowerInstance):
    def __init__(self):
        super().__init__(PowerId.COVERED, 1)

    def should_allow_hitting(self, owner, combat):
        return False


def _make_ironclad_combat(relics: list[str] | None = None, *, seed: int = 600) -> CombatState:
    combat = CombatState(
        player_hp=80,
        player_max_hp=80,
        deck=create_ironclad_starter_deck(),
        rng_seed=seed,
        character_id="Ironclad",
        relics=relics or [],
    )
    creature, ai = create_shrinker_beetle(Rng(seed))
    combat.add_enemy(creature, ai)
    combat.start_combat()
    return combat


def _make_necrobinder_combat(relics: list[str] | None = None, *, seed: int = 601) -> CombatState:
    combat = CombatState(
        player_hp=70,
        player_max_hp=70,
        deck=create_necrobinder_starter_deck(),
        rng_seed=seed,
        character_id="Necrobinder",
        relics=relics or [],
    )
    creature, ai = create_shrinker_beetle(Rng(seed))
    combat.add_enemy(creature, ai)
    combat.start_combat()
    return combat


class TestRelicParityRareShopExtra8:
    def test_big_hat_generates_two_ethereal_cards_on_first_turn(self):
        combat = _make_necrobinder_combat(["BigHat"])
        generated = [card for card in combat.hand if card.is_ethereal]

        assert len(generated) == 2

    def test_bread_removes_two_energy_on_round_one_and_restores_bonus_afterward(self):
        combat = _make_ironclad_combat(["Bread"])

        assert combat.max_energy == 3
        assert combat.energy == 1

        combat.end_player_turn()

        assert combat.round_number == 2
        assert combat.max_energy == 4
        assert combat.energy == 4

    def test_chandelier_grants_three_energy_on_round_three(self):
        combat = _make_ironclad_combat(["Chandelier"])

        combat.end_player_turn()
        assert combat.round_number == 2
        assert combat.energy == 3

        combat.end_player_turn()
        assert combat.round_number == 3
        assert combat.energy == 6

    def test_history_course_replays_last_attack_or_skill_on_next_turn_only_once(self):
        combat = _make_ironclad_combat(["HistoryCourse"])
        enemy = combat.enemies[0]
        starting_hp = enemy.current_hp
        combat.hand = [make_strike_ironclad()]
        combat.energy = 1

        assert combat.play_card(0, 0)
        assert enemy.current_hp == starting_hp - 6

        combat.end_player_turn()

        assert enemy.current_hp == starting_hp - 10
        combat.end_player_turn()
        assert enemy.current_hp == starting_hp - 10

    def test_ninja_scroll_adds_three_shivs_on_round_one(self):
        combat = _make_ironclad_combat(["NinjaScroll"])
        shivs = [card for card in combat.hand if card.card_id == CardId.SHIV]

        assert len(shivs) == 3

    def test_snecko_eye_applies_confused_and_draws_two_extra(self):
        combat = _make_ironclad_combat(["SneckoEye"])

        assert combat.player.get_power_amount(PowerId.CONFUSED) == 1
        assert len(combat.hand) == 7

    def test_spiked_gauntlets_adds_max_energy_and_makes_power_cost_one_more_to_play(self):
        combat = _make_ironclad_combat(["SpikedGauntlets"])
        inflame = make_inflame()
        inflame.owner = combat.player
        combat.hand = [inflame]

        assert combat.max_energy == 4
        assert combat.energy == 4

        combat.energy = 1
        assert combat.can_play_card(inflame) is False

        combat.energy = 2
        assert combat.can_play_card(inflame) is True

    def test_stone_calendar_deals_fifty_two_to_all_enemies_on_turn_seven(self):
        combat = _make_ironclad_combat(["StoneCalendar"])
        enemy = combat.enemies[0]
        enemy.max_hp = 100
        enemy.current_hp = 100

        for _ in range(6):
            combat.end_player_turn()

        assert combat.round_number == 7
        assert enemy.current_hp == 100

        combat.end_player_turn()

        assert combat.round_number == 8
        assert enemy.current_hp == 48

    def test_stone_calendar_skips_unhittable_enemies(self):
        combat = _make_ironclad_combat(["StoneCalendar"], seed=612)
        enemy = combat.enemies[0]
        enemy.max_hp = 100
        enemy.current_hp = 100
        enemy.powers[PowerId.COVERED] = _CannotHitPower()

        for _ in range(7):
            combat.end_player_turn()

        assert combat.round_number == 8
        assert enemy.current_hp == 100
