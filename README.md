# MOLTRACE — 单分子纳米孔电流信号分析

**MOLTRACE** MT by 1moltry for Huang Lab：纳米孔数据处理平台，基于此的多算法开发实现更定制化的事件查找、指纹处理、自动化流程

它读取 `.abf` 电流记录，自动完成事件分割、特征提取和异常剔除，并导出 Excel、图片和 MATLAB 数据。软件在本机运行，数据不上传。

当前版本 `v3.0.0`。仓库：<https://github.com/1moltry/MT-MolTrace>。

## 下载使用

1. 打开 [Releases](https://github.com/1moltry/MT-MolTrace/releases)，在最新版本下方的 **Assets** 下载 `MOLTRACE_v3.0.0_win64.zip`。
2. 右键 zip，选择“全部解压缩”，解压到硬盘目录，例如 `D:\MOLTRACE`。
3. 双击 `MOLTRACE.exe` 启动。
4. 首次运行若提示“Windows 已保护你的电脑”，点“更多信息”，再点“仍要运行”。

> `MOLTRACE.exe` 与 `_internal` 文件夹必须放在同一层。只把 exe 单独拷走，程序无法启动。

完整的使用教程见 [tutorial.md](tutorial.md)，发行包内也附带同一份。

## 核心功能

- **事件检测**：电平法、驻留包络、平台滞回三种算法，可并排对比。
- **特征提取**：输出 20 列事件特征表，含阻孔比、驻留时间、偏度、峰度等。
- **异常处理**：识别反压恢复、膜抖动、基线漂移、炸膜等区间；剔除原因可追溯。
- **批量处理**：整个文件夹一次导出，可选事件波形、图片、批次汇总与合并训练表。
- **可视化**：全程波形、事件切片、深度-时长散点与直方图，点击事件表联动定位。

## 开发哲学

- **以 Clampfit 语义为参照**：电平判断与事件边界遵循课题组熟悉的口径，结果可对照。
- **特征与课题组规范对齐**：列名与定义遵循既定特征表，保证后续模型训练一致。
- **测试先行**：算法变更配套合成信号真值回归，交付前 `pytest` 全绿。
- **单一底座，按需启用模块**：默认最小输出，需要什么再勾选。
- **本地运行，结果可追溯**：数据不出本机；每个被剔除事件都能查到原因。

## 开发与反馈

源码运行与架构说明见 [DEVELOPMENT.md](DEVELOPMENT.md)；分支、提交与 PR 流程见 [CONTRIBUTING.md](CONTRIBUTING.md)。问题与建议请开 [Issue](https://github.com/1moltry/MT-MolTrace/issues)。

## 许可

MIT 许可证，见 [LICENSE](LICENSE)。

由 Huang Lab 的 Yize Liu（1moltry）开发与维护。
