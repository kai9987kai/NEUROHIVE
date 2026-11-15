# NeuroHive 1.0 Architecture Note

## Design intent
A local-first, deterministic simulation of successive functional replication with live desktop (`tkinter`) and browser (`http.server` + `dashboard.html`) digital-twin interfaces. Experimental intensity remains anchored at 35%: practical software, logistics, and manufacturing abstractions with explicit safety boundaries.

## State model
The simulation state comprises:
- `Hive`: identity, generation, parent, status, commissioning tick, verified capabilities, and per-hive Digital Twin progress maps (`components_built`, `assembly_progress`, `verification_progress`).
- `Agent`: role, completed task count, busy ticks, 2D grid coordinates (`x`, `y`, `target_x`, `target_y`), assigned station, energy level & expenditure, distance traveled, live `status`, `current_task`, and fault/repair counters.
- `Task`: role requirement, duration, remaining work, phase, station, energy cost per tick, status, assigned agent, and recoverable retries.
- `stock` & `total_resupplied`: conserved quantities for aluminium, polymer, copper, electronics, motors and batteries.
- `events`: append-only event trace for auditability.
- `history`: per-tick telemetry snapshots (`active_agents`, `busy_pct`, `avg_energy`, `stock_pct`, `progress_pct`, fault counts).

## Control loop
Each discrete tick:
1. Stop if complete, failed or tick budget exhausted.
2. Run maintenance/repair logic for any `offline` agents (repaired rapidly by `maintenance` bots or via multi-tick self-recovery).
3. Assign queued tasks to idle agents with matching roles.
4. Consume a task's BOM once at task start (with optional `reserved_bom` pre-checks or `auto_resupply` replenishment).
5. Move agents across the 12×8 station grid (`DEPOT`, `CHARGER`, `FAB_BAY`, `SYS_LAB`, `ASM_DOCK`, `QA_CELL`, `HIVE_PAD`). When `enable_travel_ticks` is enabled, transit consumes travel ticks before task execution.
6. Advance assigned work by one unit unless a recoverable fault or permanent offline fault is injected.
7. Mark completed tasks, update the target hive's Digital Twin blueprint, recharge idle agents, and record events/telemetry.
8. When a phase is complete, transition manufacturing → assembly → verification → commissioned.
9. A commissioned successor becomes the parent of the next replication.

## Determinism
Primary stochastic fault injection uses a private `random.Random(seed)` instance, while optional permanent faults use a separate `random.Random(seed + 10007)`. Identical inputs and seed produce identical run outcomes, preserving exact baseline determinism when optional modes are disabled.

## Resource model & strategies
The bill of materials is an explicit dictionary in `neurohive.py` (`BOM`, `SINGLE_HIVE_BOM`). Conservation holds across all runs and resupply drops (`material_used + material_remaining == initial_stock + total_resupplied`):
- `standard`: atomic per-task deduction at `_begin_task`.
- `reserved_bom`: validates full `SINGLE_HIVE_BOM` availability before starting a successor hive, failing fast rather than stalling mid-build.
- `auto_resupply`: orders `1x SINGLE_HIVE_BOM` shipments automatically whenever stock falls below requirements, enabling multi-generation studies.

## Safety boundaries
This is not a machine-control system. There are no hardware drivers, external network-control interfaces, actuator commands, or code-execution-from-model features. Verification is a simulated gate only.
