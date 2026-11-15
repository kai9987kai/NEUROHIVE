#!/usr/bin/env python3
"""NeuroHive 1.0 Native Desktop GUI (Tkinter) with live spatial factory visuals."""
from __future__ import annotations

import json
import math
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Dict, Optional

from neurohive import (
    ASSEMBLY_TASKS,
    COMPONENT_DURATIONS,
    GRID_HEIGHT,
    GRID_WIDTH,
    STATIONS,
    VALID_RESOURCE_STRATEGIES,
    VERIFICATION_TASKS,
    NeuroHiveSimulation,
    run_parameter_sweep,
)

THEME = {
    "bg": "#0b0f19",
    "panel": "#131b2e",
    "panel_alt": "#1a243d",
    "border": "#263352",
    "text": "#e2e8f0",
    "muted": "#94a3b8",
    "cyan": "#00e5ff",
    "emerald": "#10b981",
    "amber": "#f59e0b",
    "crimson": "#ef4444",
    "violet": "#a78bfa",
    "slate": "#334155",
}

ROLE_COLORS = {
    "fabricator": "#22d3ee",
    "systems": "#a78bfa",
    "assembler": "#34d399",
    "inspector": "#fb7185",
    "maintenance": "#f59e0b",
    "logistics": "#38bdf8",
}


class NeuroHiveApp:
    """Interactive Tkinter desktop workbench for NeuroHive 1.0."""

    def __init__(
        self,
        root: tk.Tk,
        seed: int = 42,
        generations: int = 2,
        fault_rate: float = 0.01,
        permanent_fault_rate: float = 0.0,
        resource_strategy: str = "standard",
        enable_travel_ticks: bool = False,
        max_ticks: int = 2000,
        continuous_mode: bool = False,
        overclock_active: bool = False,
    ):
        self.root = root
        self.root.title("NeuroHive 1.0 — Live Multi-Agent Replication Studio")
        self.root.geometry("1440x880")
        self.root.minsize(1160, 720)
        self.root.configure(bg=THEME["bg"])

        self.playing = False
        self.anim_phase = 0.0
        self.tick_accumulator_ms = 0
        self.anim_interval_ms = 35
        self._after_id: Optional[str] = None
        self.visual_pos: Dict[str, list[float]] = {}

        # Control variables
        self.var_seed = tk.IntVar(value=seed)
        self.var_generations = tk.IntVar(value=generations)
        self.var_fault_rate = tk.DoubleVar(value=fault_rate)
        self.var_perm_fault_rate = tk.DoubleVar(value=permanent_fault_rate)
        self.var_strategy = tk.StringVar(value=resource_strategy)
        self.var_travel = tk.BooleanVar(value=enable_travel_ticks)
        self.var_maint = tk.BooleanVar(value=False)
        self.var_logistics = tk.BooleanVar(value=False)
        self.var_continuous = tk.BooleanVar(value=continuous_mode)
        self.var_overclock = tk.BooleanVar(value=overclock_active)
        self.var_spawn_role = tk.StringVar(value="fabricator")
        self.var_max_ticks = tk.IntVar(value=max_ticks)
        self.var_speed_ms = tk.IntVar(value=180)
        self.var_event_filter = tk.StringVar(value="ALL")

        self.sim = self._create_simulation()
        self._sync_visual_positions(snap=True)
        self._configure_styles()
        self._build_layout()
        self.refresh_ui()

        self._after_id = self.root.after(self.anim_interval_ms, self._animation_loop)

    def _create_simulation(self) -> NeuroHiveSimulation:
        agent_counts = None
        if self.var_maint.get() or self.var_logistics.get():
            agent_counts = {
                "fabricator": 2,
                "systems": 1,
                "assembler": 2,
                "inspector": 1,
                "maintenance": 1 if self.var_maint.get() else 0,
                "logistics": 1 if self.var_logistics.get() else 0,
            }
        return NeuroHiveSimulation(
            seed=int(self.var_seed.get()),
            max_generations=int(self.var_generations.get()),
            fault_rate=float(self.var_fault_rate.get()),
            max_ticks=int(self.var_max_ticks.get()),
            permanent_fault_rate=float(self.var_perm_fault_rate.get()),
            resource_strategy=self.var_strategy.get(),
            enable_travel_ticks=bool(self.var_travel.get()),
            agent_counts=agent_counts,
            continuous_mode=bool(self.var_continuous.get()),
            overclock_active=bool(self.var_overclock.get()),
        )

    def _sync_visual_positions(self, snap: bool = False) -> None:
        for agent in self.sim.agents:
            if snap or agent.agent_id not in self.visual_pos:
                self.visual_pos[agent.agent_id] = [float(agent.x), float(agent.y)]
            else:
                vx, vy = self.visual_pos[agent.agent_id]
                self.visual_pos[agent.agent_id] = [
                    vx + (agent.x - vx) * 0.28,
                    vy + (agent.y - vy) * 0.28,
                ]

    def _configure_styles(self) -> None:
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        style.configure(
            "NH.TFrame",
            background=THEME["bg"],
        )
        style.configure(
            "Panel.TFrame",
            background=THEME["panel"],
        )
        style.configure(
            "NH.TLabel",
            background=THEME["panel"],
            foreground=THEME["text"],
            font=("Segoe UI", 9),
        )
        style.configure(
            "Header.TLabel",
            background=THEME["bg"],
            foreground=THEME["cyan"],
            font=("Segoe UI", 13, "bold"),
        )
        style.configure(
            "Section.TLabel",
            background=THEME["panel"],
            foreground=THEME["cyan"],
            font=("Segoe UI", 10, "bold"),
        )
        style.configure(
            "NH.TButton",
            background=THEME["panel_alt"],
            foreground=THEME["text"],
            bordercolor=THEME["border"],
            padding=(10, 5),
            font=("Segoe UI", 9, "bold"),
        )
        style.map(
            "NH.TButton",
            background=[("active", "#263659")],
            foreground=[("active", THEME["cyan"])],
        )
        style.configure(
            "Primary.TButton",
            background="#0e7490",
            foreground="#ffffff",
            padding=(12, 5),
            font=("Segoe UI", 9, "bold"),
        )
        style.map("Primary.TButton", background=[("active", "#0891b2")])
        style.configure(
            "NH.Treeview",
            background=THEME["panel_alt"],
            foreground=THEME["text"],
            fieldbackground=THEME["panel_alt"],
            rowheight=24,
            font=("Consolas", 9),
        )
        style.configure(
            "NH.Treeview.Heading",
            background=THEME["bg"],
            foreground=THEME["cyan"],
            font=("Segoe UI", 9, "bold"),
        )
        style.configure(
            "NH.TCheckbutton",
            background=THEME["panel"],
            foreground=THEME["text"],
            font=("Segoe UI", 9),
        )

    def _build_layout(self) -> None:
        # Top header + controls bar
        top_bar = tk.Frame(self.root, bg=THEME["panel"], highlightbackground=THEME["border"], highlightthickness=1)
        top_bar.pack(fill="x", padx=10, pady=(10, 6))

        title_row = tk.Frame(top_bar, bg=THEME["panel"])
        title_row.pack(fill="x", padx=10, pady=(8, 4))

        tk.Label(
            title_row,
            text="NEUROHIVE 1.0  |  LIVE DIGITAL TWIN & SWARM STUDIO",
            bg=THEME["panel"],
            fg=THEME["cyan"],
            font=("Segoe UI", 12, "bold"),
        ).pack(side="left")

        self.lbl_status_pill = tk.Label(
            title_row,
            text="READY",
            bg=THEME["emerald"],
            fg="#04110b",
            font=("Consolas", 9, "bold"),
            padx=10,
            pady=2,
        )
        self.lbl_status_pill.pack(side="right")

        # Parameter row
        param_row = tk.Frame(top_bar, bg=THEME["panel"])
        param_row.pack(fill="x", padx=10, pady=4)

        self._add_spin(param_row, "Seed", self.var_seed, 1, 99999, 1, 6)
        self._add_spin(param_row, "Gens", self.var_generations, 1, 12, 1, 4)
        self._add_spin(param_row, "Fault Rate", self.var_fault_rate, 0.0, 0.5, 0.01, 5)
        self._add_spin(param_row, "Hard Fault", self.var_perm_fault_rate, 0.0, 0.2, 0.01, 5)

        tk.Label(param_row, text="Strategy:", bg=THEME["panel"], fg=THEME["muted"], font=("Segoe UI", 9)).pack(side="left", padx=(8, 2))
        strat_box = ttk.Combobox(
            param_row,
            textvariable=self.var_strategy,
            values=list(VALID_RESOURCE_STRATEGIES),
            width=13,
            state="readonly",
        )
        strat_box.pack(side="left", padx=(0, 8))

        ttk.Checkbutton(
            param_row,
            text="∞ Continuous Mode",
            variable=self.var_continuous,
            command=self.toggle_continuous_mode,
            style="NH.TCheckbutton",
        ).pack(side="left", padx=4)
        ttk.Checkbutton(
            param_row,
            text="Overclock (2x)",
            variable=self.var_overclock,
            command=self.toggle_overclock,
            style="NH.TCheckbutton",
        ).pack(side="left", padx=4)
        ttk.Checkbutton(
            param_row, text="Travel Physics", variable=self.var_travel, style="NH.TCheckbutton"
        ).pack(side="left", padx=4)
        ttk.Checkbutton(
            param_row, text="MNT-01 Repair", variable=self.var_maint, style="NH.TCheckbutton"
        ).pack(side="left", padx=4)
        ttk.Checkbutton(
            param_row, text="LOG-01 Convoy", variable=self.var_logistics, style="NH.TCheckbutton"
        ).pack(side="left", padx=4)

        # Action button row
        btn_row = tk.Frame(top_bar, bg=THEME["panel"])
        btn_row.pack(fill="x", padx=10, pady=(4, 8))

        self.btn_play = ttk.Button(
            btn_row, text="Play", command=self.toggle_play, style="Primary.TButton"
        )
        self.btn_play.pack(side="left", padx=(0, 6))
        ttk.Button(btn_row, text="Step +1", command=self.step_once, style="NH.TButton").pack(
            side="left", padx=4
        )
        ttk.Button(btn_row, text="Reset", command=self.reset_sim, style="NH.TButton").pack(
            side="left", padx=4
        )
        ttk.Button(
            btn_row, text="Coolant Flush", command=self.flush_coolant, style="NH.TButton"
        ).pack(side="left", padx=4)
        ttk.Button(
            btn_row, text="Inject Fault", command=lambda: self.inject_fault(False), style="NH.TButton"
        ).pack(side="left", padx=4)
        ttk.Button(
            btn_row, text="Hard Fault", command=lambda: self.inject_fault(True), style="NH.TButton"
        ).pack(side="left", padx=4)
        ttk.Button(
            btn_row, text="Supply Drop (+1 BOM)", command=self.resupply_bom, style="NH.TButton"
        ).pack(side="left", padx=4)
        ttk.Combobox(
            btn_row,
            textvariable=self.var_spawn_role,
            values=["fabricator", "systems", "assembler", "inspector", "maintenance", "logistics"],
            width=11,
            state="readonly",
        ).pack(side="left", padx=(6, 2))
        ttk.Button(
            btn_row, text="+ Spawn Bot", command=self.spawn_bot, style="NH.TButton"
        ).pack(side="left", padx=2)
        ttk.Button(
            btn_row, text="Run Sweep", command=self.show_sweep_modal, style="NH.TButton"
        ).pack(side="left", padx=4)
        ttk.Button(
            btn_row, text="Export JSON", command=self.export_json, style="NH.TButton"
        ).pack(side="left", padx=4)

        tk.Label(
            btn_row, text="Tick Delay (ms):", bg=THEME["panel"], fg=THEME["muted"], font=("Segoe UI", 9)
        ).pack(side="right", padx=(8, 4))
        speed_scale = tk.Scale(
            btn_row,
            from_=25,
            to=600,
            orient="horizontal",
            variable=self.var_speed_ms,
            bg=THEME["panel"],
            fg=THEME["text"],
            troughcolor=THEME["bg"],
            highlightthickness=0,
            length=150,
            showvalue=True,
        )
        speed_scale.pack(side="right")

        # Main split workspace
        main_pane = tk.PanedWindow(
            self.root, orient="horizontal", bg=THEME["bg"], sashwidth=6, relief="flat"
        )
        main_pane.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        # Left visual column: Spatial Factory + Lineage & Blueprint
        left_col = tk.Frame(main_pane, bg=THEME["bg"])
        main_pane.add(left_col, stretch="always", minsize=680)

        factory_card = tk.Frame(
            left_col, bg=THEME["panel"], highlightbackground=THEME["border"], highlightthickness=1
        )
        factory_card.pack(fill="both", expand=True, pady=(0, 6))

        fac_hdr = tk.Frame(factory_card, bg=THEME["panel"])
        fac_hdr.pack(fill="x", padx=10, pady=(6, 2))
        ttk.Label(fac_hdr, text="2D SPATIAL FACTORY FLOOR", style="Section.TLabel").pack(side="left")
        self.lbl_phase_banner = tk.Label(
            fac_hdr,
            text="PHASE: MANUFACTURING | TARGET: NH-B",
            bg=THEME["panel"],
            fg=THEME["amber"],
            font=("Consolas", 9, "bold"),
        )
        self.lbl_phase_banner.pack(side="right")

        self.factory_canvas = tk.Canvas(
            factory_card,
            bg="#080c16",
            highlightthickness=0,
            height=410,
        )
        self.factory_canvas.pack(fill="both", expand=True, padx=8, pady=8)

        lineage_card = tk.Frame(
            left_col, bg=THEME["panel"], highlightbackground=THEME["border"], highlightthickness=1
        )
        lineage_card.pack(fill="x")
        ttk.Label(
            lineage_card,
            text="HIVE LINEAGE & DIGITAL TWIN BLUEPRINT MATRIX",
            style="Section.TLabel",
        ).pack(anchor="w", padx=10, pady=(6, 2))
        self.lineage_canvas = tk.Canvas(
            lineage_card,
            bg="#080c16",
            highlightthickness=0,
            height=210,
        )
        self.lineage_canvas.pack(fill="x", padx=8, pady=(2, 8))

        # Right telemetry column
        right_col = tk.Frame(main_pane, bg=THEME["bg"], width=480)
        main_pane.add(right_col, minsize=440)

        # KPI strip
        kpi_frame = tk.Frame(right_col, bg=THEME["bg"])
        kpi_frame.pack(fill="x", pady=(0, 6))
        self.kpi_labels: Dict[str, tk.Label] = {}
        kpis = [
            ("tick", "TICK"),
            ("progress", "PROGRESS"),
            ("replicas", "REPLICAS"),
            ("faults", "FAULTS"),
            ("energy", "ENERGY"),
        ]
        for idx, (key, label) in enumerate(kpis):
            box = tk.Frame(
                kpi_frame,
                bg=THEME["panel"],
                highlightbackground=THEME["border"],
                highlightthickness=1,
            )
            box.grid(row=0, column=idx, sticky="nsew", padx=(0 if idx == 0 else 4, 0))
            kpi_frame.columnconfigure(idx, weight=1)
            tk.Label(
                box, text=label, bg=THEME["panel"], fg=THEME["muted"], font=("Segoe UI", 8, "bold")
            ).pack(pady=(5, 0))
            val_lbl = tk.Label(
                box, text="0", bg=THEME["panel"], fg=THEME["cyan"], font=("Consolas", 11, "bold")
            )
            val_lbl.pack(pady=(0, 5))
            self.kpi_labels[key] = val_lbl

        # Material Core Ledger
        mat_card = tk.Frame(
            right_col, bg=THEME["panel"], highlightbackground=THEME["border"], highlightthickness=1
        )
        mat_card.pack(fill="x", pady=(0, 6))
        ttk.Label(mat_card, text="MATERIAL CORE LEDGER", style="Section.TLabel").pack(
            anchor="w", padx=10, pady=(6, 4)
        )
        self.mat_canvas = tk.Canvas(
            mat_card, bg=THEME["panel"], highlightthickness=0, height=155
        )
        self.mat_canvas.pack(fill="x", padx=10, pady=(0, 8))

        # SwarmCore Agent Roster
        agent_card = tk.Frame(
            right_col, bg=THEME["panel"], highlightbackground=THEME["border"], highlightthickness=1
        )
        agent_card.pack(fill="x", pady=(0, 6))
        ttk.Label(agent_card, text="SWARMCORE AGENT ROSTER", style="Section.TLabel").pack(
            anchor="w", padx=10, pady=(6, 4)
        )
        cols = ("agent", "role", "status", "station", "task", "energy", "done")
        self.agent_tree = ttk.Treeview(
            agent_card, columns=cols, show="headings", height=7, style="NH.Treeview"
        )
        col_widths = {
            "agent": 68,
            "role": 84,
            "status": 68,
            "station": 76,
            "task": 118,
            "energy": 56,
            "done": 46,
        }
        for c in cols:
            self.agent_tree.heading(c, text=c.upper())
            self.agent_tree.column(c, width=col_widths[c], anchor="w")
        self.agent_tree.pack(fill="x", padx=8, pady=(0, 8))

        # Live Event Feed
        evt_card = tk.Frame(
            right_col, bg=THEME["panel"], highlightbackground=THEME["border"], highlightthickness=1
        )
        evt_card.pack(fill="both", expand=True)
        evt_hdr = tk.Frame(evt_card, bg=THEME["panel"])
        evt_hdr.pack(fill="x", padx=10, pady=(6, 4))
        ttk.Label(evt_hdr, text="LIVE HIVE-NET EVENT TRACE", style="Section.TLabel").pack(
            side="left"
        )
        evt_filter = ttk.Combobox(
            evt_hdr,
            textvariable=self.var_event_filter,
            values=["ALL", "FAULTS", "MILESTONES", "SUPPLY"],
            width=12,
            state="readonly",
        )
        evt_filter.pack(side="right")
        evt_filter.bind("<<ComboboxSelected>>", lambda _e: self._render_events())

        self.event_text = tk.Text(
            evt_card,
            bg="#080c16",
            fg=THEME["text"],
            font=("Consolas", 9),
            relief="flat",
            wrap="word",
            state="disabled",
            height=10,
        )
        self.event_text.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self.event_text.tag_configure("milestone", foreground=THEME["emerald"])
        self.event_text.tag_configure("fault", foreground=THEME["crimson"])
        self.event_text.tag_configure("supply", foreground=THEME["amber"])
        self.event_text.tag_configure("info", foreground=THEME["muted"])

    def _add_spin(
        self,
        parent: tk.Widget,
        label: str,
        var: tk.Variable,
        from_: float,
        to: float,
        inc: float,
        width: int,
    ) -> None:
        tk.Label(
            parent, text=f"{label}:", bg=THEME["panel"], fg=THEME["muted"], font=("Segoe UI", 9)
        ).pack(side="left", padx=(6, 2))
        spin = tk.Spinbox(
            parent,
            from_=from_,
            to=to,
            increment=inc,
            textvariable=var,
            width=width,
            bg=THEME["panel_alt"],
            fg=THEME["text"],
            buttonbackground=THEME["border"],
            relief="flat",
            font=("Consolas", 9),
        )
        spin.pack(side="left", padx=(0, 6))

    def toggle_play(self) -> None:
        if self.sim.phase == "complete" or self.sim.failed:
            self.reset_sim()
        self.playing = not self.playing
        self.btn_play.configure(text="Pause" if self.playing else "Play")

    def step_once(self) -> None:
        if self.sim.phase != "complete" and not self.sim.failed:
            self.sim.step()
            self.refresh_ui()
        if self.sim.phase == "complete" or self.sim.failed:
            self.playing = False
            self.btn_play.configure(text="Play")

    def reset_sim(self) -> None:
        self.playing = False
        self.btn_play.configure(text="Play")
        try:
            self.sim = self._create_simulation()
        except ValueError as exc:
            messagebox.showerror("Invalid Parameters", str(exc))
            return
        self._sync_visual_positions(snap=True)
        self.refresh_ui()

    def inject_fault(self, permanent: bool = False) -> None:
        self.sim.inject_fault(permanent=permanent)
        self.refresh_ui()

    def resupply_bom(self) -> None:
        self.sim.resupply(1)
        self.refresh_ui()

    def toggle_continuous_mode(self) -> None:
        enabled = bool(self.var_continuous.get())
        self.sim.set_continuous_mode(enabled)
        if enabled and not self.playing:
            self.playing = True
            self.btn_play.configure(text="Pause")
        self.refresh_ui()

    def toggle_overclock(self) -> None:
        self.sim.set_overclock(bool(self.var_overclock.get()))
        self.refresh_ui()

    def flush_coolant(self) -> None:
        self.sim.coolant_flush()
        self.refresh_ui()

    def spawn_bot(self) -> None:
        self.sim.spawn_agent(self.var_spawn_role.get())
        self._sync_visual_positions(snap=False)
        self.refresh_ui()

    def export_json(self) -> None:
        path = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON files", "*.json")],
            initialfile="neurohive_gui_run.json",
        )
        if not path:
            return
        Path(path).write_text(json.dumps(self.sim.report(), indent=2), encoding="utf-8")
        messagebox.showinfo("Exported", f"Simulation report saved to:\n{path}")

    def show_sweep_modal(self) -> None:
        sweep = run_parameter_sweep(
            generations=int(self.var_generations.get()),
            max_ticks=int(self.var_max_ticks.get()),
            resource_strategy=self.var_strategy.get(),
            permanent_fault_rate=float(self.var_perm_fault_rate.get()),
        )
        modal = tk.Toplevel(self.root)
        modal.title("NeuroHive Parameter Sweep Benchmark")
        modal.geometry("760x520")
        modal.configure(bg=THEME["bg"])

        tk.Label(
            modal,
            text=f"FAULT-RATE SWEEP BENCHMARK (Generations={sweep['generations']}, Seeds={sweep['seeds']})",
            bg=THEME["bg"],
            fg=THEME["cyan"],
            font=("Segoe UI", 11, "bold"),
        ).pack(pady=(12, 8))

        cols = ("fault_rate", "success", "avg_ticks", "range", "avg_faults", "util", "energy")
        tree = ttk.Treeview(modal, columns=cols, show="headings", height=6, style="NH.Treeview")
        for c, title in zip(
            cols,
            ("Fault Rate", "Success %", "Avg Ticks", "Min-Max", "Avg Faults", "Util %", "Avg Energy"),
        ):
            tree.heading(c, text=title)
            tree.column(c, width=98, anchor="center")
        for row in sweep["summary"]:
            tree.insert(
                "",
                "end",
                values=(
                    f"{row['fault_rate']:.0%}",
                    f"{row['success_rate']:.1f}%",
                    f"{row['avg_ticks']:.1f}",
                    f"{row['min_ticks']}-{row['max_ticks']}",
                    f"{row['avg_faults']:.2f}",
                    f"{row['avg_utilisation_pct']:.1f}%",
                    f"{row['avg_energy_used']:.1f}",
                ),
            )
        tree.pack(fill="x", padx=16, pady=8)

        chart = tk.Canvas(modal, bg="#080c16", highlightthickness=0, height=250)
        chart.pack(fill="both", expand=True, padx=16, pady=(4, 16))
        modal.update_idletasks()
        w = max(680, chart.winfo_width())
        h = max(230, chart.winfo_height())
        max_ticks = max((r["avg_ticks"] for r in sweep["summary"]), default=1.0)
        bar_w = 72
        gap = (w - 80 - bar_w * len(sweep["summary"])) / max(1, len(sweep["summary"]) - 1)
        for i, row in enumerate(sweep["summary"]):
            x0 = 40 + i * (bar_w + gap)
            bar_h = (row["avg_ticks"] / max(1.0, max_ticks)) * (h - 70)
            y0 = h - 38 - bar_h
            y1 = h - 38
            chart.create_rectangle(x0, y0, x0 + bar_w, y1, fill=THEME["cyan"], outline="")
            chart.create_text(
                x0 + bar_w / 2,
                y0 - 12,
                text=f"{row['avg_ticks']:.1f}t",
                fill=THEME["text"],
                font=("Consolas", 9, "bold"),
            )
            chart.create_text(
                x0 + bar_w / 2,
                y1 + 16,
                text=f"{row['fault_rate']:.0%}",
                fill=THEME["muted"],
                font=("Consolas", 9),
            )

    def _animation_loop(self) -> None:
        self.anim_phase = (self.anim_phase + 0.18) % (math.tau)
        if self.playing:
            self.tick_accumulator_ms += self.anim_interval_ms
            if self.tick_accumulator_ms >= max(20, int(self.var_speed_ms.get())):
                self.tick_accumulator_ms = 0
                self.step_once()
        self._sync_visual_positions(snap=False)
        self._draw_factory_floor()
        self._after_id = self.root.after(self.anim_interval_ms, self._animation_loop)

    def refresh_ui(self) -> None:
        snap = self.sim.snapshot()
        status = snap["status"].upper()
        pill_color = {
            "RUNNING": THEME["cyan"],
            "SUCCESS": THEME["emerald"],
            "FAILED": THEME["crimson"],
        }.get(status, THEME["muted"])
        self.lbl_status_pill.configure(text=status, bg=pill_color)

        target = snap["current_target"] or "NONE"
        mode_tag = "∞ CONTINUOUS" if snap.get("continuous_mode") else "FINITE"
        oc_tag = " | OVERCLOCK 2x" if snap.get("overclock_active") else ""
        self.lbl_phase_banner.configure(
            text=f"{mode_tag}{oc_tag}  |  PHASE: {snap['phase'].upper()}  |  TARGET: {target}"
        )

        self.kpi_labels["tick"].configure(text=f"{snap['tick']}/{snap['max_ticks']}")
        self.kpi_labels["progress"].configure(text=f"{snap['progress_pct']:.1f}%")
        self.kpi_labels["replicas"].configure(
            text=f"{snap['completed_replications']}/{snap['requested_replications']}"
        )
        self.kpi_labels["faults"].configure(
            text=f"{snap['total_recoverable_faults']}/{snap['total_hard_faults']}",
            fg=THEME["amber"] if snap["total_recoverable_faults"] else THEME["emerald"],
        )
        self.kpi_labels["energy"].configure(text=f"{snap['total_energy_used']:.0f}")

        self._draw_factory_floor()
        self._draw_lineage_and_blueprint(snap)
        self._draw_materials(snap)
        self._update_agent_table(snap)
        self._render_events()

    def _draw_factory_floor(self) -> None:
        c = self.factory_canvas
        w = max(c.winfo_width(), 640)
        h = max(c.winfo_height(), 360)
        c.delete("all")

        pad_x, pad_y = 38, 28
        usable_w = w - 2 * pad_x
        usable_h = h - 2 * pad_y

        def to_px(gx: float, gy: float) -> tuple[float, float]:
            return (
                pad_x + (gx / GRID_WIDTH) * usable_w,
                pad_y + (gy / GRID_HEIGHT) * usable_h,
            )

        # Subtle background grid
        for gx in range(GRID_WIDTH + 1):
            px, _ = to_px(gx, 0)
            c.create_line(px, pad_y, px, h - pad_y, fill="#111a2e", width=1)
        for gy in range(GRID_HEIGHT + 1):
            _, py = to_px(0, gy)
            c.create_line(pad_x, py, w - pad_x, py, fill="#111a2e", width=1)

        # Logistics paths between stations
        links = [
            ("DEPOT", "FAB_BAY"),
            ("DEPOT", "SYS_LAB"),
            ("FAB_BAY", "ASM_DOCK"),
            ("SYS_LAB", "ASM_DOCK"),
            ("ASM_DOCK", "QA_CELL"),
            ("QA_CELL", "HIVE_PAD"),
            ("CHARGER", "DEPOT"),
        ]
        for s1, s2 in links:
            x1, y1 = to_px(STATIONS[s1]["x"], STATIONS[s1]["y"])
            x2, y2 = to_px(STATIONS[s2]["x"], STATIONS[s2]["y"])
            c.create_line(x1, y1, x2, y2, fill="#1f2c47", dash=(4, 4), width=2)

        active_stations = {
            a.station
            for a in self.sim.agents
            if a.status in ("working", "repairing", "delivering")
        }

        # Draw station zones
        for sid, info in STATIONS.items():
            px, py = to_px(info["x"], info["y"])
            temp = self.sim.station_temps.get(sid, 22.0)
            hot = temp >= 68.0
            warm = temp >= 45.0
            pulse = 4.0 * math.sin(self.anim_phase * 1.5) if sid in active_stations else 0.0
            rx, ry = 46 + pulse, 28 + pulse * 0.6
            outline = (
                THEME["crimson"]
                if hot
                else (THEME["amber"] if warm else (info["color"] if sid in active_stations else "#314266"))
            )
            width = 2 if (sid in active_stations or hot) else 1
            c.create_rectangle(
                px - rx,
                py - ry,
                px + rx,
                py + ry,
                fill="#29121a" if hot else "#111a2f",
                outline=outline,
                width=width,
            )
            c.create_text(
                px,
                py - ry + 11,
                text=f"{sid} {temp:.0f}°C",
                fill=info["color"],
                font=("Consolas", 8, "bold"),
            )
            c.create_text(
                px,
                py + ry + 11,
                text=info["label"],
                fill=THEME["muted"],
                font=("Segoe UI", 8),
            )

        # Offset agents sharing identical coordinates so they don't overlap
        coord_groups: Dict[tuple[float, float], list] = {}
        for agent in self.sim.agents:
            vx, vy = self.visual_pos.get(agent.agent_id, [agent.x, agent.y])
            key = (round(vx, 1), round(vy, 1))
            coord_groups.setdefault(key, []).append(agent)

        for group in coord_groups.values():
            n = len(group)
            for idx, agent in enumerate(group):
                vx, vy = self.visual_pos.get(agent.agent_id, [agent.x, agent.y])
                px, py = to_px(vx, vy)
                if n > 1:
                    offset_x = (idx - (n - 1) / 2.0) * 30.0
                    px += offset_x

                st_x, st_y = to_px(
                    STATIONS[agent.station]["x"], STATIONS[agent.station]["y"]
                )
                if agent.status in ("working", "repairing", "delivering"):
                    c.create_line(
                        px,
                        py,
                        st_x,
                        st_y,
                        fill=ROLE_COLORS.get(agent.role, THEME["cyan"]),
                        width=2,
                        dash=(3, 3),
                    )

                ring_color = {
                    "working": THEME["cyan"],
                    "moving": THEME["violet"],
                    "repairing": THEME["amber"],
                    "delivering": "#38bdf8",
                    "offline": THEME["crimson"],
                    "idle": THEME["emerald"],
                }.get(agent.status, THEME["muted"])
                if agent.fault_flash:
                    ring_color = THEME["crimson"]

                r = 14
                c.create_oval(
                    px - r - 3,
                    py - r - 3,
                    px + r + 3,
                    py + r + 3,
                    outline=ring_color,
                    width=2,
                )
                c.create_oval(
                    px - r,
                    py - r,
                    px + r,
                    py + r,
                    fill=ROLE_COLORS.get(agent.role, THEME["cyan"]),
                    outline="#0b0f19",
                    width=2,
                )
                c.create_text(
                    px,
                    py,
                    text=agent.agent_id.split("-")[0],
                    fill="#040812",
                    font=("Consolas", 7, "bold"),
                )
                c.create_text(
                    px,
                    py - r - 10,
                    text=agent.agent_id,
                    fill=THEME["text"],
                    font=("Consolas", 8, "bold"),
                )
                # Energy bar below agent
                bw = 28
                c.create_rectangle(
                    px - bw / 2, py + r + 5, px + bw / 2, py + r + 9, fill="#1e293b", outline=""
                )
                fill_w = max(1.0, (agent.energy / 100.0) * bw)
                bar_col = (
                    THEME["emerald"]
                    if agent.energy > 50
                    else (THEME["amber"] if agent.energy > 20 else THEME["crimson"])
                )
                c.create_rectangle(
                    px - bw / 2,
                    py + r + 5,
                    px - bw / 2 + fill_w,
                    py + r + 9,
                    fill=bar_col,
                    outline="",
                )

    def _draw_lineage_and_blueprint(self, snap: dict) -> None:
        c = self.lineage_canvas
        w = max(c.winfo_width(), 640)
        c.delete("all")

        hives = snap["hives"][-8:]
        x_start = 42
        step_x = min(135, max(82, (w - 80) // max(1, len(hives))))
        y_node = 44

        for i, hive in enumerate(hives):
            cx = x_start + i * step_x
            if i > 0:
                c.create_line(
                    cx - step_x + 32,
                    y_node,
                    cx - 32,
                    y_node,
                    fill=THEME["cyan"],
                    width=2,
                    arrow=tk.LAST,
                )
            col = (
                THEME["emerald"]
                if hive["status"] == "commissioned"
                else (THEME["crimson"] if snap["status"] == "failed" else THEME["cyan"])
            )
            c.create_rectangle(
                cx - 30, y_node - 18, cx + 30, y_node + 18, fill="#111b33", outline=col, width=2
            )
            c.create_text(
                cx, y_node - 4, text=hive["hive_id"], fill=THEME["text"], font=("Consolas", 9, "bold")
            )
            tick_txt = (
                f"t={hive['commissioned_tick']}"
                if hive["commissioned_tick"] is not None
                else hive["status"].upper()
            )
            c.create_text(
                cx, y_node + 10, text=tick_txt, fill=col, font=("Consolas", 7)
            )

        # Digital Twin Blueprint matrix for active/latest hive
        target = next(
            (h for h in hives if h["hive_id"] == snap["current_target"]),
            hives[-1],
        )
        c.create_text(
            18,
            90,
            text=f"DIGITAL TWIN BLUEPRINT: {target['hive_id']} (Gen {target['generation']})",
            anchor="w",
            fill=THEME["cyan"],
            font=("Consolas", 9, "bold"),
        )

        items = (
            [(k, target["components_built"].get(k, False)) for k in COMPONENT_DURATIONS]
            + [(k, target["assembly_progress"].get(k, False)) for k in ASSEMBLY_TASKS]
            + [(k, target["verification_progress"].get(k, False)) for k in VERIFICATION_TASKS]
        )
        running_tasks = {t["name"] for t in snap["tasks"] if t["status"] == "running"}

        cols = 5
        cell_w = max(116, (w - 36) // cols - 6)
        for idx, (name, done) in enumerate(items):
            r = idx // cols
            col_i = idx % cols
            x0 = 18 + col_i * (cell_w + 6)
            y0 = 108 + r * 32
            if done:
                bg, bd, fg = "#0d3326", THEME["emerald"], THEME["emerald"]
            elif name in running_tasks:
                bg, bd, fg = "#0b2e3d", THEME["cyan"], THEME["cyan"]
            else:
                bg, bd, fg = "#121a2d", THEME["border"], THEME["muted"]
            c.create_rectangle(x0, y0, x0 + cell_w, y0 + 25, fill=bg, outline=bd, width=1)
            short_name = name.replace("_", " ")[:18]
            c.create_text(
                x0 + 6, y0 + 12, text=short_name, anchor="w", fill=fg, font=("Consolas", 8)
            )

    def _draw_materials(self, snap: dict) -> None:
        c = self.mat_canvas
        w = max(c.winfo_width(), 380)
        c.delete("all")
        mats = snap["materials"]
        bar_x = 104
        bar_w = max(120, w - 210)
        for idx, (name, info) in enumerate(mats.items()):
            y = 14 + idx * 24
            total = max(1, info["initial"] + info["resupplied"])
            rem = info["remaining"]
            frac = max(0.0, min(1.0, rem / total))
            c.create_text(
                4, y, text=name.upper(), anchor="w", fill=THEME["text"], font=("Consolas", 9)
            )
            c.create_rectangle(
                bar_x, y - 6, bar_x + bar_w, y + 6, fill="#080c16", outline=THEME["border"]
            )
            fill_col = (
                THEME["emerald"]
                if frac > 0.35
                else (THEME["amber"] if frac > 0.15 else THEME["crimson"])
            )
            if rem > 0:
                c.create_rectangle(
                    bar_x,
                    y - 6,
                    bar_x + max(2, bar_w * frac),
                    y + 6,
                    fill=fill_col,
                    outline="",
                )
            c.create_text(
                bar_x + bar_w + 8,
                y,
                text=f"{rem:3d} rem / {info['used']:3d} used",
                anchor="w",
                fill=THEME["muted"],
                font=("Consolas", 8),
            )

    def _update_agent_table(self, snap: dict) -> None:
        for item in self.agent_tree.get_children():
            self.agent_tree.delete(item)
        for a in snap["agents"]:
            self.agent_tree.insert(
                "",
                "end",
                values=(
                    a["agent_id"],
                    a["role"],
                    a["status"].upper(),
                    a["station"],
                    a["current_task"] or "-",
                    f"{a['energy']:.0f}%",
                    a["tasks_completed"],
                ),
            )

    def _render_events(self) -> None:
        filt = self.var_event_filter.get()
        events = self.sim.events[-80:]
        self.event_text.configure(state="normal")
        self.event_text.delete("1.0", "end")
        for ev in events:
            name = ev["event"]
            if filt == "FAULTS" and "fault" not in name and "failure" not in name:
                continue
            if filt == "MILESTONES" and name not in (
                "replication_started",
                "manufacturing_complete",
                "assembly_complete",
                "hive_commissioned",
            ):
                continue
            if filt == "SUPPLY" and "supply" not in name and "bom" not in name:
                continue

            tag = "info"
            if "fault" in name or "failure" in name:
                tag = "fault"
            elif "complete" in name or "commissioned" in name or "repaired" in name:
                tag = "milestone"
            elif "supply" in name or "bom" in name:
                tag = "supply"

            details = " ".join(
                f"{k}={v}" for k, v in ev.items() if k not in ("tick", "event")
            )
            self.event_text.insert("end", f"[t={ev['tick']:03d}] {name} {details}\n", tag)
        self.event_text.see("end")
        self.event_text.configure(state="disabled")

    def close(self) -> None:
        if self._after_id is not None:
            try:
                self.root.after_cancel(self._after_id)
            except tk.TclError:
                pass
        self.root.destroy()


def launch_gui(**kwargs) -> None:
    root = tk.Tk()
    app = NeuroHiveApp(root, **kwargs)
    root.protocol("WM_DELETE_WINDOW", app.close)
    root.mainloop()


if __name__ == "__main__":
    launch_gui()
