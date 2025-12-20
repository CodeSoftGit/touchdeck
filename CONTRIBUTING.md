# Contributing to touchdeck

Thanks for helping make touchdeck better. This project is early-stage and Linux-first; small, focused changes with clear repro steps are easiest to review.

## Local setup
1) Install dependencies with uv (recommended):
```bash
uv venv
uv sync
# Optional GPU stats
uv pip install nvidia-ml-py
```
2) Run the app:
```bash
uv run touchdeck
```
3) If you prefer pip:
```bash
python -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -e ".[nvidia]"   # drop [nvidia] if you don't need GPU stats
touchdeck
```

## Development guidelines
- Keep the default experience working on 800x480 touch displays.
- Favor clear type hints and small, testable functions.
- When adding settings, document them in `README.md` and ensure safe defaults.
- Handle failures quietly where appropriate (e.g., missing MPRIS player, NVML not available) and log or display gentle messages.
- UI styling should use the existing theme tokens rather than hard-coded colors.

## Testing
- Install dev extras: `pip install -e ".[dev]"` (or `uv pip install pytest`).
- Run automated tests: `pytest`.
- Do a quick manual smoke pass:
  - Start an MPRIS-compatible player, then verify Now Playing controls.
  - Open the Settings page, toggle options, and confirm they persist to `~/.config/touchdeck/settings.json`.
  - Run the Speedtest page and ensure errors are handled gracefully if the network is unavailable.

## Submitting changes
- Add a short note to `CHANGELOG.md` under **[Unreleased]** for user-visible changes.
- Keep pull requests small and focused; include repro steps for bug fixes.
- Follow the `CODE_OF_CONDUCT.md` in all interactions.
