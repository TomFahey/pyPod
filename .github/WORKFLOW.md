# CodeClub Calculator — Agentic Coding Workflow

This document records the workflow, tooling decisions, and lessons learned building this project using VS Code GitHub Copilot's agentic coding features. It is intended as a reference for future CodeClub projects.

---

## Project Overview

**Goal:** A working MicroPython calculator app for the M5Stack Tab5, built as a 4-session coding course for 10–11 year olds new to text-based Python.

**Dual deliverable:**
1. `device/` — MicroPython source code (runs on the Tab5)
2. `docs/` — HTML lesson notes (served via GitHub Pages)

---

## Agentic Scaffolding

### Two custom agents

| Agent | File | Role |
|---|---|---|
| Calculator Coder | `.github/agents/calculator-coder.agent.md` | Writes and reviews all MicroPython device code |
| Lesson Author | `.github/agents/lesson-author.agent.md` | Writes all HTML lesson notes |

**Why two agents?** The two workstreams have almost no overlap in tooling, constraints, or output format. Separating them gives each agent a tight, focused context and prevents accidental cross-contamination (e.g. the lesson author doesn't need to know about LVGL event types; the coder doesn't need the CSS class inventory).

### File instructions (auto-applied by glob pattern)

| File | Pattern | Purpose |
|---|---|---|
| `micropython.instructions.md` | `device/**/*.py` | Enforces coding rules whenever a `.py` file is opened |
| `lesson-notes.instructions.md` | `docs/**/*.html` | Enforces HTML conventions whenever a lesson file is opened |

### Prompts (slash commands)

| Prompt | Trigger | Purpose |
|---|---|---|
| `generate-lesson` | `/generate-lesson 3` | Generates a lesson HTML file for a given session number |
| `review-student-code` | `/review-student-code` | Validates `main.py` against pedagogical coding rules |

### Global instructions

`.github/copilot-instructions.md` is loaded for every interaction in the repo. It contains:
- Architecture overview (two-file device split)
- Session plan and concept schedule
- Proto-function map (Lesson 3 → Lesson 4)
- State variable table
- `calculator_ui.py` public API
- Critical rules
- LVGL/UIFlow2 known issues

---

## Development Workflow Used

### Phase 1 — Scaffolding

1. Discuss project requirements and constraints with the user before writing any code
2. Create `copilot-instructions.md` — this is the single source of truth that all agents read first
3. Create the two custom agents and the two instruction files
4. Create the two prompt files

### Phase 2 — Device code first

1. Write `device/calculator_ui.py` (teacher wrapper) — handles all LVGL complexity
2. Write session stubs in `device/main.py` — one labelled section per session
3. Test on physical device; fix bugs before writing lesson notes
4. Bug fixes are documented in `copilot-instructions.md` and `micropython.instructions.md` so future agents don't re-introduce them

### Phase 3 — Lesson notes iteratively

1. Start from the student's perspective: "what would a 10-year-old need to understand this?"
2. Write lessons in order (1 → 4) but be prepared to restructure as you go
3. Use the lesson-author agent for first drafts; review and request revisions from the human teacher
4. Key restructure decisions made during this project:
   - Phase 5 of Lesson 2 (functions) was moved to Lesson 3 after review
   - Lesson 3 was expanded with proto-functions (`rick`, `rock_paper_scissors`, `tournament`) before introducing `handle_key`
   - Lesson 4 was restructured to open each function with a "Remember X from Session 3?" callback

### Phase 4 — Documentation

1. Update all agent/instruction/prompt files to reflect the final, working state
2. Write this `WORKFLOW.md` as a meta-reference for future projects

---

## Key Pedagogical Decisions

### Wrapper module pattern

All UIFlow2/LVGL complexity is hidden in `calculator_ui.py`, which students never see. This lets `main.py` stay conceptually clean: students only use `setup_screen()`, `show_input()`, `show_result()`, `when_key_pressed()`, and `run()`.

**Lesson:** For any embedded/hardware project with young learners, budget significant time upfront for the teacher wrapper. The wrapper is the foundation everything else rests on.

### Scaffolded concept introduction

Concepts are introduced in a strict order across sessions:
- Session 1: calling functions (no definitions)
- Session 2: variables and data types (no functions yet)
- Session 3: defining functions, flow control, scope
- Session 4: applying all of the above to real logic

**Lesson:** Resist the urge to introduce concepts early. Even when a concept would make a later session easier, introducing it before the student is ready breaks the pedagogical flow.

### Proto-function technique

Lesson 3 introduces simplified "proto-functions" (`rick`, `rock_paper_scissors`, `tournament`) that share the structural DNA of the real calculator functions in Lesson 4. When Lesson 4 introduces `add_digit`, `calculate`, and `press_equals`, the student can immediately recognise the pattern.

**Lesson:** When you know what the final code will look like, design the teaching examples to be structurally isomorphic to it. This dramatically reduces the cognitive leap at the application stage.

### Callback explanation strategy

`when_key_pressed` passes a function as an argument — a concept that can confuse beginners. The approach used here:
1. First establish that functions can call other functions (tournament → rock_paper_scissors)
2. Then establish that a function can take another function as an argument (before introducing `when_key_pressed`)
3. Then introduce `when_key_pressed` with the "delivery driver" analogy
4. Only then show the actual `handle_key` function being passed to it

**Lesson:** Never introduce callbacks cold. Always build to them via the functions-calling-functions concept first.

---

## Files Changed (complete list)

```
device/
  calculator_ui.py          Teacher wrapper; LVGL bug fixes applied
  main.py                   Student code; session-labelled sections

docs/
  lesson1.html              Session 1: Hello, Screen!
  lesson2.html              Session 2: Variables & Lists
  lesson3.html              Session 3: Functions & Key Handling
  lesson4.html              Session 4: The Full Calculator
  style.css                 Shared stylesheet for all lesson HTML

.github/
  copilot-instructions.md   Global project context for all agents
  agents/
    calculator-coder.agent.md   Device code agent
    lesson-author.agent.md      Lesson HTML agent
  instructions/
    micropython.instructions.md   Auto-applied rules for device/*.py
    lesson-notes.instructions.md  Auto-applied rules for docs/*.html
  prompts/
    generate-lesson.prompt.md     /generate-lesson N slash command
    review-student-code.prompt.md /review-student-code slash command
  WORKFLOW.md               This file
```

---

## LVGL / UIFlow2 Bug Notes

These bugs were discovered during testing on the physical device and are fixed in `calculator_ui.py`. Future projects using UIFlow2 buttons should be aware of all four:

1. **Wrong event type:** `lv.EVENT.VALUE_CHANGED` does not fire for `M5Button`. Use `lv.EVENT.ALL` and filter on `lv.EVENT.CLICKED`.
2. **GC discards C-side callback:** Store callback as `self._on_press = func` before passing to `add_event_cb`.
3. **Closure loop capture:** All callbacks in a loop share the final loop variable. Use a class with `self.k = key` in `__init__`.
4. **GC collects local objects:** Objects created inside a function are GC-eligible when the function returns. Store in a module-level list.
