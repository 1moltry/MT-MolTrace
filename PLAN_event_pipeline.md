# PLAN — 事件检测收敛与单事件描述层

> 状态：**v2.1 已实施**（2026-10-22）。糖项目 `npsweep` 完成事件检测收敛与描述层骨架；
> SDL `nanopore` 已把平台法接入为第三种可选检测器（`detector=level/burst/plateau`），
> 默认仍是电平法，现有行为不变。
> 关联：`DEVLOG.md` [2026-10-22]；糖项目 `docs/EVENT_DESCRIPTION.md`。

## 0. 目标

用户当前数据已进入**指纹阶段**，事件边界视为已定。本阶段只做两件事：

1. **找事件只保留最精的一个算法**，删掉重复实现，保留被数据证明必要的机制。
2. **划定事件内描述层边界**，为后续非均一化描述（变长形状、词表、DTW、ML）预留入口。

## 1. 算法审计（结论）

| 算法 | 机制 | 裁决 |
|---|---|---|
| SDL 电平法 `nanopore/detect.py` | 最近电平归属 + 游程 + ignore 吸收 + 流式电平更新 + 驻留/平台门控 | **保留**（肽/多电平生产路径），待平台法验证后再评估 |
| SDL burst `detect_events_burst` | 阻孔布尔化 + 形态学开闭 + 占有率/深度门控 | **保留**为 `event_mode` 可选 |
| npsweep 平台滞回 `detect_events_plateau` | 深阈值进入 + 浅阈值退出 + 短开孔合并 + 电压/炸膜/脉冲后处理 | **保留为糖数据唯一事件检测** |
| npsweep Clampfit-lite `detect_events` | 中点阈值二分 + 短游程合并 | **删除**：与 SDL 电平法数值等价 |
| cutlab 滞回 `detector.py` | 阻孔基线 + σ 归一 + 双阈值 | **保留**为事件内候选生成（并入描述层） |
| DP+BIC `steps.py` | 最优划分 + BIC + 自适应去边 | **保留**为 `dp_bic` 描述器 |
| PELT/形状挖掘 `work/shape_*` | 变点 + DTW/Fréchet/DBA/SAX | **研究沙箱**，不进生产默认 |

## 2. 诊断证据（2026-10-22）

6 个糖文件（GalNAc-1/2、GlcNAc-1、半乳糖-1、果糖-1、葡萄糖-1），同一 `level0`：

- 平台法 vs SDL 电平法：匹配率 96–99%，边界差中位 **0.08 / 0.12 ms**。
- npsweep Clampfit-lite vs SDL 电平法：边界差中位 **7×10⁻¹² ms**（同一算法）。
- 平台法能精确复现现有 `sweeps_all` 事件表（GalNAc-1：977 事件，逐值一致）。
- 长分歧（半乳糖-1 264.8–285.4 s、505–508 s）：平台法保留含部分恢复的长事件；
  电平法在 50% 中点处切断。**平台语义符合“事件内指纹不被切断”**。

结论：糖数据的事件边界由平台滞回定义，不再保留第二套事件检测。

## 3. 描述层契约

实现见糖项目 `npsweep/describe.py` + `docs/EVENT_DESCRIPTION.md`。

```python
EventView(
    event_id, source, fs, lowpass_hz, effective_bw_hz,
    start, end, ctx_start, ctx_end,
    current, i_open, i_blockade, sigma_open,
    voltage=None, i0_profile=None, state="A", meta={},
)

Segment(start, end, level_pA, level_rel, level_norm, attrs={})
EventDescription(
    event_id, source, describer, describer_version, schema_version,
    params, segments=[...], features={...}, payload={...}, quality={...},
)

class EventDescriber:
    id, label, version, params: tuple[ParamSpec, ...]
    def describe(view, params=None) -> EventDescription
```

硬约束：

- 段数、段长**不固定**；`len(segments)` 是结果，不是配置。
- `Segment.start/end` 相对事件起点；换上下文窗不改变坐标。
- 新增描述器只实现 `EventDescriber` + `register` + 单测，不改检测层/GUI。
- 三个基线不可混用：`i_open`（开孔）、`i_blockade`（阻孔基线 p15）、`i0_profile`（漂移）。

## 4. 跨项目迁移步骤

1. **糖项目（已完成）**：删 Clampfit-lite；平台法唯一；新增 `describe.py`；σ 估计修复；
   37 tests；GalNAc-1 重提取逐值一致。
2. **SDL 集成（已完成 v2.1）**：
   - 新增 `nanopore/detect_plateau.py`（平台滞回 + 电压屏蔽 + 脉冲清除 + 炸膜剔除）；
   - `nanopore/detect.py` 增加 `resolve_detector_id` 与 plateau 分派；
   - `PipelineConfig.detector` + 平台法参数；GUI 检测算法下拉 + 平台参数组；
   - CLI `--detector` 与平台法参数；版本 `2.1.0`；
   - GUI：首页工作台（单文件 / 批量 / 对比 / 教程 + 最近打开）；分析窗口顶部工作栏
     固定“检测算法 / 算法对比 / 批量处理 / 结果摘要”；对比窗口可并排看三法的事件与边界；
   - 糖数据 GalNAc-1 用 `--detector plateau` 得到 **977 事件**，与现有语料一致。
3. **肽样本验证（进行中）**：6 样本初步对比见 DEVLOG；kept 事件数在 Asp/ARNKRS 上有差异，
   需逐条核查后再决定是否把 plateau 设为某些数据的默认。**默认仍为 level。**
4. **统一注册表（待做）**：`Detector` 接口（id/label/capabilities/params/detect）供 GUI/CLI
   共用；平台法与电平法是同一实现的两个预设，不是两份代码。
5. **描述层迁移（待做）**：`npsweep/describe.py` → 共享 core；`cutlab.core.EventView` 改为复用；
   SDL GUI 增加“描述器”下拉与事件内段叠加。
6. **删除重复**：npsweep Clampfit-lite 已删；SDL 内的重复编排按 `analyze()` 统一。

## 5. 验收

- 糖：`pytest tests` 全绿；GalNAc-1 事件表逐值不变；`describe` 两描述器跑通。
- SDL：6 样本事件数/异常计数与当前一致（或差异逐条有解释）。
- 描述层：真实事件上 σ≈1.8 pA；段边界落在人工标注附近；JSON 往返保结构。
- 新增描述器不改 `detect.py` / `steps.py` / GUI。

## 6. 风险

- **SDL 平台法验证未做**：多电平/双向/近基线事件可能不如电平法；在验证前不切默认。
- **DP+BIC 过分割**：GalNAc-1 事件 1 实测 30 段 vs 人工 18 指纹；这是当前分辨率
  与 BIC 罚项的已知问题，留给后续描述器，不在本阶段调参。
- **σ 估计**：已修窄带 MAD；`cutlab` 同步修复，需回归指纹检测指标。
