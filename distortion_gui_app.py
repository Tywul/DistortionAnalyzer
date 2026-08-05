# -*- coding: utf-8 -*-
"""
Distortion Analysis GUI App (PyQt5) v4.0
- Two analysis modes: Distortion Grid / Pupil Swim
- All charts in independent popup dialogs (FigureDialog)
- Wavelength-aware: single color or multi-color overlay from SEQ file
"""

from typing import Optional, Any
import sys
import traceback
import numpy as np
from pathlib import Path

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QGroupBox, QLabel, QPushButton, QComboBox, QCheckBox, QSpinBox,
    QDoubleSpinBox, QLineEdit, QTextEdit, QFileDialog, QSplitter,
    QProgressBar, QMessageBox, QGridLayout, QScrollArea, QFormLayout,
    QDialog, QTabWidget, QRadioButton, QButtonGroup, QSizePolicy,
    QDialogButtonBox,
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer, QObject
from PyQt5.QtGui import QFont, QIcon

# --- matplotlib lazy init ---
_mpl_ready = False

def _init_mpl():
    """Import & configure matplotlib on first use (reduces cold-start time)."""
    global _mpl_ready
    if _mpl_ready:
        return
    import matplotlib
    matplotlib.use('Qt5Agg')
    import matplotlib.pyplot as _plt
    _plt.rcParams['font.sans-serif'] = ['Microsoft YaHei', 'SimHei']
    _plt.rcParams['axes.unicode_minus'] = False
    _mpl_ready = True

# Wavelength-to-color mapping for multi-color overlay
WL_COLORS = ['red', 'green', 'blue', 'orange', 'purple', 'cyan',
             'magenta', 'olive', 'brown', 'pink', 'gray', 'black']

# ── i18n / help ──
I18N = {
    "zh": {
        "app_title": "畸变分析器 V1.2",
        "status_tip": "加载镜头文件后，点击开始分析。",
        "settings": "设置",
        "language": "界面语言",
        "help": "使用说明",
        "help_content": (
            "畸变分析器使用说明\n\n"
            "1. 加载镜头文件\n"
            "   点击“浏览...”选择 .seq 文件，自动读取波长和变焦信息。\n\n"
            "2. 畸变网格分析 (Tab 1)\n"
            "   - 选择波长模式（单色/多色叠加）和变焦位。\n"
            "   - 点击“开始分析”运行 CODE V 追踪。\n"
            "   - 结果在右侧画布显示，可点击“导出 PNG”保存。\n\n"
            "3. 畸变校正 (Tab 1 下半部分)\n"
            "   - CODE V 模式：自动用三个波长分别追踪。\n"
            "   - TXT 模式：手动导入 r.txt/g.txt/b.txt。\n"
            "   - 点击“拟合校正”拟合多项式系数。\n"
            "   - 点击“导出 CSV”导出 svrapi_lens.csv。\n\n"
            "4. 瞳孔游动 (Tab 2)\n"
            "   分析变焦位间的光线位移，支持矢量和热力图视图。\n\n"
            "5. 设置 (右上角齿轮图标)\n"
            "   切换界面语言 / 查看使用说明。"
        ),
        "lens_file": "镜头文件",
        "browse": "浏览...",
        "tab_distortion": "畸变网格",
        "tab_correction": "校正",
        "tab_pupil_swim": "瞳孔游动",
        "select_all": "全选",
        "clear": "清除",
        "start_analysis": "开始分析",
        "fit_correction": "拟合校正",
        "fit_from_txt": "从 TXT 拟合",
        "export_csv": "导出 CSV",
        "export_png": "导出 PNG",
        "select_valid_seq": "请选择有效的 .seq 文件",
        "load_seq_first": "请先加载 SEQ 文件",
        "seq_not_found": "未找到 SEQ 文件：\n{seq}",
        "select_at_least_one_zoom": "至少选择一个变焦位",
        "ref_target_different": "参考和目标变焦位必须不同",
        "run_analysis_first": "请先运行分析",
        "run_fit_first": "请先运行拟合再导出",
        "select_txt_file": "请至少选择一个 R/G/B TXT 文件",
        "no_data_yet": "尚无数据",
        "export_csv_save_title": "导出 CSV（左侧）",
        "save_png": "保存 PNG",
        "close": "关闭",
        "save_png_title": "保存 PNG",
        "saved_message": "已保存：\n{path}",
        "fit_error_title": "拟合错误",
        "zoom_item": "Z{id}",
        "zoom_item_with_name": "Z{id} {name}",
        "zoom_tooltip": "变焦 {id}",
        "wavelength_item": "W{id}: {wl:.1f}nm{ref}",
        "ref_tag": " (REF)",
        "manual": "（手动）",
        "select_model": "选择型号...",
        "seq_placeholder": ".seq 文件路径...",
        "log_placeholder": "分析日志输出...",
        "parameters": "参数",
        "x_half_fov": "X 半 FOV (°):",
        "y_half_fov": "Y 半 FOV (°):",
        "grid_size": "网格尺寸:",
        "axis_range": "轴范围:",
        "x_range_label": "±X (mm):",
        "y_range_label": "±Y (mm):",
        "x_range_tooltip": "±X 范围 (mm), 0=自动",
        "y_range_tooltip": "±Y 范围 (mm), 0=自动",
        "enable_iqr": "启用异常值移除 (IQR)",
        "iqr_factor": "IQR 因子:",
        "output_dir": "输出目录:",
        "wavelength_mode": "波长模式",
        "single_color": "单色 (参考波长)",
        "multi_color": "多色 (全部波长)",
        "wavelength_label": "波长:",
        "zoom_positions": "变焦位",
        "correction_section": "校正（多项式拟合 + CSV 导出）",
        "panel_half_w": "面板半宽:",
        "panel_half_h": "面板半高:",
        "zoom_label": "变焦:",
        "brand": "品牌:",
        "model": "型号:",
        "active_w_px": "有效宽 (px):",
        "active_h_px": "有效高 (px):",
        "pre_corr_w_px": "校正前宽 (px):",
        "pre_corr_h_px": "校正前高 (px):",
        "pixel_size": "像素尺寸 (mm):",
        "numcols": "列数:",
        "numrows": "行数:",
        "offset_x": "偏移 X (px):",
        "offset_y": "偏移 Y (px):",
        "h_symmetry": "水平对称 (Y 偶次项)",
        "v_symmetry": "垂直对称 (X 偶次项)",
        "source": "来源:",
        "code_v": "CODE V",
        "txt_files": "TXT 文件",
        "file_label": "{channel} 文件:",
        "zoom_positions_ref_target": "变焦位 (参考 vs 目标)",
        "reference": "参考:",
        "target": "目标:",
        "output_format": "输出格式",
        "both_grid_vectors_heatmap": "矢量+热力图（推荐）",
        "grid_vectors_only": "仅矢量",
        "heatmap_only": "仅热力图",
        "grid_vectors": "矢量",
        "heatmap": "热力图",
        "app_help_title": "帮助",
        "error_title": "错误",
        "hint_title": "提示",
        "saved_title": "已保存",
        "open_seq_title": "打开 SEQ",
        "open_txt_title": "打开 Trace TXT",
        "browse_output_dir": "选择输出目录",
    },
    "en": {
        "app_title": "Distortion Analyzer V1.2",
        "status_tip": "Load a lens file, then click Start Analysis.",
        "settings": "Settings",
        "language": "Language",
        "help": "Help",
        "help_content": (
            "Distortion Analyzer User Guide\n\n"
            "1. Load Lens File\n"
            "   Click Browse to select a .seq file. Wavelengths and\n"
            "   zoom info are read automatically.\n\n"
            "2. Distortion Grid Analysis (Tab 1)\n"
            "   - Select wavelength mode (single/multi) and zoom positions.\n"
            "   - Click Start Analysis to run CODE V tracing.\n"
            "   - Results shown on right canvas. Export PNG to save.\n\n"
            "3. Distortion Correction (Tab 1, lower section)\n"
            "   - CODE V mode: auto-trace with three wavelengths.\n"
            "   - TXT mode: manually import r.txt/g.txt/b.txt.\n"
            "   - Click Fit Correction to fit polynomial coefficients.\n"
            "   - Click Export CSV to save svrapi_lens.csv.\n\n"
            "4. Pupil Swim (Tab 2)\n"
            "   Analyze ray shifts between zoom positions. Supports vector\n"
            "   and heatmap views.\n\n"
            "5. Settings (gear icon, top right)\n"
            "   Switch UI language / view help."
        ),
        "lens_file": "Lens File",
        "browse": "Browse...",
        "tab_distortion": "Distortion Grid",
        "tab_correction": "Correction",
        "tab_pupil_swim": "Pupil Swim",
        "select_all": "Select All",
        "clear": "Clear",
        "start_analysis": "Start Analysis",
        "fit_correction": "Fit Correction",
        "fit_from_txt": "Fit from TXT",
        "save_png": "Save PNG",
        "close": "Close",
        "save_png_title": "Save PNG",
        "saved_message": "Saved to:\n{path}",
        "fit_error_title": "Fit Error",
        "zoom_item": "Z{id}",
        "zoom_item_with_name": "Z{id} {name}",
        "zoom_tooltip": "Zoom {id}",
        "wavelength_item": "W{id}: {wl:.1f}nm{ref}",
        "ref_tag": " (REF)",
        "select_valid_seq": "Select a valid .seq file",
        "load_seq_first": "Load a SEQ file first",
        "seq_not_found": "SEQ not found:\n{seq}",
        "select_at_least_one_zoom": "Select at least 1 Zoom position",
        "ref_target_different": "Ref and Target must be different",
        "run_analysis_first": "Run analysis first",
        "run_fit_first": "Run fit first before exporting",
        "select_txt_file": "Select at least one R/G/B TXT file",
        "no_data_yet": "No data yet",
        "export_csv_save_title": "Export CSV (left)",
        "manual": "(manual)",
        "select_model": "Select model...",
        "seq_placeholder": ".seq path...",
        "log_placeholder": "Analysis log output...",
        "parameters": "Parameters",
        "x_half_fov": "X Half-FOV (°):",
        "y_half_fov": "Y Half-FOV (°):",
        "grid_size": "Grid Size:",
        "axis_range": "Axis Range:",
        "x_range_label": "±X (mm):",
        "y_range_label": "±Y (mm):",
        "x_range_tooltip": "±X range (mm), 0=auto",
        "y_range_tooltip": "±Y range (mm), 0=auto",
        "enable_iqr": "Enable Outlier Removal (IQR)",
        "iqr_factor": "IQR Factor:",
        "output_dir": "Output Dir:",
        "wavelength_mode": "Wavelength Mode",
        "single_color": "Single Color (reference wavelength)",
        "multi_color": "Multi Color (all wavelengths)",
        "wavelength_label": "Wavelength:",
        "zoom_positions": "Zoom Position(s)",
        "correction_section": "Correction (Polynomial Fit + CSV Export)",
        "panel_half_w": "Panel half-W:",
        "panel_half_h": "half-H:",
        "zoom_label": "Zoom:",
        "brand": "Brand:",
        "model": "Model:",
        "active_w_px": "Active W (px):",
        "active_h_px": "Active H (px):",
        "pre_corr_w_px": "Pre-corr W (px):",
        "pre_corr_h_px": "Pre-corr H (px):",
        "pixel_size": "Pixel size (mm):",
        "numcols": "NumCols:",
        "numrows": "NumRows:",
        "offset_x": "Offset X (px):",
        "offset_y": "Offset Y (px):",
        "h_symmetry": "H symmetry (Y even-order)",
        "v_symmetry": "V symmetry (X even-order)",
        "source": "Source:",
        "code_v": "CODE V",
        "txt_files": "TXT files",
        "file_label": "{channel} file:",
        "zoom_positions_ref_target": "Zoom Positions (Reference vs Target)",
        "reference": "Reference:",
        "target": "Target:",
        "output_format": "Output Format",
        "both_grid_vectors_heatmap": "Both Grid Vectors + Heatmap (Recommended)",
        "grid_vectors_only": "Grid Vectors Only",
        "heatmap_only": "Heatmap Only",
        "grid_vectors": "Grid Vectors",
        "heatmap": "Heatmap",
        "app_help_title": "Help",
        "error_title": "Error",
        "hint_title": "Hint",
        "saved_title": "Saved",
        "open_seq_title": "Open SEQ",
        "open_txt_title": "Open Trace TXT",
        "browse_output_dir": "Select Output Directory",
    },
}
_current_lang = "zh"


# ============================================================
#  Settings Dialog
# ============================================================
class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(I18N[_current_lang]["settings"])
        self.setMinimumSize(500, 420)
        lo = QVBoxLayout(self)

        tabs = QTabWidget()
        # Tab: Language
        tab_lang = QWidget()
        lang_lo = QVBoxLayout(tab_lang)
        lang_lo.addWidget(QLabel(I18N[_current_lang]["language"] + ":"))
        self.cb_lang = QComboBox()
        self.cb_lang.addItem("中文", "zh")
        self.cb_lang.addItem("English", "en")
        self.cb_lang.setCurrentIndex(0 if _current_lang == "zh" else 1)
        lang_lo.addWidget(self.cb_lang)
        lang_lo.addStretch()
        tabs.addTab(tab_lang, I18N[_current_lang]["language"])

        # Tab: Help
        tab_help = QWidget()
        help_lo = QVBoxLayout(tab_help)
        te = QTextEdit()
        te.setReadOnly(True)
        te.setPlainText(I18N[_current_lang]["help_content"])
        help_lo.addWidget(te)
        tabs.addTab(tab_help, I18N[_current_lang]["help"])

        lo.addWidget(tabs)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self._apply)
        btns.rejected.connect(self.reject)
        lo.addWidget(btns)

    def _apply(self):
        global _current_lang
        new_lang = self.cb_lang.currentData()
        if new_lang != _current_lang:
            _current_lang = new_lang
            # Refresh dialog itself
            self.setWindowTitle(I18N[_current_lang]["settings"])
            tabs = self.findChild(QTabWidget)
            if tabs:
                tabs.setTabText(0, I18N[_current_lang]["language"])
                tabs.setTabText(1, I18N[_current_lang]["help"])
                tw = tabs.widget(1)  # help tab
                if isinstance(tw, QWidget):
                    te = tw.findChild(QTextEdit)
                    if te:
                        te.setPlainText(I18N[_current_lang]["help_content"])
            # Refresh main window
            p = self.parent()
            if p is not None and hasattr(p, '_refresh_ui_language'):
                p._refresh_ui_language()
        self.accept()


# ============================================================
#  Worker Thread (simplified: only grid mode via DistortionAnalyzer)
# ============================================================
class AnalysisWorker(QThread):
    progress = pyqtSignal(str)
    finished_signal = pyqtSignal(object)
    error_signal = pyqtSignal(str)

    def __init__(self, seq_path: str, **kwargs: Any) -> None:
        """
        Args:
            seq_path: path to .seq file
            kwargs:
                mode: 'grid' | 'pupil_swim'
                zoom_ids: list of int (for grid mode)
                wl_mode: 'single' | 'multi'
                wl_index: int (for single-wavelength mode, 1-based ref index)
                x_fov, y_fov: float
                grid_size: int
                ref_zoom_id: int (for pupil swim)
                tgt_zoom_id: int (for pupil swim)
                iqr_enabled: bool
                iqr_factor: float
        """
        super().__init__()
        self.seq_path = seq_path
        self.kwargs = kwargs

    def run(self) -> None:
        analyzer = None
        try:
            from distortion_analyzer import DistortionAnalyzer

            workdir = str(Path(self.seq_path).parent)
            mode = self.kwargs.get('mode', 'grid')

            self.progress.emit("Connecting CODE V ...")
            analyzer = DistortionAnalyzer(workdir=workdir, auto_connect=False)

            self.progress.emit("Loading lens ...")
            analyzer.load_lens(self.seq_path)

            # Read available wavelengths from SEQ
            wl_info = analyzer.get_wavelengths_from_seq(self.seq_path)
            wavelengths = wl_info['wavelengths']
            ref_idx = wl_info['ref_index']

            if mode == 'grid':
                result = self._run_grid(analyzer, wavelengths, ref_idx)
            elif mode == 'pupil_swim':
                result = self._run_pupil_swim(analyzer, wavelengths, ref_idx)
            else:
                raise ValueError(f"Unknown mode: {mode}")

            self.finished_signal.emit(result)

        except Exception as e:
            self.error_signal.emit(str(e))

        finally:
            if analyzer is not None:
                try:
                    analyzer.disconnect()
                except Exception:
                    pass

    @staticmethod
    def _pack_grid_result(grid, gs: int, **extra) -> dict:
        """Pack grid data into result dict, or zero-fill on failure (grid=None)."""
        n = gs
        if grid is not None:
            d = {
                'actual': grid.actual.copy(),
                'paraxial': grid.paraxial.copy(),
                'dx': grid.actual[:, :, 0] - grid.paraxial[:, :, 0],
                'dy': grid.actual[:, :, 1] - grid.paraxial[:, :, 1],
            }
        else:
            d = {
                'actual': np.zeros((n, n, 2)),
                'paraxial': np.zeros((n, n, 2)),
                'dx': np.zeros((n, n)), 'dy': np.zeros((n, n)),
            }
        d.update(extra)
        return d

    def _run_grid(self, analyzer: Any, wavelengths: list, ref_idx: int) -> dict:
        zoom_ids = self.kwargs.get('zoom_ids', [1])
        wl_mode = self.kwargs.get('wl_mode', 'single')
        wl_choice = self.kwargs.get('wl_index', ref_idx)
        x_fov = self.kwargs.get('x_fov', 26.565)
        y_fov = self.kwargs.get('y_fov', 26.565)
        gs = self.kwargs.get('grid_size', 21)
        cached = self.kwargs.get('cached_results', {})
        WL_TAGS = {1: 'r', 2: 'g', 3: 'b'}

        results = {}

        if wl_mode == 'multi':
            color_names = ['RED', 'GRE', 'BLU', 'MAG', 'YEL', 'CYA', 'WHI']
            total = len(zoom_ids) * len(wavelengths)
            count = 0
            for zid in zoom_ids:
                for wi, wl_val in enumerate(wavelengths):
                    count += 1
                    wl_index = wi + 1
                    cache_key = (zid, wl_index, gs, x_fov, y_fov)
                    if cache_key in cached:
                        results[(zid, wi)] = cached[cache_key]
                        self.progress.emit(f"[{count}/{total}] Z{zid} WL{wl_index} (cached)")
                        continue
                    wl_label = f"{wl_val:.0f}nm"
                    self.progress.emit(f"[{count}/{total}] Z{zid} @ {wl_label} ...")
                    try:
                        grid = analyzer.get_distortion_grid(
                            zoom_pos=zid, num_lines=gs,
                            x_fov=x_fov, y_fov=y_fov,
                            wavelength=color_names[wi % len(color_names)],
                            wl_index=wl_index,
                            tag=WL_TAGS.get(wl_index, f'w{wl_index}'))
                        results[(zid, wi)] = self._pack_grid_result(
                            grid, gs, x_fov=x_fov, y_fov=y_fov,
                            wavelength=wl_val, wl_index=wl_index)
                    except Exception as e:
                        self.progress.emit(f"  Z{zid}@{wl_label} failed: {e}")
                        results[(zid, wi)] = self._pack_grid_result(
                            None, gs, wavelength=wl_val, wl_index=wl_index)
        else:
            wl_val = wavelengths[wl_choice - 1] if wl_choice <= len(wavelengths) else wavelengths[0]
            wl_label = f"{wl_val:.0f}nm"
            for zi, zid in enumerate(zoom_ids):
                cache_key = (zid, wl_choice, gs, x_fov, y_fov)
                if cache_key in cached:
                    results[zid] = cached[cache_key]
                    self.progress.emit(f"[{zi+1}/{len(zoom_ids)}] Z{zid} WL{wl_choice} (cached)")
                    continue
                self.progress.emit(f"[{zi+1}/{len(zoom_ids)}] Z{zid} @ {wl_label} ...")
                try:
                    grid = analyzer.get_distortion_grid(
                        zoom_pos=zid, num_lines=gs,
                        x_fov=x_fov, y_fov=y_fov,
                        wl_index=wl_choice, wavelength=wl_label,
                        tag=WL_TAGS.get(wl_choice, f'w{wl_choice}'))
                    results[zid] = self._pack_grid_result(
                        grid, gs, x_fov=x_fov, y_fov=y_fov,
                        wavelength=wl_val, wl_index=wl_choice)
                except Exception as e:
                    self.progress.emit(f"  Z{zid} failed: {e}")
                    results[zid] = self._pack_grid_result(
                        None, gs, wavelength=wl_val, wl_index=wl_choice)

        return {
            'mode': 'grid',
            'wl_mode': wl_mode,
            'wavelengths': wavelengths,
            'results': results,
            'x_fov': x_fov, 'y_fov': y_fov,
            'grid_size': gs,
            'xlim': self.kwargs.get('xlim', 0),
            'ylim': self.kwargs.get('ylim', 0),
        }

    # ---- Pupil Swim Mode ----
    def _run_pupil_swim(self, analyzer: Any, wavelengths: list, ref_idx: int) -> dict:
        ref_id = self.kwargs.get('ref_zoom_id', 2)
        tgt_id = self.kwargs.get('tgt_zoom_id', 5)
        x_fov = self.kwargs.get('x_fov', 26.565)
        y_fov = self.kwargs.get('y_fov', 26.565)
        gs = self.kwargs.get('grid_size', 21)
        cached = self.kwargs.get('cached_results', {})
        wl_val = wavelengths[ref_idx - 1]
        wl_label = f"{wl_val:.0f}nm"
        WL_TAGS = {1: 'r', 2: 'g', 3: 'b'}
        wl_tag = WL_TAGS.get(ref_idx, f'w{ref_idx}')

        results = {}
        for zid, name in [(ref_id, 'Reference'), (tgt_id, 'Target')]:
            cache_key = (zid, ref_idx, gs, x_fov, y_fov)
            if cache_key in cached:
                results[zid] = cached[cache_key]
                self.progress.emit(f"Z{zid} ({name}) (cached)")
                continue
            self.progress.emit(f"Tracing Z{zid} ({name}) @ {wl_label} ...")
            try:
                grid = analyzer.get_distortion_grid(
                    zoom_pos=zid, num_lines=gs,
                    x_fov=x_fov, y_fov=y_fov,
                    wl_index=ref_idx, wavelength=wl_label,
                    tag=wl_tag)
                results[zid] = self._pack_grid_result(
                    grid, gs, x_fov=x_fov, y_fov=y_fov)
            except Exception as e:
                self.progress.emit(f"  Z{zid} ({name}) failed: {e}")
                results[zid] = self._pack_grid_result(None, gs)

        return {
            'mode': 'pupil_swim',
            'wavelengths': wavelengths,
            'ref_id': ref_id, 'tgt_id': tgt_id,
            'results': results,
            'x_fov': x_fov, 'y_fov': y_fov,
            'grid_size': gs,
            'xlim': self.kwargs.get('xlim', 0),
            'ylim': self.kwargs.get('ylim', 0),
        }


# ============================================================
#  Correction Worker (Tab 3: CODE V tracing + polynomial fitting)
# ============================================================
class CorrectionWorker(QObject):
    """畸变拟合：共用 DistortionAnalyzer 追迹 R/G/B，自动保存 z{zoom}_{r,g,b}.txt"""
    progress = pyqtSignal(str)
    finished = pyqtSignal(str, int, str)  # (work_dir, zoom, error_msg)

    def __init__(self, seq_path, halfx, halfy, panel_w, panel_h,
                 zoom, num_lines, wl_indices, macro_path):
        super().__init__()
        self.seq_path = seq_path; self.halfx = halfx; self.halfy = halfy
        self.panel_w = panel_w; self.panel_h = panel_h
        self.zoom = zoom; self.num_lines = num_lines
        self.wl_indices = wl_indices; self.macro_path = macro_path

    def run(self) -> None:
        from distortion_analyzer import DistortionAnalyzer

        work_dir = str(Path(self.seq_path).parent)
        WL_TAGS = {1: 'r', 2: 'g', 3: 'b'}
        labels = ["R", "G", "B"]

        try:
            self.progress.emit("Connecting CODE V ...")
            analyzer = DistortionAnalyzer(workdir=work_dir, auto_connect=False)
            analyzer.load_lens(self.seq_path)

            for idx, wl in enumerate(self.wl_indices):
                label = labels[idx]
                wl_tag = WL_TAGS.get(wl, f'w{wl}')
                self.progress.emit(f"Trace {label} (WL={wl}) ...")
                try:
                    analyzer.get_distortion_grid(
                        zoom_pos=self.zoom, num_lines=self.num_lines,
                        x_fov=self.halfx, y_fov=self.halfy,
                        panel_width=self.panel_w, panel_height=self.panel_h,
                        wl_index=wl, wavelength="GRE",
                        tag=wl_tag)
                    self.progress.emit(f"  -> z{self.zoom}_{wl_tag}.txt")
                except Exception as e:
                    self.progress.emit(f"  {label} failed: {e}")

            self.progress.emit("CODE V done.")
            analyzer.disconnect()
            self.finished.emit(work_dir, self.zoom, "")
        except Exception as e:
            self.finished.emit("", self.zoom, f"CODE V error: {e}\n{traceback.format_exc()}")


# ============================================================
#  Popup Dialog (independent matplotlib window)
# ============================================================
class FigureDialog(QDialog):
    """Independent popup dialog for matplotlib figures with toolbar + save."""
    def __init__(self, parent=None, title="Plot", width=16, height=10, dpi=100):
        super().__init__(parent)
        _init_mpl()
        from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
        from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
        import matplotlib.pyplot as plt

        self.setWindowTitle(title)
        self.setGeometry(80, 80, int(width*dpi*0.82), int(height*dpi*0.82))
        lo = QVBoxLayout(self)
        self.fig, self.ax = plt.subplots(figsize=(width, height), dpi=dpi)
        self.canvas = FigureCanvas(self.fig)
        self.toolbar = NavigationToolbar(self.canvas, self)
        lo.addWidget(self.toolbar)
        lo.addWidget(self.canvas)
        btn_lo = QHBoxLayout()
        btn_save = QPushButton(I18N[_current_lang]["save_png"]); btn_save.clicked.connect(self._save_png)
        btn_close = QPushButton(I18N[_current_lang]["close"]); btn_close.clicked.connect(self.accept)
        btn_lo.addWidget(btn_save); btn_lo.addWidget(btn_close); btn_lo.addStretch()
        lo.addLayout(btn_lo)
        self._save_path = None

    def set_save_path(self, path):
        self._save_path = path

    def _save_png(self):
        p, _ = QFileDialog.getSaveFileName(self, I18N[_current_lang]["save_png_title"],
                                            self._save_path or "plot.png",
                                            "PNG (*.png);;PDF (*.pdf);;All (*)")
        if p:
            self.fig.savefig(p, dpi=200, bbox_inches='tight')
            QMessageBox.information(self, I18N[_current_lang]["saved_title"],
                                    I18N[_current_lang]["saved_message"].format(path=p))

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(100, self.canvas.draw)


# ============================================================
#  Main Window
# ============================================================
class DistortionGUI(QMainWindow):

    DEFAULT_OUT  = str(Path(__file__).parent.resolve())  # program root

    def __init__(self):
        super().__init__()
        self.setWindowTitle(self._t("app_title"))
        self.setGeometry(50, 50, 1500, 950)
        self.result = None
        self._wl_info = None   # cached wavelengths from SEQ
        self._loaded_seq_path = ""
        self._grid_cache = {}   # cache: (zoom, wl_index, x_fov, y_fov, num_lines) → result dict
        self._corr_work_dir = ""
        self._corr_csv_str = ""
        self._corr_fit_result = None
        self._corr_wl_r = self._corr_wl_g = self._corr_wl_b = None
        self._active_run_tab = None
        self._localized_widgets = []
        self._build_ui()
        self._load_displays_db()

    # ==================== UI LAYOUT ====================
    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_lo = QVBoxLayout(central)

        # ---- Top bar: Lens File + Settings ----
        top_lo = QHBoxLayout()
        grp_lens = self._register_text(QGroupBox(self._t("lens_file")), "lens_file", "setTitle")
        self._grp_lens = grp_lens
        lens_lo = QHBoxLayout(grp_lens)
        self.ed_seq = self._register_placeholder(QLineEdit(), "seq_placeholder")
        btn_lens = self._register_text(QPushButton(self._t("browse")), "browse")
        btn_lens.clicked.connect(self._browse_seq)
        lens_lo.addWidget(self.ed_seq, stretch=1)
        lens_lo.addWidget(btn_lens)
        top_lo.addWidget(grp_lens, stretch=1)
        btn_settings = self._register_text(QPushButton("  \u2699\uFE0F " + self._t("settings") + "  "), "settings", template="  \u2699\uFE0F {label}  ")
        self._btn_settings = btn_settings
        btn_settings.clicked.connect(self._show_settings)
        top_lo.addWidget(btn_settings)
        main_lo.addLayout(top_lo)

        # ---- Tab Widget ----
        self.tabs = QTabWidget()
        main_lo.addWidget(self.tabs)

        # Tab 1: Distortion Grid
        tab_grid = self._build_tab_grid()
        self.tabs.addTab(tab_grid, "  \U0001F4CF " + self._t("tab_distortion") + "  ")

        # Tab 2: Pupil Swim
        tab_ps = self._build_tab_pupil_swim()
        self.tabs.addTab(tab_ps, "  \U0001F441 " + self._t("tab_pupil_swim") + "  ")

        # ---- Progress Bar ----
        self.bar = QProgressBar(); self.bar.setRange(0, 1); self.bar.setTextVisible(True)
        main_lo.addWidget(self.bar)

        # ---- Log area ----
        self.log = self._register_placeholder(QTextEdit(), "log_placeholder")
        self.log.setMaximumHeight(110)
        self.log.setFont(QFont("Consolas", 9))
        main_lo.addWidget(self.log)

    def _register_text(self, widget, key, method='setText', fmt_args=None, template=None):
        self._localized_widgets.append((widget, method, key, fmt_args, template))
        return widget

    def _register_placeholder(self, widget, key):
        self._localized_widgets.append((widget, 'setPlaceholderText', key, None, None))
        return widget

    def _register_tooltip(self, widget, key):
        self._localized_widgets.append((widget, 'setToolTip', key, None, None))
        return widget

    # ========== Shared UI Builders ==========
    def _build_param_group(self, prefix: str, default_fov_x: float = 5,
                           default_fov_y: float = 5) -> QGroupBox:
        """Build a Parameters QGroupBox with FOV, Grid Size, Axis Range, IQR, Output Dir.
        
        Sets attributes on self as: sp_fovx_{prefix}, sp_fovy_{prefix}, sp_gs_{prefix},
        sp_xlim_{prefix}, sp_ylim_{prefix}, chk_iqr_{prefix}, sp_iqr_{prefix}, ed_out_{prefix}.
        """
        grp_p = self._register_text(QGroupBox(self._t("parameters")), "parameters", "setTitle")
        pl = QFormLayout(grp_p)

        # FOV X/Y
        fovx = QDoubleSpinBox(); fovx.setRange(0.1, 90); fovx.setValue(default_fov_x); fovx.setDecimals(3)
        fovx.setMaximumWidth(80)
        lbl_fovx = self._register_text(QLabel(self._t("x_half_fov")), "x_half_fov")
        pl.addRow(lbl_fovx, fovx)
        fovy = QDoubleSpinBox(); fovy.setRange(0.1, 90); fovy.setValue(default_fov_y); fovy.setDecimals(3)
        fovy.setMaximumWidth(80)
        lbl_fovy = self._register_text(QLabel(self._t("y_half_fov")), "y_half_fov")
        pl.addRow(lbl_fovy, fovy)

        # Grid Size
        gs = QSpinBox(); gs.setRange(11, 21); gs.setValue(21); gs.setSingleStep(2)
        gs.setMaximumWidth(70)
        lbl_gs = self._register_text(QLabel(self._t("grid_size")), "grid_size")
        pl.addRow(lbl_gs, gs)

        # Axis Range
        h_box = QHBoxLayout()
        xlim = QDoubleSpinBox(); xlim.setRange(0, 50); xlim.setValue(0); xlim.setDecimals(2)
        xlim.setMaximumWidth(70)
        self._register_tooltip(xlim, "x_range_tooltip")
        ylim = QDoubleSpinBox(); ylim.setRange(0, 50); ylim.setValue(0); ylim.setDecimals(2)
        ylim.setMaximumWidth(70)
        self._register_tooltip(ylim, "y_range_tooltip")
        lbl_xlim = self._register_text(QLabel(self._t("x_range_label")), "x_range_label")
        lbl_ylim = self._register_text(QLabel(self._t("y_range_label")), "y_range_label")
        h_box.addWidget(lbl_xlim); h_box.addWidget(xlim)
        h_box.addWidget(lbl_ylim); h_box.addWidget(ylim); h_box.addStretch()
        lbl_axis = self._register_text(QLabel(self._t("axis_range")), "axis_range")
        pl.addRow(lbl_axis, h_box)

        # IQR
        chk_iqr = self._register_text(QCheckBox(self._t("enable_iqr")), "enable_iqr")
        chk_iqr.setChecked(True)
        pl.addRow(chk_iqr)
        sp_iqr = QDoubleSpinBox(); sp_iqr.setRange(1.0, 5.0); sp_iqr.setValue(1.5)
        sp_iqr.setEnabled(True); sp_iqr.setMaximumWidth(70)
        chk_iqr.toggled.connect(sp_iqr.setEnabled)
        lbl_iqr = self._register_text(QLabel(self._t("iqr_factor")), "iqr_factor")
        pl.addRow(lbl_iqr, sp_iqr)

        # Output Dir
        ed_out = QLineEdit(self.DEFAULT_OUT)
        ed_out.setMaximumWidth(180)
        btn_out = self._register_text(QPushButton(self._t("browse")), "browse")
        btn_out.clicked.connect(lambda checked, p=prefix: self._browse_out(p))
        lbl_out = self._register_text(QLabel(self._t("output_dir")), "output_dir")
        pl.addRow(lbl_out, ed_out)
        pl.addRow(btn_out)

        # Store widgets as instance attributes
        setattr(self, f'sp_fovx_{prefix}', fovx)
        setattr(self, f'sp_fovy_{prefix}', fovy)
        setattr(self, f'sp_gs_{prefix}', gs)
        setattr(self, f'sp_xlim_{prefix}', xlim)
        setattr(self, f'sp_ylim_{prefix}', ylim)
        setattr(self, f'chk_iqr_{prefix}', chk_iqr)
        setattr(self, f'sp_iqr_{prefix}', sp_iqr)
        setattr(self, f'ed_out_{prefix}', ed_out)

        return grp_p

    # ---------- Tab 1: Distortion Grid + Correction ----------
    def _build_tab_grid(self):
        """Tab 1: left = params + correction, right = canvas tabs (Distortion/Correction)."""
        w = QWidget()
        lo = QHBoxLayout(w)
        lo.setContentsMargins(0, 0, 0, 0)
        left_scroll = QScrollArea()
        left_scroll.setWidgetResizable(True)
        left_scroll.setMinimumWidth(310)
        left_panel = QWidget()
        llo = QVBoxLayout(left_panel)
        llo.setSpacing(6)

        # ── Wavelength Mode ──
        grp_wl = self._register_text(QGroupBox(self._t("wavelength_mode")), "wavelength_mode", "setTitle")
        wl_lo = QVBoxLayout(grp_wl)
        self.bg_wl = QButtonGroup(self)
        self.rb_single = self._register_text(QRadioButton(self._t("single_color")), "single_color")
        self.rb_multi = self._register_text(QRadioButton(self._t("multi_color")), "multi_color")
        self.bg_wl.addButton(self.rb_single, 0)
        self.bg_wl.addButton(self.rb_multi, 1)
        self.rb_single.setChecked(True)
        self.bg_wl.buttonClicked.connect(self._on_wl_mode_changed)
        wl_lo.addWidget(self.rb_single)
        wl_lo.addWidget(self.rb_multi)
        sel_lo = QHBoxLayout()
        self._lbl_wl = self._register_text(QLabel(self._t("wavelength_label")), "wavelength_label")
        sel_lo.addWidget(self._lbl_wl)
        self.cb_wl_g = QComboBox()
        self.cb_wl_g.setMaximumWidth(110)
        sel_lo.addWidget(self.cb_wl_g)
        sel_lo.addStretch()
        wl_lo.addLayout(sel_lo)
        llo.addWidget(grp_wl)

        # ── Zoom positions ──
        self._grp_zoom_g = self._register_text(QGroupBox(self._t("zoom_positions")), "zoom_positions", "setTitle")
        self._zl_grid = QGridLayout(self._grp_zoom_g)
        self.chk_zoom = {}
        self.cmb_corr_zoom = None  # created later in Correction section
        self._rebuild_zoom_checkboxes(1)
        llo.addWidget(self._grp_zoom_g)

        # ── Parameters ──
        llo.addWidget(self._build_param_group('g', 5, 5))

        # ── Correction section ──
        self._grp_corr = self._register_text(QGroupBox(self._t("correction_section")), "correction_section", "setTitle")
        corr_lo = QVBoxLayout(self._grp_corr)
        corr_lo.setSpacing(4)

        # Panel Geometry
        pg_lo = QHBoxLayout()
        self.dsb_corr_pw = QDoubleSpinBox(); self.dsb_corr_pw.setRange(0.0, 999)
        self.dsb_corr_pw.setValue(0.0); self.dsb_corr_pw.setDecimals(3)
        self.dsb_corr_pw.setMaximumWidth(72)
        self.dsb_corr_ph = QDoubleSpinBox(); self.dsb_corr_ph.setRange(0.0, 999)
        self.dsb_corr_ph.setValue(0.0); self.dsb_corr_ph.setDecimals(3)
        self.dsb_corr_ph.setMaximumWidth(72)
        pg_lo.addWidget(self._register_text(QLabel(self._t("panel_half_w")), "panel_half_w")); pg_lo.addWidget(self.dsb_corr_pw)
        pg_lo.addWidget(self._register_text(QLabel(self._t("panel_half_h")), "panel_half_h")); pg_lo.addWidget(self.dsb_corr_ph)
        corr_lo.addLayout(pg_lo)

        # Zoom selection
        zoom_corr_lo = QHBoxLayout()
        zoom_corr_lo.addWidget(self._register_text(QLabel(self._t("zoom_label")), "zoom_label"))
        self.cmb_corr_zoom = QComboBox(); self.cmb_corr_zoom.setMaximumWidth(110)
        zoom_corr_lo.addWidget(self.cmb_corr_zoom)
        zoom_corr_lo.addStretch()
        corr_lo.addLayout(zoom_corr_lo)

        # Display panel
        dp_lo = QFormLayout(); dp_lo.setVerticalSpacing(2)
        self.cmb_corr_brand = QComboBox(); self.cmb_corr_brand.setMaximumWidth(140)
        self.cmb_corr_model = QComboBox(); self.cmb_corr_model.setMaximumWidth(140)
        self.cmb_corr_brand.activated.connect(self._on_corr_brand_changed)
        self.cmb_corr_model.activated.connect(self._on_corr_model_changed)
        # 每次展开品牌下拉前重新读取 displays.json（支持热更新）
        _orig_show_popup = self.cmb_corr_brand.showPopup
        def _reload_then_show():
            self._load_displays_db()
            _orig_show_popup()
        self.cmb_corr_brand.showPopup = _reload_then_show
        dp_lo.addRow(self._register_text(QLabel(self._t("brand")), "brand"), self.cmb_corr_brand)
        dp_lo.addRow(self._register_text(QLabel(self._t("model")), "model"), self.cmb_corr_model)
        self.sb_corr_w0 = QSpinBox(); self.sb_corr_w0.setRange(1, 99999); self.sb_corr_w0.setValue(1920); self.sb_corr_w0.setMaximumWidth(80)
        self.sb_corr_h0 = QSpinBox(); self.sb_corr_h0.setRange(1, 99999); self.sb_corr_h0.setValue(1080); self.sb_corr_h0.setMaximumWidth(80)
        self.sb_corr_w = QSpinBox(); self.sb_corr_w.setRange(1, 99999); self.sb_corr_w.setValue(1920); self.sb_corr_w.setMaximumWidth(80)
        self.sb_corr_h = QSpinBox(); self.sb_corr_h.setRange(1, 99999); self.sb_corr_h.setValue(1080); self.sb_corr_h.setMaximumWidth(80)
        self.dsb_corr_px = QDoubleSpinBox(); self.dsb_corr_px.setRange(0.0001, 5.0)
        self.dsb_corr_px.setValue(0.00756); self.dsb_corr_px.setDecimals(6); self.dsb_corr_px.setMaximumWidth(90)
        self.sb_corr_cols = QSpinBox(); self.sb_corr_cols.setRange(3, 101); self.sb_corr_cols.setValue(17); self.sb_corr_cols.setMaximumWidth(70)
        self.sb_corr_rows = QSpinBox(); self.sb_corr_rows.setRange(3, 101); self.sb_corr_rows.setValue(9); self.sb_corr_rows.setMaximumWidth(70)
        self.dsb_corr_ox = QDoubleSpinBox(); self.dsb_corr_ox.setRange(-9999, 9999); self.dsb_corr_ox.setValue(0); self.dsb_corr_ox.setDecimals(3); self.dsb_corr_ox.setMaximumWidth(80)
        self.dsb_corr_oy = QDoubleSpinBox(); self.dsb_corr_oy.setRange(-9999, 9999); self.dsb_corr_oy.setValue(0); self.dsb_corr_oy.setDecimals(3); self.dsb_corr_oy.setMaximumWidth(80)
        dp_lo.addRow(self._register_text(QLabel(self._t("active_w_px")), "active_w_px"), self.sb_corr_w0)
        dp_lo.addRow(self._register_text(QLabel(self._t("active_h_px")), "active_h_px"), self.sb_corr_h0)
        dp_lo.addRow(self._register_text(QLabel(self._t("pre_corr_w_px")), "pre_corr_w_px"), self.sb_corr_w)
        dp_lo.addRow(self._register_text(QLabel(self._t("pre_corr_h_px")), "pre_corr_h_px"), self.sb_corr_h)
        dp_lo.addRow(self._register_text(QLabel(self._t("pixel_size")), "pixel_size"), self.dsb_corr_px)
        dp_lo.addRow(self._register_text(QLabel(self._t("numcols")), "numcols"), self.sb_corr_cols)
        dp_lo.addRow(self._register_text(QLabel(self._t("numrows")), "numrows"), self.sb_corr_rows)
        dp_lo.addRow(self._register_text(QLabel(self._t("offset_x")), "offset_x"), self.dsb_corr_ox)
        dp_lo.addRow(self._register_text(QLabel(self._t("offset_y")), "offset_y"), self.dsb_corr_oy)
        corr_lo.addLayout(dp_lo)

        # Symmetry
        sym_lo = QHBoxLayout()
        self.chk_corr_sym_h = self._register_text(QCheckBox(self._t("h_symmetry")), "h_symmetry")
        self.chk_corr_sym_h.setChecked(True)
        self.chk_corr_sym_v = self._register_text(QCheckBox(self._t("v_symmetry")), "v_symmetry")
        self.chk_corr_sym_v.setChecked(False)
        sym_lo.addWidget(self.chk_corr_sym_h); sym_lo.addWidget(self.chk_corr_sym_v)
        corr_lo.addLayout(sym_lo)

        # Source mode: CODE V vs TXT files
        src_mode_lo = QHBoxLayout()
        src_mode_lo.addWidget(self._register_text(QLabel(self._t("source")), "source"))
        self.rb_corr_codev = self._register_text(QRadioButton(self._t("code_v")), "code_v")
        self.rb_corr_txt = self._register_text(QRadioButton(self._t("txt_files")), "txt_files")
        self.rb_corr_codev.setChecked(True)
        self.bg_corr_src = QButtonGroup(self)
        self.bg_corr_src.addButton(self.rb_corr_codev, 0)
        self.bg_corr_src.addButton(self.rb_corr_txt, 1)
        self.bg_corr_src.buttonClicked.connect(self._on_corr_src_changed)
        src_mode_lo.addWidget(self.rb_corr_codev)
        src_mode_lo.addWidget(self.rb_corr_txt)
        src_mode_lo.addStretch()
        corr_lo.addLayout(src_mode_lo)

        # TXT file pickers (R/G/B, hidden by default)
        self._corr_txt_rows = QVBoxLayout()
        self._corr_txt_collect = []  # list of (QLabel, QLineEdit, QPushButton)

        for ch in ["R", "G", "B"]:
            row = QHBoxLayout()
            lbl = self._register_text(QLabel(self._t("file_label").format(channel=ch)), "file_label", fmt_args={"channel": ch})
            ed = QLineEdit()
            ed.setMaximumWidth(200)
            btn = self._register_text(QPushButton(self._t("browse")), "browse")
            btn.clicked.connect(lambda checked, c=ch: self._browse_corr_txt(c))
            row.addWidget(lbl)
            row.addWidget(ed)
            row.addWidget(btn)
            self._corr_txt_rows.addLayout(row)
            self._corr_txt_collect.append((lbl, ed, btn, row))
        corr_lo.addLayout(self._corr_txt_rows)
        # Hide TXT file rows initially
        self._corr_txt_rows_set_visible(False)

        llo.addWidget(self._grp_corr)

        # ── 面板半宽/半高 ↔ 有效宽/高 双向联动（所有 widget 创建后绑定）──
        self._panel_sync_lock = False
        self.dsb_corr_pw.valueChanged.connect(self._on_panel_hw_changed)
        self.dsb_corr_ph.valueChanged.connect(self._on_panel_hh_changed)
        self.sb_corr_w0.valueChanged.connect(self._on_active_w_changed)
        self.sb_corr_h0.valueChanged.connect(self._on_active_h_changed)

        # ── Buttons: Row 1 (Analysis) ──
        btn_lo1 = QHBoxLayout()
        btn_run = self._register_text(QPushButton("  \u25b6 " + self._t("start_analysis") + "  "), "start_analysis", template="  \u25b6 {label}  ")
        btn_run.setStyleSheet(
            "QPushButton{font-size:13px;font-weight:bold;padding:6px 12px;"
            "background:#1976D2;color:white;border-radius:4px;}"
            "QPushButton:disabled{background:#9e9e9e;color:#e0e0e0;}")
        btn_run.clicked.connect(lambda: self._on_run_tab(0))
        self._btn_run_g = btn_run
        btn_exp = self._register_text(QPushButton("  \U0001F4BE " + self._t("export_png") + "  "), "export_png", template="  \U0001F4BE {label}  ")
        btn_exp.setStyleSheet(
            "font-size:13px;font-weight:bold;padding:6px 12px;"
            "background:#43a047;color:white;border-radius:4px;")
        btn_exp.clicked.connect(lambda: self._on_export_tab(0))
        btn_lo1.addWidget(btn_run)
        btn_lo1.addWidget(btn_exp)
        btn_lo1.addStretch()
        llo.addLayout(btn_lo1)

        # ── Buttons: Row 2 (Correction) ──
        btn_lo2 = QHBoxLayout()
        self._btn_corr_fit = self._register_text(QPushButton("  \U0001F9EE " + self._t("fit_correction") + "  "), "fit_correction", template="  \U0001F9EE {label}  ")
        self._btn_corr_fit.setStyleSheet(
            "QPushButton{font-size:13px;font-weight:bold;padding:6px 12px;"
            "background:#E65100;color:white;border-radius:4px;}"
            "QPushButton:disabled{background:#9e9e9e;color:#e0e0e0;}")
        self._btn_corr_fit.clicked.connect(self._on_fit_correction)
        self._btn_corr_export = self._register_text(QPushButton("  \U0001F4E4 " + self._t("export_csv") + "  "), "export_csv", template="  \U0001F4E4 {label}  ")
        self._btn_corr_export.setStyleSheet(
            "font-size:13px;font-weight:bold;padding:6px 12px;"
            "background:#6A1B9A;color:white;border-radius:4px;")
        self._btn_corr_export.clicked.connect(self._export_correction_csv)
        btn_lo2.addWidget(self._btn_corr_fit)
        btn_lo2.addWidget(self._btn_corr_export)
        btn_lo2.addStretch()
        llo.addLayout(btn_lo2)

        llo.addStretch()
        left_scroll.setWidget(left_panel)

        # ---- Right: canvas with Distortion / Correction tabs ----
        canvas_dist = self._build_canvas_tab("fig_g", "canvas_g", "tb_g", "Distortion Grid")
        canvas_corr = self._build_canvas_tab("fig_corr", "canvas_corr", "tb_corr", "Correction Grid")
        self._right_tabs = QTabWidget()
        self._right_tabs.addTab(canvas_dist, "  \U0001F4CF " + self._t("tab_distortion") + "  ")
        self._right_tabs.addTab(canvas_corr, "  \U0001F9EE " + self._t("tab_correction") + "  ")
        lo.addWidget(left_scroll)
        lo.addWidget(self._right_tabs, 1)
        return w

    # ---------- Tab 2: Pupil Swim ----------
    def _build_tab_pupil_swim(self):
        """Tab 2: left = parameters + buttons, right = matplotlib canvas."""
        w = QWidget()
        lo = QHBoxLayout(w)
        lo.setContentsMargins(0, 0, 0, 0)

        # ---- Left: parameter panel ----
        left_scroll = QScrollArea()
        left_scroll.setWidgetResizable(True)
        left_scroll.setMinimumWidth(290)
        left_panel = QWidget()
        llo = QVBoxLayout(left_panel)
        llo.setSpacing(6)

        # Zoom pair
        self._grp_zoom_ps = self._register_text(QGroupBox(self._t("zoom_positions_ref_target")), "zoom_positions_ref_target", "setTitle")
        self._zl_ps = QFormLayout(self._grp_zoom_ps)
        self.cb_ref = QComboBox(); self.cb_ref.setMaximumWidth(110)
        self.cb_tgt = QComboBox(); self.cb_tgt.setMaximumWidth(110)
        self._zl_ps.addRow(self._register_text(QLabel(self._t("reference")), "reference"), self.cb_ref)
        self._zl_ps.addRow(self._register_text(QLabel(self._t("target")), "target"), self.cb_tgt)
        self._rebuild_ps_zoom_combos(12)
        llo.addWidget(self._grp_zoom_ps)

        # Output format
        grp_of = self._register_text(QGroupBox(self._t("output_format")), "output_format", "setTitle")
        of_lo = QVBoxLayout(grp_of)
        self.bg_fmt = QButtonGroup(self)
        self.rb_fmt_both = self._register_text(QRadioButton(self._t("both_grid_vectors_heatmap")), "both_grid_vectors_heatmap")
        self.rb_fmt_vec = self._register_text(QRadioButton(self._t("grid_vectors_only")), "grid_vectors_only")
        self.rb_fmt_hm = self._register_text(QRadioButton(self._t("heatmap_only")), "heatmap_only")
        self.bg_fmt.addButton(self.rb_fmt_both, 0)
        self.bg_fmt.addButton(self.rb_fmt_vec, 1)
        self.bg_fmt.addButton(self.rb_fmt_hm, 2)
        self.rb_fmt_both.setChecked(True)
        of_lo.addWidget(self.rb_fmt_both)
        of_lo.addWidget(self.rb_fmt_vec)
        of_lo.addWidget(self.rb_fmt_hm)
        llo.addWidget(grp_of)

        # Parameters
        llo.addWidget(self._build_param_group('ps', 26.565, 26.565))

        # Buttons: Start Analysis + Export PNG
        btn_lo = QHBoxLayout()
        btn_run = self._register_text(QPushButton("  \u25b6 " + self._t("start_analysis") + "  "), "start_analysis", template="  \u25b6 {label}  ")
        btn_run.setStyleSheet(
            "QPushButton{font-size:13px;font-weight:bold;padding:6px 12px;"
            "background:#1976D2;color:white;border-radius:4px;}"
            "QPushButton:disabled{background:#9e9e9e;color:#e0e0e0;}")
        btn_run.clicked.connect(lambda: self._on_run_tab(1))
        self._btn_run_ps = btn_run
        btn_exp = self._register_text(QPushButton("  \U0001F4BE " + self._t("export_png") + "  "), "export_png", template="  \U0001F4BE {label}  ")
        btn_exp.setStyleSheet(
            "font-size:13px;font-weight:bold;padding:6px 12px;"
            "background:#43a047;color:white;border-radius:4px;")
        btn_exp.clicked.connect(lambda: self._on_export_tab(1))
        btn_lo.addWidget(btn_run)
        btn_lo.addWidget(btn_exp)
        btn_lo.addStretch()
        llo.addLayout(btn_lo)

        llo.addStretch()
        left_scroll.setWidget(left_panel)

        # ---- Right: canvas with Vectors / Heatmap tabs ----
        canvas_vec = self._build_canvas_tab("fig_psv", "canvas_psv", "tb_psv", "Grid Vectors")
        canvas_hm = self._build_canvas_tab("fig_psh", "canvas_psh", "tb_psh", "Heatmap")
        self._right_tabs_ps = QTabWidget()
        self._right_tabs_ps.addTab(canvas_vec, "  \u27A1\ufe0f " + self._t("grid_vectors") + "  ")
        self._right_tabs_ps.addTab(canvas_hm, "  \U0001F321\ufe0f " + self._t("heatmap") + "  ")
        lo.addWidget(left_scroll)
        lo.addWidget(self._right_tabs_ps, 1)
        return w

    # === Canvas builder (matplotlib tabs) ===
    def _build_canvas_tab(self, fig_attr, canvas_attr, toolbar_attr, title):
        """Build a single matplotlib canvas tab (in-tab embedding, not popup)."""
        _init_mpl()
        from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
        from matplotlib.figure import Figure

        tab = QWidget()
        tl = QVBoxLayout(tab)
        fig = Figure(figsize=(8, 6))
        canvas = FigureCanvas(fig)
        canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        tl.addWidget(canvas)
        setattr(self, fig_attr, fig)
        setattr(self, canvas_attr, canvas)
        return tab

    def _load_displays_db(self):
        """Load display panel database. 打包后优先读 exe 同目录的 displays.json。"""
        from distortion_correction import load_displays_db
        if getattr(sys, 'frozen', False):
            # 打包模式：先找 exe 同目录，找不到再用打包内置的
            external = Path(sys.executable).parent / "displays.json"
            bundled = Path(sys._MEIPASS) / "displays.json"
            db_path = str(external if external.is_file() else bundled)
        else:
            db_path = str(Path(__file__).parent / "displays.json")
        self._displays_db = load_displays_db(db_path)
        brands = sorted(set(d["brand"] for d in self._displays_db))
        self.cmb_corr_brand.clear()
        self.cmb_corr_brand.addItem(self._t("manual"), None)
        for b in brands:
            self.cmb_corr_brand.addItem(b, b)
        self.cmb_corr_model.clear()
        self.cmb_corr_model.addItem(self._t("manual"), -1)

    def _on_corr_brand_changed(self, idx):
        self.cmb_corr_model.clear()
        brand = self.cmb_corr_brand.currentData()
        if brand is None:
            self.cmb_corr_model.addItem(self._t("manual"), -1)
        else:
            items = sorted((d for d in self._displays_db if d["brand"] == brand),
                           key=lambda d: d["model"])
            self.cmb_corr_model.addItem(self._t("select_model"), -1)
            for d in items:
                sz = f'{d["size"]}" ' if d["size"] > 0 else ""
                idx_db = self._displays_db.index(d)
                self.cmb_corr_model.addItem(f"{sz}{d['model']}", idx_db)

    def _on_corr_model_changed(self, idx):
        entry_idx = self.cmb_corr_model.currentData()
        if entry_idx is None or entry_idx < 0:
            return
        entry = self._displays_db[entry_idx]
        self.sb_corr_w0.setValue(entry["width0"])
        self.sb_corr_h0.setValue(entry["height0"])
        self.dsb_corr_px.setValue(entry["pixelsize_mm"])
        self.sb_corr_w.setValue(entry["width0"])
        self.sb_corr_h.setValue(entry["height0"])
        pw = entry["width0"] * entry["pixelsize_mm"] / 2
        ph = entry["height0"] * entry["pixelsize_mm"] / 2
        self.dsb_corr_pw.setValue(pw)
        self.dsb_corr_ph.setValue(ph)

    # ── 面板半宽/半高 ↔ 有效宽/高 双向联动 ──
    def _on_panel_hw_changed(self, val):
        if self._panel_sync_lock: return
        px = self.dsb_corr_px.value()
        if px > 0:
            self._panel_sync_lock = True
            self.sb_corr_w0.setValue(int(round(val * 2 / px)))
            self._panel_sync_lock = False

    def _on_panel_hh_changed(self, val):
        if self._panel_sync_lock: return
        px = self.dsb_corr_px.value()
        if px > 0:
            self._panel_sync_lock = True
            self.sb_corr_h0.setValue(int(round(val * 2 / px)))
            self._panel_sync_lock = False

    def _on_active_w_changed(self, val):
        if self._panel_sync_lock: return
        px = self.dsb_corr_px.value()
        self._panel_sync_lock = True
        self.dsb_corr_pw.setValue(val * px / 2)
        self._panel_sync_lock = False

    def _on_active_h_changed(self, val):
        if self._panel_sync_lock: return
        px = self.dsb_corr_px.value()
        self._panel_sync_lock = True
        self.dsb_corr_ph.setValue(val * px / 2)
        self._panel_sync_lock = False

    # ========== Correction: source mode ==========
    def _on_corr_src_changed(self, btn):
        """Toggle CODE V / TXT source mode UI."""
        is_txt = (self.bg_corr_src.id(btn) == 1)
        self._corr_txt_rows_set_visible(is_txt)
        if is_txt:
            self._btn_corr_fit.setText("  \U0001F9EE " + self._t("fit_from_txt") + "  ")
        else:
            self._btn_corr_fit.setText("  \U0001F9EE " + self._t("fit_correction") + "  ")

    def _corr_txt_rows_set_visible(self, vis):
        for _, ed, btn, _ in self._corr_txt_collect:
            ed.setVisible(vis)
            btn.setVisible(vis)
        # Also show/hide labels (first item's label)
        for lbl, _, _, _ in self._corr_txt_collect:
            lbl.setVisible(vis)

    def _browse_corr_txt(self, channel):
        """Browse for a single R/G/B TXT file."""
        ch_idx = {"R": 0, "G": 1, "B": 2}[channel]
        _, ed, _, _ = self._corr_txt_collect[ch_idx]
        current = ed.text().strip()
        if current and Path(current).parent.is_dir():
            start_dir = str(Path(current).parent)
        else:
            start_dir = str(Path(self.ed_seq.text().strip()).parent) if Path(self.ed_seq.text().strip()).is_file() else ""
        f, _ = QFileDialog.getOpenFileName(self, f"{self._t('open_txt_title')} {channel}.txt",
                                            start_dir, "TXT files (*.txt)")
        if f:
            ed.setText(f)

    def _on_fit_correction(self):
        """Fit correction: route to CODE V or TXT mode."""
        if self.rb_corr_txt.isChecked():
            self._run_correction_fit_only()
        else:
            self._run_correction_codev()

    # ========== Correction: populate SEQ info ==========
    def _populate_corr_seq_info(self):
        """Extract wavelengths/zoom info from SEQ for correction section."""
        from distortion_analyzer import DistortionAnalyzer
        seq = self.ed_seq.text().strip()
        if not Path(seq).is_file():
            return

        # Store wavelengths for correction (R=longest, G=center, B=shortest)
        try:
            wl_info = DistortionAnalyzer.get_wavelengths_from_seq(seq)
            wavelengths = wl_info['wavelengths']
            ref_idx = wl_info['ref_index']
        except Exception:
            wavelengths = [625.0]; ref_idx = 1

        self._corr_wavelengths = wavelengths
        self._corr_ref_idx = ref_idx

        # Derive R/G/B wavelength indices
        if len(wavelengths) >= 3:
            wl_vals = [(i+1, v) for i, v in enumerate(wavelengths)]
            self._corr_wl_r = max(wl_vals, key=lambda x: x[1])[0]
            self._corr_wl_g = ref_idx
            self._corr_wl_b = min(wl_vals, key=lambda x: x[1])[0]
        else:
            self._corr_wl_r = ref_idx
            self._corr_wl_g = ref_idx
            self._corr_wl_b = ref_idx

    # ========== Correction: handlers ==========
    def _run_correction_codev(self) -> None:
        """Run CODE V R/G/B trace + polynomial fitting (using Tab 1 controls)."""
        seq = self.ed_seq.text().strip()
        if not Path(seq).is_file():
            QMessageBox.warning(self, self._t("error_title"), self._t("select_valid_seq")); return

        # R/G/B wavelength indices (auto-derived from SEQ)
        if not hasattr(self, '_corr_wl_g') or self._corr_wl_g is None:
            QMessageBox.warning(self, self._t("error_title"), self._t("load_seq_first")); return
        wl_eff = [self._corr_wl_r, self._corr_wl_g, self._corr_wl_b]

        # FOV from Tab 1 shared spinners
        halfx = self.sp_fovx_g.value()
        halfy = self.sp_fovy_g.value()

        # Zoom: from Correction section's own combo
        zoom = self.cmb_corr_zoom.currentData()
        if zoom is None:
            zoom = 1

        macro = str(Path(__file__).parent / "dist_real_pro.seq")

        self._log("=" * 50)
        self._log(f"Correction: {Path(seq).name}")
        self._log(f"R/G/B WL indices: {wl_eff}")
        self._log(f"FOV H={halfx:.3f} V={halfy:.3f} Zoom={zoom} N={self.sp_gs_g.value()}")

        self._btn_corr_fit.setEnabled(False)
        self._btn_corr_export.setEnabled(False)
        self._btn_run_g.setEnabled(False)
        self._btn_run_ps.setEnabled(False)
        self.bar.setRange(0, 0)

        self._corr_worker = CorrectionWorker(
            seq, halfx, halfy,
            self.dsb_corr_pw.value(), self.dsb_corr_ph.value(),
            zoom, self.sp_gs_g.value(), wl_eff, macro)
        self._corr_thread = QThread()
        self._corr_worker.moveToThread(self._corr_thread)
        self._corr_worker.progress.connect(self._log)
        self._corr_worker.finished.connect(self._on_correction_done)
        self._corr_worker.finished.connect(self._corr_thread.quit)
        self._corr_thread.started.connect(self._corr_worker.run)
        self._corr_thread.start()

    def _on_correction_done(self, work_dir, zoom, err):
        self._btn_corr_fit.setEnabled(True)
        self._btn_corr_export.setEnabled(True)
        self._btn_run_g.setEnabled(True)
        self._btn_run_ps.setEnabled(True)
        self.bar.setRange(0, 1)
        if err:
            self._log(f"[Correction Error] {err}")
            QMessageBox.critical(self, "CODE V Error", err[:500])
            return
        self._corr_work_dir = work_dir
        z_prefix = f"z{zoom}_"
        paths = {c: str(Path(work_dir) / f"{z_prefix}{c}.txt") for c in ["r", "g", "b"]}
        self._run_correction_fit(paths)

    def _run_correction_fit_only(self):
        """Read R/G/B TXT files (missing filled with G>R>B priority)."""
        paths = {}
        for ch_idx, ch in enumerate(["R", "G", "B"]):
            _, ed, _, _ = self._corr_txt_collect[ch_idx]
            p = ed.text().strip()
            if p and Path(p).is_file():
                paths[ch.lower()] = p
        if not paths:
            QMessageBox.warning(self, self._t("error_title"), self._t("select_txt_file"))
            return
        self._run_correction_fit(paths)

    def _run_correction_fit(self, paths):
        from distortion_correction import parse_dist_txt, fit_distortion, build_csv_content
        self._log(f"Reading txt: {list(paths.keys())}")
        try:
            # Parse available files
            data = {}  # {'r': ndarray, 'g': ndarray, 'b': ndarray}
            for ch in ["r", "g", "b"]:
                if ch in paths and Path(paths[ch]).is_file():
                    data[ch] = parse_dist_txt(paths[ch])
                    self._log(f"  Loaded {ch}.txt: {len(data[ch])} points")
                else:
                    self._log(f"  {ch}.txt: not found")

            if not data:
                raise FileNotFoundError("No TXT data loaded")

            # Fill missing channels with priority: G > R > B
            for ch in ["r", "g", "b"]:
                if ch not in data:
                    for src in ["g", "r", "b"]:  # G first, then R, then B
                        if src in data:
                            data[ch] = data[src].copy()
                            self._log(f"  {ch}.txt: filled from {src}.txt")
                            break

            self._log(f"Data points: R={len(data['r'])}, G={len(data['g'])}, B={len(data['b'])}")
            if len(data['r']) == 0 or len(data['g']) == 0 or len(data['b']) == 0:
                raise ValueError("R/G/B trace files must contain data")
            if not (len(data['r']) == len(data['g']) == len(data['b'])):
                raise ValueError("R/G/B trace files have mismatched point counts")

            disdata = np.stack([data['r'], data['g'], data['b']], axis=2)
            p = self._corr_params()

            self._log("Fitting...")
            QApplication.processEvents()

            rdx, rdy, pdx, pdy, ix, iy = fit_distortion(
                disdata=disdata,
                pixelsize=p["pixelsize"],
                Width0=p["Width0"], Height0=p["Height0"],
                Width=p["Width"], Height=p["Height"],
                NumCols=p["NumCols"], NumRows=p["NumRows"],
                OffsetXPixel=p["OffsetXPixel"], OffsetYPixel=p["OffsetYPixel"],
                sym_h=self.chk_corr_sym_h.isChecked(),
                sym_v=self.chk_corr_sym_v.isChecked(),
            )

            SizeX = p["Width0"] * p["pixelsize"]
            SizeY = p["Height0"] * p["pixelsize"]
            OffsetY = p["OffsetYPixel"] * p["pixelsize"]

            self._corr_csv_str = build_csv_content(
                SizeX, SizeY, p["NumCols"], p["NumRows"], OffsetY,
                ix, iy, pdx, pdy, rdx, rdy,
            )
            self._corr_fit_result = dict(
                rdx=rdx, rdy=rdy, pdx=pdx, pdy=pdy,
                ix=ix, iy=iy,
                NumCols=p["NumCols"], NumRows=p["NumRows"],
                pixelsize=p["pixelsize"], disdata=disdata,
            )

            self._log("Fitting done. Drawing...")
            self._draw_correction_grid()
            self._right_tabs.setCurrentIndex(1)  # switch to Correction canvas
            self._log("Done! Click 'Export CSV' to save.")

        except Exception as e:
            self._log(f"[Fit Error] {e}\n{traceback.format_exc()}")
            QMessageBox.critical(self, self._t("fit_error_title"), str(e))

    def _corr_params(self) -> dict:
        return dict(
            Width0=self.sb_corr_w0.value(), Height0=self.sb_corr_h0.value(),
            Width=self.sb_corr_w.value(), Height=self.sb_corr_h.value(),
            pixelsize=self.dsb_corr_px.value(),
            NumCols=self.sb_corr_cols.value(), NumRows=self.sb_corr_rows.value(),
            OffsetXPixel=self.dsb_corr_ox.value(), OffsetYPixel=self.dsb_corr_oy.value(),
        )

    def _draw_correction_grid(self):
        """Draw fitted distortion grid on the embedded canvas."""
        r = self._corr_fit_result
        NC, NR = r["NumCols"], r["NumRows"]
        px = r["pixelsize"]
        disdata = r["disdata"]
        n_pts = int(round(disdata.shape[0] ** 0.5))
        off_y = self.dsb_corr_oy.value()

        self.fig_corr.clear()
        ax = self.fig_corr.add_subplot(111)
        ax.set_aspect("equal")
        ax.set_facecolor("#f9f9f9")
        ax.set_title("Distortion Grid (dashed=CODE V raw, solid=fitted, black=ideal)", fontsize=10)
        ax.set_xlabel("x (pixel)"); ax.set_ylabel("y (pixel)")

        colors = ["#e53935", "#43a047", "#1e88e5"]
        labels = ["R", "G", "B"]

        # CODE V raw (dashed)
        for n in range(3):
            RX = disdata[:, 2, n].reshape(n_pts, n_pts) / px
            RY = disdata[:, 3, n].reshape(n_pts, n_pts) / px
            for i in range(n_pts):
                ax.plot(RX[i, :], RY[i, :], "--", color=colors[n], alpha=0.3, lw=0.7)
                ax.plot(RX[:, i], RY[:, i], "--", color=colors[n], alpha=0.3, lw=0.7)

        # Fitted (solid)
        for n in range(3):
            rxg = r["rdx"][:, n].reshape(NR, NC, order='F') / px
            ryg = r["rdy"][:, n].reshape(NR, NC, order='F') / px - off_y
            for i in range(NR):
                ax.plot(rxg[i, :], ryg[i, :], "-", color=colors[n], lw=1.0,
                        label=f"Fitted-{labels[n]}" if i == 0 else "")
            for j in range(NC):
                ax.plot(rxg[:, j], ryg[:, j], "-", color=colors[n], lw=1.0)

        # Ideal (black)
        w0 = self.sb_corr_w0.value(); h0 = self.sb_corr_h0.value()
        refx, refy = np.meshgrid(
            np.linspace(-w0 / 2, w0 / 2, NC),
            np.linspace(h0 / 2, -h0 / 2, NR)
        )
        for i in range(NR):
            ax.plot(refx[i, :], refy[i, :], "-", color="black", lw=0.6, alpha=0.4,
                    label="Ideal" if i == 0 else "")
        for j in range(NC):
            ax.plot(refx[:, j], refy[:, j], "-", color="black", lw=0.6, alpha=0.4)

        ax.legend(loc="upper right", fontsize=8, ncol=2)
        ax.grid(True, linestyle=":", alpha=0.3)
        self.fig_corr.tight_layout()
        self.canvas_corr.draw()

    def _export_correction_csv(self):
        if not hasattr(self, '_corr_csv_str') or not self._corr_csv_str:
            QMessageBox.warning(self, self._t("hint_title"), self._t("run_fit_first")); return

        wd = self._corr_work_dir if hasattr(self, '_corr_work_dir') and self._corr_work_dir else ""
        default = str(Path(wd) / "svrapi_lens_left.csv") if wd else ""
        path, _ = QFileDialog.getSaveFileName(self, self._t("export_csv_save_title"), default,
                                               "CSV (*.csv);;All (*)")
        if not path: return

        Path(path).write_text(self._corr_csv_str, newline='')
        base = Path(path)
        if base.name.lower().endswith('_left.csv'):
            right_path = base.with_name(base.name[:-9] + '_right.csv')
        elif base.suffix.lower() == '.csv':
            right_path = base.with_name(base.stem + '_right.csv')
        else:
            right_path = Path(str(base) + '_right.csv')

        Path(right_path).write_text(self._corr_csv_str, newline='')

        self._log(f"CSV saved: {path}")
        self._log(f"           {right_path}")
        QMessageBox.information(self, self._t("saved_title"),
                                self._t("saved_message").format(path=f"{path}\n{right_path}"))

    # ========== File Browsers & Settings ==========
    def _show_settings(self):
        dlg = SettingsDialog(self)
        dlg.exec_()

    def _t(self, key):
        return I18N[_current_lang].get(key, key)

    def _refresh_ui_language(self):
        """Update all UI labels to current language immediately."""
        self.setWindowTitle(self._t("app_title"))
        self.tabs.setTabText(0, "  \U0001F4CF " + self._t("tab_distortion") + "  ")
        self.tabs.setTabText(1, "  \U0001F441 " + self._t("tab_pupil_swim") + "  ")
        for widget, method, key, fmt_args, template in self._localized_widgets:
            text = self._t(key)
            if template is not None:
                text = template.format(label=text, **(fmt_args or {}))
            elif fmt_args is not None:
                text = text.format(**fmt_args)
            getattr(widget, method)(text)
        if hasattr(self, '_btn_settings'):
            self._btn_settings.setText("  \u2699\uFE0F " + self._t("settings") + "  ")
        if hasattr(self, '_btn_sa_g'):
            self._btn_sa_g.setText(self._t("select_all"))
        if hasattr(self, '_btn_cl_g'):
            self._btn_cl_g.setText(self._t("clear"))
        if hasattr(self, '_right_tabs'):
            self._right_tabs.setTabText(0, "  \U0001F4CF " + self._t("tab_distortion") + "  ")
            self._right_tabs.setTabText(1, "  \U0001F441 " + self._t("tab_pupil_swim") + "  ")
        if hasattr(self, '_right_tabs_ps'):
            self._right_tabs_ps.setTabText(0, "  \u27A1\ufe0f " + self._t("grid_vectors") + "  ")
            self._right_tabs_ps.setTabText(1, "  \U0001F321\ufe0f " + self._t("heatmap") + "  ")
        if hasattr(self, 'chk_zoom'):
            def preserve_suffix(old_text, new_prefix):
                if old_text.startswith(new_prefix):
                    return old_text[len(new_prefix):]
                if ' ' in old_text:
                    return old_text[old_text.index(' '):]
                return ''

            for zid, chk in self.chk_zoom.items():
                if chk is None:
                    continue
                prefix = I18N[_current_lang]["zoom_item"].format(id=zid)
                suffix = preserve_suffix(chk.text(), prefix)
                chk.setText(prefix + suffix)
                chk.setToolTip(I18N[_current_lang]["zoom_tooltip"].format(id=zid))
        if hasattr(self, 'cmb_corr_zoom') and self.cmb_corr_zoom is not None:
            sel = self.cmb_corr_zoom.currentData()
            old_items = [self.cmb_corr_zoom.itemText(i) for i in range(self.cmb_corr_zoom.count())]
            self.cmb_corr_zoom.clear()
            count = len(self.chk_zoom)
            for zid in range(1, count + 1):
                prefix = I18N[_current_lang]["zoom_item"].format(id=zid)
                suffix = ''
                if zid - 1 < len(old_items):
                    suffix = preserve_suffix(old_items[zid - 1], prefix)
                self.cmb_corr_zoom.addItem(prefix + suffix, zid)
            if sel is not None:
                idx = self.cmb_corr_zoom.findData(sel)
                if idx >= 0:
                    self.cmb_corr_zoom.setCurrentIndex(idx)
        if hasattr(self, 'cb_ref') and hasattr(self, 'cb_tgt'):
            ref_sel = self.cb_ref.currentData()
            tgt_sel = self.cb_tgt.currentData()
            old_ref_items = [self.cb_ref.itemText(i) for i in range(self.cb_ref.count())]
            old_tgt_items = [self.cb_tgt.itemText(i) for i in range(self.cb_tgt.count())]
            count = len(self.chk_zoom)
            self.cb_ref.clear(); self.cb_tgt.clear()
            for z in range(1, count + 1):
                prefix = I18N[_current_lang]["zoom_item"].format(id=z)
                ref_suffix = preserve_suffix(old_ref_items[z - 1], prefix) if z - 1 < len(old_ref_items) else ''
                tgt_suffix = preserve_suffix(old_tgt_items[z - 1], prefix) if z - 1 < len(old_tgt_items) else ''
                self.cb_ref.addItem(prefix + ref_suffix, userData=z)
                self.cb_tgt.addItem(prefix + tgt_suffix, userData=z)
            if ref_sel is not None:
                idx = self.cb_ref.findData(ref_sel)
                if idx >= 0:
                    self.cb_ref.setCurrentIndex(idx)
            if tgt_sel is not None:
                idx = self.cb_tgt.findData(tgt_sel)
                if idx >= 0:
                    self.cb_tgt.setCurrentIndex(idx)
        if hasattr(self, '_wl_info') and self._wl_info and hasattr(self, 'cb_wl_g'):
            ref_idx = self._wl_info.get('ref_index', 1)
            wavelengths = self._wl_info.get('wavelengths', [])
            for i, wl in enumerate(wavelengths):
                ref = I18N[_current_lang]["ref_tag"] if i + 1 == ref_idx else ''
                self.cb_wl_g.setItemText(i, I18N[_current_lang]["wavelength_item"].format(id=i+1, wl=wl, ref=ref))
        self.setStatusTip(self._t("status_tip"))

    def _browse_seq(self):
        p, _ = QFileDialog.getOpenFileName(self, self._t("open_seq_title"), "", "SEQ (*.seq);;All (*)")
        if p:
            self.ed_seq.setText(p)
            self._load_wavelengths(p)
            self._populate_corr_seq_info()
            self._loaded_seq_path = p
            # Auto-set output dir to {program_root}/{lens_name}/
            lens_name = Path(p).stem
            out_dir = str(Path(__file__).parent / lens_name)
            Path(out_dir).mkdir(parents=True, exist_ok=True)
            self.ed_out_g.setText(out_dir)
            self.ed_out_ps.setText(out_dir)

    def _browse_out(self, prefix: str):
        """Unified output dir browser for both tabs."""
        p = QFileDialog.getExistingDirectory(self, self._t("browse_output_dir"))
        if p:
            getattr(self, f'ed_out_{prefix}').setText(p)

    # ========== Wavelength Management ==========
    def _load_wavelengths(self, seq_path):
        """Read WL/REF, ZOO count, and FOV from SEQ file, populate widgets."""
        from distortion_analyzer import DistortionAnalyzer

        # --- Parse zoom count (robust, always executed) ---
        try:
            num_zooms = DistortionAnalyzer.get_zoom_count_from_seq(seq_path)
            zoom_names = DistortionAnalyzer.get_zoom_names_from_seq(seq_path)
        except Exception:
            num_zooms = 1  # fallback on parse error
            zoom_names = {}
        # Always rebuild zoom widgets — independent of wavelength/FOV parsing
        self._rebuild_zoom_checkboxes(num_zooms, zoom_names)
        self._rebuild_ps_zoom_combos(num_zooms, zoom_names)

        # --- Parse wavelengths and FOV ---
        try:
            self._wl_info = DistortionAnalyzer.get_wavelengths_from_seq(seq_path)
            fov_info = DistortionAnalyzer.get_fov_from_seq(seq_path)
            wavelengths = self._wl_info['wavelengths']
            ref_idx = self._wl_info['ref_index']
            x_fov, y_fov = fov_info['x_max'], fov_info['y_max']
            self._log(f"SEQ: {len(wavelengths)} wavelengths, REF={ref_idx}, {num_zooms} zoom(s), "
                      f"FOV(max) X={x_fov:.2f}\u00b0 Y={y_fov:.2f}\u00b0")

            # Populate wavelength combo
            self.cb_wl_g.clear()
            for i, wl in enumerate(wavelengths):
                ref_text = I18N[_current_lang]["ref_tag"] if i + 1 == ref_idx else ''
                label = I18N[_current_lang]["wavelength_item"].format(id=i+1, wl=wl, ref=ref_text)
                self.cb_wl_g.addItem(label, userData=i+1)
            if 1 <= ref_idx <= self.cb_wl_g.count():
                self.cb_wl_g.setCurrentIndex(ref_idx - 1)

            # Set FOV defaults on both tabs
            self.sp_fovx_g.setValue(x_fov)
            self.sp_fovy_g.setValue(y_fov)
            self.sp_fovx_ps.setValue(x_fov)
            self.sp_fovy_ps.setValue(y_fov)
            self._loaded_seq_path = seq_path
        except Exception as e:
            self._log(f"Warning: could not read wavelengths/FOV: {e}")
            self.cb_wl_g.clear()
            label = I18N[_current_lang]["wavelength_item"].format(id=1, wl=625.0, ref=I18N[_current_lang]["ref_tag"])
            self.cb_wl_g.addItem(label, userData=1)
            self._wl_info = {'wavelengths': [625.0], 'ref_index': 1}
            self._loaded_seq_path = seq_path

    def _rebuild_zoom_checkboxes(self, num_zooms: int,
                                  zoom_names: dict = None):
        """Clear and rebuild Tab1 zoom checkboxes for the given zoom count."""
        if zoom_names is None:
            zoom_names = {}
        # Remove ALL old widgets (checkboxes + buttons)
        while self._zl_grid.count():
            item = self._zl_grid.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        self.chk_zoom.clear()
        for zid in range(1, num_zooms + 1):
            name = zoom_names.get(zid, '')
            label = I18N[_current_lang]["zoom_item_with_name"].format(id=zid, name=name) if name else I18N[_current_lang]["zoom_item"].format(id=zid)
            ch = QCheckBox(label)
            ch.setToolTip(name if name else I18N[_current_lang]["zoom_tooltip"].format(id=zid))
            self.chk_zoom[zid] = ch
            r, c = divmod(zid - 1, 4)
            self._zl_grid.addWidget(ch, r, c)

        # Default select first 3 (or all if fewer)
        for z in range(1, min(4, num_zooms + 1)):
            self.chk_zoom[z].setChecked(True)

        # Recreate Select All / Clear buttons fresh each time
        num_rows = (num_zooms - 1) // 4 + 1
        self._btn_sa_g = QPushButton(self._t("select_all"))
        self._btn_cl_g = QPushButton(self._t("clear"))
        self._btn_sa_g.clicked.connect(
            lambda: [c.setChecked(True) for c in self.chk_zoom.values()])
        self._btn_cl_g.clicked.connect(
            lambda: [c.setChecked(False) for c in self.chk_zoom.values()])
        self._zl_grid.addWidget(self._btn_sa_g, num_rows, 0)
        self._zl_grid.addWidget(self._btn_cl_g, num_rows, 1)

        # Also rebuild the Correction section zoom combo (if created)
        if self.cmb_corr_zoom is not None:
            self.cmb_corr_zoom.blockSignals(True)
            try:
                self.cmb_corr_zoom.clear()
                for zid in range(1, num_zooms + 1):
                    name = zoom_names.get(zid, '')
                    text = I18N[_current_lang]["zoom_item_with_name"].format(id=zid, name=name) if name else I18N[_current_lang]["zoom_item"].format(id=zid)
                    self.cmb_corr_zoom.addItem(text, zid)
                if num_zooms >= 1:
                    self.cmb_corr_zoom.setCurrentIndex(0)
            finally:
                self.cmb_corr_zoom.blockSignals(False)

    def _rebuild_ps_zoom_combos(self, num_zooms: int,
                                 zoom_names: dict = None):
        """Clear and rebuild Tab2 zoom dropdowns for the given zoom count."""
        if zoom_names is None:
            zoom_names = {}
        self.cb_ref.blockSignals(True)
        self.cb_tgt.blockSignals(True)
        try:
            self.cb_ref.clear()
            self.cb_tgt.clear()
            for z in range(1, num_zooms + 1):
                name = zoom_names.get(z, '')
                label = I18N[_current_lang]["zoom_item_with_name"].format(id=z, name=name) if name else I18N[_current_lang]["zoom_item"].format(id=z)
                self.cb_ref.addItem(label, userData=z)
                self.cb_tgt.addItem(label, userData=z)
            # sensible defaults
            if num_zooms >= 2:
                self.cb_ref.setCurrentIndex(1)   # Z2
            if num_zooms >= 5:
                self.cb_tgt.setCurrentIndex(4)   # Z5
            elif num_zooms >= 3:
                self.cb_tgt.setCurrentIndex(2)   # Z3
        finally:
            self.cb_ref.blockSignals(False)
            self.cb_tgt.blockSignals(False)

    def _on_wl_mode_changed(self, btn):
        """Toggle wavelength selector visibility based on single/multi choice."""
        is_single = (btn == self.rb_single)
        # Only hide/show the wavelength selector widgets, NOT the parent GroupBox
        self.cb_wl_g.setVisible(is_single)
        self._lbl_wl.setVisible(is_single)

    # ========== Log ==========
    def _log(self, msg: str) -> None:
        self.log.append(msg)
        sb = self.log.verticalScrollBar(); sb.setValue(sb.maximum())

    def _log_exc(self, prefix: str, e: Exception) -> None:
        """Log exception with prefix and print full traceback."""
        import traceback
        self._log(f"{prefix}: {e}")
        traceback.print_exc()

    # ========== RUN ANALYSIS ==========
    def _get_active_iqr_widgets(self):
        """Return the IQR widgets for currently active tab."""
        idx = self.tabs.currentIndex()
        if idx == 0:
            return self.chk_iqr_g, self.sp_iqr_g
        else:
            return self.chk_iqr_ps, self.sp_iqr_ps

    def _on_run(self) -> None:
        seq = self.ed_seq.text().strip()
        if not Path(seq).is_file():
            QMessageBox.warning(self, self._t("error_title"), self._t("seq_not_found").format(seq=seq))
            return

        idx = self.tabs.currentIndex()

        if idx == 0:
            # === Distortion Grid mode ===
            zooms = [z for z, ch in self.chk_zoom.items() if ch.isChecked()]
            if not zooms:
                QMessageBox.warning(self, self._t("hint_title"), self._t("select_at_least_one_zoom"))
                return
            wl_mode = 'multi' if self.rb_multi.isChecked() else 'single'
            wl_idx = self.cb_wl_g.currentData() or 1
            cfg = dict(
                mode='grid',
                zoom_ids=zooms,
                wl_mode=wl_mode,
                wl_index=wl_idx,
                x_fov=self.sp_fovx_g.value(),
                y_fov=self.sp_fovy_g.value(),
                grid_size=self.sp_gs_g.value(),
                xlim=self.sp_xlim_g.value(),
                ylim=self.sp_ylim_g.value(),
            )
        else:
            # === Pupil Swim mode ===
            ref_id = self.cb_ref.currentData() or 2
            tgt_id = self.cb_tgt.currentData() or 5
            if ref_id == tgt_id:
                QMessageBox.warning(self, self._t("hint_title"), self._t("ref_target_different"))
                return
            cfg = dict(
                mode='pupil_swim',
                ref_zoom_id=ref_id,
                tgt_zoom_id=tgt_id,
                x_fov=self.sp_fovx_ps.value(),
                y_fov=self.sp_fovy_ps.value(),
                grid_size=self.sp_gs_ps.value(),
                xlim=self.sp_xlim_ps.value(),
                ylim=self.sp_ylim_ps.value(),
            )

        chk_iqr, sp_iqr = self._get_active_iqr_widgets()
        cfg['iqr_enabled'] = chk_iqr.isChecked()
        cfg['iqr_factor'] = sp_iqr.value()

        if self._loaded_seq_path != seq:
            self._load_wavelengths(seq)
            self._populate_corr_seq_info()
            self._grid_cache.clear()  # 更换镜头 → 清空缓存

        # ── 检查缓存：全部命中则跳过 CODE V ──
        seq = self.ed_seq.text().strip()
        gs = cfg.get('grid_size', 21)
        x_fov = cfg.get('x_fov', 26.565)
        y_fov = cfg.get('y_fov', 26.565)
        full_result, cached_entries = self._check_cache(cfg, gs, x_fov, y_fov)
        if full_result is not None:
            self._log("All results cached, reusing...")
            self.result = full_result
            QTimer.singleShot(100, self._auto_popup)
            self._on_done(full_result)
            return
        if cached_entries:
            self._log(f"Partial cache: {len(cached_entries)} entries reused, will trace the rest")
            cfg['cached_results'] = cached_entries

        # Disable CODE-V-triggering buttons during analysis
        self._active_run_tab = self.tabs.currentIndex()
        self._btn_run_g.setEnabled(False)
        self._btn_run_ps.setEnabled(False)
        self._btn_corr_fit.setEnabled(False)
        self.bar.setRange(0, 0)
        self._log(f"Start: {cfg['mode']}, SEQ={Path(seq).name}")
        self.worker = AnalysisWorker(seq, **cfg)
        self.worker.progress.connect(self._log)
        self.worker.finished_signal.connect(self._on_done)
        self.worker.error_signal.connect(self._on_err)
        self.worker.start()

    # ---------- In-tab button slots ----------
    # ── 结果缓存 ──
    def _check_cache(self, cfg, gs, x_fov, y_fov):
        """返回 (full_result, 缓存命中项 dict)。全命中返回 (result, {})；部分命中返回 (None, {key: entry})；全未命中返回 (None, {})"""
        wl_info = self._wl_info or {'wavelengths': [625.0], 'ref_index': 1}
        wavelengths = wl_info['wavelengths']
        mode = cfg.get('mode', 'grid')
        cached = {}
        missing = False
        if mode == 'grid':
            zoom_ids = cfg.get('zoom_ids', [1])
            wl_mode = cfg.get('wl_mode', 'single')
            wl_idx = cfg.get('wl_index', wl_info['ref_index'])
            if wl_mode == 'multi':
                for zid in zoom_ids:
                    for wi in range(len(wavelengths)):
                        key = (zid, wi + 1, gs, x_fov, y_fov)
                        if key in self._grid_cache:
                            cached[key] = self._grid_cache[key]
                        else:
                            missing = True
            else:
                for zid in zoom_ids:
                    key = (zid, wl_idx, gs, x_fov, y_fov)
                    if key in self._grid_cache:
                        cached[key] = self._grid_cache[key]
                    else:
                        missing = True
        elif mode == 'pupil_swim':
            ref_idx = wl_info['ref_index']
            for zid in [cfg['ref_zoom_id'], cfg['tgt_zoom_id']]:
                key = (zid, ref_idx, gs, x_fov, y_fov)
                if key in self._grid_cache:
                    cached[key] = self._grid_cache[key]
                else:
                    missing = True
        if not missing and cached:
            if mode == 'grid':
                results = {}
                for (zid, wi, *_rest), entry in cached.items():
                    if wl_mode == 'multi':
                        results[(zid, wi)] = entry
                    else:
                        results[zid] = entry
                return {
                    'mode': 'grid', 'wl_mode': wl_mode,
                    'wavelengths': wavelengths, 'results': results,
                    'x_fov': x_fov, 'y_fov': y_fov, 'grid_size': gs,
                    'xlim': cfg.get('xlim', 0), 'ylim': cfg.get('ylim', 0),
                }, {}
            else:
                results = {}
                for (zid, _wi, *_rest), entry in cached.items():
                    results[zid] = entry
                return {
                    'mode': 'pupil_swim',
                    'wavelengths': wavelengths,
                    'ref_id': cfg['ref_zoom_id'], 'tgt_id': cfg['tgt_zoom_id'],
                    'results': results,
                    'x_fov': x_fov, 'y_fov': y_fov, 'grid_size': gs,
                    'xlim': cfg.get('xlim', 0), 'ylim': cfg.get('ylim', 0),
                }, {}
        # 部分命中或无命中 → 返回命中项供 worker 跳过
        return (None, cached) if cached else (None, {})

    def _on_run_tab(self, tab_index: int) -> None:
        """Called by Start buttons inside Tab 1/2; switches to target tab then runs."""
        self.tabs.setCurrentIndex(tab_index)
        self._on_run()

    def _on_export_tab(self, tab_index: int) -> None:
        """Called by Export PNG buttons inside Tab 1/2; saves the in-tab canvas figure(s)."""
        if self.result is None:
            QMessageBox.information(self, self._t("hint_title"), self._t("run_analysis_first"))
            return
        if tab_index == 0:
            out_dir = self.ed_out_g.text().strip()
            Path(out_dir).mkdir(parents=True, exist_ok=True)
            wl_mode = self.result.get('wl_mode', 'single')
            wl_val = list(self.result['results'].values())[0].get('wavelength', 625) if self.result.get('results') else 625
            fname = f"distortion_grid_{wl_val:.0f}nm.png" if wl_mode == 'single' else "distortion_grid_multi.png"
            path = str(Path(out_dir) / fname)
            try:
                self.fig_g.savefig(path, dpi=200, bbox_inches='tight')
                self._log(f"Exported: {path}")
                QMessageBox.information(self, self._t("saved_title"), self._t("saved_message").format(path=path))
            except Exception as e:
                self._log(f"Export error: {e}")
                QMessageBox.warning(self, self._t("error_title"), str(e))
        else:
            out_dir = self.ed_out_ps.text().strip()
            Path(out_dir).mkdir(parents=True, exist_ok=True)
            ref_id = self.result.get('ref_id', 2)
            tgt_id = self.result.get('tgt_id', 5)
            fmt = self._output_format()
            saved = []
            if fmt in ('both', 'vectors') and hasattr(self, 'fig_psv'):
                p = str(Path(out_dir) / f'ps_vectors_Z{ref_id}_vs_Z{tgt_id}.png')
                self.fig_psv.savefig(p, dpi=200, bbox_inches='tight')
                saved.append(p)
            if fmt in ('both', 'heatmap') and hasattr(self, 'fig_psh'):
                p = str(Path(out_dir) / f'ps_heatmap_Z{ref_id}_Z{tgt_id}.png')
                self.fig_psh.savefig(p, dpi=200, bbox_inches='tight')
                saved.append(p)
            if saved:
                self._log(f"Exported: " + ", ".join(saved))
                QMessageBox.information(self, self._t("saved_title"), self._t("saved_message").format(path="\n".join(saved)))
            else:
                QMessageBox.information(self, self._t("hint_title"), self._t("run_analysis_first"))

    def _on_done(self, res: Optional[dict]) -> None:
        self._btn_run_g.setEnabled(True)
        self._btn_run_ps.setEnabled(True)
        self._btn_corr_fit.setEnabled(True)
        self._active_run_tab = None
        self.bar.setRange(0, 1)
        if not res:
            return
        self.result = res
        # ── 存入缓存 ──
        gs = res.get('grid_size', 21)
        x_fov = res.get('x_fov', 0)
        y_fov = res.get('y_fov', 0)
        for key, entry in res.get('results', {}).items():
            if isinstance(key, tuple):
                zid, wi = key
                wl = entry.get('wl_index', wi + 1)
            else:
                zid, wl = key, entry.get('wl_index', 1)
            cache_key = (zid, wl, gs, x_fov, y_fov)
            self._grid_cache[cache_key] = entry
        mode = res.get('mode', '?')
        n_results = len(res.get('results', {}))
        self._log(f"Done: mode={mode}, {n_results} dataset(s)")

        # Auto-popup after 300ms
        QTimer.singleShot(300, self._auto_popup)

    def _on_err(self, e: str) -> None:
        self._btn_run_g.setEnabled(True)
        self._btn_run_ps.setEnabled(True)
        self._btn_corr_fit.setEnabled(True)
        self._active_run_tab = None
        self.bar.setRange(0, 1)
        self._log(f"ERROR: {e}")
        QMessageBox.critical(self, self._t("error_title"), e)

    # ====================================================================
    #  DRAWING — draw on in-tab canvas (no popup)
    # ====================================================================
    def _auto_popup(self):
        """Draw results on the in-tab canvas after analysis completes."""
        if not self.result: return
        try:
            mode = self.result.get('mode', '?')
            if mode == 'grid':
                wl_mode = self.result.get('wl_mode', 'single')
                results = self.result['results']
                x_fov = self.result.get('x_fov', 5.0)
                y_fov = self.result.get('y_fov', 5.0)
                self.fig_g.clear()
                ax = self.fig_g.add_subplot(111)
                if wl_mode == 'multi':
                    wavelengths = self.result.get('wavelengths', [])
                    self._render_multi_color_grid(ax, results, x_fov, y_fov, wavelengths)
                else:
                    self._render_single_color_grid(ax, results, x_fov, y_fov)
                self.fig_g.tight_layout()
                self.canvas_g.draw()
                self._log("Grid result drawn on canvas.")
            elif mode == 'pupil_swim':
                fmt = self._output_format()
                results = self.result['results']
                ref_id = self.result['ref_id']
                tgt_id = self.result['tgt_id']
                x_fov = self.result.get('x_fov', 26.565)
                y_fov = self.result.get('y_fov', 26.565)
                if fmt in ('both', 'vectors'):
                    self.fig_psv.clear()
                    ax = self.fig_psv.add_subplot(111)
                    self._render_ps_vectors(ax, results, ref_id, tgt_id, x_fov, y_fov)
                    self.fig_psv.tight_layout()
                    self.canvas_psv.draw()
                if fmt in ('both', 'heatmap'):
                    self.fig_psh.clear()
                    ax = self.fig_psh.add_subplot(111)
                    self._render_ps_heatmap(ax, results, ref_id, tgt_id, x_fov, y_fov)
                    self.fig_psh.tight_layout()
                    self.canvas_psh.draw()
                self._log("Pupil Swim result drawn on canvas.")
        except Exception as e:
            self._log_exc("Draw err", e)

    def _output_format(self):
        if self.rb_fmt_vec.isChecked(): return 'vectors'
        if self.rb_fmt_hm.isChecked(): return 'heatmap'
        return 'both'

    # ---- IQR helpers ----
    def _iqr_mask(self, flat, factor=None):
        f = factor or self.sp_iqr_g.value()
        q1, q3 = np.percentile(flat, [25, 75])
        lo, hi = q1 - f * (q3 - q1), q3 + f * (q3 - q1)
        mask = (flat >= lo) & (flat <= hi)
        return mask, int((~mask).sum()), lo, hi

    def _iqr_mask_ps(self):
        """Get IQR settings from Pupil Swim tab."""
        factor = self.sp_iqr_ps.value()
        enabled = self.chk_iqr_ps.isChecked()
        return enabled, factor

    def _get_iqr_settings(self, iqr_tab: str):
        """Unified IQR settings lookup for both tabs."""
        if iqr_tab == 'ps':
            return self._iqr_mask_ps()
        return self.chk_iqr_g.isChecked(), self.sp_iqr_g.value()

    # ---- helper: apply coordinate range ----
    def _apply_coord_range(self, ax, xlim, ylim):
        """Apply custom axis limits. 0 = auto from data."""
        if xlim > 0:
            ax.set_xlim(-xlim, xlim)
        if ylim > 0:
            ax.set_ylim(-ylim, ylim)

    # ---- helper: mesh grid lines ----
    def _plot_mesh(self, ax, grid, color, label, num_lines, alpha=0.7, lw=1.0):
        for i in range(num_lines):
            ax.plot(grid[i, :, 0], grid[i, :, 1], color=color,
                    linewidth=lw, alpha=alpha, label=label if i == 0 else "")
        for j in range(num_lines):
            ax.plot(grid[:, j, 0], grid[:, j, 1], color=color,
                    linewidth=lw, alpha=alpha)

    # ====================================================================
    # POPUP DRAW METHODS — v4.0
    # ====================================================================

    # ---- Single-Color Distortion Grid Popup ----
    def _render_single_color_grid(self, ax, results, x_fov, y_fov):
        """Render single-wavelength distortion grid onto ax (shared by popup & export)."""
        wl_val = list(results.values())[0].get('wavelength', '?') if results else '?'
        drawn = False
        for zid in sorted(results.keys()):
            if not isinstance(zid, tuple):  # single-mode keys are plain ints
                r = results[zid]
                if r['actual'].max() != 0:
                    gs = r['actual'].shape[0]
                    c = WL_COLORS[(zid - 1) % len(WL_COLORS)]
                    self._plot_mesh(ax, r['actual'], c, f'Z{zid}', gs)
                    drawn = True

        if drawn:
            first_r = list(results.values())[0]
            if 'paraxial' in first_r and first_r['paraxial'].max() != 0:
                gs = first_r['actual'].shape[0]
                self._plot_mesh(ax, first_r['paraxial'], 'lightgray', 'ideal paraxial', gs, alpha=0.35, lw=0.6)

        ax.set_aspect('equal'); ax.grid(True, alpha=0.3)
        ax.set_xlabel('X (mm)', fontsize=12); ax.set_ylabel('Y (mm)', fontsize=12)
        ax.set_title(f'Distortion Grid ({wl_val:.0f}nm)\nFOV = {x_fov}\u00b0 / {y_fov}\u00b0', fontsize=14)
        ax.legend(loc='upper right', fontsize=10)
        self._apply_coord_range(ax, self.result.get('xlim', 0), self.result.get('ylim', 0))

    def _draw_single_color_popup(self):
        """Draw distortion grid for single-wavelength (one or more zooms)."""
        results = self.result['results']
        out_dir = self.ed_out_g.text().strip()
        x_fov = self.result.get('x_fov', 26.565)
        y_fov = self.result.get('y_fov', 26.565)
        wl_val = list(results.values())[0].get('wavelength', '?') if results else '?'
        self._show_figure(
            self._render_single_color_grid,
            f"Distortion Grid ({wl_val:.0f}nm)", 12, 10,
            f'distortion_grid_{wl_val:.0f}nm.png', out_dir,
            results, x_fov, y_fov)

    # ---- Multi-Color Distortion Grid Popup ----
    def _render_multi_color_grid(self, ax, results, x_fov, y_fov, wavelengths):
        """Render multi-wavelength distortion grid overlay onto ax."""
        zoom_groups = {}
        for (zid, wl_idx), r in results.items():
            if zid not in zoom_groups:
                zoom_groups[zid] = []
            zoom_groups[zid].append((wl_idx, r))

        drawn_any = False
        paraxial_shown = False
        for zid in sorted(zoom_groups.keys()):
            items = zoom_groups[zid]
            for wl_idx, r in items:
                if r['actual'].max() == 0:
                    continue
                gs = r['actual'].shape[0]
                wl_val = r.get('wavelength', wl_idx * 100)
                c = WL_COLORS[wl_idx % len(WL_COLORS)]
                label = f'Z{zid} @{wl_val:.0f}nm'
                self._plot_mesh(ax, r['actual'], c, label, gs)
                drawn_any = True

                if not paraxial_shown and 'paraxial' in r:
                    self._plot_mesh(ax, r['paraxial'], 'lightgray', 'ideal paraxial', gs, alpha=0.3, lw=0.5)
                    paraxial_shown = True

        if not drawn_any:
            ax.text(.5, .5, 'No data', ha='center', va='center',
                    transform=ax.transAxes, fontsize=14, color='gray')
        else:
            ax.set_aspect('equal'); ax.grid(True, alpha=0.3)
            ax.set_xlabel('X (mm)', fontsize=12); ax.set_ylabel('Y (mm)', fontsize=12)
            ax.set_title(f'Multi-Wavelength Distortion Grid\nFOV = {x_fov}\u00b0 / {y_fov}\u00b0 | '
                         f'Wavelengths: {" ".join(f"{w:.0f}" for w in wavelengths)} nm',
                         fontsize=13)
            ax.legend(loc='upper right', fontsize=9)
        self._apply_coord_range(ax, self.result.get('xlim', 0), self.result.get('ylim', 0))

    def _draw_multi_color_popup(self):
        """Draw all wavelengths overlaid on same coordinate system."""
        results = self.result['results']
        out_dir = self.ed_out_g.text().strip()
        x_fov = self.result.get('x_fov', 26.565)
        y_fov = self.result.get('y_fov', 26.565)
        wavelengths = self.result.get('wavelengths', [])
        self._show_figure(
            self._render_multi_color_grid,
            "Multi-Wavelength Distortion Grid Overlay", 14, 11,
            'distortion_grid_multi_wavelength.png', out_dir,
            results, x_fov, y_fov, wavelengths)

    # ---- Pupil Swim: Vectors popup ----
    def _render_ps_vectors(self, ax, results, ref_id, tgt_id, x_fov, y_fov):
        """Render pupil swim vector plot onto ax (shared by popup & export)."""
        if ref_id not in results or tgt_id not in results:
            ax.text(.5, .5, f"No data Z{ref_id}/Z{tgt_id}", ha='center',
                    transform=ax.transAxes, color='red', fontsize=13)
            return

        rR, rT = results[ref_id], results[tgt_id]
        lab_r = f"Z{ref_id} (Reference)"
        lab_t = f"Z{tgt_id} (Target)"
        title_str = f"Pupil Swim: {lab_r} vs {lab_t}\nFOV = {x_fov}\u00b0 / {y_fov}\u00b0"
        self._draw_pupil_swim_pair(ax, rR, rT, lab_r, lab_t, title_str, iqr_tab='ps')
        self._apply_coord_range(ax, self.result.get('xlim', 0), self.result.get('ylim', 0))

    def _draw_ps_vectors_popup(self):
        """Pupil Swim vector comparison: Reference grid + Target grid + quiver arrows."""
        results = self.result['results']
        ref_id = self.result['ref_id']
        tgt_id = self.result['tgt_id']
        out_dir = self.ed_out_ps.text().strip()
        x_fov = self.result.get('x_fov', 26.565)
        y_fov = self.result.get('y_fov', 26.565)
        self._show_figure(
            self._render_ps_vectors,
            f"Pupil Swim Vectors: Z{ref_id} -> Z{tgt_id}", 12, 10,
            f'ps_vectors_Z{ref_id}_vs_Z{tgt_id}.png', out_dir,
            results, ref_id, tgt_id, x_fov, y_fov)

    # ---- Pupil Swim: Heatmap popup ----
    def _render_ps_heatmap(self, ax, results, ref_id, tgt_id, x_fov, y_fov):
        """Render pupil swim displacement heatmap onto ax (shared by popup & export)."""
        if ref_id not in results or tgt_id not in results:
            ax.text(.5, .5, "No data", ha='center',
                    transform=ax.transAxes, color='red', fontsize=13)
            return

        rR, rT = results[ref_id], results[tgt_id]
        title_str = f"Pupil Swim Heatmap: Z{ref_id} -> Z{tgt_id}"
        self._draw_heatmap_pair(ax, rR, rT, title_str, iqr_tab='ps')
        ax.set_aspect('equal')
        ax.set_xlabel('X (mm)', fontsize=11); ax.set_ylabel('Y (mm)', fontsize=11)
        self._apply_coord_range(ax, self.result.get('xlim', 0), self.result.get('ylim', 0))

    def _draw_ps_heatmap_popup(self):
        """Pupil Swim displacement heatmap."""
        results = self.result['results']
        ref_id = self.result['ref_id']
        tgt_id = self.result['tgt_id']
        out_dir = self.ed_out_ps.text().strip()
        x_fov = self.result.get('x_fov', 26.565)
        y_fov = self.result.get('y_fov', 26.565)
        self._show_figure(
            self._render_ps_heatmap,
            f"Pupil Swim Heatmap: Z{ref_id} -> Z{tgt_id}", 11, 9,
            f'ps_heatmap_Z{ref_id}_Z{tgt_id}.png', out_dir,
            results, ref_id, tgt_id, x_fov, y_fov)

    # ====================================================================
    # SHARED DRAWING HELPERS
    # ====================================================================

    # ---- Pupil Swim Pair (vector grid on given axes) ----
    def _draw_pupil_swim_pair(self, ax, rR, rT, lab_r, lab_t, title_str,
                               iqr_tab='grid'):
        """Draw Reference (dark blue) + Target (orange) grids + quiver arrows."""
        gs = rR['actual'].shape[0]
        self._plot_mesh(ax, rR['actual'], 'darkblue', lab_r, gs)
        self._plot_mesh(ax, rT['actual'], 'orange', lab_t, gs)
        U = rT['actual'][:, :, 0] - rR['actual'][:, :, 0]
        V = rT['actual'][:, :, 1] - rR['actual'][:, :, 1]
        X = rR['actual'][:, :, 0]; Y = rR['actual'][:, :, 1]
        mag = np.sqrt(U**2 + V**2); n_rm = 0

        # IQR outlier removal
        iqr_en, iqr_f = self._get_iqr_settings(iqr_tab)
        if iqr_en:
            mk, n_rm, _, _ = self._iqr_mask(mag.flatten(), factor=iqr_f)
            m2d = mk.reshape(gs, gs); U = U.copy(); V = V.copy(); mf = mag.astype(float)
            U[~m2d] = 0; V[~m2d] = 0; mf[~m2d] = np.nan
            if n_rm > 0:
                ax.scatter(X[~m2d], Y[~m2d], c='red', s=60, marker='x', linewidths=2,
                          label=f'Outlier({n_rm})', zorder=5)
        else:
            mf = mag.astype(float)

        st = max(1, gs // 11)
        q = ax.quiver(X[::st, ::st], Y[::st, ::st], U[::st, ::st], V[::st, ::st], mf[::st, ::st],
                      scale=0.1, scale_units='xy', angles='xy',
                      color='red', width=0.002, headwidth=4, headlength=5)
        try:
            ax.quiverkey(q, X=0.85, Y=1.02, U=0.05, label='0.05mm', labelpos='E')
        except Exception:
            pass
        valid = mf[~np.isnan(mf)] if np.any(~np.isnan(mf)) else mag
        ax.text(0.02, 0.02,
                f'Max={valid.max()*1e3:.1f}um  RMS={np.sqrt(np.mean(valid**2))*1e3:.1f}um',
                transform=ax.transAxes, fontsize=7, va='bottom',
                bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.8))
        ax.set_aspect('equal'); ax.grid(True, alpha=0.3)
        ax.set_xlabel('X(mm)', fontsize=11); ax.set_ylabel('Y(mm)', fontsize=11)
        ax.set_title(title_str, fontweight='bold', fontsize=10)
        ax.legend(loc='upper right', fontsize=7)

    # ---- Heatmap Pair (on given axes) ----
    def _draw_heatmap_pair(self, ax, rR, rT, title_str, iqr_tab='grid'):
        """Draw triangulated displacement heatmap."""
        from matplotlib.tri import Triangulation, LinearTriInterpolator
        disp = rT['actual'] - rR['actual']
        dmag = np.sqrt(disp[:, :, 0]**2 + disp[:, :, 1]**2)
        X = rR['actual'][:, :, 0]; Y = rR['actual'][:, :, 1]
        xf, yf, mf = X.flatten(), Y.flatten(), dmag.flatten()
        mask = np.ones(len(mf), dtype=bool); n_rm = 0

        iqr_en, iqr_f = self._get_iqr_settings(iqr_tab)
        if iqr_en:
            mask, n_rm, lo, hi = self._iqr_mask(mf, factor=iqr_f)

        xc, yc, mc = xf[mask], yf[mask], mf[mask]
        tri = Triangulation(xc, yc)
        xi = np.linspace(X.min(), X.max(), 200)
        yi = np.linspace(Y.min(), Y.max(), 200)
        Xi, Yi = np.meshgrid(xi, yi)
        Zi = LinearTriInterpolator(tri, mc)(Xi, Yi)
        im = ax.pcolormesh(Xi, Yi, Zi, shading='gouraud', cmap='hot')
        ax.figure.colorbar(im, ax=ax, label='Disp.(mm)', shrink=0.8)
        if n_rm > 0:
            ax.scatter(xf[~mask], yf[~mask], c='cyan', s=25, marker='x', linewidths=1,
                       label=f'Out({n_rm})', zorder=5)
            ax.legend(fontsize=6)
        ax.set_title(f'{title_str} (outliers removed: {n_rm})', fontweight='bold', fontsize=10)

    # ---------- Shared dialog helper ----------
    def _show_figure(self, render_fn, title, width, height, save_name, out_dir, *render_args):
        """Create FigureDialog, call render_fn(ax, *args), tight_layout, show."""
        dlg = FigureDialog(self, title=title, width=width, height=height, dpi=100)
        dlg.set_save_path(str(Path(out_dir) / save_name))
        render_fn(dlg.ax, *render_args)
        dlg.fig.tight_layout()
        dlg.show()

    # ---------- Export ----------
    def _save_figure(self, render_fn, path, figsize, *render_args):
        """Create non-interactive figure, call render_fn(ax, *args), save to path."""
        from matplotlib.figure import Figure
        from matplotlib.backends.backend_agg import FigureCanvasAgg

        fig = Figure(figsize=figsize, dpi=200)
        FigureCanvasAgg(fig)
        ax = fig.add_subplot(111)
        render_fn(ax, *render_args)
        fig.tight_layout()
        fig.savefig(path, bbox_inches='tight')
        return path

    def _on_export(self):
        """Batch-save all analysis charts to output directory."""
        if not self.result:
            QMessageBox.information(self, self._t("hint_title"), self._t("no_data_yet")); return

        out_dir = self.ed_out_g.text().strip() if self.tabs.currentIndex() == 0 \
                  else self.ed_out_ps.text().strip()
        Path(out_dir).mkdir(parents=True, exist_ok=True)
        mode = self.result.get('mode', '?')
        results = self.result['results']
        x_fov = self.result.get('x_fov', 26.565)
        y_fov = self.result.get('y_fov', 26.565)
        saved = []

        try:
            if mode == 'grid':
                wl_mode = self.result.get('wl_mode', 'single')
                if wl_mode == 'multi':
                    wavelengths = self.result.get('wavelengths', [])
                    p = str(Path(out_dir) / 'distortion_grid_multi.png')
                    saved.append(self._save_figure(
                        self._render_multi_color_grid, p, (14, 11),
                        results, x_fov, y_fov, wavelengths))
                else:
                    wl_val = list(results.values())[0].get('wavelength', '?') if results else '?'
                    p = str(Path(out_dir) / f'distortion_grid_{wl_val:.0f}nm.png')
                    saved.append(self._save_figure(
                        self._render_single_color_grid, p, (12, 10),
                        results, x_fov, y_fov))

            elif mode == 'pupil_swim':
                ref_id = self.result['ref_id']
                tgt_id = self.result['tgt_id']
                fmt = self._output_format()

                if fmt in ('both', 'vectors'):
                    p = str(Path(out_dir) / f'ps_vectors_Z{ref_id}_vs_Z{tgt_id}.png')
                    saved.append(self._save_figure(
                        self._render_ps_vectors, p, (12, 10),
                        results, ref_id, tgt_id, x_fov, y_fov))

                if fmt in ('both', 'heatmap'):
                    p = str(Path(out_dir) / f'ps_heatmap_Z{ref_id}_Z{tgt_id}.png')
                    saved.append(self._save_figure(
                        self._render_ps_heatmap, p, (11, 9),
                        results, ref_id, tgt_id, x_fov, y_fov))

            if saved:
                self._log(f"Exported {len(saved)} file(s):\n" + "\n".join(saved))
            else:
                self._log("No chart to export.")
        except Exception as e:
            self._log_exc("Export failed", e)


# ============================================================
#  Entry Point
# ============================================================
def main():
    app = QApplication(sys.argv); app.setStyle('Fusion')
    # Window icon: frozen (exe) → exe dir; dev → script dir
    base = Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(__file__).parent
    icon = base / 'icon.ico'
    if icon.exists():
        app.setWindowIcon(QIcon(str(icon)))
    w = DistortionGUI(); w.show()
    sys.exit(app.exec_())

if __name__ == '__main__':
    main()
