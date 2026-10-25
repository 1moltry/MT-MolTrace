# DEVELOPMENT.md — 开发文档

面向开发与维护。**用户使用请看 [README.md](README.md)**；变更记录见 [DEVLOG.md](DEVLOG.md)；协作流程见 [CONTRIBUTING.md](CONTRIBUTING.md)。

仓库地址：<https://github.com/1moltry/MT-MolTrace>

## 背景

实验室用膜片钳固定纳米孔，实时监测分析物过孔时的电流信号。原流程靠人工设定基线与事件电平来找事件；本管线自动估计电平并分割事件。pCLAMP 11.2 保留作对照查看器与文档来源。

## 环境与安装

需要 Python ≥ 3.11（开发环境 3.13）。

```bash
pip install -e ".[dev]"      # 可编辑安装，含 GUI 依赖与 pytest
```

依赖由 `pyproject.toml` 声明：运行核心为 numpy / scipy / pandas / matplotlib / openpyxl / pyabf；GUI 另需 PyQt5 / pyqtgraph（`[gui]` 或 `[dev]` extra）。

安装后可用 `moltrace` 命令；下文的 `python -m nanopore` 是等价的旧别名。

## 数据准备

实验数据 `.abf` 不入库（体积大，且属实验产物）。从实验室共享盘拷到本地 `abf数据案例/` 即可——代码与文档里的示例路径都基于这个目录名。目录约定与各样例对应的异常场景见 `data/README.md`。

## 命令行

```bash
# 批处理整个目录（默认输出到 ./output）
python -m nanopore run "abf数据案例/abf数据案例"

# 指定输出目录与参数文件
python -m nanopore run <目录> -o <输出目录> --config params.json

# 单文件处理
python -m nanopore run "abf数据案例/abf数据案例/Ala.abf"

# 手动指定电平（双态孔 / 双物种数据推荐；不给则自动估计）
python -m nanopore run His.abf --level0 185 --level1 116

# 双向 / 多电平检测（肽信号基线上下波动，如 ARNKRS）
python -m nanopore run "pore2 ARNKRS 2Mm_0000.abf" --polarity both

# 导出当前参数为 JSON（作为后续 --config 模板）
python -m nanopore run <目录> --save-config params.json

# 模块化：默认只跑底座；--all 打开全部模块；--mods 自选（依赖自动补齐）
python -m nanopore run <目录> --minimal
python -m nanopore run <目录> --all
python -m nanopore run <目录> --mods anomaly,plots

# 驻留包络去抖（毛刺 / 多电平）；跨基线多电平再开 --burst-cross-base
python -m nanopore run <目录> --event-mode burst
python -m nanopore run <目录> --event-mode burst --burst-cross-baseline
```

批处理递归搜索 ABF，单个文件失败不会中断其他文件。

## GUI（开发向）

```bash
python -m nanopore gui                       # 不带参数，用工具栏「打开」选文件
python -m nanopore gui "abf数据案例/abf数据案例/Ala.abf"   # 启动并直接载入
```

源码方式启动也可双击 `MOLTRACE.bat`：要求已 `pip install -e .`，用 PATH 上的 `pythonw` 无控制台窗口运行。若双击后无反应，改双击 `MOLTRACE-debug.bat`，它会保留控制台显示报错。

功能要点：主波形支持滚轮缩放、拖动平移、自动缩放与 30M 样本自适应降采样，叠加蓝色理想化事件方波线与硬异常淡色带；下方切片显示选中事件的原始电流（事件内时间轴 ms，含起止虚线与开孔基准线）。事件表按 State 过滤，剔除表带 `drop_reason` 与计数汇总，两表首列均为稳定「序号」。点击主波形、表格行或散点都会选中同一事件：主波形平移跳转、缩放比例不变（工具栏「选中时自适应缩放」可切成缩放模式）。参数面板改动后自动重跑（600 ms 防抖，运行中的请求合并为一次），并可存/读 JSON 协议。统计面板含 dwell 直方图（线性 / log10 切换，时间单位 μs/ms/s/min 自适应）与 SD-|ΔI| 散点。Cursor 选区可对子区间用独立电平重析。图形统一白底，只用蓝色突出事件。

## 输出

每个输入文件生成（取决于启用的模块；未开对应模块则无对应产物）：

| 文件 | 内容 |
|------|------|
| `<名>_events.xlsx` | 事件特征表（events sheet，列名遵循课题组既定特征表规范）+ **excluded sheet**（被剔除事件及其 `drop_stage` / `drop_code` / `drop_reason`；异常 kind 如 `membrane_rupture`、`baseline_drift`，检测器规则如 `plateau:rupture`，导出过滤如 `toff<min`）+ 异常区间表（启用异常模块时生成） |
| `<名>_overview.png` | 全程轨迹（块均值）+ 蓝色理想化事件线 + 硬异常淡色带（红=breakdown/炸膜，橙=blockage，紫=jitter，蓝=反压/人工恢复，棕=baseline_drift；baseline_step 仅在异常表，不画） |
| `<名>_scatter.png` | 2×2 散点：dwell/时间 × ΔI、dwell/时间 × Io。ΔI 按正负分色（ΔI<0 蓝、ΔI≥0 红），纵轴保持线性并保留全部事件（含远离主群的真实电平）；toff 跨度超一个数量级时横轴转对数 |
| `<名>_hist.png` | 深度直方图 + log10 时长直方图 |
| `<名>_events.mat` | 每个保留事件的原始电流序列（`waveform_export` 模块）：cell 数组，每元素含 `current_pA`（起点到终点的原始采样，不含前后余量）、`start_sample` / `n_samples`、`t1_s` / `t2_s`、`fs_hz`、`event_id`。取原始信号，即使开启 `lowpass` 也不导滤波后波形 |

批次级：

| 文件 | 内容 |
|------|------|
| `summary.xlsx` | 每文件事件数、候选数、检测规则剔除数、异常是否启用、有效率（异常关闭时为空）、检测器、level0、极性、噪声 σ、异常计数、错误、耗时 |
| `dataset_all.csv` | 全部文件的保留事件纵向拼接（每行一个事件），供 MATLAB / 机器学习使用，含 `source_file` 列回溯来源 |

### 导入 MATLAB / 机器学习

`dataset_all.csv` 即为此准备（UTF-8 BOM，`readtable` 直接可读）：

```matlab
T = readtable('output/dataset_all.csv');
X = T{:, {'mean','rel_mean','std','skew','kurt','toff','MAD','CV', ...
          'q1','q2','q3','iqr','outlier_ratio'}};
y = categorical(T.Label);          % 分类目标（物种 / 样本）
```

该表对列名做了两处规范化（**仅此表**；`_events.xlsx` 保持课题组特征表规范列名不变）：

- `%mean` → **`rel_mean`**：`%` 不是合法 MATLAB 标识符，`readtable` 会把它静默改成 `x_mean`，按名取列会取错；
- `t1`/`t2` → **`t1_s`/`t2_s`**：本管线为**秒**，课题组特征表规范为**毫秒**，改名以免无声差 1000 倍。

做特征时应排除 `t1_s` / `t2_s`（时间戳，会造成时间泄漏）与 `I0`（逐记录常数）。

需要逐事件原始电流波形时，开启 `waveform_export` 模块，每个 `.abf` 得到同名 `<名>_events.mat`：

```matlab
S = load('output/Ala_events.mat');
if ~isempty(S.events)
    e = S.events{1};                      % 一个事件（struct）
    w = e.current_pA(:);                  % 原始电流序列 [n×1]，无前后余量
    t = e.t1_s + (0:numel(w)-1)'/e.fs_hz; % 每个采样点的时间（s）

    all_events = [S.events{:}];           % 全部事件拼成 1×N struct 数组
end
```

`start_sample`（0-based）与 `n_samples` 是权威边界，与 `_events.xlsx` 的 `t1` / `t2` 一致；`events` 为空的记录仍会生成可加载的空 cell。

## 功能模块（mod）

管线 = **底座 + 可多选模块**。底座恒跑：读盘 → 电平估计 → 事件检测 → 特征提取 → 事件表 `<名>_events.xlsx`。其余功能都是模块，**默认全关**，按需开启（CLI `--mods/--all/--minimal`；GUI「模块」区按功能分标签页勾选，并记住上次选择）。

| mod | 分类 | 作用 | 主要参数 | 产物 |
|-----|------|------|----------|------|
| `lowpass` | 预处理 | 检测前低通滤波 | `filter_lowpass_hz` | 滤波后信号 |
| `dynamic_i0` | 预处理 | 动态开孔基线，逐事件 Io | `dr_pA` | 逐事件 Io |
| `anomaly` | 异常检测 | 检测后的可选异常区间（反压 / 膜抖 / 炸膜 / 漂移）；不改变事件边界 | `jump_min_ms` 等 | anomalies sheet + 区带 + 剔除 |
| `refined_anomaly` | 异常检测 | 细粒度分级异常（依赖 `anomaly` + `dynamic_i0`） | `refined_*` | 分级 kind |
| `plots` | 单文件输出 | 输出三张图 | — | `_overview/_scatter/_hist.png` |
| `waveform_export` | 单文件输出 | 每事件原始电流序列 | — | `<名>_events.mat` |
| `dataset_export` | 批次输出 | 合并训练表 | — | `dataset_all.csv` |
| `summary` | 批次输出 | 批次汇总 | — | `summary.xlsx` |

新增模块只需在 `nanopore/mods.py` 注册一个 `ModSpec`（含 `category=`），GUI 标签页与 CLI 解析都会自动带上。

**检测变体不是模块**：事件极性（`polarity`）、事件平台占比（毛刺门控）等仍在参数里，它们改变底座「怎么检测」，与模块正交。

> **行为变更**：默认「只底座」不同于旧版（旧版默认全开异常 / 图 / 合并表 / 汇总）。需要旧行为用 `--all`。

异常识别是**检测后的可选后处理**：关闭时结果对象与界面都明确标记“未筛查”，不会用 `有效 100%` 冒充已检查；开启时也只剔除已检出事件，不改变 level / burst / plateau 的事件边界。检测器自身的候选有效性规则单独记为 `drop_stage=detector`，与异常原因分属不同命名空间。GUI 顶部的“异常识别：开/关”标签显示本次实际状态。

检测器目录集中在 `nanopore/registry.py`，GUI、CLI、批处理与对比窗口都从同一份元数据生成选项。参数面板从上次载入的完整协议增量覆盖；未在界面暴露的配置字段不再被重置。未知配置键会告警，不再静默丢弃。

## 检测模式：电平法 / 驻留包络去抖（burst）

`event_mode` 决定底座怎么分割事件，默认 `level`。

| 模式 | 做法 | 适用 |
|------|------|------|
| `level` | 逐样本最近电平 → 游程 → 同电平桥接 | 常规清晰脉冲；慢孔态切换（Ala/Asp/Gln） |
| `burst` | 阻孔指示器 + 去抖（丢短块 / 填空隙 / 真开孔判定） | 事件体内大量毛刺回落或越孔；电流在开孔上下跳跃、多电平 |

burst 参数（仅该模式生效）：

- `burst_min_gap_ms`（默认 30，GUI「开孔回落容差」）：两次阻孔之间的回落短于此值不切断事件——主调钮。量的是「电流回到距开孔不超过判定阈值」的连续时长，不是肉眼回基线时长；间隙中间超过判定阈值的毛刺也会中断计时。调大更不易切碎，但可能并掉相邻真事件。
- `burst_open_cover`（默认 0.75，GUI「开孔判定比例」）：间隙里至少这么大比例的时间落在 ±`burst_enter_frac`×步长 的开孔带内，才允许切分；否则并入同一事件。开孔带与进入阈值共用同一个 ×步长 比例，不另设电流比例。
- `burst_merge_max_ms`（默认 200，GUI「最长合并间隙」）：没真正回到开孔时，只合并不超过这个时长的间隙；更长的浅态保留为独立事件。0 = 不合并。
- `burst_min_block_ms`（默认 2，GUI「最短阻孔时长」）：短于此的阻孔碎片先丢弃（滤孤立尖峰，也不用于桥接相邻事件）。
- `burst_enter_frac` / `burst_exit_frac`（默认 0.30 / 0.20，GUI「阻孔判定阈值」/「事件幅值取样下限」）：前者决定电流偏离开孔多少算阻孔，事件起止按它切；后者只决定用哪些样本估幅值，不剔除事件。两者均为 × 电平步长。
- `burst_cross_baseline`（默认关）：把开孔两侧的偏离都算作同一事件（多电平 / 上下穿越）。
- `burst_min_occupied_frac`（默认 0.30）：事件体内确实阻孔的样本占比低于它则丢弃（滤稀疏尖峰链与浅脉冲）。
- `burst_min_depth_frac`（默认 0.15）：活动体中位偏离低于此比例 × 步长则丢弃。两项必须同时满足；双侧模式下取两侧中位幅值的大者，避免平衡多电平被整体中位抵消。

> 「尖峰抑制 / 事件合并容差 / Level contribution / 事件平台占比」只用于电平法。burst 模式下界面会隐藏它们——它们不参与 burst 计算。

burst 用动态 I0(t) 作开孔参考以吸收漂移，但它假设开孔电平稳定。Ala/Asp/Gln 这类慢速孔态切换（110↔180 pA、分钟级驻留）会把另一态读成长阻孔，请继续用电平法。

## 参数说明

| 参数 | 含义 | 默认 |
|------|------|------|
| `ignore_duration_ms` | 尖峰抑制（检测前）：离开电平短于此时长的短暂偏离被吸收，不产生事件 | 2 ms |
| `ignore_event_duration_ms` | 事件电平上下文：同电平事件之间基线间隙短于此时长的合并为一个事件（长阻孔内的噪声槽不切碎） | 50 ms |
| `level_contribution` | 电平跟踪的指数更新权重 | 0.10 |
| `dwell_min_frac` | 尖峰抑制：事件 body 需 ≥30% 样本落在某电平邻域 | 0.30 |
| `event_plateau_min_frac` | 事件稳定性门控（毛刺 / 闪烁）：事件体驻留单一电平（最近整数电平 ±0.5 步）的样本占比低于此值即剔除。快闪烁约 0.5，真阻孔约 1.0。默认 0=关（单一标量无法既剔毛刺又保住多电平文件；TRP 这类密集毛刺文件手动设 0.85~0.95） | 0 |
| `--level0/--level1` | 人工指定电平（不给则自动估计） | 自动 |
| `--polarity` | 事件极性（搜索方向）：`auto`=按电平直方图推断（默认）；`up`/`down`=仅向上 / 向下；`both`=双向（基线两侧阻孔都算，并自动多电平）。ARNKRS 这类肽信号需 `both` 才能检出深阻孔；`both` 对部分文件会过检，建议逐文件确认 | auto |
| 电平中点阈值 | 50% crossing（两电平中点） | — |
| 短事件判定（brief） | < 4τ（滤波时间常数），State 列标 B | 自动 |
| `pre_event_ms` | 特征提取的开孔电流窗口（与特征表规范一致） | 25 ms |
| `min_toff_ms` | 最短事件时长（仅导出）：已检出事件中 dwell ≤ 此值的进剔除表（`toff<min`） | 10 ms |
| `event_mode` / `burst_*` | 检测模式与 burst 参数，见「检测模式」一节 | level |
| `hold_voltage_mV` | 电压 protocol 的保持电平；不给则取电压轨迹中位数 | 自动 |
| `refined_drift_enabled` | 慢漂移 / 不稳定区间检测（kind `baseline_drift`）：缓慢、不可逆、且伴随高散布的开孔电平位移。需位移与不稳定两个键同时满足——稳定的孔态阶跃、可恢复的瞬态、以及位移但仍在出正常事件的良性漂移都不会误报 | 开 |
| `refined_drift_min_frac` | 位移键：块中值偏离记录头锚点 ≥ 此比例 ×\|锚点\| | 0.05 |
| `refined_drift_iqr_ratio` | 不稳定键：区间 IQR ÷ 记录头 IQR ≥ 此倍数 | 3.0 |
| `refined_drift_block_s` / `_min_s` | 块长（s）/ 漂移段最短时长（s） | 15 / 20 |

## 电压 protocol 与异常区间

电压信息有两个来源，按优先级使用：

1. 电压 ADC 通道（`IN 1` 等，与电流等长）——多数双通道记录（Ala/His/T3/Asp⋯⋯）；
2. 命令电压波形（ABF 头里的 protocol / epoch 表，pyabf `sweepC`）——tPAL 这类只录电流、但带电压 protocol 的文件也能取到。

判定规则：保持电平 = 电压轨迹的中位数（主导电平即传感段）。任何持续偏离保持电平的区段（反压、tPAL 的排出 / 静息段、0 mV 段）都记为异常区间 `reverse_voltage`，落在其中的事件被剔除（`drop_reason` 可查），切换处带一段瞬态保护窗。因此不预设「反压 = 负电压」，正脉冲与 0 mV 静息段同样会被识别。

### 慢漂移 / 不稳定区间（`baseline_drift`）

与电压无关的第二类结构性异常。判据取自动态 I0 基线的逐 1 s 窗中值（含非安静窗——安静窗链会跟随漂移而看不到它），聚合成 15 s 块中值，标注同时满足以下四条的末端区间：

1. **位移**：块中值偏离记录头锚点 ≥ `refined_drift_min_frac × |锚点|`（默认 5%）；
2. **不稳定**：区间 IQR ÷ 记录头 IQR ≥ `refined_drift_iqr_ratio`（默认 3.0）；
3. **渐进**：块间最大跳变 ≤ `max(6 pA, 5% × |锚点|)`——拒绝 110↔180 那样的孔态阶跃；
4. **持续不可逆**：长度 ≥ `refined_drift_min_s`，且不回到位移带内——拒绝可恢复的瞬态。

位移与不稳定必须同时满足：良性慢漂移（有位移、仍在出正常事件、散布正常）不判；密集事件团（散布大、但基线不位移）也不判。区间内事件剔除；不稳定度达到炸膜级别（IQR ≥ 4× 记录头）时，尾部再嵌套标一个 `membrane_rupture`，异常面板可区分「漂移」与「漂移导致的炸膜」。

## 双态孔与多物种数据

部分样例（Ala/Asp/Gln）存在慢速孔态切换（如 110↔180 pA 间分钟级驻留），切换边界以 `baseline_step` 异常标记（不判无效）。自动模式取离基线最近的显著电平为事件电平；若需分析另一态或另一物种，用 `--level0/--level1` 手动指定（如 His：`--level0 185 --level1 116` 得到深阻断物种事件）。

## pCLAMP 自带样例

pCLAMP 11.2 安装在 `pCLAMP11.2/`（该目录不入库，本地保留作对照查看器），其 `Sample Data/` 自带约 35 个 `.abf` 演示数据（含干净单通道 `kchann.abf`、`burst.abf` 等）。pyabf 不支持其中 float 格式 ABF1（"Support for float data is not implemented"）；`io.read_abf` 先嗅探文件签名，float-ABF1 走内建读取器（含多通道 / 真实单位 / 损坏校验），其余交 pyabf：

```bash
python -m nanopore run "pCLAMP11.2/Sample Data" -o output_pclamp
```

回归测试 `tests/test_io.py` 在 pCLAMP 样例存在时自动启用（否则 skip），验证 float-ABF1 读取与 kchann 事件检测。注意多数 Sample Data 是电压钳 / 宏演示，不是单通道电流数据，检出事件数仅供参考；只有事件类样例（kchann / singles / burst / 4level）有分析意义。

## 项目结构

```
nanopore/          Python 包
├── io.py          读取：签名嗅探分发 + 内建 float-ABF1 读取器 + pyabf；双通道样例自动读入电压通道
├── preprocess.py  可选低通滤波
├── baseline.py    自动 Level0/Level1 估计
├── baseline_i0.py 动态 I0(t) 开孔电流基线（逐事件 Io 免疫阻孔漂移）
├── detect.py      事件检测分派（电平法 / burst）与检测诊断
├── detect_plateau.py 平台滞回检测（含可追溯的检测器有效性剔除）
├── params.py      通用参数元数据（ParamSpec）
├── registry.py    检测器目录、id 解析与配置规范化
├── anomaly.py     异常检测（可选后处理；不参与事件边界）
├── features.py    特征提取（列名遵循课题组既定特征表规范）
├── roi.py         Cursor 局部分析（子区间独立电平重析）
├── analysis.py    输出：事件表 / 图 / 合并表 / 事件波形 .mat
├── analyze.py     共享分析编排（底座 + 模块；pipeline 与 GUI 共用）
├── mods.py        功能模块注册表（ModSpec / MODS / resolve_mods）
├── cli.py         命令行入口（run / gui）
├── config.py      参数管理
└── gui/           交互式桌面 GUI（PyQt5 + pyqtgraph）
release/
└── build_release.py  Windows 发行包构建脚本
tests/             合成信号回归测试
```

**本地目录，不入库**（见 `.gitignore`）：`abf数据案例/`（实验数据）、`pCLAMP11.2/`（商业软件）、`_tmp/`（Clampfit 帮助提取文本）、`output/`（默认输出目录）。

## 测试

```bash
python -m pytest tests/ -q                                  # 完整门禁
python -m pytest tests/ -q -m "not gui and not integration" # 日常快检
python -m pytest tests/ -q -m gui                           # 界面
python -m pytest tests/ -q -m integration                   # 本地样例端到端
```

`tests/test_gui_*.py` 由 `tests/conftest.py` 自动加 `gui` 标记；依赖本地 `.abf` 的慢测试使用 `integration` 标记。编辑中先跑相关文件与快检，提交前跑完整套件，发布前再加真实样例和发行包自测。测试策略与后续阶段计划见 [`PLAN_fingerprint_platform.md`](PLAN_fingerprint_platform.md)。

算法变更须配套 tests/ 回归（合成信号解析真值），交付前全绿。CI 在 ubuntu 与 windows 上跑同一套完整测试。

## 发行打包

```bash
python release/build_release.py          # 出 release/MOLTRACE_v<版本>_win64.zip
```

构建脚本先用 `git archive HEAD` 取干净源码树（`.gitattributes` 里的 `export-ignore` 规则剔除 tests、DEVLOG、规划稿、CI 配置、启动 bat；未入库的本地文件本就进不去），再用 PyInstaller 打成免安装 exe 目录，附上 `README.md` 与 `LICENSE`，最后校验清单并压缩。

构建使用独立的干净 venv（默认 `build/venv`，不存在时脚本自动创建并按 `pyproject.toml` 安装依赖）。这一步很关键：直接用 Anaconda 基础环境会把 MKL、cupy、panel 等无关包带进包里，体积从约 300 MB 膨胀到 2 GB。

要求工作区已提交（`--dirty` 可跳过检查，仅用于调试即出包）；图标默认取 `E:\download\1moltry_nanopore_no_person.ico`，可用 `--icon` 覆盖。

## 开发约定

- 每次开发会话在 `DEVLOG.md` 追加一条（变更、测试状态、下一步）。
- 算法实现以实样数据 + 合成真值测试为准；本地 `_tmp/` 下的对照资料（含 Clampfit 帮助文本，不入库）可查阅参考，但不作为依据。
- 分支、提交与 PR 流程见 `CONTRIBUTING.md`。

## 路线图

- **v1（完成）**：双向事件分割、异常检测剔除、逐事件开孔电流漂移补偿、17 特征、散点 / 直方图、CLI 批处理。
- **v2（完成）**：交互式 GUI（事件表 + 剔除表 + 切片联动 + 统计面板 + Cursor 局部分析），事件波形导出 `.mat`，批量处理与批次汇总。
- **v3（规划）**：多电流平台 / 混合信号自动多电平检测；近基线 template matching（Clements & Bekkers 1997）；tPAL 多电压 protocol 解析。
