"""
FieldForge — Resource Scorer
==============================
Converts GCC output metrics into human-readable efficiency grades.
This is the project's real "reward function" — all numbers come from GCC.
"""

import logging
from typing import Optional

from pydantic import BaseModel, Field
from rich.console import Console
from rich.table import Table
from rich.text import Text

from compiler.gcc_wrapper import ResourceMetrics, EfficiencyScore

logger = logging.getLogger(__name__)


class ImprovementReport(BaseModel):
    """Comparison between before/after Critic fix."""
    instruction_delta: int = 0
    instruction_pct: float = 0.0
    size_delta: int = 0
    size_pct: float = 0.0
    stack_delta: int = 0
    stack_pct: float = 0.0
    score_before: float = 0.0
    score_after: float = 0.0
    headline: str = ""


class ResourceScorer:
    """
    Scores compiled firmware on resource efficiency.

    Metrics:
    - Instruction count (40% weight)
    - Binary size in bytes (40% weight)
    - Estimated stack depth (20% weight)

    Grades: A (≥85), B (≥70), C (≥50), F (<50)
    """

    def score(self, metrics: ResourceMetrics) -> EfficiencyScore:
        """
        Compute efficiency score from resource metrics.

        All numbers come directly from arm-none-eabi-gcc output — no faking.
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

    def compare(
        self, before: ResourceMetrics, after: ResourceMetrics
    ) -> ImprovementReport:
        """
        Compare metrics before and after the Critic's fix.

        Shows the real impact of the Critic agent's corrections.
        """
        from compiler.gcc_wrapper import GCCWrapper
        gcc = GCCWrapper()

        i_delta = after.instruction_count - before.instruction_count
        s_delta = after.binary_size_bytes - before.binary_size_bytes
        k_delta = after.estimated_stack_bytes - before.estimated_stack_bytes

        i_pct = (i_delta / max(before.instruction_count, 1)) * 100
        s_pct = (s_delta / max(before.binary_size_bytes, 1)) * 100
        k_pct = (k_delta / max(before.estimated_stack_bytes, 1)) * 100

        score_before = self.score(before).overall
        score_after = self.score(after).overall

        # Build headline
        parts = []
        if i_delta < 0:
            parts.append(f"instruction count by {abs(i_pct):.0f}%")
        if s_delta < 0:
            parts.append(f"binary size by {abs(s_pct):.0f}%")

        headline = "Critic's fix reduced " + " and ".join(parts) if parts else "Critic's fix applied"

        return ImprovementReport(
            instruction_delta=i_delta,
            instruction_pct=round(i_pct, 1),
            size_delta=s_delta,
            size_pct=round(s_pct, 1),
            stack_delta=k_delta,
            stack_pct=round(k_pct, 1),
            score_before=score_before,
            score_after=score_after,
            headline=headline,
        )

    def to_table(self, score: EfficiencyScore, metrics: ResourceMetrics = None) -> Table:
        """
        Build a rich Table showing the efficiency breakdown.
        """
        table = Table(
            title="⚡ Resource Efficiency Score",
            show_lines=True,
            border_style="bright_blue",
        )
        table.add_column("Metric", style="bold white", width=18)
        table.add_column("Raw Value", style="cyan", justify="right", width=12)
        table.add_column("Score", justify="right", width=8)
        table.add_column("Weight", style="dim", justify="right", width=8)
        table.add_column("Contribution", justify="right", width=14)

        raw_instr = str(metrics.instruction_count) if metrics else "—"
        raw_size = f"{metrics.binary_size_bytes:,}B" if metrics else "—"
        raw_stack = f"{metrics.estimated_stack_bytes}B" if metrics else "—"

        table.add_row(
            "Instructions",
            raw_instr,
            f"{score.instruction_score:.1f}",
            "40%",
            f"{score.instruction_score * 0.4:.1f}",
        )
        table.add_row(
            "Binary Size",
            raw_size,
            f"{score.size_score:.1f}",
            "40%",
            f"{score.size_score * 0.4:.1f}",
        )
        table.add_row(
            "Stack Depth",
            raw_stack,
            f"{score.stack_score:.1f}",
            "20%",
            f"{score.stack_score * 0.2:.1f}",
        )

        # Grade color
        grade_colors = {"A": "green", "B": "yellow", "C": "dark_orange", "F": "red"}
        color = grade_colors.get(score.grade, "white")
        grade_text = f"[bold {color}]{score.grade}[/bold {color}]"

        table.add_section()
        table.add_row(
            "[bold]OVERALL[/bold]",
            "",
            f"[bold]{score.overall:.1f}[/bold]",
            "100%",
            grade_text,
        )

        return table
