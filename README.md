# 🎵 pyPod — CodeClub MP3 Karaoke Player

A six-session CodeClub project that guides young programmers through building a fully functional **MP3/karaoke player** for the [M5Stack Core S3](https://docs.m5stack.com/en/core/CoreS3) microcontroller.

This project is designed as a follow-on to the [pyCalculator](https://github.com/TomFahey/pyCalculator) CodeClub project, and introduces more advanced Python concepts — classes, file I/O, string parsing, and event-driven programming — through the motivating goal of building something genuinely cool.

---

## 📖 Lesson Documents

The lesson plans are hosted on GitHub Pages:

| Session | Title | Link |
|---------|-------|------|
| 1 | Meet the Track | [Lesson 1 →](https://tomfahey.github.io/pyPod/lesson1.html) |
| 2 | Songs from the SD Card | [Lesson 2 →](https://tomfahey.github.io/pyPod/lesson2.html) |
| 3 | Reading the Lyrics | [Lesson 3 →](https://tomfahey.github.io/pyPod/lesson3.html) |
| 4 | Making Music Play | [Lesson 4 →](https://tomfahey.github.io/pyPod/lesson4.html) |
| 5 | Keeping Time | [Lesson 5 →](https://tomfahey.github.io/pyPod/lesson5.html) |
| 6 | Sing Along! | [Lesson 6 →](https://tomfahey.github.io/pyPod/lesson6.html) |

---

## 🧠 What students learn

| Session | New concepts |
|---------|-------------|
| 1 | Python `class`, `__init__`, `self`, object instances |
| 2 | String slicing, `rfind`, `strip`, functions, `for` loops, tuples |
| 3 | File reading (`open`/`with`), `split()`, `int()`, nested lists, `try/except` |
| 4 | Callbacks, the `@` decorator syntax, the `global` keyword |
| 5 | Tick-based updates, integer division (`//`, `%`), formatted strings |
| 6 | Searching a sorted list, the lookahead trick, combining all 6 lessons |

---

## 🏗️ Project structure

```
pyPod/
├── device/
│   ├── pypod.py        # Teacher-written wrapper — hides hardware complexity
│   └── main.py         # Student-written code — the finished 6-lesson project
├── docs/
│   ├── style.css       # Shared stylesheet for all lesson pages
│   ├── lesson1.html
│   ├── lesson2.html
│   ├── lesson3.html
│   ├── lesson4.html
│   ├── lesson5.html
│   └── lesson6.html
└── .github/
    └── WORKFLOW.md     # Notes on the project workflow and pedagogical approach
```

### The wrapper module pattern

All hardware complexity — LVGL UI, audio playback, timers, interrupt scheduling — is hidden inside `pypod.py`, which is written and deployed by the teacher before the session. Students only ever write simple, readable Python in `main.py`, importing named helpers from `pypod`:

```python
from pypod import Track, add_track, play, on_song_selected, start
```

This keeps student code clean and beginner-friendly while still running real code on real hardware.

---

## 🛠️ Hardware requirements

- **[M5Stack Core S3](https://docs.m5stack.com/en/core/CoreS3)** — the target device
- **MicroSD card** inserted into the Core S3
  - `/sd/music/` — MP3 files named `Song Title (Artist).mp3`
  - `/sd/transcripts/` — Lyrics files named `Song Title.txt` ([LRC-style timestamps](https://en.wikipedia.org/wiki/LRC_(file_format)), `M:SS` format)
- **UIFlow 2 MicroPython** firmware flashed to the device

---

## 🚀 Getting started (teacher setup)

1. Flash the Core S3 with UIFlow 2 MicroPython firmware.
2. Copy `device/pypod.py` to the root of the device filesystem.
3. Populate the MicroSD card with MP3s and matching transcript files.
4. At the start of each session, deploy the student's current `main.py` to the device.
5. Open the lesson page for that session on the classroom screen.

---

## 📜 Licence

MIT — free to use, adapt, and share for educational purposes.
