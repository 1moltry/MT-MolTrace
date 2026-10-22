"""GUI entry point: ``python -m nanopore.gui [file.abf]``.

No file -> the home workbench (the normal way to start the software).
A file  -> the analysis workspace directly (handy for shortcuts / drag-drop).
"""

from __future__ import annotations

import sys

from PyQt5.QtWidgets import QApplication

from .home import HomeWindow
from .main_window import MainWindow


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv if argv is None else argv)
    app = QApplication(args)
    data = None
    for a in args[1:]:
        if a and not a.startswith("-"):
            data = a
            break
    if data:
        win = MainWindow(data=data)
        win.resize(1500, 950)
        win.show()
    else:
        win = HomeWindow()
        win.show()
    return app.exec_()


if __name__ == "__main__":
    raise SystemExit(main())
