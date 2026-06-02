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
    import matplotlib.pyplot as _plt
    _plt.rcParams['font.sans-serif'] = ['Microsoft YaHei', 'SimHei']
    _plt.rcParams['axes.unicode_minus'] = False
    _mpl_ready = True

# Wavelength-to-color mapping for multi-color overlay
WL_COLORS = ['red', 'green', 'blue', 'orange', 'purple', 'cyan',
             'magenta', 'olive', 'brown', 'pink', 'gray', 'black']


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
        try:
            from distortion_analyzer import DistortionAnalyzer

            workdir = str(Path(self.seq_path).parent)
            mode = self.kwargs.get('mode', 'grid')

            self.progress.emit("Connecting CODE V ...")
            analyzer = DistortionAnalyzer(workdir=workdir)

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

            analyzer.disconnect()
            self.finished_signal.emit(result)

        except Exception as e:
            self.error_signal.emit(str(e))

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
        wl_choice = self.kwargs.get('wl_index', ref_idx)  # user-selected for single
        x_fov = self.kwargs.get('x_fov', 26.565)
        y_fov = self.kwargs.get('y_fov', 26.565)
        gs = self.kwargs.get('grid_size', 21)

        results = {}

        if wl_mode == 'multi':
            # Multi-color: run all wavelengths for each selected zoom
            # KEY: wl_index (1-based) controls REF switching for ray tracing.
            #      wavelength string only controls plot line color (ARG6).
            color_names = ['RED', 'GRE', 'BLU', 'MAG', 'YEL', 'CYA', 'WHI']
            total = len(zoom_ids) * len(wavelengths)
            count = 0
            for zid in zoom_ids:
                for wi, wl_val in enumerate(wavelengths):
                    count += 1
                    wl_index = wi + 1  # 1-based wavelength index for REF
                    wl_label = f"{wl_val:.0f}nm"
                    self.progress.emit(f"[{count}/{total}] Z{zid} @ {wl_label} ...")
                    try:
                        grid = analyzer.get_distortion_grid(
                            zoom_pos=zid, num_lines=gs,
                            x_fov=x_fov, y_fov=y_fov,
                            wavelength=color_names[wi % len(color_names)],
                            wl_index=wl_index)
                        results[(zid, wi)] = self._pack_grid_result(
                            grid, gs, x_fov=x_fov, y_fov=y_fov,
                            wavelength=wl_val, wl_index=wi + 1)
                    except Exception as e:
                        self.progress.emit(f"  Z{zid}@{wl_label} failed: {e}")
                        results[(zid, wi)] = self._pack_grid_result(
                            None, gs, wavelength=wl_val, wl_index=wi + 1)
        else:
            # Single-color: use chosen wavelength
            wl_val = wavelengths[wl_choice - 1] if wl_choice <= len(wavelengths) else wavelengths[0]
            wl_label = f"{wl_val:.0f}nm"
            for zi, zid in enumerate(zoom_ids):
                self.progress.emit(f"[{zi+1}/{len(zoom_ids)}] Z{zid} @ {wl_label} ...")
                try:
                    grid = analyzer.get_distortion_grid(
                        zoom_pos=zid, num_lines=gs,
                        x_fov=x_fov, y_fov=y_fov,
                        wl_index=wl_choice, wavelength=wl_label)
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
        wl_val = wavelengths[ref_idx - 1]
        wl_label = f"{wl_val:.0f}nm"

        results = {}
        for zid, name in [(ref_id, 'Reference'), (tgt_id, 'Target')]:
            self.progress.emit(f"Tracing Z{zid} ({name}) @ {wl_label} ...")
            try:
                grid = analyzer.get_distortion_grid(
                    zoom_pos=zid, num_lines=gs,
                    x_fov=x_fov, y_fov=y_fov,
                    wl_index=ref_idx, wavelength=wl_label)
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
    """CODE V 后台追迹（独立 R/G/B 通道波长）+ 多项式拟合"""
    progress = pyqtSignal(str)
    finished = pyqtSignal(str, str)  # (work_dir, error_msg)

    def __init__(self, seq_path, halfx, halfy, panel_w, panel_h,
                 zoom, num_lines, wl_indices, macro_path):
        super().__init__()
        self.seq_path = seq_path; self.halfx = halfx; self.halfy = halfy
        self.panel_w = panel_w; self.panel_h = panel_h
        self.zoom = zoom; self.num_lines = num_lines
        self.wl_indices = wl_indices; self.macro_path = macro_path

    def run(self) -> None:
        try:
            import win32com.client
        except ImportError:
            self.finished.emit("", "未找到 win32com，请安装 pywin32：pip install pywin32")
            return

        macro = Path(self.macro_path)
        if not macro.is_file():
            self.finished.emit("", f"找不到宏文件：{self.macro_path}")
            return

        work_dir = str(Path(self.seq_path).parent)
        try:
            self.progress.emit("Connecting CODE V ...")
            cv = win32com.client.Dispatch("CODEV.Command")
            try: cv.StartCodeV()
            except Exception: pass
            cv.Command(f'CD "{work_dir}"')
            cv.Command(f'IN "{self.seq_path}"')

            out_names = ["r.txt", "g.txt", "b.txt"]
            labels = ["R", "G", "B"]
            traced = {}

            for idx, wl in enumerate(self.wl_indices):
                label = labels[idx]
                outfile = str(Path(work_dir) / out_names[idx])
                if wl in traced:
                    self.progress.emit(f"{label} (WL={wl}, reuse) -> {out_names[idx]}")
                    Path(outfile).write_text(traced[wl], encoding='utf-8')
                else:
                    self.progress.emit(f"Trace {label} (WL={wl}) ...")
                    cv.Command(f"REF {wl}")
                    cmd = (f'IN "{self.macro_path}" {self.halfx} {self.halfy} '
                           f'{self.panel_w} {self.panel_h} '
                           f'"" GRE {self.num_lines} {self.zoom} "Yes"')
                    cv.Command(cmd)
                    try: output = cv.GetCommandOutput()
                    except Exception: output = ""
                    traced[wl] = output
                    Path(outfile).write_text(output, encoding='utf-8')
                    self.progress.emit(f"  -> {out_names[idx]} ({len(output)} chars)")
            self.progress.emit("CODE V done.")
            self.finished.emit(work_dir, "")
        except Exception as e:
            self.finished.emit("", f"CODE V error: {e}\n{traceback.format_exc()}")


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
        btn_save = QPushButton("Save PNG"); btn_save.clicked.connect(self._save_png)
        btn_close = QPushButton("Close"); btn_close.clicked.connect(self.accept)
        btn_lo.addWidget(btn_save); btn_lo.addWidget(btn_close); btn_lo.addStretch()
        lo.addLayout(btn_lo)
        self._save_path = None

    def set_save_path(self, path):
        self._save_path = path

    def _save_png(self):
        p, _ = QFileDialog.getSaveFileName(self, "Save PNG",
                                            self._save_path or "plot.png",
                                            "PNG (*.png);;PDF (*.pdf);;All (*)")
        if p:
            self.fig.savefig(p, dpi=200, bbox_inches='tight')
            QMessageBox.information(self, "Saved", f"Saved to:\n{p}")

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
        self.setWindowTitle("Distortion Analyzer V1.1")
        self.setGeometry(50, 50, 980, 700)
        self.result = None
        self._wl_info = None   # cached wavelengths from SEQ
        self._corr_work_dir = ""
        self._corr_csv_str = ""
        self._corr_fit_result = None
        self._build_ui()
        self._load_displays_db()

    # ==================== UI LAYOUT ====================
    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_lo = QVBoxLayout(central)

        # ---- Shared Lens File (above tabs) ----
        grp_lens = QGroupBox("Lens File")
        lens_lo = QHBoxLayout(grp_lens)
        self.ed_seq = QLineEdit(); self.ed_seq.setPlaceholderText(".seq path...")
        btn_lens = QPushButton("Browse..."); btn_lens.clicked.connect(self._browse_seq)
        lens_lo.addWidget(self.ed_seq, stretch=1)
        lens_lo.addWidget(btn_lens)
        main_lo.addWidget(grp_lens)

        # ---- Tab Widget ----
        self.tabs = QTabWidget()
        main_lo.addWidget(self.tabs)

        # Tab 1: Distortion Grid
        tab_grid = self._build_tab_grid()
        self.tabs.addTab(tab_grid, "  \U0001F4CF Distortion Grid  ")

        # Tab 2: Pupil Swim
        tab_ps = self._build_tab_pupil_swim()
        self.tabs.addTab(tab_ps, "  \U0001F441 Pupil Swim  ")

        # Tab 3: Distortion Correction
        tab_corr = self._build_tab_correction()
        self.tabs.addTab(tab_corr, "  \U0001F4E6 Distortion Correction  ")

        # ---- Bottom Shared Area ----
        bottom_w = QWidget()
        bot_lo = QHBoxLayout(bottom_w)
        self.btn_run = QPushButton("  \u25b6 Start Analysis  ")
        self.btn_run.setStyleSheet(
            "font-size:14px;font-weight:bold;padding:8px;"
            "background:#1976D2;color:white;border-radius:4px;")
        self.btn_run.clicked.connect(self._on_run)
        bot_lo.addWidget(self.btn_run)
        self.btn_exp = QPushButton("  \U0001F4BE Export PNG  ")
        self.btn_exp.clicked.connect(self._on_export)
        bot_lo.addWidget(self.btn_exp)
        bot_lo.addSpacing(20)
        self.bar = QProgressBar(); self.bar.setRange(0, 1); self.bar.setTextVisible(True)
        bot_lo.addWidget(self.bar, stretch=1)
        main_lo.addWidget(bottom_w)

        # Log area
        self.log = QTextEdit(); self.log.setMaximumHeight(110)
        self.log.setFont(QFont("Consolas", 9))
        self.log.setPlaceholderText("Analysis log output...")
        main_lo.addWidget(self.log)

    # ========== Shared UI Builders ==========
    def _build_param_group(self, prefix: str, default_fov_x: float = 5,
                           default_fov_y: float = 5) -> QGroupBox:
        """Build a Parameters QGroupBox with FOV, Grid Size, Axis Range, IQR, Output Dir.
        
        Sets attributes on self as: sp_fovx_{prefix}, sp_fovy_{prefix}, sp_gs_{prefix},
        sp_xlim_{prefix}, sp_ylim_{prefix}, chk_iqr_{prefix}, sp_iqr_{prefix}, ed_out_{prefix}.
        """
        grp_p = QGroupBox("Parameters")
        pl = QFormLayout(grp_p)

        # FOV X/Y
        fovx = QDoubleSpinBox(); fovx.setRange(0.1, 90); fovx.setValue(default_fov_x); fovx.setDecimals(3)
        pl.addRow("X Half-FOV (\u00b0):", fovx)
        fovy = QDoubleSpinBox(); fovy.setRange(0.1, 90); fovy.setValue(default_fov_y); fovy.setDecimals(3)
        pl.addRow("Y Half-FOV (\u00b0):", fovy)

        # Grid Size
        gs = QSpinBox(); gs.setRange(11, 21); gs.setValue(21); gs.setSingleStep(2)
        pl.addRow("Grid Size:", gs)

        # Axis Range
        h_box = QHBoxLayout()
        xlim = QDoubleSpinBox(); xlim.setRange(0, 50); xlim.setValue(0); xlim.setDecimals(2)
        xlim.setToolTip("\u00b1X range (mm), 0=auto")
        ylim = QDoubleSpinBox(); ylim.setRange(0, 50); ylim.setValue(0); ylim.setDecimals(2)
        ylim.setToolTip("\u00b1Y range (mm), 0=auto")
        h_box.addWidget(QLabel("\u00b1X (mm):")); h_box.addWidget(xlim)
        h_box.addWidget(QLabel("  \u00b1Y (mm):")); h_box.addWidget(ylim); h_box.addStretch()
        pl.addRow("Axis Range:", h_box)

        # IQR
        chk_iqr = QCheckBox("Enable Outlier Removal (IQR)")
        chk_iqr.setChecked(True)
        pl.addRow(chk_iqr)
        sp_iqr = QDoubleSpinBox(); sp_iqr.setRange(1.0, 5.0); sp_iqr.setValue(1.5)
        sp_iqr.setEnabled(True)
        chk_iqr.toggled.connect(sp_iqr.setEnabled)
        pl.addRow("IQR Factor:", sp_iqr)

        # Output Dir
        ed_out = QLineEdit(self.DEFAULT_OUT)
        btn_out = QPushButton("Browse...")
        btn_out.clicked.connect(lambda checked, p=prefix: self._browse_out(p))
        pl.addRow("Output Dir:", ed_out); pl.addRow(btn_out)

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

    # ---------- Tab 1: Distortion Grid ----------
    def _build_tab_grid(self):
        w = QScrollArea(); w.setWidgetResizable(True)
        panel = QWidget(); lo = QVBoxLayout(panel)

        # Wavelength Mode
        grp_wl = QGroupBox("Wavelength Mode")
        wl_lo = QVBoxLayout(grp_wl)
        self.bg_wl = QButtonGroup(self)
        self.rb_single = QRadioButton("Single Color (reference wavelength)")
        self.rb_multi = QRadioButton("Multi Color (all wavelengths)")
        self.bg_wl.addButton(self.rb_single, 0); self.bg_wl.addButton(self.rb_multi, 1)
        self.rb_single.setChecked(True)
        self.bg_wl.buttonClicked.connect(self._on_wl_mode_changed)
        wl_lo.addWidget(self.rb_single); wl_lo.addWidget(self.rb_multi)
        # Wavelength selector (only visible for single mode)
        sel_lo = QHBoxLayout()
        self._lbl_wl = QLabel("Wavelength:")
        sel_lo.addWidget(self._lbl_wl)
        self.cb_wl_g = QComboBox()
        sel_lo.addWidget(self.cb_wl_g)
        sel_lo.addStretch()
        wl_lo.addLayout(sel_lo)
        lo.addWidget(grp_wl)

        # Zoom positions
        self._grp_zoom_g = QGroupBox("Zoom Position(s)")
        self._zl_grid = QGridLayout(self._grp_zoom_g)
        self.chk_zoom = {}
        self._rebuild_zoom_checkboxes(1)  # initial default, replaced on SEQ load
        lo.addWidget(self._grp_zoom_g)

        # Parameters
        lo.addWidget(self._build_param_group('g', 5, 5))
        lo.addStretch()
        w.setWidget(panel)
        return w

    # ---------- Tab 2: Pupil Swim ----------
    def _build_tab_pupil_swim(self):
        w = QScrollArea(); w.setWidgetResizable(True)
        panel = QWidget(); lo = QVBoxLayout(panel)

        # Zoom pair
        self._grp_zoom_ps = QGroupBox("Zoom Positions (Reference vs Target)")
        self._zl_ps = QFormLayout(self._grp_zoom_ps)
        self.cb_ref = QComboBox()
        self.cb_tgt = QComboBox()
        self._zl_ps.addRow("Reference:", self.cb_ref)
        self._zl_ps.addRow("Target:", self.cb_tgt)
        self._rebuild_ps_zoom_combos(12)  # initial, replaced on SEQ load
        lo.addWidget(self._grp_zoom_ps)

        # Output format
        grp_of = QGroupBox("Output Format")
        of_lo = QVBoxLayout(grp_of)
        self.bg_fmt = QButtonGroup(self)
        self.rb_fmt_both = QRadioButton("Both Grid Vectors + Heatmap (Recommended)")
        self.rb_fmt_vec = QRadioButton("Grid Vectors Only")
        self.rb_fmt_hm = QRadioButton("Heatmap Only")
        self.bg_fmt.addButton(self.rb_fmt_both, 0)
        self.bg_fmt.addButton(self.rb_fmt_vec, 1)
        self.bg_fmt.addButton(self.rb_fmt_hm, 2)
        self.rb_fmt_both.setChecked(True)
        of_lo.addWidget(self.rb_fmt_both); of_lo.addWidget(self.rb_fmt_vec); of_lo.addWidget(self.rb_fmt_hm)
        lo.addWidget(grp_of)

        # Parameters
        lo.addWidget(self._build_param_group('ps', 26.565, 26.565))
        lo.addStretch()
        w.setWidget(panel)
        return w

    # ---------- Tab 3: Distortion Correction ----------
    def _build_tab_correction(self):
        """Build Tab 3: polynomial fitting + svrapi_lens CSV export."""
        w = QWidget()
        splitter = QSplitter(Qt.Horizontal)

        # ── Left: control panel ──
        left_scroll = QScrollArea(); left_scroll.setWidgetResizable(True)
        left_scroll.setFixedWidth(420)
        left_panel = QWidget()
        llo = QVBoxLayout(left_panel); llo.setSpacing(6)

        # 1. Wavelength (R/G/B)
        grp_wl = QGroupBox("1. Wavelength (R/G/B)")
        wlay = QFormLayout(grp_wl); wlay.setVerticalSpacing(3)
        self.cmb_corr_wl = []; self.chk_corr_wl = []; self.lbl_corr_nm = []
        for lbl in ["R", "G", "B"]:
            row = QHBoxLayout()
            chk = QCheckBox(); chk.setChecked(True)
            chk.setToolTip(f"Checked=use selected WL for {lbl}; unchecked=center WL")
            self.chk_corr_wl.append(chk); row.addWidget(chk)
            cmb = QComboBox(); cmb.setMinimumWidth(140)
            cmb.addItem("(no SEQ)", None); self.cmb_corr_wl.append(cmb); row.addWidget(cmb)
            nm = QLabel(""); nm.setMinimumWidth(55)
            nm.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.lbl_corr_nm.append(nm); row.addWidget(nm)
            wlay.addRow(f"  {lbl}:", row)
        self.lbl_corr_center = QLabel("Center WL: (no SEQ)")
        self.lbl_corr_center.setStyleSheet("color:#555;")
        wlay.addRow(QLabel(""), self.lbl_corr_center)
        llo.addWidget(grp_wl)

        # 2. Trace params
        grp_tr = QGroupBox("2. Trace Parameters")
        trlay = QFormLayout(grp_tr); trlay.setVerticalSpacing(3)
        self.cmb_corr_fovh = QComboBox(); self.cmb_corr_fovh.setEditable(True)
        self.cmb_corr_fovh.setMinimumWidth(120)
        self.cmb_corr_fovh.setToolTip("H half-FOV from XAN, editable")
        trlay.addRow("H half-FOV (deg):", self.cmb_corr_fovh)
        self.cmb_corr_fovv = QComboBox(); self.cmb_corr_fovv.setEditable(True)
        self.cmb_corr_fovv.setMinimumWidth(120)
        self.cmb_corr_fovv.setToolTip("V half-FOV from YAN, editable")
        trlay.addRow("V half-FOV (deg):", self.cmb_corr_fovv)
        self.cmb_corr_zoom = QComboBox(); self.cmb_corr_zoom.setMinimumWidth(150)
        self.cmb_corr_zoom.addItem("(no SEQ)", 1)
        trlay.addRow("Zoom:", self.cmb_corr_zoom)
        self.dsb_corr_pw = QDoubleSpinBox(); self.dsb_corr_pw.setRange(0.01, 999)
        self.dsb_corr_pw.setValue(11.904); self.dsb_corr_pw.setDecimals(3)
        trlay.addRow("Panel half-W (mm):", self.dsb_corr_pw)
        self.dsb_corr_ph = QDoubleSpinBox(); self.dsb_corr_ph.setRange(0.01, 999)
        self.dsb_corr_ph.setValue(11.904); self.dsb_corr_ph.setDecimals(3)
        trlay.addRow("Panel half-H (mm):", self.dsb_corr_ph)
        self.sb_corr_gs = QSpinBox(); self.sb_corr_gs.setRange(3, 21)
        self.sb_corr_gs.setValue(21)
        trlay.addRow("Grid lines:", self.sb_corr_gs)
        self.chk_corr_sym_h = QCheckBox("Horizontal symmetry (Y fit even-order)")
        self.chk_corr_sym_h.setChecked(True)
        self.chk_corr_sym_v = QCheckBox("Vertical symmetry (X fit even-order)")
        self.chk_corr_sym_v.setChecked(False)
        trlay.addRow("Symmetry:", self.chk_corr_sym_h)
        trlay.addRow("", self.chk_corr_sym_v)
        llo.addWidget(grp_tr)

        # 3. Display panel
        grp_disp = QGroupBox("3. Display Panel")
        dplay = QFormLayout(grp_disp); dplay.setVerticalSpacing(3)
        self.cmb_corr_brand = QComboBox(); self.cmb_corr_brand.setMinimumWidth(150)
        self.cmb_corr_model = QComboBox(); self.cmb_corr_model.setMinimumWidth(150)
        self.cmb_corr_brand.activated.connect(self._on_corr_brand_changed)
        self.cmb_corr_model.activated.connect(self._on_corr_model_changed)
        dplay.addRow("Brand:", self.cmb_corr_brand)
        dplay.addRow("Model:", self.cmb_corr_model)

        self.sb_corr_w0 = QSpinBox(); self.sb_corr_w0.setRange(1, 99999); self.sb_corr_w0.setValue(1920)
        self.sb_corr_h0 = QSpinBox(); self.sb_corr_h0.setRange(1, 99999); self.sb_corr_h0.setValue(1080)
        self.sb_corr_w = QSpinBox(); self.sb_corr_w.setRange(1, 99999); self.sb_corr_w.setValue(1920)
        self.sb_corr_h = QSpinBox(); self.sb_corr_h.setRange(1, 99999); self.sb_corr_h.setValue(1080)
        self.dsb_corr_px = QDoubleSpinBox(); self.dsb_corr_px.setRange(0.0001, 5.0)
        self.dsb_corr_px.setValue(0.00756); self.dsb_corr_px.setDecimals(6)
        self.sb_corr_cols = QSpinBox(); self.sb_corr_cols.setRange(3, 101); self.sb_corr_cols.setValue(17)
        self.sb_corr_rows = QSpinBox(); self.sb_corr_rows.setRange(3, 101); self.sb_corr_rows.setValue(9)
        self.dsb_corr_ox = QDoubleSpinBox(); self.dsb_corr_ox.setRange(-9999, 9999); self.dsb_corr_ox.setValue(0); self.dsb_corr_ox.setDecimals(3)
        self.dsb_corr_oy = QDoubleSpinBox(); self.dsb_corr_oy.setRange(-9999, 9999); self.dsb_corr_oy.setValue(0); self.dsb_corr_oy.setDecimals(3)

        dplay.addRow("Active W (px):", self.sb_corr_w0)
        dplay.addRow("Active H (px):", self.sb_corr_h0)
        dplay.addRow("Pre-correction W (px):", self.sb_corr_w)
        dplay.addRow("Pre-correction H (px):", self.sb_corr_h)
        dplay.addRow("Pixel size (mm/px):", self.dsb_corr_px)
        dplay.addRow("NumCols:", self.sb_corr_cols)
        dplay.addRow("NumRows:", self.sb_corr_rows)
        dplay.addRow("Offset X (px):", self.dsb_corr_ox)
        dplay.addRow("Offset Y (px):", self.dsb_corr_oy)
        llo.addWidget(grp_disp)

        # 4. Manual load
        grp_load = QGroupBox("4. Manual Load (skip CODE V)")
        gload = QHBoxLayout(grp_load)
        self.le_corr_dir = QLineEdit(); self.le_corr_dir.setPlaceholderText("Directory with r/g/b.txt")
        btn_ld = QPushButton("Browse..."); btn_ld.clicked.connect(self._browse_corr_dir)
        gload.addWidget(self.le_corr_dir); gload.addWidget(btn_ld)
        llo.addWidget(grp_load)

        # Buttons
        btn_row = QHBoxLayout()
        def _b(text, color, slot):
            b = QPushButton(text); b.setMinimumHeight(32)
            b.setStyleSheet(f"font-weight:bold;background:{color};color:white;border-radius:3px;padding:4px 8px;")
            b.clicked.connect(slot); return b
        btn_row.addWidget(_b("CODE V Calc", "#1565C0", self._run_correction_codev))
        btn_row.addWidget(_b("Fit Only", "#2E7D32", self._run_correction_fit_only))
        btn_row.addWidget(_b("Export CSV", "#6A1B9A", self._export_correction_csv))
        llo.addLayout(btn_row)

        llo.addStretch()
        left_scroll.setWidget(left_panel)

        # ── Right: matplotlib canvas ──
        right = self._build_canvas_tab("fig_corr", "canvas_corr", "tb_corr", "Distortion Grid")
        right_tabs = QTabWidget()
        right_tabs.addTab(right, "Distortion Grid")

        splitter.addWidget(left_scroll)
        splitter.addWidget(right_tabs)
        splitter.setStretchFactor(1, 1)

        lo = QHBoxLayout(w); lo.setContentsMargins(0, 0, 0, 0)
        lo.addWidget(splitter)
        return w

    def _build_canvas_tab(self, fig_attr, canvas_attr, toolbar_attr, title):
        """Build a single matplotlib canvas tab (in-tab embedding, not popup)."""
        _init_mpl()
        from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
        from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
        from matplotlib.figure import Figure

        tab = QWidget()
        tl = QVBoxLayout(tab)
        fig = Figure(figsize=(8, 6))
        canvas = FigureCanvas(fig)
        canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        tb = NavigationToolbar(canvas, tab)
        tl.addWidget(tb); tl.addWidget(canvas)
        setattr(self, fig_attr, fig)
        setattr(self, canvas_attr, canvas)
        setattr(self, toolbar_attr, tb)
        return tab

    def _load_displays_db(self):
        """Load display panel database for correction tab."""
        from distortion_correction import load_displays_db
        db_path = str(Path(__file__).parent / "displays.json")
        self._displays_db = load_displays_db(db_path)
        brands = sorted(set(d["brand"] for d in self._displays_db))
        self.cmb_corr_brand.clear()
        self.cmb_corr_brand.addItem("(manual)", None)
        for b in brands:
            self.cmb_corr_brand.addItem(b, b)
        self.cmb_corr_model.clear()
        self.cmb_corr_model.addItem("(manual)", -1)

    def _on_corr_brand_changed(self, idx):
        self.cmb_corr_model.clear()
        brand = self.cmb_corr_brand.currentData()
        if brand is None:
            self.cmb_corr_model.addItem("(manual)", -1)
        else:
            items = sorted((d for d in self._displays_db if d["brand"] == brand),
                           key=lambda d: d["model"])
            self.cmb_corr_model.addItem("Select model...", -1)
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

    def _browse_corr_dir(self):
        d = QFileDialog.getExistingDirectory(self, "Select txt directory")
        if d:
            self.le_corr_dir.setText(d)

    # ========== Correction: populate SEQ info ==========
    def _populate_corr_seq_info(self):
        """Populate correction tab widgets from loaded SEQ data."""
        from distortion_analyzer import DistortionAnalyzer
        seq = self.ed_seq.text().strip()
        if not Path(seq).is_file():
            return

        try:
            num_zooms = DistortionAnalyzer.get_zoom_count_from_seq(seq)
            zoom_names = DistortionAnalyzer.get_zoom_names_from_seq(seq)
        except Exception:
            num_zooms = 1; zoom_names = {}

        # Zoom
        self.cmb_corr_zoom.clear()
        for zid in range(1, num_zooms + 1):
            name = zoom_names.get(zid, '')
            label = f"Z{zid}: {name}" if name else f"Z{zid}"
            self.cmb_corr_zoom.addItem(label, zid)

        # Wavelengths
        try:
            wl_info = DistortionAnalyzer.get_wavelengths_from_seq(seq)
            wavelengths = wl_info['wavelengths']
            ref_idx = wl_info['ref_index']
            ref_nm = wavelengths[ref_idx - 1] if ref_idx <= len(wavelengths) else wavelengths[0]
            self.lbl_corr_center.setText(f"Center WL: WL[{ref_idx}] = {ref_nm:.1f}nm")
        except Exception:
            wavelengths = [625.0]; ref_idx = 1; ref_nm = 625.0
            self.lbl_corr_center.setText("Center WL: (unknown)")

        for cmb in self.cmb_corr_wl:
            cmb.clear()
        for i, cmb in enumerate(self.cmb_corr_wl):
            for wi, v in enumerate(wavelengths):
                cmb.addItem(f"WL[{wi+1}] = {v:.1f}nm", wi + 1)
            # Defaults: R->longest, G->center, B->shortest
            if len(wavelengths) >= 3:
                defaults = {0: max(wavelengths), 1: ref_nm, 2: min(wavelengths)}
                target = defaults.get(i, ref_nm)
                for j, v in enumerate(wavelengths):
                    if abs(v - target) < 1.0:
                        cmb.setCurrentIndex(j); break
            elif cmb.count() > 1:
                cmb.setCurrentIndex(min(ref_idx - 1, cmb.count() - 1))
            # Update nm label
            cd = cmb.currentData()
            if cd is not None and cd <= len(wavelengths):
                self.lbl_corr_nm[i].setText(f"{wavelengths[cd - 1]:.1f}nm")
            else:
                self.lbl_corr_nm[i].setText("")

        # Connect combobox change -> update labels
        for i, cmb in enumerate(self.cmb_corr_wl):
            try: cmb.currentIndexChanged.disconnect()
            except Exception: pass
        def _make_updater(idx):
            return lambda: self._update_corr_wl_label(idx)
        for i, cmb in enumerate(self.cmb_corr_wl):
            cmb.currentIndexChanged.connect(_make_updater(i))

        # FOV
        try:
            fov_info = DistortionAnalyzer.get_fov_from_seq(seq)
            x_fov, y_fov = fov_info['x_max'], fov_info['y_max']
        except Exception:
            x_fov, y_fov = 26.565, 26.565

        self.cmb_corr_fovh.clear()
        self.cmb_corr_fovv.clear()
        if x_fov > 0:
            self.cmb_corr_fovh.addItem(f"{x_fov:.4f}", x_fov)
            self.cmb_corr_fovh.setCurrentIndex(0)
        if y_fov > 0:
            self.cmb_corr_fovv.addItem(f"{y_fov:.4f}", y_fov)
            self.cmb_corr_fovv.setCurrentIndex(0)

    def _update_corr_wl_label(self, idx):
        cmb = self.cmb_corr_wl[idx]
        txt = cmb.currentText()
        if "=" in txt:
            self.lbl_corr_nm[idx].setText(txt.split("=")[-1].strip())
        else:
            self.lbl_corr_nm[idx].setText(txt)

    # ========== Correction: handlers ==========
    def _run_correction_codev(self) -> None:
        seq = self.ed_seq.text().strip()
        if not Path(seq).is_file():
            QMessageBox.warning(self, "Error", "Select a valid .seq file"); return

        wl_sel = [cmb.currentData() for cmb in self.cmb_corr_wl]
        if any(v is None for v in wl_sel):
            QMessageBox.warning(self, "Error", "Load a SEQ file first"); return

        center_text = self.lbl_corr_center.text()
        center_wl = wl_sel[1]
        if "WL[" in center_text:
            try:
                center_wl = int(center_text.split("WL[")[1].split("]")[0])
            except (ValueError, IndexError):
                pass

        wl_eff = []
        for i in range(3):
            if self.chk_corr_wl[i].isChecked():
                wl_eff.append(wl_sel[i])
            else:
                wl_eff.append(center_wl)

        try:
            halfx = self.cmb_corr_fovh.currentData()
            halfy = self.cmb_corr_fovv.currentData()
            if halfx is None: halfx = float(self.cmb_corr_fovh.currentText())
            if halfy is None: halfy = float(self.cmb_corr_fovv.currentText())
        except (ValueError, TypeError):
            QMessageBox.warning(self, "Error", "Invalid FOV value"); return

        zoom = self.cmb_corr_zoom.currentData() or 1
        macro = str(Path(__file__).parent / "dist_real_pro.seq")

        self._log("=" * 50)
        self._log(f"Correction CODE V: {Path(seq).name}")
        labels = ["R", "G", "B"]
        self._log(f"WL: {', '.join(f'{labels[i]}:WL[{wl_eff[i]}]' for i in range(3))}")
        self._log(f"FOV H={halfx:.3f} V={halfy:.3f} Zoom={zoom} N={self.sb_corr_gs.value()}")

        self.btn_run.setEnabled(False)
        self.bar.setRange(0, 0)

        self._corr_worker = CorrectionWorker(
            seq, halfx, halfy,
            self.dsb_corr_pw.value(), self.dsb_corr_ph.value(),
            zoom, self.sb_corr_gs.value(), wl_eff, macro)
        self._corr_thread = QThread()
        self._corr_worker.moveToThread(self._corr_thread)
        self._corr_worker.progress.connect(self._log)
        self._corr_worker.finished.connect(self._on_correction_done)
        self._corr_worker.finished.connect(self._corr_thread.quit)
        self._corr_thread.started.connect(self._corr_worker.run)
        self._corr_thread.start()

    def _on_correction_done(self, work_dir, err):
        self.btn_run.setEnabled(True)
        self.bar.setRange(0, 1)
        if err:
            self._log(f"[Correction Error] {err}")
            QMessageBox.critical(self, "CODE V Error", err[:500])
            return
        self._corr_work_dir = work_dir
        self.le_corr_dir.setText(work_dir)
        self._run_correction_fit(work_dir)

    def _run_correction_fit_only(self):
        ld = self.le_corr_dir.text().strip()
        if not ld:
            seq = self.ed_seq.text().strip()
            if Path(seq).is_file():
                ld = str(Path(seq).parent)
            else:
                QMessageBox.warning(self, "Error", "Specify txt directory or load SEQ first"); return
        self._corr_work_dir = ld
        self._run_correction_fit(ld)

    def _run_correction_fit(self, work_dir):
        from distortion_correction import parse_dist_txt, fit_distortion, build_csv_content
        self._log(f"Reading txt: {work_dir}")
        try:
            paths = {c: str(Path(work_dir) / f"{c}.txt") for c in ["r", "g", "b"]}
            for p in paths.values():
                if not Path(p).is_file():
                    raise FileNotFoundError(f"Not found: {p}")

            rd = parse_dist_txt(paths["r"])
            gd = parse_dist_txt(paths["g"])
            bd = parse_dist_txt(paths["b"])
            self._log(f"Data points: R={len(rd)}, G={len(gd)}, B={len(bd)}")

            disdata = np.stack([rd, gd, bd], axis=2)
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
            self._log("Done! Click 'Export CSV' to save.")

        except Exception as e:
            self._log(f"[Fit Error] {e}\n{traceback.format_exc()}")
            QMessageBox.critical(self, "Fit Error", str(e))

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
            QMessageBox.warning(self, "Hint", "Run fit first before exporting"); return

        wd = self._corr_work_dir if hasattr(self, '_corr_work_dir') and self._corr_work_dir else ""
        default = str(Path(wd) / "svrapi_lens_left.csv") if wd else ""
        path, _ = QFileDialog.getSaveFileName(self, "Export CSV (left)", default,
                                               "CSV (*.csv);;All (*)")
        if not path: return

        Path(path).write_text(self._corr_csv_str, newline='')
        right_path = path.replace("_left.csv", "_right.csv")
        Path(right_path).write_text(self._corr_csv_str, newline='')

        self._log(f"CSV saved: {path}")
        self._log(f"           {right_path}")
        QMessageBox.information(self, "Saved", f"Saved:\n{path}\n{right_path}")

    # ========== File Browsers ==========
    def _browse_seq(self):
        p, _ = QFileDialog.getOpenFileName(self, "Open SEQ", "", "SEQ (*.seq);;All (*)")
        if p:
            self.ed_seq.setText(p)
            self._load_wavelengths(p)
            self._populate_corr_seq_info()
            # Auto-set output dir to {program_root}/{lens_name}/
            lens_name = Path(p).stem
            out_dir = str(Path(__file__).parent / lens_name)
            Path(out_dir).mkdir(parents=True, exist_ok=True)
            self.ed_out_g.setText(out_dir)
            self.ed_out_ps.setText(out_dir)

    def _browse_out(self, prefix: str):
        """Unified output dir browser for both tabs."""
        p = QFileDialog.getExistingDirectory(self, "Output Dir")
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
                label = f"W{i+1}: {wl:.1f}nm {'(REF)' if i+1 == ref_idx else ''}"
                self.cb_wl_g.addItem(label, userData=i+1)
            if 1 <= ref_idx <= self.cb_wl_g.count():
                self.cb_wl_g.setCurrentIndex(ref_idx - 1)

            # Set FOV defaults on both tabs
            self.sp_fovx_g.setValue(x_fov)
            self.sp_fovy_g.setValue(y_fov)
            self.sp_fovx_ps.setValue(x_fov)
            self.sp_fovy_ps.setValue(y_fov)
        except Exception as e:
            self._log(f"Warning: could not read wavelengths/FOV: {e}")
            self.cb_wl_g.clear()
            self.cb_wl_g.addItem("W1: 625.0nm (REF)", userData=1)
            self._wl_info = {'wavelengths': [625.0], 'ref_index': 1}

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
            label = f"Z{zid} {name}" if name else f"Z{zid}"
            ch = QCheckBox(label)
            ch.setToolTip(name if name else f"Zoom {zid}")
            self.chk_zoom[zid] = ch
            r, c = divmod(zid - 1, 4)
            self._zl_grid.addWidget(ch, r, c)

        # Default select first 3 (or all if fewer)
        for z in range(1, min(4, num_zooms + 1)):
            self.chk_zoom[z].setChecked(True)

        # Recreate Select All / Clear buttons fresh each time
        num_rows = (num_zooms - 1) // 4 + 1
        self._btn_sa_g = QPushButton("Select All")
        self._btn_cl_g = QPushButton("Clear")
        self._btn_sa_g.clicked.connect(
            lambda: [c.setChecked(True) for c in self.chk_zoom.values()])
        self._btn_cl_g.clicked.connect(
            lambda: [c.setChecked(False) for c in self.chk_zoom.values()])
        self._zl_grid.addWidget(self._btn_sa_g, num_rows, 0)
        self._zl_grid.addWidget(self._btn_cl_g, num_rows, 1)

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
                label = f"Z{z} {name}" if name else f"Z{z}"
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
            QMessageBox.warning(self, "Error", f"SEQ not found:\n{seq}")
            return

        idx = self.tabs.currentIndex()

        if idx == 2:
            # === Correction tab: delegate to its own handler ===
            self._run_correction_codev()
            return

        if idx == 0:
            # === Distortion Grid mode ===
            zooms = [z for z, ch in self.chk_zoom.items() if ch.isChecked()]
            if not zooms:
                QMessageBox.warning(self, "Hint", "Select at least 1 Zoom position")
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
                QMessageBox.warning(self, "Hint", "Ref and Target must be different")
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

        self.btn_run.setEnabled(False)
        self.bar.setRange(0, 0)
        self._log(f"Start: {cfg['mode']}, SEQ={Path(seq).name}")
        self.worker = AnalysisWorker(seq, **cfg)
        self.worker.progress.connect(self._log)
        self.worker.finished_signal.connect(self._on_done)
        self.worker.error_signal.connect(self._on_err)
        self.worker.start()

    def _on_done(self, res: Optional[dict]) -> None:
        self.btn_run.setEnabled(True)
        self.bar.setRange(0, 1)
        if not res: return
        self.result = res
        mode = res.get('mode', '?')
        n_results = len(res.get('results', {}))
        self._log(f"Done: mode={mode}, {n_results} dataset(s)")

        # Auto-popup after 300ms
        QTimer.singleShot(300, self._auto_popup)

    def _on_err(self, e: str) -> None:
        self.btn_run.setEnabled(True)
        self.bar.setRange(0, 1)
        self._log(f"ERROR: {e}")
        QMessageBox.critical(self, "Error", e)

    # ====================================================================
    #  DRAWING — auto-popup on analysis complete
    # ====================================================================
    def _auto_popup(self):
        """Popup chart(s) matching current analysis mode."""
        if not self.result: return
        try:
            mode = self.result.get('mode', '?')
            if mode == 'grid':
                wl_mode = self.result.get('wl_mode', 'single')
                if wl_mode == 'multi':
                    self._draw_multi_color_popup()
                else:
                    self._draw_single_color_popup()
            elif mode == 'pupil_swim':
                fmt = self._output_format()
                if fmt in ('both', 'vectors'):
                    self._draw_ps_vectors_popup()
                if fmt in ('both', 'heatmap'):
                    self._draw_ps_heatmap_popup()
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
            QMessageBox.information(self, "Hint", "No data yet"); return

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
