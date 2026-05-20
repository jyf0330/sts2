# AGENTS.md

Agents working in this repo follow the rules below.

## Project context

- Project path: /home/ywh/games/sts2-rl-agent
- Project type: library + web tool (RL agent for Slay the Spire 2 simulation, with damage validation workbench)
- Primary tech stack: Python 3.11+ (game simulation, RL environment), HTML/CSS/JS (damage lab UI)

## Workflow: Spec Kit

All development follows the Spec-Driven Development workflow:

1. `/speckit-constitution` — Project principles and governance
2. `/speckit-specify` — Feature specification with user stories and requirements
3. `/speckit-clarify` — Optional: resolve ambiguities before planning
4. `/speckit-plan` — Technical implementation plan
5. `/speckit-tasks` — Ordered, actionable task breakdown
6. `/speckit-implement` — Execute tasks and generate code

## BDD gate

- If `**/BDD-待审核.md` exists anywhere in the repo, implementation is BLOCKED.
- Only human reviewer renames `BDD-待审核.md` → `BDD-已通过.md`.
- Once renamed, the gate is cleared and implementation can proceed.
- While the gate is closed: write or update tests only, do not write implementation code.

## Delivery gates

- `implementation-subagent-template.md`: For multi-module parallel implementation
- `manual-acceptance-template.md`: For human operation verification
- `tester-prompt-template.md`: For automated verification following acceptance doc
- `delivery-gate-ledger-template.md`: Audit trail across all gates

## Quality overlay (UI projects only)

- `/impeccable teach` — Generate DESIGN.md from design context (before spec/plan)
- `/impeccable audit` — Technical quality check (after implement)
- `/impeccable critique` — UX review (after implement)
- `/impeccable polish` — Final design alignment (before delivery)
- Non-UI projects skip quality overlay.

## Rules

- No implementation code before spec approval.
- No implementation code while BDD gate is closed.
- Read existing documentation before proposing changes.
- Commit messages: `<type>: <description>`.
- Do not fabricate information not present in source documents.
- Do not access external sites beyond the project's declared data sources.

## Project-specific

### Damage Lab

- Server: `scripts/run_damage_lab_server.py` (default port 8765)
- Backend: `sts2_env/damage_lab/` (service, web, tracing)
- Frontend: `sts2_env/damage_lab/static/index_dual.html` (dual-view: planner + tech mode)
- Tests: `tests/test_damage_lab.py`
- Do not rewrite the damage calculation core logic (`sts2_env/core/damage.py`, `sts2_env/core/hooks.py`).
- The planner mode exposes no raw JSON; all designer-facing UI uses forms, dropdowns, and Chinese-language results.

### Core simulation

- This is a Slay the Spire 2 RL environment. Core game logic lives in `sts2_env/core/`.
- Cards are in `sts2_env/cards/`, characters in `sts2_env/characters/`, powers in `sts2_env/powers/`.
- Do not modify core simulation logic to accommodate UI requirements — adapt the UI to the simulation.
