"""
FieldForge — Tool Registry
============================
Function calling tools for Gemma 4 agents.
Maps tool names to actual system operations (GCC, simulator, file I/O).
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Callable

from compiler.gcc_wrapper import GCCWrapper, CompileResult
from config import OUTPUT_DIR

logger = logging.getLogger(__name__)


class ToolRegistry:
    """
    Registry of callable tools that Gemma 4 agents can invoke
    via function calling. Each tool maps to a real system operation.
    """

    def __init__(self, gcc: GCCWrapper = None):
        self.gcc = gcc or GCCWrapper()
        self._tools: dict[str, Callable] = {
            "compile_firmware": self._compile_firmware,
            "request_critic_review": self._request_critic_review,
            "save_firmware": self._save_firmware,
        }
        self._pending_review: dict = {}

    @property
    def tool_definitions(self) -> list[dict]:
        """Return OpenAI-compatible tool definitions for the API."""
        return [
            {
                "type": "function",
                "function": {
                    "name": "compile_firmware",
                    "description": (
                        "Compile C firmware source code to ARM Cortex-M0 ELF binary "
                        "using arm-none-eabi-gcc. Returns compilation status, errors, "
                        "and resource metrics."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "code": {
                                "type": "string",
                                "description": "Complete C source code to compile.",
                            },
                            "target": {
                                "type": "string",
                                "description": "ARM CPU target. Default: cortex-m0",
                                "default": "cortex-m0",
                            },
                            "optimization": {
                                "type": "string",
                                "description": "GCC optimization level (0, 1, 2, 3, s, g). Default: Os",
                                "default": "Os",
                            },
                        },
                        "required": ["code"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "request_critic_review",
                    "description": (
                        "Submit firmware code for review by the Critic agent. "
                        "The Critic will check for pointer safety, buffer bounds, "
                        "and embedded-specific bugs."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "code": {
                                "type": "string",
                                "description": "C firmware source code to review.",
                            },
                            "schematic_description": {
                                "type": "string",
                                "description": "Text description of what the schematic shows.",
                            },
                        },
                        "required": ["code"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "save_firmware",
                    "description": "Save firmware source code to a file in the output directory.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "code": {
                                "type": "string",
                                "description": "C source code to save.",
                            },
                            "filename": {
                                "type": "string",
                                "description": "Filename (without path). Default: firmware.c",
                                "default": "firmware.c",
                            },
                        },
                        "required": ["code"],
                    },
                },
            },
        ]

    def execute(self, tool_name: str, arguments: dict) -> dict:
        """
        Execute a tool by name with the given arguments.

        Args:
            tool_name: Name of the tool to execute.
            arguments: Dict of arguments from the model's tool_call.

        Returns:
            Dict with the tool's result.
        """
        if tool_name not in self._tools:
            return {"error": f"Unknown tool: {tool_name}"}

        try:
            logger.info(f"Executing tool: {tool_name}")
            return self._tools[tool_name](**arguments)
        except Exception as e:
            logger.error(f"Tool {tool_name} failed: {e}")
            return {"error": str(e)}

    def _compile_firmware(
        self, code: str, target: str = "cortex-m0", optimization: str = "Os"
    ) -> dict:
        """Compile firmware and return structured result."""
        result = self.gcc.compile(code, target=target, optimization=optimization)
        return {
            "success": result.success,
            "elf_path": result.elf_path,
            "errors": [e.model_dump() for e in result.errors],
            "warnings": [w.model_dump() for w in result.warnings],
            "metrics": result.metrics.model_dump() if result.metrics else None,
        }

    def _request_critic_review(
        self, code: str, schematic_description: str = ""
    ) -> dict:
        """Store code for critic review (actual review done by orchestrator)."""
        self._pending_review = {
            "code": code,
            "schematic_description": schematic_description,
        }
        return {
            "status": "queued",
            "message": "Code submitted for Critic review.",
        }

    def _save_firmware(self, code: str, filename: str = "firmware.c") -> dict:
        """Save firmware source to the output directory."""
        output_path = Path(OUTPUT_DIR) / filename
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(code, encoding="utf-8")
        logger.info(f"Firmware saved: {output_path}")
        return {
            "status": "saved",
            "path": str(output_path),
            "size_bytes": len(code),
        }

    def get_pending_review(self) -> dict:
        """Get and clear the pending critic review request."""
        review = self._pending_review
        self._pending_review = {}
        return review
