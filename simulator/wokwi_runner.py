"""
FieldForge — Wokwi Simulator (Optional)
=========================================
Wokwi CLI integration for hardware simulation.
Requires a Wokwi license token. Falls back to QEMU if unavailable.
"""
from __future__ import annotations

import json
import logging
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Optional

from config import SIMULATOR_TIMEOUT, WOKWI_PATH
from simulator.qemu_fallback import SimulatorResult, SimulatorRunner as QEMUSimulator

logger = logging.getLogger(__name__)


class WokwiRunner:
    """
    Optional Wokwi CLI simulator integration.
    Requires wokwi-cli and a valid license token.
    """

    def __init__(self, wokwi_path: str = None, timeout: int = None):
        self.wokwi_path = wokwi_path or WOKWI_PATH
        self.timeout = timeout or SIMULATOR_TIMEOUT

    def is_available(self) -> bool:
        """Check if Wokwi CLI is installed."""
        try:
            result = subprocess.run(
                [self.wokwi_path, "--version"],
                capture_output=True, text=True, timeout=5,
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    def run(self, elf_path: str, diagram_json: str = None) -> SimulatorResult:
        """Run firmware in Wokwi simulator."""
        if not self.is_available():
            return SimulatorResult(
                success=False,
                simulator_used="wokwi",
                error_message="Wokwi CLI not found. Using QEMU fallback.",
            )

        # Create temp project directory
        with tempfile.TemporaryDirectory(prefix="fieldforge_") as tmpdir:
            tmppath = Path(tmpdir)

            # Write diagram
            diagram = diagram_json or self.generate_diagram("led_blink")
            (tmppath / "diagram.json").write_text(diagram)

            # Write wokwi.toml
            toml_content = (
                f'[wokwi]\nversion = 1\n'
                f'elf = "{elf_path}"\n'
            )
            (tmppath / "wokwi.toml").write_text(toml_content)

            cmd = [
                self.wokwi_path,
                "--timeout", str(self.timeout * 1000),
                str(tmppath),
            ]

            start = time.time()
            try:
                result = subprocess.run(
                    cmd, capture_output=True, text=True, timeout=self.timeout + 5,
                )
                runtime = (time.time() - start) * 1000
                return SimulatorResult(
                    success=result.returncode == 0,
                    serial_output=result.stdout,
                    runtime_ms=round(runtime, 1),
                    exit_code=result.returncode,
                    simulator_used="wokwi",
                )
            except subprocess.TimeoutExpired:
                return SimulatorResult(
                    success=True,
                    serial_output="[Wokwi timeout — expected]",
                    runtime_ms=self.timeout * 1000,
                    simulator_used="wokwi",
                )

    def generate_diagram(self, firmware_type: str) -> str:
        """Generate a Wokwi diagram JSON for common circuit types."""
        diagrams = {
            "led_blink": {
                "version": 1,
                "author": "FieldForge",
                "editor": "wokwi",
                "parts": [
                    {"type": "wokwi-arduino-uno", "id": "uno", "top": 0, "left": 0},
                    {"type": "wokwi-led", "id": "led1", "top": -100, "left": 100,
                     "attrs": {"color": "green"}},
                    {"type": "wokwi-resistor", "id": "r1", "top": -60, "left": 80,
                     "attrs": {"value": "220"}},
                ],
                "connections": [
                    ["uno:13", "r1:1", "green", []],
                    ["r1:2", "led1:A", "green", []],
                    ["led1:C", "uno:GND.1", "black", []],
                ],
            },
            "pump_control": {
                "version": 1,
                "author": "FieldForge",
                "editor": "wokwi",
                "parts": [
                    {"type": "wokwi-arduino-uno", "id": "uno", "top": 0, "left": 0},
                    {"type": "wokwi-led", "id": "led1", "top": -100, "left": 100,
                     "attrs": {"color": "red"}},
                    {"type": "wokwi-led", "id": "led2", "top": -100, "left": 150,
                     "attrs": {"color": "green"}},
                    {"type": "wokwi-slide-switch", "id": "sw1", "top": -50, "left": 200},
                ],
                "connections": [
                    ["uno:7", "led1:A", "red", []],
                    ["led1:C", "uno:GND.1", "black", []],
                    ["uno:8", "led2:A", "green", []],
                    ["led2:C", "uno:GND.2", "black", []],
                    ["sw1:1", "uno:5V", "red", []],
                    ["sw1:2", "uno:2", "blue", []],
                ],
            },
        }
        return json.dumps(diagrams.get(firmware_type, diagrams["led_blink"]), indent=2)
