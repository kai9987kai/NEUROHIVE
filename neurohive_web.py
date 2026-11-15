#!/usr/bin/env python3
"""NeuroHive 1.0 Live Web Dashboard Server (standard-library HTTP + JSON API)."""
from __future__ import annotations

import json
import socket
import threading
import webbrowser
from functools import partial
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Optional

from neurohive import NeuroHiveSimulation, run_parameter_sweep


class SimulationController:
    """Thread-safe controller managing a live NeuroHiveSimulation instance."""

    def __init__(
        self,
        seed: int = 42,
        generations: int = 2,
        fault_rate: float = 0.01,
        permanent_fault_rate: float = 0.0,
        resource_strategy: str = "standard",
        enable_travel_ticks: bool = False,
        max_ticks: int = 2000,
        maintenance_bot: bool = False,
    ):
        self._lock = threading.Lock()
        self.params: Dict[str, Any] = {
            "seed": seed,
            "generations": generations,
            "fault_rate": fault_rate,
            "permanent_fault_rate": permanent_fault_rate,
            "resource_strategy": resource_strategy,
            "enable_travel_ticks": enable_travel_ticks,
            "max_ticks": max_ticks,
            "maintenance_bot": maintenance_bot,
        }
        self.sim = self._build_sim(self.params)

    @staticmethod
    def _build_sim(params: Dict[str, Any]) -> NeuroHiveSimulation:
        agent_counts = None
        if params.get("maintenance_bot"):
            agent_counts = {
                "fabricator": 2,
                "systems": 1,
                "assembler": 2,
                "inspector": 1,
                "maintenance": 1,
            }
        return NeuroHiveSimulation(
            seed=int(params.get("seed", 42)),
            max_generations=int(params.get("generations", 2)),
            fault_rate=float(params.get("fault_rate", 0.01)),
            max_ticks=int(params.get("max_ticks", 2000)),
            permanent_fault_rate=float(params.get("permanent_fault_rate", 0.0)),
            resource_strategy=str(params.get("resource_strategy", "standard")),
            enable_travel_ticks=bool(params.get("enable_travel_ticks", False)),
            agent_counts=agent_counts,
        )

    def get_state(self) -> dict:
        with self._lock:
            return self.sim.snapshot()

    def get_report(self) -> dict:
        with self._lock:
            return self.sim.report()

    def step(self, count: int = 1) -> dict:
        steps = max(1, min(100, int(count)))
        with self._lock:
            for _ in range(steps):
                if self.sim.phase == "complete" or self.sim.failed:
                    break
                self.sim.step()
            return self.sim.snapshot()

    def reset(self, new_params: Optional[Dict[str, Any]] = None) -> dict:
        with self._lock:
            merged = dict(self.params)
            if new_params:
                merged.update(new_params)
            sim = self._build_sim(merged)
            self.params = merged
            self.sim = sim
            return self.sim.snapshot()

    def inject_fault(
        self, agent_id: Optional[str] = None, permanent: bool = False
    ) -> dict:
        with self._lock:
            result = self.sim.inject_fault(agent_id=agent_id, permanent=permanent)
            return {"result": result, "state": self.sim.snapshot()}

    def resupply(self, multiplier: int = 1) -> dict:
        with self._lock:
            added = self.sim.resupply(multiplier=int(multiplier))
            return {"added": added, "state": self.sim.snapshot()}

    def sweep(self, params: Optional[Dict[str, Any]] = None) -> dict:
        with self._lock:
            cfg = dict(self.params)
        if params:
            cfg.update(params)
        return run_parameter_sweep(
            generations=int(cfg.get("generations", 2)),
            max_ticks=int(cfg.get("max_ticks", 2000)),
            resource_strategy=str(cfg.get("resource_strategy", "standard")),
            permanent_fault_rate=float(cfg.get("permanent_fault_rate", 0.0)),
        )


class NeuroHiveRequestHandler(BaseHTTPRequestHandler):
    """HTTP request handler serving the NeuroHive live dashboard and JSON API."""

    def __init__(self, *args, controller: SimulationController, **kwargs):
        self.controller = controller
        self.dashboard_path = Path(__file__).with_name("dashboard.html")
        super().__init__(*args, **kwargs)

    def log_message(self, format: str, *args) -> None:
        # Keep stdout clean when running interactively or in tests.
        return

    def _send_json(self, payload: dict, status: int = HTTPStatus.OK) -> None:
        raw = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    def _read_json_body(self) -> dict:
        length = int(self.headers.get("Content-Length", "0") or 0)
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        if not raw:
            return {}
        return json.loads(raw.decode("utf-8"))

    def do_GET(self) -> None:
        if self.path in ("/", "/index.html", "/dashboard.html"):
            if not self.dashboard_path.exists():
                self._send_json(
                    {"error": "dashboard.html not found"}, status=HTTPStatus.NOT_FOUND
                )
                return
            html = self.dashboard_path.read_bytes()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(html)))
            self.end_headers()
            self.wfile.write(html)
            return

        if self.path == "/api/state":
            self._send_json(self.controller.get_state())
            return

        if self.path == "/api/report":
            self._send_json(self.controller.get_report())
            return

        self._send_json({"error": "Not found"}, status=HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        try:
            body = self._read_json_body()
        except json.JSONDecodeError as exc:
            self._send_json(
                {"error": f"Invalid JSON payload: {exc}"}, status=HTTPStatus.BAD_REQUEST
            )
            return

        try:
            if self.path == "/api/step":
                count = int(body.get("count", 1))
                self._send_json(self.controller.step(count))
                return

            if self.path == "/api/reset":
                self._send_json(self.controller.reset(body))
                return

            if self.path == "/api/inject-fault":
                agent_id = body.get("agent_id")
                permanent = bool(body.get("permanent", False))
                self._send_json(self.controller.inject_fault(agent_id, permanent))
                return

            if self.path == "/api/resupply":
                multiplier = int(body.get("multiplier", 1))
                self._send_json(self.controller.resupply(multiplier))
                return

            if self.path == "/api/sweep":
                self._send_json(self.controller.sweep(body))
                return
        except (ValueError, TypeError) as exc:
            self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
            return

        self._send_json({"error": "Not found"}, status=HTTPStatus.NOT_FOUND)


class ExclusiveHTTPServer(ThreadingHTTPServer):
    """HTTP server that refuses silent port double-binding on Windows."""

    allow_reuse_address = False

    def server_bind(self) -> None:
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


def create_server(
    host: str = "127.0.0.1",
    port: int = 8765,
    auto_port: bool = False,
    **sim_kwargs,
) -> tuple[ThreadingHTTPServer, SimulationController]:
    controller = SimulationController(**sim_kwargs)
    handler = partial(NeuroHiveRequestHandler, controller=controller)
    candidates = [port]
    if auto_port:
        candidates.extend([p for p in range(8790, 8811) if p != port])
        candidates.append(0)
    last_err: Optional[OSError] = None
    for cand in candidates:
        try:
            server = ExclusiveHTTPServer((host, cand), handler)
            return server, controller
        except OSError as exc:
            last_err = exc
    assert last_err is not None
    raise last_err


def launch_web_dashboard(
    port: int = 8765,
    open_browser: bool = True,
    **sim_kwargs,
) -> None:
    server, _controller = create_server(
        host="127.0.0.1", port=port, auto_port=True, **sim_kwargs
    )
    actual_port = server.server_address[1]
    url = f"http://127.0.0.1:{actual_port}/"
    print(f"NeuroHive 1.0 Live Web Dashboard running at {url}", flush=True)
    print("Press Ctrl+C to stop.", flush=True)
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down NeuroHive Web Dashboard...", flush=True)
    finally:
        server.server_close()


if __name__ == "__main__":
    launch_web_dashboard()
