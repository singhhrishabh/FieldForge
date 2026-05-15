# FieldForge — Demo Video Script

> **Duration:** 2:55 (target ≤3:00)
> **Format:** Screen recording + voiceover
> **Speaking pace:** ~130 WPM

---

## ACT 1 — THE PROBLEM (0:00 – 0:25)

**[VISUAL]** Close-up of hands sketching a circuit on paper. Dim lighting. A pen traces a rectangle labeled "MCU", draws wires to an LED symbol, adds a resistor. The paper is slightly crumpled.

**[VOICEOVER]**
"It's three in the morning. The hospital's water pump has failed. The flood that knocked out the internet also fried the control board. But the engineer knows the circuit. She's fixed it a hundred times. She draws it from memory — MCU, driver, status LED. Every component, every connection."

**[ON-SCREEN TEXT]**
`1.8 billion people live in climate-vulnerable areas`

**[VOICEOVER]**
"She has the knowledge. What she doesn't have is a laptop, an IDE, or a compiler. All she has is a phone."

---

## ACT 2 — THE TOOL (0:25 – 1:00)

**[VISUAL]** Terminal opens. Font is large (20pt+). The FieldForge banner appears.

**[ON-SCREEN TEXT]**
`FieldForge v1.0 | Powered by Gemma 4 via llama.cpp`

**[VISUAL]** Quick cut: WiFi is OFF. Show the macOS WiFi menu — "Wi-Fi: Off" clearly visible. Hold for 3 seconds.

**[VOICEOVER]**
"No internet. No cloud. Just Gemma 4, running locally through llama dot cpp."

**[VISUAL]** Terminal shows the llama.cpp server status: "Gemma 4 E4B — ONLINE via llama.cpp"

**[VISUAL]** Command typed: `python -m ui.cli run --offline-demo tests/sample_schematics/pump_control.png`

**[VOICEOVER]**
"One command. The phone photo of her sketch goes into FieldForge."

**[VISUAL]** Step 1 spinner completes: "Image preprocessed ✓ — 5 components, complexity: moderate"
Step 2 spinner appears: "Architect analyzing schematic..."

**[VOICEOVER]**
"Gemma 4 reads the hand-drawn schematic — not a clean diagram, a real sketch — and writes C firmware for an ARM Cortex-M-zero."

**[VISUAL]** Step 2 completes: "Firmware generated ✓ — 94 lines of C. Tool called: compile_firmware"

**[VOICEOVER]**
"Ninety-four lines. Vector table, GPIO configuration, interrupt handlers. Generated in twelve seconds."

---

## ACT 3 — THE CRITIC (1:00 – 1:50) ← CLIMAX

**[VISUAL]** Step 3 shows: "Compiled successfully ✓"
Step 4 spinner: "Critic reviewing code for bugs..."

**[VOICEOVER]**
"But writing code isn't enough. In embedded systems, one uninitialized pointer crashes the device. So FieldForge has a second agent — the Critic."

**[VISUAL]** Step 4 completes. The verdict appears in red: **"FAIL | Issues: 2"**

The bug table renders:
```
┌──────┬──────┬──────────────────────────────────────────┐
│ Line │ Sev  │ Description                              │
├──────┼──────┼──────────────────────────────────────────┤
│   12 │ CRIT │ GPIO accessed without enabling RCC clock │
│   34 │ HIGH │ Missing volatile on register pointer     │
└──────┴──────┴──────────────────────────────────────────┘
```

**[ON-SCREEN TEXT]** Highlight line 12 with a red box. Caption: "This bug would cause a bus fault on real hardware."

**[VOICEOVER]**
"Two bugs. Line twelve — the GPIO port is accessed before its clock is enabled. On a real Cortex-M-zero, that's a hard fault. The device freezes. Line thirty-four — a register pointer without the volatile keyword. The compiler optimizes away the read. The firmware never sees the hardware change."

*[Pause for emphasis]*

"The Critic caught what the Architect missed."

**[VISUAL]** "Applied Critic's fixes →"
Step 5: "Compiling validated firmware..."
Step 5: "Final build successful ✓"

**[VOICEOVER]**
"The fixes are applied. The firmware recompiles. Clean."

---

## ACT 4 — THE PROOF (1:50 – 2:25)

**[VISUAL]** Step 6: Simulator output. Step 7: Report generation.

The final panel renders:
```
╔══════════════════════════════════════════╗
║  FIELDFORGE — FIRMWARE GENERATED ✓      ║
║  Schematic → Firmware in 47.3s          ║
║                                         ║
║  Bugs caught by Critic: 2              ║
║  Final verdict: PASS                    ║
║                                         ║
║  RESOURCE SCORE: A (88.1/100)          ║
║  Instructions:  312                     ║
║  Binary size:   5,104 bytes            ║
║  Stack depth:   412 bytes              ║
╚══════════════════════════════════════════╝
```

**[ON-SCREEN TEXT]** "All metrics from real GCC output — nothing faked"

**[VOICEOVER]**
"Three hundred twelve instructions. Five K binary. Grade A. Every number comes from the real ARM toolchain — arm-none-eabi-gcc. This isn't a mockup. This is firmware you could flash onto hardware right now."

**[VISUAL]** Quick flash of the resource score table with colored grade.

---

## ACT 5 — THE VISION (2:25 – 2:55)

**[VISUAL]** World map highlighting climate-vulnerable regions. Transition to a hand holding a phone showing FieldForge running.

**[VOICEOVER]**
"Three point eight billion Android devices worldwide. Gemma 4 runs on mobile hardware. ARM Cortex-M-zero is the most deployed thirty-two bit architecture on earth. FieldForge sits at the intersection."

**[VISUAL]** Return to the sketch from Act 1. The paper. The pen. The dim light.

**[VOICEOVER]**
"We didn't build a demo. We built a tool. For the engineer at three AM, in the hospital with no internet, with nothing but a sketch and a phone."

*[Final beat — 2 seconds of silence]*

**[ON-SCREEN TEXT]**
`FieldForge — Sketch it. Snap it. Flash it.`
`Built with Gemma 4 via llama.cpp | 100% Offline`

---

## Recording Instructions

### Before Recording
1. Set terminal font to **20pt** (Monaco or SF Mono)
2. Terminal background: pure black, foreground: white
3. Window size: 1920×1080 (full HD)
4. **Disable WiFi:** macOS: `networksetup -setairportpower en0 off` / Linux: `nmcli radio wifi off`
5. Have the pump_control.png schematic visible in a Finder/file manager window

### Terminal Commands for Recording
```bash
# Show WiFi is off (pause for camera)
networksetup -getairportpower en0

# Start server (should already be running)
./start_server.sh

# Run the demo
python -m ui.cli run --offline-demo --verbose tests/sample_schematics/pump_control.png
```

### Timing Tips
- The progress spinners create natural pauses — don't rush narration during waits
- The Critic verdict is the emotional peak — let the red "FAIL" sit on screen for 3 full seconds before narrating
- The final panel is the payoff — hold it for 5 seconds with no voiceover
