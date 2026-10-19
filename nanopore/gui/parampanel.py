"""Detection/feature parameter panel (the search configuration).

Edits a :class:`PipelineConfig`, saves/loads it as JSON (a reusable analysis
protocol) and triggers a background re-run.

Layout:
- 模块（可多选）: one checkbox per :mod:`nanopore.mods` entry. Empty = base only.
  Enabling a mod auto-checks its prerequisites; the last selection is remembered
  via QSettings.
- 参数: the base pipeline parameters (always shown).
- 模块参数: per-mod parameter groups (低通 / 动态开孔基线 / 细粒度异常), shown
  only while the owning mod is enabled.
"""

from __future__ import annotations

import json
from dataclasses import asdict, fields
from pathlib import Path

from PyQt5.QtCore import QSettings
from PyQt5.QtWidgets import (QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog,
                             QFormLayout, QGroupBox, QHBoxLayout, QLineEdit,
                             QPushButton, QVBoxLayout, QWidget)

from ..config import PipelineConfig
from ..mods import MODS, ORDER, resolve_mods
from .bus import bus

_SETTINGS = ("SDL-Nanopore", "gui")


def _spin(minimum: float, maximum: float, value: float, suffix: str = "",
          step: float = 0.1) -> QDoubleSpinBox:
    s = QDoubleSpinBox()
    s.setRange(minimum, maximum)
    s.setDecimals(3)
    s.setSingleStep(step)
    s.setValue(value)
    s.setSuffix(suffix)
    return s


def _tip(widget, text: str):
    """Attach a hover help text with the parameter's meaning / effect / when to tune."""
    widget.setToolTip(text)
    return widget


class ParamPanel(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        # --- base parameters (always shown) ---
        self.ignore = _spin(0.0, 100.0, 2.0, " ms", 0.5)
        self.pre = _spin(0.0, 500.0, 25.0, " ms", 1.0)
        self.contrib = _spin(0.01, 1.0, 0.10, "", 0.01)
        self.min_toff = _spin(0.0, 100.0, 10.0, " ms", 0.5)
        self.plateau = _spin(0.0, 1.0, 0.0, "", 0.05)
        self.lab = QLineEdit()
        self.l0_en = QCheckBox("手动 Level0")
        self.l0 = _spin(-10000.0, 10000.0, 0.0, " pA", 1.0)
        self.l1_en = QCheckBox("手动 Level1")
        self.l1 = _spin(-10000.0, 10000.0, 0.0, " pA", 1.0)
        self.polarity = QComboBox()
        for label, value in (("自动", None), ("向上", 1), ("向下", -1), ("双向", 0)):
            self.polarity.addItem(label, value)

        # --- mod-owned parameters (grouped, shown per mod) ---
        self.lowpass = _spin(0.0, 20000.0, 0.0, " Hz", 100.0)
        self.dr = _spin(0.0, 100.0, 5.0, " pA", 0.5)
        self.drift_en = QCheckBox("启用慢漂移检测")
        self.drift_en.setChecked(True)
        self.drift_frac = _spin(0.0, 1.0, 0.05, "", 0.01)
        self.drift_iqr = _spin(1.0, 20.0, 3.0, " x", 0.5)

        # --- detection variant: level vs burst (base detector) ---
        self.event_mode = QComboBox()
        self.event_mode.addItem("电平法（现状）", "level")
        self.event_mode.addItem("驻留包络去抖（burst）", "burst")
        self.ignore_event = _spin(0.0, 2000.0, 50.0, " ms", 5.0)
        self.b_enter = _spin(0.0, 2.0, 0.30, "", 0.05)
        self.b_exit = _spin(0.0, 2.0, 0.20, "", 0.05)
        self.b_gap = _spin(0.0, 5000.0, 30.0, " ms", 5.0)
        self.b_block = _spin(0.0, 2000.0, 2.0, " ms", 0.5)
        self.b_cross = QCheckBox("基线上下穿越（多电平）")
        self.b_occ = _spin(0.0, 1.0, 0.30, "", 0.05)
        self.b_depth = _spin(0.0, 2.0, 0.15, "", 0.05)

        # --- mod checkboxes ---
        self.mod_boxes: dict[str, QCheckBox] = {}
        for mid in ORDER:
            spec = MODS[mid]
            cb = QCheckBox(spec.label)
            tip = spec.desc
            if spec.requires:
                tip += "\n依赖：" + "、".join(MODS[d].label for d in spec.requires)
            _tip(cb, tip)
            self.mod_boxes[mid] = cb

        _tip(self.ignore, "尖峰抑制（检测前 · Ignore duration）\n"
                          "离开当前电平短于此值的『短暂偏离』被吸收，不注册为事件（滤毛刺）。\n"
                          "例：设为 2 ms 时，一个 1.5 ms 的阻孔根本不会被检出。\n"
                          "调大：更狠地滤短偏离；调小：保留更短的偏离。\n"
                          "与下面『最短事件时长』不同：那是在事件检出『之后』再剔除。")
        _tip(self.pre, "pre_event（开孔电流参考窗）\n"
                        "事件前取多长一段作为开孔电流参考。\n"
                        "一般不用改；基线漂移明显时可略调。")
        _tip(self.contrib, "Level contribution（电平跟踪权重）\n"
                            "电平流式更新的步长比例。\n"
                            "调大：电平跟随快、对噪声敏感；调小：更稳但滞后。")
        _tip(self.min_toff, "最短事件时长（仅导出 · min toff）\n"
                             "已检出事件中，dwell ≤ 此值的不进保留表，改记入剔除表（reason=toff<min）。\n"
                             "与『尖峰抑制』的区别：尖峰抑制在检测『前』让短偏离根本不成为事件；\n"
                             "这里是在检出『之后』按事件总时长过滤，被剔的仍可追溯。\n"
                             "短肽事件（毫秒级）需调小，如 2 ms。")
        _tip(self.plateau, "事件平台占比下限（毛刺/闪烁门控）\n"
                            "事件体驻留单一电平（最近整数电平 ±0.5 步）的样本占比低于此值\n"
                            "判为毛刺剔除。0=关（默认，不改动任何文件）。\n"
                            "开：TRP 这类密集毛刺文件可设 0.85~0.95；\n"
                            "注意会同时剔除多电平/混合样文件（T3、DQ混合样等）的真事件。")
        _tip(self.lab, "Label：导出表 Label 列的值，留空用文件名。")
        _tip(self.l0_en, "勾选后跳过自动基线估计，用右侧值作 Level0。")
        _tip(self.l1_en, "勾选后跳过自动事件电平估计，用右侧值作 Level1。")
        _tip(self.polarity, "事件极性（搜索方向）\n"
                             "自动：按电平直方图推断（默认，与现状一致）。\n"
                             "双向：允许基线两侧的阻孔，并自动多电平（探测器按 ±8 步\n"
                             "电平网格判定）——ARNKRS 这类『基线上下波动』的肽信号\n"
                             "需要它才能检出深/向上阻孔。\n"
                             "注意：双向对部分文件会过检（噪声侧被当成事件），\n"
                             "建议逐文件确认后再开。")
        _tip(self.lowpass, "低通滤波\n"
                            "0=关。非零时先做零相位低通再检测。\n"
                            "噪声大时可开；会加宽事件前后沿。")
        _tip(self.dr, "Io 漂移容差\n"
                       "逐事件开孔电流 |Io−参考| 超过该值时沿用前一事件 Io。\n"
                       "pA；一般不用改。")
        _tip(self.drift_en, "慢漂移检测\n"
                             "开：自动标记『缓慢、不可逆、且伴随高散布』的开孔电平漂移区间\n"
                             "（如 TRP 尾部基线抬升 + 炸膜），并剔除区间内事件。\n"
                             "稳定的孔态阶跃与可恢复的瞬态不会误报。")
        _tip(self.drift_frac, "漂移位移阈值\n"
                               "块中值偏离记录头锚点 ≥ 此比例 ×|锚点| 才算位移。\n"
                               "调大：更保守（只标明显漂移）；调小：更灵敏。")
        _tip(self.drift_iqr, "漂移不稳定阈值\n"
                              "区间 IQR ÷ 记录头 IQR ≥ 此倍数才算『不稳定』。\n"
                              "与位移阈值同时满足才判漂移（防止把平稳的孔态变化当漂移）。")
        _tip(self.event_mode, "检测模式（底座）\n"
                              "电平法：逐样本最近电平 + 同电平桥接（现状，默认）。\n"
                              "驻留包络去抖：把一次阻孔内的毛刺、越孔、上下跳跃合并为一个事件。\n"
                              "假设开孔电平稳定；Ala/Asp/Gln 这类慢孔态切换请用电平法。\n"
                              "只改变分割方式，默认关，不影响底座。")
        _tip(self.ignore_event, "事件合并容差（仅电平法 · Ignore short level changes）\n"
                                "同电平事件之间、回到开孔的间隙短于此值时合并为一个事件。\n"
                                "调大：长阻孔更不易被噪声槽切碎；调小：更接近逐次开合。")
        _tip(self.b_enter, "阻孔进入阈值（×电平步长）\n"
                           "|电流−开孔| 超过此比例才算进入阻孔。0.30 = 30% 步长。")
        _tip(self.b_exit, "事件电平取样阈值（×步长）\n"
                          "估事件电平时只取超过此比例的样本（< 进入阈值，避开边缘过渡）。")
        _tip(self.b_gap, "毛刺 / 开孔容差（ms）· 主调钮\n"
                         "回到开孔的时长短于它就不切断事件：吸收毛刺、合并上下跳跃。\n"
                         "调大：更不易切碎，但可能把相邻真事件并成一个；调小：反之。")
        _tip(self.b_block, "最短阻孔（ms）\n"
                           "短于此的阻孔碎片丢弃（滤孤立尖峰，不新建事件）。")
        _tip(self.b_cross, "基线上下穿越（多电平）\n"
                           "把开孔电流两侧的偏离都算作同一事件。\n"
                           "用于电流在基线上下来回跳、甚至多电平的信号。默认关。")
        _tip(self.b_occ, "最小占位率\n"
                         "事件体内『确实阻孔』的样本占比低于它时，判为稀疏尖峰链而非事件。\n"
                         "填空隙可能把尖峰之间的开孔也并进来，此门控防止凭空造事件。\n"
                         "调大：更狠地滤尖峰链；调小：保留更稀疏的阻孔。")
        _tip(self.b_depth, "最小体内偏离（×步长）\n"
                           "即使占位率低，只要体内中位电流偏离开孔 ≥ 此比例 × 步长，\n"
                           "仍保留——用于浅但持续的阻孔状态。")

        # ---------------- layout ----------------
        # 模块（可多选）
        modbox = QGroupBox("模块（可多选；不勾=只跑底座）")
        mlay = QVBoxLayout(modbox)
        for mid in ORDER:
            mlay.addWidget(self.mod_boxes[mid])
        btn_all = QPushButton("全选")
        btn_min = QPushButton("仅底座")
        btn_all.clicked.connect(lambda: self._set_mods(ORDER))
        btn_min.clicked.connect(lambda: self._set_mods([]))
        btnrow = QHBoxLayout()
        btnrow.addWidget(btn_all)
        btnrow.addWidget(btn_min)
        mlay.addLayout(btnrow)

        # 参数（底座）
        base = QGroupBox("参数")
        form = QFormLayout(base)
        form.addRow("pre_event", self.pre)
        form.addRow("最短事件时长 (ms)", self.min_toff)
        form.addRow("Label", self.lab)
        form.addRow(self.l0_en, self.l0)
        form.addRow(self.l1_en, self.l1)
        form.addRow("事件极性", self.polarity)
        form.addRow("检测模式", self.event_mode)

        # 电平法专用参数（burst 模式下不参与计算，故随之隐藏）
        self.level_box = QGroupBox("电平法参数")
        lf0 = QFormLayout(self.level_box)
        lf0.addRow("尖峰抑制 (ms)", self.ignore)
        lf0.addRow("事件合并容差 (ms)", self.ignore_event)
        lf0.addRow("Level contribution", self.contrib)
        lf0.addRow("事件平台占比 (0=关)", self.plateau)

        # 模块参数（随模块显隐）
        self.burst_box = QGroupBox("驻留包络去抖（burst）")
        bf = QFormLayout(self.burst_box)
        bf.addRow("进入阈值 (×步长)", self.b_enter)
        bf.addRow("取样阈值 (×步长)", self.b_exit)
        bf.addRow("毛刺 / 开孔容差 (ms)", self.b_gap)
        bf.addRow("最短阻孔 (ms)", self.b_block)
        bf.addRow("最小占位率", self.b_occ)
        bf.addRow("最小体内偏离 (×步长)", self.b_depth)
        bf.addRow("", self.b_cross)

        self.lowpass_box = QGroupBox("低通滤波")
        lf = QFormLayout(self.lowpass_box)
        lf.addRow("截止频率 (0=关)", self.lowpass)

        self.i0_box = QGroupBox("动态开孔基线")
        i0f = QFormLayout(self.i0_box)
        i0f.addRow("Io 漂移容差", self.dr)

        self.refined_box = QGroupBox("异常检测（细粒度）")
        rf = QFormLayout(self.refined_box)
        rf.addRow("", self.drift_en)
        rf.addRow("漂移位移阈值", self.drift_frac)
        rf.addRow("漂移不稳定阈值", self.drift_iqr)

        self.run = QPushButton("重跑检测")
        self.save = QPushButton("存参数")
        self.load = QPushButton("读参数")
        self.run.clicked.connect(self._run)
        self.save.clicked.connect(self._save)
        self.load.clicked.connect(self._load)
        btns = QHBoxLayout()
        btns.addWidget(self.run)
        btns.addWidget(self.save)
        btns.addWidget(self.load)

        lay = QVBoxLayout(self)
        lay.addWidget(modbox)
        lay.addWidget(base)
        lay.addWidget(self.level_box)
        lay.addWidget(self.burst_box)
        lay.addWidget(self.lowpass_box)
        lay.addWidget(self.i0_box)
        lay.addWidget(self.refined_box)
        lay.addLayout(btns)
        lay.addStretch(1)

        # restore last selection, then wire change signals
        self._load_settings()
        for mid, cb in self.mod_boxes.items():
            cb.stateChanged.connect(lambda _state, m=mid: self._on_mod_toggled(m))
        self.event_mode.currentIndexChanged.connect(self._sync_mode)
        self._update_visibility()
        self._sync_mode()

    # ---------------- mod helpers ----------------
    def _checked_raw(self) -> list[str]:
        return [mid for mid in ORDER if self.mod_boxes[mid].isChecked()]

    def enabled_ids(self) -> tuple[str, ...]:
        """Selected mods with prerequisites resolved and ordered."""
        return resolve_mods(self._checked_raw())

    def _set_checked(self, mid: str, value: bool) -> None:
        cb = self.mod_boxes[mid]
        if cb.isChecked() != value:
            cb.blockSignals(True)
            cb.setChecked(value)
            cb.blockSignals(False)

    def _set_mods(self, ids) -> None:
        on = set(resolve_mods(ids))
        for mid in ORDER:
            self._set_checked(mid, mid in on)
        self._update_visibility()
        self._save_settings()

    def _on_mod_toggled(self, mid: str) -> None:
        """Direction-aware coupling: checking a mod pulls its prerequisites in;
        unchecking one drops the mods that depend on it."""
        if self.mod_boxes[mid].isChecked():
            for dep in MODS[mid].requires:
                self._set_checked(dep, True)
        else:
            for other in ORDER:
                if mid in MODS[other].requires:
                    self._set_checked(other, False)
        self._update_visibility()
        self._save_settings()

    def _update_visibility(self) -> None:
        on = set(self._checked_raw())
        self.lowpass_box.setVisible("lowpass" in on)
        self.i0_box.setVisible("dynamic_i0" in on)
        self.refined_box.setVisible("refined_anomaly" in on)

    def _sync_mode(self) -> None:
        burst = self.event_mode.currentData() == "burst"
        self.burst_box.setVisible(burst)
        self.level_box.setVisible(not burst)
        self._save_settings()

    def _load_settings(self) -> None:
        s = QSettings(*_SETTINGS)
        last = s.value("last_config", None)
        if last:
            try:
                data = json.loads(str(last))
                valid = {f.name for f in fields(PipelineConfig)}
                self.load_config(PipelineConfig(**{k: v for k, v in data.items() if k in valid}))
                return
            except Exception:                    # noqa: BLE001 — corrupt settings: use defaults
                pass
        saved = s.value("enabled_mods", None)
        if saved is None:
            ids = [mid for mid in ORDER if MODS[mid].default_on]
        else:
            ids = [x for x in str(saved).split(",") if x]
        idset = set(resolve_mods(ids))
        for mid in ORDER:
            self.mod_boxes[mid].setChecked(mid in idset)

    def _save_settings(self) -> None:
        s = QSettings(*_SETTINGS)
        s.setValue("enabled_mods", ",".join(self._checked_raw()))
        try:
            # remember the full protocol (detection mode + every parameter),
            # not just the module checkboxes — otherwise the mode silently
            # reverts to "level" on restart and the results change underfoot.
            s.setValue("last_config", json.dumps(asdict(self.build_config()), ensure_ascii=False))
        except Exception:                        # noqa: BLE001
            pass

    # ---------------- config round-trip ----------------
    def build_config(self) -> PipelineConfig:
        return PipelineConfig(
            enabled_mods=self.enabled_ids(),
            filter_lowpass_hz=self.lowpass.value() or None,
            level0=self.l0.value() if self.l0_en.isChecked() else None,
            level1=self.l1.value() if self.l1_en.isChecked() else None,
            polarity=self.polarity.currentData(),
            ignore_duration_ms=self.ignore.value(),
            ignore_event_duration_ms=self.ignore_event.value(),
            event_mode=self.event_mode.currentData(),
            burst_enter_frac=self.b_enter.value(),
            burst_exit_frac=self.b_exit.value(),
            burst_min_gap_ms=self.b_gap.value(),
            burst_min_block_ms=self.b_block.value(),
            burst_min_occupied_frac=self.b_occ.value(),
            burst_min_depth_frac=self.b_depth.value(),
            burst_cross_baseline=self.b_cross.isChecked(),
            level_contribution=self.contrib.value(),
            min_toff_ms=self.min_toff.value(),
            event_plateau_min_frac=self.plateau.value(),
            refined_drift_enabled=self.drift_en.isChecked(),
            refined_drift_min_frac=self.drift_frac.value(),
            refined_drift_iqr_ratio=self.drift_iqr.value(),
            pre_event_ms=self.pre.value(),
            dr_pA=self.dr.value(),
            label=self.lab.text(),
        )

    def load_config(self, cfg: PipelineConfig) -> None:
        self.ignore.setValue(cfg.ignore_duration_ms)
        self.ignore_event.setValue(cfg.ignore_event_duration_ms)
        self.b_enter.setValue(cfg.burst_enter_frac)
        self.b_exit.setValue(cfg.burst_exit_frac)
        self.b_gap.setValue(cfg.burst_min_gap_ms)
        self.b_block.setValue(cfg.burst_min_block_ms)
        self.b_occ.setValue(cfg.burst_min_occupied_frac)
        self.b_depth.setValue(cfg.burst_min_depth_frac)
        self.b_cross.setChecked(cfg.burst_cross_baseline)
        idx = self.event_mode.findData(cfg.event_mode)
        self.event_mode.setCurrentIndex(idx if idx >= 0 else 0)
        self._sync_mode()
        self.pre.setValue(cfg.pre_event_ms)
        self.contrib.setValue(cfg.level_contribution)
        self.lowpass.setValue(cfg.filter_lowpass_hz or 0.0)
        self.min_toff.setValue(cfg.min_toff_ms)
        self.plateau.setValue(cfg.event_plateau_min_frac)
        self.dr.setValue(cfg.dr_pA)
        self.drift_en.setChecked(cfg.refined_drift_enabled)
        self.drift_frac.setValue(cfg.refined_drift_min_frac)
        self.drift_iqr.setValue(cfg.refined_drift_iqr_ratio)
        self.lab.setText(cfg.label)
        self.l0_en.setChecked(cfg.level0 is not None)
        self.l1_en.setChecked(cfg.level1 is not None)
        if cfg.level0 is not None:
            self.l0.setValue(cfg.level0)
        if cfg.level1 is not None:
            self.l1.setValue(cfg.level1)
        idx = self.polarity.findData(cfg.polarity)
        self.polarity.setCurrentIndex(idx if idx >= 0 else 0)
        self._set_mods(cfg.enabled_mods)

    # ---------------- actions ----------------
    def _run(self) -> None:
        from .controller import controller

        if controller.rec is None:
            bus.status.emit("请先打开一个 .abf 文件")
            return
        self._save_settings()
        controller.set_config(self.build_config())
        controller.rerun()

    def _save(self) -> None:
        from .controller import controller

        path, _ = QFileDialog.getSaveFileName(self, "保存参数", "params.json", "JSON (*.json)")
        if path:
            controller.set_config(self.build_config())
            controller.cfg.save(path)
            bus.status.emit(f"参数已保存: {path}")

    def _load(self) -> None:
        from .controller import controller

        path, _ = QFileDialog.getOpenFileName(self, "读取参数", "", "JSON (*.json)")
        if path:
            cfg = PipelineConfig.load(Path(path))
            controller.set_config(cfg)
            self.load_config(cfg)
            bus.status.emit(f"参数已读取: {path}")
