# PLAN — 功能模块化（mod 注册表）

> 状态：**未实施**。本文件是实施规格，供后续 agent 直接落实。
> 基线：`main` @ `f138e34` 之后（含 2026-10-19 清理提交）。行号可能漂移。
> 关联模块：`nanopore/config.py`、`pipeline.py`、`cli.py`、`gui/controller.py`、`gui/parampanel.py`、`gui/main_window.py`、`analysis.py`。
> 伴生规格：`PLAN_burst_detection.md`（检测变体，见 §12）。

---

## 0. 决策（已与用户确认）

1. **默认最小 + 记住上次选择**：默认只跑底座，模块手动勾选；勾选与参数持久化，下次打开恢复。
2. **mod 只收「阶段／产物」；检测变体留参数面板**（见 §2）。
3. GUI 与 CLI **共用同一张注册表**，不各写一套。

---

## 1. 目标与非目标

**目标**：功能可多选、可关，避免每次全开；底座最小且为所有任务共用；配置可存、可复现、可分享。

**非目标**：不做动态插件发现（单包 ~8 个 mod，注册表足够）；不改检测算法本身。

---

## 2. 概念边界（关键）

- **底座（永远跑）**：`io`（读盘）→ `baseline`（电平）→ `detect`（事件分割）→ `features`（特征）→ 事件表 `_events.xlsx`。
- **mod（阶段／产物，可多选）**：见 §3。
- **检测变体（留参数面板，不做 mod）**：`polarity`、`event_mode`（`level`/`burst`）、`event_plateau_min_frac`（毛刺门控）、`ignore_duration_ms`、`ignore_event_duration_ms`、`level_contribution`、`update_levels`、`dwell_min_frac`、`--level0/--level1`。这些改变「底座怎么检测」，塞进模块列表会造成"开 A 却要先关 B"的错乱。

> 例外：`roi`（Cursor 局部分析）是 GUI 交互能力、无流水线阶段，**不算 mod**；`gui`／`batch` 是入口模式，不是 mod。

---

## 3. 模块清单

| id | 名称 | 现状默认 | 新默认 | 依赖 | 主要参数 | 产物／影响 |
|----|------|----------|--------|------|----------|------------|
| `lowpass` | 低通滤波 | 关 | 关 | — | `filter_lowpass_hz` | 检测前滤波（`preprocess.lowpass`） |
| `dynamic_i0` | 动态开孔基线 I0(t) | **开** | 关 | — | `dr_pA` | 逐事件 `Io`（免疫阻孔漂移） |
| `anomaly` | 宏异常（反压/膜抖/炸膜/漂移） | **开** | 关 | — | `jump_min_ms`、`noise_sigma_mult`、`jitter_min_ms`、`refined_jitter_level_frac_max` | anomalies sheet + 区带 + `drop_reason` |
| `refined_anomaly` | 细粒度异常判据 | **开** | 关 | `anomaly`、`dynamic_i0`、（电压通道） | 全部 `refined_*` | 分级 `kind`（spontaneous/manual、轻/重膜抖、炸膜） |
| `plots` | 输出图 | **开** | 关 | — | — | `<名>_overview/scatter/hist.png` |
| `dataset_export` | 合并训练表 | **开** | 关 | — | — | `dataset_all.csv`（批次） |
| `summary` | 批次汇总 | **开** | 关 | — | — | `summary.xlsx`（批次） |

**特别注意 `refined_anomaly` 依赖 `dynamic_i0`**：动态 I0(t) 是它的输入之一；启用时须自动补齐前置（§6）。

---

## 4. 机制

### 4.1 新增 `nanopore/mods.py`
```python
from dataclasses import dataclass

@dataclass(frozen=True)
class ModSpec:
    id: str
    label: str                    # 中文名（GUI 显示）
    desc: str                     # 一句话（GUI tooltip）
    default_on: bool = False
    requires: tuple[str, ...] = ()
    params: tuple[str, ...] = ()   # 本模块消费的 PipelineConfig 字段名

ORDER: tuple[str, ...] = ("lowpass", "dynamic_i0", "anomaly", "refined_anomaly",
                          "plots", "dataset_export", "summary")   # 拓扑序，依赖在前

MODS: dict[str, ModSpec] = {m.id: m for m in (
    ModSpec("lowpass", "低通滤波", "检测前做零相位低通（需设截止频率）",
            params=("filter_lowpass_hz",)),
    ModSpec("dynamic_i0", "动态开孔基线", "逐事件 Io 跟随开孔漂移，免疫长阻孔污染",
            params=("dr_pA",)),
    ModSpec("anomaly", "异常检测（宏）", "反压/膜抖/炸膜/慢漂移区间，剔除其中事件",
            params=("jump_min_ms", "noise_sigma_mult", "jitter_min_ms",
                    "refined_jitter_level_frac_max")),
    ModSpec("refined_anomaly", "异常检测（细粒度）", "分级异常判据（反压恢复 spontaneous/manual、轻/重膜抖、炸膜）",
            requires=("anomaly", "dynamic_i0"), params=("refined_*",)),
    ModSpec("plots", "输出图", "overview / scatter / hist 三张图"),
    ModSpec("dataset_export", "合并训练表", "所有文件的保留事件纵向拼接（dataset_all.csv）"),
    ModSpec("summary", "批次汇总", "每文件事件数/有效率/异常计数（summary.xlsx）"),
)}


def resolve_mods(ids) -> tuple[str, ...]:
    """补依赖、去重、按 ORDER 排序。未知 id 忽略并告警。"""
```

### 4.2 `PipelineConfig` 变更（`config.py`）
- 新增 `enabled_mods: tuple[str, ...] = ()`（空 = 仅底座；JSON 存为列表）。
- 删除被 mod 取代的三个开关：`anomaly_enabled`、`refined_anomaly_enabled`、`dynamic_i0_enabled`。
- 保留：各 mod 的参数、以及全部**检测变体**参数。
- `load`（`config.py:90`）已按 `fields(cls)` 过滤未知键，向后兼容读取；但旧文件里的 `*_enabled` 不再生效（见 §8）。

### 4.3 编排重构（`pipeline.py`）
- 定义 `PipelineState` dataclass：`rec / lv / filtered / det / i0_profile / anom / df / df_excluded / dataset_row / outputs`。
- 底座函数 `_run_base(state)`：`read → estimate_levels → (可选 lowpass 由 mod 覆盖) → detect → compute_features`。恒跑。
- 每个 mod 一个 `stage(state) -> None` 函数，只读自己那组 `params`。
- `process_file` 改为：建 state → `_run_base` → `for mid in resolve_mods(cfg.enabled_mods): _STAGE[mid](state)` → 落盘。

### 4.4 抽取共享 `analyze()`（顺带消除重复）
现状 `pipeline.process_file`（`pipeline.py:43-198`）与 `gui/controller.AnalysisWorker.run`（`controller.py:34-125`）是**近乎重复**的编排。模块化时抽出 `nanopore/analyze.py`（或放 `pipeline.py`）：
```python
def analyze(rec, cfg) -> AnalysisResult:   # AnalysisResult 即 PipelineState 的只读视图
```
`process_file` 与 `AnalysisWorker` 都调它。**这是本次顺带修掉的真重复**，避免 GUI/CLI 两条路径继续漂移。

---

## 5. 代码改动清单（逐文件）

| 文件 | 改动 |
|------|------|
| `nanopore/mods.py` | **新增**：`ModSpec`／`MODS`／`ORDER`／`resolve_mods` |
| `nanopore/config.py` | `enabled_mods`；删三个 `*_enabled` |
| `nanopore/analyze.py` | **新增**：共享 `analyze(rec, cfg)` + `PipelineState`（或并入 `pipeline.py`） |
| `nanopore/pipeline.py` | `process_file` 改 use `analyze`；`run_batch` 的 dataset/summary 归 `dataset_export`/`summary` stage |
| `nanopore/gui/controller.py` | `AnalysisWorker.run` 改 use `analyze`（删重复编排） |
| `nanopore/gui/modpanel.py` | **新增**：模块多选面板（§6） |
| `nanopore/gui/parampanel.py` | 参数按 mod 分组、随开关显隐；变体参数单独常显组 |
| `nanopore/gui/main_window.py` | 加「模块」dock（`modpanel`） |
| `nanopore/cli.py` | `--mods`／`--minimal`／`--all`；`--no-anomaly` 转别名 |
| `README.md`／`DEVLOG.md` | 模块一节 + 默认最小说明 + CLI 示例 |

---

## 6. GUI 规格

- **新增 dock「模块」**（`modpanel.py`）：按 `ORDER` 列出每个 mod 一行 `QCheckBox`，label = `ModSpec.label`，tooltip = `ModSpec.desc`。
- 两个按钮：**「全选」**（勾 `ORDER` 全体）、**「仅底座」**（清空）。
- **依赖联动**：勾 `refined_anomaly` → 自动勾上 `anomaly`、`dynamic_i0`，状态栏提示；取消 `anomaly`/`dynamic_i0` → 联动取消 `refined_anomaly`。
- **参数分组**（`parampanel.py`）：每个 mod 的参数装进一个 `QGroupBox`，随该 mod 勾选显隐；底座参数常显；**检测变体**（极性/模式/毛刺门控等）单独一组常显。
- **记住上次选择**：`QSettings("SDL-Nanopore", "gui")` 存 `enabled_mods` + 全部参数，启动时恢复；「存参数／读参数」仍走 JSON 协议（可复现、可分享、可当"启动项预设"）。
- 「重跑检测」（`parampanel.py:127,185`）即时生效。

---

## 7. CLI 规格

```bash
python -m nanopore run <path> --mods lowpass,dynamic_i0,anomaly,refined_anomaly,plots,dataset_export,summary
python -m nanopore run <path> --minimal        # = --mods ""（仅底座）
python -m nanopore run <path> --all            # = 全部 mod（≈今日默认）
python -m nanopore run <path> --no-anomaly     # 兼容别名：从 mods 去掉 anomaly/refined_anomaly
```

---

## 8. 兼容与默认行为变更（务必写进 README）

- **默认输出会变少**：今日默认全开；改为默认最小后，默认不再产出异常剔除、图、`dataset_all.csv`。这是用户明确要求的行为变更，README 顶部需醒目标注并给 `--all`。
- **旧 JSON 协议**：`PipelineConfig.load` 过滤未知键故仍可读；但旧文件里 `anomaly_enabled=True` 等字段已删、不再生效。GUI「读参数」遇到含已删字段的旧协议时提示一次，并把对应 mod 自动映射进 `enabled_mods`（尽力而为）。
- 同步更新 README「参数说明」为「模块 + 参数」两节。

---

## 9. 测试规格

- **新增 `tests/test_mods.py`**：
  - 注册表完整性：`id` 唯一、`requires` 均存在、`params` 都在 `PipelineConfig` 字段内、`ORDER` 覆盖全部 `MODS`。
  - `resolve_mods`：补依赖、去重、按 `ORDER` 排序；未知 id 被忽略。
  - **最小运行**：`enabled_mods=()` 只产 `_events.xlsx`（无 anomalies sheet、无图、无 `dataset_all.csv`）。
  - **全开 golden**：`--all` 路径与今日全开路径**逐值一致**（事件数、特征表、异常区数）。
- **现有测试**：多数直调 `detect_events`／`compute_features`／`analyze_roi`，不受影响；`test_dataset_export` 等改为显式开对应 mod。

---

## 10. 验收标准

1. `pytest` 全绿（含最小路径与全开 golden）。
2. GUI：模块面板可多选；参数随模块显隐；关掉某模块其产物消失、其余不受影响；重开 GUI 恢复上次选择。
3. CLI：`--minimal` 只出事件表；`--all` 产出与今日一致。
4. README／DEVLOG 已更新。

---

## 11. 风险与回滚

- **默认行为变更影响同事脚本**：README 顶部醒目标注 + `--all` 后路 + DEVLOG 记录。
- **编排抽取属重构**：以 golden 回归兜底。
- **回滚**：把 `enabled_mods` 默认改回全开即恢复旧行为；或 revert 提交。

---

## 12. 与 burst 检测（`PLAN_burst_detection.md`）的关系

`event_mode`（`level`/`burst`）属**检测变体**，不做成 mod；burst 的实现纳入底座检测层（`detect` 分派，见该规格 §5.1），在参数面板受控。两份规格可并行落地，互不阻塞。

---

## 13. 工作流与检查点

1. 建 `mods.py` + `resolve_mods` + `PipelineState`；过渡期把现有 `*_enabled` 映射到 `enabled_mods`，保证 `--all` 等价。
2. 抽共享 `analyze()`，`pipeline` 与 `controller` 都改调它。
3. 接 GUI 模块面板 + 参数分组；接 CLI 三个开关。
4. 补 `tests/test_mods.py`；README／DEVLOG；PR 走 `CONTRIBUTING.md`。
