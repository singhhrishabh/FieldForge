"""
Test that the main_template.c compiles successfully with ARM GCC.
"""
from __future__ import annotations

import subprocess
import os

def test_template_compiles():
    """The C template must compile with arm-none-eabi-gcc without errors."""
    project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    template = os.path.join(project_dir, "compiler", "templates", "main_template.c")
    linker = os.path.join(project_dir, "compiler", "templates", "linker.ld")
    
    # Find GCC
    gcc = "arm-none-eabi-gcc"
    for candidate in ["/opt/homebrew/bin/arm-none-eabi-gcc", "/usr/local/bin/arm-none-eabi-gcc"]:
        if os.path.isfile(candidate):
            gcc = candidate
            break
    
    result = subprocess.run(
        [gcc, "-mcpu=cortex-m0", "-mthumb", "-Os", "-nostdlib", "-nostartfiles",
         f"-T{linker}", "-Wall", "-Wextra", template, "-o", "/tmp/test_template.elf"],
        capture_output=True, text=True, timeout=10,
    )
    
    assert result.returncode == 0, f"Template failed to compile:\n{result.stderr}"
    assert os.path.exists("/tmp/test_template.elf"), "ELF file not created"
    
    # Check binary size
    size_result = subprocess.run(
        [gcc.replace("gcc", "size"), "/tmp/test_template.elf"],
        capture_output=True, text=True, timeout=5,
    )
    print(f"\nTemplate binary:\n{size_result.stdout}")

if __name__ == "__main__":
    test_template_compiles()
    print("✅ PASS — Template compiles successfully")
