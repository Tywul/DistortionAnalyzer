# 更新日志

## V1.1 — 2026-05-30

### 代码重构（30 项优化）

**GUI 层 (`distortion_gui_app.py`)**
- 提取 `_pack_grid_result()` 消除 6 处网格数据打包重复
- 提取 `_save_figure()` + `_log_exc()` 消除绘图保存/日志样板
- 提取 `_show_figure()` 消除 4 个 popup 方法的 FigureDialog 模板
- 全部 `os.path.*` → `pathlib.Path`（零 os 引用）
- 补充所有方法返回类型注解（`-> None`, `-> dict`, `Optional[...]` 等）
- 移除未使用的 `Qt`、`datetime` 导入
- 简化 `main()` 图标路径逻辑（frozen/dev 分支合并）

**分析层 (`distortion_analyzer.py`)**
- 提取 `_read_seq_lines()` 消除 4 个静态方法的 try/except 读取模板
- 提取 `_unwrap_grid()` 统一畸变网格展开逻辑
- `_read_temp_file` 改用 `Path.read_text()`
- `print()` → `logging` 模块（6 处）
- 全部 `os.path.*` → `pathlib.Path`
- 移除未使用的 `os`、`sys` 导入，移除冗余局部 `import re`
- 移除 `_run_polar_macro` 中未使用的 `plt_file` 变量
- 补充 `Generator`、`-> None` 等返回类型

**构建脚本 (`build_exe.py`)**
- `sys.argv` → `argparse`（`--clean` / `--no-cleanup` 参数）
- `os.walk` → `Path.rglob()`，`os.path.getsize` → `.stat().st_size`
- `build()` 新增 `skip_cleanup` 参数

### 净效果
- 三文件合计净减 ~200 行
- 零 `os.path.*` 残留（仅 `os.pathsep` 保留）
- 零未使用 import
- 所有公开方法已标注返回类型

---

## V1.0-alpha — 2026-05-21

### 新增

- **双标签页界面**：Distortion Grid / Pupil Swim 独立参数面板
- **变焦名称显示**：从 SEQ 文件 `TIT Z<n> "name"` 自动解析变焦名称，复选框和下拉列表均显示
- **多波长叠加分析**：Multi Color 模式下所有波长畸变网格叠加在同一坐标系中
- **独立图表弹窗**：运行结果在 FigureDialog 中弹出，带 Matplotlib 工具栏、Save PNG、Close
- **异常值过滤 (IQR)**：可启用的四分位距异常值检测，参数可调
- **坐标轴范围控制**：±X/±Y 手动设置或自动（0 = auto）
- **输出目录自动设置**：加载 SEQ 后自动创建 `{程序根目录}/{镜头名}/` 子目录
- **自定义程序图标**：5×5 青色网格 + 深蓝底，嵌入 exe 文件图标和窗口标题栏

### 改进

- 移除默认镜头加载，启动时需手动浏览 SEQ
- FOV 默认值改为 5°，变焦默认勾选第 1 个
- Grid Size 上限从 51 收紧至 21
- Pupil Swim 输出格式三选一（矢量+热力图 / 仅矢量 / 仅热力图）
- 宏文件路径改为程序根目录引用，避免外部路径依赖
- 窗口标题 "Distortion Analyzer V1.0-alpha"

### 修复

- Pupil Swim 页面变焦数量与 SEQ 不匹配（拆分变焦解析与波长/FOV 解析）
- 复选框重建时 `RuntimeError: wrapped C/C++ object deleted`（按钮随复选框一起重建）
- 打包后 numpy `_multiarray_umath` DLL 缺失（`libscipy_openblas` 误删修复）
- 打包后 `pyparsing.testing` 缺失 `unittest`（从排除列表中移除 `unittest`）
- 打包后 PIL 缺失导致 matplotlib 崩溃（添加 `--hidden-import PIL`）

### 打包

- PyInstaller `--onefile --windowed`，自包含 ~132 MB
- 排除未使用模块（asyncio, test, setuptools, lib2to3, xmlrpc, http.server）
- 构建后清理冗余 DLL（_avif, libssl, libcrypto, Qt5Quick, Qt5Qml, Qt5Network）
- 图标嵌入 exe + 复制到 dist 根目录

### 依赖

- Python 3.13 / PyQt5 / matplotlib / numpy / scipy / pywin32 / Pillow
- CODE V COM 接口（运行时需 CODE V 已安装）
- PyInstaller 6.20（打包用）
