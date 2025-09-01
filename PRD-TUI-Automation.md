# Product Requirements Document (PRD)

Title: TUI Automation Wrapper (Windows-first, cross-platform later)
Owner: You
Date: 2025-09-01
Status: Draft for implementation

## 1) Summary

A desktop app that runs text-based terminal (TUI) applications inside a GUI, renders the terminal output, and automates interactions based on user-defined pattern rules. Primary goal: reliably drive interactive CLI tools (e.g., ssh prompts, package installers, REPLs) with configurable automation.

## 2) Goals and Non-Goals

- Goals (MVP)

  - Host an interactive TUI process in a window and provide keyboard input.
  - Render terminal output with color and cursor movement.
  - Define automation rules (regex pattern -> response) that trigger on output.
  - Provide a sidebar of preset commands/buttons.
  - Load/save configuration from JSON/YAML.
  - Windows support first (ConPTY); Linux/macOS follow-up.

- Non-Goals (MVP)
  - Full VT/DEC terminal parity; advanced terminals (tmux/vim edge features) may be imperfect.
  - SSH client implementation (use system ssh or any CLI program as a child process).
  - Multi-tab/multi-session management (single session MVP).

## 3) Personas & Primary Use Cases

- DevOps Engineer: Automate repetitive CLI setup flows (e.g., answering common prompts).
- QA/Release Engineer: Scripted validation runs with interactive tools.
- Support Engineer: Assist users by wrapping complex TUIs with presets.

Top use cases

- Auto-respond to login/password prompts (e.g., ssh, database CLIs).
- Auto-accept confirmations (y/n) in installers or CLIs.
- Run one-click presets (buttons) that send commands.

## 4) User Stories (Acceptance Criteria)

- As a user, I can start a command like `ssh user@host` inside the app and see the live terminal.
  - AC: Text, colors, and cursor updates render; I can type; command runs as expected.
- As a user, I can define a regex `"password:"` with response `"hunter2\n"`.
  - AC: When the prompt appears, the response is sent once; the flow continues.
- As a user, I can click a preset button to send `"y\n"` or a longer command.
  - AC: Command text is injected immediately and visible in the session.
- As a user, I can resize the window.
  - AC: Terminal resizes; wrapped lines behave reasonably; app remains responsive.
- As an admin, I can load a config file with buttons and rules.
  - AC: App reflects buttons/rules without code changes; invalid config yields a clear error.

## 5) Functional Requirements

- Terminal Hosting

  - Start/stop a child process attached to a pseudo terminal (Windows: ConPTY via pywinpty; POSIX: pty).
  - Read/write raw byte streams; handle UTF-8 with replacement for invalid bytes.
  - Surface process exit status and errors.

- Rendering

  - Interpret ANSI escape codes (SGR colors, clear, cursor movement) via a terminal emulator backend (e.g., pyte) and paint to a custom widget.
  - Monospace font; show cursor; basic color support (16 colors minimum; 256 preferable).

- Input

  - Forward keystrokes (printable, Enter, Backspace, arrows, Home/End, PgUp/PgDn if feasible) to the process.
  - Map common shortcuts (Ctrl+C, Ctrl+D) to terminal sequences.

- Automation Rules

  - Regex + response pairs with options: once vs repeat, delay ms (optional), case sensitivity, active flag.
  - Apply rules on the raw output stream before rendering; avoid self-trigger loops.
  - Rule evaluation order deterministic (list order) with short-circuiting.

- Preset Commands

  - Clickable buttons that send predefined text/commands.
  - Optional grouping/labels.

- Configuration

  - Load from `config.json` (JSON) by default; YAML optional later.
  - Validate on load; provide helpful errors.

- Logging
  - Optional session log to file (plain text) with timestamped lines.

## 6) Non-Functional Requirements

- Performance: Keep UI responsive; process and render updates at ~30–60 fps target; avoid blocking the UI thread.
- Reliability: Survive child process exit; show a clear status; allow restart.
- Security: Do not log secrets by default; option to mask sensitive responses. Encourage secure storage of secrets (e.g., Windows Credential Manager) but not required in MVP.
- Portability: Windows 10/11 with ConPTY; plan for POSIX PTYs later.
- Observability: Minimal telemetry (optional) or none in MVP.

## 7) Platform Constraints & Risks

- Windows
  - Use ConPTY (pywinpty). Qt’s QSocketNotifier doesn’t work with console handles; use a dedicated reader thread or QTimer polling for pipe reads.
  - Keyboard mapping on Windows differs for some virtual keys; ensure core keys work.
- POSIX
  - Use pty.openpty; integrate with QSocketNotifier for non-blocking reads.
- Risks
  - Terminal emulation completeness (pyte coverage) vs advanced TUIs.
  - ANSI/UTF-8 edge cases and large output bursts.
  - Infinite rule-response loops; require guard state.

## 8) System Architecture (High Level)

- MainWindow (PySide6): Hosts layout, menu/toolbar, status bar.
- ProcessManager
  - Windows: spawns child via pywinpty (ConPTY). Background thread reads bytes; thread-safe queue to main thread.
  - POSIX: PTY + QSocketNotifier. Common interface: start(cmd, args, env), stop(), write(bytes).
- TerminalEmulator
  - pyte Screen/Stream; feed decoded text; maintain buffer state.
  - TerminalWidget paints grid using QPainter; monospace font; draws cursor; handles resize.
- AutomationEngine
  - Subscribes to output; evaluates rules; writes responses; guards against re-entrant triggers.
- SidebarWidget
  - Buttons from config; emits command strings to ProcessManager.
- ConfigLoader
  - Loads/validates config.json; exposes typed objects.

## 9) Data Contracts

- Config schema (JSON) v1

```
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "TUI Automator Config",
  "type": "object",
  "properties": {
    "sidebar_buttons": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["label", "command"],
        "properties": {
          "label": {"type": "string"},
          "command": {"type": "string"}
        }
      },
      "default": []
    },
    "automation_rules": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["pattern", "response"],
        "properties": {
          "name": {"type": "string"},
          "pattern": {"type": "string"},
          "response": {"type": "string"},
          "once": {"type": "boolean", "default": true},
          "case_sensitive": {"type": "boolean", "default": false},
          "delay_ms": {"type": "integer", "minimum": 0, "default": 0},
          "is_active": {"type": "boolean", "default": true}
        }
      },
      "default": []
    },
    "shell": {"type": "string", "description": "Optional shell/command to start by default"}
  },
  "additionalProperties": false
}
```

- ProcessManager interface (pseudo)

  - start(command: string, args: string[], env?: dict) -> bool
  - stop(signal?: string) -> void
  - write(data: bytes) -> void
  - signals/events:
    - onOutput(data: bytes)
    - onExit(code: int, signal?: string)
    - onError(message: string)

- TerminalWidget interface (pseudo)
  - feedOutput(data: bytes) -> void
  - signals:
    - onKey(bytes) -> forward to ProcessManager.write

## 10) UX Notes

- Single main window: left sidebar (buttons + config reload), right terminal area.
- Menu: File (Open Config, Exit), View (Font size +/-, Toggle log), Help (About).
- Status bar: process running/exit status.

## 11) Edge Cases & Error Handling

- Child exits unexpectedly: show message; disable input; allow restart.
- Huge output bursts: throttle repaint (coalesce) to ~30–60 fps.
- Binary/noisy output: replace undecodable bytes; don’t crash.
- Regex pathologies: timeouts not required in MVP; recommend simple patterns.
- Rule loops: per-rule ‘once’ default; optionally cooldown.

## 12) Telemetry, Logging, and Privacy

- Session logging: off by default; when enabled, write to file; masking for patterns with sensitive responses (e.g., replace with \*\*\*).
- No external telemetry in MVP.

## 13) Packaging & Distribution

- Dev: pip install requirements; run `python main.py`.
- Optional later: PyInstaller one-file exe for Windows.

## 14) Milestones (MVP-first)

- M0: Skeleton project, config load, UI scaffold (1–2 days)
- M1: Windows ConPTY ProcessManager with basic read/write (2–3 days)
- M2: Terminal emulation + rendering + input (pyte + paint) (3–5 days)
- M3: Automation engine + sidebar presets + config wiring (2–3 days)
- M4: Resize, logging, error states, polish (2–3 days)

## 15) Test Plan (Minimum)

- Unit
  - Config validation with valid/invalid fixtures.
  - Rule engine: match/no-match, once vs repeat, case sensitivity.
- Integration
  - Spawn `cmd.exe` or `powershell.exe` on Windows; echo/dir; verify echo text.
  - Simulate prompt output and ensure auto-response is sent.
  - Resize window and ensure no crashes; cursor visible.
- Manual
  - Run `python` REPL; type `print("ok")`; see output.
  - Run `ssh` to a known host; test password prompt flow (against a test VM).

## 16) Open Questions

- Do we need secret storage integration in MVP? (Probably no; document risks.)
- Do we need multi-session tabs? (Defer.)
- How important is full 256-color vs basic 16-color? (Start simple; iterate.)

## 17) Out of Scope (for now)

- Macro recording/playback
- Terminal file uploads/downloads
- Multi-user collaboration

## 18) References

- idea2.md: Architecture with PySide6 + pyte + PTY + QProcess (baseline)
- idea.md: Alternative sketch using pexpect/QTextEdit (less Windows-friendly)

---

# Implementation Notes for AI Agents

Provide these artifacts and follow this order:

1. Project structure

```
/ (repo root)
  main.py                # Entry point, MainWindow wiring
  process_manager.py     # ConPTY (Windows) + PTY (POSIX) impl with common interface
  terminal_widget.py     # pyte integration + paintEvent + keyPressEvent
  automation.py          # Rule engine and config models
  sidebar.py             # Preset buttons from config
  config.json            # Example config (matches schema)
  requirements.txt       # PySide6, pyte, pywinpty (win), jsonschema
  README.md              # How to run (Windows-first)
```

2. Dependencies (Windows)

- PySide6
- pyte
- pywinpty (Windows only)
- jsonschema (config validation)

3. Contracts

- Implement ProcessManager with:
  - start(cmd: str, args: list[str]) -> bool
  - write(data: bytes) -> None
  - stop() -> None
  - thread emitting PySide6 signal: output(bytes)
- Implement TerminalWidget with:
  - feed_output(data: bytes) -> None
  - key mapping for arrows, Enter, Backspace, Ctrl+C, Ctrl+D

4. Minimal happy-path script to validate

- Start default shell from config (e.g., powershell.exe) in ConPTY.
- Render prompt, send `echo Hello` via sidebar, verify "Hello" appears.
- Add rule: pattern `"Proceed\? \[Y/N\]"` -> `"Y\n"`, simulate output, ensure it triggers.

5. Edge handling to code

- Coalesce paint updates with QTimer (e.g., 16–33ms interval) when many chunks arrive.
- Guard rules with `once=true` by default; allow toggling.
- On window resize, update terminal size (ConPTY: ResizePseudoConsole; POSIX: TIOCSWINSZ) and pyte screen.

6. Example config.json

```
{
  "sidebar_buttons": [
    { "label": "List", "command": "dir\n" },
    { "label": "Clear", "command": "cls\n" }
  ],
  "automation_rules": [
    { "name": "Accept prompt", "pattern": "\\[Y/N\\]", "response": "Y\n", "once": true }
  ],
  "shell": "powershell.exe"
}
```

7. Done criteria (MVP)

- On Windows 10/11, app runs; can start powershell.exe; render prompt and colors; send keys; automation triggers; resize works; no crashes in 15-minute smoke test.
