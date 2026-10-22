"""Home workbench and comparison-metric tests (offscreen)."""

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PyQt5")
pytest.importorskip("pyqtgraph")

from PyQt5.QtWidgets import QApplication


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication(sys.argv)


def test_home_has_all_task_entries(qapp):
    from nanopore.gui.home import HomeWindow

    w = HomeWindow()
    try:
        assert "单文件分析" in w.card_open.text()
        assert "批量处理" in w.card_batch.text()
        assert "算法对比" in w.card_compare.text()
        assert "使用教程" in w.card_tutorial.text()
        assert w.recent.count() >= 1     # empty-state placeholder or real entries
    finally:
        w.close()


def test_compare_metric_matching():
    from nanopore.gui.compare import boundary_metrics

    base = [(0.0, 1.0), (2.0, 3.0)]
    other = [(0.01, 1.01), (2.0, 2.90), (5.0, 6.0)]
    m = boundary_metrics(base, other)
    assert m["matched"] == 2
    assert m["only_other"] == 1
    assert 0.0 <= m["d_boundary_ms"] < 200.0


def test_compare_dialog_instantiates(qapp):
    from nanopore.config import PipelineConfig
    from nanopore.gui.compare import CompareDialog

    dlg = CompareDialog(current_path=None, cfg=PipelineConfig())
    try:
        assert dlg.table.columnCount() == 9
        assert dlg.btn_run.isEnabled()
    finally:
        dlg.close()
