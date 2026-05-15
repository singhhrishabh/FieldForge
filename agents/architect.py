"""
FieldForge — Architect Agent
==============================
Gemma 4 multimodal agent that reads circuit schematic photos
and generates ARM Cortex-M0 C firmware via function calling.
"""

import json
import logging
import re
from typing import Optional

from pydantic import BaseModel, Field

from config import ARCHITECT_SYSTEM_PROMPT
from llama_client import LlamaClient, LlamaResponse

logger = logging.getLogger(__name__)


class ArchitectResult(BaseModel):
    """Result from the Architect agent's firmware generation."""
    code: str = ""
    description: str = ""
    tool_called: str = ""
    confidence: float = 0.0
    raw_response: str = ""


class ArchitectAgent:
    """
    The Architect agent: reads a schematic image and generates C firmware.

    Uses Gemma 4's multimodal capabilities to parse hand-drawn circuits,
    then generates complete, compilable C code for ARM Cortex-M0.
    Leverages native function calling to trigger compilation.
    """

    def __init__(self, client: LlamaClient):
        self.client = client

    def define_tools(self) -> list[dict]:
        """Return tool definitions for Gemma 4 function calling."""
        return [
            {
                "type": "function",
                "function": {
                    "name": "compile_firmware",
                    "description": (
                        "Compile the generated C firmware to ARM Cortex-M0 ELF. "
                        "Call this when you have written the complete firmware."
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
                                "description": "ARM target CPU.",
                                "default": "cortex-m0",
                            },
                            "optimization": {
                                "type": "string",
                                "description": "GCC optimization level.",
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
                    "description": "Send firmware code to the Critic agent for safety review.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "code": {
                                "type": "string",
                                "description": "C source code to review.",
                            },
                            "schematic_description": {
                                "type": "string",
                                "description": "What the schematic shows.",
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
                    "description": "Save firmware source code to disk.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "code": {"type": "string", "description": "C code to save."},
                            "filename": {"type": "string", "description": "Output filename."},
                        },
                        "required": ["code"],
                    },
                },
            },
        ]

    def generate_firmware(self, image_data: dict) -> ArchitectResult:
        """
        Generate C firmware from a preprocessed schematic image.

        Args:
            image_data: Dict from ImageProcessor.prepare_for_gemma() containing
                        base64_image, complexity, width, height, component_count.

        Returns:
            ArchitectResult with the generated C code.

        Raises:
            ConnectionError: If the llama.cpp server is unreachable.
            ValueError: If no code could be extracted from the response.
        """
        user_text = (
            f"Analyze this hand-drawn circuit schematic carefully.\n\n"
            f"Image info: {image_data['width']}x{image_data['height']}px, "
            f"{image_data['component_count']} components detected, "
            f"complexity: {image_data['complexity']}.\n\n"
            f"Instructions:\n"
            f"1. Identify ALL components and their connections in the schematic.\n"
            f"2. Map components to GPIO pins on an ARM Cortex-M0 MCU.\n"
            f"3. Generate COMPLETE, compilable C firmware.\n"
            f"4. Include: vector table, SystemInit, GPIO configuration, main loop.\n"
            f"5. Use volatile for all hardware register accesses.\n"
            f"6. When the code is ready, call the compile_firmware tool.\n\n"
            f"Generate the firmware now."
        )

        tools = self.define_tools()

        logger.info("Sending schematic to Gemma 4 Architect...")
        response = self.client.chat_with_image(
            system_prompt=ARCHITECT_SYSTEM_PROMPT,
            image_base64=image_data["base64_image"],
            user_text=user_text,
            tools=tools,
        )

        return self._process_response(response)

    def generate_firmware_from_text(self, description: str) -> ArchitectResult:
        """
        Generate firmware from a text description (no image).
        Useful for testing and text-based schematic descriptions.
        """
        messages = [
            {"role": "system", "content": ARCHITECT_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"Generate complete C firmware for ARM Cortex-M0 based on "
                    f"this circuit description:\n\n{description}\n\n"
                    f"Include: vector table, SystemInit, GPIO config, main loop. "
                    f"Call compile_firmware when done."
                ),
            },
        ]

        tools = self.define_tools()
        response = self.client.chat(messages, tools=tools)
        return self._process_response(response)

    def fix_compile_errors(self, code: str, errors: list[dict]) -> ArchitectResult:
        """
        Ask the Architect to fix GCC compilation errors.

        Args:
            code: The code that failed to compile.
            errors: List of error dicts from GCCWrapper.

        Returns:
            ArchitectResult with corrected code.
        """
        error_text = "\n".join(
            f"  Line {e.get('line', '?')}: {e.get('message', e.get('raw', ''))}"
            for e in errors
        )

        messages = [
            {"role": "system", "content": ARCHITECT_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"The following C firmware failed to compile with arm-none-eabi-gcc.\n\n"
                    f"ERRORS:\n{error_text}\n\n"
                    f"ORIGINAL CODE:\n```c\n{code}\n```\n\n"
                    f"Fix ALL errors and output the COMPLETE corrected C file. "
                    f"Call compile_firmware with the fixed code."
                ),
            },
        ]

        tools = self.define_tools()
        response = self.client.chat(messages, tools=tools)
        return self._process_response(response)

    def _process_response(self, response: LlamaResponse) -> ArchitectResult:
        """Process the Gemma 4 response — extract code from tool calls or text."""
        # Check for tool calls first
        if response.tool_calls:
            tc = response.tool_calls[0]
            code = tc.arguments.get("code", "")
            if code:
                logger.info(f"Architect called tool: {tc.name} ({len(code)} chars)")
                return ArchitectResult(
                    code=code,
                    description=tc.arguments.get("schematic_description", ""),
                    tool_called=tc.name,
                    confidence=0.9,
                    raw_response=response.content,
                )

        # Fallback: extract code from text response
        if response.content:
            try:
                code = self.extract_code_from_response(response.content)
                return ArchitectResult(
                    code=code,
                    description="Extracted from text response",
                    tool_called="none",
                    confidence=0.7,
                    raw_response=response.content,
                )
            except ValueError:
                # Retry with explicit instruction
                logger.warning("No code found in response, retrying...")
                retry_messages = [
                    {"role": "system", "content": ARCHITECT_SYSTEM_PROMPT},
                    {"role": "assistant", "content": response.content},
                    {
                        "role": "user",
                        "content": (
                            "Output ONLY the complete C source code in a ```c code block. "
                            "No explanations. Just the code."
                        ),
                    },
                ]
                retry_resp = self.client.chat(retry_messages)
                code = self.extract_code_from_response(retry_resp.content)
                return ArchitectResult(
                    code=code,
                    description="Extracted after retry",
                    tool_called="none",
                    confidence=0.5,
                    raw_response=retry_resp.content,
                )

        raise ValueError("Architect produced no code. The model may need a simpler prompt.")

    @staticmethod
    def extract_code_from_response(text: str) -> str:
        """
        Extract C code from a markdown response.

        Handles ```c, ```cpp, and bare ``` code blocks.

        Raises:
            ValueError: If no code block is found.
        """
        # Try ```c or ```cpp blocks first
        patterns = [
            r"```c\n(.*?)```",
            r"```cpp\n(.*?)```",
            r"```\n(.*?)```",
        ]

        for pattern in patterns:
            matches = re.findall(pattern, text, re.DOTALL)
            if matches:
                # Return the longest match (most likely the full firmware)
                code = max(matches, key=len).strip()
                if len(code) > 50:  # Sanity check
                    return code

        # Last resort: look for code-like content
        if "#include" in text and "int main" in text:
            # Try to extract everything from #include to the end
            start = text.find("#include")
            code = text[start:].strip()
            if len(code) > 50:
                return code

        raise ValueError(
            "No C code block found in response. "
            "Expected ```c ... ``` format."
        )
