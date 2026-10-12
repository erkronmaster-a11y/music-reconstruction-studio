# AI Music Reconstruction Studio

Turns your finished songs (the full mix plus whatever stems you have) back into
editable **Ableton Live 12** projects: bass, melody and drum MIDI aligned to your
original audio, with your original vocals kept untouched.

**It reconstructs. It does not compose.** Notes it isn't sure of are marked as
uncertain, never passed off as exact, and missing notes are never invented.

## Status
| Sprint | Contents | State |
|---|---|---|
| 0 | Environment check, Live API test, transcription probe | 🟡 waiting on Mac test results |
| 1 | Audio to MIDI (bass, melody) | not started |

## Start here
- **On the Mac:** [SETUP_MACOS.md](SETUP_MACOS.md)
- **How it's built:** [ARCHITECTURE.md](ARCHITECTURE.md)
- **Plan:** [ROADMAP.md](ROADMAP.md)
- **What has been measured:** [TEST_RESULTS.md](TEST_RESULTS.md)
- **Rules for contributors and AI agents:** [AGENTS.md](AGENTS.md)

## Developer quick start
```bash
uv venv -p 3.11 .venv && uv pip install -p .venv/bin/python -r requirements.txt
.venv/bin/python -m pytest -q tests
.venv/bin/python tools/probe_transcription.py   # Basic Pitch vs pYIN on known notes
```
