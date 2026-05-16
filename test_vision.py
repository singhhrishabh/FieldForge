#!/usr/bin/env python3
"""
FieldForge — Vision Test
Tests that llama.cpp server can process images via Gemma 4 E4B + mmproj.
Usage: python3 test_vision.py
"""
from __future__ import annotations

import base64
import io
import json
import sys

import requests
from PIL import Image, ImageDraw


def create_test_schematic() -> str:
    """Create a synthetic circuit schematic image and return base64."""
    img = Image.new("RGB", (400, 300), "white")
    draw = ImageDraw.Draw(img)

    # MCU rectangle
    draw.rectangle([150, 80, 250, 220], outline="black", width=2)
    draw.text((170, 140), "MCU", fill="black")

    # LED (circle)
    draw.ellipse([300, 100, 340, 140], outline="black", width=2)
    draw.text((310, 145), "LED", fill="black")

    # Resistor (zigzag approximation)
    draw.line([(250, 120), (275, 120)], fill="black", width=2)
    draw.line([(275, 110), (285, 130), (295, 110), (300, 120)], fill="black", width=2)

    # Ground symbol
    draw.line([(200, 220), (200, 260)], fill="black", width=2)
    draw.line([(185, 260), (215, 260)], fill="black", width=2)
    draw.line([(190, 268), (210, 268)], fill="black", width=1)
    draw.line([(195, 276), (205, 276)], fill="black", width=1)

    # Power line
    draw.line([(200, 80), (200, 40)], fill="black", width=2)
    draw.text((190, 25), "VCC", fill="black")

    # Save and encode
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    img.save("/tmp/test_schematic.png")
    return base64.b64encode(buf.getvalue()).decode("utf-8")


def test_vision():
    """Send a test image to the server and verify multimodal response."""
    print("=" * 50)
    print("FieldForge Vision Test")
    print("=" * 50)

    # Step 1: Create test image
    print("\n[1/4] Creating test schematic image...")
    img_b64 = create_test_schematic()
    print(f"  ✓ Image created: /tmp/test_schematic.png ({len(img_b64)} bytes base64)")

    # Step 2: Build request
    print("\n[2/4] Sending to Gemma 4 E4B (multimodal)...")
    payload = {
        "model": "gemma-4",
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{img_b64}"
                        },
                    },
                    {
                        "type": "text",
                        "text": "Describe what you see in this image. List any circuit components you can identify.",
                    },
                ],
            }
        ],
        "max_tokens": 200,
    }

    # Step 3: Send request
    try:
        resp = requests.post(
            "http://localhost:8080/v1/chat/completions",
            json=payload,
            timeout=120,
        )
    except requests.ConnectionError:
        print("  ✗ FAIL: Cannot connect to server at localhost:8080")
        print("    Run: ./start_server.sh")
        return False

    print(f"  HTTP Status: {resp.status_code}")

    # Step 4: Validate response
    print("\n[3/4] Checking response...")

    if resp.status_code != 200:
        print(f"  ✗ FAIL: HTTP {resp.status_code}")
        print(f"  Response: {resp.text[:300]}")
        if "image input is not supported" in resp.text:
            print("\n  ⚠ The server was started WITHOUT --mmproj.")
            print("  Run: ./stop_server.sh && ./start_server.sh")
        return False

    data = resp.json()
    content = data.get("choices", [{}])[0].get("message", {}).get("content", "")

    if not content:
        print("  ✗ FAIL: Response content is empty")
        return False

    if "image input is not supported" in content:
        print("  ✗ FAIL: Server lacks multimodal support")
        print("  The mmproj file is not loaded. Restart server.")
        return False

    print(f"  Response length: {len(content)} chars")
    print(f"\n[4/4] Model response:")
    print(f"  {content[:500]}")

    print("\n" + "=" * 50)
    print("  ✅ PASS — Vision is working!")
    print("  Gemma 4 E4B can see and describe images.")
    print("=" * 50)
    return True


if __name__ == "__main__":
    success = test_vision()
    sys.exit(0 if success else 1)
