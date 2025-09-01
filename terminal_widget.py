from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QPainter, QColor, QFont, QKeyEvent, QFontMetrics, QGuiApplication
from PySide6.QtWidgets import QWidget, QMenu

import pyte


class TerminalWidget(QWidget):
    key_bytes = Signal(bytes)
    resized = Signal(int, int)  # cols, rows

    def __init__(self, cols: int = 120, rows: int = 30, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setFocusPolicy(Qt.StrongFocus)
        self.font = QFont("Consolas", 11)
        self.char_width = 8
        self.char_height = 16
        self.cols = cols
        self.rows = rows

        self.screen = pyte.Screen(self.cols, self.rows)
        self.stream = pyte.Stream(self.screen)

        self._pending_repaint = False
        self._coalesce_timer = QTimer(self)
        self._coalesce_timer.setInterval(16)
        self._coalesce_timer.timeout.connect(self._flush_repaint)

    # --- public API ---
    def feed_output(self, data: bytes) -> None:
        text = data.decode("utf-8", errors="replace")
        self.stream.feed(text)
        if not self._pending_repaint:
            self._pending_repaint = True
            self._coalesce_timer.start()

    # --- paint ---
    def paintEvent(self, event):  # type: ignore[override]
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(0, 0, 0))
        painter.setFont(self.font)
        fm = painter.fontMetrics()
        self.char_width = fm.horizontalAdvance("M")
        self.char_height = fm.height()

        for y, line in enumerate(self.screen.display):
            if y >= self.rows:
                break
            for x, ch in enumerate(line):
                if ch == "\x00" or ch == " ":
                    continue
                painter.setPen(QColor(200, 200, 200))
                painter.drawText(x * self.char_width, (y + 1) * self.char_height, ch)

        cx, cy = self.screen.cursor.x, self.screen.cursor.y
        painter.fillRect(
            cx * self.char_width,
            cy * self.char_height + self.char_height - 2,
            self.char_width,
            2,
            QColor(200, 200, 200),
        )

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        fm = QFontMetrics(self.font)
        cw = max(1, fm.horizontalAdvance("M"))
        ch = max(1, fm.height())
        cols = max(10, self.width() // cw)
        rows = max(5, self.height() // ch)
        if cols != self.cols or rows != self.rows:
            self.cols = cols
            self.rows = rows
            try:
                self.screen.resize(rows, cols)
            except Exception:
                self.screen.columns = cols
                self.screen.lines = rows
            self.resized.emit(cols, rows)
            self.update()

    # --- input ---
    def keyPressEvent(self, event: QKeyEvent) -> None:  # type: ignore[override]
        mods = event.modifiers()
        if (mods & Qt.ControlModifier) and (mods & Qt.ShiftModifier):
            if event.key() == Qt.Key_C:
                self._copy_to_clipboard()
                return
            if event.key() == Qt.Key_V:
                self._paste_from_clipboard()
                return
        b = self._map_key(event)
        if b is not None:
            self.key_bytes.emit(b)
        else:
            super().keyPressEvent(event)

    def _map_key(self, event: QKeyEvent) -> Optional[bytes]:
        key = event.key()
        text = event.text()
        if text:
            return text.encode()
        if key in (Qt.Key_Return, Qt.Key_Enter):
            return b"\r"
        if key == Qt.Key_Backspace:
            return b"\x08"  # Backspace
        if key == Qt.Key_Left:
            return b"\x1b[D"
        if key == Qt.Key_Right:
            return b"\x1b[C"
        if key == Qt.Key_Up:
            return b"\x1b[A"
        if key == Qt.Key_Down:
            return b"\x1b[B"
        if key == Qt.Key_C and event.modifiers() & Qt.ControlModifier:
            return b"\x03"  # Ctrl-C (SIGINT)
        if key == Qt.Key_D and event.modifiers() & Qt.ControlModifier:
            return b"\x04"  # Ctrl-D (EOT)
        return None

    # --- clipboard/context menu ---
    def _copy_to_clipboard(self) -> None:
        try:
            text = "\n".join(line.rstrip() for line in self.screen.display[: self.rows])
            QGuiApplication.clipboard().setText(text)
        except Exception:
            pass

    def _paste_from_clipboard(self) -> None:
        try:
            text = QGuiApplication.clipboard().text()
            if not text:
                return
            normalized = text.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "\r\n")
            self.key_bytes.emit(normalized.encode())
        except Exception:
            pass

    def contextMenuEvent(self, event) -> None:  # type: ignore[override]
        menu = QMenu(self)
        act_copy = menu.addAction("Copy All")
        act_paste = menu.addAction("Paste")
        action = menu.exec(event.globalPos())
        if action == act_copy:
            self._copy_to_clipboard()
        elif action == act_paste:
            self._paste_from_clipboard()

    # --- internals ---
    def _flush_repaint(self) -> None:
        self._coalesce_timer.stop()
        self._pending_repaint = False
        self.update()
