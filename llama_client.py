"""
FieldForge — llama.cpp Client
==============================
Python client for the llama.cpp OpenAI-compatible server.
Supports multimodal input (base64 images) and function/tool calling.
"""

import base64
import json
import logging
import time
from pathlib import Path
from typing import Any, Optional

import requests
from pydantic import BaseModel, Field

from config import LLAMA_SERVER_URL, MAX_TOKENS, TEMPERATURE

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# Response Models
# ─────────────────────────────────────────────
class ToolCall(BaseModel):
    """A tool/function call returned by the model."""
    id: str = ""
    name: str
    arguments: dict[str, Any]


class LlamaResponse(BaseModel):
    """Structured response from the llama.cpp server."""
    content: str = ""
    tool_calls: list[ToolCall] = Field(default_factory=list)
    finish_reason: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    model: str = ""
    raw: dict = Field(default_factory=dict)


class LlamaClient:
    """
    Client for llama.cpp's OpenAI-compatible API.

    Supports:
    - Text chat completions
    - Multimodal input (base64-encoded images)
    - Function/tool calling with structured responses
    - Retry logic with exponential backoff
    """

    def __init__(self, base_url: str = None, max_retries: int = 3):
        self.base_url = (base_url or LLAMA_SERVER_URL).rstrip("/")
        self.max_retries = max_retries
        self.session = requests.Session()

    def health_check(self) -> bool:
        """Check if the llama.cpp server is running."""
        try:
            resp = self.session.get(f"{self.base_url}/health", timeout=5)
            return resp.status_code == 200
        except requests.ConnectionError:
            return False

    def get_model_info(self) -> dict:
        """Get model properties from the server."""
        try:
            resp = self.session.get(f"{self.base_url}/props", timeout=5)
            if resp.status_code == 200:
                return resp.json()
        except Exception:
            pass
        return {}

    def chat(
        self,
        messages: list[dict],
        tools: list[dict] = None,
        max_tokens: int = None,
        temperature: float = None,
        stop: list[str] = None,
    ) -> LlamaResponse:
        """
        Send a chat completion request to the llama.cpp server.

        Args:
            messages: List of message dicts with 'role' and 'content'.
            tools: Optional list of tool definitions for function calling.
            max_tokens: Maximum tokens to generate.
            temperature: Sampling temperature.
            stop: Stop sequences.

        Returns:
            LlamaResponse with content and/or tool_calls.
        """
        payload = {
            "messages": messages,
            "max_tokens": max_tokens or MAX_TOKENS,
            "temperature": temperature or TEMPERATURE,
            "stream": False,
        }

        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        if stop:
            payload["stop"] = stop

        return self._request(payload)

    def chat_with_image(
        self,
        system_prompt: str,
        image_base64: str,
        user_text: str,
        tools: list[dict] = None,
        max_tokens: int = None,
    ) -> LlamaResponse:
        """
        Send a multimodal chat request with a base64-encoded image.

        Args:
            system_prompt: System message for the model.
            image_base64: Base64-encoded image (PNG/JPEG).
            user_text: Text instruction accompanying the image.
            tools: Optional tool definitions.
            max_tokens: Maximum tokens to generate.

        Returns:
            LlamaResponse with generated content.
        """
        messages = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{image_base64}"
                        },
                    },
                    {
                        "type": "text",
                        "text": user_text,
                    },
                ],
            },
        ]

        return self.chat(messages, tools=tools, max_tokens=max_tokens)

    def _request(self, payload: dict) -> LlamaResponse:
        """Send request with retry logic and exponential backoff."""
        url = f"{self.base_url}/v1/chat/completions"
        last_error = None

        for attempt in range(1, self.max_retries + 1):
            try:
                logger.debug(f"Request attempt {attempt}/{self.max_retries}")
                resp = self.session.post(url, json=payload, timeout=120)

                if resp.status_code == 200:
                    return self._parse_response(resp.json())

                last_error = f"HTTP {resp.status_code}: {resp.text[:200]}"
                logger.warning(f"Attempt {attempt} failed: {last_error}")

            except requests.ConnectionError as e:
                last_error = f"Connection refused — is llama-server running? {e}"
                logger.warning(f"Attempt {attempt}: {last_error}")
            except requests.Timeout:
                last_error = "Request timed out (120s). Model may be overloaded."
                logger.warning(f"Attempt {attempt}: {last_error}")
            except Exception as e:
                last_error = f"Unexpected error: {e}"
                logger.warning(f"Attempt {attempt}: {last_error}")

            if attempt < self.max_retries:
                wait = 2 ** attempt
                logger.info(f"Retrying in {wait}s...")
                time.sleep(wait)

        raise ConnectionError(
            f"llama.cpp server unreachable after {self.max_retries} attempts. "
            f"Last error: {last_error}\n"
            f"Make sure the server is running: ./start_server.sh"
        )

    def _parse_response(self, data: dict) -> LlamaResponse:
        """Parse the OpenAI-compatible response into a LlamaResponse."""
        choice = data.get("choices", [{}])[0]
        message = choice.get("message", {})
        usage = data.get("usage", {})

        # Parse tool calls if present
        tool_calls = []
        raw_tool_calls = message.get("tool_calls", [])
        for tc in raw_tool_calls:
            func = tc.get("function", {})
            args = func.get("arguments", "{}")
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    args = {"raw": args}

            tool_calls.append(ToolCall(
                id=tc.get("id", ""),
                name=func.get("name", ""),
                arguments=args,
            ))

        return LlamaResponse(
            content=message.get("content", "") or "",
            tool_calls=tool_calls,
            finish_reason=choice.get("finish_reason", ""),
            prompt_tokens=usage.get("prompt_tokens", 0),
            completion_tokens=usage.get("completion_tokens", 0),
            total_tokens=usage.get("total_tokens", 0),
            model=data.get("model", ""),
            raw=data,
        )
