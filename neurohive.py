#!/usr/bin/env python3
"""NeuroHive 1.0: deterministic, resource-constrained self-replication simulator.

This is a research simulation, not hardware-control software.
Only standard-library modules are required.
"""
from __future__ import annotations

import argparse
import json
import math
import random
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence


EXPERIMENTAL_INTENSITY = 0.35
VERSION = "1.0.0"

GRID_WIDTH = 12
GRID_HEIGHT = 8

STATIONS: Dict[str, dict] = {
    "DEPOT": {"x": 1.0, "y": 4.0, "label": "Material Depot", "color": "#38bdf8"},
    "CHARGER": {"x": 1.0, "y": 1.2, "label": "Repair & Charge Bay", "color": "#f59e0b"},
    "FAB_BAY": {"x": 4.2, "y": 2.0, "label": "Fabrication Bay", "color": "#22d3ee"},
    "SYS_LAB": {"x": 4.2, "y": 6.0, "label": "Systems & Firmware Lab", "color": "#a78bfa"},
    "ASM_DOCK": {"x": 8.0, "y": 2.6, "label": "Assembly Dock", "color": "#34d399"},
    "QA_CELL": {"x": 8.0, "y": 5.8, "label": "QA Verification Cell", "color": "#fb7185"},
    "HIVE_PAD": {"x": 10.6, "y": 4.0, "label": "Commissioning Pad", "color": "#10b981"},
}

ROLE_HOME_STATION: Dict[str, str] = {
    "fabricator": "FAB_BAY",
    "systems": "SYS_LAB",
    "assembler": "ASM_DOCK",
    "inspector": "QA_CELL",
    "maintenance": "CHARGER",
    "logistics": "DEPOT",
}

ROLE_PREFIXES: Dict[str, str] = {
    "fabricator": "FAB",
    "systems": "SYS",
    "assembler": "ASM",
    "inspector": "QA",
    "maintenance": "MNT",
    "logistics": "LOG",
}

TASK_STATIONS: Dict[str, str] = {
    "frame_module": "FAB_BAY",
    "controller": "SYS_LAB",
    "sensor_pack": "FAB_BAY",
    "actuator_pack": "FAB_BAY",
    "power_unit": "FAB_BAY",
    "fabrication_unit": "FAB_BAY",
    "communications": "SYS_LAB",
    "safety_system": "FAB_BAY",
    "software_image": "SYS_LAB",
    "mechanical_assembly": "ASM_DOCK",
    "electrical_integration": "ASM_DOCK",
    "self_test": "QA_CELL",
    "safety_validation": "QA_CELL",
}

# Each replica is a functional research-hive, not a complete semiconductor factory.
# Specialist electronics, motors, batteries and compute modules are stocked inputs.
BOM = {
    "frame_module": {"aluminium": 30, "polymer": 6},
    "controller": {"electronics": 3, "copper": 2},
    "sensor_pack": {"electronics": 2, "copper": 2},
    "actuator_pack": {"motors": 4, "copper": 4},
    "power_unit": {"battery": 1, "copper": 2},
    "fabrication_unit": {"electronics": 2, "aluminium": 4},
    "communications": {"electronics": 1, "copper": 1},
    "safety_system": {"electronics": 1, "polymer": 1},
    "software_image": {},
}

COMPONENT_DURATIONS = {
    "frame_module": 5,
    "controller": 3,
    "sensor_pack": 2,
    "actuator_pack": 4,
    "power_unit": 2,
    "fabrication_unit": 4,
    "communications": 2,
    "safety_system": 2,
    "software_image": 3,
}

ASSEMBLY_TASKS = ("mechanical_assembly", "electrical_integration")
VERIFICATION_TASKS = ("self_test", "safety_validation")

INITIAL_STOCK = {
    # Enough for two successive replicas with a small reserve.
    "aluminium": 80,
    "polymer": 20,
    "copper": 40,
    "electronics": 28,
    "motors": 10,
    "battery": 3,
}

SINGLE_HIVE_BOM: Dict[str, int] = {}
for _recipe in BOM.values():
    for _mat, _qty in _recipe.items():
        SINGLE_HIVE_BOM[_mat] = SINGLE_HIVE_BOM.get(_mat, 0) + _qty

VALID_RESOURCE_STRATEGIES = ("standard", "reserved_bom", "auto_resupply")


@dataclass
class Agent:
    agent_id: str
    role: str
    tasks_completed: int = 0
    busy_ticks: int = 0
    x: float = 1.0
    y: float = 4.0
    target_x: float = 1.0
    target_y: float = 4.0
    station: str = "DEPOT"
    energy: float = 100.0
    energy_used: float = 0.0
    distance_traveled: float = 0.0
    status: str = "idle"
    current_task: Optional[str] = None
    retries: int = 0
    hard_faults: int = 0
    repair_remaining: int = 0
    fault_flash: bool = False


@dataclass
class Task:
    name: str
    role: str
    duration: int
    remaining: int
    status: str = "queued"
    assigned_to: Optional[str] = None
    retries: int = 0
    phase: str = "manufacturing"
    station: str = "FAB_BAY"
    energy_cost_per_tick: float = 1.2


@dataclass
class Hive:
    hive_id: str
    generation: int
    parent_id: str
    status: str = "planned"
    commissioned_tick: Optional[int] = None
    capabilities: Dict[str, bool] = field(default_factory=dict)
    started_tick: int = 0
    firmware_version: str = "v1.0.0"
    quality_score: float = 100.0
    build_duration_ticks: int = 0
    components_built: Dict[str, bool] = field(default_factory=dict)
    assembly_progress: Dict[str, bool] = field(default_factory=dict)
    verification_progress: Dict[str, bool] = field(default_factory=dict)


class NeuroHiveSimulation:
    """Tick-based multi-agent model of a hive constructing successor hives."""

    def __init__(
        self,
        seed: int = 42,
        max_generations: int = 2,
        fault_rate: float = 0.01,
        max_ticks: int = 2000,
        permanent_fault_rate: float = 0.0,
        resource_strategy: str = "standard",
        enable_travel_ticks: bool = False,
        agent_counts: Optional[Dict[str, int]] = None,
        initial_stock: Optional[Dict[str, int]] = None,
        continuous_mode: bool = False,
        overclock_active: bool = False,
    ):
        if max_generations < 1:
            raise ValueError("max_generations must be at least 1")
        if not 0.0 <= fault_rate <= 1.0:
            raise ValueError("fault_rate must be between 0 and 1")
        if not 0.0 <= permanent_fault_rate <= 1.0:
            raise ValueError("permanent_fault_rate must be between 0 and 1")
        if max_ticks < 1:
            raise ValueError("max_ticks must be positive")
        if resource_strategy not in VALID_RESOURCE_STRATEGIES:
            raise ValueError(
                f"resource_strategy must be one of {VALID_RESOURCE_STRATEGIES}"
            )

        self.rng = random.Random(seed)
        self.aux_rng = random.Random(seed + 10007)
        self.seed = seed
        self.max_generations = max_generations
        self.fault_rate = fault_rate
        self.permanent_fault_rate = permanent_fault_rate
        self.resource_strategy = resource_strategy
        self.enable_travel_ticks = enable_travel_ticks
        self.continuous_mode = bool(continuous_mode)
        self.overclock_active = bool(overclock_active)
        self.max_ticks = max_ticks
        self.tick_count = 0

        base_stock = dict(INITIAL_STOCK)
        if initial_stock is not None:
            for k, v in initial_stock.items():
                if v < 0:
                    raise ValueError(f"initial_stock for {k} cannot be negative")
                base_stock[k] = int(v)
        self.stock = dict(base_stock)
        self.initial_stock = dict(base_stock)
        self.total_resupplied: Dict[str, int] = {k: 0 for k in self.initial_stock}

        self.agents = self._build_agents(agent_counts)
        self.station_temps: Dict[str, float] = {sid: 22.0 for sid in STATIONS}
        self._thermal_warned: set[str] = set()
        self.power_grid: Dict[str, object] = {
            "solar_kw": 22.0,
            "reactor_kw": 26.0,
            "load_kw": 8.0,
            "grid_storage_kwh": 320.0,
            "max_storage_kwh": 500.0,
            "overclock_active": self.overclock_active,
        }
        origin_hive = Hive(
            "NH-A",
            0,
            "origin",
            "commissioned",
            commissioned_tick=0,
            capabilities=self._full_capabilities(),
            started_tick=0,
            firmware_version="v1.0.0",
            quality_score=100.0,
            build_duration_ticks=0,
            components_built={k: True for k in COMPONENT_DURATIONS},
            assembly_progress={k: True for k in ASSEMBLY_TASKS},
            verification_progress={k: True for k in VERIFICATION_TASKS},
        )
        self.hives = [origin_hive]
        self.active_hive_index = 0
        self.current_target: Optional[Hive] = None
        self.phase = "idle"
        self.tasks: List[Task] = []
        self.events: List[dict] = []
        self.history: List[dict] = []
        self.completed_replications = 0
        self.failed = False
        self.failure_reason: Optional[str] = None
        self.total_faults = 0
        self.total_hard_faults = 0
        self.total_energy_used = 0.0
        self._target_retries = 0
        self._target_hard_faults = 0
        self._logistics_cursor = 0
        self._start_next_replication()
        self._record_history()

    @staticmethod
    def _build_agents(agent_counts: Optional[Dict[str, int]]) -> List[Agent]:
        if agent_counts is None:
            specs = [
                ("FAB-01", "fabricator"),
                ("FAB-02", "fabricator"),
                ("SYS-01", "systems"),
                ("ASM-01", "assembler"),
                ("ASM-02", "assembler"),
                ("QA-01", "inspector"),
            ]
        else:
            specs = []
            for role, prefix in ROLE_PREFIXES.items():
                count = int(agent_counts.get(role, 0))
                if count < 0:
                    raise ValueError(f"Agent count for {role} cannot be negative")
                for i in range(1, count + 1):
                    specs.append((f"{prefix}-{i:02d}", role))
            if not specs:
                raise ValueError("Simulation requires at least one agent")

        agents: List[Agent] = []
        for agent_id, role in specs:
            station = ROLE_HOME_STATION.get(role, "DEPOT")
            coords = STATIONS[station]
            agents.append(
                Agent(
                    agent_id=agent_id,
                    role=role,
                    x=coords["x"],
                    y=coords["y"],
                    target_x=coords["x"],
                    target_y=coords["y"],
                    station=station,
                )
            )
        return agents

    @staticmethod
    def _full_capabilities() -> Dict[str, bool]:
        return {
            "planning": True,
            "fabrication": True,
            "assembly": True,
            "sensing": True,
            "communications": True,
            "safety": True,
            "replication": True,
        }

    @staticmethod
    def _format_hive_id(index: int) -> str:
        if index < 26:
            return f"NH-{chr(65 + index)}"
        return f"NH-{index + 1:02d}"

    def _log(self, event: str, **data) -> None:
        self.events.append({"tick": self.tick_count, "event": event, **data})
        if self.continuous_mode and len(self.events) > 2500:
            del self.events[:-1500]

    def _record_history(self) -> None:
        active_agents = sum(
            1
            for a in self.agents
            if a.status in ("working", "moving", "repairing", "delivering")
        )
        avg_energy = (
            sum(a.energy for a in self.agents) / len(self.agents) if self.agents else 0.0
        )
        total_avail = sum(self.initial_stock.values()) + sum(self.total_resupplied.values())
        stock_pct = (
            round(100.0 * sum(self.stock.values()) / total_avail, 1)
            if total_avail > 0
            else 0.0
        )
        peak_temp = max(self.station_temps.values()) if self.station_temps else 22.0
        self.history.append(
            {
                "tick": self.tick_count,
                "active_agents": active_agents,
                "busy_pct": round(100.0 * active_agents / len(self.agents), 1),
                "avg_energy": round(avg_energy, 1),
                "stock_pct": stock_pct,
                "peak_temp_c": round(peak_temp, 1),
                "load_kw": self.power_grid["load_kw"],
                "total_faults": self.total_faults,
                "hard_faults": self.total_hard_faults,
                "progress_pct": self._compute_progress_pct(),
                "phase": self.phase,
            }
        )
        if self.continuous_mode and len(self.history) > 2500:
            del self.history[:-1500]

    def _compute_progress_pct(self) -> float:
        if self.phase == "complete":
            return 100.0
        total_steps = self.max_generations * 3.0
        if total_steps <= 0:
            return 0.0
        phase_base = {"manufacturing": 0.0, "assembly": 1.0, "verification": 2.0}.get(
            self.phase, 0.0
        )
        if self.tasks:
            done_work = sum(t.duration - t.remaining for t in self.tasks)
            total_work = sum(t.duration for t in self.tasks)
            phase_frac = done_work / total_work if total_work > 0 else 0.0
        else:
            phase_frac = 0.0
        if self.continuous_mode:
            return round(min(100.0, 100.0 * (phase_base + phase_frac) / 3.0), 1)
        completed_units = self.completed_replications * 3.0 + phase_base + phase_frac
        return round(min(100.0, 100.0 * completed_units / total_steps), 1)

    def _start_next_replication(self) -> None:
        if self.continuous_mode and self.completed_replications >= self.max_generations:
            self.max_generations = self.completed_replications + 1

        if self.completed_replications >= self.max_generations:
            self.phase = "complete"
            for agent in self.agents:
                agent.status = "idle"
                agent.current_task = None
                agent.fault_flash = False
            return

        if (
            self.continuous_mode or self.resource_strategy == "auto_resupply"
        ) and not self._materials_available(SINGLE_HIVE_BOM):
            self.resupply(
                1,
                reason="continuous_resupply"
                if self.continuous_mode
                else "auto_resupply",
            )

        if self.resource_strategy == "reserved_bom" and not self._materials_available(
            SINGLE_HIVE_BOM
        ):
            missing = {
                k: v - self.stock.get(k, 0)
                for k, v in SINGLE_HIVE_BOM.items()
                if self.stock.get(k, 0) < v
            }
            self.failed = True
            self.failure_reason = (
                f"Insufficient reserved BOM stock for next hive: {missing}"
            )
            self._log("resource_failure", task="bom_reservation", missing=missing)
            return

        parent = self.hives[-1]
        child_number = len(self.hives)
        next_gen = parent.generation + 1
        self._target_retries = 0
        self._target_hard_faults = 0
        child = Hive(
            self._format_hive_id(child_number),
            next_gen,
            parent.hive_id,
            started_tick=self.tick_count,
            firmware_version=f"v1.{next_gen}.0",
            components_built={k: False for k in COMPONENT_DURATIONS},
            assembly_progress={k: False for k in ASSEMBLY_TASKS},
            verification_progress={k: False for k in VERIFICATION_TASKS},
        )
        self.current_target = child
        self.hives.append(child)
        self.phase = "manufacturing"
        self.tasks = [
            Task(
                name=name,
                role="systems"
                if name in {"controller", "software_image", "communications"}
                else "fabricator",
                duration=duration,
                remaining=duration,
                phase="manufacturing",
                station=TASK_STATIONS.get(name, "FAB_BAY"),
            )
            for name, duration in COMPONENT_DURATIONS.items()
        ]
        self._log(
            "replication_started",
            parent=parent.hive_id,
            child=child.hive_id,
            generation=child.generation,
            firmware=child.firmware_version,
        )
        self._log(
            "digital_twin_created", hive=child.hive_id, blueprint_components=len(BOM)
        )
        if self.resource_strategy == "reserved_bom":
            self._log("bom_reserved", hive=child.hive_id)

    def _materials_available(self, recipe: Dict[str, int]) -> bool:
        return all(self.stock.get(k, 0) >= v for k, v in recipe.items())

    def _consume_materials(self, recipe: Dict[str, int]) -> bool:
        if not self._materials_available(recipe):
            if self.continuous_mode or self.resource_strategy == "auto_resupply":
                self.resupply(
                    1,
                    reason="continuous_resupply"
                    if self.continuous_mode
                    else "auto_resupply",
                )
            if not self._materials_available(recipe):
                return False
        for material, amount in recipe.items():
            self.stock[material] -= amount
        return True

    def set_continuous_mode(self, enabled: bool) -> dict:
        """Toggle live continuous replication mode without interrupting active runs."""
        self.continuous_mode = bool(enabled)
        self._log(
            "continuous_mode_enabled"
            if self.continuous_mode
            else "continuous_mode_disabled"
        )
        if self.continuous_mode and self.phase == "complete" and not self.failed:
            self.max_generations = self.completed_replications + 1
            self.max_ticks = max(self.max_ticks, self.tick_count + 1000)
            self._start_next_replication()
        return {
            "continuous_mode": self.continuous_mode,
            "phase": self.phase,
            "current_target": self.current_target.hive_id
            if self.current_target
            else None,
        }

    def set_overclock(self, enabled: bool) -> dict:
        """Toggle swarm overclocking (2x work throughput at higher thermal & energy draw)."""
        self.overclock_active = bool(enabled)
        self.power_grid["overclock_active"] = self.overclock_active
        self._log(
            "overclock_enabled" if self.overclock_active else "overclock_disabled"
        )
        return {"overclock_active": self.overclock_active}

    def coolant_flush(self) -> dict:
        """Purge accumulated thermal load across all stations back to ambient 22.0°C."""
        self.station_temps = {sid: 22.0 for sid in STATIONS}
        self._thermal_warned.clear()
        self._log("coolant_flush", ambient_c=22.0)
        return dict(self.station_temps)

    def spawn_agent(self, role: str) -> dict:
        """Dynamically commission a new specialized agent into the active swarm."""
        if role not in ROLE_PREFIXES:
            raise ValueError(f"Unknown agent role: {role}")
        prefix = ROLE_PREFIXES[role]
        existing = sum(1 for a in self.agents if a.role == role)
        agent_id = f"{prefix}-{existing + 1:02d}"
        station = ROLE_HOME_STATION.get(role, "DEPOT")
        coords = STATIONS[station]
        agent = Agent(
            agent_id=agent_id,
            role=role,
            x=coords["x"],
            y=coords["y"],
            target_x=coords["x"],
            target_y=coords["y"],
            station=station,
        )
        self.agents.append(agent)
        self._log("agent_spawned", agent=agent.agent_id, role=role, station=station)
        return asdict(agent)

    def resupply(self, multiplier: int = 1, reason: str = "manual_supply_drop") -> dict:
        """Add multiplier x SINGLE_HIVE_BOM units into active stock."""
        if multiplier < 1:
            raise ValueError("multiplier must be at least 1")
        added: Dict[str, int] = {}
        for material, amount in SINGLE_HIVE_BOM.items():
            delta = amount * multiplier
            self.stock[material] = self.stock.get(material, 0) + delta
            self.total_resupplied[material] = (
                self.total_resupplied.get(material, 0) + delta
            )
            added[material] = delta
        self._log("supply_drop", reason=reason, multiplier=multiplier, added=added)
        return added

    def inject_fault(
        self, agent_id: Optional[str] = None, permanent: bool = False
    ) -> dict:
        """Manually inject a recoverable or permanent hardware fault for testing/GUI."""
        target = None
        if agent_id is not None:
            target = next((a for a in self.agents if a.agent_id == agent_id), None)
        else:
            target = next(
                (a for a in self.agents if a.status in ("working", "moving")),
                self.agents[0] if self.agents else None,
            )
        if target is None:
            return {"injected": False, "reason": "No matching agent found"}

        if permanent:
            target.status = "offline"
            target.hard_faults += 1
            target.repair_remaining = 3
            target.fault_flash = True
            self.total_hard_faults += 1
            self._log(
                "permanent_fault_injected",
                agent=target.agent_id,
                task=target.current_task,
            )
            return {"injected": True, "type": "permanent", "agent_id": target.agent_id}

        running = next(
            (
                t
                for t in self.tasks
                if t.status == "running" and t.assigned_to == target.agent_id
            ),
            None,
        )
        target.retries += 1
        target.fault_flash = True
        self.total_faults += 1
        if running is not None:
            running.retries += 1
            running.remaining += 1
        self._log(
            "recoverable_fault_injected",
            agent=target.agent_id,
            task=running.name if running else target.current_task,
        )
        return {"injected": True, "type": "recoverable", "agent_id": target.agent_id}

    def _move_agent_toward(self, agent: Agent, station: str, consume_tick: bool) -> bool:
        coords = STATIONS[station]
        agent.station = station
        agent.target_x = coords["x"]
        agent.target_y = coords["y"]
        dx = agent.target_x - agent.x
        dy = agent.target_y - agent.y
        dist = math.hypot(dx, dy)
        if dist < 1e-6:
            return True

        if not consume_tick:
            agent.distance_traveled += dist
            agent.x = agent.target_x
            agent.y = agent.target_y
            return True

        step_speed = 2.5
        if dist <= step_speed:
            agent.distance_traveled += dist
            agent.x = agent.target_x
            agent.y = agent.target_y
            return True

        ratio = step_speed / dist
        agent.x += dx * ratio
        agent.y += dy * ratio
        agent.distance_traveled += step_speed
        return False

    def _begin_task(self, task: Task, agent: Agent) -> bool:
        if task.name in BOM and not self._consume_materials(BOM[task.name]):
            self.failed = True
            missing = {
                k: v - self.stock.get(k, 0)
                for k, v in BOM[task.name].items()
                if self.stock.get(k, 0) < v
            }
            self.failure_reason = f"Insufficient materials for {task.name}: {missing}"
            self._log("resource_failure", task=task.name, missing=missing)
            return False
        task.status = "running"
        task.assigned_to = agent.agent_id
        agent.current_task = task.name
        agent.status = "working"
        self._move_agent_toward(agent, task.station, consume_tick=self.enable_travel_ticks)
        self._log("task_started", task=task.name, agent=agent.agent_id)
        return True

    def _phase_tasks(self, phase: str) -> List[Task]:
        if phase == "assembly":
            return [
                Task(
                    "mechanical_assembly",
                    "assembler",
                    5,
                    5,
                    phase="assembly",
                    station=TASK_STATIONS["mechanical_assembly"],
                ),
                Task(
                    "electrical_integration",
                    "systems",
                    4,
                    4,
                    phase="assembly",
                    station=TASK_STATIONS["electrical_integration"],
                ),
            ]
        if phase == "verification":
            return [
                Task(
                    "self_test",
                    "inspector",
                    3,
                    3,
                    phase="verification",
                    station=TASK_STATIONS["self_test"],
                ),
                Task(
                    "safety_validation",
                    "inspector",
                    2,
                    2,
                    phase="verification",
                    station=TASK_STATIONS["safety_validation"],
                ),
            ]
        return []

    def _mark_blueprint_progress(self, task: Task) -> None:
        if self.current_target is None:
            return
        if task.name in self.current_target.components_built:
            self.current_target.components_built[task.name] = True
        elif task.name in self.current_target.assembly_progress:
            self.current_target.assembly_progress[task.name] = True
        elif task.name in self.current_target.verification_progress:
            self.current_target.verification_progress[task.name] = True

    def _advance_phase(self) -> None:
        if self.phase == "manufacturing":
            self.phase = "assembly"
            self.tasks = self._phase_tasks("assembly")
            self._log("manufacturing_complete", hive=self.current_target.hive_id)
        elif self.phase == "assembly":
            self.phase = "verification"
            self.tasks = self._phase_tasks("verification")
            self._log("assembly_complete", hive=self.current_target.hive_id)
        elif self.phase == "verification":
            assert self.current_target is not None
            self.current_target.status = "commissioned"
            self.current_target.commissioned_tick = self.tick_count
            self.current_target.build_duration_ticks = (
                self.tick_count - self.current_target.started_tick
            )
            self.current_target.quality_score = round(
                max(
                    85.0,
                    min(
                        100.0,
                        100.0
                        - 0.4 * self._target_retries
                        - 1.5 * self._target_hard_faults
                        + min(3.0, self.current_target.generation * 0.2),
                    ),
                ),
                1,
            )
            self.current_target.capabilities = self._full_capabilities()
            self.completed_replications += 1
            self._log(
                "hive_commissioned",
                hive=self.current_target.hive_id,
                parent=self.current_target.parent_id,
                generation=self.current_target.generation,
                firmware=self.current_target.firmware_version,
                quality=self.current_target.quality_score,
            )
            self._start_next_replication()

    def _handle_maintenance(self) -> None:
        offline_agents = [a for a in self.agents if a.status == "offline"]
        maint_agents = [a for a in self.agents if a.role == "maintenance" and a.status != "offline"]

        assigned_repairs = set()
        for mnt in maint_agents:
            target = next(
                (a for a in offline_agents if a.agent_id not in assigned_repairs), None
            )
            if target is not None:
                assigned_repairs.add(target.agent_id)
                mnt.status = "repairing"
                mnt.current_task = f"repair:{target.agent_id}"
                mnt.busy_ticks += 1
                mnt.target_x = target.x
                mnt.target_y = target.y
                dx = target.x - mnt.x
                dy = target.y - mnt.y
                dist = math.hypot(dx, dy)
                if dist > 0.0:
                    mnt.distance_traveled += dist
                    mnt.x = target.x
                    mnt.y = target.y
                target.repair_remaining = max(0, target.repair_remaining - 2)
                if target.repair_remaining == 0:
                    target.status = "working" if target.current_task else "idle"
                    mnt.tasks_completed += 1
                    self._log(
                        "agent_repaired",
                        agent=target.agent_id,
                        by=mnt.agent_id,
                    )
            else:
                mnt.status = "idle"
                mnt.current_task = None
                home = ROLE_HOME_STATION["maintenance"]
                self._move_agent_toward(mnt, home, consume_tick=False)
                mnt.energy = min(100.0, mnt.energy + 5.0)

        for offline in offline_agents:
            if offline.agent_id not in assigned_repairs:
                offline.repair_remaining = max(0, offline.repair_remaining - 1)
                if offline.repair_remaining == 0:
                    offline.status = "working" if offline.current_task else "idle"
                    self._log("agent_self_recovered", agent=offline.agent_id)

    def _handle_logistics(self) -> None:
        log_agents = [
            a for a in self.agents if a.role == "logistics" and a.status != "offline"
        ]
        if not log_agents:
            return

        active_targets = sorted(
            {
                a.station
                for a in self.agents
                if a.role not in ("logistics", "maintenance")
                and a.status in ("working", "moving")
            }
        )
        low_stock = any(
            self.stock.get(m, 0) < qty for m, qty in SINGLE_HIVE_BOM.items()
        )
        for idx, agent in enumerate(log_agents):
            if low_stock and (
                self.continuous_mode or self.resource_strategy == "auto_resupply"
            ):
                self._move_agent_toward(agent, "DEPOT", consume_tick=False)
                self.resupply(1, reason="logistics_convoy")
                agent.status = "delivering"
                agent.current_task = "convoy_resupply"
                agent.tasks_completed += 1
                agent.busy_ticks += 1
                low_stock = False
            elif active_targets:
                dest = active_targets[(self._logistics_cursor + idx) % len(active_targets)]
                self._move_agent_toward(agent, dest, consume_tick=False)
                agent.status = "delivering"
                agent.current_task = f"shuttle:{dest}"
                agent.busy_ticks += 1
                agent.energy = max(15.0, agent.energy - 0.6)
                agent.energy_used += 0.6
                self.total_energy_used += 0.6
            else:
                agent.status = "idle"
                agent.current_task = None
                agent.energy = min(100.0, agent.energy + 5.0)
                self._move_agent_toward(agent, "DEPOT", consume_tick=False)
        self._logistics_cursor += 1

    def _update_environment_telemetry(self) -> None:
        heat_per_worker = 1.8 if self.overclock_active else 0.85
        for sid in STATIONS:
            workers = sum(
                1
                for a in self.agents
                if a.station == sid and a.status in ("working", "repairing")
            )
            cur = self.station_temps.get(sid, 22.0)
            nxt = max(22.0, min(95.0, cur + workers * heat_per_worker - 0.45))
            self.station_temps[sid] = round(nxt, 1)
            if nxt >= 68.0 and sid not in self._thermal_warned:
                self._thermal_warned.add(sid)
                self._log("thermal_warning", station=sid, temp_c=round(nxt, 1))
            elif nxt < 50.0 and sid in self._thermal_warned:
                self._thermal_warned.discard(sid)

        solar_kw = round(22.0 + 10.0 * math.sin(self.tick_count * 0.15), 2)
        active_work = sum(
            1
            for a in self.agents
            if a.status in ("working", "moving", "repairing", "delivering")
        )
        load_kw = round(
            6.5 + active_work * (11.5 if self.overclock_active else 5.2), 2
        )
        reactor_kw = round(max(12.0, load_kw - solar_kw + 6.0), 2)
        net_kwh = (solar_kw + reactor_kw - load_kw) * 0.05
        storage = max(
            20.0,
            min(500.0, float(self.power_grid["grid_storage_kwh"]) + net_kwh),
        )
        self.power_grid = {
            "solar_kw": solar_kw,
            "reactor_kw": reactor_kw,
            "load_kw": load_kw,
            "grid_storage_kwh": round(storage, 2),
            "max_storage_kwh": 500.0,
            "overclock_active": self.overclock_active,
        }

    def step(self) -> None:
        if self.phase == "complete" or self.failed:
            return
        if self.continuous_mode and self.tick_count >= self.max_ticks - 50:
            self.max_ticks = max(self.max_ticks, self.tick_count + 1000)
        if self.tick_count >= self.max_ticks:
            self.failed = True
            self.failure_reason = f"Maximum tick budget ({self.max_ticks}) exceeded"
            self._log("simulation_timeout")
            self._record_history()
            return

        self.tick_count += 1
        for a in self.agents:
            a.fault_flash = False

        self._handle_maintenance()

        # A task remains assigned to its agent until complete. New tasks are
        # dispatched in stable order, making runs reproducible for a given seed.
        for agent in self.agents:
            if agent.role in ("maintenance", "logistics"):
                continue
            if agent.status == "offline":
                continue

            running = next(
                (
                    t
                    for t in self.tasks
                    if t.status == "running" and t.assigned_to == agent.agent_id
                ),
                None,
            )
            if running is None:
                candidate = next(
                    (
                        t
                        for t in self.tasks
                        if t.status == "queued" and t.role == agent.role
                    ),
                    None,
                )
                if candidate is not None:
                    if not self._begin_task(candidate, agent):
                        self._update_environment_telemetry()
                        self._record_history()
                        return
                    running = candidate

            if running is not None:
                if self.enable_travel_ticks:
                    arrived = self._move_agent_toward(
                        agent, running.station, consume_tick=True
                    )
                    if not arrived:
                        agent.status = "moving"
                        agent.busy_ticks += 1
                        agent.energy = max(5.0, agent.energy - 0.5)
                        agent.energy_used += 0.5
                        self.total_energy_used += 0.5
                        continue

                agent.status = "working"
                agent.current_task = running.name
                agent.busy_ticks += 1
                tick_energy = running.energy_cost_per_tick * (
                    2.2 if self.overclock_active else 1.0
                )
                agent.energy = max(5.0, agent.energy - tick_energy)
                agent.energy_used += tick_energy
                self.total_energy_used += tick_energy

                if (
                    self.permanent_fault_rate > 0.0
                    and self.aux_rng.random() < self.permanent_fault_rate
                ):
                    agent.status = "offline"
                    agent.hard_faults += 1
                    agent.repair_remaining = 3
                    agent.fault_flash = True
                    self.total_hard_faults += 1
                    self._target_hard_faults += 1
                    self._log(
                        "permanent_fault",
                        task=running.name,
                        agent=agent.agent_id,
                    )
                    continue

                # Faults add a recovery tick; they do not silently corrupt the build.
                if self.rng.random() < self.fault_rate:
                    running.retries += 1
                    agent.retries += 1
                    agent.fault_flash = True
                    self.total_faults += 1
                    self._target_retries += 1
                    self._log("recoverable_fault", task=running.name, agent=agent.agent_id)
                else:
                    work_units = 2 if self.overclock_active else 1
                    running.remaining = max(0, running.remaining - work_units)
                if running.remaining <= 0:
                    running.status = "complete"
                    agent.tasks_completed += 1
                    agent.current_task = None
                    agent.status = "idle"
                    self._mark_blueprint_progress(running)
                    self._log(
                        "task_completed", task=running.name, agent=agent.agent_id
                    )
            else:
                agent.status = "idle"
                agent.current_task = None
                agent.energy = min(100.0, agent.energy + 5.0)
                home = ROLE_HOME_STATION.get(agent.role, "DEPOT")
                self._move_agent_toward(agent, home, consume_tick=False)

        if self.tasks and all(t.status == "complete" for t in self.tasks):
            self._advance_phase()

        self._handle_logistics()
        self._update_environment_telemetry()
        self._record_history()

    def run(self) -> dict:
        while self.phase != "complete" and not self.failed:
            self.step()
        return self.report()

    def snapshot(self) -> dict:
        """Return a live, JSON-serializable state snapshot for GUI and web visuals."""
        commissioned = [h for h in self.hives if h.status == "commissioned"]
        replica_hives = [h for h in commissioned if h.generation > 0]
        materials = {}
        for name, init_qty in self.initial_stock.items():
            resupplied = self.total_resupplied.get(name, 0)
            remaining = self.stock.get(name, 0)
            used = init_qty + resupplied - remaining
            materials[name] = {
                "initial": init_qty,
                "resupplied": resupplied,
                "used": used,
                "remaining": remaining,
            }

        status = (
            "failed"
            if self.failed
            else ("success" if self.phase == "complete" else "running")
        )
        swarm_iq = round(100.0 + self.completed_replications * 4.5, 1)
        throughput = (
            round((self.completed_replications / self.tick_count) * 100.0, 2)
            if self.tick_count > 0
            else 0.0
        )
        latest_fw = self.hives[-1].firmware_version if self.hives else "v1.0.0"
        return {
            "project": "NeuroHive 1.0",
            "version": VERSION,
            "experimental_intensity": EXPERIMENTAL_INTENSITY,
            "tick": self.tick_count,
            "max_ticks": self.max_ticks,
            "seed": self.seed,
            "fault_rate": self.fault_rate,
            "permanent_fault_rate": self.permanent_fault_rate,
            "resource_strategy": self.resource_strategy,
            "enable_travel_ticks": self.enable_travel_ticks,
            "continuous_mode": self.continuous_mode,
            "overclock_active": self.overclock_active,
            "phase": self.phase,
            "status": status,
            "requested_replications": self.max_generations,
            "completed_replications": self.completed_replications,
            "replica_count": len(replica_hives),
            "progress_pct": self._compute_progress_pct(),
            "total_recoverable_faults": self.total_faults,
            "total_hard_faults": self.total_hard_faults,
            "total_energy_used": round(self.total_energy_used, 2),
            "swarm_intelligence_index": swarm_iq,
            "throughput_per_100t": throughput,
            "latest_firmware": latest_fw,
            "station_temps": dict(self.station_temps),
            "power_grid": dict(self.power_grid),
            "failure_reason": self.failure_reason,
            "current_target": self.current_target.hive_id
            if self.current_target
            else None,
            "grid": {
                "width": GRID_WIDTH,
                "height": GRID_HEIGHT,
                "stations": STATIONS,
            },
            "total_hives": len(self.hives),
            "hives": [asdict(h) for h in self.hives[-40:]],
            "agents": [asdict(a) for a in self.agents],
            "tasks": [asdict(t) for t in self.tasks],
            "materials": materials,
            "events": self.events[-100:],
            "total_events": len(self.events),
            "history": self.history[-200:],
        }

    def report(self) -> dict:
        commissioned = [h for h in self.hives if h.status == "commissioned"]
        replica_hives = [h for h in commissioned if h.generation > 0]
        material_used = {
            k: self.initial_stock[k] + self.total_resupplied.get(k, 0) - self.stock[k]
            for k in self.initial_stock
        }
        agent_metrics = {
            a.agent_id: {
                "role": a.role,
                "tasks_completed": a.tasks_completed,
                "busy_ticks": a.busy_ticks,
                "energy_used": round(a.energy_used, 2),
                "distance_traveled": round(a.distance_traveled, 2),
                "hard_faults": a.hard_faults,
            }
            for a in self.agents
        }
        swarm_iq = round(100.0 + self.completed_replications * 4.5, 1)
        throughput = (
            round((self.completed_replications / self.tick_count) * 100.0, 2)
            if self.tick_count > 0
            else 0.0
        )
        return {
            "project": "NeuroHive 1.0",
            "version": VERSION,
            "experimental_intensity": EXPERIMENTAL_INTENSITY,
            "seed": self.seed,
            "status": "success"
            if (self.phase == "complete" or self.continuous_mode) and not self.failed
            else "failed",
            "ticks": self.tick_count,
            "requested_replications": self.max_generations,
            "completed_replications": self.completed_replications,
            "commissioned_hives": [asdict(h) for h in commissioned],
            "replica_count": len(replica_hives),
            "material_used": material_used,
            "material_remaining": dict(self.stock),
            "total_resupplied": dict(self.total_resupplied),
            "total_recoverable_faults": self.total_faults,
            "total_hard_faults": self.total_hard_faults,
            "total_energy_used": round(self.total_energy_used, 2),
            "resource_strategy": self.resource_strategy,
            "continuous_mode": self.continuous_mode,
            "overclock_active": self.overclock_active,
            "swarm_intelligence_index": swarm_iq,
            "throughput_per_100t": throughput,
            "station_temps": dict(self.station_temps),
            "power_grid": dict(self.power_grid),
            "agents": agent_metrics,
            "failure_reason": self.failure_reason,
            "events": self.events,
            "history": self.history,
        }


def run_parameter_sweep(
    fault_rates: Sequence[float] = (0.0, 0.01, 0.05, 0.10, 0.20),
    generations: int = 2,
    seeds: Sequence[int] = (42, 7, 17),
    max_ticks: int = 2000,
    resource_strategy: str = "standard",
    permanent_fault_rate: float = 0.0,
) -> dict:
    """Run multi-seed benchmarks across fault rates to compare reliability & makespan."""
    rows: List[dict] = []
    details: List[dict] = []
    for rate in fault_rates:
        rate_runs = []
        for seed in seeds:
            rep = NeuroHiveSimulation(
                seed=seed,
                max_generations=generations,
                fault_rate=rate,
                max_ticks=max_ticks,
                permanent_fault_rate=permanent_fault_rate,
                resource_strategy=resource_strategy,
            ).run()
            agent_count = len(rep["agents"])
            total_busy = sum(a["busy_ticks"] for a in rep["agents"].values())
            util_pct = (
                100.0 * total_busy / (rep["ticks"] * agent_count)
                if rep["ticks"] > 0 and agent_count > 0
                else 0.0
            )
            item = {
                "fault_rate": rate,
                "seed": seed,
                "status": rep["status"],
                "ticks": rep["ticks"],
                "faults": rep["total_recoverable_faults"],
                "hard_faults": rep["total_hard_faults"],
                "energy_used": rep["total_energy_used"],
                "utilisation_pct": round(util_pct, 1),
            }
            rate_runs.append(item)
            details.append(item)

        success_count = sum(1 for r in rate_runs if r["status"] == "success")
        rows.append(
            {
                "fault_rate": rate,
                "runs": len(rate_runs),
                "success_count": success_count,
                "success_rate": round(100.0 * success_count / len(rate_runs), 1),
                "avg_ticks": round(
                    sum(r["ticks"] for r in rate_runs) / len(rate_runs), 2
                ),
                "min_ticks": min(r["ticks"] for r in rate_runs),
                "max_ticks": max(r["ticks"] for r in rate_runs),
                "avg_faults": round(
                    sum(r["faults"] for r in rate_runs) / len(rate_runs), 2
                ),
                "avg_energy_used": round(
                    sum(r["energy_used"] for r in rate_runs) / len(rate_runs), 2
                ),
                "avg_utilisation_pct": round(
                    sum(r["utilisation_pct"] for r in rate_runs) / len(rate_runs), 1
                ),
            }
        )
    return {
        "generations": generations,
        "seeds": list(seeds),
        "resource_strategy": resource_strategy,
        "summary": rows,
        "details": details,
    }


def render_sweep_summary(sweep_result: dict) -> str:
    lines = [
        f"NeuroHive Parameter Sweep | generations={sweep_result['generations']} "
        f"| seeds={sweep_result['seeds']} | strategy={sweep_result['resource_strategy']}",
        "=" * 78,
        f"{'FAULT RATE':>10s} | {'SUCCESS':>8s} | {'AVG TICKS':>9s} | {'MIN-MAX':>9s} | "
        f"{'AVG FAULTS':>10s} | {'UTIL %':>6s} | {'AVG ENERGY':>10s}",
        "-" * 78,
    ]
    for row in sweep_result["summary"]:
        span = f"{row['min_ticks']}-{row['max_ticks']}"
        lines.append(
            f"{row['fault_rate']:9.1%} | {row['success_rate']:7.1f}% | "
            f"{row['avg_ticks']:9.2f} | {span:>9s} | "
            f"{row['avg_faults']:10.2f} | {row['avg_utilisation_pct']:5.1f}% | "
            f"{row['avg_energy_used']:10.1f}"
        )
    return "\n".join(lines)


def render_summary(report: dict) -> str:
    lines = [
        f"{report['project']} v{report['version']} | experimental intensity: "
        f"{report['experimental_intensity']:.0%}",
        "=" * 72,
        f"STATUS: {report['status'].upper()}",
        f"Simulation ticks: {report['ticks']}",
        f"Replications: {report['completed_replications']}/{report['requested_replications']}",
        f"Commissioned hives: {', '.join(h['hive_id'] for h in report['commissioned_hives'])}",
        f"Recoverable faults: {report['total_recoverable_faults']}",
        "",
        "MATERIAL BALANCE",
    ]
    for name, used in report["material_used"].items():
        lines.append(
            f"  {name:14s} used={used:3d} remaining={report['material_remaining'][name]:3d}"
        )
    lines.extend(["", "AGENT UTILISATION"])
    for agent_id, data in report["agents"].items():
        lines.append(
            f"  {agent_id:7s} {data['role']:12s} tasks={data['tasks_completed']:2d} "
            f"busy_ticks={data['busy_ticks']:3d}"
        )
    if report["failure_reason"]:
        lines.extend(["", f"FAILURE: {report['failure_reason']}"])
    lines.extend(
        ["", "Note: simulated outputs are model results, not physical validation."]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the NeuroHive 1.0 self-replication simulation."
    )
    parser.add_argument(
        "--seed", type=int, default=42, help="Deterministic random seed (default: 42)"
    )
    parser.add_argument(
        "--generations",
        type=int,
        default=2,
        help="Number of successive replications: A->B is 1; A->B->C is 2.",
    )
    parser.add_argument(
        "--fault-rate",
        type=float,
        default=0.01,
        help="Per-agent-tick recoverable fault probability, 0..1 (default: 0.01).",
    )
    parser.add_argument(
        "--permanent-fault-rate",
        type=float,
        default=0.0,
        help="Per-agent-tick permanent fault probability requiring repair (default: 0.0).",
    )
    parser.add_argument(
        "--resource-strategy",
        choices=VALID_RESOURCE_STRATEGIES,
        default="standard",
        help="Inventory strategy: standard, reserved_bom, or auto_resupply.",
    )
    parser.add_argument(
        "--travel-ticks",
        action="store_true",
        help="Simulate spatial travel ticks between factory stations.",
    )
    parser.add_argument(
        "--max-ticks", type=int, default=2000, help="Simulation time budget."
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("neurohive_run.json"),
        help="JSON report path.",
    )
    parser.add_argument(
        "--sweep",
        action="store_true",
        help="Run multi-seed fault-rate sweep benchmark.",
    )
    parser.add_argument(
        "--gui",
        action="store_true",
        help="Launch the interactive Tkinter desktop GUI.",
    )
    parser.add_argument(
        "--web",
        action="store_true",
        help="Launch the live interactive web dashboard.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8765,
        help="Port for the live web dashboard server (default: 8765).",
    )
    parser.add_argument(
        "--continuous",
        action="store_true",
        help="Enable live continuous replication mode (non-stop generational progression).",
    )
    parser.add_argument(
        "--overclock",
        action="store_true",
        help="Enable swarm overclocking (2x work throughput at higher heat and energy).",
    )
    args = parser.parse_args()

    if args.gui:
        from neurohive_gui import launch_gui

        launch_gui(
            seed=args.seed,
            generations=args.generations,
            fault_rate=args.fault_rate,
            permanent_fault_rate=args.permanent_fault_rate,
            resource_strategy=args.resource_strategy,
            enable_travel_ticks=args.travel_ticks,
            max_ticks=args.max_ticks,
            continuous_mode=args.continuous,
            overclock_active=args.overclock,
        )
        return 0

    if args.web:
        from neurohive_web import launch_web_dashboard

        launch_web_dashboard(
            port=args.port,
            seed=args.seed,
            generations=args.generations,
            fault_rate=args.fault_rate,
            permanent_fault_rate=args.permanent_fault_rate,
            resource_strategy=args.resource_strategy,
            enable_travel_ticks=args.travel_ticks,
            max_ticks=args.max_ticks,
            continuous_mode=args.continuous,
            overclock_active=args.overclock,
        )
        return 0

    if args.sweep:
        sweep = run_parameter_sweep(
            generations=args.generations,
            max_ticks=args.max_ticks,
            resource_strategy=args.resource_strategy,
            permanent_fault_rate=args.permanent_fault_rate,
        )
        print(render_sweep_summary(sweep))
        args.output.write_text(json.dumps(sweep, indent=2), encoding="utf-8")
        print(f"\nSweep report written to: {args.output.resolve()}")
        return 0

    sim = NeuroHiveSimulation(
        seed=args.seed,
        max_generations=args.generations,
        fault_rate=args.fault_rate,
        max_ticks=args.max_ticks,
        permanent_fault_rate=args.permanent_fault_rate,
        resource_strategy=args.resource_strategy,
        enable_travel_ticks=args.travel_ticks,
        continuous_mode=args.continuous,
        overclock_active=args.overclock,
    )
    if args.continuous:
        for _ in range(args.max_ticks):
            if sim.failed:
                break
            sim.step()
        report = sim.report()
    else:
        report = sim.run()
    print(render_summary(report))
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nJSON report written to: {args.output.resolve()}")
    return 0 if report["status"] == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main())
