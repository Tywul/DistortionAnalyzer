# Distortion Analyzer V1.1

畸变分析工具 — 基于 CODE V COM 接口的光学畸变网格分析与 Pupil Swim 评估。

## 功能概览

| 分析模式 | 说明 |
|----------|------|
| **Distortion Grid（畸变网格）** | 获取真实光线与近轴光线的网格坐标，可视化畸变；支持单波长 / 多波长叠加 |
| **Pupil Swim（瞳孔偏移）** | 比较两个变焦位置间的网格位移，输出矢量图和热力图 |

## 运行环境

- **CODE V**（已安装并激活）
- **Windows 10/11**（64位）
- 无需额外安装 Python 环境（exe 已自包含）

## 使用步骤

### 1. 加载镜头

点击 **Lens File → Browse...** 选择 `.seq` 格式的 CODE V 镜头文件。程序会自动解析：
- 变焦位置（含名称）
- 波长列表
- 半视场角

输出目录自动设为程序根目录下的 `{镜头名称}/` 子文件夹。

### 2. 选择分析模式

界面提供两个标签页：

#### Distortion Grid（畸变网格）

| 参数 | 说明 | 默认值 |
|------|------|--------|
| Wavelength Mode | Single Color：单个波长；Multi Color：所有波长叠加 | Single |
| Wavelength | 单波长模式下的波长选择（自动读取 SEQ 中的 WL 列表） | 参考波长 |
| Zoom Position(s) | 勾选要分析的变焦位置（可多选） | 前 3 个 |
| X/Y Half-FOV | X/Y 方向半视场角（度），自动读取 SEQ 中的 XAN/YAN | 从 SEQ 解析 |
| Grid Size | 网格线数量（11~21，步长 2） | 21 |
| Axis Range | 图表坐标轴范围（mm），0 表示自动 | 自动 |
| Outlier Removal (IQR) | 是否启用异常值过滤 | 启用，因子 1.5 |
| Output Dir | 图表输出目录 | `{程序根目录}/{镜头名}/` |

#### Pupil Swim（瞳孔偏移）

| 参数 | 说明 | 默认值 |
|------|------|--------|
| Reference | 参考变焦位置 | Z2 |
| Target | 目标变焦位置 | Z5（或 Z3） |
| Output Format | Both：矢量图+热力图；Vectors：仅矢量；Heatmap：仅热力图 | Both |
| 其余参数 | 同 Distortion Grid 中的 FOV/Grid/Axis/IQR | — |

### 3. 运行分析

点击 **▶ Start Analysis**，程序通过 CODE V COM 接口在后台执行光线追迹。进度和日志在底部显示，主界面不卡顿。

### 4. 查看结果

分析完成后自动弹出独立的图表窗口，包含：
- **Matplotlib 工具栏**：缩放、平移、保存
- **Save PNG** 按钮：导出高清 PNG（200 dpi）
- **Close** 按钮：关闭窗口

### 图表类型

| 图表 | 内容 |
|------|------|
| 单波长畸变网格 | 实际网格 + 近轴理想网格（灰色虚线），按变焦位置着色 |
| 多波长叠加畸变 | 所有波长网格叠加在同一坐标系中 |
| Pupil Swim 矢量图 | Reference（深蓝）+ Target（橙色）网格 + 红色位移箭头 + Max/RMS 标注 |
| Pupil Swim 热力图 | 三角剖分插值位移幅度热图 |

## 目录结构

```
DistortionAnalyzer/
├── distortion_gui_app.py       # 主 GUI 程序
├── distortion_analyzer.py      # 分析核心（CODE V COM 接口）
├── distortion_grid_plotter.py  # 独立畸变网格绘图器
├── build_exe.py                # PyInstaller 打包脚本
├── dist_real_pro.seq           # 畸变网格宏（CODE V）
├── dist_polar_pro.seq          # 极坐标畸变宏（备用）
├── icon.ico                    # 程序图标
├── requirements.txt            # Python 依赖
├── CHANGELOG.md                # 更新日志
├── README.md                   # 本文件
├── tests/                      # 单元测试
└── .gitignore
```

**构建输出：** `dist/`（独立 exe）和 `build/`（临时文件）由 `build_exe.py` 生成，已加入 `.gitignore`。

## 开发运行

```bash
pip install -r requirements.txt
python distortion_gui_app.py
```

要求 CODE V 已安装并启动。

## 注意事项

- 运行前确保 CODE V 已启动（程序会自动连接已有实例）
- Multi Color 模式下每次运行切换参考波长，耗时约为单波长 × 波长数
- 异常值过滤（IQR）在数据噪声大时建议启用
- 图表窗口可独立拖放、缩放，不影响主界面操作
