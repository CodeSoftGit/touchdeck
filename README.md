# touchdeck

[![MIT License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
![Static Badge](https://img.shields.io/badge/Python-Python?style=flat&logo=Python&logoColor=white&labelColor=gray)


Touch-friendly “Stream Deck-like” UI for small landscape displays, focused on quick music controls and system stats.

<img width="794" height="507" alt="touchdeck screenshot" src="https://github.com/user-attachments/assets/e11b0a90-857f-47ad-b9c8-e6f25e89dd63" />

## What it does
- Now Playing page with transport + seek using MPRIS over D-Bus (Linux-first; Windows is experimental)
- System Stats page (CPU/RAM + optional NVIDIA GPU via NVML)
- Speedtest page powered by `speedtest-cli`
- Clock page with 12/24h and optional seconds
- Themes and swipe navigation, tuned for 800x480 touch displays

> [!WARNING]
> touchdeck is early-stage software. Expect rough edges and please report issues with steps.

## Requirements
- Python 3.10+
- Linux desktop with D-Bus and an MPRIS-compatible player running (Spotify, VLC, etc.)
- PySide6 runtime (installed via dependencies)
- Optional: NVIDIA GPU + NVML for GPU stats (`nvidia-ml-py`)
- A small landscape display (defaults to 800x480) with touch input

## Install
### Using uv (recommended)
```bash
uv venv
uv sync
# Optional GPU support
uv pip install nvidia-ml-py
```

### Using pip
```bash
python -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -e ".[nvidia]"   # drop [nvidia] if you don't need GPU stats
```

## Run
```bash
uv run touchdeck        # if installed via uv
touchdeck               # if installed via pip
# or
python -m touchdeck
```

## Configuration
- Settings are stored at `~/.config/touchdeck/settings.json` (created on first save).
- Defaults:
  - `enable_gpu_stats`: true
  - `clock_24h`: false
  - `show_clock_seconds`: false
  - `music_poll_ms`: 500
  - `stats_poll_ms`: 1000
  - `ui_opacity_percent`: 90
  - `theme`: `midnight`
- Available themes: `midnight`, `glacier`, `sunset`

Example:
```json
{
  "enable_gpu_stats": false,
  "clock_24h": true,
  "show_clock_seconds": true,
  "music_poll_ms": 750,
  "stats_poll_ms": 1500,
  "ui_opacity_percent": 90,
  "theme": "glacier"
}
```

## Troubleshooting
- No Now Playing data: ensure a D-Bus/MPRIS-compatible player is running.
- GPU stats empty: install `nvidia-ml-py` and confirm NVML is available, or set `enable_gpu_stats` to false.
- Qt cannot open a display: run under X/Wayland with a reachable display and touch input.
- Speedtest errors: requires network access; try again or skip the Speedtest page.

## Development
- Follow the setup in `CONTRIBUTING.md`.
- Run locally with `uv run touchdeck` (or `python -m touchdeck` in an activated venv).
- Update `CHANGELOG.md` for user-visible changes.

## Credits
- Uses Google Noto Color Emoji
- Built with Python and PySide6

## License
touchdeck is licensed under the MIT License. See `LICENSE` for details.
