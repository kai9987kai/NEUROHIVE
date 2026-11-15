import json
import threading
import tkinter as tk
import unittest
import urllib.request

from neurohive import (
    BOM,
    INITIAL_STOCK,
    NeuroHiveSimulation,
    run_parameter_sweep,
)
from neurohive_gui import NeuroHiveApp
from neurohive_web import create_server


class NeuroHiveTests(unittest.TestCase):
    def test_default_run_commissions_two_successive_replicas(self):
        report = NeuroHiveSimulation(seed=42, max_generations=2, fault_rate=0).run()
        self.assertEqual(report["status"], "success")
        self.assertEqual(report["completed_replications"], 2)
        self.assertEqual(report["replica_count"], 2)
        self.assertEqual(
            [h["hive_id"] for h in report["commissioned_hives"]],
            ["NH-A", "NH-B", "NH-C"],
        )

    def test_replica_can_be_configured_as_single_generation(self):
        report = NeuroHiveSimulation(max_generations=1, fault_rate=0).run()
        self.assertEqual(report["completed_replications"], 1)
        self.assertEqual(report["replica_count"], 1)

    def test_run_is_reproducible_for_same_seed(self):
        a = NeuroHiveSimulation(seed=17, fault_rate=0.08).run()
        b = NeuroHiveSimulation(seed=17, fault_rate=0.08).run()
        self.assertEqual(a["ticks"], b["ticks"])
        self.assertEqual(a["total_recoverable_faults"], b["total_recoverable_faults"])
        self.assertEqual(a["status"], b["status"])

    def test_material_balance_is_conserved(self):
        report = NeuroHiveSimulation(max_generations=1, fault_rate=0).run()
        for material, initial in INITIAL_STOCK.items():
            self.assertEqual(
                report["material_used"][material] + report["material_remaining"][material],
                initial,
            )

    def test_invalid_parameters_are_rejected(self):
        with self.assertRaises(ValueError):
            NeuroHiveSimulation(max_generations=0)
        with self.assertRaises(ValueError):
            NeuroHiveSimulation(fault_rate=1.5)
        with self.assertRaises(ValueError):
            NeuroHiveSimulation(max_ticks=0)

    def test_high_fault_rate_still_recovers_within_budget(self):
        report = NeuroHiveSimulation(seed=3, max_generations=1, fault_rate=0.2,
                                     max_ticks=5000).run()
        self.assertEqual(report["status"], "success")
        self.assertGreater(report["total_recoverable_faults"], 0)

    def test_snapshot_schema_and_spatial_coordinates(self):
        sim = NeuroHiveSimulation(seed=42, max_generations=2, fault_rate=0.01)
        snap = sim.snapshot()
        for key in (
            "tick",
            "phase",
            "status",
            "progress_pct",
            "grid",
            "hives",
            "agents",
            "tasks",
            "materials",
            "events",
            "history",
        ):
            self.assertIn(key, snap)
        self.assertIn("stations", snap["grid"])
        self.assertEqual(len(snap["agents"]), 6)
        sim.step()
        after = sim.snapshot()
        self.assertEqual(after["tick"], 1)
        self.assertTrue(any(a["status"] == "working" for a in after["agents"]))

    def test_resupply_and_resource_strategies(self):
        # Auto-resupply enables 4 generations beyond initial 2-hive stock.
        auto_rep = NeuroHiveSimulation(
            seed=42,
            max_generations=4,
            fault_rate=0.0,
            resource_strategy="auto_resupply",
        ).run()
        self.assertEqual(auto_rep["status"], "success")
        self.assertEqual(auto_rep["completed_replications"], 4)
        for mat, initial in INITIAL_STOCK.items():
            supplied = auto_rep["total_resupplied"][mat]
            self.assertEqual(
                auto_rep["material_used"][mat] + auto_rep["material_remaining"][mat],
                initial + supplied,
            )

        # Reserved BOM fails cleanly before consuming materials when 3rd gen lacks stock.
        reserved_rep = NeuroHiveSimulation(
            seed=42,
            max_generations=3,
            fault_rate=0.0,
            resource_strategy="reserved_bom",
        ).run()
        self.assertEqual(reserved_rep["status"], "failed")
        self.assertEqual(reserved_rep["completed_replications"], 2)
        self.assertIn("Insufficient reserved BOM stock", reserved_rep["failure_reason"])

        # Manual resupply unblocks continued production.
        sim = NeuroHiveSimulation(seed=42, max_generations=3, fault_rate=0.0)
        added = sim.resupply(1)
        self.assertGreater(added["aluminium"], 0)
        rep = sim.run()
        self.assertEqual(rep["status"], "success")

    def test_fault_injection_and_maintenance_repair(self):
        sim = NeuroHiveSimulation(
            seed=42,
            max_generations=1,
            fault_rate=0.0,
            agent_counts={
                "fabricator": 2,
                "systems": 1,
                "assembler": 1,
                "inspector": 1,
                "maintenance": 1,
            },
        )
        sim.step()
        rec = sim.inject_fault(agent_id="FAB-01", permanent=False)
        self.assertTrue(rec["injected"])
        self.assertEqual(sim.total_faults, 1)

        perm = sim.inject_fault(agent_id="FAB-01", permanent=True)
        self.assertTrue(perm["injected"])
        self.assertEqual(sim.total_hard_faults, 1)
        fab1 = next(a for a in sim.agents if a.agent_id == "FAB-01")
        self.assertEqual(fab1.status, "offline")

        report = sim.run()
        self.assertEqual(report["status"], "success")
        self.assertGreaterEqual(report["agents"]["MNT-01"]["tasks_completed"], 1)

    def test_travel_physics_records_distance_and_energy(self):
        sim = NeuroHiveSimulation(
            seed=42,
            max_generations=1,
            fault_rate=0.0,
            enable_travel_ticks=True,
        )
        report = sim.run()
        self.assertEqual(report["status"], "success")
        self.assertGreater(report["total_energy_used"], 0.0)
        total_dist = sum(a["distance_traveled"] for a in report["agents"].values())
        self.assertGreater(total_dist, 0.0)

    def test_parameter_sweep_output_and_determinism(self):
        sweep_a = run_parameter_sweep(fault_rates=(0.0, 0.05), generations=1, seeds=(42, 7))
        sweep_b = run_parameter_sweep(fault_rates=(0.0, 0.05), generations=1, seeds=(42, 7))
        self.assertEqual(sweep_a["summary"], sweep_b["summary"])
        self.assertEqual(len(sweep_a["summary"]), 2)
        self.assertEqual(sweep_a["summary"][0]["success_rate"], 100.0)

    def test_web_dashboard_api_endpoints(self):
        server, _controller = create_server(host="127.0.0.1", port=0)
        port = server.server_address[1]
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/") as resp:
                self.assertEqual(resp.status, 200)
                html = resp.read().decode("utf-8")
                self.assertIn("NEUROHIVE 1.0", html)

            with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/state") as resp:
                state = json.loads(resp.read().decode("utf-8"))
                self.assertEqual(state["tick"], 0)

            def post_json(path: str, payload: dict) -> dict:
                req = urllib.request.Request(
                    f"http://127.0.0.1:{port}{path}",
                    data=json.dumps(payload).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(req) as r:
                    return json.loads(r.read().decode("utf-8"))

            stepped = post_json("/api/step", {"count": 3})
            self.assertEqual(stepped["tick"], 3)

            faulted = post_json("/api/inject-fault", {"permanent": False})
            self.assertTrue(faulted["result"]["injected"])

            resupplied = post_json("/api/resupply", {"multiplier": 1})
            self.assertGreater(resupplied["added"]["aluminium"], 0)

            reset_state = post_json("/api/reset", {"seed": 7, "generations": 1})
            self.assertEqual(reset_state["tick"], 0)
            self.assertEqual(reset_state["seed"], 7)

            sweep = post_json("/api/sweep", {"generations": 1})
            self.assertEqual(len(sweep["summary"]), 5)
        finally:
            server.shutdown()
            server.server_close()

    def test_gui_initializes_cleanly(self):
        try:
            root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(f"Tk display unavailable in this environment: {exc}")
            return
        root.withdraw()
        app = NeuroHiveApp(root, seed=42, generations=1, fault_rate=0.0)
        try:
            app.step_once()
            self.assertEqual(app.sim.tick_count, 1)
            app.inject_fault(permanent=False)
            self.assertEqual(app.sim.total_faults, 1)
            app.resupply_bom()
            self.assertGreater(app.sim.total_resupplied["aluminium"], 0)
        finally:
            app.close()


if __name__ == "__main__":
    unittest.main()
