"""
app/log_handler.py – Qt-compatible logging handler.

Formats log records and emits them as a Qt signal so they can be displayed
in the main window's QPlainTextEdit without blocking the UI thread.
"""

import logging

from PyQt6.QtCore import QObject, pyqtSignal


class QtLogHandler(logging.Handler, QObject):
    """Logging handler that emits a Qt signal for each log record."""

    log_emitted = pyqtSignal(str)

    def __init__(self) -> None:
        logging.Handler.__init__(self)
        QObject.__init__(self)
        self.setFormatter(
            logging.Formatter(
                "%(asctime)s [%(levelname)s] %(message)s",
                datefmt="%H:%M:%S",
            )
        )

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
            self.log_emitted.emit(msg)
        except Exception:
            self.handleError(record)
