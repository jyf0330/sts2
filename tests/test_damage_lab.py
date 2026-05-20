"""Tests for the damage validation workbench."""

from __future__ import annotations

from sts2_env.damage_lab import validate_case, validate_suite
from sts2_env.damage_lab.web import dispatch_request, render_index_html


def test_validate_case_reports_real_damage_pipeline_trace() -> None:
    case = {
        "name": "strength-vulnerable-block",
        "seed": 42,
        "player": {
            "max_hp": 80,
            "current_hp": 80,
            "powers": [
                {"id": "STRENGTH", "amount": 3},
            ],
        },
        "enemies": [
            {
                "monster_id": "TEST_DUMMY",
                "max_hp": 50,
                "current_hp": 50,
                "block": 5,
                "powers": [
                    {"id": "VULNERABLE", "amount": 2},
                ],
            }
        ],
        "operations": [
            {
                "type": "deal_damage",
                "actor": "player",
                "target": "enemy:0",
                "base_damage": 10,
                "props": ["MOVE"],
            }
        ],
    }

    result = validate_case(case)

    operation = result["operations"][0]
    damage_event = operation["damage_events"][0]
    trace = damage_event["damage_trace"]
    application = damage_event["application"]

    assert trace["base_damage"] == 10
    assert trace["final_damage"] == 19
    assert trace["additive"] == [
        {
            "source_type": "power",
            "source_id": "STRENGTH",
            "owner": "player",
            "delta": 3,
            "before": 10.0,
            "after": 13.0,
        }
    ]
    assert trace["multiplicative"] == [
        {
            "source_type": "power",
            "source_id": "VULNERABLE",
            "owner": "enemy:0",
            "multiplier": 1.5,
            "before": 13.0,
            "after": 19.5,
        }
    ]
    assert application["target"] == "enemy:0"
    assert application["block_before"] == 5
    assert application["blocked"] == 5
    assert application["hp_before"] == 50
    assert application["hp_after"] == 36
    assert application["hp_lost"] == 14
    assert result["final_state"]["enemies"][0]["current_hp"] == 36


def test_validate_case_reports_real_block_pipeline_trace() -> None:
    case = {
        "name": "dexterity-frail-block",
        "seed": 7,
        "player": {
            "max_hp": 80,
            "current_hp": 80,
            "powers": [
                {"id": "DEXTERITY", "amount": 2},
                {"id": "FRAIL", "amount": 2},
            ],
        },
        "enemies": [],
        "operations": [
            {
                "type": "gain_block",
                "actor": "player",
                "base_block": 5,
                "props": ["MOVE"],
            }
        ],
    }

    result = validate_case(case)

    operation = result["operations"][0]
    trace = operation["block_trace"]

    assert trace["base_block"] == 5
    assert trace["final_block"] == 5
    assert trace["additive"] == [
        {
            "source_type": "power",
            "source_id": "DEXTERITY",
            "owner": "player",
            "delta": 2,
            "before": 5.0,
            "after": 7.0,
        }
    ]
    assert trace["multiplicative"] == [
        {
            "source_type": "power",
            "source_id": "FRAIL",
            "owner": "player",
            "multiplier": 0.75,
            "before": 7.0,
            "after": 5.25,
        }
    ]
    assert operation["applied_block"] == 5
    assert result["final_state"]["player"]["block"] == 5


def test_validate_suite_reports_passes_and_mismatches() -> None:
    suite = {
        "cases": [
            {
                "name": "expected-pass",
                "player": {"max_hp": 80, "current_hp": 80},
                "enemies": [
                    {"monster_id": "TEST_DUMMY", "max_hp": 20, "current_hp": 20},
                ],
                "operations": [
                    {
                        "type": "deal_damage",
                        "actor": "player",
                        "target": "enemy:0",
                        "base_damage": 6,
                        "props": ["MOVE", "UNPOWERED"],
                    }
                ],
                "expect": {
                    "operations": [
                        {
                            "damage_events": [
                                {
                                    "damage_trace": {"final_damage": 6},
                                    "application": {"hp_lost": 6},
                                }
                            ]
                        }
                    ]
                },
            },
            {
                "name": "expected-fail",
                "player": {"max_hp": 80, "current_hp": 80},
                "enemies": [
                    {"monster_id": "TEST_DUMMY", "max_hp": 20, "current_hp": 20},
                ],
                "operations": [
                    {
                        "type": "deal_damage",
                        "actor": "player",
                        "target": "enemy:0",
                        "base_damage": 6,
                        "props": ["MOVE", "UNPOWERED"],
                    }
                ],
                "expect": {
                    "operations": [
                        {
                            "damage_events": [
                                {
                                    "damage_trace": {"final_damage": 9},
                                }
                            ]
                        }
                    ]
                },
            },
        ]
    }

    report = validate_suite(suite)

    assert report["summary"] == {"total": 2, "passed": 1, "failed": 1}
    assert report["cases"][0]["passed"] is True
    assert report["cases"][1]["passed"] is False
    assert report["cases"][1]["mismatches"] == [
        {
            "path": "operations[0].damage_events[0].damage_trace.final_damage",
            "expected": 9,
            "actual": 6,
        }
    ]


def test_web_dispatch_serves_html_and_validate_api() -> None:
    html = render_index_html()
    assert "伤害验证台" in html
    assert "策划验证" in html
    assert "技术调试" in html
    assert "planner-view" in html
    assert "tech-view" in html
    assert "hero-character" in html
    assert "run-button" in html
    assert "tech-input-json" in html
    assert "tech-output-json" in html
    assert "tech-diff-output" in html
    assert "batch-suite-json" in html
    assert 'fetch("api/catalog")' in html
    assert 'fetch("api/validate"' in html
    assert "r-final-damage" in html
    assert "r-steps" in html
    assert "预设用例" in html
    assert "copy-button" in html
    assert "计算过程" in html

    status, headers, body = dispatch_request(
        "POST",
        "/api/validate",
        {
            "player": {"max_hp": 80, "current_hp": 80},
            "enemies": [{"monster_id": "TEST_DUMMY", "max_hp": 20, "current_hp": 20}],
            "operations": [
                {
                    "type": "deal_damage",
                    "actor": "player",
                    "target": "enemy:0",
                    "base_damage": 6,
                    "props": ["MOVE", "UNPOWERED"],
                }
            ],
        },
    )

    assert status == 200
    assert headers["Content-Type"] == "application/json; charset=utf-8"
    assert body["operations"][0]["damage_events"][0]["damage_trace"]["final_damage"] == 6


def test_web_dispatch_supports_suite_validation() -> None:
    status, headers, body = dispatch_request(
        "POST",
        "/api/validate",
        {
            "cases": [
                {
                    "name": "suite-pass",
                    "player": {"max_hp": 80, "current_hp": 80},
                    "enemies": [{"monster_id": "TEST_DUMMY", "max_hp": 20, "current_hp": 20}],
                    "operations": [
                        {
                            "type": "deal_damage",
                            "actor": "player",
                            "target": "enemy:0",
                            "base_damage": 6,
                            "props": ["MOVE", "UNPOWERED"],
                        }
                    ],
                    "expect": {
                        "operations": [
                            {
                                "damage_events": [
                                    {"damage_trace": {"final_damage": 6}, "application": {"hp_lost": 6}}
                                ]
                            }
                        ]
                    },
                }
            ]
        },
    )

    assert status == 200
    assert headers["Content-Type"] == "application/json; charset=utf-8"
    assert body["summary"] == {"total": 1, "passed": 1, "failed": 0}
    assert body["cases"][0]["passed"] is True


def test_web_dispatch_exposes_catalog() -> None:
    status, headers, body = dispatch_request("GET", "/api/catalog")

    assert status == 200
    assert headers["Content-Type"] == "application/json; charset=utf-8"
    assert "Ironclad" in body["character_ids"]
    assert "DASH" in body["card_ids"]
    assert "BURNING_BLOOD" in body["relic_ids"]
    assert "STRENGTH" in body["powers"]
    assert "MOVE" in body["value_props"]
    assert "create_big_dummy" in body["monster_factories"]
    assert "deal_damage" in body["operation_types"]
