"""Main-window layout: secondary panels hidden by default, 视图 menu toggles."""

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PyQt5")
pytest.importorskip("pyqtgraph")

from PyQt5.QtCore import QSettings
from PyQt5.QtWidgets import QApplication


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication(sys.argv)
    return app


@pytest.fixture()
def win(qapp, monkeypatch):
    from nanopore.gui import parampanel as pp

    monkeypatch.setattr(pp, "_SETTINGS", ("SDL-Nanopore-test-layout", "gui"))
    QSettings("SDL-Nanopore-test-layout", "gui").clear()

    from nanopore.gui.main_window import MainWindow

    w = MainWindow()
    yield w
    w.close()
    w.deleteLater()


def test_secondary_docks_start_hidden(win):
    assert win.dock_excluded.isHidden()
    assert win.dock_scatter.isHidden()
    assert not win.dock_event.isHidden()
    assert not win.dock_params.isHidden()


def test_view_menu_lists_and_toggles_all_docks(win):
    menus = [a.menu() for a in win.menuBar().actions() if a.menu() is not None]
    view = next(m for m in menus if m.title() == "视图")
    assert len(view.actions()) == 4

    act = win.dock_scatter.toggleViewAction()
    assert not act.isChecked()
    act.trigger()
    assert not win.dock_scatter.isHidden()
    assert act.isChecked()
    act.trigger()
    assert win.dock_scatter.isHidden()
