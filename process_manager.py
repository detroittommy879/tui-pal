from __future__ import annotations

import sys
import threading
from typing import Callable, Optional

from PySide6.QtCore import QObject, Signal

# Windows-first: use pywinpty to access ConPTY
IS_WINDOWS = sys.platform == "win32"

if IS_WINDOWS:
    _PTY_BACKEND = None  # type: ignore
    _PTY_BACKEND_NAME: Optional[str] = None
    _PYWINPTY_IMPORT_ERROR: Optional[BaseException] = None
    _WINPTY_IMPORT_ERROR: Optional[BaseException] = None
    try:
        import pywinpty as _PTY_BACKEND  # type: ignore
        _PTY_BACKEND_NAME = "pywinpty"
    except Exception as e:  # pragma: no cover - fallback if not available yet
        _PYWINPTY_IMPORT_ERROR = e
        try:
            import winpty as _PTY_BACKEND  # type: ignore
            _PTY_BACKEND_NAME = "winpty"
        except Exception as e2:
            _WINPTY_IMPORT_ERROR = e2
            _PTY_BACKEND = None  # type: ignore
else:
    import os
    import pty
    import fcntl
    import termios
    import select


class ProcessManager(QObject):
    output = Signal(bytes)
    exited = Signal(int)
    error = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self._proc = None
        self._reader_thread: Optional[threading.Thread] = None
        self._alive = False
        self._write_fn: Optional[Callable[[bytes], None]] = None
        self._resize_fn: Optional[Callable[[int, int], None]] = None

    def start(self, command: str, args: list[str] | None = None) -> bool:
        args = args or []
        try:
            if IS_WINDOWS:
                if _PTY_BACKEND is None or not hasattr(_PTY_BACKEND, "PtyProcess"):
                    # Provide detailed diagnostics and use fallback without PTY.
                    parts = []
                    if '_PYWINPTY_IMPORT_ERROR' in globals() and _PYWINPTY_IMPORT_ERROR is not None:
                        parts.append(f"pywinpty: {repr(_PYWINPTY_IMPORT_ERROR)}")
                    if '_WINPTY_IMPORT_ERROR' in globals() and _WINPTY_IMPORT_ERROR is not None:
                        parts.append(f"winpty: {repr(_WINPTY_IMPORT_ERROR)}")
                    if _PTY_BACKEND is not None and not hasattr(_PTY_BACKEND, "PtyProcess"):
                        parts.append("backend present but missing PtyProcess; using fallback")
                    details = "; ".join(parts) if parts else "unknown import error"
                    try:
                        self._spawn_windows_fallback(command, args)
                    except Exception as ex:
                        self.error.emit(
                            "No usable Windows PTY backend (pywinpty/winpty). "
                            f"Details: {details}. "
                            "Tried fallback using pexpect.popen_spawn.PopenSpawn but it also failed. "
                            f"Fallback error: {ex!r}. "
                            "Troubleshooting: ensure this venv is active and run "
                            "'pip install --force-reinstall --no-cache-dir pywinpty pexpect'. "
                            "Older releases import as 'winpty' but may not expose PtyProcess. "
                            "If you encounter 'DLL load failed', install the Microsoft Visual C++ Redistributable (x64)."
                        )
                        return False
                else:
                    # Create a new PTY and spawn the child process (ConPTY via pywinpty/winpty)
                    self._spawn_windows(command, args)
            else:
                self._spawn_posix(command, args)
            self._alive = True
            # Start reader thread
            self._reader_thread = threading.Thread(target=self._reader_loop, daemon=True)
            self._reader_thread.start()
            return True
        except Exception as e:  # pragma: no cover
            self.error.emit(str(e))
            return False

    def write(self, data: bytes) -> None:
        if self._write_fn:
            try:
                self._write_fn(data)
            except Exception as e:
                self.error.emit(str(e))

    def resize(self, cols: int, rows: int) -> None:
        """Resize the underlying PTY/console window if supported."""
        try:
            if self._resize_fn:
                self._resize_fn(cols, rows)
        except Exception as e:
            self.error.emit(str(e))

    def stop(self) -> None:
        self._alive = False
        # No explicit kill for now; rely on child shell exit via written command.

    # --- platform specifics ---
    def _spawn_windows(self, command: str, args: list[str]) -> None:
        # Using pywinpty (ConPTY) API. PtyProcess provides text-based read/write.
        # Accept either a string or a list of args.
        cmdline = [command] + args
        # spawn accepts a str; join with spaces for simplicity (quotes omitted for MVP)
        self._proc = _PTY_BACKEND.PtyProcess.spawn(" ".join(cmdline))  # type: ignore[attr-defined]

        def _writer(data: bytes) -> None:
            # pywinpty expects text
            self._proc.write(data.decode(errors="ignore"))

        self._write_fn = _writer

        def _resizer(cols: int, rows: int) -> None:
            # pywinpty PtyProcess exposes set_size(rows, cols) in newer versions; try both orders.
            if hasattr(self._proc, "set_size"):
                try:
                    self._proc.set_size(rows, cols)  # type: ignore[attr-defined]
                except TypeError:
                    self._proc.set_size(cols, rows)  # type: ignore[attr-defined]
            elif hasattr(self._proc, "setwinsize"):
                try:
                    self._proc.setwinsize(rows, cols)  # type: ignore[attr-defined]
                except TypeError:
                    self._proc.setwinsize(cols, rows)  # type: ignore[attr-defined]

        self._resize_fn = _resizer

    def _spawn_windows_fallback(self, command: str, args: list[str]) -> None:
        # Fallback: use pexpect's PopenSpawn (no PTY; basic I/O only).
        import pexpect
        cmdline = [command] + args
        self._proc = pexpect.popen_spawn.PopenSpawn(" ".join(cmdline), encoding="utf-8", timeout=0.1)

        def _writer(data: bytes) -> None:
            self._proc.send(data.decode(errors="ignore"))

        self._write_fn = _writer

        def _resizer(cols: int, rows: int) -> None:
            # No-op: cannot resize without PTY on Windows fallback
            pass

        self._resize_fn = _resizer

    def _spawn_posix(self, command: str, args: list[str]) -> None:
        import subprocess
        import os
        import pty

        master_fd, slave_fd = pty.openpty()
        self._master_fd = master_fd
        self._proc = subprocess.Popen(
            [command] + args,
            stdin=slave_fd,
            stdout=slave_fd,
            stderr=slave_fd,
            close_fds=True,
        )

        def _writer(data: bytes) -> None:
            os.write(master_fd, data)

        self._write_fn = _writer

        def _resizer(cols: int, rows: int) -> None:
            import fcntl
            import struct
            import termios
            # TIOCSWINSZ expects rows, cols, xpix, ypix
            size = struct.pack("HHHH", rows, cols, 0, 0)
            fcntl.ioctl(master_fd, termios.TIOCSWINSZ, size)

        self._resize_fn = _resizer

    # --- reader loop ---
    def _reader_loop(self) -> None:
        try:
            if IS_WINDOWS:
                self._reader_loop_windows()
            else:
                self._reader_loop_posix()
        finally:
            self._alive = False

    def _reader_loop_windows(self) -> None:
        # Read in chunks from either pywinpty PtyProcess or pexpect PopenSpawn
        try:
            import pexpect  # type: ignore
        except Exception:
            pexpect = None  # type: ignore

        while self._alive and self._proc is not None:
            try:
                if pexpect is not None and hasattr(self._proc, "read_nonblocking"):
                    # pexpect PopenSpawn path
                    try:
                        data = self._proc.read_nonblocking(4096, timeout=0.1)  # str
                        if data:
                            self.output.emit(data.encode(errors="replace"))
                        continue
                    except Exception as e:
                        # TIMEOUT means no data yet; keep looping
                        if pexpect and isinstance(e, pexpect.exceptions.TIMEOUT):
                            continue
                        # EOF or other errors -> exit loop
                        break
                else:
                    # pywinpty PtyProcess path
                    data = self._proc.read(4096)  # str
                    if not data:
                        break
                    self.output.emit(data.encode(errors="replace"))
            except Exception:
                break
        self.exited.emit(0)

    def _reader_loop_posix(self) -> None:
        import os
        import select

        while self._alive and self._proc and self._proc.poll() is None:
            r, _, _ = select.select([self._master_fd], [], [], 0.1)
            if r:
                try:
                    data = os.read(self._master_fd, 4096)
                    if not data:
                        break
                    self.output.emit(data)
                except Exception:
                    break
        code = self._proc.returncode if self._proc else 0
        self.exited.emit(code if code is not None else 0)
