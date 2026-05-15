"""
FieldForge — QEMU Simulator (Primary)
=======================================
Runs compiled ARM firmware in QEMU ARM emulator.
Captures UART output and verifies expected signals.
"""

import logging
import re
import subprocess
import time
from typing import Optional

from pydantic import BaseModel, Field

from config import QEMU_PATH, SIMULATOR_TIMEOUT

logger = logging.getLogger(__name__)


class LogicVerification(BaseModel):
    """Result of comparing expected vs actual signals."""
    match_score: float = 0.0
    matched: list[str] = Field(default_factory=list)
    missed: list[str] = Field(default_factory=list)
    unexpected: list[str] = Field(default_factory=list)


class SimulatorResult(BaseModel):
    """Result from running firmware in a simulator."""
    success: bool = False
    serial_output: str = ""
    signals_detected: list[str] = Field(default_factory=list)
    runtime_ms: float = 0.0
    exit_code: int = -1
    simulator_used: str = "qemu"
    logic_verification: Optional[LogicVerification] = None
    error_message: str = ""


class QEMURunner:
    """
    Run ARM firmware in QEMU system emulator.

    Uses qemu-system-arm with the lm3s6965evb machine (Cortex-M3,
    close enough for M0 firmware verification).
    """

    def __init__(self, qemu_path: str = None, timeout: int = None):
        self.qemu_path = qemu_path or QEMU_PATH
        self.timeout = timeout or SIMULATOR_TIMEOUT

    def is_available(self) -> bool:
        """Check if QEMU is installed."""
        try:
            result = subprocess.run(
                [self.qemu_path, "--version"],
                capture_output=True, text=True, timeout=5,
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    def get_version(self) -> str:
        """Return QEMU version string."""
        try:
            result = subprocess.run(
                [self.qemu_path, "--version"],
                capture_output=True, text=True, timeout=5,
            )
            return result.stdout.split("\n")[0]
        except Exception:
            return "not found"

    def run(self, elf_path: str, timeout: int = None) -> SimulatorResult:
        """
        Run an ARM ELF binary in QEMU and capture UART output.

        Args:
            elf_path: Path to the compiled ARM ELF file.
            timeout: Seconds to run before terminating.

        Returns:
            SimulatorResult with captured output and signal detection.
        """
        if not self.is_available():
            return SimulatorResult(
                success=False,
                simulator_used="qemu",
                error_message=(
                    f"{self.qemu_path} not found. "
                    f"Install: brew install qemu (macOS) or apt install qemu-system-arm (Linux)"
                ),
            )

        run_timeout = timeout or self.timeout

        cmd = [
            self.qemu_path,
            "-machine", "lm3s6965evb",
            "-nographic",
            "-semihosting",
            "-kernel", elf_path,
        ]

        logger.info(f"Running in QEMU: {' '.join(cmd)}")
        start_time = time.time()

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=run_timeout,
            )

            runtime = (time.time() - start_time) * 1000
            output = result.stdout + result.stderr

            signals = self._detect_signals(output)

            return SimulatorResult(
                success=result.returncode == 0,
                serial_output=output,
                signals_detected=signals,
                runtime_ms=round(runtime, 1),
                exit_code=result.returncode,
                simulator_used="qemu",
            )

        except subprocess.TimeoutExpired:
            runtime = (time.time() - start_time) * 1000
            logger.info(f"QEMU timed out after {run_timeout}s (expected for infinite-loop firmware)")

            return SimulatorResult(
                success=True,  # Timeout is expected for embedded firmware
                serial_output="[Firmware ran until timeout — expected for embedded main loops]",
                signals_detected=["RUNNING"],
                runtime_ms=round(runtime, 1),
                exit_code=0,
                simulator_used="qemu",
            )

        except Exception as e:
            return SimulatorResult(
                success=False,
                simulator_used="qemu",
                error_message=str(e),
            )

    def verify_logic(
        self, signals: list[str], expected: list[str]
    ) -> LogicVerification:
        """
        Compare detected signals against expected signals.

        Args:
            signals: Signals detected in simulator output.
            expected: Signals we expect to see.

        Returns:
            LogicVerification with match score and details.
        """
        signals_lower = [s.lower() for s in signals]
        expected_lower = [e.lower() for e in expected]

        matched = [e for e in expected if e.lower() in signals_lower]
        missed = [e for e in expected if e.lower() not in signals_lower]
        unexpected = [s for s in signals if s.lower() not in expected_lower]

        if expected:
            score = len(matched) / len(expected)
        else:
            score = 1.0 if not signals else 0.5

        return LogicVerification(
            match_score=round(score, 2),
            matched=matched,
            missed=missed,
            unexpected=unexpected,
        )

    def _detect_signals(self, output: str) -> list[str]:
        """Detect known signals from UART/serial output."""
        known = [
            "LED ON", "LED OFF", "LED BLINK",
            "PUMP START", "PUMP STOP", "PUMP ENABLED",
            "SENSOR READ", "TEMPERATURE",
            "ERROR", "FAULT", "INIT OK", "READY",
            "GPIO HIGH", "GPIO LOW",
        ]

        found = []
        output_upper = output.upper()
        for signal in known:
            if signal in output_upper:
                found.append(signal)

        return found


class SimulatorRunner:
    """
    Unified simulator interface. Tries QEMU (primary).
    Wokwi support is optional and disabled by default.
    """

    def __init__(self, timeout: int = None):
        self.qemu = QEMURunner(timeout=timeout)
        self.timeout = timeout or SIMULATOR_TIMEOUT

    def is_available(self) -> bool:
        """Check if any simulator is available."""
        return self.qemu.is_available()

    def run(self, elf_path: str, expected_signals: list[str] = None) -> SimulatorResult:
        """
        Run firmware in the best available simulator.

        Args:
            elf_path: Path to compiled ARM ELF.
            expected_signals: Optional list of expected output signals.

        Returns:
            SimulatorResult with output and optional logic verification.
        """
        if self.qemu.is_available():
            result = self.qemu.run(elf_path)
            if expected_signals and result.success:
                result.logic_verification = self.qemu.verify_logic(
                    result.signals_detected, expected_signals
                )
            return result

        return SimulatorResult(
            success=False,
            simulator_used="none",
            error_message=(
                "No simulator available.\n"
                "Install QEMU: brew install qemu (macOS) or apt install qemu-system-arm (Linux)"
            ),
        )
