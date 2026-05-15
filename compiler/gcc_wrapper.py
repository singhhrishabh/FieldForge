"""
FieldForge — GCC Compiler Wrapper
===================================
Interface to arm-none-eabi-gcc for compiling Gemma 4-generated C code
to ARM Cortex-M0 firmware. Extracts resource metrics for scoring.
"""
from __future__ import annotations

import logging
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

from config import (
    COMPILE_TIMEOUT, GCC_OBJDUMP_PATH, GCC_PATH,
    GCC_SIZE_PATH, LINKER_SCRIPT, OUTPUT_DIR, TEMPLATE_DIR,
)

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# Pydantic Models
# ─────────────────────────────────────────────
class CompileError(BaseModel):
    """A single GCC compilation error or warning."""
    line: int = 0
    column: int = 0
    severity: str = "error"  # "error" | "warning" | "note"
    message: str = ""
    raw: str = ""


class ResourceMetrics(BaseModel):
    """Resource usage metrics extracted from the compiled ELF."""
    binary_size_bytes: int = 0
    instruction_count: int = 0
    estimated_stack_bytes: int = 0
    text_size: int = 0
    data_size: int = 0
    bss_size: int = 0


class EfficiencyScore(BaseModel):
    """Weighted efficiency score computed from resource metrics."""
    overall: float = 0.0
    instruction_score: float = 0.0
    size_score: float = 0.0
    stack_score: float = 0.0
    grade: str = "F"


class CompileResult(BaseModel):
    """Result of a GCC compilation attempt."""
    success: bool = False
    elf_path: str = ""
    errors: list[CompileError] = Field(default_factory=list)
    warnings: list[CompileError] = Field(default_factory=list)
    metrics: Optional[ResourceMetrics] = None
    stdout: str = ""
    stderr: str = ""


class GCCWrapper:
    """
    Wrapper around arm-none-eabi-gcc for cross-compiling
    C firmware to ARM Cortex-M0 ELF binaries.
    """

    def __init__(
        self,
        gcc_path: str = None,
        output_dir: str = None,
        linker_script: str = None,
    ):
        self.gcc_path = gcc_path or self._find_gcc()
        self.output_dir = Path(output_dir or OUTPUT_DIR)
        self.linker_script = linker_script or LINKER_SCRIPT
        self.output_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _find_gcc() -> str:
        """Auto-discover arm-none-eabi-gcc from known paths."""
        import shutil
        candidates = [
            GCC_PATH,
            "/opt/homebrew/bin/arm-none-eabi-gcc",
            "/usr/local/bin/arm-none-eabi-gcc",
        ]
        for path in candidates:
            if shutil.which(path) or os.path.isfile(path):
                return path
        return GCC_PATH  # Fallback to config default

    def _tool_path(self, tool: str) -> str:
        """Derive sibling tool path from gcc_path (e.g. arm-none-eabi-size)."""
        prefix = self.gcc_path.replace("arm-none-eabi-gcc", "")
        return prefix + tool

    def is_available(self) -> bool:
        """Check if the ARM GCC toolchain is installed."""
        try:
            result = subprocess.run(
                [self.gcc_path, "--version"],
                capture_output=True, text=True, timeout=5,
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    def get_version(self) -> str:
        """Return GCC version string."""
        try:
            result = subprocess.run(
                [self.gcc_path, "--version"],
                capture_output=True, text=True, timeout=5,
            )
            return result.stdout.split("\n")[0]
        except Exception:
            return "not found"

    def compile(
        self,
        code: str,
        target: str = "cortex-m0",
        optimization: str = "Os",
        filename: str = "firmware",
    ) -> CompileResult:
        """
        Compile C source code to ARM ELF binary.

        Args:
            code: Complete C source code string.
            target: ARM CPU target (default: cortex-m0).
            optimization: GCC optimization level (default: Os).
            filename: Output filename base (without extension).

        Returns:
            CompileResult with success status, ELF path, errors, and metrics.
        """
        if not self.is_available():
            return CompileResult(
                success=False,
                errors=[CompileError(
                    message=f"{self.gcc_path} not found. Install: brew install --cask gcc-arm-embedded",
                    severity="error",
                )],
            )

        # Write source to temp file
        src_path = self.output_dir / f"{filename}.c"
        elf_path = self.output_dir / f"{filename}.elf"
        map_path = self.output_dir / f"{filename}.map"

        src_path.write_text(code, encoding="utf-8")
        logger.info(f"Source written: {src_path} ({len(code)} chars)")

        # Build GCC command
        cmd = [
            self.gcc_path,
            f"-mcpu={target}",
            f"-O{optimization}",
            "-mthumb",
            "-nostdlib",
            "-nostartfiles",
            f"-T{self.linker_script}",
            f"-Wl,-Map={map_path}",
            "-Wall",
            "-Wextra",
            str(src_path),
            "-o", str(elf_path),
        ]

        logger.info(f"Compiling: {' '.join(cmd)}")

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=COMPILE_TIMEOUT,
                cwd=str(self.output_dir),
            )

            errors, warnings = self._parse_gcc_output(result.stderr)

            if result.returncode == 0 and elf_path.exists():
                metrics = self.extract_metrics(str(elf_path))
                logger.info(f"Compilation successful: {elf_path}")
                return CompileResult(
                    success=True,
                    elf_path=str(elf_path),
                    errors=[],
                    warnings=warnings,
                    metrics=metrics,
                    stdout=result.stdout,
                    stderr=result.stderr,
                )
            else:
                logger.warning(f"Compilation failed: {len(errors)} errors")
                return CompileResult(
                    success=False,
                    errors=errors,
                    warnings=warnings,
                    stdout=result.stdout,
                    stderr=result.stderr,
                )

        except subprocess.TimeoutExpired:
            return CompileResult(
                success=False,
                errors=[CompileError(
                    message=f"Compilation timed out after {COMPILE_TIMEOUT}s",
                    severity="error",
                )],
            )
        except Exception as e:
            return CompileResult(
                success=False,
                errors=[CompileError(message=str(e), severity="error")],
            )

    def extract_metrics(self, elf_path: str) -> ResourceMetrics:
        """
        Extract resource metrics from a compiled ELF file.

        Uses arm-none-eabi-size for section sizes and
        arm-none-eabi-objdump for instruction count and stack analysis.
        """
        metrics = ResourceMetrics()

        # --- Section sizes via arm-none-eabi-size ---
        try:
            result = subprocess.run(
                [self._tool_path("arm-none-eabi-size"), elf_path],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0:
                lines = result.stdout.strip().split("\n")
                if len(lines) >= 2:
                    parts = lines[1].split()
                    if len(parts) >= 4:
                        metrics.text_size = int(parts[0])
                        metrics.data_size = int(parts[1])
                        metrics.bss_size = int(parts[2])
                        metrics.binary_size_bytes = int(parts[3])
        except Exception as e:
            logger.warning(f"arm-none-eabi-size failed: {e}")

        # --- Instruction count + stack via objdump ---
        try:
            result = subprocess.run(
                [self._tool_path("arm-none-eabi-objdump"), "-d", elf_path],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0:
                disasm = result.stdout
                # Count instruction lines (hex address followed by instruction)
                instr_pattern = re.compile(r"^\s+[0-9a-f]+:\s+[0-9a-f]+", re.MULTILINE)
                metrics.instruction_count = len(instr_pattern.findall(disasm))

                # Estimate stack by counting PUSH instructions and their register counts
                push_pattern = re.compile(r"push\s+\{([^}]+)\}", re.IGNORECASE)
                max_push = 0
                for match in push_pattern.finditer(disasm):
                    regs = match.group(1).split(",")
                    max_push = max(max_push, len(regs))
                # Each pushed register = 4 bytes, add 256 for locals estimate
                metrics.estimated_stack_bytes = (max_push * 4) + 256

        except Exception as e:
            logger.warning(f"arm-none-eabi-objdump failed: {e}")

        logger.info(
            f"Metrics: {metrics.binary_size_bytes}B binary, "
            f"{metrics.instruction_count} instructions, "
            f"{metrics.estimated_stack_bytes}B stack"
        )
        return metrics

    def score(self, metrics: ResourceMetrics) -> EfficiencyScore:
        """
        Compute an efficiency score from resource metrics.

        Scoring:
        - instruction_score: 100 * (1 - min(count/5000, 1))
        - size_score:        100 * (1 - min(bytes/32768, 1))
        - stack_score:       100 * (1 - min(stack/2048, 1))
        - overall: 40% instruction + 40% size + 20% stack
        """
        i_score = 100.0 * (1.0 - min(metrics.instruction_count / 5000.0, 1.0))
        s_score = 100.0 * (1.0 - min(metrics.binary_size_bytes / 32768.0, 1.0))
        k_score = 100.0 * (1.0 - min(metrics.estimated_stack_bytes / 2048.0, 1.0))
        overall = (i_score * 0.4) + (s_score * 0.4) + (k_score * 0.2)

        if overall >= 85:
            grade = "A"
        elif overall >= 70:
            grade = "B"
        elif overall >= 50:
            grade = "C"
        else:
            grade = "F"

        return EfficiencyScore(
            overall=round(overall, 1),
            instruction_score=round(i_score, 1),
            size_score=round(s_score, 1),
            stack_score=round(k_score, 1),
            grade=grade,
        )

    def _parse_gcc_output(self, stderr: str) -> tuple[list[CompileError], list[CompileError]]:
        """Parse GCC stderr into structured error and warning lists."""
        errors = []
        warnings = []

        # GCC format: file.c:line:col: error/warning: message
        pattern = re.compile(
            r"([^:]+):(\d+):(\d+):\s+(error|warning|note):\s+(.+)"
        )

        for line in stderr.split("\n"):
            match = pattern.match(line.strip())
            if match:
                entry = CompileError(
                    line=int(match.group(2)),
                    column=int(match.group(3)),
                    severity=match.group(4),
                    message=match.group(5),
                    raw=line.strip(),
                )
                if entry.severity == "error":
                    errors.append(entry)
                else:
                    warnings.append(entry)
            elif "error:" in line.lower():
                errors.append(CompileError(message=line.strip(), severity="error", raw=line.strip()))
            elif "undefined reference" in line.lower():
                errors.append(CompileError(message=line.strip(), severity="error", raw=line.strip()))

        return errors, warnings
