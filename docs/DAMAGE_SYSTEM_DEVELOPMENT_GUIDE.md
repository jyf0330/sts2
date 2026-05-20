# 伤害系统开发使用文档

本文档基于当前仓库已经实现的伤害逻辑整理，不重新设计规则，也不改核心代码。目标是让程序、策划、测试和后续 AI 都能直接按现有实现接入。

相关源码优先级如下：

- `sts2_env/core/combat.py`
- `sts2_env/core/damage.py`
- `sts2_env/core/hooks.py`
- `sts2_env/core/enums.py`
- `sts2_env/powers/common.py`
- `sts2_env/powers/block_modifiers.py`
- `sts2_env/powers/damage_reactions.py`
- `sts2_env/powers/monster.py`
- `sts2_env/damage_lab/service.py`
- `sts2_env/damage_lab/tracing.py`
- `tests/test_damage.py`
- `tests/test_damage_lab.py`

如果你要先看可验证的 JSON 接入方式，建议先读 [伤害验证台文档](./DAMAGE_VALIDATION_WORKBENCH.md)。

## 1. 伤害从哪里开始

当前有三层入口，按“真实战斗里最常用”的顺序看：

| 入口 | 作用 | 适用场景 |
|---|---|---|
| `CombatState.deal_damage()` | 战斗中的统一伤害入口 | 卡牌、力量、反伤、怪物行为、药水等 |
| `calculate_damage()` | 只算最终伤害值，不直接扣血 | 单测、调试、trace 预估 |
| `apply_damage()` | 把已经算好的伤害真正打到某个生物身上 | 需要走 block / HP / hook 的场景 |
| `calculate_block()` | 只算最终格挡值 | `gain_block`、技能 block 预估 |

### 推荐调用顺序

1. 真实战斗逻辑优先走 `CombatState.deal_damage()`。
2. 只想算数值时用 `calculate_damage()` / `calculate_block()`。
3. 只做最终扣血时用 `apply_damage()`，但要明确它不会帮你重新做完整的加算/乘算。

### `deal_damage()` 的关键行为

- `dealer is None` 时，直接把 `amount` 当作原始伤害应用，不走 `calculate_damage()`。
- `dealer is not None` 时，先进入 `calculate_damage()`，再进入 `apply_damage()`。
- `targets` 支持多目标；返回值是 `list[DamageResult]`，顺序和目标列表一致。
- 当存在攻击上下文时，会把 `AttackContext` 塞进 hook 链，供 `Vigor`、`Accuracy`、`Surrounded` 等逻辑读取。

## 2. 输入哪些数据

### 2.1 核心函数输入

| 参数 | 出现位置 | 含义 |
|---|---|---|
| `base_damage` / `amount` | `calculate_damage()`、`deal_damage()` | 原始伤害值，未经过任何修正 |
| `dealer` | `calculate_damage()`、`apply_damage()`、`deal_damage()` | 伤害发起者，决定 Strength、Weak、部分职业/怪物逻辑是否生效 |
| `target` | `calculate_damage()`、`apply_damage()`、`deal_damage()` | 受伤目标，决定 Vulnerable、Block、Intangible、Buffer 等逻辑是否生效 |
| `props` | 所有伤害/格挡相关入口 | `ValueProp` 位标记，决定这次结算是不是“powered attack”、是不是 `UNBLOCKABLE` 等 |
| `combat` | `calculate_damage()`、`calculate_block()`、`apply_damage()` | 当前战斗状态，负责 hook 派发、攻击上下文、事件记录和多实体遍历 |
| `combat_or_creatures` | `calculate_damage()`、`calculate_block()` | 兼容参数：可以传 `CombatState`，也可以传 `list[Creature]` 的 legacy 路径 |
| `card_source` | `calculate_damage()`、`calculate_block()`、hook 链 | 当前卡牌来源对象；部分力量/灌注/附魔只在有 `card_source` 时生效 |
| `card_play` | `calculate_block()`、hook 链 | 当前卡牌播放 token；用于区分一次播放链里的不同 block 事件 |

### 2.2 Damage Lab JSON 输入

`sts2_env/damage_lab/service.py` 支持的 JSON 输入，当前最小闭环如下：

- `seed`
- `character_id`
- `player`
- `enemies`
- `operations`

其中 `operations` 支持：

- `deal_damage`
- `gain_block`
- `apply_power`

`tests/test_damage_lab.py` 和 `docs/DAMAGE_VALIDATION_WORKBENCH.md` 都在用这套结构。

## 3. 每个字段是什么意思

### 3.1 `ValueProp`

当前用于伤害/格挡的位标记只有这几个：

| 标记 | 含义 | 对伤害的影响 |
|---|---|---|
| `MOVE` | 卡牌动作或怪物动作的伤害/格挡 | 许多“powered”判定都要求它存在 |
| `UNPOWERED` | 非 powered | 会让 Strength / Weak / Vulnerable / Frail 这类 powered 逻辑失效 |
| `UNBLOCKABLE` | 穿透 block | 直接跳过 block 吸收 |
| `SKIP_HURT_ANIM` | 跳过受击动画 | 不改数值，只影响表现 |

当前逻辑里，`props.is_powered_attack()` 等价于：

```python
bool(props & ValueProp.MOVE) and not bool(props & ValueProp.UNPOWERED)
```

### 3.2 `Creature`

伤害系统实际只依赖这些字段：

| 字段 | 含义 |
|---|---|
| `current_hp` | 当前 HP |
| `max_hp` | 最大 HP |
| `block` | 当前格挡值 |
| `powers` | 当前生效的力量/状态/怪物能力 |
| `side` | `PLAYER` 或 `ENEMY`，用于很多侧向判断 |
| `is_player` | 是否是玩家实体 |
| `pet_owner` | 召唤物/宠物的拥有者，部分伤害修正会看它 |
| `owner` | 某些怪物/实体附属关系会用到 |
| `combat_state` | 让 creature 能回到当前战斗上下文 |

### 3.3 `DamageResult`

`apply_damage()` 的返回值是 `DamageResult`，字段如下：

| 字段 | 含义 |
|---|---|
| `target` | 本次实际结算到的目标 |
| `blocked` | 被 block 吸收掉的伤害 |
| `hp_lost` | 真正扣掉的 HP |
| `was_killed` | 这次结算是否致死 |
| `unblocked_damage` | 实际穿过 block 的伤害，通常等于 `hp_lost` |
| `overkill_damage` | 超出目标剩余 HP 的部分 |
| `was_block_broken` | 这次是否把 block 打空 |
| `was_fully_blocked` | 这次是否被完整挡下 |
| `total_damage` | 便捷属性，等于 `blocked + unblocked_damage` |

### 3.4 Damage Lab trace 输出

`validate_case()` 的输出会把伤害拆成两个层次：

| 输出字段 | 含义 |
|---|---|
| `damage_trace.base_damage` | 原始伤害 |
| `damage_trace.additive` | 所有加算来源 |
| `damage_trace.multiplicative` | 所有乘算来源 |
| `damage_trace.caps` | 所有 cap 来源 |
| `damage_trace.final_damage` | 最终伤害 |
| `application.block_before` | 结算前 block |
| `application.blocked` | 实际挡掉多少 |
| `application.remaining_after_block` | 过 block 后剩余多少 |
| `application.hp_before` / `hp_after` | 结算前后 HP |
| `application.hp_lost` | 真正失去多少 HP |
| `application.was_fully_blocked` | 是否完全格挡 |
| `application.was_killed` | 是否致死 |
| `application.redirect` | 如有重定向，会记录来源和去向 |

## 4. 计算流程是什么

### 4.1 伤害计算流程

当前的数值流程是：

1. 取 `base_damage`。
2. 加上 card enchantment 的 additive 修正。
3. 依次遍历所有 power 的 additive 修正。
4. 依次遍历所有 relic 的 additive 修正。
5. 依次遍历所有 power 的 multiplicative 修正。
6. 依次遍历所有 relic 的 multiplicative 修正。
7. 再应用 card enchantment 的 multiplicative 修正。
8. 收集所有 cap，取最小值。
9. 对 cap 取 `min()`。
10. `floor()`，然后 `max(0, ...)`。

### 4.2 应用流程

`apply_damage()` 里还会继续做：

1. 记录伤害 trace。
2. 检查是否允许命中目标。
3. 触发 `before_damage_received`。
4. 先做 block 吸收。
5. 做 `modify_hp_lost_before_osty()`。
6. 如果需要，做目标重定向。
7. 做 `modify_hp_lost_after_osty()`。
8. 扣 HP。
9. 记录 overkill、block broken、fully blocked 等信息。
10. 触发 `after_current_hp_changed`、`after_damage_given`、`after_damage_received`、`kill_creature` 等后续流程。

## 5. 核心公式是什么

当前核心公式可以按下面这段看：

```python
damage = base_damage

damage += enchant_damage_additive(card_source, props)

for each power/relic:
    damage += additive_modifier

for each power/relic:
    damage *= multiplicative_modifier

damage *= enchant_damage_multiplicative(card_source, props)

damage = min(damage, cap)
final_damage = max(0, floor(damage))
```

格挡阶段：

```python
blocked = 0 if unblockable else min(target.block, final_damage)
remaining = final_damage - blocked
```

HP loss 阶段：

```python
remaining = modify_hp_lost_before_osty(remaining, ...)
remaining = modify_hp_lost_after_osty(remaining, ...)
hp_lost = target.lose_hp(remaining)
overkill = max(0, remaining - hp_lost)
```

## 6. 元素克制怎么参与计算

当前实现里，**没有独立的元素字段、元素倍率表或元素克制表**。

也就是说：

- `ValueProp` 不是元素系统。
- `deal_damage()` / `calculate_damage()` 也没有 `element` 入参。
- 伤害不会因为“火 / 冰 / 物理 / 毒”这类元素标签自动乘一层克制倍率。

如果后续需求文档里写了“元素克制参与伤害”，那和当前实现是冲突的。要实现它，必须新增字段和测试，不能靠现有逻辑“自动兼容”。

## 7. 方向块怎么影响伤害

当前实现里，**没有独立的“方向块”字段**。

如果这里说的“方向”是前后/背击相关机制，那么当前真实存在的是这套逻辑：

- `SurroundedPower`
- `BackAttackLeftPower`
- `BackAttackRightPower`

规则是：

- `SurroundedPower` 记录一个 `facing` 状态。
- 如果攻击者带有与当前朝向相反的 `BackAttack` 标记，就会获得 `1.5x` 伤害倍率。
- 这是一条**乘算修正**，不是 block。
- `facing` 默认是向右，且会在选择目标时根据卡牌或药水目标更新。

换句话说：

- **有方向伤害**
- **没有方向 block**

如果你原本想找的是“某种方向格挡减伤”，当前代码里没有。

## 8. 职业差异怎么影响伤害

当前伤害管线本身**不直接按 `character_id` 乘倍率**。

职业差异的影响主要是间接出现的：

1. 不同职业的卡牌池不同。
2. 不同职业的卡牌会放出不同的 `card_source`、tag、`effect_vars`。
3. 不同职业的职业专属力量会进入同一条通用伤害管线。
4. 某些效果只对特定牌型生效，比如 Shiv、Strike、Attack、Monster Move 等。

所以当前结论是：

- **伤害公式是通用的**
- **职业差异来自输入内容，而不是核心公式分支**

这也是为什么在文档和测试里，职业差异应当通过“卡牌/力量/遗物/怪物行为”去验证，而不是新增一个“职业伤害倍率”假设。

## 9. 最终结果怎么输出

### 9.1 运行时输出

`CombatState.deal_damage()` 返回的是 `list[DamageResult]`。

单目标时，这个列表通常只有一个元素；多目标时会有多个元素。

`DamageResult` 里最常看的字段是：

- `blocked`
- `hp_lost`
- `was_killed`
- `unblocked_damage`
- `overkill_damage`
- `was_block_broken`
- `was_fully_blocked`

### 9.2 Damage Lab 输出

`validate_case()` 会返回：

- `operations`
- `final_state`

其中每个 damage 操作会带：

- `damage_events`
- `block_trace`
- `application`

这套输出特别适合做回归测试，因为它能区分：

- 算数对不对
- block 先后顺序对不对
- HP loss 修正对不对
- 重定向是否发生
- 最终状态是否一致

## 10. 开发时怎么写测试用例验证

建议按下面四层写，越靠前越轻量：

| 测试层 | 适用问题 | 推荐文件 |
|---|---|---|
| 纯数值测试 | 只验证公式 | `tests/test_damage.py` |
| hook / 状态测试 | 需要 block、反伤、致死、重定向 | `tests/test_damage.py`、`tests/test_powers.py` |
| JSON 接入测试 | 验证 damage lab 的输入输出契约 | `tests/test_damage_lab.py` |
| 真实卡牌回归 | 验证某张牌的完整伤害流程 | 对应角色/卡牌的 parity tests |

### 10.1 推荐测试写法

1. 先写一个“基准 case”，不带任何修正。
2. 再写一个只引入单一修正的 case，比如只加 `STRENGTH` 或只加 `VULNERABLE`。
3. 再写一个组合 case，确认加算、乘算、block 顺序没有变。
4. 最后写边界 case：
   - `UNPOWERED`
   - `UNBLOCKABLE`
   - 0 伤害
   - 负数修正后被 clamp 到 0
   - 致死
   - 完全格挡
   - 背击 / `Surrounded`

### 10.2 建议断言什么

至少断言这三类结果：

- 数值结果：`final_damage`、`blocked`、`hp_lost`
- 状态结果：`current_hp`、`block`、`is_dead`
- 顺序结果：trace 里的 `additive` / `multiplicative` 顺序

### 10.3 一条最小单测模板

```python
def test_strength_and_vulnerable(simple_combat):
    player = simple_combat.player
    enemy = simple_combat.enemies[0]
    player.apply_power(PowerId.STRENGTH, 3)
    enemy.apply_power(PowerId.VULNERABLE, 2)

    dmg = calculate_damage(10, player, enemy, ValueProp.MOVE, simple_combat)

    assert dmg == 19
```

### 10.4 一条 Damage Lab 模板

```python
def test_damage_lab_case():
    case = {
        "name": "strength-vulnerable-block",
        "seed": 42,
        "character_id": "Ironclad",
        "player": {
            "max_hp": 80,
            "current_hp": 80,
            "block": 0,
            "powers": [
                {"id": "STRENGTH", "amount": 3}
            ],
            "relics": []
        },
        "enemies": [
            {
                "monster_id": "TEST_DUMMY",
                "max_hp": 50,
                "current_hp": 50,
                "block": 5,
                "powers": [
                    {"id": "VULNERABLE", "amount": 2}
                ]
            }
        ],
        "operations": [
            {
                "type": "deal_damage",
                "actor": "player",
                "target": "enemy:0",
                "base_damage": 10,
                "props": ["MOVE"]
            }
        ]
    }

    result = validate_case(case)

    assert result["operations"][0]["damage_events"][0]["damage_trace"]["final_damage"] == 19
    assert result["final_state"]["enemies"][0]["current_hp"] == 36
```

## 11. 可复制的 JSON 示例

### 11.1 单个 case

下面这个 case 可以直接喂给 `validate_case()`，也可以放进 suite 里：

```json
{
  "name": "strength-vulnerable-block",
  "seed": 42,
  "character_id": "Ironclad",
  "player": {
    "max_hp": 80,
    "current_hp": 80,
    "block": 0,
    "powers": [
      { "id": "STRENGTH", "amount": 3 }
    ],
    "relics": []
  },
  "enemies": [
    {
      "monster_id": "TEST_DUMMY",
      "max_hp": 50,
      "current_hp": 50,
      "block": 5,
      "powers": [
        { "id": "VULNERABLE", "amount": 2 }
      ]
    }
  ],
  "operations": [
    {
      "type": "deal_damage",
      "actor": "player",
      "target": "enemy:0",
      "base_damage": 10,
      "props": ["MOVE"]
    }
  ]
}
```

### 11.2 suite 版本，带 expect

`validate_suite()` 会对 `expect` 做部分匹配，适合写回归集：

```json
{
  "cases": [
    {
      "name": "expected-pass",
      "character_id": "Ironclad",
      "player": {
        "max_hp": 80,
        "current_hp": 80,
        "powers": [
          { "id": "STRENGTH", "amount": 3 }
        ]
      },
      "enemies": [
        {
          "monster_id": "TEST_DUMMY",
          "max_hp": 50,
          "current_hp": 50,
          "block": 5,
          "powers": [
            { "id": "VULNERABLE", "amount": 2 }
          ]
        }
      ],
      "operations": [
        {
          "type": "deal_damage",
          "actor": "player",
          "target": "enemy:0",
          "base_damage": 10,
          "props": ["MOVE"]
        }
      ],
      "expect": {
        "operations": [
          {
            "damage_events": [
              {
                "damage_trace": { "final_damage": 19 },
                "application": {
                  "blocked": 5,
                  "hp_lost": 14
                }
              }
            ]
          }
        ]
      }
    }
  ]
}
```

## 12. 已发现的冲突 / 缺口

下面这些点目前和“常见口语化需求”容易混淆，单独列出，避免后续改错方向：

| 主题 | 当前仓库状态 | 结论 |
|---|---|---|
| 元素克制 | 没有独立 `element` 字段，也没有元素倍率表 | 当前**不存在** |
| 方向块 | 没有独立方向 block 字段 | 当前**不存在** |
| 背击/朝向 | `SurroundedPower` + `BackAttackLeft/Right` 存在 | 这是当前唯一的方向伤害逻辑 |
| 职业直伤倍率 | `character_id` 不参与核心伤害公式 | 当前**不存在** |
| `UNPOWERED` | 会跳过 powered 的伤害/格挡修正 | 这是现有核心规则 |
| `UNBLOCKABLE` | 只跳过 block，不影响后续 HP loss 修正 | 这是现有核心规则 |
| Damage Lab schema | 只支持 `deal_damage` / `gain_block` / `apply_power` | 目前没有元素/方向字段 |

### 12.1 如果后续文档和代码冲突，应该以什么为准

以当前代码和测试为准，优先级是：

1. `sts2_env/core/damage.py`
2. `sts2_env/core/hooks.py`
3. `tests/test_damage.py`
4. `tests/test_damage_lab.py`
5. 其他文档

如果以后要补“元素克制”或“方向块”，建议先补测试，再改实现，最后再改文档。
