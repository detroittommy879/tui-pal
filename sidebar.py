from __future__ import annotations

import json
from typing import List, Dict

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QWidget, QVBoxLayout, QPushButton, QLabel


class SidebarWidget(QWidget):
    command_triggered = Signal(str)

    def __init__(self, config_path: str = "config.json", parent: QWidget | None = None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        self.layout.addWidget(QLabel("Presets"))
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            buttons = cfg.get("sidebar_buttons", [])
        except Exception:
            buttons = []
        for item in buttons:
            label = item.get("label", "Button")
            cmd = item.get("command", "\n")
            btn = QPushButton(label)
            btn.clicked.connect(lambda _=False, c=cmd: self.command_triggered.emit(c))
            self.layout.addWidget(btn)
        self.layout.addStretch(1)
