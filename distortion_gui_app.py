# -*- coding: utf-8 -*-
"""
Distortion Analysis GUI App (PyQt5) v4.0
- Two analysis modes: Distortion Grid / Pupil Swim
- All charts in independent popup dialogs (FigureDialog)
- Wavelength-aware: single color or multi-color overlay from SEQ file
"""

from typing import Optional, Any
import sys
import numpy as np
from pathlib import Path

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QGroupBox, QLabel, QPushButton, QComboBox, QCheckBox, QSpinBox,
    QDoubleSpinBox, QLineEdit, QTextEdit, QFileDialog, QSplitter,
    QProgressBar, QMessageBox, QGridLayout, QScrollArea, QFormLayout,
    QDialog, QTabWidget, QRadioButton, QButtonGroup,
)
from PyQt5.QtCore import QThread, pyqtSignal, QTimer
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
        self._build_ui()

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

    # ========== File Browsers ==========
    def _browse_seq(self):
        p, _ = QFileDialog.getOpenFileName(self, "Open SEQ", "", "SEQ (*.seq);;All (*)")
        if p:
            self.ed_seq.setText(p)
            self._load_wavelengths(p)
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
