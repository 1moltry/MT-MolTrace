# PLAN — 统一指纹平台后续阶段

> 状态：阶段 1-5、7 已完成；阶段 6（标注与评测闭环）与阶段 8（发行）待实施。
> 阶段 4-5 与阶段 7 于 2026-10-25 完成（分支 `chore/repo-slimming`）。
> 本文供新的干净上下文直接接手；开工前先读 `CLAUDE.md`、本文件和 `DEVLOG.md` 的 [2026-10-25] 条目。

## 1. 已确定的目标与边界

目标是把 MOLTRACE 收敛为唯一生产平台，打通事件检测、事件内指纹查找、标注、评测和导出。糖测序项目保留数据与实验适配。深度信号分析项目作为历史研究归档。

以下决定不再重新讨论：

1. 主程序收敛，不拆第二个共享库，不保留第二套生产 GUI。
2. 异常识别只做检测后的可选后处理。它不得改变 level、burst、平台滞回的事件边界。
3. 本轮不做机器学习。只做可解释的分段、形状查找、匹配、聚类和评测。
4. 旧的非 ML 形状算法可以迁入，但必须标记为实验性，不得进入默认生产结果。
5. 旧配置、QSettings、CLI 参数、Excel sheet、MATLAB 合并表列名必须保持兼容；新增字段只追加。
6. 旧研究项目的数据和未提交改动不迁移、不清理，只在需要时建立显式适配层。

## 2. 当前完成状态

阶段 1-2 已完成并提交：

- 检测器目录集中在 `nanopore/registry.py`，GUI、CLI、批处理和对比窗口共用元数据。
- 参数元数据集中在 `nanopore/params.py`。
- GUI 配置从完整载入协议增量构造，未暴露字段不再被重置。
- 配置 JSON 集合字段规范为 tuple/dict；未知键告警。
- 异常保持可选；关闭时 `valid_pct` 为空，界面明确显示“异常识别：关”。
- 平台法剔除进入 `df_excluded`，带 `drop_stage=detector` 和 `drop_code`，不与异常 kind 混用。
- 全量测试 `229 passed`；真实 `Ala.abf` 批处理验收通过。

当前完成状态：

- 缺口 1、2：阶段 3 关闭（描述层使用分析上下文与稳定事件身份）。
- 缺口 3：阶段 4 关闭（方向感知、整数边界、时间窗边缘、慢出孔修剪、BIC 诊断、classic 描述器、全局区间与评测适配器）。
- 缺口 4：标注与评测闭环仍开放（阶段 6）；跨事件形状发现已接入实验层（阶段 7），但未验证、默认关闭。

**阶段 3 已完成（2026-10-25，待提交）**：新增 `nanopore/fingerprint/` 包（contracts / context / registry / engine / builtin），描述层改吃 `AnalysisResult`，使用检测时的分析波形、动态 I0 与电压窗口；事件身份改为 `source_id` + `event_key`；缓存键改为 `(event_key, describer, version, params_hash, data_hash)`；指纹 Excel/JSON 与事件波形 `.mat` 补充事件键、全局采样和溯源字段。旧 `event_id` 保留为 `legacy_event_id`，旧列与旧 JSON 键不变。缺口 1、2 关闭。

**阶段 4 已完成（2026-10-25）**：`edge_bounds` 方向感知（向下 p15 / 向上 p85 / 双向带状回孔），边缘窗改为毫秒；`Step` 记录整数起止，降采样余数并入最后一段；慢出孔尾部过渡段修剪；BIC 增加 `bic_penalty` 与 `bic_n_eff` 诊断；新增 `classic` 双阈值描述器（beta）；`dp_bic` 因实测过分割改标 beta；新增 `fingerprint/intervals.py` 的全局区间与区间 F1 适配器。现有 `GalNAc-1` 标注上 `classic` 复现 F1@0.5 ms ≈ 0.536，`dp_bic` 仍过分割（195 vs 97，F1 ≈ 0.151），BIC 自动有效样本数不是解药（33 段，F1 ≈ 0.062），故默认保持源行为、诊断参数 opt-in。

**阶段 5 已完成（2026-10-25）**：描述器下拉与参数表单由注册表生成；分段表支持并排比较；描述缓存与代次竞态修复；工具栏“导出指纹”；批量对话框显示检测器/描述器/异常状态并支持描述阶段取消；对比窗口复用纯比较函数并增加描述器指标；CLI 新增 `--describers`，保留 `--describe` / `--fp-param` 旧语义。

**阶段 7 已完成（2026-10-25，先上线后调试）**：新增 `nanopore/fingerprint/research/`（PELT / DTW / 离散 Fréchet / DBA / 形状词表 / null / 语料 / 模型 / 工作流）；`shape_vocab` 与 `pelt` 注册为 `experimental`，默认关闭；`ShapeModel` 支持 JSON 保存/加载与解码叠加；GUI 首页新增“指纹研究”工作区；CLI 新增 `research fit / decode / nulls`；`research` extra 与发行 hidden imports 已接。旧词表 AUC 0.674 / 0.715 < 0.85 的事实保留在界面与导出中。真实 GalNAc-1 冒烟通过，但准确率与参数标定尚未完成。

## 3. 目标数据流

```text
ABF
 → 读取与可选预处理
 → 检测器生成候选事件
 → 检测器有效性规则（记为 drop_stage=detector）
 → 可选异常识别（只做检测后剔除）
 → 特征表 + 完整排除记录
 → 统一 EventView
 → 单事件指纹描述器（分段/候选区间）
 → 跨事件语料与形状发现（实验性）
 → GUI / CLI / 批处理 / 标注 / 评测 / 导出
```

三条硬约束：

- 检测器只决定事件边界；异常不参与边界。
- 描述器只消费 `EventView`，不得自行读 ABF，不得依赖 Qt。
- 跨项目比较必须按稳定事件身份和全局采样坐标连接，不能按行号。

## 4. 统一契约

### 4.1 事件身份

```text
source_id = ABF 内容 SHA-256；退化时使用 path + size + mtime
event_key = sha1(source_id | fs | start_sample | end_sample)[:16]
legacy_event_id + id_base + id_scope = 兼容审计字段
```

`event_id` 继续表示当前运行中的界面序号。`event_key` 不包含检测器 id，使同一物理边界可以跨检测器比较。检测器来源另行记录。

旧标注迁移必须冻结当时的事件表：

1. 找到并校验当时的 `_events_index.csv`，记录 SHA-256。
2. 用旧 `event_id` 和 `id_base` 解析事件 span。
3. 建立旧 span 到 `event_key` 的 `event_map`。
4. 记录 exact、overlap、orphan 三种匹配状态。
5. 无法校验的标注进入隔离清单，绝不按新事件号静默重映射。

### 4.2 EventView

必须包含：

- `source_id`、`event_key`、`legacy_event_id`；
- 全局 `start/end/ctx_start/ctx_end`、采样率、单位；
- 分析波形和原始波形，并声明描述器使用哪一份；
- `i_open`、`i_blockade`、`sigma_open` 及其来源；
- 动态 I0 窗口、电压窗口、事件方向；
- 检测器 id、版本、参数摘要、分析配置摘要。

当前 `make_event_view()` 只接收记录和特征行，阶段 3 改为接收 `AnalysisResult` 和事件引用。不得再维护第二套 `cutlab.EventView`。

### 4.3 指纹结果

`EventDescription` 和 `Segment` 保留现有字段，追加：

- `event_key`、`source_id`、`fs_hz`；
- 事件全局起止采样；
- 每段的相对采样和全局采样；
- `describer_version`、`params_hash`、`trace_source`；
- `quality`、`coverage`、`attrs_json`。

JSON 保持旧键，`schema_version` 升到 `1.1`；Excel 旧列顺序不变，新列追加在后。

### 4.4 算法接口

```python
class FingerprintDescriber(Protocol):
    id: str
    version: str
    maturity: str                 # stable / beta / experimental
    input_trace: str              # analysis / raw
    params: tuple[ParamSpec, ...]
    def describe(view: EventView, params): -> EventDescription: ...


class CorpusShapeMethod(FingerprintDescriber, Protocol):
    def fit(corpus: EventCorpus, params): -> ShapeModel: ...
    def decode(view: EventView, model: ShapeModel, params): -> EventDescription: ...
```

注册采用显式 import，兼容 PyInstaller。不要使用 entry points 动态发现。新算法只实现接口、注册并补测试，不改检测层和 GUI。

## 5. 阶段 3：描述上下文与稳定身份

### 任务

1. 新建 `nanopore/fingerprint/` 包：
   - `contracts.py`：事件身份、EventView、Segment、EventDescription、RunManifest。
   - `context.py`：从 `AnalysisResult` 构建 EventView。
   - `registry.py`：描述器注册与成熟度。
   - `engine.py`：单事件、多描述器、批量描述与缓存键。
2. `nanopore/describe.py` 保留为兼容门面，重导出新接口。
3. `analyze()` 把 `AnalysisResult` 传入描述层；描述使用本次实际分析波形，同时保留原始波形。
4. 缓存键改为 `(event_key, describer, version, params_hash, data_hash)`。
5. 指纹导出补充全局坐标、事件键、波形来源与分析配置摘要。
6. 旧 `event_id` 保留为 `legacy_event_id`，不改界面序号。

### 文件

- 新增 `nanopore/fingerprint/*`。
- 修改 `nanopore/analyze.py`、`nanopore/describe.py`、`nanopore/analysis.py`、`nanopore/gui/controller.py`。
- 新增 `tests/test_fingerprint_contract.py`、`tests/test_fingerprint_context.py`、`tests/test_fingerprint_export.py`。

### 验收

- 开启低通、动态 I0 或电压时，EventView 使用与分析一致的数据和切片。
- 同一物理事件在重跑、改剔除阈值后 `event_key` 不变。
- `event_key` 可以从 Excel、JSON 和事件波形导出中互相回溯。
- 旧 JSON 键仍可读，旧测试不降级。
- 快检与相关 GUI 测试通过，阶段门禁跑全量。

## 6. 阶段 4：分段算法正确性与评测（已完成 2026-10-25）

### 任务

1. 方向感知：
   - 向下事件使用 p97 开孔电流和 p15 阻孔基线；
   - 向上事件使用 p3 和 p85；
   - 双向或多电平事件不得强行套用单一阻孔基线，保留明确的质量标记。
2. 边缘处理：
   - `t_in` 继续用导数法；
   - `t_out` 按事件方向选择回到开孔的判据；
   - 边缘窗由固定采样改为时间窗，25 kHz 与 50 kHz 行为一致。
3. 边界改为整数采样：
   - `Step` 记录整数长度和起止；
   - 降采样余数并入最后一段；
   - 最后一层必须覆盖到 `t_out`。
4. 过分割：
   - 标定 `snr_min`，默认值变更必须有数据证据；
   - 评估 BIC（Bayesian Information Criterion，贝叶斯信息准则，用复杂度惩罚选择段数）的有效样本数或惩罚乘子；
   - 不通过降低 `k_max` 掩盖过分割。
5. 新增 `classic` 描述器，包装现有双阈值候选器，标记 `beta`。
6. 提供 `to_global_intervals()` 与标注评测适配器。

### 验收指标

- 合成三步、单步、向上、向下、双向事件恢复正确。
- 浅事件、慢出孔、事件体占上下文窗 80% 时无过渡假段。
- 长事件 `coverage_frac=1`。
- 在已有 12 事件、97 个指纹的标注上报告以下指标：
  - 区间 F1：综合起止漏检与误检的调和平均；
  - 边界位移；
  - 漏切与误切。
- 无新增标注时不得宣称参数最优。

## 7. 阶段 5：前后端联动（已完成 2026-10-25）

### 任务

1. 描述器下拉与参数表单由注册表自动生成。
2. `SliceView` 只叠加当前描述器的分段；`SegmentTable` 支持描述器切换和并排比较。
3. 修复 GUI 描述缓存、代次竞态和切换文件后的旧结果。
4. 当前文件增加“导出指纹”，复用现有 writer。
5. 批量对话框显示检测器、描述器和异常状态；描述阶段支持取消。
6. 对比窗口复用纯比较函数，增加描述器指标；保持旧对比 CSV 口径。
7. CLI 保留 `--describe` 与 `--fp-param` 旧语义，新增多描述器参数。

### 验收

- 同一事件可切换描述器，参数变化使缓存失效。
- GUI、CLI、批处理对同一输入产生一致的分段结果。
- 单文件与批量导出字段一致。
- 关闭异常时不会显示“异常 0”，而是“未筛查”。

## 8. 阶段 6：标注与评测闭环

### 任务

1. 迁移 `cutlab` 的纯逻辑：标注长表、区间与重叠检查、一致性分析、区间 F1、报告。
2. 新增旧标注迁移命令和 `event_map`；原始标注只读保留。
3. 在现有主界面增加只读标注复核；人工编辑作为显式模式，不覆盖计算描述。
4. 评测结果写入报告文件，记录预测、真值、参数和事件键。
5. 现有数据事实：主要标注为 `GalNAc-1` 的 12 事件、97 个指纹；尚无第二轮标注。不得把“标注完成”写进结论。

### 验收

- 旧标注迁移后可复现读取，cut 起止保持全局采样。
- 旧号与新事件不匹配时进入隔离清单。
- GUI 与 CLI 对同一预测得到相同 F1 和边界位移。
- 无需命令行即可完成“导入标注 → 评测 → 查看报告”。

## 9. 阶段 7：实验性形状发现（已完成 2026-10-25）

### 任务

1. 把以下非 ML 方法迁入 `nanopore/fingerprint/research/`：
   - PELT（线性时间复杂度的变点检测）；
   - DTW（动态时间规整，对齐长度不同的轨迹）；
   - 离散 Fréchet（曲线之间的几何距离）；
   - DBA（DTW 重心平均，生成共识轨迹）；
   - 形状词表。
2. 依赖放入可选 `research` extra；缺失时界面明确提示，不静默失败。
3. 新建跨事件语料对象和 `CorpusShapeMethod`，支持拟合、保存、加载和解码。
4. 在首页增加“指纹研究”工作区：选择语料、拟合词表、查看缩略图、叠加解码结果。
5. 每个实验算法声明成熟度、版本、参数和数据前提。

### 已知事实

旧形状词表在结构化 null 上未达到原定判据。对 N1tele 的 AUC（ROC 曲线下面积，衡量区分能力，1 为完美）为 0.674，对 N2phase 为 0.715，低于 0.85。null 指同管线生成的对照信号。

该结果只能作为实验基线。不得默认启用，也不得在文档中写成已验证成果。

### 验收

- 旧算法可在主程序复现并明确标注“实验性”。
- 新算法只需新增实现和注册，不改检测层与 GUI。
- 合成 null、留一文件复现和人工叠加检查都有入口。
- 默认生产流程不启用实验算法。

## 10. 阶段 8：兼容、文档与发布

- 更新 README、DEVELOPMENT、tutorial、DEVLOG 和迁移说明。
- 检查旧 JSON、QSettings、CLI、Excel、CSV、MATLAB 消费路径。
- 全量测试、真实样例批处理、GUI 离屏冒烟和发行包自测。
- 发行版本号与上传 Release 由维护者在验收后决定；代码提交不等于发布。

## 11. 测试分层

测试数量不是问题，重复跑完整套件才是时间成本。当前实测：

| 层级 | 内容 | 规模 | 耗时 |
|------|------|------|------|
| 日常快检 | 非 GUI、非本地数据集成 | 231 项 | 约 35 秒 |
| GUI | Qt 离屏界面 | 58 项 | 约 12 秒 |
| 集成 | 依赖本地 `.abf` / 标注的端到端路径 | 14 项 | 约 57 秒 |
| 完整门禁 | 全部测试 | 303 项 | 约 98 秒 |

命令：

```bash
python -m pytest tests/ -q -m "not gui and not integration"
python -m pytest tests/ -q -m gui
python -m pytest tests/ -q -m integration
python -m pytest tests/ -q
```

规则：

1. 每次小改动只跑相关测试文件；核心接口改动加跑日常快检。
2. 提交前跑完整门禁。纯文档提交可只跑快检，并在提交信息中说明。
3. 发布前跑完整门禁、真实样例和 GUI 冒烟。
4. 不得通过删除回归测试来缩短时间；用 marker、fixture 和 session 级 QApplication 优化。
5. 新增 GUI 测试放入 `tests/test_gui_*.py`，自动获得 `gui` 标记；依赖本地数据且较慢的测试加 `integration` 标记。

## 12. 兼容与风险

1. 描述层会首次真正使用分析波形；低通开启时指纹结果可能变化，必须用标注评测解释差异。
2. 稳定事件身份是新增字段；旧 `event_id` 语义保留一轮，不能直接替换。
3. 旧标注迁移依赖冻结事件表；缺表时只能几何校验或隔离，不能猜测。
4. 方向修复会改变向上和双向事件结果，必须先有合成真值和 RED 测试。
5. 形状算法仍是实验品；任何默认启用都需要人工验收。
6. 研究项目不是 git 仓库或有未提交改动，迁移时只读复制，不在原地清理。
7. 发布包使用 PyInstaller 显式导入；新增包必须在构建脚本中验证可见性。

## 13. 新上下文开工清单

1. `git status --short --branch`，确认分支和未提交改动。
2. 阅读 `CLAUDE.md`、本文件、`DEVLOG.md` 的 [2026-10-25] 条目。
3. 运行 `python -m pytest tests/ -q -m "not gui and not integration"`，确认快检基线。
4. 阶段 4-5、7 已完成；下一轮从阶段 6 开始；阶段 7 只做上线后的参数标定，不再新增未验证算法。
5. 每个阶段结束追加 DEVLOG，写明变更、测试、下一步和兼容性影响。
6. 提交前运行完整测试；没有明确要求时不推送远端、不构建发行包。
