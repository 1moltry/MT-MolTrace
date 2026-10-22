# MOLTRACE — 单分子纳米孔电流信号分析

**MOLTRACE** MT by 1moltry for Huang Lab：纳米孔数据处理平台，基于此的多算法开发实现更定制化的事件查找、指纹处理、自动化流程

它读取 `.abf` 电流记录，自动完成事件分割、特征提取和异常剔除，并导出 Excel、图片和 MATLAB 数据。软件在本机运行，数据不上传。

当前代码版本：`v3.0.0`。仓库：<https://github.com/1moltry/MT-MolTrace>。

> **本项目不提供免安装的 exe。** 软件以源码方式发布，用 GitHub Desktop 一次性克隆到电脑，之后点一下就能更新到最新版。第一次需要安装 Python，约 5～15 分钟；以后每次更新只需 1 分钟。

## 30 秒看懂

1. 装一次 Python 和 GitHub Desktop。
2. 把仓库克隆到电脑，双击 `MOLTRACE.bat`，脚本自动装依赖并打开界面。
3. 以后要最新版：打开 GitHub Desktop，点 **Pull origin**，再双击 `MOLTRACE.bat`。

| 你的目的 | 推荐方式 | 需要准备 |
|---|---|---|
| 用软件的最新版 | GitHub Desktop 克隆后双击启动 | GitHub 账号、Python 3.11+（一次装好） |
| 不想装 GitHub Desktop | 下载 ZIP 后双击启动 | Python 3.11+；更新时重新下载 |
| 改代码、提改动 | Fork（复刻）后按开发流程提交 | 同上，另加 Git 基础 |
| 只想知道有没有更新 | 仓库页点 **Watch** 收邮件 | GitHub 账号 |

> **Fork 不是更新方式。** Fork 只是把仓库复制一份到你的账号下，作者的更新不会自动流进来，必须手动点 **Sync fork**。只想用软件的人不要 Fork，直接克隆主仓库。

## 1. 一次性准备（只做一次）

### 1.1 注册 GitHub 账号

打开 <https://github.com/signup>，按提示注册。邮箱激活后即可。

### 1.2 安装 Python

1. 打开 <https://www.python.org/downloads/>，下载 Windows 安装包（3.11 或更高）。
2. 运行安装包，在第一个界面**勾选 `Add python.exe to PATH`**，再点 `Install Now`。
3. 装完关掉窗口即可，不需要打开命令行。

> 这一步不能省。`Add python.exe to PATH` 没勾选，双击启动脚本时会提示“没有找到 Python”。补救办法：重新运行安装包，选 `Modify`，把这一项勾上。

### 1.3 安装 GitHub Desktop

1. 打开 <https://desktop.github.com/>，下载并安装。
2. 首次打开，选 `Sign in to GitHub.com`，用 1.1 的账号登录。
3. 登录后停在欢迎页即可。

GitHub Desktop（GitHub 桌面客户端）：一个用鼠标完成克隆、同步、查看改动的图形界面，不需要敲 Git 命令。

## 2. 第一次安装 MOLTRACE

### 2.1 克隆仓库

1. 在 GitHub Desktop 菜单点 **File → Clone repository…**。
2. 选 **URL** 标签，粘贴仓库地址：

```
https://github.com/1moltry/MT-MolTrace.git
```

3. `Local path` 选一个固定位置，例如 `D:\MOLTRACE`。**不要放在 OneDrive、桌面同步目录或有空格的路径下。**
4. 点 **Clone**，等进度条结束。

克隆（Clone）：把仓库完整下载到电脑，并记住它来自哪里，以后才能一键同步。

### 2.2 启动

1. 菜单点 **Repository → Show in Explorer**，打开克隆下来的文件夹。
2. 双击 `MOLTRACE.bat`。
3. 首次运行会弹出一个黑色窗口，显示“正在安装依赖”，**不要关闭它**。整个过程约 5～15 分钟，取决于网速。
4. 安装完成后界面自动打开，黑窗口消失。以后每次双击只需几秒。

脚本做了三件事：在文件夹里建一个独立的 Python 环境 `.venv`、安装依赖、启动界面。它不会改动系统里的 Python，也不会写注册表。

### 2.3 放实验数据

把 `.abf` 文件或文件夹放进克隆目录下的 `abf数据案例/`：

```
D:\MOLTRACE\
├── MOLTRACE.bat
├── abf数据案例\          ← 数据放这里（不会上传，也不会被更新覆盖）
│   └── 你的数据\
└── output\               ← 结果默认导出到这里
```

详见 [data/README.md](data/README.md)。数据目录已加入 `.gitignore`，Git 不会上传它，更新代码也不会删它。

## 3. 以后更新到最新版

### 3.1 同步代码

1. 打开 GitHub Desktop，确认左上角仓库是 `MT-MolTrace`。
2. 点顶部的 **Fetch origin**（获取远端更新）。
3. 如果作者有新提交，按钮会变成 **Pull origin**，再点一次。
4. 上方 **History** 出现新的提交记录，说明已是新版。

GitHub Desktop 开着时会定时检查更新。没有变化时按钮一直是 `Fetch origin`，属于正常。

### 3.2 重新启动

关闭软件，再双击 `MOLTRACE.bat`。若本次更新改了依赖，脚本会自动补装，等黑窗口结束即可。

### 3.3 为什么更新不会丢数据

`abf数据案例/`、`output/` 和 `.venv/` 都在 `.gitignore` 里，Git 不管这些目录。更新只替换代码和文档。**不要手动修改仓库里的代码文件**，否则同步时可能冲突；只调参数请在软件里“存参数”。

### 3.4 想收到更新提醒

打开仓库页 <https://github.com/1moltry/MT-MolTrace>，点右上角 **Watch → All Activity**。有更新时 GitHub 会发邮件。邮件只负责提醒，真正更新仍按 3.1 操作。

## 4. 不想装 GitHub Desktop

### 4.1 下载 ZIP

1. 打开仓库页，点绿色的 **Code** 按钮，选 **Download ZIP**。
2. 解压到一个固定目录，例如 `D:\MOLTRACE`。
3. 装好 Python 后，双击 `MOLTRACE.bat`，流程同 2.2。
4. 缺点是**没有一键更新**。要新版时重新下载 ZIP，解压覆盖旧目录；`abf数据案例/` 和 `output/` 不会被覆盖。

### 4.2 命令行

```bash
git clone https://github.com/1moltry/MT-MolTrace.git
cd MT-MolTrace
```

之后双击 `MOLTRACE.bat` 即可。更新用：

```bash
git pull
```

## 5. Fork 是什么，什么时候用

| 操作 | 结果 | 适合谁 |
|---|---|---|
| Clone（克隆） | 下载到电脑，可一键同步上游 | 只想用软件的人 |
| Fork（复刻） | 在你的账号下复制一份，可自由改 | 想改代码并提交回来的人 |
| Download ZIP | 下载源码快照，没有同步能力 | 偶尔看一眼、不打算更新的人 |

Fork 之后要拿作者的更新，必须手动同步：

1. 打开你的 Fork 页面。
2. 点 **Sync fork → Update branch**。

想改代码并提交，完整流程见 [CONTRIBUTING.md](CONTRIBUTING.md) 和第 10 节。

## 6. 出问题先看这里

**双击 `MOLTRACE.bat` 后黑窗口一闪就没了。**
双击 `MOLTRACE-debug.bat`，它会保留窗口并显示完整报错。把最后几行发到 [Issues](https://github.com/1moltry/MT-MolTrace/issues)。

**提示“没有找到 Python”。**
安装 Python 时没勾 `Add python.exe to PATH`。重新运行安装包 → `Modify` → 勾选后完成。

**依赖安装失败或卡住。**
脚本会自动改用清华镜像重试一次。仍失败时，检查网络和代理，或手动执行：

```bat
.venv\Scripts\python -m pip install -e ".[gui]" -i https://pypi.tuna.tsinghua.edu.cn/simple
```

**移动了文件夹后打不开。**
`.venv` 里记录的是绝对路径。删掉 `.venv` 文件夹，再双击 `MOLTRACE.bat`，重新安装一次。

**双击没有反应，也没有窗口。**
检查安全软件是否拦截了 `.bat`；确认解压/克隆完整，`MOLTRACE.bat` 与 `pyproject.toml` 在同一层。

**界面能开，但导入数据后没有事件。**
先看波形有没有明显阻孔，再检查检测算法、Level0/Level1 和阈值。点“全览”确认数据已加载。

**结果准不准？**
算法有实验室样例回归测试，但自动检测总有边界情况。正式统计前，请抽查波形、事件表和剔除表。

**数据会上传吗？**
不会。软件只在本机读写文件。

**支持 Mac 或 Linux 吗？**
启动脚本是 Windows 版。其他系统可以从源码运行，见 [DEVELOPMENT.md](DEVELOPMENT.md)。

## 7. 第一次打开软件（5 分钟）

1. 启动后进入首页工作台。
2. 点“单文件分析”，选择一个 `.abf`。
3. 在顶部工作栏选择检测算法，右侧参数只显示当前算法的参数。
4. 点左侧事件表的任意一行，主图和下方切片会跳到该事件。
5. 点“算法对比…”可以并排看三种算法的数量与边界差异。
6. 要导出结果，点“批量处理…”，选文件和输出目录，点“开始处理”。

首页四个入口：

| 入口 | 作用 |
|---|---|
| 单文件分析 | 打开一个 `.abf`，查看波形与事件 |
| 批量处理 | 选文件或文件夹，用同一套参数导出 |
| 算法对比 | 同一文件并排比较三种检测算法 |
| 使用教程 | 打开完整教程 |

首页下方是“最近打开”，双击即可继续上次的文件。单文件界面只用于查看，不写文件；导出走“批量处理…”。

## 8. 三种事件检测算法

顶部工作栏“检测算法”可选：

| 算法 | 适合的信号 | 特点 |
|---|---|---|
| 电平法（Clampfit 语义） | 常规单通道、多电平、肽 | 逐样本归到最近电平，边界在 50% 交叉 |
| 驻留包络（burst） | 抖动、毛刺、基线上下跳 | 把一次阻孔内的碎片合并成一个事件 |
| 平台滞回（sweep/plateau） | 糖、长阻孔、事件内有部分恢复 | 边界贴近开孔，部分恢复不切碎事件 |

平台滞回的默认参数按糖数据标定（进入 60 pA、退出 15 pA、短开孔 1 ms）。换数据集时，先在单文件里看波形和事件表，再批量处理。

三种算法共用同一套后处理、特征表和导出格式；切换算法不会改变输出文件的结构。

### 8.1 算法对比怎么用

1. 打开一个文件，或从首页点“算法对比”再选文件。
2. 勾选 2～3 种算法，点“开始对比”。
3. 表格给出原始/保留事件数、中位驻留、中位深度、用时、与基准算法的匹配数和边界差。
4. 图上彩色标记是各算法的事件起点和终点；滚轮缩放可看局部差异。
5. 选中表格一行，点“用选中算法查看”，回到分析界面用该算法重跑。

对比只读，不写事件表。确定算法后再走“批量处理”导出。

## 9. 输出什么

每个 `.abf` 至少生成一个事件表。勾选模块后，还会生成图片、MATLAB 波形和批次汇总。

| 文件 | 内容 | 何时生成 |
|---|---|---|
| `<文件名>_events.xlsx` | 事件特征表；另有 `excluded`、`anomalies` 工作表 | 总是 |
| `<文件名>_events.mat` | 每个事件的原始电流序列 | 勾选“事件波形导出” |
| `<文件名>_overview.png` | 全程波形、事件标记、异常区间 | 勾选“输出图” |
| `<文件名>_scatter.png` | 深度-时长散点等 | 勾选“输出图” |
| `<文件名>_hist.png` | 深度和时长直方图 | 勾选“输出图” |
| `summary.xlsx` | 每个文件一行的事件数、有效率、异常计数 | 勾选“批次汇总” |
| `dataset_all.csv` | 所有文件的保留事件合并表 | 勾选“合并训练表” |

## 10. 改代码并提交（开发者）

1. 在 GitHub 网页点 **Fork**。
2. 按第 2 节把 Fork 克隆到本地。
3. 新建分支：

```bash
git checkout -b fix/my-change
```

4. 修改代码或文档。
5. 运行测试，确认全绿：

```bash
python -m pytest tests -q
```

6. 提交并推送：

```bash
git add 修改的文件
git commit -m "fix: 一句话说明改了什么"
git push origin fix/my-change
```

7. 回到 GitHub 页面，点 **Compare & pull request**，写清问题和改动。
8. 等作者审查。审查意见会出现在 PR 页面。

只改软件参数、不改代码时不需要 Fork：在软件里调参数，点“存参数”保存为 JSON 即可。

## 11. 常用命令

```bash
moltrace gui                                              # 打开首页工作台
moltrace run "abf数据案例/abf数据案例" -o output            # 批量处理
moltrace run "文件.abf" -o output --detector plateau       # 指定检测算法
python -m pytest tests -q                                  # 运行测试
```

`python -m nanopore` 是旧别名，仍可使用。命令需在已激活的 `.venv` 中运行：

```bat
.venv\Scripts\activate
```

## 12. 反馈问题

1. 打开 [Issues](https://github.com/1moltry/MT-MolTrace/issues)，点 **New issue**。
2. 选择 bug 报告或功能建议模板。
3. 写清以下信息：
   - 软件版本（例如 `v3.0.0`）。
   - 文件类型和大致场景。
   - 复现步骤。
   - 预期结果和实际结果。
   - 报错原文或截图。
4. 不要上传未公开的实验数据。可以换成合成信号或脱敏片段。

## 13. 详细教程

完整的界面说明、参数解释、批量处理、MATLAB 对接和故障排查，见 [tutorial.md](tutorial.md)。

## 14. 许可与作者

MIT 许可证，见 [LICENSE](LICENSE)。

由 Huang Lab 的 Yize Liu（1moltry）开发与维护。产品名 **MOLTRACE（摩尔迹）**，仓库 `MT-MolTrace`。
