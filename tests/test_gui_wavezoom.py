"""WaveView right-drag rectangle zoom (offscreen)."""

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PyQt5")
pytest.importorskip("pyqtgraph")

import pyqtgraph as pg
from PyQt5.QtCore import QPointF, Qt
from PyQt5.QtWidgets import QApplication

from nanopore.gui.waveview import WaveView, _drag_rect_ok


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication(sys.argv)
    return app


class _Drag:
    """Minimal MouseDragEvent stand-in for the patched ViewBox handler."""

    def __init__(self, p0, p1, finish=False):
        self._p0, self._p1, self._finish = p0, p1, finish

    def button(self):
        return Qt.RightButton

    def accept(self):
        pass

    def isFinish(self):
        return self._finish

    def buttonDownPos(self, btn=None):
        return self._p0

    def pos(self):
        return self._p1


def test_min_drag_size_guard():
    assert not _drag_rect_ok(QPointF(0, 0), QPointF(3, 50))
    assert not _drag_rect_ok(QPointF(0, 0), QPointF(50, 3))
    assert _drag_rect_ok(QPointF(0, 0), QPointF(10, 10))


def test_right_drag_sets_view_to_rectangle(qapp):
    w = WaveView()
    w.resize(800, 400)
    w.show()
    qapp.processEvents()

    vb = w.plot.getViewBox()
    vb.setRange(xRange=(0.0, 10.0), yRange=(0.0, 100.0), padding=0)
    qapp.processEvents()

    p0 = vb.mapFromView(pg.Point(2.0, 20.0))
    p1 = vb.mapFromView(pg.Point(8.0, 80.0))
    vb.mouseDragEvent(_Drag(p0, p1, finish=False))
    vb.mouseDragEvent(_Drag(p0, p1, finish=True))
    qapp.processEvents()

    (x0, x1), (y0, y1) = vb.viewRange()
    assert x0 == pytest.approx(2.0, abs=0.3)
    assert x1 == pytest.approx(8.0, abs=0.3)
    assert y0 == pytest.approx(20.0, abs=2.0)
    assert y1 == pytest.approx(80.0, abs=2.0)
    assert not w.plot.getPlotItem().menuEnabled()

    w.close()
    w.deleteLater()


def test_tiny_right_drag_does_nothing(qapp):
    w = WaveView()
    w.resize(800, 400)
    w.show()
    qapp.processEvents()

    vb = w.plot.getViewBox()
    vb.setRange(xRange=(0.0, 10.0), yRange=(0.0, 100.0), padding=0)
    qapp.processEvents()
    before = vb.viewRange()

    p0 = vb.mapFromView(pg.Point(2.0, 20.0))
    vb.mouseDragEvent(_Drag(p0, QPointF(p0.x() + 2, p0.y() + 2), finish=True))
    qapp.processEvents()
    assert vb.viewRange() == before

    w.close()
    w.deleteLater()
