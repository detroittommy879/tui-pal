# TUI Automation Wrapper (Windows-first)

This MVP hosts an interactive CLI (e.g., powershell.exe) in a Qt (PySide6) window, renders output via a simple terminal widget, and triggers automation rules based on regex patterns.

## Prereqs

- Python 3.10+
- Windows 10/11 recommended (ConPTY). POSIX support is stubbed.

## Install

```powershell
python -m venv .venv
. .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

If `pywinpty` import fails, install build tools and retry:

```powershell
pip install --upgrade pip wheel setuptools
pip install pywinpty
```

## Run

```powershell
python .\main.py
```

The app will start `powershell.exe` by default. Change the shell in `config.json`.

## Config

- `config.json`: buttons and automation rules.
- Example included; edit and restart the app to apply.

## Notes

- Rendering is minimal (monochrome) for MVP. Color/attributes can be added using pyte state.
- On Windows, we use `pywinpty` for ConPTY; ensure it's installed.
- Automation defaults to `once=true` per rule to avoid loops.

## Roadmap

- Colors/attributes rendering
- Resize PTY on window resize
- Logging to file with secret masking
- Config schema validation with jsonschema
- POSIX reader via QSocketNotifier
