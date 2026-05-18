"""Additional focused parity tests for event/ancient relics."""

import sts2_env.powers  # noqa: F401

from sts2_env.cards.ironclad import create_ironclad_starter_deck, make_inflame
from sts2_env.cards.ironclad_basic import make_strike_ironclad
from sts2_env.cards.silent import make_backstab
from sts2_env.cards.status import make_luminesce
from sts2_env.core.combat import CombatState
from sts2_env.core.enums import CardId, CombatSide, PowerId
from sts2_env.core.rng import Rng
from sts2_env.monsters.act1_weak import create_shrinker_beetle
from sts2_env.run.reward_objects import AddCardsReward, RelicReward, UpgradeCardsReward
from sts2_env.run.run_state import RunState


def _make_combat(relics: list[str] | None = None, *, seed: int = 881) -> CombatState:
    combat = CombatState(
        player_hp=80,
        player_max_hp=80,
        deck=create_ironclad_starter_deck(),
        rng_seed=seed,
        character_id="Ironclad",
        relics=relics or [],
        gold=50,
    )
    creature, ai = create_shrinker_beetle(Rng(seed))
    combat.add_enemy(creature, ai)
    combat.start_combat()
    return combat


class TestRelicParityEventExtra10:
    def test_fiddle_adds_two_to_opening_hand_draw(self):
        combat = _make_combat(["Fiddle"])
        assert len(combat.hand) == 7

    def test_fiddle_blocks_non_hand_draws_only_on_owner_turn(self):
        combat = _make_combat(["Fiddle"], seed=893)
        combat.hand = []
        combat.draw_pile = [make_strike_ironclad(), make_strike_ironclad()]

        combat.current_side = CombatSide.PLAYER
        combat.draw_cards(combat.player, 1)
        assert len(combat.hand) == 0
        assert len(combat.draw_pile) == 2

        combat.current_side = CombatSide.ENEMY
        combat.draw_cards(combat.player, 1)
        assert len(combat.hand) == 1
        assert len(combat.draw_pile) == 1

    def test_jeweled_mask_moves_power_to_hand_and_makes_it_free(self):
        combat = CombatState(
            player_hp=80,
            player_max_hp=80,
            deck=create_ironclad_starter_deck(),
            rng_seed=890,
            character_id="Ironclad",
            relics=["JeweledMask"],
        )
        power = make_inflame()
        combat.draw_pile = [make_strike_ironclad() for _ in range(6)] + [power]
        combat.hand = []
        combat.discard_pile = []
        combat.exhaust_pile = []

        combat._start_player_turn()  # noqa: SLF001

        assert power in combat.hand
        assert power not in combat.draw_pile
        assert combat.modified_card_cost(combat.player, power) == 0

    def test_pollinous_core_resets_turn_count_after_bonus_draw(self):
        combat = CombatState(
            player_hp=80,
            player_max_hp=80,
            deck=create_ironclad_starter_deck(),
            rng_seed=891,
            character_id="Ironclad",
            relics=["PollinousCore"],
        )
        relic = next(relic for relic in combat.relics if relic.relic_id.name == "POLLINOUS_CORE")
        relic._turns_seen = 3  # noqa: SLF001
        combat.draw_pile = [make_strike_ironclad() for _ in range(8)]
        combat.hand = []
        combat.discard_pile = []
        combat.exhaust_pile = []

        combat._start_player_turn()  # noqa: SLF001

        assert len(combat.hand) == 7
        assert relic._turns_seen == 0  # noqa: SLF001

    def test_toasty_mittens_round_one_exhausts_non_innate_card(self):
        combat = CombatState(
            player_hp=80,
            player_max_hp=80,
            deck=create_ironclad_starter_deck(),
            rng_seed=892,
            character_id="Ironclad",
            relics=["ToastyMittens"],
        )
        innate = make_backstab()
        non_innate = make_strike_ironclad()
        combat.draw_pile = [innate, non_innate]
        combat.hand = []
        combat.discard_pile = []
        combat.exhaust_pile = []

        combat._start_player_turn()  # noqa: SLF001

        assert innate in combat.hand
        assert non_innate in combat.exhaust_pile
        assert combat.player.get_power_amount(PowerId.STRENGTH) == 1

    def test_pomander_queues_single_upgrade_reward_when_followups_are_deferred(self):
        run_state = RunState(seed=882, character_id="Ironclad")
        run_state.defer_followup_rewards = True

        assert run_state.player.obtain_relic("POMANDER")
        assert len(run_state.pending_rewards) == 1
        reward = run_state.pending_rewards[0]
        assert isinstance(reward, UpgradeCardsReward)
        assert reward.count == 1

    def test_preserved_fog_queues_remove_five_and_folly_reward(self):
        run_state = RunState(seed=883, character_id="Ironclad")
        run_state.defer_followup_rewards = True

        assert run_state.player.obtain_relic("PRESERVED_FOG")
        assert len(run_state.pending_rewards) == 2
        assert isinstance(run_state.pending_rewards[0], UpgradeCardsReward) is False
        assert isinstance(run_state.pending_rewards[1], AddCardsReward)
        assert [card.card_id.name for card in run_state.pending_rewards[1].cards] == ["FOLLY"]

    def test_pumpkin_candle_only_grants_energy_in_act_obtained(self):
        run_state = RunState(seed=884, character_id="Ironclad")
        run_state.current_act_index = 1
        run_state.player.deck = create_ironclad_starter_deck()
        assert run_state.player.obtain_relic("PUMPKIN_CANDLE")

        combat = CombatState(
            player_hp=80,
            player_max_hp=80,
            deck=list(run_state.player.deck),
            rng_seed=884,
            character_id="Ironclad",
            player_state=run_state.player,
        )
        assert combat.max_energy == 4

        run_state.current_act_index = 2
        next_act_combat = CombatState(
            player_hp=80,
            player_max_hp=80,
            deck=list(run_state.player.deck),
            rng_seed=885,
            character_id="Ironclad",
            player_state=run_state.player,
        )
        assert next_act_combat.max_energy == 3

    def test_radiant_pearl_adds_luminesce_to_hand_on_round_one(self):
        combat = _make_combat(["RadiantPearl"], seed=885)
        assert any(card.card_id == CardId.LUMINESCE for card in combat.hand)

    def test_royal_poison_deals_four_unblockable_damage_on_round_one(self):
        combat = _make_combat(["RoyalPoison"], seed=886)
        assert combat.player.current_hp == 76

    def test_sai_grants_seven_block_each_player_turn(self):
        combat = _make_combat(["Sai"], seed=887)
        assert combat.player.block == 7
        combat.end_player_turn()
        assert combat.player.block == 7

    def test_signet_ring_grants_nine_hundred_ninety_nine_gold_on_obtain(self):
        run_state = RunState(seed=888, character_id="Ironclad")
        starting_gold = run_state.player.gold

        assert run_state.player.obtain_relic("SIGNET_RING")
        assert run_state.player.gold == starting_gold + 999

    def test_small_capsule_queues_one_relic_reward(self):
        run_state = RunState(seed=889, character_id="Ironclad")

        assert run_state.player.obtain_relic("SMALL_CAPSULE")
        rewards = [reward for reward in run_state.pending_rewards if isinstance(reward, RelicReward)]
        assert len(rewards) == 1
