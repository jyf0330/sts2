# Damage Validation Workbench

`sts2-rl-agent` 现在包含一个“杀戮尖塔2伤害计算验证台”，目标是复用仓库现有的 `combat / damage / hooks / powers` 逻辑，做成更适合人工核对和批量回归的工具层，而不是重写一套规则。

如果你要先搞清楚“当前规则到底是什么”，先看 [伤害系统开发使用文档](./DAMAGE_SYSTEM_DEVELOPMENT_GUIDE.md)。本文档更偏向“怎么跑、怎么写 case”。

## 能力概览

- 真实结算：直接走 `CombatState.deal_damage()`、`calculate_damage()`、`apply_damage()`、`modify_block()` 等原链路。
- JSON 适配：把玩家、怪物、Power、Block、动作都描述成 JSON。
- 详细 trace：输出加算、乘算、cap、格挡吸收、HP loss 修正、重定向等步骤。
- 批量校验：从单个 JSON、suite JSON 或目录批量跑 case，并对 `expect` 做部分匹配断言。
- Web 验证台：本地打开页面，手填玩家 / 敌人 / 动作并查看结果。

## 启动 Web 验证台

```bash
PYTHONPATH=. uv run python scripts/run_damage_lab_server.py --host 127.0.0.1 --port 8765
```

打开：

```text
http://127.0.0.1:8765
```

## 批量验证脚本

单个 case：

```bash
PYTHONPATH=. uv run python scripts/validate_damage_cases.py cases/example.json
```

目录模式：

```bash
PYTHONPATH=. uv run python scripts/validate_damage_cases.py cases/
```

suite 模式：

```bash
PYTHONPATH=. uv run python scripts/validate_damage_cases.py suites/act1_damage_suite.json
```

当输入是 suite 或目录时，只要有 case 断言失败，脚本会返回非零退出码。

## Case 结构

```json
{
  "name": "strength-vulnerable-block",
  "seed": 42,
  "character_id": "ironclad",
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

## 敌人描述

两种方式都支持：

1. 手填属性
```json
{
  "monster_id": "TEST_DUMMY",
  "max_hp": 50,
  "current_hp": 50
}
```

2. 复用仓库怪物工厂
```json
{
  "monster_factory": "create_big_dummy"
}
```

`/api/catalog` 会暴露当前仓库可用的 `monster_factories`、`powers`、`value_props`。

## 当前支持的操作

### `deal_damage`

```json
{
  "type": "deal_damage",
  "actor": "player",
  "target": "enemy:0",
  "base_damage": 10,
  "props": ["MOVE"]
}
```

### `gain_block`

```json
{
  "type": "gain_block",
  "actor": "player",
  "base_block": 5,
  "props": ["MOVE"]
}
```

### `apply_power`

```json
{
  "type": "apply_power",
  "actor": "enemy:0",
  "power_id": "WEAK",
  "amount": 2,
  "applier": "player"
}
```

## Suite 结构

```json
{
  "cases": [
    {
      "name": "expected-pass",
      "player": { "max_hp": 80, "current_hp": 80 },
      "enemies": [{ "monster_id": "TEST_DUMMY", "max_hp": 20, "current_hp": 20 }],
      "operations": [
        {
          "type": "deal_damage",
          "actor": "player",
          "target": "enemy:0",
          "base_damage": 6,
          "props": ["MOVE", "UNPOWERED"]
        }
      ],
      "expect": {
        "operations": [
          {
            "damage_events": [
              {
                "damage_trace": { "final_damage": 6 },
                "application": { "hp_lost": 6 }
              }
            ]
          }
        ]
      }
    }
  ]
}
```

`expect` 采用“部分匹配”语义，只要你关心的字段对得上就算通过。
