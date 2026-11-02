<p align="center">
  <img src="clipboard_fx_icon_1780927283406.png" alt="Does CtrlC Work Icon" width="128">
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
- **Text Viewport Navigation** — Use `Ctrl+Alt+←/→` to pan and `Ctrl+Alt+↓/↑` to expand/collapse. Plain arrows remain available to the foreground application.
- **Copy Success (Image)** — 120×120 rounded thumbnail with pixel-style reveal animation.
- **Multi-Image Layouts** — Choose the original three-image fan or a four-image horizontal cascade from the tray's compact text selector; the selected mode is remembered.
- **Holding Mode** — Copy feedback stays on screen until `Ctrl+V` is detected or a timeout is reached. It represents a paste-key intent, not a system-wide guarantee that the target app accepted the paste.
- **Clipboard-first Image Loading** — Browser-provided `image/*` bytes are snapshotted before any URL fetch; file/data-URI sources follow, and web-image download is a bounded final fallback.
- **Optional Web Image Fallback** — Remote previews are off by default. Start with `--remote-previews` to allow bounded, cancellable public HTTP(S) image requests. Clipboard-provided images work offline.
- **Image Exit Animation** — Thumbnail shrinks toward the yellow indicator dot and disappears in sync with text collapse.
- **Web Image Compatibility** — Supports clipboard image extraction from:
  - Direct bitmap (`image/*`)
  - Local file URL/path (`text/uri-list`, `file:///...`)
  - HTML `<img src=...>` (all images extracted, not just the first)
  - `data:image/...;base64` and `http/https` image URL fallback
- **Copy Unconfirmed** — Red indicator dot when a clipboard update could not be confirmed; this does not prove that the target application failed to copy.
- **Paste Key Detected** — Green indicator dot for the key intent; this does not prove that the target application accepted the paste.
- **Silent Mode** — Toggle visual feedback on/off while app keeps running in tray (`Ctrl+Shift+M`).
- **Cursor-bound** — Animation follows your mouse directly, no delay.
- **System Tray Resident** — Background running with quick status and exit control.
- **Per-surface Styling** — Independently configure menu background/text, content background/text, image surface, plus separate English and Chinese feedback fonts.

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
| `Ctrl+C` without a confirmed clipboard update | Red dot (update unconfirmed) |
| `Ctrl+V` | Green dot (paste detected) |
| `Ctrl+Shift+M` | Toggle Silent Mode (visual feedback on/off) |
| `Ctrl+Shift+H` | Toggle Holding Mode (dismiss a held copy on `Ctrl+V`) |
| `Ctrl+Shift+Q` | Quit the application |
| Tray image-layout selector (`Fan/Cascade`) | Switch future multi-image feedback between fan and horizontal cascade |
| Right-click tray icon → Exit | Quit the application |

## Quick Start

```bash
cd dose-ctrlc
pip install -r requirements.txt
python main.py
```

If you only want to use it, download the `.exe` from Releases.

## Build

Build instructions and the measured package-size audit are in [docs/PACKAGING.md](docs/PACKAGING.md). Use the checked-in spec: it excludes unused Qt modules/plugins and is the lean reproducible onefile build.

```bash
cd dose-ctrlc
.\.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean DoesCtrlCWork.spec
```

Do not append broad `--collect-all` / `--hidden-import` flags unless a measured missing-runtime error requires them; those flags can undo the spec's size exclusions.

If you use Conda and want to force a specific env:

```bash
conda run -n ctrlc python -m PyInstaller --noconfirm --clean DoesCtrlCWork.spec
```

Output exe location: `dist/DoesCtrlCWork.exe`.

If global hotkeys are unavailable, clipboard-change feedback continues. Normal Windows use does not require running the entire application as administrator; elevated foreground applications may restrict input observation.

## Documentation

The `feature/device-transfer` branch is developing automatic nearby-device discovery for two Windows computers with Bluetooth enabled. Install `requirements.txt` for source development, then start normally with `python main.py`; discovery starts automatically and can be disabled for debugging with `--no-nearby`. No manual IP, port, key setup or new transfer interface is required. The native backend currently provides discovery only: automatic authenticated pairing, Windows BLE text reception, drag-to-send integration and cross-device delivery are not complete. All 203 tests pass, and the frozen exe has passed real startup, advertising/scanning and shutdown checks on one PC; two-computer validation remains pending. `requirements-transfer.txt` is only for internal protocol experiments. See [current capabilities and limits](docs/TRANSFER_PREVIEW.md).

- [Documentation index](docs/README.md)
- [Current technical review and status](docs/planning711/PROJECT_REVIEW.md)
- [Packaging slimming guide](docs/PACKAGING.md)

## Release History

### v2.3.1 — Clipboard Sessions and Safe Preview Lifecycle

Copy intents and clipboard changes are correlated independently of GUI callback order. New events invalidate old retries and image jobs; late images update only their own copy session. All application hotkeys dispatch on the GUI thread. A bounded preview service owns cancellation, decoding and shutdown. Remote fetching is opt-in, image inputs have byte/pixel/count budgets, navigation uses modifier keys, logs rotate, and a process lock prevents duplicate instances. `app_version.py` is the version source; build dependencies are pinned in `requirements-build.txt`.

Windows offscreen regression and isolated event tests accompany these changes. Native desktop interaction and other platforms still require manual acceptance.

### v2.3.0 — Text Viewport, Clipboard Image Reliability, and Typography

This release contains the text-navigation, clipboard-image reliability, styling, and animation improvements introduced by the current feature branch.

**Highlights**

- Long copied text now uses a bounded viewport instead of expanding the feedback panel indefinitely. Horizontal arrow input pans smoothly as one shared column; vertical input reveals up to five compact text rows for inspection.
- Expanded text remains visible until the user collapses it. If its normal display timer has already elapsed, collapsing it completes the exit animation instead of dismissing content prematurely.
- Short text panels now use their measured content width, while longer lines retain a fixed readable viewport without blank trailing space at the scroll limit.
- Clipboard images now prefer the local bitmap or raw `image/png/jpeg/webp/gif/bmp/tiff` MIME bytes already supplied by the clipboard. HTML, file, data-URI, and remote URL sources remain ordered fallbacks.
- Remote image URLs run only in background workers, with a 3-second per-attempt timeout, one limited retry, a 2 MB per-image limit, and structured diagnostics at `%LOCALAPPDATA%\\DoseCtrlC\\dose-ctrlc.log`.
- Tray settings now expose independent colours for menu/content/image surfaces and independent English/Chinese feedback font pickers. Both persist across restarts.
- Right-edge docking now uses a longer S-curve transition and a 4 ms active motion clock for smoother yellow-dot and anchor-line movement; timers stop while idle.




**Notes**
- For stable builds, package with `python -m PyInstaller` from the intended environment.
- Run as Administrator if global hotkey capture is blocked by system policy.

## Tech Stack

| Language / Framework | Purpose |
|---------------------|---------|
| Python | Core language |
| PySide6 (Qt 6) | GUI framework |
| keyboard | Global hotkey listener |
| PyInstaller | Windows executable packaging |

## Project Architecture

```text
Global hotkeys + clipboard change event
                 │
                 ▼
       ClipboardMonitor (core)
  snapshot text / QImage / raw MIME bytes
  file path / data URI / HTML image URLs
                 │
                 ├── local resources ──► background byte worker ──► QImage decode
                 └── remote URLs ──────► bounded download fallback
                 │
                 ▼
       ClipboardFXApp (main.py)
  settings, tray commands, navigation-hotkey bridge
                 │
                 ▼
          FeedbackWidget (ui)
  property animation engine + cursor docking + text viewport
                 │
                 ▼
  Dot / ContentBox / image renderers / image layouts
```

- `ClipboardMonitor` takes a bounded snapshot as soon as clipboard ownership changes, so browser-provided raw image data is not lost before background work begins.
- `FeedbackWidget` owns the short-lived visual lifecycle. `PropertyEngine` advances active animations on a precise timer and stops it when there is no active animation or frame client.
- `TextViewport` retains the full copied text but only renders a small visible slice, avoiding layout and allocation costs for long clipboard content.
- `ThemeController` and `QSettings` persist palettes, component colour overrides, image-layout preference, and language-specific feedback fonts.

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
│   └── clipboard_monitor.py  # Clipboard snapshots + rich image extraction/fallbacks
└── ui/
    ├── animation/
    │   └── property_engine.py # Active animation frame clock and interpolation
    ├── components/            # Dot, content box, and image renderers
    ├── feedback_widget.py     # Dot/text/image lifecycle + edge docking
    ├── text_viewport.py       # Bounded long-text navigation model
    ├── text_style.py          # Script-aware text fonts, metrics, and layouts
    ├── theme.py               # Palette and component-colour persistence
    ├── tray_menu.py           # Qt tray popup
    └── windows_tray_menu.py   # Native Windows owner-drawn tray menu
```

## License

[MIT](../LICENSE)
