<p align="center">
  <img src="clipboard_fx_icon_1780927283406.png" alt="Dose Ctrl+C Icon" width="128">
</p>

<h1 align="center">Does your Ctrl+C really work?</h1>

<p align="center">
  A lightweight clipboard feedback tool that shows a visual animation near your cursor<br>
  when you copy (<code>Ctrl+C</code>) or paste (<code>Ctrl+V</code>) content.<br>
  Never wonder again whether your copy actually worked.
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3776AB?style=flat&logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/PySide6-41CD52?style=flat&logo=qt&logoColor=white" alt="PySide6">
  <img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="MIT License">
</p>

## Features

- **Copy Success (Text)** — Yellow indicator dot + expanding panel with scramble-text reveal.
- **Copy Success (Image)** — 120×120 rounded thumbnail with pixel-style reveal animation.
- **Multi-Image Stack** — When copying multiple images (2+), a stack effect fans out behind the main thumbnail, with configurable real-thumbnail or placeholder mode.
- **Holding Mode** — Feedback animation stays on screen until a paste is detected or a timeout is reached, giving you confidence that the copy landed.
- **Parallel Image Loading** — Web images are downloaded concurrently (up to 3 threads), reducing wait time for multi-image clipboard content.
- **Image Exit Animation** — Thumbnail shrinks toward the yellow indicator dot and disappears in sync with text collapse.
- **Web Image Compatibility** — Supports clipboard image extraction from:
  - Direct bitmap (`image/*`)
  - Local file URL/path (`text/uri-list`, `file:///...`)
  - HTML `<img src=...>` (all images extracted, not just the first)
  - `data:image/...;base64` and `http/https` image URL fallback
- **Copy Failed** — Red indicator dot (no valid copied content detected).
- **Paste Success** — Green indicator dot.
- **Silent Mode** — Toggle visual feedback on/off while app keeps running in tray (`Ctrl+Shift+M`).
- **Cursor-bound** — Animation follows your mouse directly, no delay.
- **System Tray Resident** — Background running with quick status and exit control.

<p align="center">
  <img src="gif/Does-CtrlC-Work-recording.gif" alt="Does-CtrlC-Work-recording">
</p>

<p align="center">
  <img src="gif/RecordingpicFeatures.gif" alt="Does-CtrlC-Work-recording">
</p>

<p align="center">
  <img src="gif/RecordingMultiImages-final1.gif" alt="Does-CtrlC-Work-recording">
</p>

## Usage

| Action | Effect |
|--------|--------|
| `Ctrl+C` (with text) | Yellow dot + text panel |
| `Ctrl+C` (with image) | Yellow dot + image thumbnail + stack if multiple images |
| `Ctrl+C` (no selection / unchanged clipboard) | Red dot (copy failed) |
| `Ctrl+V` | Green dot (paste detected) |
| `Ctrl+Shift+M` | Toggle Silent Mode (visual feedback on/off) |
| `Ctrl+Shift+Q` | Quit the application |
| Right-click tray icon → Exit | Quit the application |

## Quick Start

```bash
cd dose-ctrlc
pip install -r requirements.txt
python main.py
```

If you only want to use it, download the `.exe` from Releases.

## Build

Recommended (avoid interpreter mismatch):

```bash
cd dose-ctrlc
python -m PyInstaller --noconfirm --clean --name "DoesCtrlCWork" --onefile --windowed --icon app_icon.ico --version-file version.txt --add-data "config.py;." main.py
```

If you use Conda and want to force a specific env:

```bash
conda run -n ctrlc python -m PyInstaller --noconfirm --clean --name "DoesCtrlCWork" --onefile --windowed --icon app_icon.ico --version-file version.txt --add-data "config.py;." main.py
```

Output exe location: `dist/DoesCtrlCWork.exe`.

> Note: `keyboard` library requires **Administrator privileges** for global hotkey detection on Windows.  
> Right-click the exe and choose "Run as administrator".

## New Release Description
### v2.1.0 — Multi-Image Stack + Holding Mode + Parallel Loading

This release adds multi-image visual feedback, a holding mode that waits for paste confirmation, and parallel image downloading for faster web image handling.

**Highlights**
- **Multi-Image Stack Animation** — When copying 2+ images (from file manager or web), additional images fan out behind the main thumbnail as a stack. Stack layers use spring-physics animation and can show either real thumbnails or translucent placeholders (configurable via `show_real_thumbnails`).
- **Holding Mode** — Animation stays visible until a paste (`Ctrl+V`) is detected or a 30-second timeout is reached, giving clear confirmation that the copy-paste cycle completed.
- **Parallel Image Download** — Web images are now fetched concurrently using `ThreadPoolExecutor` (up to 3 threads). Copying 3 web images takes ~0.8s instead of ~2.4s.
- **Full HTML Image Extraction** — All `<img>` tags in clipboard HTML are now extracted (previously only the first), so multi-image web copies are correctly detected.
- **Configurable Placeholder Opacity** — Image placeholder transparency is now adjustable via `placeholder_opacity` in `IMAGE_STACK` config.

**Bug Fixes**
- Fixed stack animation starting at wrong time (state machine timing issue).
- Fixed stack placeholder layers disappearing after the first image loaded.
- Fixed drawing order: main image now correctly renders on top of stack layers.

**Notes**
- For stable builds, package with `python -m PyInstaller` from the intended environment.
- Run as Administrator if global hotkey capture is blocked by system policy.

## Tech Stack

| Language / Framework | Purpose |
|---------------------|---------|
| Python | Core language |
| PySide6 (Qt 6) | GUI framework |
| pyperclip | Clipboard text fallback |
| keyboard | Global hotkey listener |
| PyInstaller | Windows executable packaging |

## File Structure

```text
dose-ctrlc/
├── main.py                   # Entry point: tray + hotkeys + event wiring
├── config.py                 # Animation timing, colors, sizes, params
├── requirements.txt          # Python dependencies
├── app_icon.ico              # Application icon
├── version.txt               # PyInstaller version metadata
├── build.bat                 # Build script
├── core/
│   ├── mouse_tracker.py      # Global cursor tracking + spring physics
│   └── clipboard_monitor.py  # Ctrl+C/V detection + rich clipboard extraction
└── ui/
    └── feedback_widget.py    # Dot/text/image animation lifecycle
```

## License

[MIT](../LICENSE)
