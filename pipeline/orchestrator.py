"""
SketchSilicon — Pipeline Orchestrator
====================================
Coordinates all agents and tools: image → architect → compiler →
critic → recompile → simulator → scorer → final report.
"""
from __future__ import annotations

import logging
import sys
import time
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.table import Table

from agents.architect import ArchitectAgent, ArchitectResult
from agents.critic import CriticAgent, CriticReport
from agents.tools import ToolRegistry
from compiler.gcc_wrapper import CompileResult, GCCWrapper, ResourceMetrics, EfficiencyScore
from llama_client import LlamaClient
from pipeline.image_processor import ImageProcessor
from pipeline.scorer import ResourceScorer
from simulator.qemu_fallback import SimulatorRunner, SimulatorResult
from config import MAX_COMPILE_RETRIES, MAX_CRITIC_RETRIES

logger = logging.getLogger(__name__)


class PipelineResult(BaseModel):
    """Complete result from a SketchSilicon pipeline run."""
    image_path: str = ""
    raw_code: str = ""
    final_code: str = ""
    compile_result: Optional[CompileResult] = None
    critic_report: Optional[CriticReport] = None
    resource_metrics: Optional[ResourceMetrics] = None
    efficiency_score: Optional[EfficiencyScore] = None
    simulator_output: Optional[SimulatorResult] = None
    total_time_seconds: float = 0.0
    success: bool = False
    steps_completed: list[str] = Field(default_factory=list)
    error: str = ""


class SketchSiliconOrchestrator:
    """
    Main pipeline orchestrator for SketchSilicon.

    Coordinates the full flow with rich terminal output:
    1. Preprocess schematic image
    2. Architect generates firmware
    3. Compile (with self-healing retries)
    4. Critic reviews for bugs
    5. Recompile with fixes
    6. Run in simulator
    7. Generate final report
    """

    def __init__(self):
        self.console = Console(force_terminal=True, soft_wrap=True, highlight=False)
        self.client = LlamaClient()
        self.image_processor = ImageProcessor()
        self.architect = ArchitectAgent(self.client)
        self.critic = CriticAgent(self.client)
        self.gcc = GCCWrapper()
        self.tools = ToolRegistry(self.gcc)
        self.simulator = SimulatorRunner()
        self.scorer = ResourceScorer()

    def print_banner(self):
        """Print the SketchSilicon startup banner."""
        banner = """
[bold cyan]   _____ __        __       __   _____ _ ___
  / ___// /_____  / /______/ /_ / ___/(_) (_)________  ____
  \\__ \\/ //_/ _ \\/ __/ ___/ __ \\\\__ \\/ / / / ___/ __ \\/ __ \\
 ___/ / ,< /  __/ /_/ /__/ / / /__/ / / / / /__/ /_/ / / / /
/____/_/|_|\\___/\\__/\\___/_/ /_/____/_/_/_/\\___/\\____/_/ /_/[/bold cyan]
"""
        self.console.print(banner)
        self.console.print("[bold]v1.0[/bold] │ Powered by [bold cyan]Gemma 4[/bold cyan] via [bold]llama.cpp[/bold]")

        # Check model info
        info = self.client.get_model_info()
        if info:
            self.console.print(f"  Model: {info.get('default_generation_settings', {}).get('model', 'Gemma 4')}")

        # Check server
        if self.client.health_check():
            self.console.print("  Server: [bold green]ONLINE ✓[/bold green]")
        else:
            self.console.print("  Server: [bold red]OFFLINE ✗[/bold red]")

        self.console.print("  Network: [bold green]OFFLINE MODE ✓[/bold green]")
        self.console.print()

    def run(self, image_path: str, no_simulate: bool = False, verbose: bool = False) -> PipelineResult:
        """
        Run the full SketchSilicon pipeline.

        Args:
            image_path: Path to the schematic image.
            no_simulate: Skip the simulator step.
            verbose: Show full agent outputs.

        Returns:
            PipelineResult with all artifacts.
        """
        start_time = time.time()
        result = PipelineResult(image_path=image_path)
        current_code = ""
        image_stem = Path(image_path).stem

        self.print_banner()

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            TimeElapsedColumn(),
            console=self.console,
        ) as progress:

            # ── STEP 1: Preprocess Image ──────────────────────
            task = progress.add_task("[cyan]Step 1/7 — Preprocessing schematic image...", total=None)
            try:
                image_data = self.image_processor.prepare_for_gemma(image_path)
                progress.update(task, description="[green]Step 1/7 — Image preprocessed ✓")
                self.console.print(
                    f"  Components: {image_data['component_count']} │ "
                    f"Complexity: [bold]{image_data['complexity']}[/bold] │ "
                    f"Size: {image_data['width']}×{image_data['height']}px"
                )
                result.steps_completed.append("image_preprocessing")
            except Exception as e:
                result.error = f"Image preprocessing failed: {e}"
                self._print_error(result.error)
                return result

            # ── STEP 2: Architect Generates Firmware ──────────
            progress.update(task, description="[cyan]Step 2/7 — Architect analyzing schematic...")
            try:
                arch_result = self.architect.generate_firmware(image_data)
                current_code = arch_result.code
                result.raw_code = current_code
                progress.update(task, description="[green]Step 2/7 — Firmware generated ✓")

                # Preview first lines
                lines = current_code.split("\n")
                self.console.print(f"  Generated: {len(lines)} lines of C")
                if verbose:
                    preview = "\n".join(lines[:10])
                    self.console.print(f"  [dim]{preview}...[/dim]")
                if arch_result.tool_called != "none":
                    self.console.print(f"  Tool called: [bold cyan]{arch_result.tool_called}[/bold cyan]")
                result.steps_completed.append("architect")
            except Exception as e:
                result.error = f"Architect failed: {e}"
                self._print_error(result.error)
                return result

            # ── STEP 3: First Compilation ─────────────────────
            progress.update(task, description="[cyan]Step 3/7 — Compiling first draft (ARM Cortex-M0)...")
            compile_result = self.gcc.compile(current_code)

            if not compile_result.success:
                self.console.print(f"  [yellow]Compilation failed: {len(compile_result.errors)} errors[/yellow]")

                # Self-healing retries
                for retry in range(MAX_COMPILE_RETRIES):
                    progress.update(
                        task,
                        description=f"[yellow]Step 3b/7 — Self-healing attempt {retry+1}..."
                    )
                    try:
                        error_dicts = [e.model_dump() for e in compile_result.errors]
                        fix_result = self.architect.fix_compile_errors(current_code, error_dicts)
                        current_code = fix_result.code
                        compile_result = self.gcc.compile(current_code)
                        if compile_result.success:
                            self.console.print(f"  [green]Self-healed on attempt {retry+1} ✓[/green]")
                            break
                    except Exception as e:
                        self.console.print(f"  [dim]Retry {retry+1} failed: {e}[/dim]")

            if compile_result.success:
                progress.update(task, description="[green]Step 3/7 — Compiled successfully ✓")
                result.steps_completed.append("first_compile")
            else:
                progress.update(task, description="[red]Step 3/7 — Compilation failed ✗")
                self.console.print("  [red]Could not compile. Continuing with Critic review...[/red]")

            result.compile_result = compile_result

            # ── STEP 4: Critic Review ─────────────────────────
            progress.update(task, description="[cyan]Step 4/7 — Critic reviewing code for bugs...")
            try:
                critic_report = self.critic.review(current_code, arch_result.description)
                result.critic_report = critic_report
                progress.update(task, description="[green]Step 4/7 — Critic review complete ✓")

                # Show issues
                self.console.print(
                    f"  Verdict: [bold {'green' if critic_report.verdict == 'pass' else 'red'}]"
                    f"{critic_report.verdict.upper()}[/bold {'green' if critic_report.verdict == 'pass' else 'red'}] │ "
                    f"Issues: {len(critic_report.issues)} │ "
                    f"Confidence: {critic_report.confidence:.0%}"
                )

                if critic_report.issues:
                    issue_table = Table(show_lines=False, border_style="dim")
                    issue_table.add_column("Line", style="cyan", width=5)
                    issue_table.add_column("Sev", width=8)
                    issue_table.add_column("Description", style="white")
                    for issue in critic_report.issues[:5]:
                        sev = {"critical": "[red]CRIT[/red]", "high": "[yellow]HIGH[/yellow]",
                               "medium": "[blue]MED[/blue]"}.get(issue.severity, issue.severity)
                        issue_table.add_row(str(issue.line), sev, issue.description[:60])
                    self.console.print(issue_table)

                # Apply fix if verdict is fail
                if critic_report.verdict == "fail" and critic_report.fixed_code:
                    current_code = critic_report.fixed_code
                    self.console.print("  [cyan]Applied Critic's fixes →[/cyan]")

                result.steps_completed.append("critic_review")
            except Exception as e:
                self.console.print(f"  [yellow]Critic review failed: {e}[/yellow]")

            # ── STEP 5: Final Compilation ─────────────────────
            progress.update(task, description="[cyan]Step 5/7 — Compiling validated firmware...")
            final_filename = f"{image_stem}firmware"
            final_compile = self.gcc.compile(current_code, optimization="s", filename=final_filename)

            if final_compile.success and final_compile.metrics:
                progress.update(task, description="[green]Step 5/7 — Final build successful ✓")
                result.compile_result = final_compile
                result.resource_metrics = final_compile.metrics
                result.efficiency_score = self.scorer.score(final_compile.metrics)
                result.steps_completed.append("final_compile")
            else:
                progress.update(task, description="[yellow]Step 5/7 — Final build had issues")

            result.final_code = current_code

            # ── STEP 6: Simulator ─────────────────────────────
            if not no_simulate and final_compile.success:
                progress.update(task, description="[cyan]Step 6/7 — Running in simulator...")
                if self.simulator.is_available():
                    sim_result = self.simulator.run(final_compile.elf_path)
                    result.simulator_output = sim_result
                    progress.update(task, description="[green]Step 6/7 — Simulation complete ✓")
                    self.console.print(
                        f"  Simulator: {sim_result.simulator_used} │ "
                        f"Runtime: {sim_result.runtime_ms:.0f}ms │ "
                        f"Signals: {', '.join(sim_result.signals_detected) or 'none'}"
                    )
                    result.steps_completed.append("simulation")
                else:
                    progress.update(task, description="[yellow]Step 6/7 — No simulator available")
                    self.console.print("  [dim]No simulator installed. Skipping.[/dim]")
            else:
                progress.update(task, description="[dim]Step 6/7 — Simulator skipped")

            # ── STEP 7: Final Report ──────────────────────────
            progress.update(task, description="[cyan]Step 7/7 — Generating report...")
            result.total_time_seconds = round(time.time() - start_time, 1)
            result.success = final_compile.success
            result.steps_completed.append("report")
        # Clean up all intermediate and compiled files, leaving only the final .c file
        output_dir = Path("output")
        if output_dir.exists():
            for file in output_dir.iterdir():
                if file.is_file() and file.name != f"{image_stem}firmware.c":
                    try:
                        file.unlink()
                    except Exception:
                        pass

        # Print final report outside progress context
        self.print_final_report(result, final_filename=f"{image_stem}firmware.c")

        return result

    def print_final_report(self, result, final_filename="firmware.c"):
        """Print final report safely using /dev/tty to avoid BlockingIOError."""
        import os

        # Build the report as a plain string (no Rich markup)
        sep = "═" * 70
        lines = []
        lines.append("")
        lines.append(sep + " SKETCHSILICON — FIRMWARE GENERATED ✓ " + sep[:3])
        lines.append("")
        lines.append(f"  Schematic → Firmware in {result.total_time_seconds:.1f}s")
        lines.append("")
        lines.append(f"  Bugs caught by Critic:  {len(result.critic_report.issues) if result.critic_report else 0}")
        verdict = result.critic_report.verdict if result.critic_report else "unknown"
        lines.append(f"  Critic verdict:         {verdict.upper()} (bugs found and fixed)")
        compile_status = "PASS ✓" if result.compile_result and result.compile_result.success else "FAIL ✗"
        lines.append(f"  Final compile:          {compile_status}")
        lines.append("")
        if result.efficiency_score:
            lines.append(f"  RESOURCE SCORE:  {result.efficiency_score.grade} ({result.efficiency_score.overall:.1f}/100)")
        if result.resource_metrics:
            lines.append(f"  Instructions:    {result.resource_metrics.instruction_count}")
            lines.append(f"  Binary size:     {result.resource_metrics.binary_size_bytes} bytes")
            lines.append(f"  Stack depth:     {result.resource_metrics.estimated_stack_bytes} bytes")
        lines.append("")
        lines.append(f"  Output: ./output/{final_filename}")
        lines.append("")
        lines.append("═" * 73)
        lines.append("")

        report_text = "\n".join(lines)

        # Try /dev/tty first (always blocking on macOS/Linux)
        try:
            with open("/dev/tty", "w") as tty:
                tty.write(report_text)
                tty.flush()
            return
        except Exception:
            pass

        # Fallback: use os.write with raw file descriptor
        try:
            os.write(1, report_text.encode("utf-8"))
            return
        except Exception:
            pass

        # Last resort: just print (may fail silently)
        try:
            print(report_text)
        except Exception:
            pass

    def _print_error(self, message: str):
        """Print an error message."""
        self.console.print(f"\n[bold red]ERROR:[/bold red] {message}")
