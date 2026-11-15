# NeuroHive 1.0 — Self-Replication Simulation & Live Digital Twin

**Experimental intensity:** 35%  
**Runtime:** Python 3.10+  
**Dependencies:** Python standard library only (including `tkinter` and `http.server` for live visuals)  
**Purpose:** A reproducible, resource-constrained, multi-agent simulation in which an original hive plans, manufactures, assembles, verifies and commissions successor hives — now with a live desktop GUI, interactive web dashboard, spatial factory floor, maintenance/repair mechanics, resource strategies, and parametric sweep benchmarks.

> This is a software research model. It does not control real machinery and does not demonstrate physical self-replication.

## What it simulates

- **NeuroCore:** replication planning, digital-twin blueprint tracking, and phase control.
- **MaterialCore:** inventory, bill of materials, material conservation, and planning strategies (`standard`, `reserved_bom`, `auto_resupply`).
- **SwarmCore:** role-specialised agents (`FAB-01/02`, `SYS-01`, `ASM-01/02`, `QA-01`, and optional `MNT-01` maintenance/repair robot) operating across a 12×8 spatial factory grid.
- **FabricationCore:** component production across dedicated stations (`DEPOT`, `FAB_BAY`, `SYS_LAB`, `ASM_DOCK`, `QA_CELL`, `HIVE_PAD`, `CHARGER`) with energy and travel physics.
- **HiveNet:** task dispatch, live telemetry snapshots, and filterable coordination event traces.
- **Verification:** self-test and safety-validation gates before commissioning.
- **Reliability & Fault Injection:** deterministic recoverable delays (`--fault-rate`), permanent hardware faults (`--permanent-fault-rate`) repaired by `MNT-01` or internal diagnostics, and live interactive fault/supply injection.
- **Lineage:** NH-A builds NH-B; NH-B can build NH-C, and so on (with multi-generation auto-resupply support).

The model deliberately treats motors, batteries, compute modules and electronic assemblies as supplied specialist inputs. It does not pretend that a desktop-scale hive can manufacture semiconductors or battery cells.

## Quick start

### 1. Live Interactive Web Dashboard (Browser)

```powershell
python neurohive.py --web
```

Opens a live interactive dashboard at `http://127.0.0.1:8765/` featuring:
- 60fps HTML5 `<canvas>` 2D Spatial Factory Floor with interpolated agent motion, animated logistics links, particle bursts, and hover telemetry tooltips.
- Interactive SVG Hive Lineage graph and 13-cell Digital Twin Blueprint matrix.
- Real-time multi-series telemetry chart (`Busy %`, `Stock %`, `Avg Energy %`).
- Live playback (`Play/Pause`, `Step +1`, `Step +5`, speed slider), fault injection, BOM supply drops, JSON export, and Parameter Sweep Benchmark dialog.

### 2. Native Desktop GUI (Tkinter)

```powershell
python neurohive.py --gui
```

Launches the standalone dark-theme desktop studio (`neurohive_gui.py`) with live 2D spatial canvas, lineage/blueprint inspector, Material Core ledger, SwarmCore roster, filterable event trace, and sweep chart modal.

### 3. CLI Simulation & Benchmarks

```powershell
# Default two successive replications (NH-A -> NH-B -> NH-C)
python neurohive.py --generations 2 --seed 42 --fault-rate 0.01

# One replication: A builds B
python neurohive.py --generations 1 --fault-rate 0

# Multi-generation run with auto-resupply and spatial travel physics
python neurohive.py --generations 4 --resource-strategy auto_resupply --travel-ticks

# Multi-seed fault-rate sweep benchmark (0%, 1%, 5%, 10%, 20%)
python neurohive.py --sweep --generations 2
```

`--fault-rate` is the probability of a recoverable delay on each active agent tick. `--permanent-fault-rate` adds permanent offline faults that require `MNT-01` or multi-tick recovery.

## Tests

```bash
python -m unittest discover -s tests -v
```

Thirteen unit tests cover core replication, determinism, material conservation, invalid parameter rejection, fault recovery, `snapshot()` schema, resource strategies (`reserved_bom`, `auto_resupply`, manual `resupply`), maintenance repair, spatial travel physics, parameter sweeps, the HTTP Web Dashboard API, and Tkinter GUI initialization.

## Model architecture

```text
NeuroHive_1_0
├── neurohive.py         # Core simulation engine, spatial stations, sweep runner & CLI
├── neurohive_gui.py     # Native Tkinter desktop GUI with live spatial & blueprint visuals
├── neurohive_web.py     # Thread-safe local HTTP server & JSON API for the web dashboard
├── dashboard.html       # Responsive dark-mode web UI (Canvas, SVG lineage, telemetry charts)
└── tests/
    └── test_neurohive.py
```

## Experimental assumptions and limitations

- Time is discrete and measured in abstract simulation ticks, not hours.
- Task durations and material quantities are illustrative model parameters, not vendor-validated engineering estimates.
- Agents are role-specialised; spatial coordinates and travel ticks model coarse 2D station transitions rather than realistic robot kinematics or collision physics.
- Safety validation is represented as a required stage, not a certified safety case.
