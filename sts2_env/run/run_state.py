"""RunState: persistent player state across combats.

Matches RunState.cs from MegaCrit.Sts2.Core.Runs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sts2_env.cards.enchantments import can_enchant_card
from sts2_env.cards.factory import (
    create_card,
    create_transform_card,
    eligible_character_cards,
    eligible_registered_cards,
)
from sts2_env.core.selection import CardChoiceOption, PendingCardChoice
from sts2_env.core.enums import CardId, CardRarity, CardType
from sts2_env.core.rng import Rng, deterministic_hash_code
from sts2_env.core.enums import MapPointType, RoomType
from sts2_env.characters.all import get_character
from sts2_env.map.map_point import MapCoord, MapPoint
from sts2_env.map.generator import ActMap, generate_act_map, generate_spoils_act_map
from sts2_env.map.acts import ActConfig, get_act_config, ALL_ACTS
from sts2_env.potions.base import PotionInstance
from sts2_env.relics.base import RelicRarity
from sts2_env.cards.base import (
    CardInstance,
    capture_self_mutating_card_progress,
    restore_self_mutating_card_progress,
)
from sts2_env.run.odds import UnknownMapPointOdds, CardRarityOdds, PotionRewardOdds


_MULTIPLAYER_ONLY_CARD_IDS = frozenset({
    CardId.BEACON_OF_HOPE,
    CardId.BELIEVE_IN_YOU,
    CardId.COORDINATE_CARD,
    CardId.DEMONIC_SHIELD,
    CardId.ENERGY_SURGE,
    CardId.FLANKING,
    CardId.GANG_UP,
    CardId.GLIMPSE_BEYOND,
    CardId.HAMMER_TIME,
    CardId.HUDDLE_UP,
    CardId.IGNITION,
    CardId.INTERCEPT_CARD,
    CardId.KNOCKDOWN,
    CardId.LARGESSE,
    CardId.LEGION_OF_BONE,
    CardId.LIFT,
    CardId.MIMIC,
    CardId.RALLY,
    CardId.SNEAKY_CARD,
    CardId.TAG_TEAM,
    CardId.TANK_CARD,
})


@dataclass
class PlayerState:
    """Persistent state for a single player across a run."""

    player_id: int = 1
    character_id: str = "Ironclad"
    max_hp: int = 80
    current_hp: int = 80
    gold: int = 99
    deck: list[CardInstance] = field(default_factory=list)
    relics: list[str] = field(default_factory=list)
    relic_objects: list[Any] = field(default_factory=list)
    potions: list[PotionInstance | None] = field(default_factory=list)
    can_remove_potions: bool = True
    max_potion_slots: int = 3
    max_energy: int = 3
    base_orb_slot_count: int = 0
    relic_grab_bag: list[str] = field(default_factory=list)
    relic_grab_bag_by_rarity: dict[RelicRarity, list[str]] = field(default_factory=dict)
    relic_grab_bag_fallback: list[str] = field(default_factory=list)
    unlock_state: dict[str, Any] = field(default_factory=dict)
    discovered_cards: list[str] = field(default_factory=list)
    discovered_relics: list[str] = field(default_factory=list)
    discovered_potions: list[str] = field(default_factory=list)
    discovered_enemies: list[str] = field(default_factory=list)
    discovered_epochs: list[str] = field(default_factory=list)
    card_shop_removals_used: int = 0
    wongo_points: int = 0
    run_state: Any = None

    def add_potion(self, potion: PotionInstance) -> bool:
        """Add a potion to first empty slot. Returns False if no room."""
        for i in range(self.max_potion_slots):
            if i >= len(self.potions):
                self.potions.append(None)
            if self.potions[i] is None:
                potion.slot_index = i
                self.potions[i] = potion
                return True
        return False

    def remove_potion(self, slot: int) -> PotionInstance | None:
        if 0 <= slot < len(self.potions):
            p = self.potions[slot]
            self.potions[slot] = None
            return p
        return None

    def held_potions(self) -> list[PotionInstance]:
        return [p for p in self.potions if p is not None]

    def request_deck_choice(
        self,
        *,
        prompt: str,
        cards: list[CardInstance],
        resolver,
        allow_skip: bool = False,
        min_count: int = 1,
        max_count: int = 1,
        require_manual_confirmation: bool = False,
    ) -> bool:
        if (
            self.run_state is None
            or self.run_state.pending_choice is not None
            or not getattr(self.run_state, "enable_deck_choice_requests", False)
        ):
            return False
        if not cards:
            return False
        if self._can_auto_resolve_deck_choice(
            cards,
            allow_skip=allow_skip,
            min_count=min_count,
            max_count=max_count,
            require_manual_confirmation=require_manual_confirmation,
        ):
            resolver(list(cards))
            return True
        self.run_state.pending_choice = PendingCardChoice(
            prompt=prompt,
            options=[CardChoiceOption(card=card, source_pile="deck") for card in cards],
            resolver=resolver,
            allow_skip=allow_skip,
            min_choices=min_count,
            max_choices=max_count,
        )
        return True

    def _can_auto_resolve_deck_choice(
        self,
        cards: list[CardInstance],
        *,
        allow_skip: bool,
        min_count: int,
        max_count: int,
        require_manual_confirmation: bool = False,
    ) -> bool:
        return (
            self.run_state is not None
            and self.run_state.pending_choice is None
            and getattr(self.run_state, "enable_deck_choice_requests", False)
            and not require_manual_confirmation
            and not allow_skip
            and min_count == max_count
            and len(cards) <= min_count
        )

    def heal(self, amount: int) -> int:
        before = self.current_hp
        self.current_hp = min(self.current_hp + amount, self.max_hp)
        return self.current_hp - before

    def lose_hp(self, amount: int) -> int:
        actual = min(amount, self.current_hp)
        self.current_hp = max(0, self.current_hp - amount)
        return actual

    def gain_gold(self, amount: int) -> None:
        if amount <= 0:
            return
        for relic in self._ensure_relic_objects():
            if relic.should_gain_gold(self, amount) is False:
                return
        self.gold += int(amount)
        for relic in self._ensure_relic_objects():
            on_gold_gained = getattr(relic, "on_gold_gained", None)
            if callable(on_gold_gained):
                on_gold_gained(self, amount)

    def lose_gold(self, amount: int) -> int:
        actual = min(amount, self.gold)
        self.gold -= actual
        return actual

    def gain_potion_slots(self, amount: int) -> None:
        if amount > 0:
            self.max_potion_slots += amount

    def _ensure_relic_objects(self) -> list[Any]:
        from sts2_env.relics.registry import create_relic_by_name

        if len(self.relic_objects) == len(self.relics):
            return self.relic_objects
        self.relic_objects = []
        for relic_id in self.relics:
            try:
                self.relic_objects.append(create_relic_by_name(relic_id))
            except KeyError:
                continue
        return self.relic_objects

    def get_relic_objects(self) -> list[Any]:
        return self._ensure_relic_objects()

    def has_event_pet(self) -> bool:
        return any(relic_id in {"BYRDPIP", "PAELS_LEGION"} for relic_id in self.relics)

    def _roll_relic_rarity(self, rng: Any) -> RelicRarity:
        roll = rng.next_float()
        if roll < 0.5:
            return RelicRarity.COMMON
        if roll < 0.83:
            return RelicRarity.UNCOMMON
        return RelicRarity.RARE

    def populate_relic_grab_bag(self) -> None:
        from sts2_env.relics.base import RelicPool
        from sts2_env.relics.registry import RELIC_REGISTRY, load_all_relics

        load_all_relics()
        desired_pool = getattr(RelicPool, self.character_id.upper(), None)
        allowed_rarities = (
            RelicRarity.COMMON,
            RelicRarity.UNCOMMON,
            RelicRarity.RARE,
            RelicRarity.SHOP,
        )
        self.relic_grab_bag_by_rarity = {rarity: [] for rarity in allowed_rarities}
        self.relic_grab_bag_fallback = []
        for relic_id, relic_cls in RELIC_REGISTRY.items():
            if relic_cls.rarity not in allowed_rarities:
                continue
            if relic_cls.pool in {RelicPool.EVENT, RelicPool.FALLBACK, RelicPool.DEPRECATED}:
                continue
            if desired_pool is not None and relic_cls.pool not in {RelicPool.SHARED, desired_pool}:
                continue
            self.relic_grab_bag_by_rarity[relic_cls.rarity].append(relic_id.name)
        for rarity, relic_ids in self.relic_grab_bag_by_rarity.items():
            self.run_state.rng.rewards.shuffle(relic_ids)
        self.relic_grab_bag = [
            relic_id
            for rarity in allowed_rarities
            for relic_id in self.relic_grab_bag_by_rarity.get(rarity, [])
        ]

    def has_available_relics(self) -> bool:
        from sts2_env.relics.registry import create_relic_by_name

        if not self.relic_grab_bag_by_rarity and not self.relic_grab_bag_fallback:
            self.populate_relic_grab_bag()
        for rarity in (RelicRarity.COMMON, RelicRarity.UNCOMMON, RelicRarity.RARE, RelicRarity.SHOP):
            for relic_id in self.relic_grab_bag_by_rarity.get(rarity, []):
                if create_relic_by_name(relic_id).is_allowed(self.run_state):
                    return True
        return any(create_relic_by_name(relic_id).is_allowed(self.run_state) for relic_id in self.relic_grab_bag_fallback)

    def _relic_grab_bag_order(self, rarity: RelicRarity) -> list[RelicRarity]:
        if rarity is RelicRarity.SHOP:
            return [RelicRarity.SHOP, RelicRarity.COMMON, RelicRarity.UNCOMMON, RelicRarity.RARE]
        if rarity is RelicRarity.COMMON:
            return [RelicRarity.COMMON, RelicRarity.UNCOMMON, RelicRarity.RARE]
        if rarity is RelicRarity.UNCOMMON:
            return [RelicRarity.UNCOMMON, RelicRarity.RARE]
        if rarity is RelicRarity.RARE:
            return [RelicRarity.RARE]
        return []

    def remove_relic_from_grab_bag(self, relic_id: str) -> None:
        while relic_id in self.relic_grab_bag:
            self.relic_grab_bag.remove(relic_id)
        for deque in self.relic_grab_bag_by_rarity.values():
            while relic_id in deque:
                deque.remove(relic_id)
        while relic_id in self.relic_grab_bag_fallback:
            self.relic_grab_bag_fallback.remove(relic_id)

    def pull_next_relic_reward_id(
        self,
        *,
        rarity: RelicRarity | None = None,
        rng_stream: str = "rewards",
        excluded_relic_ids: set[str] | None = None,
    ) -> str | None:
        from sts2_env.relics.registry import create_relic_by_name

        if not self.relic_grab_bag_by_rarity and not self.relic_grab_bag_fallback:
            self.populate_relic_grab_bag()
        relic_rng = getattr(self.run_state.rng, rng_stream, self.run_state.rng.rewards)
        target_rarity = rarity or self._roll_relic_rarity(relic_rng)
        excluded = set(excluded_relic_ids or ())
        excluded.update(self.relics)
        for candidate_rarity in self._relic_grab_bag_order(target_rarity):
            deque = self.relic_grab_bag_by_rarity.get(candidate_rarity, [])
            for idx, relic_id in enumerate(list(deque)):
                if relic_id in excluded:
                    continue
                if not create_relic_by_name(relic_id).is_allowed(self.run_state):
                    continue
                deque.pop(idx)
                if relic_id in self.relic_grab_bag:
                    self.relic_grab_bag.remove(relic_id)
                return relic_id
        for idx, relic_id in enumerate(list(self.relic_grab_bag_fallback)):
            if relic_id in excluded:
                continue
            if not create_relic_by_name(relic_id).is_allowed(self.run_state):
                continue
            self.relic_grab_bag_fallback.pop(idx)
            if relic_id in self.relic_grab_bag:
                self.relic_grab_bag.remove(relic_id)
            return relic_id
        return "CIRCLET"

    def upgrade_card_instance(self, card: CardInstance | None) -> CardInstance | None:
        if card is None or card.upgraded:
            return card
        progress = capture_self_mutating_card_progress(card)
        try:
            upgraded_card = create_card(card.card_id, upgraded=True)
        except KeyError:
            return card
        if not upgraded_card.upgraded:
            return card

        card.cost = upgraded_card.cost
        card.card_type = upgraded_card.card_type
        card.target_type = upgraded_card.target_type
        card.rarity = upgraded_card.rarity
        card.base_damage = upgraded_card.base_damage
        card.base_block = upgraded_card.base_block
        card.upgraded = upgraded_card.upgraded
        card.keywords = upgraded_card.keywords
        card.tags = upgraded_card.tags
        card.can_be_generated_in_combat = upgraded_card.can_be_generated_in_combat
        card.can_be_generated_by_modifiers = upgraded_card.can_be_generated_by_modifiers
        card.effect_vars = dict(upgraded_card.effect_vars)
        card.original_cost = upgraded_card.original_cost
        card.has_energy_cost_x = upgraded_card.has_energy_cost_x
        card.star_cost = upgraded_card.star_cost
        restore_self_mutating_card_progress(card, progress)
        return card

    def modify_card_being_added_to_deck(self, card: CardInstance) -> CardInstance:
        modified = card
        for relic in self.get_relic_objects():
            modifier = getattr(relic, "modify_card_being_added_to_deck", None)
            if not callable(modifier):
                continue
            updated = modifier(self, modified)
            if updated is not None:
                modified = updated
        return modified

    def add_card_instance_to_deck(self, card: CardInstance, source: object | None = None) -> None:
        card = self.modify_card_being_added_to_deck(card)
        self.deck.append(card)
        for relic in self.get_relic_objects():
            on_card_added = getattr(relic, "on_card_added_to_deck", None)
            if callable(on_card_added):
                on_card_added(self, card, source)
        if self.run_state is not None:
            for modifier in self.run_state.modifiers:
                modifier.after_card_added_to_deck(self, card, source)

    def gain_max_hp(self, amount: int) -> None:
        self.max_hp += amount
        self.current_hp += amount

    def lose_max_hp(self, amount: int) -> None:
        self.max_hp = max(1, self.max_hp - amount)
        self.current_hp = min(self.current_hp, self.max_hp)

    def gain_potion_slots(self, amount: int) -> None:
        self.max_potion_slots = max(0, self.max_potion_slots + amount)

    def lose_all_gold(self) -> int:
        lost = self.gold
        self.gold = 0
        return lost

    def take_damage(self, amount: int) -> int:
        return self.lose_hp(amount)

    def enchant_cards(self, enchantment: str, amount: int, count: int) -> int:
        candidates = [card for card in self.deck if can_enchant_card(card, enchantment)]
        return self.enchant_selected_cards(enchantment, amount, count, cards=candidates)

    def enchant_selected_cards(
        self,
        enchantment: str,
        amount: int,
        count: int,
        *,
        cards: list[CardInstance] | None = None,
        min_count: int | None = None,
    ) -> int:
        candidates = list(cards) if cards is not None else [card for card in self.deck if can_enchant_card(card, enchantment)]
        max_count = min(count, len(candidates))
        required = min_count if min_count is not None else max_count
        allow_skip = required == 0
        if count > 0 and candidates and self._can_auto_resolve_deck_choice(
            candidates,
            allow_skip=allow_skip,
            min_count=required,
            max_count=max_count,
        ):
            for card in candidates[:max_count]:
                card.add_enchantment(enchantment, amount)
            return max_count
        if count > 0 and candidates and self.request_deck_choice(
            prompt=f"Choose {count} cards to enchant with {enchantment}",
            cards=candidates,
            resolver=lambda selected: [card.add_enchantment(enchantment, amount) for card in selected],
            allow_skip=allow_skip,
            min_count=required,
            max_count=max_count,
        ):
            return 0
        enchanted = 0
        for card in candidates:
            if enchanted >= count:
                break
            card.add_enchantment(enchantment, amount)
            enchanted += 1
        return enchanted

    def enchant_all_cards(self, enchantment: str, amount: int = 1) -> int:
        enchanted = 0
        for card in self.deck:
            if can_enchant_card(card, enchantment):
                card.add_enchantment(enchantment, amount)
                enchanted += 1
        return enchanted

    def enchant_basic_strikes(self, enchantment: str, amount: int = 1) -> int:
        enchanted = 0
        for card in self.deck:
            if (
                card.rarity.name == "BASIC"
                and "STRIKE" in card.card_id.name
                and can_enchant_card(card, enchantment)
            ):
                card.add_enchantment(enchantment, amount)
                enchanted += 1
        return enchanted

    def _coerce_card_id(self, name: str) -> CardId | None:
        if name == "Strike":
            return next((card_id for card_id in get_character(self.character_id).card_pool if "STRIKE" in card_id.name), None)
        if name == "Defend":
            return next((card_id for card_id in get_character(self.character_id).card_pool if "DEFEND" in card_id.name), None)
        candidates = {
            name,
            name.upper(),
            "".join(("_" + ch if ch.isupper() else ch) for ch in name).upper().lstrip("_"),
        }
        for candidate in candidates:
            if candidate in CardId.__members__:
                return CardId[candidate]
        return None

    def add_card_to_deck(self, name: str, upgraded: bool = False) -> bool:
        card_id = self._coerce_card_id(name)
        if card_id is None:
            return False
        try:
            card = create_card(card_id, upgraded=upgraded)
        except KeyError:
            return False
        self.add_card_instance_to_deck(card)
        return True

    def add_random_card_to_deck(self, rarity: str, upgraded: bool = False) -> bool:
        card_rarity = CardRarity[rarity.upper()]
        candidates = eligible_character_cards(
            self.character_id,
            rarity=card_rarity,
            generation_context="modifier",
            is_multiplayer=len(self.run_state.players) > 1,
        )
        if not candidates:
            return False
        card_id = self.run_state.rng.rewards.choice(candidates)
        self.add_card_instance_to_deck(create_card(card_id, upgraded=upgraded))
        return True

    def add_random_curses(self, count: int, rng: Rng | None = None) -> int:
        curse_ids = eligible_registered_cards(card_type=CardType.CURSE, generation_context="modifier")
        selected_rng = rng or self.run_state.rng.rewards
        chosen_ids = selected_rng.sample(curse_ids, min(max(0, count), len(curse_ids)))
        added = 0
        for card_id in chosen_ids:
            self.add_card_instance_to_deck(create_card(card_id))
            added += 1
        return added

    def duplicable_deck_cards(self) -> list[CardInstance]:
        return [card for card in self.deck if card.card_type != CardType.QUEST]

    def removable_deck_cards(self) -> list[CardInstance]:
        return [
            card for card in self.deck
            if card.card_type != CardType.QUEST and card.rarity.name != "QUEST" and card.is_removable
        ]

    def transformable_deck_cards(self) -> list[CardInstance]:
        return [card for card in self.removable_deck_cards()]

    def basic_strike_defend_cards(self) -> list[CardInstance]:
        return [
            card for card in self.removable_deck_cards()
            if card.rarity == CardRarity.BASIC and ("STRIKE" in card.card_id.name or "DEFEND" in card.card_id.name)
        ]

    def upgradable_deck_cards(self, card_type: CardType | None = None) -> list[CardInstance]:
        candidates: list[CardInstance] = []
        for card in self.deck:
            if card.upgraded:
                continue
            if card_type is not None and card.card_type != card_type:
                continue
            try:
                upgraded_card = create_card(card.card_id, upgraded=True)
            except KeyError:
                continue
            if upgraded_card.upgraded:
                candidates.append(card)
        return candidates

    def duplicate_card_from_deck(self, *, cards: list[CardInstance] | None = None) -> bool:
        candidates = list(cards) if cards is not None else self.duplicable_deck_cards()
        if candidates and self._can_auto_resolve_deck_choice(
            candidates,
            allow_skip=False,
            min_count=1,
            max_count=1,
        ):
            self.add_card_instance_to_deck(candidates[0].clone(20_000_000 + len(self.deck)))
            return True
        if candidates and self.request_deck_choice(
            prompt="Choose a card to duplicate",
            cards=candidates,
            resolver=lambda selected: selected and self.add_card_instance_to_deck(selected[0].clone(20_000_000 + len(self.deck))),
            allow_skip=False,
        ):
            return True
        if not candidates:
            return False
        self.add_card_instance_to_deck(candidates[0].clone(20_000_000 + len(self.deck)))
        return True

    def duplicate_last_added_card(self, source: object | None = None) -> bool:
        if not self.deck:
            return False
        self.add_card_instance_to_deck(self.deck[-1].clone(20_000_000 + len(self.deck)), source=source)
        return True

    def upgrade_selected_cards(
        self,
        count: int,
        *,
        cards: list[CardInstance] | None = None,
        require_manual_confirmation: bool = False,
    ) -> int:
        candidates = list(cards) if cards is not None else self.upgradable_deck_cards()
        required = min(count, len(candidates))
        if required > 0 and self._can_auto_resolve_deck_choice(
            candidates,
            allow_skip=False,
            min_count=required,
            max_count=required,
            require_manual_confirmation=require_manual_confirmation,
        ):
            upgraded = 0
            for card in candidates:
                if self.upgrade_card_instance(card) is not None and card.upgraded:
                    upgraded += 1
            return upgraded
        if required > 0 and self.request_deck_choice(
            prompt=f"Choose {min(count, len(candidates))} cards to upgrade",
            cards=candidates,
            resolver=lambda selected: [self.upgrade_card_instance(card) for card in selected],
            allow_skip=False,
            min_count=required,
            max_count=required,
        ):
            return 0
        upgraded = 0
        for card in candidates:
            if upgraded >= count:
                break
            if self.upgrade_card_instance(card) is not None and card.upgraded:
                upgraded += 1
        return upgraded

    def clone_enchanted_cards(self, enchantment: str) -> int:
        clones = []
        for card in self.deck:
            if card.has_enchantment(enchantment):
                clones.append(card.clone(10_000_000 + len(clones)))
        self.deck.extend(clones)
        return len(clones)

    def remove_cards_from_deck(
        self,
        count: int,
        *,
        cards: list[CardInstance] | None = None,
        require_manual_confirmation: bool = False,
    ) -> int:
        candidates = list(cards) if cards is not None else self.removable_deck_cards()
        required = min(count, len(candidates))
        if required > 0 and self._can_auto_resolve_deck_choice(
            candidates,
            allow_skip=False,
            min_count=required,
            max_count=required,
            require_manual_confirmation=require_manual_confirmation,
        ):
            selected_ids = {id(card) for card in candidates[:required]}
            self.deck = [card for card in self.deck if id(card) not in selected_ids]
            return required
        if required > 0 and self.request_deck_choice(
            prompt=f"Choose {min(count, len(candidates))} cards to remove",
            cards=candidates,
            resolver=lambda selected: [self.deck.remove(card) for card in selected if card in self.deck],
            allow_skip=False,
            min_count=required,
            max_count=required,
        ):
            return 0
        removed = 0
        selected = candidates[:count]
        remaining = []
        for card in self.deck:
            if removed < count and card in selected:
                removed += 1
                continue
            remaining.append(card)
        self.deck = remaining
        return removed

    def transform_cards(
        self,
        count: int,
        *,
        cards: list[CardInstance] | None = None,
        rng: Rng | None = None,
    ) -> int:
        candidates = list(cards) if cards is not None else self.transformable_deck_cards()
        required = min(count, len(candidates))
        if required > 0 and self._can_auto_resolve_deck_choice(
            candidates,
            allow_skip=False,
            min_count=required,
            max_count=required,
        ):
            return self._transform_selected_cards(candidates[:required], rng=rng)
        if required > 0 and self.request_deck_choice(
            prompt=f"Choose {min(count, len(candidates))} cards to transform",
            cards=candidates,
            resolver=lambda selected: self._transform_selected_cards(selected, rng=rng),
            allow_skip=False,
            min_count=required,
            max_count=required,
        ):
            return 0
        candidates = candidates[:count]
        transformed = 0
        for card in candidates[:count]:
            replacement = create_transform_card(
                card,
                character_id=self.character_id,
                rng=rng or self.run_state.rng.niche,
                generation_context=None,
                is_multiplayer=len(self.run_state.players) > 1,
            )
            self._apply_card_replacement(card, replacement)
            transformed += 1
        return transformed

    def transform_basic_cards(self, count: int, upgrade: int = 0) -> int:
        basics = self.basic_strike_defend_cards()[:count]
        transformed = self.transform_cards(len(basics), cards=basics)
        if upgrade:
            self.upgrade_random_cards(None, upgrade)
        return transformed

    def transform_all_basic_cards(self) -> int:
        basics = self.basic_strike_defend_cards()
        return self.transform_cards(len(basics), cards=basics)

    def transform_specific_cards(self, cards: list[CardInstance], rng: Rng | None = None) -> int:
        return self._transform_selected_cards(list(cards), rng=rng)

    def transform_specific_cards_with_mapping(
        self,
        cards: list[CardInstance],
        mapping: dict[CardId, CardId],
    ) -> int:
        return self._transform_selected_cards_with_mapping(list(cards), mapping)

    def transform_starter_card(self, *, mapping: dict[CardId, CardId] | None = None) -> bool:
        basics = [
            card for card in self.deck
            if (card.rarity == CardRarity.BASIC if mapping is None else card.card_id in mapping)
        ]
        if basics and self.request_deck_choice(
            prompt="Choose a starter card to transform",
            cards=basics,
            resolver=lambda selected: self._transform_selected_cards(selected) if mapping is None else self._transform_selected_cards_with_mapping(selected, mapping),
            allow_skip=True,
        ):
            return True
        if not basics:
            return False
        if mapping is not None:
            return self._transform_selected_cards_with_mapping(basics[:1], mapping) > 0
        return self.transform_cards(1, cards=basics) > 0

    def transform_cards_to(
        self,
        name: str,
        count: int,
        *,
        cards: list[CardInstance] | None = None,
        preserve_upgrades: bool = False,
        preserve_enchantments: bool = False,
        min_count: int | None = None,
    ) -> int:
        card_id = self._coerce_card_id(name)
        if card_id is None:
            return 0
        candidates = list(cards) if cards is not None else list(self.deck)
        required = min_count if min_count is not None else min(count, len(candidates))
        max_count = min(count, len(candidates))
        allow_skip = min_count == 0
        if count > 0 and candidates and self._can_auto_resolve_deck_choice(
            candidates,
            allow_skip=allow_skip,
            min_count=required,
            max_count=max_count,
        ):
            return self._transform_selected_cards_to(
                candidates[:max_count],
                card_id,
                preserve_upgrades=preserve_upgrades,
                preserve_enchantments=preserve_enchantments,
            )
        if count > 0 and candidates and self.request_deck_choice(
            prompt=f"Choose {min(count, len(candidates))} cards to transform into {name}",
            cards=candidates,
            resolver=lambda selected: self._transform_selected_cards_to(
                selected,
                card_id,
                preserve_upgrades=preserve_upgrades,
                preserve_enchantments=preserve_enchantments,
            ),
            allow_skip=allow_skip,
            min_count=required,
            max_count=max_count,
        ):
            return 0
        transformed = 0
        for card in candidates[:count]:
            replacement = create_card(card_id, upgraded=preserve_upgrades and card.upgraded)
            old_enchantments = self._apply_card_replacement(card, replacement)
            if preserve_enchantments:
                for name, amount in old_enchantments.items():
                    if can_enchant_card(card, name):
                        card.add_enchantment(name, amount)
            transformed += 1
        return transformed

    def transform_and_upgrade_cards(
        self,
        count: int,
        *,
        cards: list[CardInstance] | None = None,
        rng: Rng | None = None,
    ) -> int:
        candidates = list(cards) if cards is not None else self.transformable_deck_cards()
        required = min(count, len(candidates))
        if required > 0 and self._can_auto_resolve_deck_choice(
            candidates,
            allow_skip=False,
            min_count=required,
            max_count=required,
        ):
            return self._transform_and_upgrade_selected(candidates[:required], rng=rng)
        if required > 0 and self.request_deck_choice(
            prompt=f"Choose {min(count, len(candidates))} cards to transform and upgrade",
            cards=candidates,
            resolver=lambda selected: self._transform_and_upgrade_selected(selected, rng=rng),
            allow_skip=False,
            min_count=required,
            max_count=required,
        ):
            return 0
        return self._transform_and_upgrade_selected(candidates[:count], rng=rng)

    def _apply_card_replacement(self, card: CardInstance, replacement: CardInstance) -> None:
        original_enchantments = dict(card.enchantments)
        card.card_id = replacement.card_id
        card.cost = replacement.cost
        card.card_type = replacement.card_type
        card.target_type = replacement.target_type
        card.rarity = replacement.rarity
        card.base_damage = replacement.base_damage
        card.base_block = replacement.base_block
        card.upgraded = replacement.upgraded
        card.keywords = replacement.keywords
        card.tags = replacement.tags
        card.can_be_generated_in_combat = replacement.can_be_generated_in_combat
        card.can_be_generated_by_modifiers = replacement.can_be_generated_by_modifiers
        card.enchantments = dict(replacement.enchantments)
        card.effect_vars = dict(replacement.effect_vars)
        card.original_cost = replacement.original_cost
        return original_enchantments

    def _transform_selected_cards(self, cards: list[CardInstance], rng: Rng | None = None) -> int:
        transformed = 0
        for card in cards:
            replacement = create_transform_card(
                card,
                character_id=self.character_id,
                rng=rng or self.run_state.rng.niche,
                generation_context=None,
                is_multiplayer=len(self.run_state.players) > 1,
            )
            self._apply_card_replacement(card, replacement)
            transformed += 1
        return transformed

    def _transform_selected_cards_to(
        self,
        cards: list[CardInstance],
        card_id: CardId,
        *,
        preserve_upgrades: bool = False,
        preserve_enchantments: bool = False,
    ) -> int:
        transformed = 0
        for card in cards:
            replacement = create_card(card_id, upgraded=preserve_upgrades and card.upgraded)
            old_enchantments = self._apply_card_replacement(card, replacement)
            if preserve_enchantments:
                for name, amount in old_enchantments.items():
                    if can_enchant_card(card, name):
                        card.add_enchantment(name, amount)
            transformed += 1
        return transformed

    def _transform_and_upgrade_selected(self, cards: list[CardInstance], rng: Rng | None = None) -> int:
        transformed = self._transform_selected_cards(cards, rng=rng)
        for card in cards:
            self.upgrade_card_instance(card)
        return transformed

    def _transform_selected_cards_with_mapping(self, cards: list[CardInstance], mapping: dict[CardId, CardId]) -> int:
        transformed = 0
        for card in cards:
            target_id = mapping.get(card.card_id)
            if target_id is None:
                continue
            replacement = create_card(target_id, upgraded=card.upgraded)
            old_enchantments = self._apply_card_replacement(card, replacement)
            for name, amount in old_enchantments.items():
                if can_enchant_card(card, name):
                    card.add_enchantment(name, amount)
            transformed += 1
        return transformed

    def upgrade_random_cards(self, card_type: CardType | None, count: int, rng: Rng | None = None) -> int:
        candidates = [card for card in self.deck if not card.upgraded and (card_type is None or card.card_type == card_type)]
        if not candidates or count <= 0:
            return 0
        selected_rng = rng or self.run_state.rng.rewards
        candidates.sort(key=lambda card: (card.card_id.name, card.upgraded))
        selected_rng.shuffle(candidates)
        upgraded = 0
        for card in candidates[:count]:
            if self.upgrade_card_instance(card) is not None and card.upgraded:
                upgraded += 1
        return upgraded

    def procure_potion(self, potion_id: str) -> bool:
        from sts2_env.potions.base import create_potion, roll_random_potion_model

        for relic in self.get_relic_objects():
            should_procure = getattr(relic, "should_procure_potion", None)
            if callable(should_procure) and should_procure(self) is False:
                return False
        if potion_id == "random":
            model = roll_random_potion_model(
                self.run_state.rng.combat_potion_generation,
                character_id=self.character_id,
                in_combat=False,
            )
            if model is None:
                return False
            return self.add_potion(create_potion(model.potion_id))
        return self.add_potion(create_potion(potion_id))

    def fill_empty_potion_slots(self) -> int:
        filled = 0
        while len(self.held_potions()) < self.max_potion_slots:
            if not self.procure_potion("random"):
                break
            filled += 1
        return filled

    def offer_card_reward(self) -> None:
        from sts2_env.run.reward_objects import CardReward

        self.run_state.pending_rewards.append(
            CardReward(self.player_id, generation_context=None, card_creation_source="other")
        )

    def offer_custom_card_reward(
        self,
        *,
        context: str = "regular",
        option_count: int | None = None,
        cards_to_pick: int = 1,
        skippable: bool = True,
        character_ids: tuple[str, ...] | None = None,
        forced_rarities: tuple[CardRarity, ...] | None = None,
        include_colorless: bool = False,
        use_default_character_pool: bool = True,
        generation_context: str | None = "combat",
        roll_upgrade: bool = True,
        card_creation_source: str | None = None,
        allow_card_pool_modifications: bool = True,
        has_custom_card_pool: bool = False,
        custom_card_ids: tuple[CardId, ...] | None = None,
        cards: list[CardInstance] | None = None,
    ) -> None:
        from sts2_env.run.reward_objects import CardReward

        reward = CardReward(
            self.player_id,
            context=context,
            option_count=option_count,
            cards_to_pick=cards_to_pick,
            skippable=skippable,
            character_ids=character_ids,
            forced_rarities=forced_rarities,
            include_colorless=include_colorless,
            use_default_character_pool=use_default_character_pool,
            generation_context=generation_context,
            roll_upgrade=roll_upgrade,
            card_creation_source=card_creation_source,
            allow_card_pool_modifications=allow_card_pool_modifications,
            has_custom_card_pool=has_custom_card_pool,
            custom_card_ids=custom_card_ids,
            cards=cards,
        )
        self.run_state.pending_rewards.append(reward)

    def offer_colorless_cards(self, count: int) -> None:
        self.offer_custom_card_reward(
            option_count=count,
            include_colorless=True,
            use_default_character_pool=False,
            generation_context=None,
            card_creation_source="other",
            has_custom_card_pool=True,
        )

    def offer_multiplayer_cards(self, count: int) -> None:
        custom_card_ids = []
        seen_ids = set()
        for card_id in eligible_registered_cards(module_name="sts2_env.cards.colorless", generation_context=None):
            if card_id in _MULTIPLAYER_ONLY_CARD_IDS:
                custom_card_ids.append(card_id)
                seen_ids.add(card_id)
        for card_id in get_character(self.character_id).card_pool:
            if card_id in _MULTIPLAYER_ONLY_CARD_IDS and card_id not in seen_ids:
                custom_card_ids.append(card_id)
                seen_ids.add(card_id)
        self.offer_custom_card_reward(
            option_count=count,
            character_ids=(),
            include_colorless=False,
            use_default_character_pool=False,
            generation_context=None,
            card_creation_source="other",
            has_custom_card_pool=True,
            custom_card_ids=tuple(custom_card_ids),
        )

    def offer_relic_rewards(
        self,
        count: int,
        *,
        rarities: tuple[Any, ...] | None = None,
        rng_stream: str = "rewards",
    ) -> None:
        from sts2_env.run.reward_objects import RelicReward

        rarity_sequence = tuple(rarities or ())
        for index in range(count):
            rarity = rarity_sequence[index] if index < len(rarity_sequence) else None
            self.run_state.pending_rewards.append(
                RelicReward(self.player_id, rarity=rarity, rng_stream=rng_stream)
            )

    def offer_specific_relic_rewards(
        self,
        relic_ids: list[str],
        *,
        is_wax: bool = False,
    ) -> None:
        from sts2_env.run.reward_objects import RelicReward

        for relic_id in relic_ids:
            self.run_state.pending_rewards.append(
                RelicReward(self.player_id, relic_id=relic_id, is_wax=is_wax)
            )

    def offer_add_cards_reward(self, cards: list[CardInstance]) -> None:
        from sts2_env.run.reward_objects import AddCardsReward

        self.run_state.pending_rewards.append(AddCardsReward(self.player_id, cards))

    def offer_obtain_relics_reward(
        self,
        count: int,
        *,
        rarities: tuple[RelicRarity | None, ...] | None = None,
        relic_ids: tuple[str, ...] | list[str] | None = None,
        rng_stream: str = "rewards",
    ) -> None:
        from sts2_env.run.reward_objects import ObtainRelicsReward

        self.run_state.pending_rewards.append(
            ObtainRelicsReward(
                self.player_id,
                count=count,
                rarities=rarities,
                relic_ids=relic_ids,
                rng_stream=rng_stream,
            )
        )

    def offer_remove_card_reward(self, count: int = 1, *, cards: list[CardInstance] | None = None) -> None:
        from sts2_env.run.reward_objects import RemoveCardReward

        self.run_state.pending_rewards.append(RemoveCardReward(self.player_id, count=count, cards=cards))

    def offer_upgrade_cards_reward(self, count: int = 1, *, cards: list[CardInstance] | None = None) -> None:
        from sts2_env.run.reward_objects import UpgradeCardsReward

        self.run_state.pending_rewards.append(UpgradeCardsReward(self.player_id, count=count, cards=cards))

    def offer_transform_cards_reward(
        self,
        count: int = 1,
        *,
        upgrade: bool = False,
        cards: list[CardInstance] | None = None,
        mapping: dict[CardId, CardId] | None = None,
        rng_stream: str = "niche",
    ) -> None:
        from sts2_env.run.reward_objects import TransformCardsReward

        self.run_state.pending_rewards.append(
            TransformCardsReward(
                self.player_id,
                count=count,
                upgrade=upgrade,
                cards=cards,
                mapping=mapping,
                rng_stream=rng_stream,
            )
        )

    def offer_duplicate_card_reward(self, count: int = 1, *, cards: list[CardInstance] | None = None) -> None:
        from sts2_env.run.reward_objects import DuplicateCardReward

        self.run_state.pending_rewards.append(DuplicateCardReward(self.player_id, count=count, cards=cards))

    def offer_enchant_cards_reward(
        self,
        enchantment: str,
        amount: int = 1,
        count: int = 1,
        *,
        cards: list[CardInstance] | None = None,
        min_count: int | None = None,
    ) -> None:
        from sts2_env.run.reward_objects import EnchantCardsReward

        self.run_state.pending_rewards.append(
            EnchantCardsReward(
                self.player_id,
                enchantment=enchantment,
                amount=amount,
                count=count,
                cards=cards,
                min_count=min_count,
            )
        )

    def offer_potion_reward(self) -> None:
        from sts2_env.run.reward_objects import PotionReward

        self.run_state.pending_rewards.append(PotionReward(self.player_id))

    def offer_potions(self, count: int) -> None:
        for _ in range(count):
            self.offer_potion_reward()

    def offer_card_bundles(self) -> None:
        from sts2_env.run.reward_objects import CardBundlesReward

        is_multiplayer = len(self.run_state.players) > 1
        common_ids = eligible_character_cards(
            self.character_id,
            rarity=CardRarity.COMMON,
            generation_context=None,
            is_multiplayer=is_multiplayer,
        )
        uncommon_ids = eligible_character_cards(
            self.character_id,
            rarity=CardRarity.UNCOMMON,
            generation_context=None,
            is_multiplayer=is_multiplayer,
        )
        used_ids: set[CardId] = set()
        bundles: list[list[CardInstance]] = []
        for _ in range(2):
            if self.character_id == "Defect" and self.run_state.rng.rewards.next_int_exclusive(0, 100) < 1:
                bundles.append([create_card(CardId.CLAW), create_card(CardId.CLAW), create_card(CardId.CLAW)])
                continue
            bundle: list[CardInstance] = []
            available_common = [card_id for card_id in common_ids if card_id not in used_ids]
            for _ in range(2):
                card_id = self.run_state.rng.rewards.choice(available_common)
                bundle.append(create_card(card_id))
                used_ids.add(card_id)
                available_common.remove(card_id)
            available_uncommon = [card_id for card_id in uncommon_ids if card_id not in used_ids]
            card_id = self.run_state.rng.rewards.choice(available_uncommon)
            bundle.append(create_card(card_id))
            used_ids.add(card_id)
            bundles.append(bundle)
        self.run_state.pending_rewards.append(CardBundlesReward(self.player_id, bundles))

    def roll_relic_reward_id(
        self,
        *,
        rarity: Any | None = None,
        rng_stream: str = "rewards",
        excluded_relic_ids: set[str] | None = None,
    ) -> str | None:
        return self.pull_next_relic_reward_id(
            rarity=rarity,
            rng_stream=rng_stream,
            excluded_relic_ids=excluded_relic_ids,
        )

    def obtain_random_relics(self, count: int) -> int:
        obtained = 0
        rolled: set[str] = set()
        for _ in range(count):
            relic_id = self.roll_relic_reward_id(excluded_relic_ids=rolled)
            if relic_id is None:
                continue
            rolled.add(relic_id)
            if self.obtain_relic(relic_id):
                obtained += 1
        return obtained

    def upgrade_starter_relic(
        self,
        starter_relic_id: str | None = None,
        upgraded_relic_id: str | None = None,
    ) -> bool:
        mapping = {
            "BURNING_BLOOD": "BLACK_BLOOD",
            "RING_OF_THE_SNAKE": "RING_OF_THE_DRAKE",
            "CRACKED_CORE": "INFUSED_CORE",
            "BOUND_PHYLACTERY": "PHYLACTERY_UNBOUND",
            "DIVINE_RIGHT": "DIVINE_DESTINY",
        }
        for i, relic_id in enumerate(self.relics):
            if starter_relic_id is not None and relic_id != starter_relic_id:
                continue
            upgraded = upgraded_relic_id or mapping.get(relic_id)
            if upgraded is None:
                continue
            self.relics[i] = upgraded
            if i < len(self.relic_objects):
                from sts2_env.relics.registry import create_relic_by_name

                self.relic_objects[i] = create_relic_by_name(upgraded)
            return True
        return False

    def obtain_relic_with_setup(
        self,
        relic_id: str,
        *,
        setup_attrs: dict[str, object] | None = None,
        is_wax: bool = False,
    ) -> bool:
        from sts2_env.relics.registry import create_relic_by_name

        try:
            relic = create_relic_by_name(relic_id)
        except KeyError:
            relic = None
        canonical_relic_id = relic.relic_id.name if relic is not None else relic_id
        if relic is None and relic_id in self.relics:
            return False
        if relic is not None and not relic.is_stackable:
            for owned_relic_id in self.relics:
                try:
                    if create_relic_by_name(owned_relic_id).relic_id == relic.relic_id:
                        return False
                except KeyError:
                    if owned_relic_id == relic_id:
                        return False
        self.remove_relic_from_grab_bag(canonical_relic_id)
        if canonical_relic_id != relic_id:
            self.remove_relic_from_grab_bag(relic_id)
        self.relics.append(canonical_relic_id)
        if relic is None:
            return True
        for key, value in (setup_attrs or {}).items():
            setattr(relic, key, value)
        if is_wax:
            setattr(relic, "is_wax", True)
            setattr(relic, "is_melted", False)
            relic.enabled = True
        self.relic_objects.append(relic)
        relic.after_obtained(self)
        return True

    def obtain_relic(self, relic_id: str) -> bool:
        return self.obtain_relic_with_setup(relic_id)

    def transform_relic(self, current_relic: Any, new_relic_id: Any) -> bool:
        from sts2_env.relics.registry import create_relic_by_name

        current_name = getattr(getattr(current_relic, "relic_id", None), "name", str(current_relic))
        new_name = getattr(new_relic_id, "name", str(new_relic_id))
        try:
            index = self.relics.index(current_name)
        except ValueError:
            return False
        self.relics[index] = new_name
        if index < len(self.relic_objects):
            self.relic_objects[index] = create_relic_by_name(new_name)
        else:
            self._ensure_relic_objects()
        return True

    @property
    def is_dead(self) -> bool:
        return self.current_hp <= 0


class RunRngSet:
    """Separate seeded RNG streams for determinism."""

    def __init__(self, master_seed: int):
        self.seed = deterministic_hash_code(str(master_seed))
        player_seed = self.seed + 1
        self.map_rngs: dict[int, Rng] = {}
        self.up_front = Rng(self.seed, "up_front")
        self.shuffle = Rng(self.seed, "shuffle")
        self.unknown_map_point = Rng(self.seed, "unknown_map_point")
        self.combat_card_generation = Rng(self.seed, "combat_card_generation")
        self.combat_potion_generation = Rng(self.seed, "combat_potion_generation")
        self.combat_card_selection = Rng(self.seed, "combat_card_selection")
        self.combat_energy_costs = Rng(self.seed, "combat_energy_costs")
        self.combat_targets = Rng(self.seed, "combat_targets")
        self.monster_ai = Rng(self.seed, "monster_ai")
        self.niche = Rng(self.seed, "niche")
        self.combat_orbs = Rng(self.seed, "combat_orbs")
        self.treasure_room = Rng(self.seed, "treasure_room_relics")
        self.combat_potion = self.combat_potion_generation
        self.rewards = Rng(player_seed, "rewards")
        self.shops = Rng(player_seed, "shops")
        self.transformations = Rng(player_seed, "transformations")

    def get_map_rng(self, act_index: int) -> Rng:
        if act_index not in self.map_rngs:
            self.map_rngs[act_index] = Rng(self.seed, f"act_{act_index + 1}_map")
        return self.map_rngs[act_index]


class RunState:
    """Complete run state, persisted across combats and rooms."""

    def __init__(
        self,
        seed: int = 0,
        ascension_level: int = 0,
        character_id: str = "Ironclad",
    ):
        self.seed = seed
        self.ascension_level = ascension_level
        self.rng = RunRngSet(seed)

        # Player
        self.player = PlayerState(character_id=character_id)
        self.player.run_state = self
        self.player.base_orb_slot_count = get_character(character_id).base_orb_slots
        self.players: list[PlayerState] = [self.player]

        # Act / map state
        self.acts: list[ActConfig] = [get_act_config(i) for i in range(len(ALL_ACTS))]
        self.current_act_index: int = 0
        self.map: ActMap | None = None
        self.visited_map_coords: list[MapCoord] = []
        self.act_floor: int = 0
        self.total_floor: int = 0

        # Event tracking
        self.visited_event_ids: set[str] = set()
        self.extra_fields: dict[str, Any] = {}
        self.modifiers: list[Any] = []

        # Primary-player compatibility aliases.
        self.relics = self.player.relics
        self.relic_grab_bag = self.player.relic_grab_bag

        # Odds systems
        self.unknown_odds = UnknownMapPointOdds()
        self.card_rarity_odds = CardRarityOdds(ascension_level)
        self.potion_reward_odds = PotionRewardOdds()
        self.pending_rewards: list[Any] = []
        self.pending_choice: PendingCardChoice | None = None
        self.enable_deck_choice_requests: bool = False
        self.defer_followup_rewards: bool = False

        # Run state flags
        self.is_over: bool = False
        self.player_won: bool = False
        self.has_double_boss: bool = False

    @property
    def current_act(self) -> ActConfig:
        return self.acts[self.current_act_index]

    def add_player(self, player: PlayerState) -> PlayerState:
        if any(existing.player_id == player.player_id for existing in self.players):
            raise ValueError(f"Duplicate player_id {player.player_id}")
        player.run_state = self
        self.players.append(player)
        return player

    def get_player(self, player_id: int) -> PlayerState:
        for player in self.players:
            if player.player_id == player_id:
                return player
        raise KeyError(f"Unknown player_id {player_id}")

    def resolve_pending_choice(self, choice_index: int | None) -> bool:
        choice = self.pending_choice
        if choice is None:
            return False

        if choice.is_multi:
            if choice_index is None:
                if not choice.can_confirm():
                    return False
                selected_cards = choice.selected_cards
                self.pending_choice = None
                choice.resolver(selected_cards)
                return True
            return choice.toggle(choice_index)

        selected_cards: list[CardInstance] = []
        if choice_index is None:
            if not choice.allow_skip:
                return False
        else:
            if choice_index < 0 or choice_index >= len(choice.options):
                return False
            selected_cards = [choice.options[choice_index].card]
        self.pending_choice = None
        choice.resolver(selected_cards)
        return True

    def initialize_run(self) -> None:
        """Set up a new run: apply ascension, generate first map."""
        self._apply_ascension_effects()
        for modifier in self.modifiers:
            on_run_created = getattr(modifier, "on_run_created", None)
            if callable(on_run_created):
                on_run_created(self)
        for player in self.players:
            player.populate_relic_grab_bag()
        for modifier in self.modifiers:
            modifier.after_relic_grab_bags_populated(self)
        self.generate_map()
        self._fire_after_act_entered()

    def _apply_ascension_effects(self) -> None:
        """Apply all ascension effects matching AscensionManager.ApplyEffectsTo
        and the runtime checks throughout the C# source.

        Ascension levels (enum order):
          0 = None
          1 = SwarmingElites   — 1.6x elite map points (handled in map gen)
          2 = WearyTraveler    — Neow heals 80% of missing HP instead of 100%
          3 = Poverty          — Starting gold × 0.75
          4 = TightBelt        — -1 max potion slot
          5 = AscendersBane    — Add Ascender's Bane curse to deck
          6 = Gloom            — Map gen effects (handled in generator.py)
          7 = Scarcity         — Card upgrade rate halved (0.125 instead of 0.25)
          8 = ToughEnemies     — Higher monster HP (handled per-monster)
          9 = DeadlyEnemies    — Higher monster damage (handled per-monster)
         10 = DoubleBoss       — Two boss fights per act
        """
        asc = self.ascension_level

        # A1: SwarmingElites — 1.6x elites on map (handled in map generator)
        # A2: WearyTraveler — Neow heal reduction (handled in event)

        # A3: Poverty — gold multiplier 0.75x
        if asc >= 3:
            self.player.gold = round(self.player.gold * 0.75)

        # A4: TightBelt — 1 fewer potion slot
        if asc >= 4:
            self.player.max_potion_slots = max(0, self.player.max_potion_slots - 1)

        # A5: AscendersBane — add curse to starting deck
        if asc >= 5:
            from sts2_env.cards.base import CardInstance
            from sts2_env.core.enums import CardId, CardType, TargetType, CardRarity as CR
            curse = CardInstance(
                card_id=CardId.ASCENDERS_BANE,
                cost=0,
                card_type=CardType.CURSE,
                target_type=TargetType.NONE,
                rarity=CR.CURSE,
                keywords=frozenset({"unplayable", "ethereal"}),
                can_be_generated_by_modifiers=False,
            )
            self.player.add_card_instance_to_deck(curse)

        # A7: Scarcity — card upgrade scaling halved (stored for rewards.py)
        # The actual check is: scaling = 0.125 if asc >= 7 else 0.25
        # Already handled in run/rewards.py roll_for_upgrade()

        # A8: ToughEnemies — higher monster HP (handled per-monster via
        #   AscensionHelper.GetValueIfAscension; our monsters use fixed values
        #   for simplicity since we don't have runtime ascension checks yet)

        # A9: DeadlyEnemies — higher monster damage (same as A8)

        # A10: DoubleBoss — two boss fights per act
        self.has_double_boss = asc >= 10

    def generate_map(self) -> None:
        """Generate the map for the current act."""
        act = self.current_act
        spoils_cards = [
            card
            for player in self.players
            for card in player.deck
            if (
                card.card_id == CardId.SPOILS_MAP
                and card.effect_vars.get("spoils_act_index", 1) == self.current_act_index
            )
        ]
        if spoils_cards:
            act_map = generate_spoils_act_map(
                num_rooms=act.num_rooms,
                rng=Rng(self.rng.seed, "spoils_map"),
                ascension_level=self.ascension_level,
                act_index=self.current_act_index,
            )
        else:
            map_rng = self.rng.get_map_rng(self.current_act_index)
            act_map = generate_act_map(
                num_rooms=act.num_rooms,
                rng=map_rng,
                ascension_level=self.ascension_level,
                act_index=self.current_act_index,
            )
        for player in self.players:
            for relic in player.get_relic_objects():
                act_map = relic.modify_generated_map(player, self, act_map, self.current_act_index)
        for player in self.players:
            for modifier in self.modifiers:
                act_map = modifier.modify_generated_map(player, self, act_map, self.current_act_index)
        for player in self.players:
            for relic in player.get_relic_objects():
                act_map = relic.modify_generated_map_late(player, self, act_map, self.current_act_index)
        treasure = next((point for point in act_map.room_points() if point.point_type == MapPointType.TREASURE), None)
        if treasure is not None:
            for card in spoils_cards:
                card.effect_vars["spoils_col"] = treasure.col
                card.effect_vars["spoils_row"] = treasure.row
                treasure.add_quest(card)
        self.map = act_map

    def enter_act(self, act_index: int) -> None:
        """Transition to a new act."""
        self.current_act_index = act_index
        self.visited_map_coords.clear()
        self.act_floor = 0
        self.unknown_odds.reset_to_base()
        self.generate_map()
        self._fire_after_act_entered()

    def _fire_after_act_entered(self) -> None:
        for modifier in self.modifiers:
            modifier.after_act_entered(self)

    def enter_next_act(self) -> bool:
        """Move to the next act. Returns False if run is over (won)."""
        if self.current_act_index >= len(self.acts) - 1:
            self.is_over = True
            self.player_won = True
            return False
        self.enter_act(self.current_act_index + 1)
        return True

    def add_visited_coord(self, coord: MapCoord) -> None:
        self.visited_map_coords.append(coord)
        self.act_floor = coord.row + 1
        self.total_floor += 1

    def get_available_next_coords(self) -> list[MapCoord]:
        """Get coordinates the player can move to from current position."""
        if self.map is None:
            return []

        if not self.visited_map_coords:
            # At start: can go to any first-row room
            if self.map.start_point:
                return [c.coord for c in self.map.start_point.children]
            return [p.coord for p in self.map.get_row(1)]

        last_coord = self.visited_map_coords[-1]
        last_point = self.map.get_point(last_coord)
        if last_point is None:
            return []
        if any(getattr(modifier, "modifier_id", None) == "flight" for modifier in self.modifiers):
            return [point.coord for point in self.map.get_row(last_coord.row + 1)]
        return [c.coord for c in last_point.children]

    def resolve_room_type(self, point_type: MapPointType) -> RoomType:
        """Convert a MapPointType to a RoomType, rolling for Unknown rooms."""
        mapping = {
            MapPointType.SHOP: RoomType.SHOP,
            MapPointType.TREASURE: RoomType.TREASURE,
            MapPointType.REST_SITE: RoomType.REST_SITE,
            MapPointType.MONSTER: RoomType.MONSTER,
            MapPointType.ELITE: RoomType.ELITE,
            MapPointType.BOSS: RoomType.BOSS,
            MapPointType.ANCIENT: RoomType.EVENT,
        }
        if point_type == MapPointType.UNKNOWN:
            if (
                self.current_act_index == 2
                and any(card.card_id == CardId.LANTERN_KEY for player in self.players for card in player.deck)
            ):
                return RoomType.EVENT
            room_types = {RoomType.EVENT, RoomType.MONSTER, RoomType.ELITE, RoomType.TREASURE, RoomType.SHOP}
            for player in self.players:
                for relic in player.get_relic_objects():
                    room_types = relic.modify_unknown_map_point_room_types(player, room_types)
            if room_types == {RoomType.EVENT}:
                return RoomType.EVENT
            blacklist: set[RoomType] = set()
            blacklist.update(
                room_type
                for room_type in (RoomType.MONSTER, RoomType.ELITE, RoomType.TREASURE, RoomType.SHOP)
                if room_type not in room_types
            )
            if RoomType.EVENT not in room_types:
                blacklist.add(RoomType.EVENT)
            return self.unknown_odds.roll(self.rng.unknown_map_point, self, blacklist=blacklist)
        return mapping.get(point_type, RoomType.MONSTER)

    def win_run(self) -> None:
        self.is_over = True
        self.player_won = True

    def lose_run(self) -> None:
        self.is_over = True
        self.player_won = False
