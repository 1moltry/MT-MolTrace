# PLAN — 驻留包络去抖事件检测（burst mode）

> 状态：**未实施**。本文件是实施规格，供后续 agent 直接落实。
> 基线：`main` @ `f138e34`（文件内行号以此为准，改动后可能漂移）。
> 关联模块：`nanopore/detect.py`、`config.py`、`pipeline.py`、`roi.py`、`gui/controller.py`、`gui/parampanel.py`、`cli.py`。

---

## 0. 阻塞项（实施前必须问用户）

1. **4 张波形图分别对应哪个 `.abf`？**
   图 3 疑似多电平文件（候选 `pCLAMP11.2/Sample Data/4level.abf`）；图 2／图 4 疑似局部实验数据。拿到文件名才能复现、才能钉住 `burst_min_gap_ms`。
2. **语义定义**：一次"驻留/一次跳跃"算**一个事件**，还是按 burst 分组（多次开合算一组）？这直接决定 `burst_min_gap_ms` 的取向。

未确认前，只能用合成信号调参与验收（见 §7）。

---

## 1. 问题与目标

现有 `detect_events`（`detect.py:124`）是**即时**判定：逐样本最近电平归属 → 电平 run → 事件，再加**同电平**桥接 `_bridge_same_level_events`（`detect.py:87`，判据 `ev.level != prev.level` 见 `detect.py:105`）。它把"样本落在非基线电平"等同于"处于事件内"，于是两类信号被截断：

- **A 毛刺型阻孔**（图 2／图 4）：事件体内大量毛刺回落，甚至**越过**开孔电流。
  - 回落到开孔 → 产生一段基线 run，事件被切开；靠同电平桥接勉强能合并，但受 `ignore_event_duration_ms`（默认 50 ms）硬限。
  - 越过开孔 → 在 `polarity=0` 下归到反方向电平，`level` 索引变化 → 同电平桥接**失效**；在单极性下被极性判据剔除，同样割裂。
- **B 站孔上下跳跃**（图 3）：电流在开孔与阻孔（及中间电平）间快速来回跳 → `level` 索引不断变化 → 一次驻留被切成多段事件。DEVLOG 已记录 `both` 模式会大面积过检（SLR 242→1055）。

**目标**：新增一种**默认关闭**的检测模式，把「**是不是事件（分割）**」与「**是哪个电平（量化）**」解耦；A、B 两类信号各得到**一个连续事件**；并能在 GUI 里选模式、调参、实时重跑。

**硬约束**：默认 `event_mode="level"`，不改动任何现有行为；`pytest` 全绿（含现有全部回归）。

---

## 2. 设计概览

把"事件边界"建立在**阻孔指示器 + 去抖**上，而不是即时电平归属：

```
I0(t) 开孔参考（默认用常量 level0；可选动态基线，见 §6 扩展）
  → d(t) = current - level0
  → 阻孔指示 b(t) =（按 polarity）sign·d > enter  或  |d| > enter
  → 去抖（形态学）：
       ① 填「非阻孔」短于 min_gap 的空隙   → 吸收毛刺（含越过开孔），一次驻留不被切断
       ② 丢「阻孔」短于 min_block 的碎片   → 尖峰不新生事件
  → 每个存活阻孔区间 = 一个事件
  → 事件电平 = 区间内「确实阻孔」样本的稳健中位数
```

为什么同时覆盖两类：

- **A**：越过开孔的样本在指示器里就是"非阻孔"（|d| 小或反向）。只要该空隙短于 `min_gap` 就被填掉——**与毛刺方向无关**，这正是同电平桥接做不到的。
- **B**：每次回到开孔的时长若短于 `min_gap` 被填掉；只有持续更久的真正离开才切分。`min_gap` 即 burst 分隔阈值。

---

## 3. 算法规格（伪码，务必按此实现）

```python
# 输入：current（已可选低通）、sample_rate_hz、level0、level1、polarity、cfg
step = abs(level1 - level0)
if step <= 0:                      # 退化：无有效电平尺度
    return DetectionResult([], levels, sr, level0, np.array([]))
sign = 1.0 if level1 > level0 else -1.0
enter = cfg.burst_enter_frac * step
exit_  = cfg.burst_exit_frac  * step
n = len(current); dt = 1.0 / sample_rate_hz
min_gap_n   = max(1, round(cfg.burst_min_gap_ms   * 1e-3 * sr))
min_block_n = max(1, round(cfg.burst_min_block_ms * 1e-3 * sr))
tau_s = tau_samples_for(sr, cutoff_hz)     # 复用 detect.py:65
trim  = int(round(2 * tau_s))
pre_n = int(round(cfg.pre_event_ms * 1e-3 * sr))

# 1) 阻孔指示器
d = current - level0
if polarity != 0:
    b = (sign * d) > enter
else:
    b = np.abs(d) > enter

# 2) 去抖（纯 numpy run-length，勿引入 scipy.ndimage，保持 detect.py 仅依赖 numpy）
b = _fill_short_runs(b, value=False, max_len=min_gap_n)     # False 游程 < min_gap_n → True
b = _drop_short_runs(b, value=True,  max_len=min_block_n)   # True  游程 < min_block_n → False

# 3) 提取阻孔区间（True 游程），忽略贴记录首尾者（与 detect.py:302 口径一致）
for (s, e) in _runs(b, value=True):
    if s == 0 or e == n:  continue
    body = current[s + trim:e - trim] if (e - s) > 2 * trim else current[s:e]
    if body.size == 0:    body = current[s:e]
    if polarity != 0:
        sel = body[sign * (body - level0) > exit_]     # 只用"确实阻孔"方向样本
    else:
        sel = body[np.abs(body - level0) > exit_]
    amp = float(np.median(sel)) if sel.size else float(np.median(body))
    local0 = float(np.median(current[max(0, s - pre_n):s])) if s > 0 else level0
    depth = amp - local0
    level = int(np.clip(round(depth / step), -8, 8))
    state = "B" if (e - s) < int(round(4 * tau_s)) else "A"
    events.append(Event(start_s=s*dt, end_s=e*dt, amplitude_pA=amp, depth_pA=depth,
                        level0_ref_pA=local0, level=level, state=state))

level0_refs = np.array([ev.level0_ref_pA for ev in events])
return DetectionResult(events, build_levels(level0, level1, polarity), sr, level0, level0_refs)
```

要点：

- **`_fill_short_runs` / `_drop_short_runs`**：run-length 编码后按游程长度翻转值；参考 `detect.py:190-193` 的 RLE 写法。等价的 `scipy.ndimage.binary_closing/binary_opening` **不采用**，以保持 `detect.py` 只依赖 numpy、且行为可逐样本单测。
- **顺序固定**：先填空隙、再丢碎片。先填后丢，保证"被填合的相邻两段若合起来仍太短则整体丢弃"。
- **`Event` 字段契约**：下游 `compute_features` 只读 `start_s / end_s / level0_ref_pA / state`（见 `features.py:110-178`），绘图理想化线只用 `df` 的 `Io` 与 `mean`（`waveview.py:228-249`）。`amplitude_pA / depth_pA / level` 仅 `detect.py` 内部使用，故新模式可自由构造，**下游零改动**。
- **对特征表的影响**（预期且合理）：burst 把一段结构合成一个事件后，`std / skew / kurt / iqr / outlier_ratio` 会反映体内结构；`mean` 仍是 3σ 去毛刺后的均值（`features.py:146-154`）。无需改 `features.py`，但需在 README 说明该语义。

---

## 4. 新增参数（`nanopore/config.py`，全部默认关/零回归）

追加到 `PipelineConfig`（`config.py:11`），放在 event detection 段内：

| 字段 | 类型 | 默认 | 含义 |
|------|------|------|------|
| `event_mode` | str | `"level"` | `"level"`=现有算法；`"burst"`=驻留包络去抖 |
| `burst_enter_frac` | float | `0.30` | 阻孔进入阈值（×step）；单侧按 polarity，双侧取绝对值 |
| `burst_exit_frac` | float | `0.20` | 事件电平取样阈值（×step，< enter） |
| `burst_min_gap_ms` | float | `30.0` | 容忍的"回到开孔"时长（毛刺容差 / burst 分隔阈值）——**主调钮** |
| `burst_min_block_ms` | float | `2.0` | 阻孔最短时长（尖峰地板） |

- `PipelineConfig.load`（`config.py:89`）已按 `fields(cls)` 过滤未知键，**旧 JSON 协议向后兼容**，无需改动。
- CLI `--config`／GUI「存参数／读参数」自动带上新参数。

---

## 5. 代码改动清单（逐文件）

### 5.1 `nanopore/detect.py`
1. 新增 `detect_events_burst(current, sample_rate_hz, level0, level1, polarity, *, cutoff_hz, pre_event_ms, burst_enter_frac, burst_exit_frac, burst_min_gap_ms, burst_min_block_ms) -> DetectionResult`（§3）。
2. 新增两个纯 numpy 辅助：`_fill_short_runs(b, value, max_len)`、`_drop_short_runs(b, value, max_len)`（或统一的 `_debounce(b, gap_n, block_n)`），以及 `_runs(b, value)`。
3. 新增**统一入口**（消除三处重复的 `detect_events(...)` 调用，防止参数漂移）：
   ```python
   def detect(current, sample_rate_hz, lv, cfg, *, cutoff_hz=None) -> DetectionResult:
       """按 cfg.event_mode 分派；lv 需具备 .level0/.level1/.polarity（鸭子类型，勿 import baseline）。"""
       if getattr(cfg, "event_mode", "level") == "burst":
           return detect_events_burst(current, sample_rate_hz, lv.level0, lv.level1, lv.polarity,
                                      cutoff_hz=cutoff_hz or cfg.filter_lowpass_hz,
                                      pre_event_ms=cfg.pre_event_ms,
                                      burst_enter_frac=cfg.burst_enter_frac,
                                      burst_exit_frac=cfg.burst_exit_frac,
                                      burst_min_gap_ms=cfg.burst_min_gap_ms,
                                      burst_min_block_ms=cfg.burst_min_block_ms)
       return detect_events(current, sample_rate_hz, lv.level0, lv.level1, ...)   # 现状，逐参不变
   ```
   `detect_events` 本体**不改**。

### 5.2 三处调用点改为 `detect(...)`
- `nanopore/pipeline.py:66-80`：替换整段为 `det = detect(filtered, rec.sample_rate_hz, lv, cfg, cutoff_hz=cutoff)`。
- `nanopore/gui/controller.py:49-63`：同上，`det = detect(filtered, rec.sample_rate_hz, lv, self.cfg, cutoff_hz=cutoff)`。
- `nanopore/roi.py:61-75`：同上，`det = detect(filtered, sr, lv, cfg, cutoff_hz=cutoff)`。
  > 注意 `roi` 传的 `lv` 已过 `set_polarity`（`roi.py:50-53`），`lv.polarity` 为最终值，分派读它即可。

### 5.3 `nanopore/cli.py`（`build_parser`，`cli.py:18-30` 内）
```python
r.add_argument("--event-mode", choices=("level", "burst"), default="level")
r.add_argument("--burst-enter-frac", type=float, default=None)
r.add_argument("--burst-exit-frac",  type=float, default=None)
r.add_argument("--burst-min-gap-ms",   type=float, default=None)
r.add_argument("--burst-min-block-ms", type=float, default=None)
```
`main` 中在 config 载入后（`cli.py:46-56` 一带）逐项 `if x is not None: cfg.<field> = x`。

### 5.4 `nanopore/gui/parampanel.py`（**用户要求：GUI 可直接选、调试**）
1. 新增控件（`__init__`，约 `parampanel.py:59-61` `self.polarity` 附近）：
   ```python
   self.mode = QComboBox()
   self.mode.addItem("电平法（现状）", "level")
   self.mode.addItem("驻留包络去抖（毛刺/多电平）", "burst")
   self.b_enter = _spin(0.0, 2.0, 0.30, "", 0.05)
   self.b_exit  = _spin(0.0, 2.0, 0.20, "", 0.05)
   self.b_gap   = _spin(0.0, 5000.0, 30.0, " ms", 5.0)
   self.b_block = _spin(0.0, 2000.0, 2.0, " ms", 0.5)
   ```
2. 加**中文 tooltip**（沿用 `_tip` 风格，`parampanel.py:63-107`）：
   - `self.mode`：`检测模式\n电平法=现状（逐样本最近电平+同电平桥接）。\n驻留包络去抖=把一次阻孔（含体内毛刺、越过开孔、上下跳跃）合并为一个事件；\n适用于毛刺型与多电平跳跃信号。`
   - `self.b_enter`：`阻孔进入阈值（×电平步长）\n|电流−开孔| 超过该比例才算进入阻孔。0.30 表示 30% 步长。`
   - `self.b_exit`：`事件电平取样阈值（×步长）\n估事件电平时，只取超过此比例的样本（<enter，避免边缘过渡混入）。`
   - `self.b_gap`：`毛刺/开孔容差（ms）\n回到开孔的时长短于它就不切断事件（吸收毛刺、合并跳跃）。\n调大：更不容易被切碎、但可能把相邻真事件并成一个；调小：反之。`
   - `self.b_block`：`最短阻孔（ms）\n短于此的阻孔碎片丢弃（滤孤立尖峰，不新建事件）。`
3. `form.addRow(...)`（约 `parampanel.py:111-125`）：新增「检测模式」行 + 四行 burst 参数。
4. `_sync_mode()`：当 `self.mode.currentData()=="burst"` 时 `setEnabled(True)`，否则禁用四个 burst 控件；接 `self.mode.currentIndexChanged.connect(self._sync_mode)`，`__init__` 末尾调用一次。
5. `build_config`（`parampanel.py:144-161`）：加
   ```python
   event_mode=self.mode.currentData(),
   burst_enter_frac=self.b_enter.value(),
   burst_exit_frac=self.b_exit.value(),
   burst_min_gap_ms=self.b_gap.value(),
   burst_min_block_ms=self.b_block.value(),
   ```
6. `load_config`（`parampanel.py:163-183`）：回填五值，末行调 `self._sync_mode()`。
7. 调试闭环：沿用现有「重跑检测」按钮（`parampanel.py:127,185-192` → `controller.set_config + rerun`）。改模式/参数后点它，波形蓝色理想化线与事件表即时更新，即可判断合并是否合理。

---

## 6. 扩展（本版不做，记为后续）
- `burst_use_dynamic_i0`：用 `baseline_i0.build_dynamic_baseline` 的 I0(t) 取代常量 level0，抗漂移（需把 `i0_profile` 传入检测；与现流水线解耦后再做）。
- 多电平上报：`DetectionResult` 增子电平数 `n_levels`、内部开孔占比，供特征表区分单/多电平事件（需动 `features.py`）。
- HMM / Viterbi 理想化（QUB 式）：最严谨，作为 v3 备选。

---

## 7. 验证 harness（测试先行）

### 7.1 扩充 `tests/synth.py`
- `inject_glitches(sig, event_index, glitches, *, return_amp_pA, overshoot_pA)`：在指定事件体内把若干时间窗的样本改写为「回落到开孔」或「越过开孔（反向）」的短毛刺。
- `make_multilevel_blocks(...)`：生成 0 / L1 / L2 之间快速切换的驻留块（含 < `min_gap` 的开孔间隙）。

### 7.2 新增 `tests/test_detect_burst.py`（合成真值）
| 用例 | 构造 | 断言 |
|------|------|------|
| C1 毛刺回落 | 1 阻孔 + 体内多处回落到开孔（各 < min_gap） | burst → **1** 事件；level 模式 → **>1**（对照，证明确有改进） |
| C2 越过开孔 | 1 阻孔 + 体内毛刺**越过**开孔（反向，且 < min_gap） | burst → **1** 事件 |
| C3 多电平跳跃 | 0↔L1↔L2 快切，开孔间隙 < min_gap | burst → **1** 事件 |
| C4 防过并 | 两个真事件，间隔 > min_gap | burst → **2** 事件 |
| C5 尖峰地板 | 孤立窄尖峰（< min_block） | burst → **0** 事件 |
| C6 首尾 | 阻孔贴记录首/尾 | 不注册（与 `detect.py:302` 口径一致） |
| C7 零回归 | `event_mode="level"` 对既有合成信号 | 逐字段与 `detect_events` 直接调用**完全一致** |

### 7.3 实样验收（`_overview.png` 蓝色理想化线叠加对照）
- 干净文件（Ala / Asp / His）：`event_mode=level` 下事件数与改动前**一致**（零回归）。
- 目标 A／B 文件：burst 模式事件数显著下降（≈1 事件/驻留），理想化线覆盖整段且**不跨越真事件间隔**。

### 7.4 命令
```bash
py -3.13 -m pytest -q
python -m nanopore run "abf数据案例/abf数据案例/Ala.abf" -o output_burst --event-mode burst
python -m nanopore gui "abf数据案例/abf数据案例/Ala.abf"   # GUI 手调
```

---

## 8. 验收标准
1. `pytest` 全绿；C7 零回归用例通过。
2. `event_mode="level"` 时，所有既有实样的事件数/特征表与改动前逐值一致。
3. A、B 两类目标文件在 burst 模式下各得到一个连续事件，理想化线不切断、不过并。
4. GUI：模式下拉可切换；burst 参数仅在 burst 模式可编辑；改参数点「重跑检测」即时刷新波形/事件表/散点。
5. README「参数说明」与 `DEVLOG.md` 已更新（新增 `event_mode` 与四个 burst 参数、语义与调参建议）。

---

## 9. 风险与回滚
- **过并**：`burst_min_gap_ms` 过大时两个相邻真事件被并成一个。**必须**用已知事件数的干净文件卡阈值，不能凭手感。
- **真反向短事件被吞**：越过开孔的毛刺若其实是真实反向短事件（罕见），默认并入主事件；靠 `burst_min_block_ms` 兜底并对比事件数变化察觉。
- **step 退化**：混合样多平台时 `level1` 的代表性差。burst 面向单/双电平驻留；退化时（`step<=0`）返回空并提示。
- **回滚**：只增不改，`event_mode` 默认 `"level"`；异常时切回即可，无迁移成本。

---

## 10. 工作流与检查点
1. 确认 §0 阻塞项（文件名 + 事件语义）。
2. 先写 §7 测试（红），再实现 §3 算法与 §5.1–5.2（绿）。
3. 接 GUI（§5.4）与 CLI（§5.3），实样对照验收（§7.3）。
4. 更新 README / DEVLOG；PR 走 `CONTRIBUTING.md` 检查清单。
