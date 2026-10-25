"""Detection/feature parameter panel (the search configuration).

Edits a :class:`PipelineConfig`, saves/loads it as JSON (a reusable analysis
protocol) and triggers a background re-run.

Layout:
- 模块（可多选）: one checkbox per :mod:`nanopore.mods` entry, grouped into
  functional tabs from :data:`nanopore.mods.CATEGORIES`. Empty = base only.
  Enabling a mod auto-checks its prerequisites; the last selection is remembered
  via QSettings.
- 参数: the base pipeline parameters (always shown).
- 模块参数: per-mod parameter groups (低通 / 动态开孔基线 / 细粒度异常), shown
  only while the owning mod is enabled.
"""

from __future__ import annotations

import json
from dataclasses import asdict, replace
from pathlib import Path

from PyQt5.QtCore import QSettings, pyqtSignal
from PyQt5.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox,
                             QDoubleSpinBox, QFileDialog, QFormLayout,
                             QGroupBox, QHBoxLayout, QLineEdit, QPushButton,
                             QScrollArea, QTabWidget, QVBoxLayout, QWidget)

from ..config import PipelineConfig
from ..mods import CATEGORIES, MODS, ORDER, resolve_mods
from ..registry import list_detectors, normalize_config
from .bus import bus

# Legacy QSettings scope kept after the product rename: existing users keep
# their saved protocol and module selection.
_SETTINGS = ("SDL-Nanopore", "gui")


def load_saved_config() -> PipelineConfig:
    """Read the last protocol from QSettings (used by Home / batch / compare)."""
    raw = QSettings(*_SETTINGS).value("last_config", None)
    if raw:
        try:
            return PipelineConfig.from_dict(json.loads(str(raw)))
        except Exception:                    # noqa: BLE001 — corrupt settings: defaults
            pass
    return PipelineConfig()


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
    changed = pyqtSignal()      # any option edit → main window schedules a rerun
    mod_changed = pyqtSignal(str, bool)   # a module checkbox changed (toolbar sync)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        # The last loaded protocol is the base for every build_config() call.
        # UI-owned fields override it; unexposed fields are preserved verbatim.
        self._base_cfg = PipelineConfig()
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

        # --- event detector selector, generated from the shared registry ---
        self.event_mode = QComboBox()
        for spec in list_detectors():
            self.event_mode.addItem(spec.label, spec.id)
        self.ignore_event = _spin(0.0, 2000.0, 50.0, " ms", 5.0)
        self.b_enter = _spin(0.0, 2.0, 0.30, "", 0.05)
        self.b_exit = _spin(0.0, 2.0, 0.20, "", 0.05)
        self.b_gap = _spin(0.0, 5000.0, 30.0, " ms", 5.0)
        self.b_open = _spin(0.0, 1.0, 0.75, "", 0.05)
        self.b_merge = _spin(0.0, 5000.0, 200.0, " ms", 10.0)
        self.b_block = _spin(0.0, 2000.0, 2.0, " ms", 0.5)
        self.b_cross = QCheckBox("基线上下穿越（多电平）")
        self.b_occ = _spin(0.0, 1.0, 0.30, "", 0.05)
        self.b_depth = _spin(0.0, 2.0, 0.15, "", 0.05)

        # --- plateau detector parameters (sugar / long-blockade signals) ---
        self.p_enter = _spin(0.0, 5000.0, 60.0, " pA", 5.0)
        self.p_exit = _spin(0.0, 5000.0, 15.0, " pA", 1.0)
        self.p_open = _spin(0.0, 5000.0, 1.0, " ms", 0.5)
        self.p_dir = QComboBox()
        for label, value in (("自动（按极性）", "auto"), ("向下", "down"),
                             ("向上", "up"), ("双向", "both")):
            self.p_dir.addItem(label, value)
        self.p_volt = QCheckBox("屏蔽电压协议段")
        self.p_volt.setChecked(True)
        self.p_pulse = QCheckBox("剔除脉冲清除事件")
        self.p_pulse.setChecked(True)
        self.p_rupt = QCheckBox("剔除炸膜/孔塌陷")
        self.p_rupt.setChecked(True)
        self.p_abs = _spin(0.0, 1e6, 1000.0, " pA", 100.0)
        self.p_diff = _spin(0.0, 1e6, 500.0, " pA", 100.0)

        # --- event description / fingerprint (mod "describe") ---
        self.describer = QComboBox()
        self.describer.addItem("DP+BIC 台阶", "dp_bic")
        self.describer.addItem("标量特征", "scalar")
        self.fp_kmax = _spin(1, 200, 30, "", 1)
        self.fp_tau = _spin(10, 5000, 250, " µs", 10)
        self.fp_amp = _spin(0, 500, 10, " pA", 1)
        self.fp_snr = _spin(0, 50, 0.0, "", 0.5)

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
        _tip(self.event_mode, "事件检测算法（底座）\n"
                              "电平法：逐样本最近电平 + 同电平桥接（Clampfit 语义，默认）。\n"
                              "驻留包络去抖：把一次阻孔内的毛刺、越孔、上下跳跃合并为一个事件。\n"
                              "平台滞回：进入深阈值、退出浅阈值，短开孔合并；边界贴近开孔，\n"
                              "事件内的部分恢复不会把事件切断（糖/长阻孔信号适用）。\n"
                              "只改变事件分割方式，后处理与特征表相同。")
        _tip(self.p_enter, "进入阻孔深度（pA）\n"
                           "阻孔段必须至少达到这个深度，才被认定为事件；\n"
                           "它只做验证，不决定事件边界。")
        _tip(self.p_exit, "退出阻孔阈值（pA）\n"
                          "事件边界定在电流回到开孔电平这个距离以内；\n"
                          "越小越贴近开孔，事件内部分恢复越不容易被切断。")
        _tip(self.p_open, "短开孔合并（ms）\n"
                          "两次阻孔之间回到开孔的时间短于此值 → 合并为同一个事件。")
        _tip(self.p_dir, "阻孔方向\n"
                         "自动：按电平直方图推断的极性决定；\n"
                         "双向：基线两侧的阻孔都算，适合基线上下波动的肽信号。")
        _tip(self.p_volt, "屏蔽电压协议段\n"
                          "命令电压偏离主体的区段（换向/清洗脉冲）不参与事件检测。")
        _tip(self.p_pulse, "剔除脉冲清除事件\n"
                           "终止于换向电压脉冲的阻孔被视为被电压清除，不计入分析物事件。")
        _tip(self.p_rupt, "剔除炸膜/孔塌陷\n"
                          "电流塌到接近 0 并持续的伪事件（膜破裂）不计入事件。")
        _tip(self.p_abs, "电流伪迹屏蔽（绝对值）\n"
                         "|I| 超过此值的采样被屏蔽（0=关）。用于剔除切换尖峰。")
        _tip(self.p_diff, "电流伪迹屏蔽（跳变）\n"
                          "相邻采样跳变超过此值的采样被屏蔽（0=关）。")
        _tip(self.ignore_event, "事件合并容差（仅电平法 · Ignore short level changes）\n"
                                "同电平事件之间、回到开孔的间隙短于此值时合并为一个事件。\n"
                                "调大：长阻孔更不易被噪声槽切碎；调小：更接近逐次开合。")
        _tip(self.b_enter, "阻孔判定阈值（× 步长）\n"
                           "电流偏离开孔电平超过这个值，才算进入阻孔；\n"
                           "事件的起点和终点也按它切。\n"
                           "步长 = |Level1 − Level0|，随文件自动估计。\n"
                           "例：步长 80 pA、比例 0.30 → 偏离超过 24 pA 才算阻孔。\n"
                           "调大：只认更深的阻孔；调小：更浅的偏离也算。")
        _tip(self.b_exit, "事件幅值取样下限（× 步长）\n"
                          "计算事件幅值时，只取偏离开孔电平超过这个值的样本，\n"
                          "避开上升/下降沿的过渡段。\n"
                          "它不剔除事件，也不改变事件起止；一般保持小于判定阈值。\n"
                          "例：步长 80 pA、比例 0.20 → 只用偏离超过 16 pA 的样本。")
        _tip(self.b_gap, "开孔回落容差（ms）· 主调钮\n"
                         "两次阻孔之间，回落时长小于它 → 仍算同一个事件。\n"
                         "配合『开孔判定比例』：时长和开孔时间占比都满足，才切断事件。\n"
                         "注意：这里量的是阈值域时长，不是肉眼看到回到基线的时长。\n"
                         "调大：更不易切碎，但可能并掉相邻真事件；调小：更接近逐次开合。")
        _tip(self.b_open, "开孔判定比例\n"
                          "间隙里至少这么大比例的时间落在『阻孔判定阈值』范围内，\n"
                          "才算真的回到开孔、允许切断事件。\n"
                          "判定带与阻孔判定阈值共用同一个 ×步长 比例，不另设电流比例。\n"
                          "例：0.75 = 间隙中 ≥75% 的时间必须在 ±判定阈值 内；\n"
                          "低于它（短暂 flicker、残余电平）就并入同一事件。\n"
                          "调大：更多浅回落被合并；调小：更容易切开。")
        _tip(self.b_merge, "最长合并间隙（ms）\n"
                           "没真正回到开孔时，只合并不超过这个时长的间隙；\n"
                           "更长的浅态保留为独立事件。\n"
                           "避免把 10 s 级的另一孔态吞进同一事件。0 = 不合并。")
        _tip(self.b_block, "最短阻孔时长（ms）\n"
                           "短于它的阻孔碎片先被丢弃：既不新建事件，\n"
                           "也不会用来桥接相邻事件。\n"
                           "用于滤孤立尖峰；不影响长阻孔。")
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
        # 模块（可多选，按功能分标签页）
        self.modbox = QGroupBox(self._module_title(0))
        mlay = QVBoxLayout(self.modbox)
        self.mod_tabs = QTabWidget()
        for cid, label in CATEGORIES:
            page = QWidget()
            pl = QVBoxLayout(page)
            pl.setContentsMargins(6, 6, 6, 6)
            for mid in ORDER:
                if MODS[mid].category == cid:
                    pl.addWidget(self.mod_boxes[mid])
            pl.addStretch(1)
            self.mod_tabs.addTab(page, label)
        mlay.addWidget(self.mod_tabs)
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
        # 检测算法选择器由 MainWindow 移到顶部工作栏，避免埋在参数表里。

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
        bf.addRow("阻孔判定阈值 (×步长)", self.b_enter)
        bf.addRow("事件幅值取样下限 (×步长)", self.b_exit)
        bf.addRow("开孔回落容差 (ms)", self.b_gap)
        bf.addRow("开孔判定比例", self.b_open)
        bf.addRow("最长合并间隙 (ms)", self.b_merge)
        bf.addRow("最短阻孔时长 (ms)", self.b_block)
        bf.addRow("最小占位率", self.b_occ)
        bf.addRow("最小体内偏离 (×步长)", self.b_depth)
        bf.addRow("", self.b_cross)

        self.plateau_box = QGroupBox("平台滞回（sweep/plateau）")
        pf = QFormLayout(self.plateau_box)
        pf.addRow("进入阻孔深度 (pA)", self.p_enter)
        pf.addRow("退出阻孔阈值 (pA)", self.p_exit)
        pf.addRow("短开孔合并 (ms)", self.p_open)
        pf.addRow("阻孔方向", self.p_dir)
        pf.addRow("", self.p_volt)
        pf.addRow("", self.p_pulse)
        pf.addRow("", self.p_rupt)
        pf.addRow("伪迹屏蔽 |I| (pA)", self.p_abs)
        pf.addRow("伪迹屏蔽 |ΔI| (pA)", self.p_diff)

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

        self.fp_box = QGroupBox("事件指纹（描述器参数）")
        ff = QFormLayout(self.fp_box)
        ff.addRow("描述器", self.describer)
        ff.addRow("最大段数", self.fp_kmax)
        ff.addRow("最小驻留 (µs)", self.fp_tau)
        ff.addRow("最小跃变 (pA)", self.fp_amp)
        ff.addRow("最小显著度 (0=关)", self.fp_snr)
        _tip(self.describer,
             "事件内描述器\n"
             "DP+BIC 台阶：把事件体切成若干恒定电平段，输出段电平、宽度与跃变。\n"
             "标量特征：整事件一组统计量，不切段，作为对照基线。")
        _tip(self.fp_kmax, "最大段数\nDP 搜索的段数上限。越大越能描述复杂形状，也越慢。")
        _tip(self.fp_tau, "最小驻留 (µs)\n短于此值的段会并入相邻段，避免把噪声当指纹。")
        _tip(self.fp_amp, "最小跃变 (pA)\n相邻段电平差小于此值就合并。")
        _tip(self.fp_snr, "最小显著度 (0=关)\n"
                          "(|跃变|/σ)·√(驻留·采样率) 下限；低于阈值的段并入相邻段。\n"
                          "源实现未启用此门控，默认 0 以保持结果一致。")

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
        lay.addWidget(self.modbox)
        lay.addWidget(base)
        lay.addWidget(self.level_box)
        lay.addWidget(self.burst_box)
        lay.addWidget(self.plateau_box)
        lay.addWidget(self.lowpass_box)
        lay.addWidget(self.i0_box)
        lay.addWidget(self.refined_box)
        lay.addWidget(self.fp_box)
        lay.addLayout(btns)
        lay.addStretch(1)

        # restore last selection, then wire change signals
        self._load_settings()
        for mid, cb in self.mod_boxes.items():
            cb.stateChanged.connect(lambda _state, m=mid: self._on_mod_toggled(m))
        self.event_mode.currentIndexChanged.connect(self._sync_mode)
        self._update_visibility()
        self._sync_mode()

        # any option edit asks the main window for a debounced auto-rerun
        for w in (self.ignore, self.ignore_event, self.contrib, self.plateau,
                  self.pre, self.min_toff, self.lowpass, self.dr,
                  self.b_enter, self.b_exit, self.b_gap, self.b_open,
                  self.b_merge, self.b_block,
                  self.b_occ, self.b_depth, self.drift_frac, self.drift_iqr,
                  self.p_enter, self.p_exit, self.p_open, self.p_abs, self.p_diff,
                  self.fp_kmax, self.fp_tau, self.fp_amp, self.fp_snr,
                  self.l0, self.l1):
            w.valueChanged.connect(self._emit_changed)
        for w in (self.l0_en, self.l1_en, self.drift_en, self.b_cross,
                  self.p_volt, self.p_pulse, self.p_rupt):
            w.stateChanged.connect(self._emit_changed)
        for w in (self.polarity, self.event_mode, self.p_dir, self.describer):
            w.currentIndexChanged.connect(self._emit_changed)
        self.describer.currentIndexChanged.connect(self._sync_describer)
        self.lab.textChanged.connect(self._emit_changed)
        for cb in self.mod_boxes.values():
            cb.stateChanged.connect(self._emit_changed)

    def _emit_changed(self, *args) -> None:
        self.changed.emit()

    # ---------------- detector selection ----------------
    def current_detector(self) -> str:
        return str(self.event_mode.currentData())

    def set_detector(self, detector: str) -> None:
        """Select level / burst / plateau from outside (top workflow bar)."""
        idx = self.event_mode.findData(detector)
        if idx < 0:
            return
        if idx != self.event_mode.currentIndex():
            self.event_mode.setCurrentIndex(idx)
        self._sync_mode()

    # ---------------- mod helpers ----------------
    @staticmethod
    def _module_title(n: int) -> str:
        return f"模块（已选 {n} 个；不勾=只跑底座）"

    def _update_module_summary(self) -> None:
        self.modbox.setTitle(self._module_title(len(self._checked_raw())))

    def _checked_raw(self) -> list[str]:
        return [mid for mid in ORDER if self.mod_boxes[mid].isChecked()]

    def enabled_ids(self) -> tuple[str, ...]:
        """Selected mods with prerequisites resolved and ordered."""
        return resolve_mods(self._checked_raw())

    def set_mod_enabled(self, mid: str, enabled: bool) -> None:
        """Toolbar shortcut: flip a module checkbox (signals fire as usual)."""
        cb = self.mod_boxes[mid]
        if cb.isChecked() != enabled:
            cb.setChecked(enabled)

    def _set_checked(self, mid: str, value: bool) -> None:
        cb = self.mod_boxes[mid]
        if cb.isChecked() != value:
            cb.blockSignals(True)
            cb.setChecked(value)
            cb.blockSignals(False)

    def _set_mods(self, ids, *, notify: bool = True) -> None:
        on = set(resolve_mods(ids))
        before = {mid: cb.isChecked() for mid, cb in self.mod_boxes.items()}
        for mid in ORDER:
            self._set_checked(mid, mid in on)
        self._update_visibility()
        for mid in ORDER:
            enabled = self.mod_boxes[mid].isChecked()
            if before[mid] != enabled:
                self.mod_changed.emit(mid, enabled)
        if notify:
            self.changed.emit()
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
        self.mod_changed.emit(mid, self.mod_boxes[mid].isChecked())

    def _update_visibility(self) -> None:
        on = set(self._checked_raw())
        self.lowpass_box.setVisible("lowpass" in on)
        self.i0_box.setVisible("dynamic_i0" in on)
        self.refined_box.setVisible("refined_anomaly" in on)
        self.fp_box.setVisible("describe" in on)
        self._update_module_summary()

    def _sync_describer(self) -> None:
        dp = self.describer.currentData() == "dp_bic"
        for w in (self.fp_kmax, self.fp_tau, self.fp_amp, self.fp_snr):
            w.setEnabled(dp)

    def _sync_mode(self) -> None:
        mode = self.event_mode.currentData()
        self.burst_box.setVisible(mode == "burst")
        self.plateau_box.setVisible(mode == "plateau")
        self.level_box.setVisible(mode == "level")
        self._save_settings()

    def _load_settings(self) -> None:
        s = QSettings(*_SETTINGS)
        last = s.value("last_config", None)
        if last:
            try:
                self.load_config(PipelineConfig.from_dict(json.loads(str(last))))
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
        detector = self.event_mode.currentData()
        params = dict(self._base_cfg.describe_params or {})
        params.update({
            "k_max": int(self.fp_kmax.value()),
            "tau_min_us": float(self.fp_tau.value()),
            "amp_min_pA": float(self.fp_amp.value()),
            "snr_min": float(self.fp_snr.value()),
        })
        # Start from the loaded protocol so fields without a widget survive.
        # Only fields actually exposed here are overwritten.
        cfg = replace(
            self._base_cfg,
            enabled_mods=self.enabled_ids(),
            filter_lowpass_hz=self.lowpass.value() or None,
            level0=self.l0.value() if self.l0_en.isChecked() else None,
            level1=self.l1.value() if self.l1_en.isChecked() else None,
            polarity=self.polarity.currentData(),
            detector=detector,
            ignore_duration_ms=self.ignore.value(),
            ignore_event_duration_ms=self.ignore_event.value(),
            burst_enter_frac=self.b_enter.value(),
            burst_exit_frac=self.b_exit.value(),
            burst_min_gap_ms=self.b_gap.value(),
            burst_min_block_ms=self.b_block.value(),
            burst_open_cover=self.b_open.value(),
            burst_merge_max_ms=self.b_merge.value(),
            burst_min_occupied_frac=self.b_occ.value(),
            burst_min_depth_frac=self.b_depth.value(),
            burst_cross_baseline=self.b_cross.isChecked(),
            plateau_direction=self.p_dir.currentData(),
            plateau_enter_depth_pA=self.p_enter.value(),
            plateau_exit_depth_pA=self.p_exit.value(),
            plateau_min_open_ms=self.p_open.value(),
            plateau_exclude_voltage=self.p_volt.isChecked(),
            plateau_exclude_pulse_cleared=self.p_pulse.isChecked(),
            plateau_exclude_rupture=self.p_rupt.isChecked(),
            plateau_artifact_abs_pA=self.p_abs.value(),
            plateau_artifact_diff_pA=self.p_diff.value(),
            level_contribution=self.contrib.value(),
            min_toff_ms=self.min_toff.value(),
            event_plateau_min_frac=self.plateau.value(),
            refined_drift_enabled=self.drift_en.isChecked(),
            refined_drift_min_frac=self.drift_frac.value(),
            refined_drift_iqr_ratio=self.drift_iqr.value(),
            pre_event_ms=self.pre.value(),
            dr_pA=self.dr.value(),
            label=self.lab.text(),
            describer=str(self.describer.currentData()),
            describe_params=params,
        )
        cfg = normalize_config(cfg)
        self._base_cfg = cfg
        return cfg

    def load_config(self, cfg: PipelineConfig) -> None:
        cfg = normalize_config(cfg)
        self._base_cfg = cfg
        self.ignore.setValue(cfg.ignore_duration_ms)
        self.ignore_event.setValue(cfg.ignore_event_duration_ms)
        self.b_enter.setValue(cfg.burst_enter_frac)
        self.b_exit.setValue(cfg.burst_exit_frac)
        self.b_gap.setValue(cfg.burst_min_gap_ms)
        self.b_open.setValue(cfg.burst_open_cover)
        self.b_merge.setValue(cfg.burst_merge_max_ms)
        self.b_block.setValue(cfg.burst_min_block_ms)
        self.b_occ.setValue(cfg.burst_min_occupied_frac)
        self.b_depth.setValue(cfg.burst_min_depth_frac)
        self.b_cross.setChecked(cfg.burst_cross_baseline)
        self.p_enter.setValue(cfg.plateau_enter_depth_pA)
        self.p_exit.setValue(cfg.plateau_exit_depth_pA)
        self.p_open.setValue(cfg.plateau_min_open_ms)
        self.p_volt.setChecked(cfg.plateau_exclude_voltage)
        self.p_pulse.setChecked(cfg.plateau_exclude_pulse_cleared)
        self.p_rupt.setChecked(cfg.plateau_exclude_rupture)
        self.p_abs.setValue(cfg.plateau_artifact_abs_pA)
        self.p_diff.setValue(cfg.plateau_artifact_diff_pA)
        idx = self.p_dir.findData(cfg.plateau_direction)
        self.p_dir.setCurrentIndex(idx if idx >= 0 else 0)
        detector = cfg.detector or cfg.event_mode
        idx = self.event_mode.findData(detector)
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
        idx = self.describer.findData(cfg.describer)
        self.describer.setCurrentIndex(idx if idx >= 0 else 0)
        params = cfg.describe_params or {}
        self.fp_kmax.setValue(int(params.get("k_max", 30)))
        self.fp_tau.setValue(float(params.get("tau_min_us", 250.0)))
        self.fp_amp.setValue(float(params.get("amp_min_pA", 10.0)))
        self.fp_snr.setValue(float(params.get("snr_min", 0.0)))
        self._sync_describer()
        self._set_mods(cfg.enabled_mods, notify=False)

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


class ParamDialog(QDialog):
    """Modal parameter editor used by the batch and comparison dialogs.

    Keeps those entry points self-contained: a user who starts from the home
    workbench can edit detection parameters without first opening a file.
    """

    def __init__(self, cfg: PipelineConfig, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("检测参数")
        self.resize(460, 760)
        self.panel = ParamPanel()
        self.panel.load_config(cfg)
        for w in (self.panel.run, self.panel.save, self.panel.load):
            w.hide()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.panel)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addWidget(scroll, 1)
        lay.addWidget(buttons)

    def config(self) -> PipelineConfig:
        return self.panel.build_config()
