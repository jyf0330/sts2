# Project Constitution — STS2 RL Agent

## 1. Project Identity

This is a **Slay the Spire 2 RL agent simulation environment** with a companion **damage validation workbench**.

- **Core simulation**: Faithful reimplementation of STS2 combat mechanics in Python
- **RL integration**: Gymnasium-compatible environment for training RL agents
- **Damage lab**: Web-based validation tool for verifying damage calculations

## 2. Core Principles

### 2.1 Simulation fidelity over convenience

The simulation must match the actual game's behavior. When in doubt, verify against decompiled game logic. Never simplify mechanics for implementation convenience.

### 2.2 Backend is the source of truth

All calculations happen in Python (`sts2_env/core/`). The web UI is a thin presentation layer — it must never reimplement game logic.

### 2.3 Designer-first UX for the damage lab

The damage lab's primary audience is designers (策划), not developers. Default mode must be usable without reading JSON or code.

### 2.4 Developer debug capabilities preserved

The technical debug mode retains full JSON I/O, diff, error display, and batch testing. Never degrade the developer toolchain.

### 2.5 Test before commit

All changes to core simulation logic must pass existing tests. UI changes must update corresponding test assertions.

## 3. Tech Stack Constraints

| Layer | Technology | Constraint |
|-------|-----------|------------|
| Simulation | Python 3.11+ | No external game engine dependencies |
| RL Environment | Gymnasium | Must follow Gymnasium API |
| Web UI | Vanilla HTML/CSS/JS | No frameworks (no React/Vue/Svelte) |
| HTTP Server | stdlib `http.server` | No Flask/FastAPI |
| Testing | pytest | All tests in `tests/` |

## 4. Module Boundaries

```
sts2_env/
├── core/        # Combat, damage, creatures, hooks — DO NOT REWRITE
├── cards/       # Card definitions and factories
├── characters/  # Character definitions
├── powers/      # Power definitions
├── relics/      # Relic definitions
├── monsters/    # Monster definitions and AI
├── damage_lab/  # Web UI and validation service (READ-ONLY consumer of core/)
└── orbs/        # Orb system
```

- `damage_lab/` is a **consumer** of `core/` — it observes and validates, never modifies core logic.
- `core/damage.py` and `core/hooks.py` may add tracer hooks, but must not change calculation results.

## 5. Damage Lab UI Rules

- **Planner mode (default)**: No raw JSON visible. Forms, dropdowns, and Chinese-language results only.
- **Tech mode**: Full JSON I/O, diff, error, batch suite — preserved from original.
- **One-screen layout**: Core inputs and results must be visible at 1366×768 without scrolling.
- **State sync**: Planner form ↔ tech JSON must stay in sync bidirectionally.
- **Presets**: At least 3 built-in example cases for quick validation.

## 6. Amendment Process

- Constitution changes require a commit that explains the rationale.
- Core simulation principles (Section 2.1, 2.2) require extra scrutiny — changing them affects all downstream behavior.
- UI rules (Section 5) can be updated more freely as design requirements evolve.

## 7. Governance

- Spec Kit workflow governs all feature development.
- BDD gate blocks implementation until human review approves.
- Delivery gate ledger tracks all gate changes through the development lifecycle.
