# DEVLOG — 开发日志

格式：`## [日期] 标题` + 变更 / 测试 / 下一步。只记里程碑与关键取舍，不记过程叙述。

> 产品更名说明：2026-10-22 起，本产品名为 **MOLTRACE（摩尔迹）**，仓库为 `MT-MolTrace`；下文历史记录保留旧名 SDL。更早的完整记录见 git 提交历史。

---

## 当前状态

- 版本 `v3.1.0`；当前分支 `chore/repo-slimming`。
- 底座：`level` / `burst` / `plateau` 三种检测器 + 20 列特征表；异常识别与各输出默认关闭，按模块开启。
- 统一指纹平台：阶段 1-5、7 完成；阶段 6（标注与评测闭环）待做。计划见 [`PLAN_fingerprint_platform.md`](PLAN_fingerprint_platform.md)。
- 测试：303 passed（快检 231 / GUI 58 / 集成 14）。
- 下一步：阶段 6——迁移 cutlab 标注纯逻辑、旧标注迁移与 event_map、区间 F1 报告与 GUI 复核；之后阶段 8 发行自测。

## 里程碑索引

| 日期 | 里程碑 | 结果 / 关键取舍 |
|------|--------|-----------------|
| 2026-10-25 | 阶段 7：实验性形状研究 | PELT/DTW/Fréchet/DBA/词表；实验性 GUI 与 CLI；null 与留一文件入口 |
| 2026-10-25 | 阶段 4-5：分段正确性与前后端联动 | 方向感知/整数边界/慢出孔修剪；classic 描述器；注册表驱动 GUI；多描述器 CLI |
| 2026-10-25 | 仓库精简 | DEVLOG 压缩；删除三份已实施 PLAN；清死代码与本地产物 |
| 2026-10-25 | 阶段 3：描述上下文与稳定身份 | 描述层改吃 `AnalysisResult`；`source_id` + `event_key`；指纹与 `.mat` 可互溯 |
| 2026-10-25 | 阶段 1-2：检测器目录与配置真值 | 检测器元数据集中到 `registry`；参数面板保留未暴露字段；异常与检测边界解耦 |
| 2026-10-22 | v3.1.0：事件指纹 | `dp_bic` / `scalar` 描述器；`describe` 模块默认关；numba 加速 |
| 2026-10-22 | v3.0.0 | 首页工作台、三检测器统一入口、算法对比、批量参数编辑 |
| 2026-10-22 | 算法审计 | 三项目检测器收敛；糖项目平台法成为唯一检测；描述层契约 |
| 2026-10-22 | 产品更名 MOLTRACE | 仓库迁至 `MT-MolTrace`；保留 QSettings 旧作用域 |
| 2026-10-22 | 发行包 v3.0.0 / v2.1 | PyInstaller 免安装包；独立干净 venv 控制体积 |
| 2026-10-21 | v2.1：首页 + 三算法整合 | 平台滞回成为第三种检测器；默认仍电平法 |
| 2026-10-21 | 用户向 README + tutorial | README 改为 Releases 下载路径；新增完整教程 |
| 2026-10-21 | burst 开孔判定与去抖顺序 | 按真正回到开孔的时间占比切分；先删碎片再填空隙 |
| 2026-10-21 | GUI 布局与交互 | 剔除表/统计图默认隐藏；模块分标签页；右键框选 |
| 2026-10-19 | 功能模块化 | 底座 + 可多选模块；默认仅底座；抽出 `analyze()` |
| 2026-10-19 | burst 检测 | 驻留包络去抖；占位率/深度门控；默认关 |
| 2026-10-19 | GUI 布局重做 | 左表 / 中切片 / 点击联动，平移不改缩放 |
| 2026-10-19 | 事件波形导出 | `waveform_export` 出 `.mat`，无余量，cell-of-structs |
| 2026-10-19 | 发行打包 | 干净源码树 + PyInstaller；DLL 补齐 |
| 2026-10-09 | 项目精简 | 删除未入库先验层，收敛单一 `nanopore` 包 |
| 2026-09-25 | 仓库更名与协作定位 | `CONTRIBUTING` 回归贡献者指南；修 CI 悬空包引用 |
| 2026-09-24 | 版本标记与协作流程 | `v1` / `v2` 标签；fork + PR；Free 套餐无分支保护 |
| 2026-09-20 | 工程化 | git / CI / pyproject / 模板 / 数据说明 |
| 2026-09-13 | G1.10 MATLAB 导出 | `dataset_all.csv` 合法列名；ΔI 线性轴 + 正负分色 |
| 2026-09-13 | G1.9 桌面入口 | bat + 快捷方式；后改为 PATH 上的 `pythonw` |
| 2026-09-11 | P7 稀疏肽误判 | 无显著电平时包络张到全部电平；新增 `polarity` |
| 2026-09-11 | G1.8 统计面板可见性 | 修 pyqtgraph 透明笔刷；时间轴单位自适应 |
| 2026-09-11 | P6 TRP 毛刺 + 漂移 | 平台占比门控默认关；`baseline_drift` 四条件 |
| 2026-09-10 | P5 电压 protocol | 命令电压波形；偏离保持电平即反压 |
| 2026-09-10 | G1.7 直方图 + 批量 | 平方根/十进制分箱；`batchdialog` |
| 2026-09-09 | P4 过分割修复 | 同电平合并 + level0 跟踪保护 |
| 2026-09-09 | G1.6 统计面板改版 | toff 直方图 + SD-|ΔI| 散点 |
| 2026-09-08 | P3 判据实证修正 | 炸膜/jitter 电平门控；基线锚定开孔 |
| 2026-09-08 | P2 Cursor 局部分析 | `roi.py` 独立电平重析 |
| 2026-09-08 | P1 剔除可追溯 | `drop_reason`；`classify_exclusions` |
| 2026-09-06 | M1-M3 电压 / 动态 I0 / 异常精筛 | 电压通道；`I0Profile`；分级异常 |
| 2026-09-06 | float-ABF1 读取 | 签名嗅探；内建读取器；真实单位 |
| 2026-09-06 | 视觉简化 + 尖峰抑制 | 白底蓝线；dwell-near-level |
| 2026-09-05 | G1 交互式 GUI | PyQt5 + pyqtgraph；QThread |
| 2026-09-04 | M0-M6 v1 | 独立 Python 管线；合成真值回归；6 样例验收 |

## 近期详细记录

### [2026-10-25] 阶段 7 自测包（v3.1.0，未发布）

**构建**：从提交 `f0cddd3` 的干净树构建 `release/MOLTRACE_v3.1.0_phase7_selftest_win64.zip`（162 MB zip / 391 MB 解压 / 1931 条目），SHA-256 `4803fd70b582cca20f7d8606b74021a6287007b5789aa4423f2c8fa8e4e20f1f`。构建 venv 含 `research` extra，PyInstaller hidden imports 已包含 `nanopore.fingerprint.research`、`ruptures`、`sklearn.cluster`。

**自测**：归档/PYZ 中确认存在全部 `nanopore.fingerprint.research.*` 模块、`ruptures.detection` 与 `sklearn.cluster`；冻结 GUI 离屏启动 8 s 未崩，带 `Ala.abf` 启动 20 s 未崩。研究功能的交互式语料/拟合/解码尚未在冻结包中人工点击，留待阶段 8 完整 GUI 验收。

**说明**：版本号暂未提升；自测包改名 `phase7_selftest` 以区别于正式 v3.1.0；未上传 Release。

---

### [2026-10-25] 阶段 7：实验性形状研究发现

**变更**
- 新增 `nanopore/fingerprint/research/`：`deps`、`curves`、`fragments`、`corpus`、`model`、`nulls`、`workflows`；迁入 PELT 变点、DTW、离散 Fréchet、DBA、变长形状词表与 N1/N2 null。
- 新增 `shape_vocab` 与 `pelt` 描述器，均标 `experimental`。`shape_vocab` 必须先在研究工作中拟合或加载词表；缺模型/缺依赖时引擎返回 `valid=False` 的可解释描述，不崩溃。
- `ShapeModel` 支持 JSON 保存/加载（中心、支持度、阈值、参数、来源、`gate_note`）。解码复用 `write_fingerprints`，输出带 `event_key`、`source_id`、全局采样与 manifest。
- GUI：首页新增「指纹研究（实验性）」入口；工作区含语料、词表缩略图、解码叠加三个页签；缺依赖时禁用拟合/解码并显示安装命令。
- CLI：新增 `research fit / decode / nulls`，拟合支持 `--nulls` 与 `--leave-one-file`。
- 依赖：`pyproject` 新增 `research` extra（ruptures / scikit-learn）并加入 `dev`；发行脚本加入 research 依赖与 hidden imports。

**状态**：实验性、默认关闭。旧词表 AUC 0.674（N1tele）/ 0.715（N2phase）低于 0.85 门槛；该事实保留在 `GATE_NOTE`、GUI 警告与导出 payload 中。真实 `GalNAc-1` 冒烟：6 事件 → 4 个中心，解码 3 个片段；GUI 与 CLI 均可跑通。

**测试**：303 passed（快检 231 / GUI 58 / 集成 14）；新增表示/距离、拟合与持久化、null/留一文件、GUI 工作区与真实数据冒烟测试。

**下一步**：阶段 6 标注与评测闭环（尚未做）；之后阶段 8 兼容、文档与发行自测，其中必须实测一次带 research 依赖的发行包。

---

### [2026-10-25] 阶段 4-5：分段正确性、classic 描述器与前后端联动

**变更**
- 分段：`edge_bounds` 方向感知（向下 p15 / 向上 p85 / 双向带状回孔）；边缘窗改毫秒（25/50 kHz 一致）；`Step` 记录整数起止，降采样余数并入最后一段；慢出孔尾部过渡段整体修剪；BIC 增加 `bic_n_eff` / `bic_penalty` 诊断（默认仍为源行为）。
- 描述器：新增 `classic` 双阈值滞回候选（beta）；`dp_bic` 版本升到 2 并改标 beta（已知过分割）；双向/多电平体带 `baseline_ambiguous` 质量标记。
- 评测：新增 `fingerprint/intervals.py`（全局区间、区间 F1、边界位移）；新增 `tests/test_annotation_eval_galnac.py`，用 12 事件 / 97 指纹冻结真值做集成回归。
- GUI：描述器下拉与参数表单由注册表生成；分段表支持并排比较；描述缓存/代次竞态修复；工具栏“导出指纹”；批量对话框显示检测器/描述器/异常状态并支持描述阶段取消；对比窗口复用纯比较函数并增加描述器指标。
- CLI：新增 `--describers`（首个写历史文件名，其余写 `_fingerprints_<id>`），保留 `--describe` / `--fp-param` 旧语义。
- 文档：README / tutorial / DEVELOPMENT 同步描述器、参数、导出与 CLI；PLAN 状态更新到阶段 6。

**关键数据**（GalNAc-1，12 事件 / 97 指纹，冻结事件表，仅评描述层）：`classic` 112 段，区间 F1@0.5 ms = 0.536（P 0.500 / R 0.577），边界位移 0.36 / 0.32 ms；`dp_bic` 195 段，F1 = 0.151；`dp_bic` + `bic_n_eff=-1` 33 段，F1 = 0.062。结论：`classic` 复现已发表基线；`dp_bic` 过分割是真实问题，BIC 自动修正不是解药；`snr_min` 0–50 的 F1 基本不变（0.151–0.154），≥100 召回骤降，默认保持 0。

**测试**：283 passed（快检 218 / GUI 53 / 集成 12）；`Ala.abf` 离屏冒烟通过（37 事件；切换描述器、并排比较、导出正常）。

**兼容**：旧 `--describe` / `--fp-param`、旧 Excel/JSON 列顺序与旧 `event_id` 语义不变；`dp_bic` 仅新增参数（`edge_win_ms`、`trim_exit_frac`、`bic_penalty`、`bic_n_eff`）与特性字段；额外描述器文件另名输出。

**下一步**：阶段 6——迁移 cutlab 标注纯逻辑、旧标注迁移与 `event_map`、区间 F1 报告与 GUI 复核。

---

### [2026-10-25] 仓库精简

**变更**
- 文档：`DEVLOG.md` 由 1,187 行压到 189 行，旧条目改为上方里程碑索引；删除三份已实施的 `PLAN_burst_detection.md`、`PLAN_mods_architecture.md`、`PLAN_event_pipeline.md`，设计要点已在 `DEVELOPMENT.md` 与 git 历史中；保留进行中的 `PLAN_fingerprint_platform.md`。
- 代码：删除 `ArtifactConfig.voltage_threshold_mV`、`steps.StepResult`、`steps._open_sigma`、`AbfRecording._auto_channel`，以及未使用的导入与局部变量。`nanopore/describe.py` 保留为迁移期兼容门面，阶段 4 后再评估删除。
- 本地：清理 `build/`、旧发行 zip、缓存、`goal.md` 与失效 PNG；`Feature extraction code.m` 移入 `_tmp/`。实验数据、`pCLAMP11.2/`、`_tmp/` 保留。

**测试**：249 passed（快检 194 / GUI 45 / 集成 10）。

**说明**：除根目录 `CLAUDE.md` 外，仓库文档不参与启动上下文；启动占用主要来自 MCP 工具定义，与本次精简无关。

---

### [2026-10-25] 阶段 3：描述上下文、稳定事件身份与导出溯源

**变更**
- 新增 `nanopore/fingerprint/`：`contracts`（事件身份、`EventView`、`Segment`、`EventDescription`、`RunManifest`、序列化）、`context`（从 `AnalysisResult` 建视图）、`registry`（描述器注册与成熟度）、`engine`（参数解析、缓存键、结果补全）、`builtin`（`scalar` / `dp_bic`）。
- 描述层不再自行读 ABF：`analyze()` 把 `AnalysisResult` 传给描述器。`EventView` 同时携带分析波形（开低通即滤波后）与原始波形，并记录动态 I0 窗口、电压窗口、`i_open` / `i_blockade` / `sigma_open` 的来源、事件方向、检测器版本与参数摘要、分析配置摘要。
- 事件身份：`source_id` = ABF 内容 SHA-256（不可读时 path + size + mtime，合成信号再并入波形摘要）；`event_key` = `sha1(source_id|fs|start_sample|end_sample)[:16]`，不含检测器与行号。旧 `event_id` 保留为 `legacy_event_id`，界面序号不变。
- 缓存键改为 `(event_key, describer, version, params_hash, data_hash)`；GUI 的 `DescribeWorker` 改为消费 `AnalysisResult`，切换描述器或参数即失效。
- 导出：`_fingerprints.xlsx` 旧列顺序不变，追加事件键、`source_id`、相对/全局采样、波形来源、描述器版本、参数摘要、覆盖度；JSON `schema_version` 升到 `1.1`，旧键保留并新增 `manifest`；`_events.mat` 每事件带 `event_key`、顶层带 `source_id`。

**测试**：新增 20 条（契约 7 / 上下文 8 / 导出 5），覆盖内容寻址、改剔除阈值后事件键不变、缓存键随参数与数据变化、低通/动态 I0/电压切片、全局坐标、旧列顺序与三处导出的键一致。全量 249 passed。

**兼容**：旧 `event_id` 语义、旧 Excel 列、旧 JSON 键、`describe_rows` / `make_event_view(rec, row)` 旧调用均保留；`describe_rows` 路径标记 `trace_source="raw"`。

**下一步**：阶段 4——方向感知的分段边界、整数采样与覆盖、BIC 过分割评测，再进入标注闭环。

---

### [2026-10-25] 阶段 1-2：检测器目录、配置单一真值与异常解耦

**变更**
- 新增 `params.py` / `registry.py`：检测器 id、标签、参数归属、电压/I0 能力集中管理；GUI、CLI、批处理、对比窗口不再各写一份选项。`normalize_config` 统一解析检测器与模块依赖，未知 id 告警而非静默降级。
- `ParamPanel` 改为保存完整载入协议并用 `dataclasses.replace` 增量覆盖；此前 65 个字段中 27 个未暴露字段会在重跑时被重置。`PipelineConfig.load` 对未知键告警；集合字段在构造时规范为 tuple/dict。
- 异常识别保持检测后的可选后处理：`AnalysisResult` / `FileReport` 记录实际检测器、异常是否启用、I0 是否参与检测；异常关闭时 `valid_pct` 为空，GUI 顶部显示“异常识别：关”。
- `DetectionResult` 新增检测器剔除、屏蔽区间与计数诊断；平台滞回原本丢弃的 pulse-cleared / rupture / threshold 事件进入 `df_excluded`，使用独立 `drop_stage=detector` 与 `plateau:*` 命名空间。
- `df_excluded` 新增 `drop_code` / `drop_stage`；选中剔除事件不再误用保留事件的指纹缓存。

**测试**：全量 229 passed。新增注册表/CLI/配置 65 字段往返、未暴露字段保留、异常开关不改变检测、burst + anomaly 边界一致、平台剔除可追溯、GUI 异常空态与剔除选中隔离等测试。

**下一步**：阶段 3——统一事件身份与描述层分析上下文。

---

### [2026-10-22] v3.1.0：事件指纹描述层集成

**变更**
- 从糖测序项目移植 `describe.py` / `steps.py`：`EventView`、`Segment`、`EventDescription`、描述器注册表、DP+BIC 分段、Scalar 对照描述器；去掉 mat / CSV / CLI 依赖。
- 新增 mod `describe`（默认关闭）：批量输出 `<名>_fingerprints.xlsx`（events / segments / params）与 `.json`（嵌套结构）。
- GUI：参数面板增加“事件指纹”组；切片图叠加分段线与段电平；右侧分段表；工具栏“指纹分段”开关。选中事件按需计算并缓存。
- CLI：`--describe dp_bic|scalar`、`--fp-param KEY=VALUE`。
- DP 内层用 numba 编译（可选，缺失时退回 numpy），长事件约 0.3–0.5 s/个；发行包保留加速内核。
- 版本 `3.0.0 → 3.1.0`；文档明确“只做分段，不做指纹分类/识别”。

**测试**：新增 14 条；全量 207 passed（46 s）。性能：Gln 6 事件 2.7 s；His 前 30 事件 9.3 s。

**已知限制**：DP+BIC 可能过分割（糖数据 30 段 vs 人工 18 指纹）；批量开启后耗时随事件长度增长。

**下一步**：标注数据足够后再做指纹匹配/分类。

---

### [2026-10-22] 检测器整合与首页工作台（v2.1 / v3.0.0）

**变更**
- 新增 `detect_plateau.py`：移植糖项目的平台滞回检测（进入深阈值 / 退出浅阈值 / 短开孔合并 + 电压屏蔽 + 脉冲清除 + 炸膜剔除），用 `depth_pA = amp - ref` 统一符号约定。
- `detect()` 按 `detector = level / burst / plateau` 分派，`event_mode` 保留为旧配置回退；默认仍电平法。
- 新增首页工作台（单文件 / 批量 / 算法对比 / 教程 + 最近打开）与分析窗口工作栏；新增 `compare.py` 并排跑 2–3 种算法。
- 版本 `2.1.0 → 3.0.0`；之后 `3.0.0 → 3.1.0`。

**测试**：全量 193 passed（v3.0.0）。离屏冒烟：Ala 三算法 level 44/37、burst 46/37、plateau 215/35。

**关键取舍**：平台法在浅/短事件上更敏感，原始数明显偏高；`min_toff` 过滤后与电平法同量级，默认不切换。

**下一步**：逐条核查 Asp / ARNKRS 平台法多出的事件。

---

### [2026-10-22] 算法审计：检测器收敛与描述层边界

**变更**
- 新增 `PLAN_event_pipeline.md`（已实施并删除）：跨三项目的算法审计、糖数据诊断证据、统一检测器与描述层契约。
- 糖项目删除 Clampfit-lite 检测，平台滞回成为唯一检测；新增描述层（`EventView` / 可变长 `Segment` / 描述器注册表 / `ParamSpec`）。
- 修 σ 估计 bug：原按 `3·std(整窗)` 取带会被事件本体污染（实测 43.9 pA，真值 1.8）；改为“深度 5% 或 5 pA 窄带 + MAD”。

**测试**：糖项目 37 passed；GalNAc-1 重提取 977 事件，与现有事件表逐值一致。

---

## 算法取舍备忘

以下结论来自实样对照，改动相关算法前先看这里。

- **skew / kurt 定义**：特征表规范用有偏估计（`skewness` / `kurtosis`，flag=1），pandas 默认无偏校正。两者实测 skew 0.80 vs 0.70、kurt 符号相反；尚未对齐，见技术债 C1。
- **ΔI 散点**：symlog 实测有害（主体只占纵轴 4–6%），固定为线性轴 + 正负分色 + 保留全部事件。
- **慢漂移**：必须同时满足位移与不稳定；弱漂移与良性漂移（有位移、散布正常）在当前特征下不可分。
- **毛刺门控**：单一标量无法既剔 TRP 毛刺又保住多电平文件，默认关；TRP 手动设 0.85–0.95。
- **burst 边界**：假设开孔电平稳定；Ala/Asp/Gln 的慢孔态切换会把另一态读成长阻孔，继续用电平法。
- **稀疏肽极性**：`polarity=auto` 会漏掉深阻孔（两侧电平占比都低于显著阈值）；ARNKRS / pore2 需显式 `both`。全局 `both` 会大面积过检，必须逐文件确认。
- **level1 选择**：取离基线最近的显著电平；“最远电平”会选中伪迹尾，导致 0–1 个事件。
- **时长参数**：`ignore_duration_ms` 在检测前吸收短偏离，`min_toff_ms` 在导出时剔除已检出事件，语义不可合并。
- **平台法**：对浅/短事件更敏感，默认不切换；差异需逐条核查。
- **MATLAB**：本机 R2024b 未装 Statistics and Machine Learning Toolbox；“在 MATLAB 里训模型”走不通，训练放 Python，MATLAB 只读 `dataset_all.csv` 出图。

## 技术债与已知限制

| # | 事项 | 现状 | 优先级 |
|---|------|------|--------|
| C1 | 特征 skew / kurt 与规范不一致 | `features.py` 仍用 pandas 无偏版 | 高 |
| R1 | 检测分类分配 `(n, 电平数)` 完整矩阵 | `detect.py` 约 30M 样本峰值 1.4 GB | 中 |
| R2 | QThread 生命周期未管理 | 重跑覆盖引用，可能 `Destroyed while thread is still running` | 中 |
| R5 | CLI 只扫当前目录且区分大小写 | `cli.py` 用 `path.glob("*.abf")`，不递归 | 中 |
| A4 | `anomaly.py` 单文件含两个检测器 | 约 670 行，可拆 `macro` / `refined` | 低 |
| A6 | 批处理把所有 DataFrame 攒在内存 | `run_batch` 最后统一拼 `dataset_all.csv` | 低 |
| — | `roi.py` 与 `analyze()` 流程重复 | ROI 需独立电平，暂未抽公共段 | 低 |
| — | 多余 `astype(float)` 拷贝 | 多数输入已是 float64 | 低 |
| — | DP+BIC 过分割 | 需标注数据评测后再调 | 待数据 |
| — | MATLAB 训练工具箱缺失 | 需 license 或改用 Python | 阻塞 |

## 版本线

| 版本 | 提交 / 内容 |
|------|-------------|
| `v1` | `42118fa`：命令行管线 + PyQt5 GUI |
| `v2` | `37b0356`：同事整合版（统一启动器 + 先验引擎入口） |
| `v3.0.0` | 首页工作台、三检测器统一入口、算法对比 |
| `v3.1.0` | 事件指纹描述层；当前版本 |
