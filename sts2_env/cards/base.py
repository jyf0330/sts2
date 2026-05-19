"""Card instance dataclass and factory."""

from __future__ import annotations

from dataclasses import dataclass, field

from sts2_env.core.enums import CardId, CardTag, CardType, TargetType, CardRarity


_STRIKE_TAG_CARD_IDS = {
    CardId.ADAPTIVE_STRIKE,
    CardId.ASHEN_STRIKE,
    CardId.BLIGHT_STRIKE,
    CardId.FOCUSED_STRIKE_CARD,
    CardId.LEADING_STRIKE,
    CardId.METEOR_STRIKE,
    CardId.MINION_STRIKE,
    CardId.MOMENTUM_STRIKE,
    CardId.PERFECTED_STRIKE,
    CardId.POMMEL_STRIKE,
    CardId.SCULPTING_STRIKE,
    CardId.SEEKER_STRIKE,
    CardId.SETUP_STRIKE_CARD,
    CardId.SHINING_STRIKE,
    CardId.SOLAR_STRIKE,
    CardId.STRIKE_DEFECT,
    CardId.STRIKE_IRONCLAD,
    CardId.STRIKE_NECROBINDER,
    CardId.STRIKE_REGENT,
    CardId.STRIKE_SILENT,
    CardId.TWIN_STRIKE,
    CardId.ULTIMATE_STRIKE,
}

_DEFEND_TAG_CARD_IDS = {
    CardId.DEFEND_DEFECT,
    CardId.DEFEND_IRONCLAD,
    CardId.DEFEND_NECROBINDER,
    CardId.DEFEND_REGENT,
    CardId.DEFEND_SILENT,
    CardId.ULTIMATE_DEFEND,
}

_OSTY_ATTACK_TAG_CARD_IDS = {
    CardId.BONE_SHARDS,
    CardId.FLATTEN,
    CardId.HIGH_FIVE,
    CardId.POKE,
    CardId.PROTECTOR,
    CardId.RATTLE,
    CardId.RIGHT_HAND_HAND,
    CardId.SNAP,
    CardId.SQUEEZE,
    CardId.SWEEPING_GAZE,
    CardId.UNLEASH,
}

_MINION_TAG_CARD_IDS = {
    CardId.MINION_DIVE_BOMB,
    CardId.MINION_SACRIFICE,
    CardId.MINION_STRIKE,
}

_SHIV_TAG_CARD_IDS = {
    CardId.KNIFE_TRAP,
    CardId.SHIV,
}

_CANONICAL_TAGS_BY_CARD_ID = {
    **{card_id: {CardTag.STRIKE} for card_id in _STRIKE_TAG_CARD_IDS},
    **{card_id: {CardTag.DEFEND} for card_id in _DEFEND_TAG_CARD_IDS},
    **{card_id: {CardTag.OSTY_ATTACK} for card_id in _OSTY_ATTACK_TAG_CARD_IDS},
    **{card_id: {CardTag.MINION} for card_id in _MINION_TAG_CARD_IDS},
    **{card_id: {CardTag.SHIV} for card_id in _SHIV_TAG_CARD_IDS},
}
_CANONICAL_TAGS_BY_CARD_ID[CardId.MINION_STRIKE] = {CardTag.MINION, CardTag.STRIKE}

_TAG_ALIASES = {
    "strike": CardTag.STRIKE,
    "defend": CardTag.DEFEND,
    "minion": CardTag.MINION,
    "osty_attack": CardTag.OSTY_ATTACK,
    "shiv": CardTag.SHIV,
}

_SELF_MUTATING_DAMAGE_BASES = {
    CardId.CLAW: (3, 4),
    CardId.KINGLY_PUNCH: (8, 8),
    CardId.MAUL: (5, 6),
    CardId.RAMPAGE: (9, 9),
    CardId.THE_SCYTHE: (13, 13),
    CardId.THRASH: (4, 6),
}

_SELF_MUTATING_BLOCK_BASES = {
    CardId.GENETIC_ALGORITHM: (1, 1),
}


def increase_base_damage(card: CardInstance, amount: int) -> None:
    card.base_damage = (card.base_damage or 0) + amount
    if "damage" in card.effect_vars:
        card.effect_vars["damage"] += amount


def increase_base_block(card: CardInstance, amount: int) -> None:
    card.base_block = (card.base_block or 0) + amount
    if "block" in card.effect_vars:
        card.effect_vars["block"] += amount


def capture_self_mutating_card_progress(card: CardInstance) -> dict[str, int]:
    progress: dict[str, int] = {}
    upgraded_index = 1 if card.upgraded else 0
    damage_bases = _SELF_MUTATING_DAMAGE_BASES.get(card.card_id)
    if damage_bases is not None and card.base_damage is not None:
        progress["damage"] = card.base_damage - damage_bases[upgraded_index]
    block_bases = _SELF_MUTATING_BLOCK_BASES.get(card.card_id)
    if block_bases is not None:
        current_block = card.effect_vars.get("block", card.base_block or 0)
        progress["block"] = current_block - block_bases[upgraded_index]
    return progress


def restore_self_mutating_card_progress(card: CardInstance, progress: dict[str, int]) -> None:
    damage_bonus = progress.get("damage", 0)
    if damage_bonus:
        increase_base_damage(card, damage_bonus)
    block_bonus = progress.get("block", 0)
    if block_bonus:
        increase_base_block(card, block_bonus)


@dataclass
class CardInstance:
    """A single card instance in combat."""

    card_id: CardId
    cost: int
    card_type: CardType
    target_type: TargetType
    rarity: CardRarity = CardRarity.BASIC
    base_damage: int | None = None
    base_block: int | None = None
    upgraded: bool = False
    keywords: frozenset[str] = frozenset()
    tags: frozenset[str] = frozenset()
    can_be_generated_in_combat: bool = True
    can_be_generated_by_modifiers: bool = True
    enchantments: dict[str, int] = field(default_factory=dict)
    effect_vars: dict[str, int] = field(default_factory=dict)
    instance_id: int = 0
    # X-cost and Star-cost support
    has_energy_cost_x: bool = False
    star_cost: int = 0
    has_star_cost_x: bool = False
    # Persistent per-combat state (e.g. Rampage extra damage, Claw buff)
    combat_vars: dict[str, object] = field(default_factory=dict)
    # Original cost for cost-modification tracking
    original_cost: int | None = None
    single_turn_retain: bool = False
    bound: bool = False
    base_replay_count: int = 0

    def __post_init__(self):
        if self.original_cost is None:
            self.original_cost = self.cost
        tags = {
            _TAG_ALIASES.get(tag, tag)
            for tag in self.tags
        }
        tags.update(_CANONICAL_TAGS_BY_CARD_ID.get(self.card_id, set()))
        self.tags = frozenset(tags)

    @property
    def is_attack(self) -> bool:
        return self.card_type == CardType.ATTACK

    @property
    def is_skill(self) -> bool:
        return self.card_type == CardType.SKILL

    @property
    def is_power(self) -> bool:
        return self.card_type == CardType.POWER

    @property
    def is_status(self) -> bool:
        return self.card_type == CardType.STATUS

    @property
    def is_curse(self) -> bool:
        return self.card_type == CardType.CURSE

    @property
    def exhausts(self) -> bool:
        return "exhaust" in self.keywords

    @property
    def is_unplayable(self) -> bool:
        return self.cost < 0 or "unplayable" in self.keywords

    @property
    def is_ethereal(self) -> bool:
        return "ethereal" in self.keywords

    @property
    def is_innate(self) -> bool:
        return "innate" in self.keywords

    @property
    def is_retain(self) -> bool:
        return "retain" in self.keywords

    @property
    def is_sly(self) -> bool:
        return "sly" in self.keywords or bool(self.combat_vars.get("sly_this_turn"))

    @property
    def has_tag(self) -> bool:
        return len(self.tags) > 0

    @property
    def is_enchanted(self) -> bool:
        return bool(self.enchantments)

    def has_card_tag(self, tag: str) -> bool:
        return tag in self.tags

    def has_enchantment(self, name: str) -> bool:
        return name in self.enchantments

    def add_enchantment(self, name: str, amount: int = 1) -> None:
        from sts2_env.cards.enchantments import apply_static_enchantment

        apply_static_enchantment(self, name, amount)

    @property
    def is_removable(self) -> bool:
        return "eternal" not in self.keywords

    @property
    def is_shiv(self) -> bool:
        return self.card_id == CardId.SHIV or CardTag.SHIV in self.tags

    @property
    def affliction(self) -> str | None:
        affliction = self.combat_vars.get("_affliction")
        if isinstance(affliction, str):
            return affliction
        if self.bound:
            return "bound"
        return None

    def has_affliction(self, name: str) -> bool:
        return self.affliction == name

    def can_afflict(self, name: str, *, stackable: bool = False) -> bool:
        current = self.affliction
        return current is None or (stackable and current == name)

    def afflict(self, name: str, *, stackable: bool = False) -> bool:
        if not self.can_afflict(name, stackable=stackable):
            return False
        self.combat_vars["_affliction"] = name
        if name == "bound":
            self.bound = True
        return True

    def clear_affliction(self, name: str | None = None) -> None:
        current = self.affliction
        if name is not None and current != name:
            return
        if current == "bound" or name == "bound":
            self.bound = False
        self.combat_vars.pop("_affliction", None)

    def clone(self, new_id: int) -> CardInstance:
        """Create a copy with a new instance_id."""
        return CardInstance(
            card_id=self.card_id,
            cost=self.cost,
            card_type=self.card_type,
            target_type=self.target_type,
            rarity=self.rarity,
            base_damage=self.base_damage,
            base_block=self.base_block,
            upgraded=self.upgraded,
            keywords=self.keywords,
            tags=self.tags,
            can_be_generated_in_combat=self.can_be_generated_in_combat,
            can_be_generated_by_modifiers=self.can_be_generated_by_modifiers,
            enchantments=dict(self.enchantments),
            effect_vars=dict(self.effect_vars),
            instance_id=new_id,
            has_energy_cost_x=self.has_energy_cost_x,
            star_cost=self.star_cost,
            has_star_cost_x=self.has_star_cost_x,
            combat_vars={**self.combat_vars, "_is_clone": 1},
            original_cost=self.original_cost,
            single_turn_retain=self.single_turn_retain,
            bound=self.bound,
            base_replay_count=self.base_replay_count,
        )

    @property
    def should_retain_this_turn(self) -> bool:
        return self.is_retain or self.single_turn_retain

    @property
    def energy_cost(self) -> int:
        return self.cost

    @energy_cost.setter
    def energy_cost(self, value: int) -> None:
        self.cost = value

    def set_temporary_cost_for_turn(self, cost: int) -> None:
        self.combat_vars["_turn_cost_override"] = cost
        self.cost = cost

    def set_temporary_star_cost_for_turn(self, cost: int) -> None:
        self.combat_vars["_turn_star_cost_override"] = cost

    def set_temporary_free_this_turn(self) -> None:
        self.set_temporary_cost_for_turn(0)
        self.set_temporary_star_cost_for_turn(0)

    def set_combat_cost(self, cost: int) -> None:
        self.cost = cost

    def set_combat_star_cost(self, cost: int) -> None:
        self.combat_vars["_combat_star_cost_override"] = cost

    def set_free_this_combat(self) -> None:
        self.set_combat_cost(0)
        self.set_combat_star_cost(0)

    def after_forged(self) -> None:
        """Card lifecycle hook fired after a forge increases this card's damage."""
        return

    def end_of_turn_cleanup(self) -> None:
        self.single_turn_retain = False
        self.bound = False
        if self.combat_vars.get("_affliction") == "bound":
            self.combat_vars.pop("_affliction", None)
        self.combat_vars.pop("sly_this_turn", None)
        if "_turn_cost_override" in self.combat_vars:
            self.combat_vars.pop("_turn_cost_override", None)
            self.cost = self.original_cost if self.original_cost is not None else self.cost
        self.combat_vars.pop("_turn_star_cost_override", None)

    def __repr__(self) -> str:
        name = self.card_id.name
        cost_str = "X" if self.has_energy_cost_x else str(self.cost)
        parts = [f"{name}({cost_str}E"]
        if self.base_damage is not None:
            parts.append(f" {self.base_damage}dmg")
        if self.base_block is not None:
            parts.append(f" {self.base_block}blk")
        if self.upgraded:
            parts.append("+")
        return "".join(parts) + ")"


# Global instance counter for unique IDs
_next_instance_id = 0


def _get_next_id() -> int:
    global _next_instance_id
    _next_instance_id += 1
    return _next_instance_id


def reset_instance_counter() -> None:
    global _next_instance_id
    _next_instance_id = 0
