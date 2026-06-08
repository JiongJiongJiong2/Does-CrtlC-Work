# Does your Ctrl+C really work?



A lightweight clipboard feedback tool that shows a visual animation near your cursor when you copy (`Ctrl+C`) or paste (`Ctrl+V`) text. Never wonder again whether your copy actually worked.

## Features

- **Copy Success** — Yellow indicator dot + expanding panel with scramble-text reveal of copied content
- **Copy Failed** — Red indicator dot (no text was copied)
- **Paste Success** — Green indicator dot
- **Cursor-bound** — Animation follows your mouse with spring-physics easing
- **Cyberpunk Unicode decode effect** — Text reveals left-to-right using block characters (`█ ▓ ▒ ░`)

## Quick Start

```bash
pip install PySide6 pyperclip keyboard
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

## File Structure

```
dose-ctrlc/
├── main.py                   # Entry point: system tray + event wiring
├── config.py                 # Animation timing, colors, sizes, spring params
├── requirements.txt          # Python dependencies
├── core/
│   ├── mouse_tracker.py      # Global cursor tracking + spring physics
│   └── clipboard_monitor.py  # Ctrl+C/V detection via keyboard hooks
└── ui/
    └── feedback_widget.py    # Full animation lifecycle (dot → box → text → collapse)
```

## Dependencies

- **PySide6** — Qt GUI framework
- **pyperclip** — Cross-platform clipboard access
- **keyboard** — Global hotkey listener