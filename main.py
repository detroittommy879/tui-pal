from __future__ import annotations

import json
import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMainWindow, QWidget, QHBoxLayout, QMessageBox

from automation import AutomationEngine, AutomationRule
from process_manager import ProcessManager
from terminal_widget import TerminalWidget
from sidebar import SidebarWidget
import process_manager as pm


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("TUI Automation Wrapper")
        self.resize(1200, 800)

        # Core components
        self.process = ProcessManager()
        try:
            print(f"Windows PTY backend: {getattr(pm, '_PTY_BACKEND_NAME', None)}", file=sys.stderr)
        except Exception:
            pass
        self.terminal = TerminalWidget()
        self.sidebar = SidebarWidget()

        # Layout
        central = QWidget(self)
        layout = QHBoxLayout(central)
        layout.addWidget(self.sidebar, 0)
        layout.addWidget(self.terminal, 1)
        self.setCentralWidget(central)

        # Signals
        self.process.output.connect(self.on_output)
        self.process.exited.connect(self.on_exit)
        self.process.error.connect(self.on_error)
        self.terminal.key_bytes.connect(self.process.write)
        self.terminal.resized.connect(self.process.resize)
        self.sidebar.command_triggered.connect(self._send_text)

        # Automation
        rules = self._load_rules()
        self.automation = AutomationEngine(rules)

        # Start default shell
        shell, args = self._default_shell()
        ok = self.process.start(shell, args)
        if not ok:
            try:
                print("Failed to start process.", file=sys.stderr)
            except Exception:
                pass
            QMessageBox.critical(self, "Error", "Failed to start process.")
        else:
            # initialize PTY size to current widget grid
            self.process.resize(self.terminal.cols, self.terminal.rows)

    def _default_shell(self) -> tuple[str, list[str]]:
        cfg = self._load_config()
        shell = cfg.get("shell") or ("powershell.exe" if sys.platform == "win32" else "bash")
        args: list[str] = []
        return shell, args

    def _load_config(self) -> dict:
        try:
            with open("config.json", "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def _load_rules(self) -> list[AutomationRule]:
        cfg = self._load_config()
        rules_cfg = cfg.get("automation_rules", [])
        rules: list[AutomationRule] = []
        for r in rules_cfg:
            rules.append(
                AutomationRule(
                    name=r.get("name"),
                    pattern=r.get("pattern", ""),
                    response=r.get("response", ""),
                    once=r.get("once", True),
                    case_sensitive=r.get("case_sensitive", False),
                    delay_ms=r.get("delay_ms", 0),
                    is_active=r.get("is_active", True),
                )
            )
        return rules

    # --- slots ---
    def on_output(self, data: bytes) -> None:
        # Automation check
        try:
            text = data.decode("utf-8", errors="replace")
            resp = self.automation.evaluate(text)
            if resp:
                self.process.write(resp.encode())
        except Exception:
            pass
        # Render
        self.terminal.feed_output(data)

    def on_exit(self, code: int) -> None:
        QMessageBox.information(self, "Process exited", f"Exit code: {code}")

    def on_error(self, message: str) -> None:
        try:
            print(f"Process error: {message}", file=sys.stderr)
        except Exception:
            pass
        QMessageBox.critical(self, "Process error", message)

    def _send_text(self, text: str) -> None:
        # Ensure commands from the sidebar are executed immediately by sending Enter.
        payload = text
        if not payload.endswith("\r") and not payload.endswith("\n"):
            payload += "\r\n"
        self.process.write(payload.encode())


if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())
