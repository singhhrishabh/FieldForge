"""
FieldForge — Critic Agent
============================
Gemma 4 code review agent that checks firmware for pointer safety,
buffer bounds, null dereferences, and embedded-specific bugs.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Optional

from pydantic import BaseModel, Field
from rich.console import Console
from rich.table import Table

from config import CRITIC_SYSTEM_PROMPT
from llama_client import LlamaClient

logger = logging.getLogger(__name__)


class BugReport(BaseModel):
    """A single bug found by the Critic."""
    line: int = 0
    category: str = ""       # e.g. "A1", "B3", "C2"
    severity: str = "medium"  # "critical" | "high" | "medium"
    description: str = ""
    fix: str = ""


class CriticReport(BaseModel):
    """Full report from the Critic agent."""
    verdict: str = "pass"     # "pass" | "fail"
    issues: list[BugReport] = Field(default_factory=list)
    fixed_code: str = ""
    summary: str = ""
    confidence: float = 0.0


class CriticAgent:
    """
    The Critic agent: reviews C firmware for safety-critical bugs.

    Performs systematic line-by-line review checking for:
    - Category A (Critical): uninitialized pointers, buffer overflows, null derefs
    - Category B (High): integer overflow, missing volatile, wrong bit masks
    - Category C (Medium): blocking delays in ISR, dead code, magic numbers
    """

    def __init__(self, client: LlamaClient):
        self.client = client

    def review(self, code: str, schematic_description: str = "") -> CriticReport:
        """
        Review C firmware code for bugs.

        Args:
            code: Complete C source code to review.
            schematic_description: What the schematic shows (for context).

        Returns:
            CriticReport with verdict, issues, and optionally fixed code.
        """
        prompt = self.build_review_prompt(code, schematic_description)

        messages = [
            {"role": "system", "content": CRITIC_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]

        logger.info(f"Critic reviewing {len(code)} chars of code...")
        response = self.client.chat(messages, max_tokens=4096)

        try:
            report = self.parse_response(response.content)
            logger.info(
                f"Critic verdict: {report.verdict} "
                f"({len(report.issues)} issues, confidence: {report.confidence})"
            )
            return report
        except Exception as e:
            logger.warning(f"Failed to parse Critic response: {e}. Retrying...")
            # Retry with explicit JSON instruction
            retry_messages = messages + [
                {"role": "assistant", "content": response.content},
                {
                    "role": "user",
                    "content": (
                        "Your response was not valid JSON. Please respond with ONLY "
                        "the JSON object in the exact format specified in your system prompt. "
                        "No text before or after the JSON."
                    ),
                },
            ]
            retry_resp = self.client.chat(retry_messages, max_tokens=4096)
            return self.parse_response(retry_resp.content)

    def build_review_prompt(self, code: str, description: str) -> str:
        """
        Build the detailed review prompt with numbered lines.

        Adds line numbers to help the Critic reference specific locations.
        """
        # Add line numbers to code
        lines = code.split("\n")
        numbered = "\n".join(f"{i+1:4d} | {line}" for i, line in enumerate(lines))

        prompt = (
            f"Review the following ARM Cortex-M0 C firmware for bugs.\n\n"
        )

        if description:
            prompt += f"SCHEMATIC CONTEXT: {description}\n\n"

        prompt += (
            f"CODE ({len(lines)} lines):\n"
            f"```c\n{numbered}\n```\n\n"
            f"REVIEW INSTRUCTIONS:\n"
            f"1. Check EVERY line for Category A (critical), B (high), and C (medium) issues.\n"
            f"2. Pay special attention to:\n"
            f"   - Are ALL pointers initialized before use?\n"
            f"   - Are ALL hardware registers accessed with volatile?\n"
            f"   - Is the GPIO clock enabled before GPIO access (RCC_AHBENR)?\n"
            f"   - Are bit shifts/masks correct for the target pins?\n"
            f"   - Is there any risk of integer overflow in counters?\n"
            f"   - Are there any blocking calls inside interrupt handlers?\n"
            f"3. If you find ANY issues, verdict must be 'fail' and you MUST provide fixed_code.\n"
            f"4. Respond with ONLY the JSON object — no other text.\n"
        )

        return prompt

    def parse_response(self, raw: str) -> CriticReport:
        """
        Parse Gemma 4's response into a CriticReport.
        Handles both pure JSON and JSON embedded in text.
        """
        # Try direct JSON parse
        try:
            data = json.loads(raw.strip())
            return self._build_report(data)
        except json.JSONDecodeError:
            pass

        # Extract JSON from text (find outermost { ... })
        json_match = re.search(r"\{[\s\S]*\}", raw)
        if json_match:
            try:
                data = json.loads(json_match.group())
                return self._build_report(data)
            except json.JSONDecodeError:
                pass

        # Extract from code block
        code_block = re.search(r"```(?:json)?\n([\s\S]*?)```", raw)
        if code_block:
            try:
                data = json.loads(code_block.group(1))
                return self._build_report(data)
            except json.JSONDecodeError:
                pass

        raise ValueError(f"Cannot parse Critic response as JSON. Raw: {raw[:200]}...")

    def _build_report(self, data: dict) -> CriticReport:
        """Build a CriticReport from parsed JSON data."""
        issues = []
        for item in data.get("issues", []):
            issues.append(BugReport(
                line=item.get("line", 0),
                category=item.get("category", ""),
                severity=item.get("severity", "medium"),
                description=item.get("description", ""),
                fix=item.get("fix", ""),
            ))

        return CriticReport(
            verdict=data.get("verdict", "pass"),
            issues=issues,
            fixed_code=data.get("fixed_code", ""),
            summary=data.get("summary", ""),
            confidence=float(data.get("confidence", 0.0)),
        )

    def format_report(self, report: CriticReport) -> str:
        """Format the Critic report as a rich terminal display."""
        console = Console(record=True)

        # Header
        if report.verdict == "pass":
            console.print("\n[bold green]✓ CRITIC VERDICT: PASS[/bold green]")
        else:
            console.print("\n[bold red]✗ CRITIC VERDICT: FAIL[/bold red]")

        console.print(f"  Confidence: {report.confidence:.0%}")
        console.print(f"  Issues found: {len(report.issues)}")

        if report.issues:
            table = Table(title="Bug Report", show_lines=True)
            table.add_column("#", style="dim", width=3)
            table.add_column("Line", style="cyan", width=5)
            table.add_column("Cat", style="yellow", width=4)
            table.add_column("Severity", width=10)
            table.add_column("Description", style="white")
            table.add_column("Fix", style="green")

            for i, issue in enumerate(report.issues, 1):
                sev_style = {
                    "critical": "[bold red]CRITICAL[/bold red]",
                    "high": "[yellow]HIGH[/yellow]",
                    "medium": "[blue]MEDIUM[/blue]",
                }.get(issue.severity, issue.severity)

                table.add_row(
                    str(i),
                    str(issue.line),
                    issue.category,
                    sev_style,
                    issue.description,
                    issue.fix[:80] + "..." if len(issue.fix) > 80 else issue.fix,
                )

            console.print(table)

        if report.summary:
            console.print(f"\n  [dim]{report.summary}[/dim]")

        return console.export_text()
