"""Home / workbench window: the software's single entry point.

Launching the app without a file shows this window. Every workflow starts here
(open a file, batch process, compare algorithms, read the tutorial), so a user
never needs a command line.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PyQt5.QtCore import Qt, QUrl
from PyQt5.QtGui import QDesktopServices, QFont
from PyQt5.QtWidgets import (QFileDialog, QGridLayout, QHBoxLayout, QLabel,
                             QListWidget, QListWidgetItem, QMainWindow,
                             QPushButton, QVBoxLayout, QWidget)

from .. import __version__
from . import history


_CARD_STYLE = """
QPushButton#taskCard {
    text-align: left;
    padding: 18px 20px;
    border: 1px solid #d0d7de;
    border-radius: 10px;
    background: #fbfcfe;
    font-size: 14px;
}
QPushButton#taskCard:hover {
    border: 1px solid #3b82f6;
    background: #f0f7ff;
}
"""


class HomeWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("MOLTRACE · 摩尔迹")
        self.resize(1000, 720)
        self._windows: list[QMainWindow] = []

        root = QWidget()
        lay = QVBoxLayout(root)
        lay.setContentsMargins(42, 32, 42, 24)
        lay.setSpacing(14)

        title = QLabel("MOLTRACE · 摩尔迹")
        f = QFont()
        f.setPointSize(22)
        f.setBold(True)
        title.setFont(f)
        lay.addWidget(title)

        sub = QLabel("单分子纳米孔电流迹分析工作台。打开一个 .abf，选择检测算法，检查事件并导出。")
        sub.setStyleSheet("color:#57606a;")
        lay.addWidget(sub)
        lay.addSpacing(8)

        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(14)
        self.card_open = self._card(
            "单文件分析",
            "打开一个 .abf，查看波形与事件，选择检测算法、调整参数。",
            self._pick_file)
        self.card_batch = self._card(
            "批量处理",
            "选择一个或多个文件 / 文件夹，用同一套参数处理并导出。",
            self._batch)
        self.card_compare = self._card(
            "算法对比",
            "同一个文件并排比较电平法、burst、平台滞回的事件与边界。",
            self._compare)
        self.card_tutorial = self._card(
            "使用教程",
            "界面说明、参数解释、输出文件与常见问题。",
            self._tutorial)
        grid.addWidget(self.card_open, 0, 0)
        grid.addWidget(self.card_batch, 0, 1)
        grid.addWidget(self.card_compare, 1, 0)
        grid.addWidget(self.card_tutorial, 1, 1)
        lay.addLayout(grid)

        lay.addSpacing(10)
        recent_title = QLabel("最近打开")
        recent_title.setStyleSheet("font-weight:600; margin-top:4px;")
        lay.addWidget(recent_title)
        self.recent = QListWidget()
        self.recent.setMaximumHeight(150)
        self.recent.itemDoubleClicked.connect(self._open_recent)
        lay.addWidget(self.recent)
        self._refresh_recent()

        foot = QHBoxLayout()
        foot.addWidget(QLabel(f"MOLTRACE {__version__} · 从一摩尔到单分子 · 1moltry"))
        foot.addStretch(1)
        btn_clear = QPushButton("清空最近记录")
        btn_clear.clicked.connect(self._clear_recent)
        foot.addWidget(btn_clear)
        lay.addLayout(foot)

        self.setCentralWidget(root)
        self.setStyleSheet(_CARD_STYLE)

    # ---- cards -----------------------------------------------------------
    def _card(self, title: str, desc: str, slot) -> QPushButton:
        b = QPushButton(f"{title}\n{desc}")
        b.setObjectName("taskCard")
        b.setMinimumHeight(118)
        b.setCursor(Qt.PointingHandCursor)
        b.clicked.connect(slot)
        return b

    # ---- actions ---------------------------------------------------------
    def _pick_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "打开 .abf", "", "ABF (*.abf)")
        if path:
            self._open_path(path)

    def _open_path(self, path: str, detector: str | None = None) -> None:
        from .main_window import MainWindow

        win = MainWindow(data=path, detector=detector)
        win.return_to_home_on_close = True
        win.home_requested.connect(lambda _=None, w=win: self._return_home(w))
        win.show()
        self._windows.append(win)
        self.hide()

    def _return_home(self, win: QMainWindow) -> None:
        win.close()
        if win in self._windows:
            self._windows.remove(win)
        self._refresh_recent()
        self.show()
        self.raise_()

    def _batch(self) -> None:
        from .batchdialog import BatchDialog
        from .parampanel import load_saved_config

        dlg = BatchDialog(load_saved_config(), self)
        dlg.exec_()

    def _compare(self) -> None:
        from .compare import CompareDialog
        from .parampanel import load_saved_config

        dlg = CompareDialog(current_path=None, cfg=load_saved_config(), parent=self)
        dlg.open_requested.connect(self._open_path)
        dlg.exec_()

    def _tutorial(self) -> None:
        for candidate in (
            Path(getattr(sys, "_MEIPASS", "")) / "tutorial.md",
            Path(sys.executable).parent / "tutorial.md",
            Path(__file__).resolve().parents[2] / "tutorial.md",
            Path(__file__).resolve().parents[2] / "README.md",
        ):
            if candidate.is_file():
                QDesktopServices.openUrl(QUrl.fromLocalFile(str(candidate)))
                return
        from PyQt5.QtWidgets import QMessageBox

        QMessageBox.information(self, "使用教程", "未找到 tutorial.md；请查看 README。")

    # ---- recent ----------------------------------------------------------
    def _refresh_recent(self) -> None:
        self.recent.clear()
        for p in history.recent_files():
            item = QListWidgetItem(Path(p).name)
            item.setToolTip(p)
            item.setData(Qt.UserRole, p)
            self.recent.addItem(item)
        if self.recent.count() == 0:
            item = QListWidgetItem("（还没有打开过文件）")
            item.setFlags(Qt.NoItemFlags)
            self.recent.addItem(item)

    def _open_recent(self, item: QListWidgetItem) -> None:
        path = item.data(Qt.UserRole)
        if path:
            self._open_path(str(path))

    def _clear_recent(self) -> None:
        history.clear_recent()
        self._refresh_recent()
