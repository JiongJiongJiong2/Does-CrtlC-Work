# Does your Ctrl+C really work?

A lightweight clipboard feedback tool that shows a visual animation near your cursor when you copy (`Ctrl+C`) or paste (`Ctrl+V`) text. Never wonder again whether your copy actually worked.

## Features

- **Copy Success** — Yellow indicator dot + expanding panel with scramble-text reveal of copied content
- **Copy Failed** — Red indicator dot (no text was copied)
- **Paste Success** — Green indicator dot
- **Cursor-bound** — Animation follows your mouse directly, no delay
- **Cyberpunk Unicode decode effect** — Text reveals left-to-right using block characters (`█ ▓ ▒ ░`)

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

## File Structure

```
dose-ctrlc/
├── main.py                   # Entry point: system tray + event wiring
├── config.py                 # Animation timing, colors, sizes, spring params
├── requirements.txt          # Python dependencies
├── app_icon.ico              # Application icon
├── core/
│   ├── __init__.py
│   ├── mouse_tracker.py      # Global cursor tracking + spring physics
│   └── clipboard_monitor.py  # Ctrl+C/V detection via keyboard hooks
└── ui/
    ├── __init__.py
    ├── feedback_widget.py    # Full animation lifecycle (dot → box → text → collapse)
    └── scramble_text.py      # Unicode block-character decode effect (standalone)
```

## Dependencies

- **PySide6** — Qt GUI framework
- **pyperclip** — Cross-platform clipboard access
- **keyboard** — Global hotkey listener

## License

[MIT](../LICENSE)