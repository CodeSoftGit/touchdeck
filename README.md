# touchdeck

A touchscreen “Stream Deck-like” UI for small displays:

- **Now Playing** page using **MPRIS over D-Bus** (Linux desktops)
- **System Stats** page (CPU/RAM + optional NVIDIA GPU via NVML)
- **Clock** page
- **Swipe** left/right to switch pages
- **Themes** for how *you* want your touchdeck to look
- **And more!**

> [!CAUTION]
> touchdeck is alpha software and should be treated as such.

> [!IMPORTANT]
> touchdeck is developed Linux-first, though may work on Windows. Support will not be provided for other platforms.

<img width="794" height="507" alt="image" src="https://github.com/user-attachments/assets/e11b0a90-857f-47ad-b9c8-e6f25e89dd63" />


## Install
### using uv (Recommended)

Set up your environment:
```bash
uv venv
uv sync
```
Optionally install NVIDIA features:
```bash
uv pip install nvidia-ml-py
```

### using pip

```bash
python -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -e ".[nvidia]"
```

If you don't have an NVIDIA GPU, skip `.[nvidia]`:

```bash
pip install -e .
```

## Run
### If you installed with uv

```bash
uv run touchdeck
```

# If you installed with pip

```bash
touchdeck
# or
python -m touchdeck
```

## Notes

- Needs a running MPRIS-compatible player (Spotify, VLC, etc).
- Built for a small landscape display (defaults to 800x480).

## Credits

Uses Google Noto Color Emoji
Built with Python and PySide6

## License

touchdeck is license under the MIT License.
