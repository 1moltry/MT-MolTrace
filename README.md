# MOLTRACE · 摩尔迹 — 单分子纳米孔电流迹分析

**MOLTRACE（摩尔迹）** 是 1moltry 为课题组做的单分子纳米孔电流迹分析工作台：从一摩尔到单分子。

它读取 `.abf` 电流记录，自动完成事件分割、特征提取和异常剔除，并导出 Excel、图片和 MATLAB 数据。软件在本机运行，数据不上传。

当前代码版本：`v3.0.0`。仓库：<https://github.com/1moltry/MT-MolTrace>。

## 先选一种用法

| 你的目的 | 推荐方式 | 需要准备 | 从哪里开始 |
|---|---|---|---|
| 只想分析数据 | 下载发行包 | Windows 电脑 | 第 1 节 |
| 想改代码、改参数、参与开发 | Fork（复制仓库）后从源码运行 | GitHub 账号、Python、Git 或 GitHub Desktop | 第 2～4 节 |
| 想反馈问题或提建议 | 新建 Issue（问题单） | GitHub 账号 | 第 6 节 |
| 想跟进后续更新 | Watch（关注）或同步自己的 Fork | GitHub 账号 | 第 5 节 |

发行包是给“只要用软件”的同事；源码方式给“要改、要看、要参与”的人。两种方式功能相同。

## 1. 直接用软件（不需要 GitHub 账号）

1. 打开 [Releases 页面](https://github.com/1moltry/MT-MolTrace/releases)。
2. 在 **Assets** 里下载最新发行包，文件名形如 `MOLTRACE_v3.0.0_win64.zip`。
3. 右键 zip，选择“全部解压缩”。
4. 打开解压后的文件夹，双击 `MOLTRACE.exe`。
5. 第一次运行，Windows 可能提示“Windows 已保护你的电脑”。点“更多信息”，再点“仍要运行”。

> **不要只把 exe 拷走。** exe 旁边的 `_internal` 文件夹必须保留，否则程序无法启动。
>
> 建议解压到硬盘目录，例如 `D:\MOLTRACE`。解压后约 250 MB。

如果 Releases 页面还没有对应版本，可以按第 3 节从源码运行，或向作者索取 zip。

### 1.1 首页四个入口

启动后先看到首页工作台：

| 入口 | 作用 |
|---|---|
| 单文件分析 | 打开一个 `.abf`，查看波形与事件 |
| 批量处理 | 选文件或文件夹，用同一套参数导出 |
| 算法对比 | 同一文件并排比较三种检测算法 |
| 使用教程 | 打开完整教程 |

首页下方是“最近打开”，双击即可继续上次的文件。

## 2. 第一次用 GitHub：先认识七个词

GitHub 是一个存放代码和版本的网站。这个项目的全部代码、文档和更新都在这里。

| 词 | 意思 | 在本项目里怎么用 |
|---|---|---|
| 仓库（repository） | 一个带版本历史的项目文件夹 | `MT-MolTrace` |
| Fork（复刻） | 把仓库复制到你的 GitHub 账号下 | 想改代码时先 Fork |
| Clone（克隆） | 把仓库下载到你的电脑，并保留 Git 历史 | 本地运行或开发 |
| Commit（提交） | 在本地保存一个版本快照 | 每完成一小步就提交 |
| Push（推送） | 把本地提交上传到 GitHub | 推送到你的 Fork |
| Pull Request（PR） | 请求作者把你的改动合并进主仓库 | 改完后发起 PR |
| Issue（问题单） | 报告 bug、提建议、问问题 | 不写代码也能用 |
| Release（发行版） | 打包好的可执行版本 | 第 1 节的 zip |

> 不想敲命令：安装 [GitHub Desktop](https://desktop.github.com/)（图形界面），用鼠标完成 Fork、Clone、Commit 和 Push。第 3.1 节给出步骤。

### 2.1 Fork、Clone、Download ZIP 的区别

| 操作 | 结果 | 什么时候用 |
|---|---|---|
| Fork | 你的账号下多一份仓库，可以自由改 | 想改代码并提交给作者 |
| Clone | 仓库下载到电脑，保留完整历史 | 本地运行、开发、同步更新 |
| Download ZIP | 下载一份不带 Git 历史的源码快照 | 只想看代码，不打算提交 |

只想运行软件，不必 Fork；直接 Clone 主仓库即可。

## 3. 从源码运行（推荐给要改代码的人）

源码方式需要 Python 3.11 或更高版本。Git 可以用命令行，也可以用 GitHub Desktop。

### 3.1 方式 A：GitHub Desktop（不写命令）

1. 注册并登录 GitHub。
2. 打开 <https://github.com/1moltry/MT-MolTrace>，点右上角 **Fork**，得到你自己的仓库地址，形如 `https://github.com/<你的用户名>/MT-MolTrace`。
3. 安装并登录 GitHub Desktop。
4. 点 **File → Clone repository → URL**，粘贴你的 Fork 地址，选择本地目录，点 **Clone**。
5. 安装 Python 3.11 或更高版本。安装时勾选 **Add Python to PATH**。
6. 在 GitHub Desktop 菜单里点 **Repository → Open in Command Prompt**（Mac 上是 **Open in Terminal**）。
7. 在终端里依次运行：

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
python -m nanopore gui
```

第 4 行也可以写成 `moltrace gui`（安装后可用）。如果不想开终端，安装完成后也可以双击仓库根目录的 `MOLTRACE.bat`。

### 3.2 方式 B：命令行

```bash
git clone https://github.com/1moltry/MT-MolTrace.git
cd MT-MolTrace
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
moltrace gui
```

如果你 Fork 过，把第一行换成你的 Fork 地址。

不想用 Git 也可以：在仓库页点 **Code → Download ZIP**，解压后进入目录，从 `python -m venv .venv` 开始执行。

### 3.3 数据放在哪里

实验数据 `.abf` 很大，不入库。把数据放到仓库根目录下的 `abf数据案例/`，目录结构见 [data/README.md](data/README.md)。没有数据也能运行测试和界面，只是不能做实际分析。

### 3.4 常用命令

```bash
moltrace gui                                              # 打开首页工作台
moltrace run "abf数据案例/abf数据案例" -o output            # 批量处理
moltrace run "文件.abf" -o output --detector plateau       # 指定检测算法
python -m pytest tests -q                                  # 运行测试
```

`python -m nanopore` 是旧别名，仍可使用。

## 4. 修改并提交：Fork 工作流

1. 在 GitHub 网页点 **Fork**。
2. 按第 3 节把 Fork Clone 到本地。
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

只改软件参数、不改代码时，不需要 Fork。直接在软件里调参数，点“存参数”保存为 JSON 即可。

## 5. 更新你的 Fork

GitHub 网页方式：

1. 打开你的 Fork 页面。
2. 点 **Sync fork → Update branch**。

命令行方式：

```bash
git remote add upstream https://github.com/1moltry/MT-MolTrace.git
git fetch upstream
git merge upstream/main
git push origin main
```

本地有未提交改动时，先 commit 或 stash，再合并。

## 6. 反馈问题

1. 打开 [Issues](https://github.com/1moltry/MT-MolTrace/issues)，点 **New issue**。
2. 选择 bug 报告或功能建议模板。
3. 写清以下信息：
   - 软件版本（例如 `v3.0.0`）。
   - 文件类型和大致场景。
   - 复现步骤。
   - 预期结果和实际结果。
   - 报错原文或截图。
4. 不要上传未公开的实验数据。可以换成合成信号或脱敏片段。

## 7. 软件怎么用（5 分钟）

1. 双击 `MOLTRACE.exe`，进入首页。
2. 点“单文件分析”，选择一个 `.abf`。
3. 在顶部工作栏选择检测算法，右侧参数只显示当前算法的参数。
4. 点左侧事件表的任意一行，主图和下方切片会跳到该事件。
5. 点“算法对比…”可以并排看三种算法的数量与边界差异。
6. 要导出结果，点“批量处理…”，选文件和输出目录，点“开始处理”。

单文件界面只用于查看，不写文件。导出走“批量处理…”。

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

## 10. 常见问题

**一定要用 GitHub 吗？** 不需要。只想分析数据，下载 Releases 里的 zip 即可。

**Fork 和 Clone 有什么区别？** Fork 是复制到自己账号下，方便改完提交；Clone 是下载到电脑，方便运行。只想用软件，Clone 主仓库或直接下载 zip 就够了。

**为什么仓库里没有实验数据？** `.abf` 文件很大，且属于实验产物，不适合放进 Git。数据放在本地 `abf数据案例/`，已加入 `.gitignore`。

**双击没有反应？** 确认 zip 已完整解压，exe 和 `_internal` 在同一层。若仍无反应，运行 `MOLTRACE-debug.bat`（源码方式）或把 exe 拖进命令提示符查看报错。

**为什么没有图？** 默认只导出事件表。在“参数 → 模块”里勾选“输出图”。

**为什么没有事件？** 先看波形有没有明显阻孔，再检查检测算法、Level0/Level1 和阈值。可以点“全览”确认数据已加载。

**结果准不准？** 算法有实验室样例回归测试，但自动检测总有边界情况。正式统计前，请抽查波形、事件表和剔除表。

**数据会上传吗？** 不会。软件只在本机读写文件。

**支持 Mac 或 Linux 吗？** 免安装包是 Windows 64 位。其他系统可以从源码运行，见 [DEVELOPMENT.md](DEVELOPMENT.md)。

## 11. 详细教程

完整的界面说明、参数解释、批量处理、MATLAB 对接和故障排查，见 [tutorial.md](tutorial.md)。

## 12. 许可与作者

MIT 许可证，见 [LICENSE](LICENSE)。

由 Huang Lab 的 Yize Liu（1moltry）开发与维护。产品名 **MOLTRACE（摩尔迹）**，仓库 `MT-MolTrace`。
