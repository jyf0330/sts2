"""Run modifiers with minimal gameplay semantics.

This module implements the subset of modifier behavior needed by the
run-start / Neow flow and the relic-grab-bag legality checks.
"""

from __future__ import annotations

from dataclasses import dataclass

from sts2_env.cards.factory import card_metadata, eligible_character_cards, eligible_registered_cards
from sts2_env.core.enums import CardRarity, CombatSide, MapPointType, PowerId, RoomType
from sts2_env.core.selection import CardChoiceOption, PendingCardChoice
from sts2_env.run.events import EventResult
from sts2_env.run.reward_objects import CardReward, GoldReward, RelicReward
from sts2_env.run.rewards import (
    CardRewardGenerationOptions,
    generate_combat_reward_cards,
    generate_uniform_noncombat_cards,
)


@dataclass
class ModifierModel:
    modifier_id: str
    clears_player_deck: bool = False

    @property
    def neow_option_title(self) -> str:
        return self.modifier_id.replace("_", " ").title()

    @property
    def neow_option_description(self) -> str:
        return self.neow_option_title

    def on_run_created(self, run_state) -> None:
        if self.clears_player_deck:
            for player in run_state.players:
                player.deck.clear()

    def after_relic_grab_bags_populated(self, run_state) -> None:
        pass

    def after_act_entered(self, run_state) -> None:
        pass

    def after_room_entered(self, run_state, room, combat=None) -> None:
        pass

    def after_creature_added_to_combat(self, creature, combat) -> None:
        pass

    def after_card_added_to_deck(self, player, card, source=None) -> None:
        pass

    def should_allow_merchant_card_removal(self, player) -> bool:
        return True

    def modify_rewards_late(self, player, rewards, room, run_state):
        return rewards

    def modify_card_reward_creation_options(self, player, options, reward, room, run_state):
        return options

    def modify_merchant_card_character_ids(self, player, character_ids, run_state):
        return character_ids

    def modify_generated_map(self, player, run_state, act_map, act_index):
        return act_map

    def modify_rest_site_options(self, player, options, run_state):
        return options

    def modify_rest_site_heal_amount(self, player, amount: int, run_state) -> int:
        return amount

    def after_rest_site_heal(self, player, healed: int, run_state) -> None:
        pass

    def modify_odds_increase_for_unrolled_room_type(self, room_type, odds_increase: float) -> float:
        return odds_increase

    def generate_neow_event_result(self, run_state) -> EventResult | None:
        return None

    def _remove_pandoras_box(self, run_state) -> None:
        for player in run_state.players:
            player.remove_relic_from_grab_bag("PANDORAS_BOX")


class DraftModifier(ModifierModel):
    def __init__(self) -> None:
        super().__init__("draft", clears_player_deck=True)

    def generate_neow_event_result(self, run_state) -> EventResult:
        rewards = [
            CardReward(
                run_state.player.player_id,
                option_count=3,
                skippable=False,
                generation_context=None,
                roll_upgrade=False,
            )
            for _ in range(10)
        ]
        self._remove_pandoras_box(run_state)
        return EventResult(
            finished=True,
            description="Drafted ten sets of cards.",
            rewards={"reward_objects": rewards},
        )


class InsanityModifier(ModifierModel):
    def __init__(self) -> None:
        super().__init__("insanity", clears_player_deck=True)

    def generate_neow_event_result(self, run_state) -> EventResult:
        cards = generate_uniform_noncombat_cards(
            run_state,
            num_cards=30,
            distinct=False,
        )
        for card in cards:
            run_state.player.add_card_instance_to_deck(card)
        self._remove_pandoras_box(run_state)
        return EventResult(finished=True, description="Added 30 random cards.")


class AllStarModifier(ModifierModel):
    def __init__(self) -> None:
        super().__init__("all_star")

    def generate_neow_event_result(self, run_state) -> EventResult:
        cards = generate_uniform_noncombat_cards(
            run_state,
            num_cards=5,
            character_ids=(),
            include_colorless=True,
            distinct=False,
        )
        for card in cards:
            run_state.player.add_card_instance_to_deck(card)
        return EventResult(finished=True, description="Added 5 random colorless cards.")


class MurderousModifier(ModifierModel):
    def __init__(self) -> None:
        super().__init__("murderous")

    def after_room_entered(self, run_state, room, combat=None) -> None:
        if combat is None:
            return
        for creature in combat.all_creatures:
            combat.apply_power_to(creature, PowerId.STRENGTH, 3)

    def after_creature_added_to_combat(self, creature, combat) -> None:
        if creature.side != CombatSide.PLAYER:
            combat.apply_power_to(creature, PowerId.STRENGTH, 3)


class TerminalModifier(ModifierModel):
    def __init__(self) -> None:
        super().__init__("terminal")

    def after_room_entered(self, run_state, room, combat=None) -> None:
        if getattr(run_state, "base_room", None) is room:
            for player in run_state.players:
                player.lose_max_hp(1)
        if combat is None:
            return
        for state in combat.combat_player_states:
            combat.apply_power_to(state.creature, PowerId.PLATING, 5)


class HoarderModifier(ModifierModel):
    def __init__(self) -> None:
        super().__init__("hoarder")

    def after_card_added_to_deck(self, player, card, source=None) -> None:
        if source is not None:
            return
        for _ in range(2):
            player.add_card_instance_to_deck(card.clone(40_000_000 + len(player.deck)), source=self)

    def should_allow_merchant_card_removal(self, player) -> bool:
        return False


class BigGameHunterModifier(ModifierModel):
    def __init__(self) -> None:
        super().__init__("big_game_hunter")

    def modify_generated_map(self, player, run_state, act_map, act_index):
        from sts2_env.core.rng import Rng
        from sts2_env.map.generator import generate_act_map

        current_elites = sum(1 for point in act_map.room_points() if point.point_type == MapPointType.ELITE)
        treasure_row = act_map.map_length - 7
        treasure_points = act_map.get_row(treasure_row) if treasure_row > 0 else []
        replace_treasure = bool(treasure_points) and all(point.point_type == MapPointType.ELITE for point in treasure_points)
        return generate_act_map(
            num_rooms=run_state.current_act.num_rooms,
            rng=Rng(run_state.rng.seed, f"act_{act_index + 1}_map"),
            ascension_level=run_state.ascension_level,
            replace_treasure_with_elite=replace_treasure,
            act_index=act_index,
            num_elites_override=round(current_elites * 2.5),
        )

    def modify_card_reward_creation_options(self, player, options, reward, room, run_state):
        if options.card_creation_source != "encounter" or options.context != "elite":
            return options
        if not options.allow_card_pool_modifications or options.forced_rarities:
            return options
        candidate_ids = tuple(options.custom_card_ids)
        rare_ids: tuple
        if candidate_ids:
            rare_ids = tuple(
                card_id
                for card_id in candidate_ids
                if card_metadata(card_id).rarity == CardRarity.RARE
            )
        else:
            character_ids = options.character_ids
            if options.use_default_character_pool and not character_ids:
                character_ids = (player.character_id,)
            seen_ids = set()
            rares = []
            for character_id in character_ids:
                for card_id in eligible_character_cards(
                    character_id,
                    rarity=CardRarity.RARE,
                    generation_context=options.generation_context,
                ):
                    if card_id in seen_ids:
                        continue
                    seen_ids.add(card_id)
                    rares.append(card_id)
            if options.include_colorless:
                for card_id in eligible_registered_cards(
                    module_name="sts2_env.cards.colorless",
                    rarity=CardRarity.RARE,
                    generation_context=options.generation_context,
                ):
                    if card_id in seen_ids:
                        continue
                    seen_ids.add(card_id)
                    rares.append(card_id)
            rare_ids = tuple(rares)
        if not rare_ids:
            rare_ids = tuple(
                eligible_character_cards(
                    player.character_id,
                    rarity=CardRarity.RARE,
                    generation_context=options.generation_context,
                )
            )
        return CardRewardGenerationOptions(
            context=options.context,
            num_cards=options.num_cards,
            character_ids=options.character_ids,
            forced_rarities=(CardRarity.RARE,) * options.num_cards,
            include_colorless=options.include_colorless,
            use_default_character_pool=False,
            generation_context=options.generation_context,
            roll_upgrade=options.roll_upgrade,
            card_creation_source=options.card_creation_source,
            allow_card_pool_modifications=options.allow_card_pool_modifications,
            has_custom_card_pool=True,
            custom_card_ids=rare_ids,
        )


class CharacterCardsModifier(ModifierModel):
    def __init__(self, character_id: str) -> None:
        super().__init__("character_cards")
        self.character_id = character_id

    def _with_character(self, character_ids: tuple[str, ...]) -> tuple[str, ...]:
        if self.character_id in character_ids:
            return character_ids
        return (*character_ids, self.character_id)

    def modify_card_reward_creation_options(self, player, options, reward, room, run_state):
        if not options.allow_card_pool_modifications:
            return options
        character_ids = options.character_ids
        if options.use_default_character_pool and not character_ids:
            character_ids = (player.character_id,)
        return CardRewardGenerationOptions(
            context=options.context,
            num_cards=options.num_cards,
            character_ids=self._with_character(character_ids),
            forced_rarities=options.forced_rarities,
            include_colorless=options.include_colorless,
            use_default_character_pool=False,
            generation_context=options.generation_context,
            roll_upgrade=options.roll_upgrade,
            card_creation_source=options.card_creation_source,
            allow_card_pool_modifications=options.allow_card_pool_modifications,
            has_custom_card_pool=options.has_custom_card_pool,
            custom_card_ids=options.custom_card_ids,
        )

    def modify_merchant_card_character_ids(self, player, character_ids, run_state):
        return self._with_character(character_ids)


class CursedRunModifier(ModifierModel):
    def __init__(self) -> None:
        super().__init__("cursed_run")

    def after_act_entered(self, run_state) -> None:
        for player in run_state.players:
            player.add_random_curses(1, rng=run_state.rng.niche)


class DeadlyEventsModifier(ModifierModel):
    def __init__(self) -> None:
        super().__init__("deadly_events")

    def on_run_created(self, run_state) -> None:
        self._set_unknown_elite_odds(run_state)

    def after_act_entered(self, run_state) -> None:
        self._set_unknown_elite_odds(run_state)

    def after_relic_grab_bags_populated(self, run_state) -> None:
        for player in run_state.players:
            player.remove_relic_from_grab_bag("JUZU_BRACELET")

    def _set_unknown_elite_odds(self, run_state) -> None:
        run_state.unknown_odds._base[RoomType.ELITE] = 0.1
        run_state.unknown_odds._current[RoomType.ELITE] = 0.1

    def modify_odds_increase_for_unrolled_room_type(self, room_type, odds_increase: float) -> float:
        if room_type is RoomType.TREASURE:
            return odds_increase * 2
        return odds_increase


class MidasModifier(ModifierModel):
    def __init__(self) -> None:
        super().__init__("midas")

    def modify_rewards_late(self, player, rewards, room, run_state):
        modified = []
        for reward in rewards:
            if isinstance(reward, GoldReward):
                amount = reward.amount if reward.is_populated else reward.min_gold
                doubled = GoldReward(player.player_id, amount * 2, amount * 2)
                doubled.amount = amount * 2
                doubled.is_populated = True
                modified.append(doubled)
            else:
                modified.append(reward)
        return modified

    def modify_rest_site_options(self, player, options, run_state):
        return [option for option in options if option.option_id != "SMITH"]


class NightTerrorsModifier(ModifierModel):
    def __init__(self) -> None:
        super().__init__("night_terrors")

    def modify_rest_site_heal_amount(self, player, amount: int, run_state) -> int:
        return player.max_hp

    def after_rest_site_heal(self, player, healed: int, run_state) -> None:
        player.lose_max_hp(5)


class VintageModifier(ModifierModel):
    def __init__(self) -> None:
        super().__init__("vintage")

    def modify_rewards_late(self, player, rewards, room, run_state):
        if getattr(room, "room_type", None) != RoomType.MONSTER:
            return rewards
        modified = []
        for reward in rewards:
            if isinstance(reward, CardReward):
                modified.append(RelicReward(player.player_id))
            else:
                modified.append(reward)
        return modified


class SpecializedModifier(ModifierModel):
    def __init__(self) -> None:
        super().__init__("specialized")

    def generate_neow_event_result(self, run_state) -> EventResult:
        cards = generate_uniform_noncombat_cards(
            run_state,
            num_cards=1,
            distinct=True,
        )
        if cards:
            card = cards[0]
            for idx in range(5):
                run_state.player.add_card_instance_to_deck(card.clone(30_000_000 + idx))
        return EventResult(finished=True, description="Added 5 copies of one random card.")


class SealedDeckModifier(ModifierModel):
    def __init__(self) -> None:
        super().__init__("sealed_deck", clears_player_deck=True)

    def generate_neow_event_result(self, run_state) -> EventResult:
        cards = generate_combat_reward_cards(
            run_state,
            context="regular",
            num_cards=30,
            generation_context=None,
            roll_upgrade=False,
        )
        if not cards:
            return EventResult(finished=True, description="No cards available.")
        run_state.pending_choice = PendingCardChoice(
            prompt="Choose 10 cards for your sealed deck",
            options=[CardChoiceOption(card=card, source_pile="deck") for card in cards],
            resolver=lambda selected: [run_state.player.add_card_instance_to_deck(card) for card in selected],
            allow_skip=False,
            min_choices=min(10, len(cards)),
            max_choices=min(10, len(cards)),
        )
        self._remove_pandoras_box(run_state)
        return EventResult(
            finished=False,
            description="Choose 10 cards for your sealed deck.",
        )
