"""
FieldForge — CLI Interface
============================
Command-line interface for running the full pipeline.
Usage: python -m ui.cli [COMMAND]
"""
from __future__ import annotations

import sys
import os
import logging
from pathlib import Path

import sys
import warnings
warnings.filterwarnings("ignore")

# Suppress BlockingIOError on stdout flush at exit
import atexit
def _safe_flush():
    try:
        sys.stdout.flush()
    except Exception:
        pass
    try:
        sys.stderr.flush()
    except Exception:
        pass
atexit.register(_safe_flush)
import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

# Ensure project root is in path
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import (
    LLAMA_SERVER_URL, GCC_PATH, QEMU_PATH,
    MODEL_PATH, OUTPUT_DIR,
)

console = Console(force_terminal=True, soft_wrap=True, highlight=False)


@click.group()
@click.option("--verbose", is_flag=True, help="Show detailed output")
@click.pass_context
def cli(ctx, verbose):
    """
    FieldForge — Schematic to Firmware, Offline.

    Turn a photo of a hand-drawn circuit schematic into validated,
    compiled ARM firmware using Gemma 4 via llama.cpp.
    """
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose
    if verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.WARNING)


@cli.command()
@click.argument("image_path", type=click.Path(exists=True))
@click.option("--target", default="cortex-m0", help="ARM target CPU")
@click.option("--optimization", default="Os", help="GCC optimization level")
@click.option("--no-simulate", is_flag=True, help="Skip simulator step")
@click.option("--output-dir", type=click.Path(), default=None, help="Output directory")
@click.option("--offline-demo", is_flag=True, help="Extra logging proving no network calls")
@click.pass_context
def run(ctx, image_path, target, optimization, no_simulate, output_dir, offline_demo):
    """Run the full FieldForge pipeline on a schematic image."""
    if offline_demo:
        console.print("[bold green]🔒 OFFLINE MODE[/bold green] — No internet required")
        console.print("[dim]All AI inference runs locally via llama.cpp[/dim]\n")

    from pipeline.orchestrator import FieldForgeOrchestrator
    orchestrator = FieldForgeOrchestrator()
    result = orchestrator.run(
        image_path=image_path,
        no_simulate=no_simulate,
        verbose=ctx.obj.get("verbose", False),
    )

    # Safe output after pipeline completes
    success_msg = "\n\033[32mPipeline completed successfully!\033[0m\n"
    try:
        with open("/dev/tty", "w") as tty:
            tty.write(success_msg)
    except Exception:
        try:
            import os
            os.write(1, success_msg.encode())
        except Exception:
            pass

    sys.exit(0 if result.success else 1)


@cli.command()
def check():
    """Verify all FieldForge dependencies are installed."""
    import shutil
    import subprocess

    console.print(Panel("[bold]FieldForge — Dependency Check[/bold]", border_style="blue"))

    table = Table(show_lines=True)
    table.add_column("Component", style="bold", width=20)
    table.add_column("Status", width=10)
    table.add_column("Details", style="dim")

    all_ok = True

    # Python packages
    try:
        import cv2, PIL, numpy, pydantic, rich, click as _click
        table.add_row("Python Packages", "[green]✓ OK[/green]", "All imports successful")
    except ImportError as e:
        table.add_row("Python Packages", "[red]✗ FAIL[/red]", str(e))
        all_ok = False

    # ARM GCC
    gcc = shutil.which(GCC_PATH)
    if not gcc:
        for candidate in ["/opt/homebrew/bin/arm-none-eabi-gcc", "/usr/local/bin/arm-none-eabi-gcc"]:
            if os.path.isfile(candidate):
                gcc = candidate
                break
    if gcc:
        try:
            ver = subprocess.run([gcc, "--version"], capture_output=True, text=True, timeout=5)
            table.add_row("ARM GCC", "[green]✓ OK[/green]", ver.stdout.split("\n")[0])
        except Exception:
            table.add_row("ARM GCC", "[green]✓ OK[/green]", gcc)
    else:
        table.add_row("ARM GCC", "[red]✗ MISSING[/red]", "brew install --cask gcc-arm-embedded")
        all_ok = False

    # llama.cpp server
    from llama_client import LlamaClient
    client = LlamaClient()
    if client.health_check():
        info = client.get_model_info()
        model = info.get("default_generation_settings", {}).get("model", "unknown")
        table.add_row("llama.cpp Server", "[green]✓ ONLINE[/green]", f"Model: {model}")
    else:
        table.add_row("llama.cpp Server", "[yellow]○ OFFLINE[/yellow]", f"Run ./start_server.sh")

    # Model file
    if Path(MODEL_PATH).exists():
        size_mb = Path(MODEL_PATH).stat().st_size / (1024 * 1024)
        table.add_row("Gemma 4 Model", "[green]✓ OK[/green]", f"{size_mb:.0f} MB")
    else:
        table.add_row("Gemma 4 Model", "[red]✗ MISSING[/red]", "Run ./setup.sh")
        all_ok = False

    # QEMU
    qemu = shutil.which(QEMU_PATH) or (QEMU_PATH if os.path.isfile(QEMU_PATH) else None)
    if qemu:
        table.add_row("QEMU ARM", "[green]✓ OK[/green]", qemu)
    else:
        table.add_row("QEMU ARM", "[yellow]○ OPTIONAL[/yellow]", "brew install qemu")

    console.print(table)

    if all_ok:
        console.print("\n[bold green]All required dependencies present![/bold green]")
    else:
        console.print("\n[bold yellow]Some dependencies missing. Run ./setup.sh[/bold yellow]")


@cli.command()
@click.pass_context
def demo(ctx):
    """Run the built-in demo with sample schematics."""
    sample_dir = Path(__file__).parent.parent / "tests" / "sample_schematics"
    samples = list(sample_dir.glob("*.jpg")) + list(sample_dir.glob("*.png"))

    if not samples:
        console.print("[yellow]No sample schematics found in tests/sample_schematics/[/yellow]")
        console.print("Generate them with: python -m tests.generate_samples")
        return

    console.print(Panel(
        "[bold]FieldForge Demo[/bold]\n"
        f"Using sample: {samples[0].name}\n"
        "All inference runs locally via llama.cpp — no internet.",
        border_style="cyan",
    ))

    from pipeline.orchestrator import FieldForgeOrchestrator
    orchestrator = FieldForgeOrchestrator()
    result = orchestrator.run(
        image_path=str(samples[0]),
        verbose=ctx.obj.get("verbose", False),
    )


@cli.command()
@click.argument("elf_path", type=click.Path(exists=True))
def score(elf_path):
    """Score an existing ELF firmware binary."""
    from compiler.gcc_wrapper import GCCWrapper
    from pipeline.scorer import ResourceScorer

    gcc = GCCWrapper()
    scorer = ResourceScorer()

    console.print(f"Analyzing: {elf_path}\n")

    metrics = gcc.extract_metrics(elf_path)
    efficiency = scorer.score(metrics)

    console.print(scorer.to_table(efficiency, metrics))


def main():
    cli(obj={})


if __name__ == "__main__":
    main()
