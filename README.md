<p align="center">
  <img src="clipboard_fx_icon_1780927283406.png" alt="Dose Ctrl+C Icon" width="128">
</p>

<h1 align="center">Does your Ctrl+C really work?</h1>

<p align="center">
  A lightweight clipboard feedback tool that shows a visual animation near your cursor<br>
  when you copy (<code>Ctrl+C</code>) or paste (<code>Ctrl+V</code>) text.<br>
  Never wonder again whether your copy actually worked.
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3776AB?style=flat&logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/PySide6-41CD52?style=flat&logo=qt&logoColor=white" alt="PySide6">
  <img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="MIT License">
</p>

## Features

- **Copy Success** — Yellow indicator dot + expanding panel with scramble-text reveal of copied content
- **Copy Failed** — Red indicator dot (no text was copied)
- **Paste Success** — Green indicator dot
- **Cursor-bound** — Animation follows your mouse directly, no delay
- **Cyberpunk Unicode decode effect** — Text reveals left-to-right using block characters (`█ ▓ ▒ ░`)

<p align="center">
  <img src="Does-CtrlC-Work-recording.gif" alt="Does-CtrlC-Work-recording">
</p>

## Quick Start

```bash
cd dose-ctrlc
pip install -r requirements.txt
python main.py
```

## Usage

| Action | Effect |
|--------|--------|
| `Ctrl+C` (with selection) | Yellow dot + panel with copied text |
| `Ctrl+C` (no selection) | Red dot (copy failed) |
| `Ctrl+V` | Green dot (paste detected) |
| `Ctrl+Shift+Q` | Quit the application |
| Right-click tray icon → Exit | Quit the application |

## Build

```bash
cd dose-ctrlc
pip install pyinstaller
pyinstaller --name "DoseCtrlC" --onefile --windowed --icon app_icon.ico main.py
```

The output exe will be in `dist/DoseCtrlC.exe`.

> Note: `keyboard` library requires **Administrator privileges** for global hotkey detection. Right-click the exe and select "Run as administrator".

## Tech Stack

| Language / Framework | Purpose |
|---------------------|---------|
| Python | Core language |
| PySide6 (Qt 6) | GUI framework |
| pyperclip | Cross-platform clipboard access |
| keyboard | Global hotkey listener |

## File Structure

```
dose-ctrlc/
├── main.py                   # Entry point: system tray + event wiring
├── config.py                 # Animation timing, colors, sizes, spring params
├── requirements.txt          # Python dependencies
├── app_icon.ico              # Application icon
├── clipboard_fx_icon_*.png   # Project logo
├── build.bat                 # PyInstaller build script
├── core/
│   ├── __init__.py
│   ├── mouse_tracker.py      # Global cursor tracking + spring physics
│   └── clipboard_monitor.py  # Ctrl+C/V detection via keyboard hooks
└── ui/
    ├── __init__.py
    ├── feedback_widget.py    # Full animation lifecycle (dot → box → text → collapse)
    └── scramble_text.py      # Unicode block-character decode effect (standalone)
```

## License

[MIT](../LICENSE)
