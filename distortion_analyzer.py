"""
distortion_analyzer.py — 畸变分析模块

提供可复用的畸变分析功能：
    1. 连接 CODE V COM 接口
    2. 加载镜头文件
    3. 运行畸变宏获取网格数据
    4. 绘制畸变网格图
    5. 计算和可视化 Pupil Swim

使用示例:
    from distortion_analyzer import DistortionAnalyzer
    
    # 初始化分析器
    analyzer = DistortionAnalyzer(workdir=r"d:\\BaiduSyncdisk\\My Optics\\OpticsClaw")
    
    # 加载镜头
    analyzer.load_lens(r"D:\\BaiduSyncdisk\\My Optics\\Pancake\\VR132P\\VR132090-0417.seq")
    
    # 获取畸变网格
    grid = analyzer.get_distortion_grid(zoom_pos=1, x_fov=5.0, y_fov=5.0, num_lines=21)
    
    # 绘制网格
    analyzer.plot_grid(grid, title="Zoom 1 Distortion Grid")
    
    # 计算 Pupil Swim
    swim = analyzer.calculate_pupil_swim(grid_ref, grid_compare)
    
    # 绘制 Pupil Swim 热力图
    analyzer.plot_pupil_swim_heatmap(grid_ref, grid_compare, title="Pupil Swim Analysis")
"""

import time
import re
import logging
from functools import cached_property
from contextlib import contextmanager
from typing import Optional, Tuple, Dict, List, Union, Generator, Any
from dataclasses import dataclass
from pathlib import Path

# Configure logging (will be overridden by GUI if needed)
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
_logger = logging.getLogger(__name__)

try:
    import numpy as np
    import matplotlib.pyplot as plt
    from matplotlib.tri import Triangulation, LinearTriInterpolator
    _HAS_NUMPY = True
except ImportError:
    _HAS_NUMPY = False

# Keywords that must not be interpreted as ZOO positions
_ZOO_EXCLUDE_WORDS = frozenset({
    'TIT', 'EPD', 'WTW', 'XAN', 'YAN', 'WTF',
    'VUX', 'VLX', 'VUY', 'VLY', 'DOR', 'PWL',
})

try:
    import win32com.client
    _HAS_WIN32 = True
except ImportError:
    _HAS_WIN32 = False


@dataclass
class DistortionGrid:
    """畸变网格数据类"""
    paraxial: np.ndarray  # 理想网格 shape=(n, n, 2)
    actual: np.ndarray    # 实际网格 shape=(n, n, 2)
    zoom_pos: int
    x_fov: float
    y_fov: float
    num_lines: int
    
    @property
    def displacement(self) -> np.ndarray:
        """计算位移 (actual - paraxial)"""
        return self.actual - self.paraxial
    
    @cached_property
    def displacement_magnitude(self) -> np.ndarray:
        """计算位移大小（缓存结果，避免 max/mean/rms 重复计算）"""
        disp = self.displacement
        return np.linalg.norm(disp, axis=2)
    
    @property
    def max_displacement(self) -> float:
        """最大位移"""
        return float(np.max(self.displacement_magnitude))
    
    @property
    def mean_displacement(self) -> float:
        """平均位移"""
        return float(np.mean(self.displacement_magnitude))
    
    @property
    def rms_displacement(self) -> float:
        """RMS位移"""
        return float(np.sqrt(np.mean(self.displacement_magnitude**2)))


@dataclass
class PupilSwimResult:
    """Pupil Swim 分析结果"""
    grid_ref: DistortionGrid
    grid_compare: DistortionGrid
    displacement: np.ndarray
    
    @cached_property
    def magnitude(self) -> np.ndarray:
        """位移大小（缓存结果，避免 max/mean/rms 重复计算）"""
        return np.linalg.norm(self.displacement, axis=2)
    
    @property
    def max_swim(self) -> float:
        """最大Pupil Swim"""
        return float(np.max(self.magnitude))
    
    @property
    def mean_swim(self) -> float:
        """平均Pupil Swim"""
        return float(np.mean(self.magnitude))
    
    @property
    def rms_swim(self) -> float:
        """RMS Pupil Swim"""
        return float(np.sqrt(np.mean(self.magnitude**2)))


class DistortionAnalyzer:
    """畸变分析器类"""
    
    # Default macro directory: program root (macro files copied alongside this module)
    _MACRO_DIR = Path(__file__).parent.resolve()
    DEFAULT_DIST_REAL_MACRO = _MACRO_DIR / "dist_real_pro.seq"
    DEFAULT_DIST_POLAR_MACRO = _MACRO_DIR / "dist_polar_pro.seq"
    
    def __init__(self, workdir: Optional[str] = None, 
                 macro_dir: Optional[str] = None,
                 auto_connect: bool = True):
        """
        初始化畸变分析器
        
        Args:
            workdir: 工作目录，默认为当前目录
            macro_dir: 宏文件目录
            auto_connect: 是否自动连接 CODE V
        """
        if not _HAS_WIN32:
            raise RuntimeError("需要 pywin32: pip install pywin32")
        if not _HAS_NUMPY:
            raise RuntimeError("需要 numpy: pip install numpy")
            
        self.workdir = workdir or str(Path.cwd())
        self.macro_dir = macro_dir or self._MACRO_DIR
        self._cv = None
        self._current_lens: Optional[str] = None
        
        if auto_connect:
            self.connect()
    
    def connect(self) -> 'DistortionAnalyzer':
        """连接 CODE V COM 接口"""
        if self._cv is None:
            self._cv = win32com.client.Dispatch("CODEV.Application")
            try:
                self._cv.StartCodeV()
            except Exception:
                pass
            self._cv.Command(f'CD "{self.workdir}"')
        return self
    
    def disconnect(self) -> None:
        """断开 CODE V 连接"""
        self._cv = None

    @contextmanager
    def session(self) -> Generator:
        """上下文管理器：自动管理 CODE V 连接生命周期。

        用法:
            with analyzer.session() as a:
                grid = a.get_distortion_grid(zoom_pos=1)
        """
        was_connected = self._cv is not None
        self.connect()
        try:
            yield self
        finally:
            if not was_connected:
                self.disconnect()
    
    @property
    def cv(self):
        """获取 CODE V COM 接口对象"""
        if self._cv is None:
            self.connect()
        return self._cv
    
    def cmd(self, command: str) -> str:
        """执行 CODE V 命令"""
        return self.cv.Command(command)
    
    def load_lens(self, lens_path: str) -> 'DistortionAnalyzer':
        """
        加载镜头文件
        
        Args:
            lens_path: SEQ 文件路径
        """
        self.cmd(f'IN "{lens_path}"')
        self._current_lens = lens_path
        return self
    
    def get_zoom_info(self) -> Dict:
        """获取变焦系统信息"""
        result = self.cmd('ZOO ?')
        # 解析输出，例如: "There are  4 zoom positions in the system"
        match = re.search(r'(\d+)\s+zoom\s+position', result, re.IGNORECASE)
        num_zooms = int(match.group(1)) if match else 1
        
        return {
            'num_zoom_positions': num_zooms,
            'raw_output': result
        }
    
    def set_zoom(self, zoom_pos: int) -> 'DistortionAnalyzer':
        """设置变焦位置"""
        self.cmd(f'ZOO {zoom_pos}')
        return self

    @staticmethod
    def _read_seq_lines(seq_path: str) -> Optional[list]:
        """Read SEQ file lines. Returns None on IO error."""
        try:
            return Path(seq_path).read_text(errors='replace').splitlines()
        except (OSError, IOError):
            return None

    @staticmethod
    def get_zoom_count_from_seq(seq_path: str) -> int:
        """
        从 SEQ 文件解析变焦位置数量

        CODE V SEQ 中，曲面数据区第一行 ZOO N 声明变焦数。
        后续 ZOO TIT/EPD/WTW 等为各变焦位置的参数值。
        这里查找 ZOO 后紧跟纯数字的行来获取 N。
        """
        lines = DistortionAnalyzer._read_seq_lines(seq_path)
        if lines is None:
            return 1

        in_surface_data = False

        for line in lines:
            upper = line.strip().upper()
            if not upper or upper.startswith('!'):
                continue
            if not in_surface_data:
                if (upper.startswith('S ') or upper == 'S' or
                    upper.startswith('STO') or upper.startswith('RDM')):
                    in_surface_data = True
                continue

            # Look for "ZOO  N" where N is a pure integer (not a keyword)
            if upper.startswith('ZOO'):
                parts = upper.split()
                if len(parts) >= 2:
                    second = parts[1]
                    if second not in _ZOO_EXCLUDE_WORDS:
                        try:
                            return int(second)
                        except ValueError:
                            pass

        return 1

    @staticmethod
    def get_zoom_names_from_seq(seq_path: str) -> Dict[int, str]:
        """
        从 SEQ 文件解析变焦位置名称（TIT Z<n> "name" 格式）

        返回: {1: 'EPD_+0_R', 2: 'EPD_0_G', ...}
        若无 TIT 行则返回空 dict，调用方自行 fallback 为 'Z1', 'Z2' 等
        """
        zoom_names: Dict[int, str] = {}
        # 匹配 TIT Z<num> "name" 或 TIT Z<num> 'name'
        tit_pattern = re.compile(
            r'^TIT\s+Z(\d+)\s+["\']([^"\']*)["\']',
            re.IGNORECASE
        )
        lines = DistortionAnalyzer._read_seq_lines(seq_path)
        if lines is None:
            return zoom_names
        for line in lines:
            m = tit_pattern.match(line.strip())
            if m:
                zid = int(m.group(1))
                name = m.group(2)
                zoom_names[zid] = name
        return zoom_names

    @staticmethod
    def get_fov_from_seq(seq_path: str) -> Dict:
        """
        从 SEQ 文件头解析 XAN/YAN 视场角，返回最大绝对值

        处理 & 续行符。返回:
            {'x_max': float, 'y_max': float}
        """
        lines = DistortionAnalyzer._read_seq_lines(seq_path)
        if lines is None:
            return {'x_max': 26.565, 'y_max': 26.565}

        def _gather_values(start_line_idx):
            """从 start_line_idx 开始收集所有以空格分隔的数值，处理 & 续行"""
            vals = []
            i = start_line_idx
            while i < len(lines):
                text = lines[i].strip()
                # Remove leading keyword (XAN or YAN)
                upper = text.upper()
                if upper.startswith('XAN'):
                    text = text[3:].strip()
                elif upper.startswith('YAN'):
                    text = text[3:].strip()
                # Split and collect
                for token in text.split():
                    tok = token.rstrip('&')
                    try:
                        vals.append(float(tok))
                    except ValueError:
                        pass
                if text.rstrip().endswith('&'):
                    i += 1
                else:
                    break
            return vals

        x_max, y_max = 0.0, 0.0
        for i, line in enumerate(lines):
            upper = line.strip().upper()
            if upper.startswith('XAN'):
                vals = _gather_values(i)
                if vals:
                    x_max = max(abs(v) for v in vals)
            elif upper.startswith('YAN'):
                vals = _gather_values(i)
                if vals:
                    y_max = max(abs(v) for v in vals)

        # Fallback: if XAN is all zero, use YAN or default
        if x_max == 0:
            x_max = y_max if y_max > 0 else 26.565
        if y_max == 0:
            y_max = x_max if x_max > 0 else 26.565

        return {'x_max': x_max, 'y_max': y_max}

    @staticmethod
    def get_wavelengths_from_seq(seq_path: str) -> Dict:
        """
        从 SEQ 文件解析 WL 和 REF 命令，返回可用波长列表

        Args:
            seq_path: SEQ 文件路径

        Returns:
            dict: {
                'wavelengths': [float, ...],  # 所有波长值 (nm)
                'ref_index': int               # 参考波长索引 (1-based)
            }
        """
        wavelengths = []
        ref_index = 1
        lines = DistortionAnalyzer._read_seq_lines(seq_path)
        if lines is None:
            return {'wavelengths': [625.0], 'ref_index': 1}

        i = 0
        while i < len(lines):
            line = lines[i].strip().upper()
            # 处理 WL 命令 (可能跨多行，用 & 续行)
            if line.startswith('WL'):
                # 收集当前行及所有续行
                wl_text = line[2:].strip()
                while wl_text.endswith('&') and i + 1 < len(lines):
                    i += 1
                    cont = lines[i].strip().upper()
                    wl_text = wl_text[:-1] + ' ' + cont.strip()
                for token in wl_text.split():
                    if token == '&':
                        continue
                    try:
                        wavelengths.append(float(token))
                    except ValueError:
                        pass
            elif line.startswith('REF'):
                parts = line[3:].split()
                if parts:
                    try:
                        ref_index = int(parts[0])
                    except ValueError:
                        pass
            i += 1

        if not wavelengths:
            wavelengths = [625.0]  # fallback

        return {'wavelengths': wavelengths, 'ref_index': ref_index}
    
    def get_distortion_grid(self,
                           zoom_pos: int = 1,
                           x_fov: float = 5.0,
                           y_fov: float = 5.0,
                           num_lines: int = 21,
                           panel_width: float = 0.0,
                           panel_height: float = 0.0,
                           use_polar: bool = False,
                           max_radius: float = 0,
                           wavelength: str = "RED",
                           wl_index: int = 2) -> DistortionGrid:
        """
        获取畸变网格数据

        Args:
            zoom_pos: 变焦位置
            x_fov: X方向半视场角（度）
            y_fov: Y方向半视场角（度）
            num_lines: 网格线数量
            panel_width: 面板半宽度（mm）
            panel_height: 面板半高度（mm）
            use_polar: 是否使用极坐标宏
            max_radius: 极坐标最大半径（0=自动计算）
            wavelength: 传给宏的#6参数，控制绘图颜色（如 "RED"/"GRE"/"BLU"）
            wl_index:  1-based 波长索引，用于 REF 切换追迹波长
                       （这才是真正决定追迹波长的参数）

        Returns:
            DistortionGrid 对象
        """
        # Note: Do NOT call set_zoom() here — the dist_real_pro.seq macro
        # handles zoom switching internally via its #8 parameter.
        # Sending ZOO before RUN actually *interferes* with the macro's
        # internal zoom handling and causes all positions to return identical data.

        if use_polar:
            return self._run_polar_macro(zoom_pos, max_radius, num_lines)
        else:
            return self._run_real_macro(zoom_pos, x_fov, y_fov, num_lines,
                                       panel_width, panel_height, wavelength,
                                       wl_index)
    
    def _run_real_macro(self, zoom_pos: int, x_fov: float, y_fov: float,
                       num_lines: int, panel_width: float,
                       panel_height: float,
                       wavelength: str = "RED",
                       wl_index: int = 2) -> DistortionGrid:
        """运行 dist_real_pro.seq 宏
        
        重要：ARG6 "color" 只控制绘图颜色，不控制追迹波长。
        必须在调用宏前用 REF 切换参考波长，否则 multi-color
        模式下所有运行追迹同一波长，网格数据完全相同。
        """
        # 创建临时文件名
        temp_file = str(Path(self.workdir) / f"dist_z{zoom_pos}_{int(time.time())}.txt")

        try:
            # ---- 关键：切换追迹波长 ----
            # ARG6 只控制绘图线条颜色，实际光线追迹使用的是 CODE V
            # 当前的参考波长。必须用 REF 命令切换后才能获得不同
            # 波长的真实畸变网格数据。
            self.cmd(f'REF {wl_index}')
            
            # 重定向输出到文件
            self.cmd(f"OUT '{temp_file}'")

            # 运行宏（参数 #6 = 绘图颜色，仅影响图表线条颜色）
            macro_path = Path(self.macro_dir) / "dist_real_pro.seq"
            cmd = (f'RUN "{macro_path}" {x_fov} {y_fov} {panel_width} {panel_height} '
                   f'"" "{wavelength}" {num_lines} {zoom_pos} "Yes"')
            self.cmd(cmd)
            
            # 恢复输出
            self.cmd("OUT")
            
            # 等待文件写入
            time.sleep(0.2)
            
            # 读取结果
            result = self._read_temp_file(temp_file)
            
            # 解析网格数据
            paraxial, actual = self._parse_grid_data(result, num_lines)
            
            return DistortionGrid(
                paraxial=paraxial,
                actual=actual,
                zoom_pos=zoom_pos,
                x_fov=x_fov,
                y_fov=y_fov,
                num_lines=num_lines
            )
            
        finally:
            # 清理临时文件
            self._safe_remove(temp_file)
    
    def _run_polar_macro(self, zoom_pos: int, max_radius: float,
                        num_lines: int) -> DistortionGrid:
        """运行 dist_polar_pro.seq 宏"""
        # 极坐标宏生成 plt 文件，需要解析
        macro_path = Path(self.macro_dir) / "dist_polar_pro.seq"
        
        # 运行宏
        cmd = f'IN "{macro_path}" {max_radius} "" 2 "RED" {num_lines} 12 {zoom_pos} "No"'
        self.cmd(cmd)
        
        # 读取 plt 文件（如果需要）
        # 注意：极坐标宏主要生成可视化输出，数据提取需要额外处理
        
        # 返回空网格（需要进一步实现 plt 解析）
        n = num_lines
        return DistortionGrid(
            paraxial=np.zeros((n, n, 2)),
            actual=np.zeros((n, n, 2)),
            zoom_pos=zoom_pos,
            x_fov=max_radius,
            y_fov=max_radius,
            num_lines=num_lines
        )
    
    def _read_temp_file(self, filepath: str, max_retries: int = 10) -> str:
        """读取临时文件内容"""
        for _ in range(max_retries):
            try:
                with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
                    return f.read()
            except FileNotFoundError:
                time.sleep(0.1)
        return ""
    
    def _safe_remove(self, filepath: str) -> None:
        """安全删除文件"""
        try:
            Path(filepath).unlink(missing_ok=True)
        except:
            pass
    
    def _parse_grid_data(self, text: str, num_lines: int) -> Tuple[np.ndarray, np.ndarray]:
        """
        解析畸变网格数据
        
        数据格式:
            Rel X Fld  Rel Y Fld      Parax X      Parax Y       Real X       Real Y
        """
        paraxial_grid = np.zeros((num_lines, num_lines, 2))
        actual_grid = np.zeros((num_lines, num_lines, 2))
        
        lines = text.split('\n')
        data_started = False
        
        for line in lines:
            line = line.strip()
            
            # 查找数据表头
            if "Rel X Fld" in line and "Parax X" in line:
                data_started = True
                continue
            
            if not data_started:
                continue
            
            # 检查是否到达数据结束
            if not line or line.startswith('CV>') or line.startswith('?'):
                continue
            
            # 解析数据行
            parts = line.split()
            
            if len(parts) >= 6:
                try:
                    rel_x = float(parts[0])
                    rel_y = float(parts[1])
                    parax_x = float(parts[2])
                    parax_y = float(parts[3])
                    
                    # 检查是否是光线失败
                    if parts[4] == "Chief":
                        continue
                    
                    real_x = float(parts[4])
                    real_y = float(parts[5])
                    
                    # 将相对场坐标转换为数组索引
                    j = int(round((rel_x + 1) / 2 * (num_lines - 1)))
                    i = int(round((1 - rel_y) / 2 * (num_lines - 1)))
                    
                    if 0 <= i < num_lines and 0 <= j < num_lines:
                        paraxial_grid[i, j] = [parax_x, parax_y]
                        actual_grid[i, j] = [real_x, real_y]
                        
                except (ValueError, IndexError):
                    continue
        
        return paraxial_grid, actual_grid
    
    def calculate_pupil_swim(self, grid_ref: DistortionGrid, 
                            grid_compare: DistortionGrid) -> PupilSwimResult:
        """
        计算 Pupil Swim
        
        Args:
            grid_ref: 参考网格
            grid_compare: 对比网格
        
        Returns:
            PupilSwimResult 对象
        """
        displacement = grid_compare.actual - grid_ref.actual
        
        return PupilSwimResult(
            grid_ref=grid_ref,
            grid_compare=grid_compare,
            displacement=displacement
        )
    
    # ==================== 绘图函数 ====================

    @staticmethod
    def _unwrap_grid(grid: Union['DistortionGrid', np.ndarray]) -> np.ndarray:
        """从 DistortionGrid 或原始 ndarray 中提取实际网格数据。"""
        return grid.actual if isinstance(grid, DistortionGrid) else grid

    def plot_grid(self, grid: Union[DistortionGrid, np.ndarray],
                  ax: Optional[plt.Axes] = None,
                  color: str = 'blue',
                  label: str = 'Grid',
                  title: Optional[str] = None,
                  show_points: bool = True,
                  alpha: float = 0.7,
                  linewidth: float = 1.0) -> Tuple[plt.Figure, plt.Axes]:
        """
        绘制畸变网格
        
        Args:
            grid: DistortionGrid 对象或实际网格数组
            ax: 可选的 matplotlib Axes 对象
            color: 网格颜色
            label: 图例标签
            title: 图表标题
            show_points: 是否显示网格点
            alpha: 透明度
            linewidth: 线宽
        """
        grid_data = self._unwrap_grid(grid)
        num_lines = grid.num_lines if isinstance(grid, DistortionGrid) else grid.shape[0]
        
        if ax is None:
            fig, ax = plt.subplots(figsize=(10, 10))
        else:
            fig = ax.figure
        
        # 同时绘制水平线和垂直线
        for i in range(num_lines):
            # 水平线（行 i）
            ax.plot(grid_data[i, :, 0], grid_data[i, :, 1], color=color,
                   linewidth=linewidth, alpha=alpha,
                   label=label if i == 0 else "")
            # 垂直线（列 i）
            ax.plot(grid_data[:, i, 0], grid_data[:, i, 1], color=color,
                   linewidth=linewidth, alpha=alpha)
        
        # 绘制网格点
        if show_points:
            ax.scatter(grid_data[:, :, 0], grid_data[:, :, 1], 
                      c=color, s=10, alpha=alpha*0.7)
        
        ax.set_aspect('equal')
        ax.set_xlabel('X (mm)', fontsize=12)
        ax.set_ylabel('Y (mm)', fontsize=12)
        ax.grid(True, alpha=0.3)
        
        if title:
            ax.set_title(title, fontsize=14)
        
        if label:
            ax.legend(loc='upper right')
        
        return fig, ax
    
    def plot_grid_comparison(self, grid_ref: Union[DistortionGrid, np.ndarray],
                            grid_compare: Union[DistortionGrid, np.ndarray],
                            ax: Optional[plt.Axes] = None,
                            color_ref: str = 'blue',
                            color_compare: str = 'red',
                            label_ref: str = 'Reference',
                            label_compare: str = 'Compare',
                            title: Optional[str] = None,
                            show_arrows: bool = True,
                            arrow_scale: float = 0.1) -> Tuple[plt.Figure, plt.Axes]:
        """
        绘制两个网格对比，带偏移矢量
        """
        grid_ref_data = self._unwrap_grid(grid_ref)
        grid_compare_data = self._unwrap_grid(grid_compare)
        
        if ax is None:
            fig, ax = plt.subplots(figsize=(10, 10))
        else:
            fig = ax.figure
        
        # 绘制两个网格
        self.plot_grid(grid_ref_data, ax=ax, color=color_ref, 
                      label=label_ref, show_points=False)
        self.plot_grid(grid_compare_data, ax=ax, color=color_compare,
                      label=label_compare, show_points=False)
        
        # 绘制偏移矢量
        if show_arrows:
            displacement = grid_compare_data - grid_ref_data
            X = grid_ref_data[:, :, 0]
            Y = grid_ref_data[:, :, 1]
            U = displacement[:, :, 0]
            V = displacement[:, :, 1]
            
            q = ax.quiver(X, Y, U, V,
                         scale=arrow_scale, scale_units='xy', angles='xy',
                         color='black', width=0.002, headwidth=4, headlength=5,
                         headaxislength=4, minshaft=1, minlength=0)
            ax.quiverkey(q, X=0.85, Y=1.02, U=0.05, 
                        label='0.05 mm', labelpos='E', 
                        fontproperties={'size': 9})
        
        ax.set_aspect('equal')
        ax.set_xlabel('X (mm)', fontsize=12)
        ax.set_ylabel('Y (mm)', fontsize=12)
        ax.grid(True, alpha=0.3)
        
        if title:
            ax.set_title(title, fontsize=14)
        
        ax.legend(loc='upper right')
        
        return fig, ax
    
    def plot_pupil_swim_heatmap(self, 
                               grid_ref: Union[DistortionGrid, np.ndarray],
                               grid_compare: Union[DistortionGrid, np.ndarray],
                               ax: Optional[plt.Axes] = None,
                               title: str = "Pupil Swim",
                               cmap: str = 'hot',
                               show_stats: bool = True) -> Tuple[plt.Figure, plt.Axes]:
        """
        绘制 Pupil Swim 热力图
        """
        grid_ref_data = self._unwrap_grid(grid_ref)
        grid_compare_data = self._unwrap_grid(grid_compare)
        
        # 计算位移
        displacement = grid_compare_data - grid_ref_data
        magnitude = np.linalg.norm(displacement, axis=2)
        
        if ax is None:
            fig, ax = plt.subplots(figsize=(10, 8))
        else:
            fig = ax.figure
        
        # 展平数组
        X = grid_ref_data[:, :, 0]
        Y = grid_ref_data[:, :, 1]
        x_flat = X.flatten()
        y_flat = Y.flatten()
        mag_flat = magnitude.flatten()
        
        # 创建三角剖分
        triang = Triangulation(x_flat, y_flat)
        
        # 创建插值网格
        x_min, x_max = x_flat.min(), x_flat.max()
        y_min, y_max = y_flat.min(), y_flat.max()
        xi = np.linspace(x_min, x_max, 200)
        yi = np.linspace(y_min, y_max, 200)
        Xi, Yi = np.meshgrid(xi, yi)
        
        # 线性插值
        interpolator = LinearTriInterpolator(triang, mag_flat)
        Zi = interpolator(Xi, Yi)
        
        # 绘制热力图
        im = ax.pcolormesh(Xi, Yi, Zi, shading='gouraud', cmap=cmap)
        plt.colorbar(im, ax=ax, label='Displacement (mm)')
        
        ax.set_aspect('equal')
        ax.set_xlabel('X (mm)', fontsize=11)
        ax.set_ylabel('Y (mm)', fontsize=11)
        ax.set_title(title, fontsize=12)
        
        # 打印统计信息
        if show_stats:
            _logger.info(f"\n=== {title} ===")
            _logger.info(f"最大位移: {np.max(magnitude):.4f} mm")
            _logger.info(f"平均位移: {np.mean(magnitude):.4f} mm")
            _logger.info(f"RMS 位移: {np.sqrt(np.mean(magnitude**2)):.4f} mm")
        
        return fig, ax
    
    def plot_multi_grids(self, 
                        grids: Dict[Union[int, str], Union[DistortionGrid, np.ndarray]],
                        colors: Optional[Dict] = None,
                        labels: Optional[Dict] = None,
                        figsize: Tuple[int, int] = (12, 12),
                        title: Optional[str] = None) -> Tuple[plt.Figure, plt.Axes]:
        """
        在一张图上绘制多个畸变网格
        
        Args:
            grids: 网格字典 {key: grid}
            colors: 颜色字典 {key: color}
            labels: 标签字典 {key: label}
        """
        fig, ax = plt.subplots(figsize=figsize)
        
        for key, grid in grids.items():
            color = colors.get(key, 'gray') if colors else 'gray'
            label = labels.get(key, str(key)) if labels else str(key)
            
            grid_data = self._unwrap_grid(grid)
            
            self.plot_grid(grid_data, ax=ax, color=color, label=label, 
                          show_points=False)
        
        ax.set_aspect('equal')
        ax.set_xlabel('X (mm)', fontsize=12)
        ax.set_ylabel('Y (mm)', fontsize=12)
        ax.grid(True, alpha=0.3)
        ax.legend(loc='upper right')
        
        if title:
            ax.set_title(title, fontsize=14)
        
        return fig, ax
    
    # ==================== 批量分析函数 ====================
    
    def analyze_zoom_range(self,
                          zoom_positions: List[int],
                          x_fov: float = 5.0,
                          y_fov: float = 5.0,
                          num_lines: int = 21,
                          panel_width: float = 0.0,
                          panel_height: float = 0.0) -> Dict[int, DistortionGrid]:
        """
        批量分析多个变焦位置
        
        Returns:
            {zoom_pos: DistortionGrid} 字典
        """
        results = {}
        for zoom_pos in zoom_positions:
            _logger.info(f"正在获取 Z{zoom_pos} 畸变网格...")
            grid = self.get_distortion_grid(
                zoom_pos=zoom_pos,
                x_fov=x_fov,
                y_fov=y_fov,
                num_lines=num_lines,
                panel_width=panel_width,
                panel_height=panel_height
            )
            results[zoom_pos] = grid
        return results
    
    def analyze_pupil_swim_matrix(self,
                                 grids: Dict[int, DistortionGrid],
                                 ref_key: int,
                                 compare_keys: List[int]) -> Dict[int, PupilSwimResult]:
        """
        计算多个变焦位置相对于参考位置的 Pupil Swim
        
        Args:
            grids: 网格字典
            ref_key: 参考变焦位置
            compare_keys: 对比变焦位置列表
        
        Returns:
            {zoom_pos: PupilSwimResult} 字典
        """
        ref_grid = grids[ref_key]
        results = {}
        
        for key in compare_keys:
            if key in grids:
                swim = self.calculate_pupil_swim(ref_grid, grids[key])
                results[key] = swim
                _logger.info(f"Z{ref_key} vs Z{key}: Max={swim.max_swim:.4f}mm, "
                      f"Mean={swim.mean_swim:.4f}mm, RMS={swim.rms_swim:.4f}mm")
        
        return results


# ==================== 便捷函数 ====================

def quick_distortion_analysis(lens_path: str,
                              zoom_positions: List[int],
                              x_fov: float = 5.0,
                              y_fov: float = 5.0,
                              num_lines: int = 21,
                              output_dir: Optional[str] = None) -> Dict[int, DistortionGrid]:
    """
    快速畸变分析 - 一键获取多个变焦位置的畸变网格
    
    Args:
        lens_path: 镜头文件路径
        zoom_positions: 变焦位置列表
        x_fov, y_fov: 视场角
        num_lines: 网格线数量
        output_dir: 输出目录（可选）
    
    Returns:
        网格字典
    
    示例:
        grids = quick_distortion_analysis(
            lens_path=r"D:\\...\\lens.seq",
            zoom_positions=[1, 2, 3],
            x_fov=5.0,
            y_fov=5.0
        )
    """
    analyzer = DistortionAnalyzer()
    analyzer.load_lens(lens_path)
    
    grids = analyzer.analyze_zoom_range(
        zoom_positions=zoom_positions,
        x_fov=x_fov,
        y_fov=y_fov,
        num_lines=num_lines
    )
    
    # 绘制所有网格
    fig, ax = analyzer.plot_multi_grids(
        grids,
        title=f"Distortion Grids - {len(zoom_positions)} Zoom Positions"
    )
    
    if output_dir:
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        fig.savefig(Path(output_dir) / "all_grids.png", 
                   dpi=150, bbox_inches='tight')
    
    plt.show()
    return grids


if __name__ == "__main__":
    # 示例用法
    print("DistortionAnalyzer 模块")
    print("=" * 50)
    print("使用示例:")
    print()
    print("from distortion_analyzer import DistortionAnalyzer")
    print()
    print("analyzer = DistortionAnalyzer()")
    print("analyzer.load_lens(r'D:\\\\...\\\\lens.seq')")
    print("grid = analyzer.get_distortion_grid(zoom_pos=1)")
    print("analyzer.plot_grid(grid)")
