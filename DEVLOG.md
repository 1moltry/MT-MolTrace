# DEVLOG — 开发日志

格式：`## [日期] 标题` + 变更 / 测试 / 下一步。只记里程碑与关键取舍，不记过程叙述。

---

## 当前状态

**v1 完成**：全自动处理 .abf → 事件分割 + 异常检测剔除 + 20 列特征表 + 静态图 + 批处理 CLI。`pytest` 29 passed，6 个实验室样例全部验收通过。
**v2 启动（GUI G1 + G1.5）**：交互式桌面程序 `python -m nanopore gui` 核心功能已验证；波形观感按用户反馈简化（白底 + 蓝色事件线）；事件检测加尖峰抑制；float-ABF1 读取使 pCLAMP Sample Data 全量可用。
**电压通道与细粒度异常 M1-M3 完成**：io 电压通道 + 动态 I0(t) 开孔电流基线 + 异常精筛（反压恢复/分级膜抖/炸膜）；M4 Cursor 局部分析见 DEVLOG 末尾规划。
**P1 剔除可追溯 + 参数接通 完成**：xlsx/GUI 可查每个被剔除事件的 drop_reason；「最短 toff (ms)」参数生效。见下方 [2026-09-08]。
**P2 M4 Cursor 完成**：GUI Cursor 选区 + 对区间重跑（独立电平）。
**P3 判据实证修正 完成**：炸膜电平门控 / 宏块 jitter 门控 / 基线锚定。见下方 [2026-09-08]。
**G1.6 右侧统计面板改版 完成**：toff 直方图（线性/log10 切换）+ SD-|ΔI| 散点。见下方 [2026-09-09]。
**P4 事件过分割/电平漂移修复 完成**：T3/SLR/angiotensin III 等实样问题根因修复。见下方 [2026-09-09]。
**P5 电压 protocol 段识别 完成**：tPAL 切换电压段不再误计为事件。见下方 [2026-09-10]。
**G1.7 统计面板修复 + GUI 批量处理 完成**：直方图分箱/坐标轴修复、批量处理入口。见下方 [2026-09-10]。
**P6 TRP 毛刺门控 + 慢漂移/炸膜区间 完成**：新增事件稳定性门控（毛刺，默认关）+ `baseline_drift` 慢漂移/不稳定区间（默认开）。见下方 [2026-09-11]。
**G1.8 统计面板可见性 + 时间轴单位 完成**：透明笔刷根因修复（柱子/异常阴影/选区底色/定位框）+ 散点单色 + x 轴单位自适应（μs/ms/s/min，附手动下拉）。见下方 [2026-09-11]。
**版本标记 完成**：GitHub 标签 `v1`（命令行管线 + PyQt5 GUI 里程碑）与 `v2`（同事整合版）已建立并附 Release。见下方 [2026-09-24]。
**P7 稀疏肽异常误判 + 双向检测开关 完成**：ARNKRS 深阻孔被误判 breakdown/blockage 的根因（包络塌缩到 8σ）修复（25 实样零回归）；新增 `polarity` 显式开关（自动/向上/向下/双向），pore2 切双向即把深阻孔纳入事件，默认自动保持现状。见下方 [2026-09-11]。
**G1.9 桌面快捷入口 完成**：双击桌面 `SDL纳米孔分析` 即开 GUI，无需命令行。见下方 [2026-09-13]。
**G1.10 MATLAB 训练导出 + 散点图极值修复 完成**：批处理产出合并表 `dataset_all.csv`（MATLAB 合法列名）；散点图 toff 转对数横轴、ΔI 改线性轴并按正负分色（symlog 实测有害，已弃）。见下方 [2026-09-13]。
**v3 规划已就绪**：全项目审查（正确性 / 健壮性 / 冗余 / 算法能力）与 MATLAB 接线硬阻塞已归纳为下方《v3 规划》章节，作为下一大版本的输入。见下方 [2026-09-13]。
**burst 检测 完成**：新增默认关闭的 `event_mode="burst"`（驻留包络去抖）：把毛刺回落、越孔、上下跳跃合并为一个事件；含占位率/深度门控防「尖峰链」伪事件、`burst_cross_baseline` 支持基线上下穿越；GUI/CLI 可选可调。见下方 [2026-10-19]。
**工程化 完成**：纳入 git 版本控制并搭建 GitHub 协作流程（CI / 模板 / Dependabot / 打包）。见下方 [2026-09-20]。
**文档与协作 完成**：仓库更名 `SDL-Auto-Data-process`；`CONTRIBUTING.md` 回归贡献者指南并载明共同开发者与资助方，协作机制移入本文件；`LICENSE` / `pyproject.toml` 署名同步。见下方 [2026-09-25]。
**项目精简 完成**：删除从未入库的「先验增强引擎」层，仓库收敛为单一 `nanopore` 包；修复 pyabf/GUI 依赖与 CI 的隐性错配。见下方 [2026-10-09]。
**功能模块化 完成**：底座 + 可多选模块（默认最小、GUI 记住上次选择）；抽出共享 `analyze()` 消除 GUI/CLI 重复。见下方 [2026-10-19]。
**GUI 布局重做 完成**：左侧事件表 + 剔除事件表、中间上波形下切片、点击联动（平移不改缩放）。见下方 [2026-10-19]。
**事件波形导出 完成**：`waveform_export` 模块把每个保留事件的原始电流序列（无余量）导出为 `<名>_events.mat`，供 MATLAB 直接读取。见下方 [2026-10-19]。
**发行打包 完成**：`release/build_release.py` 一键产出 Windows 免安装 exe + zip（干净源码树，无内部文件）；README 改为用户向，开发文档移入 `DEVELOPMENT.md`。见下方 [2026-10-19]。

---

## v3 规划（2026-09-13 全项目审查）

审查范围：`nanopore/*.py` 核心层逐行 + `nanopore/gui/*.py` 全 10 文件 + 实测验证（非静态推断）。按 **正确性 → 健壮性 → 冗余 → 算法能力** 排列，另附 MATLAB 接线的阻塞项。

### 1. 必修：正确性（影响已有数据可信度）

| # | 问题 | 位置 | 证据 |
|---|------|------|------|
| C1 | `skew`/`kurt` 与特征表规范不一致——规范侧 `skewness`/`kurtosis` 默认有偏(flag=1)，pandas `.skew()/.kurt()` 是偏差校正版 | `features.py:161` | 同组样本实测 skew **0.8007 vs 0.6969**；kurt **+0.0396 vs −0.4366（符号相反）**。违反特征对齐要求，会让按规范训出的模型推理系统性偏移 |
| C2 | GUI 参数面板静默丢配置——`build_config()` 只传 15 个 kwarg 新建 config，其余 ~20 字段回落默认 | `gui/parampanel.py:144` | 载入协议 JSON 后「重跑」→ 未暴露参数被改回默认（`refined_anomaly_enabled=False`→`True`），再保存即写坏协议；批处理对话框同用此函数 |
| C3 | 散点图点击跳转是死功能——全项目无任何 `sigClicked.connect` | `gui/scatterview.py:166` | grep 确认；测试直接调 `_click()` 所以长期为绿（测试在替死代码背书） |

### 2. 健壮性

| # | 问题 | 位置 | 证据 / 影响 |
|---|------|------|------|
| R1 | 事件检测分类分配 `(n, 电平数)` 完整矩阵 | `detect.py:185` | 实测外推：13M 样本峰值 ~595 MB、**30M ~1.4 GB**（GUI 已按 30M 设计）。改逐电平增量取 min 可降一个数量级 |
| R2 | QThread 生命周期未管理 | `gui/controller.py:200`、`gui/batchdialog.py:199` | 重跑覆盖唯一引用致运行中被 GC → `Destroyed while thread is still running` 进程中止；取消批处理 `wait(5000)` 超时同样复现。**修前先复现** |
| R3 | 未加载文件点「全览」崩溃 | `gui/waveview.py:284` | `_full_extent` 直接 `len(None)`；相邻函数均有 None 保护，仅此两处漏 |
| R4 | `config.load` 静默丢弃未知键 | `config.py:92` | 参数名写错不报错、直接忽略，用户误以为生效。应至少 `warn` |
| R5 | CLI 不递归子目录、不匹配 `.ABF`；GUI 递归 | `cli.py:67` | `abf数据案例2/` 按 tPAL / 生物胺 / 肽 分子目录，CLI 会漏扫 |

### 3. 冗余 / 可维护性

- `detect._bridge_same_level_events` 的 `step` 参数**从未使用**（`detect.py:90`）。
- `anomaly.py:416` `excluded` 死变量，且白分配 n 字节（30M ≈ 30 MB）。
- `current.astype(float)` 7 处多余整数组拷贝（`current` 本已 float64）；其中 `anomaly.py:609` 是**整记录**拷贝（30M ≈ 240 MB）→ 改 `np.asarray(x, dtype=float)` 零拷贝。
- `features.py:161` 每个事件构造一次 `pd.Series` 只为算 skew/kurt（上千事件 = 上千次对象构造）；修 C1 时一并去掉 pandas 依赖。
- `roi.py:44-83` 与 `pipeline.process_file` 重复整套「估计电平 → 极性覆盖 → 滤波 → 检测 → 特征」流程 → 抽 `_analyze_segment()` 共享。
- `anomaly.events_in_invalid_regions` 现仅测试调用（生产走 `invalid_region_reasons`）。
- GUI：square-pulse 构造重复两处（`waveview`）；table-model 样板重复（`eventtable` / `anomalyview`，且 `anomalyview.py:66` 把文本列也右对齐了）。

### 4. 算法优化

| 项 | 内容 | 说明 |
|---|------|------|
| A1 | 特征定义对齐 | 随 C1 一并修；补「特征值 vs MATLAB 公式」回归测试（现有 `test_features.py` 未覆盖该点） |
| A2 | 多电平检测 | 现硬编码 `±8 step` 网格 + 单一主导 `level1`；混合物数据（`DQ+SLR+LRG+NKR+IK mixture`）需多平台同时建模 |
| A3 | Template matching | 近基线小事件现完全检不到（README 路线图已列，Clements & Bekkers 1997） |
| A4 | 异常模块拆分 | `anomaly.py` 685 行塞两个检测器；`detect_artifact_segments` 单函数 315 行嵌套状态机 → 拆 `macro.py` / `refined.py` + 统一 `AnomalyRegion` 消费层 |
| A5 | 绘图降采样 | `plot_overview` 超长记录会画 ~30 万点 → 降到固定 ~2 万点分辨率 |
| A6 | 批处理内存 | `run_batch` 把所有保留事件 DataFrame 攒在内存再拼 `dataset_all.csv` → 大批量改流式追加 |

### 5. MATLAB 接线：硬阻塞（需决策）

实测 `D:\Matlab` = **R2024b Update 3，仅装 24 个工具箱，全是 Simulink / codegen 系**：

- ✅ 基础可用：`readtable` / `writetable` / `plot` / `mean` / `std`
- ❌ 全缺：`kmeans` `pca` `fitglm` `confusionmat` `cvpartition` `corr` `fitcensemble` `fitcsvm` `fitctree` `fitcknn` `fitcecoc` `treeBagger` `classificationLearner`

**没有 Statistics and Machine Learning Toolbox** → 「在 MATLAB 里训模型」目前走不通，属 license/安装问题，非代码问题。

| 方案 | 说明 |
|------|------|
| A 装工具箱 | 有 license 即装，之后 MATLAB 侧 `readtable → fitcensemble` 全通 |
| B Python 训练 + MATLAB 只出图（推荐）| 管线已在 Python，scikit-learn 一次 pip 即得；`dataset_all.csv` 双向可用 |
| C 纯基础 MATLAB | 无分类器，不现实 |

自动化形式（与选路无关，可先做）：批处理侧 `dataset_all.csv` **已导出**；下一步加 `--matlab` 开关或 `matlab/` 模板目录，Python 侧 `subprocess` 调 `matlab -batch "run('analyze.m')"`（`matlab` 已在 PATH）。

### v3 建议推进顺序

**C1**（特征正确性）→ **C2/C3**（GUI 真 bug）→ **R1**（内存）→ R3/R4/R5 → 冗余清理 → **A2/A3**（算法能力）。

---

## [2026-10-21] burst 去抖顺序修正：先删碎片、再填空隙

**问题**：`min_gap_ms` 较大时，回落间隙中间的短毛刺会把一段真实回落切成两段小于 `min_gap_ms` 的间隙；原顺序（先填隙、后删碎片）会把整段回落填成阻孔，两个独立事件被并成一个。用户反馈「设 30 ms 却并掉约 50 ms 的回落」。
**变更**：`detect_events_burst` 改为先 `_drop_short_blocks`（丢弃短于 `min_block_ms` 的阻孔碎片），再 `_fill_short_gaps`（填充短于 `min_gap_ms` 的开孔间隙）；docstring 同步。语义与「孤立尖峰不构成事件」一致，毛刺不再能桥接相邻事件。
**测试**：新增合成回归（50 ms 间隙 + 中央 1 ms 毛刺 → 2 个事件）；全量 `pytest` 170 passed。样例影响（默认 burst 参数）：ARNKRS 58→82、Asp 76→92、His 308→309，其余文件不变。
**下一步**：用户实样核对新增拆分的合理性；GUI 参数措辞优化（待确认）。

---

## [2026-10-19] 发行打包（免安装 exe）+ README 用户向重写

**目标**：把软件交给别人用——解压双击即开、不装 Python、不含任何内部文件。
**变更**
- 新增 `release/build_release.py`：`git archive HEAD` 取干净源码树（`.gitattributes` 的 `export-ignore` 剔除 tests/DEVLOG/DEVELOPMENT/规划稿/.github/启动 bat/data/release）→ PyInstaller `--windowed --onedir` 冻结 GUI（hidden imports: pyabf、scipy.io、openpyxl、matplotlib.pyplot+Agg；排除 tkinter 与未用到的 Qt 模块）→ 附 README/LICENSE → 清单断言 → `release/SDL纳米孔分析_v0.1.0_win64.zip`。要求工作区已提交（`--dirty` 仅调试）。
- 构建改用**独立干净 venv**（`build/venv`，缺失时自动创建）：直接用 Anaconda 基础环境会把 MKL、cupy、panel、playwright 等带进包，体积 1.9 GB → **250 MB**。
- 新增**构建后 DLL 补齐**：扫描包内 `.pyd/.dll` 的导入表，把 PyInstaller 追踪不到的 Anaconda 库（`ffi.dll`、`libexpat.dll`、`sqlite3.dll` 等 6 个）一并收进 `_internal`，否则冻结版启动即报 `_ctypes` / `expat` 导入失败。
- README 重写为**用户向**（快速上手 / 界面导览 / 如何导出 / 输出文件 / 常用设置 / MATLAB 对接 / FAQ）；开发内容迁入新建 `DEVELOPMENT.md`（安装、CLI、模块表、检测模式、参数表、电压与漂移判据、结构、测试、打包）。
- `.gitattributes` 增 `export-ignore`；`.gitignore` 增 `/release/*.zip`；`pyproject.toml` 删未引用的 `xlrd`。

**测试**：`python -m pytest tests/ -q` → 169 passed；构建脚本产出 zip（250 MB 解压 / 106 MB 压缩），清单核对无 tests/DEVLOG/PLAN/.github/CLAUDE.md/data；冻结版临时命令行程序实跑 Ala.abf → 37 事件，`_events.xlsx`、三张 PNG、`_events.mat`、`dataset_all.csv`、`summary.xlsx` 全部产出；GUI exe 启动并显示主窗口。

**下一步**：图形观感与 exe 首次启动需用户人工过目（本模型无视觉确认能力）。

---

## [2026-10-19] 事件波形导出模块（waveform_export → .mat）

**背景**：事件表只出标量特征，GUI 切片只是屏幕显示，MATLAB 侧拿不到每个事件的原始电流序列。
**变更**
- 新模块 `waveform_export`（默认关）：每个 `.abf` 出同名 `<名>_events.mat`，一个 cell 数组，每事件含 `current_pA`（起点到终点的原始采样，**无前后余量**）、`start_sample`/`n_samples`（权威边界，与 `features.py` 的 `round(t*sr)` 一致）、`t1_s`/`t2_s`、`fs_hz`、`event_id`；顶层带 `source_file`/`label`/`units`/`fs_hz`。
- 取**原始电流**（即使开 `lowpass`）；只导保留事件；空事件表也生成可加载的 1×0 cell。
- 接入点 `pipeline.process_file`（CLI 与 GUI 批处理共用）；GUI 复选框由 mod 注册表自动生成。
- `scipy.io.savemat`（scipy 已是依赖），无新增依赖。

**取舍**：cell-of-structs 而非 struct-of-cells——MATLAB 侧 `S.events{k}.current_pA` 直接取向量；`start_sample`/`n_samples` 显式存下，避免 MATLAB 再从浮点秒换算带来 off-by-one。

**测试**：`python -m pytest tests/ -q` → **169 passed**（新增 8 例：精确切片/无余量、多事件行序、尾部夹取、退化事件跳过、空表、元信息往返、开 lowpass 仍导原始、无模块时不产 mat）。样例目录 6 文件实测产出 mat，逐事件与 `read_abf` 原始切片逐样本相等。

**下一步**：文件偏大（长事件记录，Ala 31 MB / ac-Thr 138 MB）；若需要可加 `do_compression`。

---

## [2026-10-19] GUI 选项改动自动生效（防抖重跑 + 旧结果丢弃）

**问题**：改了检测模式/参数后界面不变，必须手动点「重跑检测」才生效。
**修复**
- `ParamPanel.changed` 信号：任何参数、检测模式、模块勾选改动都触发。
- `MainWindow` 用 600 ms 单次定时器防抖后自动 `build_config → rerun`；手动「重跑」会取消待执行的防抖，避免重复跑。
- `Controller` 增加**代际（generation）守卫 + 运行中合并**：运行中再改参数只记一次 pending，当前分析结束后用**最新配置**再跑；旧代结果即使晚到也丢弃，绝不覆盖新结果。
- 大文件全量分析需数秒，防抖避免逐格调参时任务排队爆炸。

**说明**：805–810 s 的两个实质事件（+42 pA/96 ms、−105 pA/1117 ms）经用户确认为真事件，保留。

**测试**：`python -m pytest -q` → **161 passed**（新增 1 例：参数/模式/模块改动发出 `changed`）。

---

## [2026-10-19] burst 门控改「同时满足」+ 电平法参数随模式隐藏

**核实**：用户把「尖峰抑制（ignore duration）」设 50 ms 后，805 s 附近的浅脉冲仍在。两条原因：
1. **burst 模式根本不使用 `ignore_duration`**（只用 `min_gap` / `min_block`）。该参数在 burst 下是惰性的，但界面一直显示——属误导。
2. 浅脉冲（≈18 pA、占位率 ≈1%）被上一版「深度兜底（OR）」放行：只要体内中位偏离 ≥ 0.15×步长就保留。

**修复**
- burst 门控改为**同时满足**：占位率 ≥ `occ` **且** 体内中位偏离 ≥ `depth`×步长。`body_depth` 在双侧模式下取「两侧各自中位幅值的大者」，避免平衡多电平被整体中位抵消。
- GUI 新增「电平法参数」组（尖峰抑制 / 事件合并容差 / Level contribution / 事件平台占比），burst 模式下隐藏；burst 组在电平法下隐藏。参数与模式不再互相误导。
- 实测该文件：事件 666→**551**，|ΔI|<25 pA 仅剩 **2 个**；805–810 s 剩 2 个实质事件（+42 pA/96 ms、−105 pA/1117 ms）；730.1–731.1 s 仍为 1 个；810–880 s 的 4 个 −16.5 pA 浅态移除。

**测试**：`python -m pytest -q` → **160 passed**。

---

## [2026-10-19] GUI 持久化完整检测协议（修「重启后退回电平法」）

**现象**：用户重启 GUI 后，730.1–731.1 s 又被切成 13 段（+29/+45/+47 pA 的向上小峰各成事件），误以为 burst 无效。
**根因**：`QSettings` 只持久化了模块勾选（`enabled_mods`），**没有持久化 `event_mode` 与参数**。重启后模式静默回到默认 `level`，看到的是电平法的切分——不是算法退步。
**修复**：
- `_load_settings` / `_save_settings` 改为持久化完整 `PipelineConfig`（JSON），启动时恢复「检测模式 + 全部参数 + 模块勾选」。
- 状态栏完成消息带模式：`完成[burst]: …` / `完成[level]: …`，避免再次看错模式。
**实测**：该文件 730.146–731.130 s 在 burst 下为 **1 个事件**（983.6 ms，occ=0.99）；level 下为 13 段（含 +29/+45/+47 pA 的向上小峰）。
**测试**：`python -m pytest -q` → **160 passed**（新增 1 例：模式与参数跨实例恢复）。

---

## [2026-10-19] burst 尖峰链门控（真实文件复现：毛刺仍被当成事件）

**现象**：`pore1 90NTA Ni HS trypsin CIS10UL_0000.abf`（2168 s）用 burst 默认参数，810–880 s 仍有大量伪事件。

**根因**：`_fill_short_gaps` 会把**稀疏尖峰之间的开孔间隙**也填掉，几次尖峰因此被拼成一个「事件」，但其体内几乎全是开孔。
- 实测（810–880 s）：伪事件（|mean|<10 pA）占 27/55，体内占位率中位数 **0.03**、体内中位偏离 **0.6 pA**；真事件占位率 **0.98**、中位偏离 **70.8 pA**——两类分得很开。

**修复**：新增两个门控（默认开）——
- `burst_min_occupied_frac=0.30`：体内「确实阻孔」的样本占比过低 → 判为尖峰链丢弃；
- `burst_min_depth_frac=0.15`：占位率低但体内中位偏离 ≥ 0.15×步长 → 保留（浅而持续的阻孔状态）。
效果：该文件事件 1335→**517**，尖峰类 813→**6**；810–880 s 55→**28 个、全为真事件**（含 −16.5 pA 的浅持续态，靠深度条款保住）。

**注意**：清除伪事件后**序号会整体前移**（先前说的 #433 不再是原位置）；GUI 序号按当前检出顺序。

**测试**：`python -m pytest -q` → **159 passed**（新增 2 例：稀疏尖峰链不产生事件；持续阻孔通过门控）。

---

## [2026-10-19] burst 检测模式（驻留包络去抖）+ ignore 参数上提

**变更**
- `detect.py` 新增 `detect_events_burst`：阻孔指示器（|I−I0| > enter×step）→ 填空隙（< min_gap）→ 丢短块（< min_block）→ 每段一个事件；`cross_baseline` 让开孔两侧的偏离都算同一事件（多电平 / 上下穿越）。
- 新增 `detect(current, sr, lv, cfg, cutoff_hz, i0_profile)` 统一分派；`analyze` 与 `roi` 改走它。`event_mode="level"` 与旧 `detect_events` **逐字段一致**（有回归测试）。
- `config.py`：`event_mode` + `burst_enter_frac / burst_exit_frac / burst_min_gap_ms / burst_min_block_ms` + `burst_cross_baseline`，默认 `level`、burst 默认关。
- burst 用动态 I0(t) 作开孔参考（抗漂移）；`dynamic_i0` 模块语义不变（仅该模块开启时特征才用 I0）。
- CLI：`--event-mode`、`--burst-*`、`--burst-cross-baseline`。
- GUI：参数面板新增「检测模式」下拉 + 「驻留包络去抖」参数组（随模式显隐）；把此前隐藏的 `ignore_event_duration_ms` 上提为「事件合并容差 (ms)」，写清它与尖峰抑制的区别。
- `PLAN_burst_detection.md` 标为已实施。

**测试**：`python -m pytest -q` → **157 passed**（新增 `tests/test_detect_burst.py` 10 例：毛刺回落、越孔、长缺口切分、上下穿越、防过并、尖峰地板、边界、level 零回归、分派）。

**边界（重要）**：burst 假设**开孔电平稳定**。Ala（110↔180 慢孔态切换）实测 burst 78 vs level 37——动态 I0 设计上只跟「安静开孔窗」，不会跟到另一孔态，故另一态被读成长阻孔。此类文件继续用电平法；burst 用于开孔稳定、毛刺型/多电平的目标信号。

---

## [2026-10-19] 事件表加「序号」+ 尖峰抑制覆盖范围实测

**变更**
- 事件表与异常事件（剔除）表首列新增「序号」（1-based）：事件表按**原始检出顺序**编号，State 筛选后编号不变；剔除表按自身顺序。切片标题同步显示「事件 #N」。便于口头指代（「第 37 个事件」）。
- 序号是 GUI 显示列，导出表的列与顺序不变。

**尖峰抑制到底覆盖了什么（实测，1.5/5/20 ms 阻孔 + 长阻孔内 1/10/60 ms 回落 + 1 ms 越基线过冲）**
- 默认参数（`ignore_duration_ms=2` + `ignore_event_duration_ms=50`）：1 ms 回落、10 ms 回落、1 ms 越基线过冲都被吸收，长阻孔不切断；**60 ms** 回落仍会切成两个事件。
- 把桥接窗口压到 2 ms：10 ms 回落立刻导致切分 → 说明 2–50 ms 的缺口是**隐藏的** `ignore_event_duration_ms`（桥接）在兜，不是 `ignore_duration`。
- `ignore_duration` 提到 70 ms：连 60 ms 缺口也吞掉，但这是靠放大检测前抑制换来的，会连带改变检测语义、可能合并真实相邻事件。
- **结论**：短回落/穿越确实能保留，但功劳分属两个参数；> 50 ms 的缺口与多电平/持续跳跃仍未覆盖 → burst 检测仍有用，不能据此收工。

**测试**：`python -m pytest -q` → **147 passed**（新增 2 例：事件表序号稳定性、切片标题事件号）。

---

## [2026-10-19] 时长参数厘清 — ignore_duration vs min_toff；删一处死过滤

用户质疑 GUI 里「Ignore duration」与「最短 toff」是否重复。核查结论：**语义不同，但表述易混**；并发现一处真的代码重复。

**语义区别（实测：1.5 / 5 / 20 ms 三个阻孔）**
- `ignore_duration_ms`（检测**前**，游程层）：短偏离被吸收，**不产生事件**。设 2 ms → 1.5 ms 阻孔直接消失；设 6 ms → 5 ms 也没了。对应 Clampfit "Ignore short level changes"，还会吸收**长事件内部**的短槽。
- `min_toff_ms`（检测**后**，导出层）：已检出事件中 dwell ≤ 阈值的**剔除**，记 `toff<min`，仍可在剔除表追溯。设 10 ms → 只留 20 ms。

**变更**
- GUI 改名并加交叉说明 tooltip：「Ignore duration」→「**尖峰抑制 (ms)**」；「最短 toff (ms)」→「**最短事件时长 (ms)**」。README 参数表同步。不改行为。
- 删除 `compute_features` 内已无人调用的 `min_toff_ms` 过滤（features.py）：生产路径早已改走 `classify_exclusions`，该参数仅被一个 backward-compat 测试使用。`tests/test_features.py` 改为只断言「compute_features 不按时长过滤」。

**记录**：还有第三个时长参数 `ignore_event_duration_ms`（默认 50 ms，事件级 ignore，用于合并被短基线槽切碎的同电平事件）**未在 GUI 暴露**——它正是「毛刺型阻孔」的关键旋钮，宜与 burst 检测一起决定是否上提。

**测试**：`python -m pytest -q` → **145 passed**。

---

## [2026-10-19] GUI 布局重做 — 左表 / 中切片 / 点击联动（平移不改缩放）

参考 `深度信号分析/npsweep/gui.py`（其自身即「借鉴自本项目」，本轮把演进收回来）。

**变更**
- **布局**：左侧 = 事件表（上）+ 异常事件（剔除）表（下）；中间 = 主波形（上）+ **选中事件放大切片**（下，QSplitter）；右侧 = 参数 + 统计（散点/直方图保留）。
- 新增 `gui/sliceview.py`（放大切片：事件内时间轴 ms、起止虚线、开孔基准线、标题带 dwell/ΔI/Io/state）。
- 新增 `gui/excludedview.py`（剔除事件表：列含 `drop_reason`，顶部汇总「剔除事件 N：reason×count」；点行 → 主图聚焦该事件 + 切片）。
- `gui/waveview.py`：新增 `focus_event(t1, t2, zoom=False)` —— **平移跳转、缩放比例不变**（默认）；`zoom=True` 才自适应缩放。新增左键点击波形 → 按「到事件区间的距离」选中最近事件（发出 `bus.event_selected`）。移除了旧的 `focus(idx)`（会缩放）与 `focus_region()`。
- `gui/main_window.py`：重排 dock；工具栏新增「选中时自适应缩放」开关（默认关）；`bus.event_selected` 统一驱动 主图聚焦 + 切片 + 事件表/散点同步；剔除表走回调 `_show_row`。
- 删除 `gui/anomalyview.py`（异常**区间**列表）及其测试：该槽位按用户选择改为「剔除事件表」。异常区间仍以淡色带画在主波形上，区间明细仍在 `_events.xlsx` 的 anomalies sheet；`bus.region_selected` 随之移除。
- **行为变更**：选中事件默认**不再缩放**主图（此前是缩放到该事件），改为平移；需要缩放时开工具栏开关。

**测试**：`python -m pytest -q` → **145 passed**（删 4 例 anomaly 面板测试，新增 `tests/test_gui_eventnav.py` 6 例：平移不改缩放 / zoom 切换 / 点击选最近事件 / 切片 / 剔除表）。离屏冒烟确认主窗口结构（中心 QSplitter + 4 dock + 工具栏项）。

**遗留**：GUI 观感需人工过目（模型无视觉能力）。

---

## [2026-10-19] 功能模块化（mod 注册表）— 默认最小、可多选

**变更**
- 新增 `nanopore/mods.py`：`ModSpec` / `MODS` / `ORDER` / `resolve_mods`（补依赖、去重、拓扑排序）。7 个模块：`lowpass`、`dynamic_i0`、`anomaly`、`refined_anomaly`、`plots`、`dataset_export`、`summary`。**检测变体（`polarity` / 事件平台占比 / `ignore_*`）不做成模块**，仍留参数面板——它们改变底座「怎么检测」，与模块正交。
- `config.py`：新增 `enabled_mods`（空 = 仅底座）；删除被模块取代的 `anomaly_enabled` / `dynamic_i0_enabled` / `refined_anomaly_enabled`。旧 JSON 协议仍可读（未知键被丢弃）。
- 新增 `nanopore/analyze.py`：共享 `analyze(rec, cfg)`（底座 + 按 mods 编排）。`pipeline.process_file` 与 GUI `AnalysisWorker` 均改调它，**消除两处近乎重复的编排**（顺带修掉的真重复）。
- `pipeline.run_batch`：`dataset_all.csv` / `summary.xlsx` 仅在对应模块开启时写出；`plots` 同理。
- `cli.py`：新增 `--mods / --minimal / --all`；`--no-anomaly` 改为「从模块集去掉 anomaly」的别名。
- GUI `parampanel.py`：新增「模块（可多选）」组，含**方向感知的依赖联动**（勾子项自动补前置、取消前置级联取消后置）；模块参数分组成框、随开关显隐；用 `QSettings` **记住上次选择**（首次为默认=仅底座）。
- **行为变更**：默认从「全开」变为「仅底座」。需要旧行为用 `--all`（README 已醒目标注）。

**测试**：`python -m pytest -q` → **143 passed**（新增 `tests/test_mods.py` 18 例：注册表完整性、`resolve_mods`、config 前后兼容、`analyze` 编排、minimal/all 端到端产物、GUI 面板联动与依赖级联）。CLI 冒烟：`--minimal` 仅出 `_events.xlsx`，`--all` 出全产物。

**遗留**
- `anomaly` 模块的 `jump_min_ms` 等参数未在 GUI 暴露（走 JSON / CLI），后续按需补控件。
- GUI 未做视觉确认（模型无视觉能力）：模块面板与参数显隐需人工过目。
- burst 检测（`PLAN_burst_detection.md`）仍待做，按约定排在模块化之后。

---

## [2026-10-19] 工作区清理 + 模块化架构规划（burst 检测同为待办）

**变更（清理，仅本机忽略项与死符号）**
- 删除生成物：`build/`（含整包旧副本 `build/lib/nanopore/`，会让后续读者/agent 读到旧代码）、`nanopore_merged_lab.egg-info/`、`output/`、`__pycache__/`、`.pytest_cache/`。
- 删除调试草稿：`_preview_*.png`（8 张）、`_gen_preview.py`；同步移除 `.gitignore` 中这两条已失效的忽略项。
- 删除生产死符号：`detect.DetectionResult.start_times_s` / `end_times_s`（全仓库无人调用）、`anomaly.events_in_invalid_regions`（仅测试调用，生产走 `invalid_region_reasons`）；改写 `tests/test_anomaly.py` 该用例改测 `invalid_region_reasons`，删除 `tests/test_traceability.py` 中仅校验两函数等价的 `test_mask_matches_reasons`，修正两处 docstring 交叉引用。
- 保留（不入库的资料/草稿）：`goal.md`、`8a558a…png`、`Feature extraction code.m`、`人工常规数据处理方法.docx`。

**测试**：`python -m pytest -q` → **125 passed**（本机 pytest 在 anaconda `python`，`py -3.13` 无 pytest）。

**下一步（规划，未实施）**
- 模块化：把「阶段／产物」类功能（低通、动态 I0、宏/细粒度异常、输出图、合并表、批次汇总）做成**默认最小、可多选、记住上次选择**的 mod；检测变体（`polarity`／`event_mode`／毛刺门控）留参数面板。规格见 `PLAN_mods_architecture.md`。
- 驻留包络去抖检测（毛刺/多电平）：规格见 `PLAN_burst_detection.md`。

---

## [2026-10-09] 项目精简 — 删除未入库的先验层，收敛为单一 nanopore 包

**变更**
- **删除从未入库的「先验增强引擎」层**：`merged_runner.py` / `nanopore_launcher.pyw` / `启动纳米孔分析.bat`。三者都 `import nanopore_prior`，而该包自 `37b0356`（Add files via upload）起就未随代码入库，故 import 即 `ModuleNotFoundError`，且从无测试覆盖。功能上其 Tk 启动器的批处理（递归搜集 ABF、写 `summary.xlsx`/`dataset_all.csv`）已被 `nanopore` PyQt5 GUI 的「批量处理」对话框（`gui/batchdialog.py`）覆盖。
- **pyproject.toml**：删 `nanopore-prior` console 入口（指向不存在的 `nanopore_prior.cli`）与 `py-modules = ["merged_runner"]`；`nanopore-review` 更名 `nanopore`（对齐 CLAUDE.md/README 使用的 `nanopore run`）。
- **修复依赖声明与 CI 的隐性错配**：`pyabf`（`io.py` 读 ABF2 的入口）从 `[review]` extra 移入核心 `dependencies`；`PyQt5`/`pyqtgraph` 放入 `[dev]` 与新增 `[gui]` extra。此前 CI 的 `pip install -e ".[dev]"` 只装 pytest，**GUI 测试全部 `importorskip` 静默跳过**，而 CI 仍在装 Qt 系统库并设 `QT_QPA_PLATFORM=offscreen`——绿但没测到 GUI；README 的 `.[dev]` 也跑不了 GUI 与真实数据。
- **删除重复依赖清单**：`requirements.txt` / `requirements-dev.txt`（唯一消费者是被删的 bat，内容与 pyproject 重复）。
- **README**：删「统一入口」死章节（原指向必然报错的 `启动纳米孔分析.bat`），收敛为「入口」节（GUI 双击 + CLI）；仓库结构清单中的死文件一并移除。
- **保留的功能意图（信息不丢）**：先验层 Tk 界面描述了 `nanopore` 目前**没有**的四项功能——局部分析起止时间（随批处理生效的 ROI）、人工标定表、事件种类数期望、严格筛选（目标电流变化/SD）。若仍需要，后续在 `nanopore` 侧补 `--start/--end` 与 GUI 批处理 ROI。

**测试**
- `pytest` 126 passed（本地样例数据在）。删除均为死代码/死引用，未动 `nanopore/` 算法。
- `pip wheel . --no-deps` 构建通过（不再引用 `nanopore_prior` / `merged_runner`）。

**下一步**
- 若确认先验层四项功能仍需要，在 `nanopore` 侧实现（CLI `--start/--end` + GUI 批处理 ROI）。
- 恢复 v3 规划主线：C1（skew/kurt 有偏校正）→ C2/C3（GUI 真 bug）→ R1（内存）。

---

## [2026-09-25] 仓库更名 SDL-Auto-Data-process + CONTRIBUTING 改定位 + 隐私核查

**变更**
- 仓库更名 `Self-Driving-Huang-Lab` → **`SDL-Auto-Data-process`**（https://github.com/1moltry/SDL-Auto-Data-process）；仓库内 README / CONTRIBUTING / data/README / pyproject 的地址与目录名一并替换（另有本地 `CLAUDE.md` 同步，该文件不入库）。
- **署名落地**：`CONTRIBUTING.md` 顶部与 `LICENSE` 版权行写明本仓库由 **Yize Liu（1moltry）与 Junjie Wen 共同开发、Huang Lab 资助**；`pyproject.toml` 新增 `authors`。
- **`CONTRIBUTING.md` 改回贡献者指南**：只留贡献者需要的技术约定（环境准备 / 分支命名 / Conventional Commits / 提交前 `pytest` / PR 检查清单 / 不入库清单）；原写在其中的协作机制叙述归入本条目（见下）。
- 修正过时描述：`启动界面.bat` 早已改为走 PATH 的 `pythonw`（提交 `e9b72cf`），README 仍写「Anaconda 的 pythonw」，一并改正。
- **修复 CI 长红**：`pyproject.toml` 的 `packages` 引用了仓库里不存在的 `nanopore_prior`，`testpaths` 引用不存在的 `tests_prior`/`tests_merged`。CI 是干净 checkout，`pip install -e ".[dev]"` 直接报 `error: package directory 'nanopore_prior' does not exist`，**三个 job 自 2026-09-24 起全部失败**。本地看不出来是因为有早先装好的 `nanopore_sdl.egg-info` 残留，且 `pytest tests/` 只点名 `tests/`、靠 cwd 就能 import。去掉这两处悬空引用；同事的 `merged_runner.py` / 启动器原样不动（它们 import 不到 `nanopore_prior` 是另一回事，已在 README 标注该入口暂不可用）。

**协作机制（原 CONTRIBUTING「协作方式 / 评审与合并 / 版本号与发布」并入此处）**
- **提交路径**：fork → 在 fork 上建分支提交 → 向 `main` 开 PR（模板自带检查清单）→ 维护者审查，需改则继续 push 到同一分支 → squash 合并后删源分支；分支落后用 `git fetch upstream && git rebase upstream/main`。不要用网页 "Add files via upload"，会绕过分支与 CI。
- **为什么不靠服务端保护**：Free 套餐无法启用 `main` 分支保护 / ruleset（`403 Upgrade to GitHub Pro`），也**无法把协作者降为只读**（协作者权限接口对 `read`/`triage` 返回 `422`）。故用**权限**代替：仓库公开 + 贡献者不给写权限，从机制上禁止直推 `main`；维护者账号仍可直推（文档、发版）。升级 Pro 后应改为开启分支保护（要求 CI 通过 + 禁止强推）。
- **版本号由维护者分配**，贡献者不自行打 tag / 建 Release。版本线：`v1` → `42118fa`（命令行管线 + PyQt5 GUI）、`v2` → `37b0356`（整合版：先验增强引擎 + 统一启动器）；回退 `git checkout v1`。

**隐私核查（全量 `git ls-files` 69 文件 + 全量 `git log`）**
- **追踪文件无泄露**：无 `.abf` / `pCLAMP11.2/` / `_tmp/` / `*.docx` / `*.m`，无同事姓名串，`.claude/settings.local.json` 未追踪。
- **提交历史含个人邮箱**：`37b0356` 作者 `REFLECTED-MOON`（163 邮箱，local part 含 11 位数字）、`1bdee85` 为个人 outlook 地址。**决定不处理**——不改写历史、不强推。本机 `user.email` 已是 GitHub noreply 地址，后续提交不暴露个人邮箱。
- 泛化追踪文件里的本机绝对路径（DEVLOG 中的解释器路径与项目工作目录），改为通用表述。

**测试**
- 纯文档 / 元数据改动，未动 `nanopore/` 算法代码；`pytest` 126 passed。
- CI 修复的验证方式：用 `pip wheel . --no-deps --no-build-isolation` 复现出 `nanopore_prior` 缺失导致的 metadata 生成失败，改完后同一命令构建成功（不必等 CI 排队）。

**下一步**
- 未处理项：`nanopore_prior` 包仍未入库，统一入口（`merged_runner.py` / `nanopore_launcher.pyw` / `启动纳米孔分析.bat`）不可用；本次只修了打断 CI 的那两处打包悬空引用，`nanopore-prior` console 入口仍指向不存在的模块（未调用则无碍）。
- 恢复 v3 规划主线：**C1**（skew/kurt 有偏校正）→ C2/C3（GUI 真 bug）→ R1（内存）。

## [2026-09-24] 版本标记与协作流程 — v1/v2 标签 + Release + 仓库地址 + PR 流程

**变更**
- 建立版本线：标签 `v1` → `42118fa`（命令行管线 + PyQt5 GUI 里程碑）、`v2` → `37b0356`（同事经 GitHub 网页上传的整合版：统一启动器 + 先验引擎入口）。删除旧标签 `v0.1.0`（原指向同一提交 `42118fa`）。未改写提交历史。
- README 合并：以 v1 的完整文档为基底恢复，在开头并入统一入口（`启动纳米孔分析.bat`；「开始主分析」/「打开交互复核界面」双界面）与批处理产物说明。
- 仓库地址固化：README 顶部、`pyproject.toml` `[project.urls]`、本文件 `CLAUDE.md`。
- GitHub Release `v1` / `v2` 建立。
- 协作流程：`CONTRIBUTING.md` 新增「协作方式（贡献者必读）」（fork + PR 步骤）与「版本号与发布」（版本号由维护者统一分配，贡献者不自行打 tag）。Free 套餐下 ruleset / 分支保护不可用，且实测无法把协作者降为只读（API 对 `read`/`triage` 返回 422），故改为**仓库公开 + 移除协作者写权限**：贡献者只能 fork + PR，从机制上禁止直推 `main`。已在 Issue #3 通知同事。

**测试**
- 仅动文档与打包元数据，未改 `nanopore/` 算法代码。

**已知问题（v2 原样保留，未修复）**
- `nanopore_prior` 包未随同事提交入库，`merged_runner.py` / `nanopore_launcher.pyw` / `启动纳米孔分析.bat` 当前不可用。
- `pyproject.toml` 的 `packages` / `testpaths` 引用了不存在的 `nanopore_prior`、`tests_prior`、`tests_merged`。

**下一步**
- 补入 `nanopore_prior` 包与 `tests_prior`/`tests_merged`，或修正 `pyproject.toml` 与启动器路径，使统一入口可用。
- 统一 README「路线图」里的 v1/v2 口径与发布标签口径。

## [2026-09-20] 工程化 — 纳入版本控制 + GitHub 协作流程

**变更**
- 仓库初始化：`git init -b main`，首次提交 65 文件 / 0.34 MB。`.gitignore` 排除实验数据（`abf数据案例/` 1.7 GB，单文件最大 143 MB，超 GitHub 100 MB 硬限制）、商业软件（`pCLAMP11.2/`）、参考文本（`_tmp/`）、生成物与本机配置。
- 打包：新增 `pyproject.toml`（setuptools），声明依赖与 `requires-python = ">=3.11"`，console 入口 `nanopore`；pytest 配置自 `pytest.ini` 迁入并删除后者。
- CI：`.github/workflows/ci.yml`——ubuntu/windows × py3.11/3.13 三 job，`QT_QPA_PLATFORM=offscreen` 无头跑 pytest；`.github/dependabot.yml` 周更依赖（合成单 PR）。
- 协作：`CONTRIBUTING.md`（分支命名 / Conventional Commits / PR 检查清单）、PR 与 issue 模板、`data/README.md`（数据获取方式与目录约定）。
- 规整：`.gitattributes`（跨平台换行符，`.bat` 保持 CRLF）、`.editorconfig`。

**测试**
- 本地 126 passed（有头与 offscreen 两种模式）；`pip install -e ".[dev]"` 通过，`python -m nanopore --version` 与 GUI 主窗口构造均正常。
- GitHub Actions 三 job 全绿，其中 py3.11 验证了声明的最低版本准确。

**已知限制**
- Free 套餐的私有仓库不支持分支保护 / ruleset（API 返回 `403 Upgrade to GitHub Pro`），`main` 无服务端强制保护，流程靠 `CONTRIBUTING.md` 约定。

**下一步**
- 可选：升级 Pro 后启用 `main` 分支保护（要求三个 CI 检查通过 + 禁止强推），届时删掉 CONTRIBUTING 里的限制说明。
- 恢复 v3 规划主线：**C1**（skew/kurt 有偏校正，影响已有数据可信度）→ C2/C3（GUI 真 bug）→ R1（内存）。

---

## [2026-09-13] G1.10 — MATLAB 训练导出 + 散点图极值修复

**背景**：评估产物对 MATLAB 的适配性（拟用于机器学习训练），并修散点图被极端值撑爆显示范围的问题。

**评估结论：MATLAB 接入可行，三个坑**
- 列名 `%mean` 非法（MATLAB 标识符须字母开头），`readtable` 会静默改成 `x_mean`，按名取列会取错。
- `t1`/`t2` 单位与特征表规范不一致：本管线**秒**，特征表规范**毫秒**（`rate=0.04 ms`），差 1000 倍。
- 无跨文件合并表，`summary.xlsx` 只有每文件聚合行。

**变更**
- 新增 `analysis.build_combined_dataset` / `write_combined_dataset`，`run_batch` 末尾产出 `dataset_all.csv`（保留事件纵向拼接 + `source_file`，UTF-8 BOM）。**仅此表**规范化列名：`%mean`→`rel_mean`、`t1`/`t2`→`t1_s`/`t2_s`；`_events.xlsx` 保持规范列名不动。
- `plot_scatter`：改 2×2 布局（dwell/时间 × ΔI、dwell/时间 × Io）。toff 跨度 >1 个数量级时横轴转对数；**ΔI 纵轴保持线性并按正负分色**，全量保留事件。原 1×3 里 Io 靠色标表达，分色后须单独成面板，故扩为 2×2 免丢信息。建图逻辑拆出 `build_scatter_figure`，使"纵轴必须线性"成为可断言的性质。

**关键取舍（两次返工，均靠实测量化否决）**
- 纵轴裁剪先试 Tukey 围栏 → 真实数据灾难性失效（Ala 只剩 [69.8, 71.1]，裁掉 90% 事件）；再试 0.5/99.5 分位 → 有符号数据仍挤。
- **symlog 实测对 ΔI 有害**：signed 数据经 symlog 后主体只占纵轴 4–6%（enkephalin 4%、GYIK/SLR 6%），线性轴为 9–30%。根因是肽类 ΔI 呈"离散电平带 + 巨大间距"——enkephalin 主群 60–67 pA 仅 7 pA 宽，另有 4% 的簇在 −103 pA，symlog 反而放大这种压缩。
- 定为 **ΔI 线性轴 + 正负分色 + 保留全部事件**（用户确认远离主群的稀疏簇是真信号，不得裁掉）。

**测试**
- 新增 `tests/test_dataset_export.py`（14 项）：导出列名全为合法 MATLAB 标识符、拼接与 `source_file` 标注、空输入、CSV 往返；散点断言"ΔI 纵轴为 linear 且不裁掉任一真实电平"、正负分色、对数列判定。
- 肽类 8 样例（`--polarity both`）复核：y 轴全部 linear、x 轴全部 log、事件覆盖 100%；分色比例与负事件占比吻合（enkephalin 96/4、angiotensin III 43/57、SLR 99% 负）。
- `pytest` 126 passed。

**下一步**
- 散点/直方图观感需用户过目（模型无视觉能力）。

---

## [2026-09-13] G1.9 — 桌面快捷入口（双击启动 GUI）

**变更**
- 新增 `启动界面.bat`：切至脚本所在目录后用 `pythonw`（无控制台窗口）启动 `python -m nanopore gui`。最初写死本机某个 Anaconda 解释器的绝对路径——本机装有多套 Python 且 PyQt5 只在其中一套，裸 `python` 可能解析到错误解释器；2026-09-20 改为走 PATH 上的 `pythonw`（提交 `e9b72cf`），要求已 `pip install -e .`。
- 新增 `启动界面-调试.bat`：同款启动但保留控制台，用于排查静默失败（主启动器无控制台输出，这是它的唯一代价）。
- 桌面快捷方式 `SDL纳米孔分析.lnk` → `启动界面.bat`，工作目录取项目根目录，图标取 pythonw。

**测试**
- 实测双击链路 lnk → bat → pythonw：`Win32_Process` 确认 `pythonw.exe -m nanopore gui` 正常驻留后手动结束。
- 快捷方式回读校验：Target / WorkingDirectory / Icon 三项均正确指向、目标文件存在。

**下一步**
- 无。GUI 观感类项目仍需用户过目（模型无视觉能力）。

---

## [2026-09-11] P7 — ARNKRS 肽信号被误判为异常

**背景**：pore2 ARNKRS 2Mm 案例中，宏块探测器把 7×breakdown + 1×jitter + 2×blockage 全判为异常，实为分析物事件（深阻孔 0.4–4 s、干净平台、可逆回到开孔）。

**根因**：`detect_anomalies` 的包络取「≥2% 显著电平」的最远偏移。稀疏肽文件里所有离散电平占比都 <2%（ARNKRS 电平达 -105..+97 pA，占比 0.02%–0.35%），`sig_levels` 为空 → 回退 `outer = 8σ`（≈18 pA），包络塌缩，任何深阻孔都被判 breakdown/blockage。

**变更**（`anomaly.py`，只改上述回退分支）
- 无显著电平时，包络张到**全部离散电平**：`outer = max|level − open_pore|`。ARNKRS 包络 18→123 pA，而最深块均值仅 −97 pA → 0 异常。
- 有显著电平的文件仍走原路径，**零回归由构造保证**（改动只在 `else` 分支）。

**零回归证明**（25 实样 base vs fix 全量对照）
- 仅 2 文件变化：pore2（异常 10→0，kept 7→12）、TYR（breakdown×3 + blockage×1 → 0，kept 10→12）。
- 其余 23 文件 kept/anomalies 完全一致（Ala 37 / Asp 64 / Gln 6 / His 274 / mixture 203 / ACTH 585 …）。
- TYR 同样无显著电平、且电平表含伪深层（最高 432 pA，frac 0.0001）故被波及；其真炸膜 437.5–438.8 s 仍由细粒度 `membrane_rupture` 捕获，剔除不受影响；被去掉的 `blockage` 88.4–93.8 s（med 175.8 pA、IQR 1.8、可逆回到开孔）确为真事件。

**双向/多电平事件检测（显式开关）**
- pore2 深阻孔是分析物事件，但 `estimate_levels` 只在**两侧都有 ≥2% 显著电平**时才给 polarity=0；稀疏肽文件两侧电平占比都 <2% → 退化为单极性（+1），向下阻孔被 sign 门拒掉。
- 探测器本身已支持多电平（`body_dwells_near_level` 走 ±8 步电平网格），缺的只是方向。故**不自动改**（全局双向会大面积过检：SLR 242→1055、DQARNKR 131→811、CAD 7→283），改为新增 `PipelineConfig.polarity`（None=自动 / 1=向上 / −1=向下 / 0=双向），接通 pipeline、roi、CLI `--polarity {auto,up,down,both}`、GUI 参数面板下拉。
- 配套 `baseline.set_polarity()`：手动指定 ±1 时把 `level1` 挪到所选一侧——`detect_events` 的电平网格按 polarity 建、符号门却按 `sign(level1−level0)`，两者不一致时会判 0 个事件（"向下"对 pore2 实测如此）。
- **默认自动 = 现状，25 文件零回归。** pore2 切双向：raw 46→115、kept 12→37，深阻孔 1181.9 s(4050 ms, −80 pA)、522.6 s(2187 ms)、636.9 s(1700 ms)、193.8 s(548 ms) 等全部入表，且异常仍为 0。

**测试**
- `tests/test_anomaly.py` +2 例：稀疏肽干净阻孔不判异常（旧 8σ 回退判 breakdown、新张到电平 → 无）、超电平缺口的真炸膜仍判 breakdown（防过度抑制）。
- `tests/test_detect.py` +3 例：polarity 选边（up 2 / down 2 / both 4）、`set_polarity` 把 level1 挪到所选一侧、config 往返含 polarity 且默认 None。
- `pytest` 112 passed（原 107 + 5）。

---

## [2026-09-11] G1.8 — 统计面板可见性 + 时间轴单位

**问题**（用户截图：dwell 直方图空白）：① 直方图看不到柱子；② SD-|ΔI| 散点仅供参考，应统一颜色、无需聚类；③ 各图 x 轴单位硬跟 pyqtgraph SI 前缀，出现 "kms"/"ks"。

**变更**
- **根因①**：`pg.mkBrush(0.12, 0.47, 0.71, 0.85)` —— pyqtgraph 的 `mkBrush` 把 4 个 float 当「颜色+width」而非 RGBA 通道，静默产出 **alpha=0 全透明**笔刷：柱子已画但不可见。改为 int RGBA。同一 bug 使 waveview 的异常阴影 / Cursor 选区底色 / 定位高亮框**全部透明不可见**，一并改 int RGBA。
- ② 散点去掉按 `Io` 的 viridis 逐点着色，统一单色（保留点击回溯 idx 与选中高亮）。
- ③ 新增 `gui/units.py`：`auto_unit`（按跨度取 μs/ms/s/min）+ `TimeAxis`（数据仍以秒存放，仅刻度按所选单位映射，关闭 `autoSIPrefix`，避免 "ks"/"kms"）。统计面板与波形各加一个单位下拉框（自动/μs/ms/s/min）。1235 s 波形由 "ks"→"min"，25.5 s dwell 由 "kms"→"s"。

**测试**
- `tests/test_gui_units.py` 6 例（单位映射 / TimeAxis 取整刻度且无 SI 前缀 / 异常色不透明 / 波形轴随记录自适应 / 异常带可见）；`test_gui_scatter.py` +3 例（柱子渲染出着色像素·防透明笔刷回归 / 散点单色 / 单位自适应与手动覆盖）。
- `pytest` 107 passed（原 98 + 9）。

---

## [2026-09-11] P6 — TRP：毛刺误检 + 慢漂移/炸膜漏检

**背景**：TRP.abf（656 s，基线 ~116 pA）暴露两个问题——① 检出 717 个原始事件，91% 是毛刺（窄尖峰 2–4 ms/~54 pA 与高频闪烁 ~550 Hz）；② ~630 s 起基线漂移、654–656 s 炸膜，均未识别且段内事件被当作事件。

**变更**
- **A 事件稳定性门控（毛刺，默认关）**：`detect.py` 增 `plateau_min_frac` 与 `body_plateau_frac()` —— 事件体驻留**单一**电平（最近整数电平 ±0.5·step）的样本占比低于阈值即剔除。现有尖峰抑制只在「靠近**任意**电平」上做要求，闪烁时一半样本贴基线电平、一半贴事件电平，两边都算「靠近」故漏过；平台占比则能区分（TRP 事件中位数 0.53，TYR/pore2 真事件 1.00）。`config.event_plateau_min_frac`（默认 0=关）接通 pipeline/roi/gui-controller。
- **B 慢漂移/不稳定区间（新 kind `baseline_drift`，默认开）**：`anomaly.detect_artifact_segments` 用 `I0Profile.window_levels`（1 s 窗中值，**含非安静窗**——安静窗链会跟随漂移）聚合成 15 s 块中值，标注同时满足四条的末端区间：位移（≥5%·|锚点|）**且**不稳定（区间 IQR ≥3× 记录头 IQR）**且**渐进（块间跳变 ≤max(6 pA, 5%·|锚点|)）**且**持续不可逆（≥20 s、不回到位移带）。区间内事件剔除；IQR ≥4× 时尾部嵌套 `membrane_rupture`。`ArtifactConfig`/`config.refined_drift_*` 接通 pipeline；waveview/analysis 上色（棕）。
- **C GUI 参数说明**：`parampanel.py` 全部参数加 tooltip（含义/作用/何时调），新增「事件平台占比」「漂移位移阈值」「漂移不稳定阈值」控件与「启用慢漂移检测」勾选。

**关键取舍（实证驱动）**
- **漂移起点取稳健档（~630 s）而非 450 s**：450 s 处仅 +0.6 pA（0.2σ）、540 s +2 pA，与 DQARNKR 的良性漂移（123→140 pA、仍在出正常事件、IQR 1.7×）在统计上**不可分**（TRP 540–630 s IQR 1.5× vs DQARNKR 1.7×）。改用「位移 **且** 不稳定」双键后，TRP 尾部（位移 +40% / IQR 4.3×）可判、DQARNKR（位移但 IQR 1.7×）不判。
- **毛刺门控默认关**：单一标量无法既剔 TRP 毛刺又保住多电平/混合样文件（plateau<0.8 会连带砍 3,5-T2 97%、DQ混合样 88%、DQARNKR 73%、T3 80%）。故做成可调；TRP 手动开。
- 试过并**弃用**的判据（供后人避坑）：跨阈次数 ≥3（砍 T3 90%/SLR 100%）、体内 IQR/步长 >1（砍 3,5-T2 92%）、落回基线占比（TRP 只剔 32%）、跨阈间隔周期性 CV、波动中位数（Ala 误报 7 段、mixture 23 段）、动态基线跨度（DQARNKR/ACTH 比 TRP 还大）。

**测试**
- 新增 `tests/test_anomaly_drift.py` 4 例（渐变漂移+尾部不稳定 → 1 区间；稳定阶跃 / 瞬态回落 / 位移但不稳定 → 0）、`tests/test_detect_plateau.py` 3 例（平台阻孔存活、闪烁被门控剔除而默认关时不剔、默认=关口径一致）。
- `pytest` 98 passed（原 91 + 7）。
- **全 25 实样**：漂移器**只在 TRP 命中**（`baseline_drift` 630–656 s + 嵌套 `membrane_rupture` 652–656 s）；DQARNKR/TYR/SLR/GYIK/3,3-T2/ACTH/Ala/Asp/His/mixture 均 0。
- **零回归证明**：`refined_drift_enabled` on/off 对 Asp/Gln/His/mixture/pore2/T3/SLR/TYR/DQARNKR/ACTH 的 raw/kept 计数**完全一致**——改动只在 TRP 生效。TRP 全关口径 kept 318 = 改动前。
- TRP 参数效果：默认（门控关）raw 717 → kept 298（漂移剔 22，valid 96%）；门控 0.85 → raw 118 → kept 67。

**备注**：6 样例 kept 计数与 M5 旧表不同（His 373→286 raw/274 kept、mixture 235→207/203、Asp 93→72/64、Gln 7→6）系 **P4/P5 既有改动**（合并 burst + 反压语义），非本次；本次已用 drift on/off 对照证明零回归。T3 187 / SLR 242 / pore2 raw 46 与 P4 记录一致。

**下一步**
- TRP 在 GUI 人工过目：毛刺门控调到满意（0.85~0.95）、看棕色漂移色带与嵌套炸膜。
- 若要求识别 450–540 s 的弱漂移倾向，需另设计判据（弱漂移 vs 良性漂移在本特征集下不可分）。
- 短肽文件 pore2 的 `toff<min` 剔除（3 ms 事件）仍靠用户调 `min_toff_ms`。

---

---

## [2026-09-10] G1.7 — 直方图修复 + GUI 批量处理

**变更**
- **toff 直方图不可见（两处缺陷）**：
  1. log10 模式下 `AxisItem.setTicks` 传了扁平列表，pyqtgraph 要求在 `[[(pos, label), …]]` 层级里——格式错误时坐标轴绘制抛异常（实测直接段错误），整个柱状图不渲染；
  2. 线性模式固定 60 等分箱，而 toff 常跨 3 个数量级（Ala 15 ms–26 s），绝大多数事件挤进第 1 箱、其余箱高度几像素，视觉上等同无直方。
  改为：线性用平方根规则控制分箱数（`clip(ceil(2√n), 8, 60)`）；log 模式按十进位/半十进位分箱（跨度 ≤4 个数量级用 0.5），刻度只标整数十进位；柱状项加同色描边避免细柱丢像素。
- **GUI 批量处理**：工具栏新增「批量处理…」→ `gui/batchdialog.py`：多选 .abf 文件或选文件夹（递归搜集，tPAL 子目录结构可用）、选输出目录、后台线程跑 `run_batch`、逐文件进度 + 汇总日志。参数复用参数面板当前值（单一数据源）。`pipeline.run_batch` 增 `progress(i, total, name, report)` 回调。

**测试**
- 新增 4 例（tests/test_gui_scatter.py）：两种刻度下真实渲染 pass 且非空白（捕获坐标轴刻度格式错误）、分箱不退化（线性非零箱 ≥5、单箱占比 <50%；log ≥4 箱）、log 刻度为层级格式。
- 新增 5 例（tests/test_gui_batch.py）：文件/文件夹递归展开与去重、空选择不启动、真实文件失败不中断批次。
- `pytest` 91 passed。

**实样验证**
- 直方图：Ala 线 13 箱（原 60 箱挤 1 箱）、log 8 箱；TREFETSC 线 56 箱、log 4 箱；SLR 线 32 箱、log 6 箱，两种刻度均渲染出柱。
- 批量：offstage 跑 tPAL 目录（4 文件）→ 逐文件日志 + `summary.xlsx` 生成。

**下一步**
- tPAL 逐电压段独立电平/基线（第二轮）。
- 批量对话框可选：多线程并行、失败重试、按文件自定义 Label。

---

## [2026-09-10] P5 — 电压 protocol 段识别（tPAL 反压段误计为事件）

**变更**
- **电压来源补齐**：`io.py` 新增 `command_voltage`（ABF 头的命令电压波形，pyabf `sweepC` 按 sweep 拼接）与 `protocol_voltage`（有电压 ADC 用 ADC，否则用命令波形）。tPAL 这类只录电流通道、但带电压 protocol 的文件此前完全取不到电压，现在可直接读。
- **判据统一**：`anomaly.py` 反压判据由「电压 ≤ 固定负阈值」改为「偏离保持电平」——保持电平取电压轨迹中位数（主导电平=传感段），任何持续偏离（反压 / tPAL 排出段 / 0 mV 静息段，正负都算）记为 `reverse_voltage` 区间，切换处加瞬态保护窗（`ArtifactConfig.protocol_transient_ms`，默认 100 ms）。落在区间内的事件按 `drop_reason` 剔除。
- `pipeline.py` / `gui/controller.py` 改用 `rec.protocol_voltage`。
- 代码/文档里不再以「Clampfit 语义」作为依据（保留 pCLAMP 作对照查看器与文档来源）；`detect.py`/`baseline.py`/`config.py`/GUI 模块的相应注释已改写。

**测试**
- 新增 `tests/test_io_command_voltage.py` 3 例：命令波形从 ABF 头读出（无电压 ADC 时）、常压文件无 protocol、tPAL 排出段事件被剔除且保留表无任何事件与 protocol 区间重叠。
- 新增 `tests/test_anomaly_refined.py` 2 例：双极性 protocol（+100 保持 + −50 排出 + 0 静息）两段都被标记；保持电平取主导电平而非固定负轨。
- `pytest` 84 passed。

**实样验证**
- tPAL 四个文件：假事件（≈2s，median −230~−280 pA）全部移入 excluded；保留表 >1.5s 事件数 0。
- Ala/Asp/T3/ACTH/DQARNKR 等：真实反压段恢复完整（Ala 1 处、Asp 5 处、ACTH 8 处、DQARNKR 3 处 0 mV 段），电压 ADC 噪声 p95 ≤ 0.09 mV，5 mV 容差无误判。

**下一步**
- tPAL 第二阶段：逐电压段独立电平/基线，分别统计传感段产出（本轮只做段排除）。
- GUI 异常面板区分「电压 protocol 段」与「反压」两种展示语义。

---

## [2026-09-09] P4 — 事件过分割与电平漂移修复（T3 / angiotensin III / SLR）

**变更**
- **同电平合并（merged burst）**：`detect.py` 新增 `_bridge_same_level_events`——同电平、基线间隙 < `ignore_event_duration_ms`（默认 50 ms，新参数）的事件合并为一个，幅值按 dwell 加权。对齐 Clampfit "Ignore short level changes"（从事件电平忽略，p112 "merged all-level search"）。长平台被噪声槽切碎的模式（T3 平台段 86 → 1 个事件）由此修复；短肽事件不受影响（pore2 间隙为秒级）。
- **电平跟踪保护**：level0 只从「幅值在当前 level0 ±0.15 步长内」的基线段更新。SLR 基线上方的噪声群体（137–170 pA）曾把 level0 拉漂 26 pA，导致分类翻转「基线当事件、事件当基线」；修复后 SLR level0 全程稳定（117.3 → 118.9）。
- `config.py`/`pipeline.py`/`gui/controller.py`/`roi.py` 接通 `ignore_event_duration_ms`；`ignore_duration_ms`（2 ms）语义收窄为基线上下文的尖峰抑制。

**测试**
- 新增 4 例（tests/test_detect.py）：长平台+10ms 基线槽合并为 2 事件、3ms 短事件存活、上方噪声群体不拖动 level0、同电平跨噪槽合并（dwell 加权幅值）；更新 2 例适配 merged-burst 语义（test_amplitude_step…、test_baseline_i0 阻孔后间隙加宽至 80ms 保持独立事件）。
- `pytest` 79 passed。批次管线 6 文件全通过。
- 实样验证（25 个 .abf 全扫）：T3 1824→187、SLR 1166→242、angiotensin III 1901→1488；pore2 52→46；全部文件 level0 漂移 < 7 pA。

**下一步**
- T3/SLR 类型数据在 GUI 里人工过目一遍（理想化线应贴合平台）。
- 多电流平台/混合信号（进阶(1)）：T3 实测 4 个显著电平（120/14/188/214 pA），当前单事件电平搜索的局限仍在路线图上。
- GUI 参数面板暴露 `ignore_event_duration_ms`。

---

## [2026-09-09] G1.6 — 右侧统计面板改版（toff 直方图 + SD-|ΔI| 散点）

**变更**
- `scatterview.py` 重写：原「深度-dwell / 深度-时间」双散点 → **事件数量-toff（dwell time）直方图 + SD-|ΔI| 散点**（ΔI=|mean|，按 Io 着色）。直方图横轴**线性/log10 单选切换**（log10 与批处理 `_hist.png` 约定一致）；散点保留点击→波形跳转事件。dock 标题改「统计 (直方图/散点)」。
- `main_window.py` dock 标题同步。
- 测试基建修复：GUI 测试的 QApplication fixture 改 **session 级**——原 module 级在模块结束时销毁 QApplication，连带删掉模块级单例 `bus` 的 C++ 对象，跨文件连跑 GUI 测试会 `RuntimeError: wrapped C/C++ object has been deleted`。

**测试**
- 新增 `tests/test_gui_scatter.py` 4 例：直方图计数守恒（∑counts = 有效 toff 数）、线性/log10 切换改变分箱、散点点数 + 点击发 `event_selected` + 越界高亮不崩、空/None 数据不崩。
- `pytest` 75 passed（含修复后的 test_gui_anomaly 4 例）。
- offscreen 端到端：Ala.abf 加载 → 37 事件，直方图/切换/高亮全通过。

**下一步**
- 用户真机看直方图观感（分箱数/配色/切换按钮位置），按反馈迭代。
- G2（dwell 对数直方项已随本面板落地）：事件 Accept/Reject、电平标记拖动重搜。

---

## [2026-09-08] P3 — 判据实证修正（F1 炸膜电平门控 / F2 宏块 jitter 门控 / F3 基线锚定）

**变更**
- **F1 炸膜误报**：`anomaly.py` `detect_artifact_segments` 加 `event_levels` 入参 + `ArtifactConfig.rupture_level_frac_max`（默认 0.24）。炸膜判定在"宽 IQR + 内部噪声比"之上，叠加**电平结构门控**：候选炸膜（单窗级 + 区间级）样本贴近任一显著电平占比 ≥ 阈值 → 是密集离散事件团（肽爆发），非弥散炸膜。同步修：`consumed = broad` 改为覆盖确认的**整个炸膜区间**（含恢复尾），避免恢复尾误标 jitter。
- **F2 宏块 jitter 误报**：`detect_anomalies` 加 `jitter_level_frac_max`（默认 0.20）。候选 jitter 块样本贴近非基线显著电平占比 ≥ 阈值 → 离散事件团，非膜抖。
- **F3 基线锚定失败**：`baseline_i0.build_dynamic_baseline` 加 `anchor_level` 入参；贪心链锚点从"首个安静窗"改为**贴近开孔电平的安静窗**（`|median − anchor|` 最小），默认无 `anchor_level` 时保持原行为。`pipeline.py`/`gui/controller.py` 传 `lv.level0`。
- `config.py` 增 `refined_rupture_level_frac_max` / `refined_jitter_level_frac_max`。

**测试**
- 新增 `tests/test_anomaly_p3.py` 4 例：密集离散事件团不判炸膜、弥散炸膜保留（rupture 或 severe jitter）、宏块密集事件团不判 jitter、动态基线锚到开孔而非首安静窗。
- `pytest` 71 passed。

**实样验收（全 27 文件快照，P3 后）**
| 指标 | 修正前 | 修正后 |
|---|---|---|
| angio | rupture×2 误剔 84 事件，kept 671 | rupture×0，kept 698 |
| REFEFTRC | rupture×7 | rupture×1（98s，span_lvl 0.23 弥散真段） |
| DQARNKR / 3,5-T2 | rupture×1 | rupture×0 |
| enkephalin | jitter×70 丢 77 事件，kept 201 | jitter×0，kept 274 |
| ACTH / TRP | jitter×28 / ×8 | jitter×0 |
| Asp `membrane_rupture` | @850.6s（level_frac 0.16）| **保留**（真炸膜） |
| T3 / TREFETSC / EFEFEC | Io_med 212 / -1 / 208（锚错）| Io_med 117 / 189 / 116（回真实开孔） |
| 6 样例回归 | — | Ala 37 / Asp 65 / Gln 7 / His 340 / mixture 223 / ARNKRS 11 不变 |

**待用户过目（计划风险项）**：T3 [364.4–367.8]s（level_frac 0.16，弥散 → 判炸膜，剔 91 事件）、TYR [437.5–438.8]s、GSH [547.6–561.5]s（13.9s 长段）真值需实验室确认。

**下一步**
- 用户核对待定炸膜区间判定表；如需对照 Clampfit 再定。
- 事件内异常平台（3b）、tPAL protocol 循环解析、Template matching、G2 其余 —— 仍按计划后置。


---

## [2026-09-08] P2 — M4 Cursor 局部分析（电压通道与细粒度异常里程碑 4/4 完成）

**变更**
- 新增 `nanopore/roi.py`：`analyze_roi(current, sr, start_s, end_s, cfg)` —— 对子区间用**独立** `estimate_levels → detect_events → compute_features`（不继承全记录电平游标，口径与全记录一致）；事件时间偏移回绝对坐标；ROI 内跳过异常检测（区间小、统计不稳）；区间 < 0.5s 抛错。
- `gui/waveview.py`：新增可拖拽 `LinearRegionItem`（Cursor 选区）+ `Cursor 选区 / 对区间重跑 / 清除选区` 三个按钮；ROI 结果以绿色方波叠加；`toggle_roi/clear_roi/_run_roi`。
- `gui/controller.py`：新增 `RoiWorker`（QThread）+ `rerun_roi(start_s, end_s)`（经 `bus.roi_rerun`/`roi_finished` 触发与回传），存储 `roi_df`/`roi_span`。
- `gui/bus.py`：加 `roi_rerun` / `roi_finished` 信号。

**测试**
- 新增 `tests/test_cursor.py` 5 例：ROI 事件绝对时间、避开阻塞段 ROI 事件数=真值、ROI 落在阻塞段内不产清洁事件、独立电平不继承记录游标、<0.5s 抛错。
- `pytest` 67 passed。
- GUI offscreen 端到端：Gln 载入 → Cursor 选区创建 → roi_rerun [1,12]s → 局部 4 事件 + 绿色方波叠加 → 清除选区复位，全程无崩。

**下一步**
- P3：判据实证修正——炸膜电平结构门控（F1）、宏块 jitter 事件团门控（F2）、动态基线锚定 anchor_level（F3）。


---

## [2026-09-08] P1 — 剔除可追溯 + 参数接通（后续三轨道之一）

**变更**
- `anomaly.py`：新增 `invalid_region_reasons()` 返回每个事件命中的 kind（`baseline_step` 不产生原因）；`events_in_invalid_regions()` 改基于它实现（行为不变）。
- `features.py`：`compute_features` 的 `min_toff_ms` 默认改 `None`（不再内部过滤）；新增 `classify_exclusions(df, regions, min_toff_ms)` 统一标注 `drop_reason`（`""`/`toff<min`/异常 kind 逗号连接）并拆分 kept/excluded，供 CLI 与 GUI 共用。删死变量 `after_n`。
- `pipeline.py`：全量特征表 → `classify_exclusions` 拆分；xlsx 新增 **excluded sheet**；`FileReport`/`summary` 增 `removed`（分原因计数）。
- `config.py`：删死字段 `min_event_ms`（GUI「最短事件」原不生效）与 `baseline_jump_pA`；`jump_min_ms`/`noise_sigma_mult`/`jitter_min_ms` 改为真正接入 `detect_anomalies` 调用；新增 `min_toff_ms`（默认 10.0，仅此字段是导出过滤阈值）。
- `gui/parampanel.py`：「最短事件」改「最短 toff (ms)」并接 `min_toff_ms`。
- `gui/`：新增 `anomalyview.py` 异常/剔除面板（kind/起止/剔除数/detail，点击→波形跳转该区间，`bus.region_selected`）；状态栏显示 `保留 N / 剔除 M`。

**测试**
- 新增 `tests/test_traceability.py`（原因归属、多区域重叠连接、mask 与 reasons 一致、config round-trip 含 min_toff、旧 JSON 兼容删字段、classify_exclusions 组合剔除）。
- 新增 `tests/test_gui_anomaly.py`（offscreen：异常面板行数=region 数、每区剔除数、summary 文本）。
- `pytest` 62 passed。
- 6 原始样例回归 kept 与 DEVLOG 一致：Ala 37 / Asp 65 / Gln 7 / His 340 / mixture 223 / ARNKRS 11。
- `process_file` xlsx 三 sheet（events/excluded/anomalies）实证；GUI offscreen 端到端（Gln 7 事件、26 region）不崩。

**已知取舍**
- `min_toff_ms` 是导出过滤阈值（toff < 该值被剔除并计入 `toff<min`）；ARNKRS 短肽默认 10ms 仍剔 35（11 kept），放宽到 2ms → 52/52 kept，参数现可在 GUI/CLI 调。
- 宏块 `jump_min_ms`/`noise_sigma_mult`/`jitter_min_ms` 接入后默认值与旧硬编码一致，6 样例宏块判定不变。

**下一步**
- P2：M4 Cursor 局部分析（ROI 区间重跑）。
- P3：判据实证修正——炸膜电平结构门控（F1）、宏块 jitter 事件团门控（F2）、动态基线锚定 anchor_level（F3）；配套合成测试 + case2 实样对比。


## [2026-09-06] M3 — 异常精筛（自发/人工反压恢复 + 分级膜抖 + 炸膜；里程碑 3/4）

**变更**
- `anomaly.py` 新增细粒度探测器 `detect_artifact_segments()`（逐窗 robust 噪声分级判据）＋ `ArtifactConfig` 阈值；新增 `merge_anomaly_results()` 将宏块包络探测器 + 细粒度探测器取并集。
- 新 region kind：`reverse_voltage`（电压列 ≤ -5mV，需 M1 voltage）、`membrane_rupture`（炸膜状态机：≥2 连宽IQR窗 + ≥5 静窗恢复 + relapse 确认）、`membrane_jitter_mild/severe`（逐窗 robust noise 分级）、`blockage_spontaneous/manual_recovery`（长偏差 + 内部不规则双判据，重叠反压段 → manual）。`baseline_step` 在合并时不再计入无效（孔态边界仍有效数据）。
- 关键判据修正（在真实样例上校准）：
  ① **振荡门控**：jitter 需 高噪声 AND 一阶差分符号翻转频繁（`jitter_osc_floor=0.45`）。ARNKRS 密集肽事件团噪声高但符号翻转稀（0.2-0.3）→ 不再误标膜抖；纯高频噪声翻转 ~0.6 → 正确抓。
  ② **炸膜双条件**：宽 IQR AND 内部噪声比≥2（`rupture_noise_min_ratio`）。电压协议段干净的宽 IQR 阶跃（noise_ratio~1.0，tPAL 65 处、mixture 930s）不再误判炸膜；Asp 末端炸膜(850.6s, nr~3) 正确保留。
- config 增 refined_* 阈值（`refined_anomaly_enabled` 默认开）；pipeline/GUI 主路径先建动态 I0 + 电压，再合并两类探测器剔除受影响事件。GUI waveview 色带 / analysis overview 按新 kind 上色（蓝=反压/人工、红=炸膜/breakdown、紫=抖、橙=自发阻孔）。

**测试**
- 新增 tests/test_anomaly_refined.py 7 例：自发阻孔恢复、阻孔+反压段重叠→manual、纯高频膜抖 σ12→severe / σ4→mild（均值贴开孔，宏块探测器漏）、炸膜状态机（σ60 3s → rupture）、无电压降级全 spontaneous、干净信号零误报。
- `pytest` 49 passed。
- 6 原始样例 refined 标注与 说明.txt 对照：Ala/Asp/His/mixture `reverse_voltage`（Asp×5、余×1）与人工反压位置一致；Asp 末端 `membrane_rupture` @850.6s（文件 854s）；Gln/ARNKRS 无误标。事件计数回归：Ala 37/Gln 7/mixture 223/His 340/ARNKRS 11（=M2，无误删），Asp 66→65（剔 1 个反压区事件）。
- 新案例：tPAL EFEFEC 假炸膜 65→0、事件 312→798（valid 54→100%）；甲状腺 T3 正常。

**下一步**
- 事件内异常平台标注（用户选择后置里程碑，避免与 detect Clampfit 事件边界冲突）。
- M4：GUI Cursor 局部分析（独立）。

---

## [2026-09-06] M2 — 动态 I0(t) 开孔电流基线（里程碑 2/4）

**变更**
- 新增 `nanopore/baseline_i0.py`：`build_dynamic_baseline(current, fs, ...)` → `I0Profile(baseline, noise, reference_noise)`。只从"安静窗"（1s 逐窗：low first-difference noise + low intra-window drift）建开孔基线，窗间贪心连锁 + median_filter + 逐样本插值。实测**深阻孔段(2-8s)期间基线保持开孔电平、不跟随阻孔平台**。
  - 关键修复：贪心连锁初版用 EMA（0.8/0.2）预测，会滞后稳定漂移、数窗后落后 >6pA 而误拒整条慢漂移；改用"最后接受窗的 median"做比较，慢漂移逐步跟随、骤跳平台（单窗 >max_step）仍被拒。
- `features.compute_features` 增 `i0_profile` 可选入参：传入时逐事件 `Io` = 该事件窗口内 profile.baseline 的 median（免疫紧邻前一个长阻孔被误当开孔、深度低估）；不传则回退到「前/后窗均值取大 + `dr_pA` 钳制」的路径。模块 docstring 区分 **I0（记录级）** 与 **Io（逐事件动态）**。
- `PipelineConfig` 增 `dynamic_i0_enabled=True`；pipeline.py / GUI controller.py 主路径默认建 profile 传入（默认开启）。
- `tests/synth.py` 未改；新测试 `tests/test_baseline_i0.py` 5 例：长阻孔期间基线保持开孔、事件体不成为 I0 窗、慢漂移被动态基线跟随（96→84）、100/150 平台切换事件 Io 取本平台 100、阻孔后事件深度真值。

**测试**
- `pytest` 42 passed（原 37 +5）；新增 abf数据案例2 四类案例批跑不崩：肽 enkephalin 356→201、生物胺 CAD 12→5、甲状腺 T3 1824→1684、tPAL EFEFEC 871→799，Io 分布合理。
- 6 原始样例回归计数与 DEVLOG 一致（223/37/66/7/340/11 kept），M2 不改检测只改特征 Io。
- GUI offscreen Gln → 7 事件、Io med 110.9。

**下一步**
- M3：电压列接入异常判据区分 spontaneous/manual 恢复 + 纯膜抖分级（依赖 M1 voltage + M2 I0(t)/ref_noise）+ 炸膜状态机 + 事件内平台标记。
- 备注：生物胺（贴近基线、短 dwell）当前参数召回偏低（CAD 5 事件），属检测层课题，非 M2 范围。

---

## [2026-09-06] M1 — io 电压通道读取（里程碑 1/4）

**变更**
- 设计结论：本项目的 Clampfit 语义对齐 + 合成信号回归是优势，保留；在此基础上补充三点——① 电压通道（判"人为反向电压后恢复"阻孔）、② 动态 I0(t) 基线（免疫阻孔延续段污染开孔电流）、③ 逐窗 robust 噪声分级异常判据（抓纯膜抖）。分 4 里程碑实施，见 DEVLOG 末尾《电压通道与细粒度异常规划》。
- io.py 扩展（本里程碑）：`AbfRecording` 增 `data`(n×ch)、`current_channel`、`voltage`、`voltage_channel`；pyabf 与 float-ABF1 两条读取路径均按单位自动选电压通道（含"mv"）；`read_abf` 默认 channel=0、返回 voltage 不变。实测 6 样例全部 2 通道（IN0=pA / IN1=mV），电压成功读出：Ala/Asp/His/mixture 含 ±100mV 反压段，Gln/ARNKRS 恒 +100mV。
- `_is_current_unit` 未用删除。

**测试**
- 新增 tests/test_io_voltage.py 3 例：双通道样例暴露 voltage 且与 current 长度一致、Ala 反压段可检出（负段>1s）、Gln 恒压无反压。
- `pytest` 37 passed（原 34 +3）；GUI offscreen 载入 Gln→7 事件、rec.voltage 就位、不崩。

**下一步**
- M2：动态 I0(t) 基线（baseline_i0.py，安静段贪心连锁判据）→ features 逐事件 Io 改取动态基线，免疫阻孔漂移。
- M3：电压列接入异常判据区分 spontaneous/manual 恢复 + 纯膜抖分级（依赖 M1 的 voltage）。

---

## [2026-09-06] float-ABF1 读取健壮化

**变更**
- `io.read_abf` 改为**主动嗅探文件签名**分发：ABF1+float 直接走内建读取器，不再依赖 pyabf 抛错字符串；ABF2/int-ABF1 仍交 pyabf。
- 内建 float-ABF1 读取器补全：从 header 读真实通道名/单位（sADCChannelName/sADCUnits 经 nADCSamplingSeq 映射，单/多通道均正确，如 muscle.abf 4 通道各自 mV/V/cmH2O/mmHg）；`units` 不再硬编码 pA。
- 读取容错：`acq_len` 与文件大小校验（截断报 "corrupt or truncated"）、非 ABF 文件报签名错误、channel 越界报错；补 `nNumPointsIgnored` 与 `nOperationMode` 语义；pyabf 路径的 ABF1 定宽字符串剥 NUL、operation_mode 映射为可读文本。
- README 同步：io.py 职责与"签名嗅探分发"说明。

**测试**
- `pytest` 34 passed（io 新增 5：真实单位 kchann/VMTestA/ecg、muscle 多通道逐通道单位与越界、签名嗅探分发、截断文件诊断、非 ABF 诊断）。
- pCLAMP 全树 50 个 .abf（含 30 float ABF1、4 通道 muscle.abf）读取全部成功、元数据无 NUL 泄漏；GUI offscreen 载入 kchann.abf → 47 事件正常。

**下一步**
- 非 pA 通道（mV/电压类样例）进管线仍无分析意义，属样例语义；GUI 默认 channel 0 未变。如需自动挑"电流通道"再议。

---

## [2026-09-06] 视觉简化 + 尖峰抑制 + pCLAMP 样例接入

**变更**
- GUI 波形（waveview.py）删灰底包络带 / 绿红电平线 / 黄 baseline_step 色带；只保留深色轨迹 + 蓝色理想化事件方波（白底）。analysis.py overview 同步简化（只画硬异常 breakdown/blockage/jitter 淡色带）。黄色竖线=旧 baseline_step 标记，已去掉。
- 事件检测加尖峰抑制（参照 Clampfit"事件 body 须驻留在某电平"语义）：
  - 极性过滤：单极性搜索时方向相反的 excursion 不算事件；
  - dwell-near-level：trimmed body ≥30% 样本（`dwell_min_frac`）须落在某整数电平邻域（≤8 倍步长，对应 Clampfit 最多 8 个 level）。巨峰（mixture 26L/Ala 45L）与反极性尖峰被清。
- `io.read_abf` 内建 float-ABF1 回退读取（pyabf 拒绝 float；pCLAMP Sample Data 多为 float ABF1）。
- eventtable 缓存行索引、baseline 聚类权重修正、detect 空 sel 回退（见前）。

**测试**
- `pytest` 29 passed（新增 spike 回归 3 + io 3：合成巨峰/反极性尖峰拒绝、0.65 深度亚电平保留；kchann float 读取+检测）。
- pCLAMP Sample Data 35 文件 + Sample Macros 15 文件全部跑通不崩。
- lab 6 样例批处理数与 DEVLOG 验收一致。

**关键取舍 / 已知差异**
- ARNKRS 批处理 52→11 与 DEVLOG 记录的 237→186 不符：ARNKRS 是短肽信号，多数事件 dwell<10ms 被默认 `min_toff_ms=10` 过滤。非本次 spike 过滤引入，是 toff 过滤既有行为；如需短肽事件保留，需放宽 min_toff。
- singles.abf（pCLAMP）事件 dwell 8.6ms，同样被 toff>10 过滤 → 0 kept。属样例/参数语义差异。

**下一步**
- 用户真机跑 GUI 确认观感；ARNKRS 短肽是否要单独调 min_toff 参数。
- G2 待办：电平拖动重搜、Cursors、Accept/Reject、dwell 对数直方。

---

## [2026-09-05] Review 修复 + 可视化语义收尾

**变更**
- 加"视觉调用规则"：模型看图前先确认视觉能力；单次 ≤3 张图。
- waveview 事件方波改用每事件 `Io`（= 局部开孔电流）作基线参考，段间 NaN 分隔；Ala/Asp 这类慢态切换样例的方波不再"悬空"。
- 修 baseline 候选聚类权重 bug（原 `_level_weights` 用合并后新值当 key 查旧权重，永远拿不到，prev_w 永远 = 1.0）；改为 value/weight 平行 list。
- 修 detect.run_amplitude 空 sel 分支的语义不清 fallback（`seg[argmax(a)]` → `seg_body.mean()`）。
- eventtable 缓存 `self._rows`，避免 `data()` 每次 np.flatnonzero。

**关键取舍（来自用户）**
- **"非开孔即事件"**：现实人工看图只找开孔电流 + 抖动基线；其余形态（平台、漂移、慢态切换等）全部识别为事件。当前管线自动模式选"离基线最近的显著电平"作 level1，与该原则方向一致；但 baseline_step 区间里**另一态的事件**会被算作基线，这一局限保留到 v2 多电平检测再解。

**测试**
- `pytest` 23 passed。
- offscreen GUI 预览（Ala）重新生成成功。

**下一步**
- 用户真机跑 `python -m nanopore gui "abf数据案例/abf数据案例/Ala.abf"` 看白底 + 全信号 + 事件方波是否符合 Clampfit 观感。
- G2 待办：电平标记拖动→重搜、Cursors 区间测量、事件 Accept/Reject、dwell 对数直方。

---

## [2026-09-05] G1 — 交互式 GUI（PyQt5 + pyqtgraph）

**变更**
- 新增 `nanopore/gui/` 包与 `python -m nanopore gui [file]` 入口（PyQt5 5.15.10 + pyqtgraph 0.14.0）。
- `bus.py` 跨视图事件选择信号（Clampfit 的"视图互联"）；`controller.py` 用 QThread 后台跑检测（复用 read_abf/estimate_levels/detect/anomaly/features，不改算法），大文件不卡 UI。
- `waveview.py`：波形浏览（滚轮缩放/拖动平移/自动缩放），可见窗口内样本 ≤ 40 万用原始点、否则分块均值降采样；叠加事件指示线（Io+mean 绝对位置）+ level0/level1 电平线 + 异常色带（红=breakdown 橙=blockage 紫=jitter 黄=state_step）+ 选中事件高亮聚焦。
- `scatterview.py`：深度-dwell（log x）与时间-深度散点，按 Io 着色；**点击散点 → 波形跳转该事件**。
- `eventtable.py`：20 列结果表，按 State（all/A/B）过滤，行点击/选中联动。
- `parampanel.py`：ignore_duration/pre_event/level_contribution/低通/最短事件/Io 容差/anomaly 开关/手动 Level0/Level1/Label，改参数重跑，存/读 JSON 协议（≡ Clampfit .spf）。
- `main_window.py`：QMainWindow + dockable 面板（中央波形/左事件/右散点/右参数）+ 工具栏（打开/重跑/全览）；cli.py 增加 `gui` 子命令。

**测试**
- offscreen 端到端冒烟：Gln 加载 → 7 事件 / 26 baseline_step 与 batch 一致；选中事件 x 轴正确缩放到该事件（t1=9.61→t2=10.47 包住）；事件表选中 + State=B 过滤为 0 行（Gln 全 A，正确）。
- `pytest` 23 passed（GUI 不改算法）。
- 说明：模型无视觉能力，界面观感（配色/布局）未经视觉确认，结构已保证，待用户运行截图/过目。

**下一步**
- 用户在真机运行 `python -m nanopore gui` 体验，反馈交互/观感后迭代。
- G2：电平标记拖动→重搜、Cursors 区间测量、事件 Accept/Reject/Suppress 状态分类、dwell 对数直方。
- G3：指数 PDF 拟合、P(open)/burst、多文件对比。

---

## [2026-09-04] M0 — 可行性评估 + harness

- 确认 pCLAMP11.2 商业闭源不可改，走 Python 独立管线（pyabf 直读 .abf）。
- 整理 Clampfit Single-channel Search 算法语义至 `_tmp/chm_clampfit/` 与 `_tmp/pclamp_*.txt`（本地参考，不入库）。
- 搭骨架：nanopore 包（io/preprocess/config/cli/`__main__`）+ README + DEVLOG + pytest + 合成信号生成器 `tests/synth.py`。
- 环境：Python 3.13.5；numpy/scipy/pandas/matplotlib/seaborn/openpyxl/pyabf 2.3.8。

## M1+M2 — 读取/滤波 + 事件检测核心

- io.py 读 ABF2（25kHz/pA，sweepCount>1 拼接）；preprocess.py 零相位 Bessel 低通。
- baseline.py 自动电平估计：全点幅值直方图 → 基线峰/基线区 → 高斯尾部显著性 → 候选聚类 → level0/level1 + 极性。
- detect.py 实现单通道搜索：最近电平归属 → run-length → Ignore duration 吸收合并 → 流式电平更新（10% 贡献、短事件降权）→ 滤波端点剔除(2τ) 与 brief(<4τ) → 首尾事件忽略；逐事件开孔电流 = 前一基线 run 末尾 pre_event_ms 均值（天然跟随漂移）。
- 6 样例特性化完成；30M 样本读 6s/估 1.4s/检 1.2s，性能可接受。

## M3 — 特征提取

- features.py 实现 17 项特征 + 新增 ton/Io/state，列名与特征表规范完全对齐：mean/%mean/std/skew/kurt/toff/Label/I0/t1/t2/MAD/CV/q1/q2/q3/iqr/outlier_ratio + ton/Io/state。
- 3σ 去毛刺、toff/ton 单位 ms、导出过滤 toff>10ms；Io= max(前窗,后窗) 均值，逐事件漂移参考。

## M4 — 异常检测

- anomaly.py：100ms 宏块统计（成本与记录长度无关）→ breakdown（出包络+极值持续）/ blockage（出包络持续≥3块，排除 ms 级深事件）/ baseline_step（状态切换边界，标记不判无效）/ jitter（块噪声超阈值且均值偏离）。
- 事件包络 = 显著电平（占比≥2%，排除开孔）最远距离 + 8σ。
- 6 样例校准：Ala 209.8s 反压、His 169s 炸膜、Asp 末端炸膜+5 组阻孔、Gln 抖动、mixture 深阻塞、ARNKRS 普通肽事件零误报。
- 关键取舍：2% 显著性 + 排除开孔 + blockage≥3 块的组合在 6 样例全部正确。

## M5 — 可视化 + 批次报告 + CLI 完整化

- pipeline.py 端到端编排（单文件异常不中断批次）；analysis.py 输出四件套：`_events.xlsx`（events+anomalies 双 sheet）、`_overview.png`、`_scatter.png`、`_hist.png`；批次 `summary.xlsx`。
- cli.py 完整化：--config/--label/--no-anomaly/--level0/--level1/--save-config。
- `baseline.py level1 选择规则修订（关键）`：显著电平（占比≥2%）中取**离基线最近者**为 level1（主导传感物种）。原"最远电平"规则在 Ala/mixture 上选中 -304 伪迹尾导致 0-1 事件。

**样例批处理**（默认参数）：

| 文件 | 事件(raw→kept) | 有效% | 异常 |
|---|---|---|---|
| ac-Thr+Thr | 235→223 | 99 | blockage×3 breakdown×1 |
| Ala | 44→37 | 100 | baseline_step×364 breakdown×1(209.8s反压) |
| Asp | 93→66 | 99 | baseline_step×546 breakdown×8 blockage×2 jitter×2 |
| Gln | 7→7 | 100 | baseline_step×26 |
| His | 373→340 | 99 | baseline_step×325 blockage×3 breakdown×1 |
| ARNKRS | 237→186 | 99 | breakdown×7 jitter×5 blockage×2 |

## [2026-09-04] M6 — v1 收尾验收

- 对照 说明.txt 逐文件核对 6 样例全部通过；特征表 20 列全齐，列名与特征表规范一致。
- README 双态孔说明/手动模式/参数对应表（含 pre_event_ms/Search Region）更新完毕；`_tmp` 调试脚本清理（保留帮助文档与用户指南的提取文本作算法参考，本地不入库）。

**已知限制（v1 范围外，待 v2）**
- 自动模式单事件电平：双向同时检测/多物种多平台需手动 `--level0/--level1` 或等 v2 多电平。
- Cursor 局部分析（Search Region=Cursors）、tPAL 多电压 protocol、近基线 Template matching 未实现。
- 图形观感未经视觉确认（模型无视觉能力），结构已保证，待用户过目。

**下一步（v2 排期）**
1. **GUI 交互看板**：波形浏览 + 事件列表 + 散点选点回溯原始事件波形 + 直方图 + 参数面板（对应进阶(4)）。
2. 多电流平台/混合信号自动多电平检测（进阶(1)(2)）。
3. 近基线 Template matching（Clements & Bekkers 1997，进阶(2)）。
4. tPAL 多电压 protocol+循环解析（进阶(3)）。
5. Cursor 局部分析（基础(5)）。

## 电压通道与细粒度异常规划（分 4 里程碑，逐段审批）

| 里程碑 | 内容 | 状态 |
|---|---|---|
| M1 | io 读入电压通道 + 通道自动选择（6 样例 2 通道） | ✅ 本日完成 |
| M2 | 动态 I0(t) 基线 → 逐事件 Io 免疫阻孔漂移（安静段贪心连锁判据） | ✅ 本日完成 |
| M3 | 异常精筛：voltage 判 spontaneous/manual 恢复 + 逐窗 robust 噪声分级抓纯膜抖 + 炸膜状态机 | ✅ 本日完成 |
| M4 | GUI Cursor 局部分析（独立） | ⬜ |

判据出处：`_tmp/chm_clampfit/`、`_tmp/pclamp_*.txt`（Clampfit 参考，本地资料不入库）；实现以实样数据 + tests/ 合成真值回归为依据。
