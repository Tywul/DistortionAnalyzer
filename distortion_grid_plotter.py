"""
distortion_grid_plotter.py — 绘制畸变网格并分析 Pupil Swim

利用 CODE V 的 DIST 宏获取畸变网格数据，然后：
    1. 绘制 Z3 和 Z4 的畸变网格在同一张图上
    2. 计算并绘制两个网格对应顶点之间的距离（Pupil Swim）
"""

import sys
import os
import re
import math
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch

# 路径设置
WORKDIR = r"d:\BaiduSyncdisk\My Optics\OpticsClaw"
SEQ_PATH = r"D:\BaiduSyncdisk\My Optics\Pancake\VR132P\VR132090-0518\vr132090_v4.seq"  # 更新为当前镜头
# SEQ_PATH = r"D:\BaiduSyncdisk\My Optics\Pancake\VR132P\VR132090-0422.seq"
# SEQ_PATH = r"D:\BaiduSyncdisk\My Optics\Pancake\VR132P\VR132090_0409_report\VR132090_0409_jiaping.seq"

# 参数设置
X_SEMI_FOV = 40  # X半视场 (度)
Y_SEMI_FOV = 0  # Y半视场 (度)
NUM_LINES = 21       # 网格线数量

# 12个变焦位置：
# Z1-Z3: RGB @ 26.565° FOV
# Z4-Z6: RGB @ 26.565° FOV + 3mm偏移
# Z7-Z9: RGB @ 35.265° FOV
# Z10-Z12: RGB @ 35.265° FOV + 3mm偏移
ZOOM_POSITIONS = list(range(1, 13))  # 1-12

# 颜色设置 - RGB对应
# Z1,Z4,Z7,Z10 = Red
# Z2,Z5,Z8,Z11 = Green
# Z3,Z6,Z9,Z12 = Blue
ZOOM_COLORS = {
    # Red通道
    1: 'red', 4: 'red', 7: 'red', 10: 'red',
    # Green通道
    2: 'green', 5: 'green', 8: 'green', 11: 'green',
    # Blue通道
    3: 'blue', 6: 'blue', 9: 'blue', 12: 'blue'
}

# 变焦分组 - 按通道
RED_ZOOMS = [1, 4, 7, 10]
GREEN_ZOOMS = [2, 5, 8, 11]
BLUE_ZOOMS = [3, 6, 9, 12]

# 变焦分组 - 按FOV和偏移
FOV_26_NO_OFFSET = [1, 2, 3]      # Z1-Z3
FOV_26_WITH_OFFSET = [4, 5, 6]    # Z4-Z6
FOV_35_NO_OFFSET = [7, 8, 9]      # Z7-Z9
FOV_35_WITH_OFFSET = [10, 11, 12] # Z10-Z12

try:
    import win32com.client
    _HAS_WIN32 = True
except ImportError:
    _HAS_WIN32 = False
    print("警告: 未安装 pywin32")

_cv = None

def get_cv():
    """获取 CODE V COM 接口"""
    global _cv
    if _cv is None:
        if not _HAS_WIN32:
            raise RuntimeError("需要 pywin32: pip install pywin32")
        _cv = win32com.client.Dispatch("CODEV.Command")
        try:
            _cv.StartCodeV()
        except Exception:
            pass
        _cv.Command(f'CD "{WORKDIR}"')
    return _cv

def cv_cmd(c):
    """执行 CODE V 命令"""
    return get_cv().Command(c)

def load_seq(path):
    """加载 SEQ 文件"""
    cv_cmd(f'IN "{path}"')
    print(f"已加载: {path}")

def run_dist_macro(zoom_pos, x_fov, y_fov, num_lines=21):
    """
    运行 dist_real_pro.seq 宏获取畸变网格数据
    
    宏参数格式: RUN "path" x_fov y_fov panel_width panel_height filename color num_lines zoom list_flag
    - #1: X FOV semi-field (35.265)
    - #2: Y FOV semi-field (35.265)
    - #3: Display panel semi-width (11.904)
    - #4: Display panel semi-height (11.904)
    - #5: Filename ("")
    - #6: Color ("RED")
    - #7: Number of grid lines (21)
    - #8: Zoom position (3 or 4)
    - #9: List flag ("Yes")
    
    返回: (paraxial_grid, actual_grid) 两个网格的坐标数组
          每个网格是 shape=(num_lines, num_lines, 2) 的数组，存储 (x, y) 坐标
    """
    import time
    
    # 创建临时文件名
    temp_file = os.path.join(WORKDIR, f"dist_z{zoom_pos}_{int(time.time())}.txt")
    
    # 运行宏，将输出重定向到文件
    # 参数: x_fov, y_fov, panel_width, panel_height, filename, color, num_lines, zoom, list_flag
    cv_cmd(f"OUT '{temp_file}'")
    cmd = f'RUN "D:\\BaiduSyncdisk\\My Optics\\Macros\\dist_real_pro.seq" {x_fov} {y_fov} 11.904 11.904 "" "RED" {num_lines} {zoom_pos} "Yes"'
    cv_cmd(cmd)
    cv_cmd("OUT")  # 恢复输出到控制台
    
    # 读取输出文件
    result = ""
    max_retries = 10
    for retry in range(max_retries):
        try:
            with open(temp_file, 'r', encoding='utf-8', errors='replace') as f:
                result = f.read()
            break
        except FileNotFoundError:
            time.sleep(0.1)
    
    # 删除临时文件
    try:
        os.remove(temp_file)
    except:
        pass
    
    print(f"\n=== ZOOM {zoom_pos} DIST 输出 (前3000字符) ===")
    print(result[:3000] if len(result) > 3000 else result)
    
    # 解析输出中的网格数据
    # 数据格式: "Rel X Fld  Rel Y Fld      Parax X      Parax Y       Real X       Real Y    Rad Dist%    Tan Dist%"
    paraxial_grid = np.zeros((num_lines, num_lines, 2))
    actual_grid = np.zeros((num_lines, num_lines, 2))
    
    lines = result.split('\n')
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
        # 格式: " -1.00     1.00      0.123456    0.234567    0.345678    0.456789     1.23      0.45"
        # 或者如果有光线失败: " -1.00     1.00      0.123456    0.234567     Chief Ray Failure"
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
                # rel_x 范围 -1 到 +1，对应列 j
                # rel_y 范围 -1 到 +1（但DIST宏中是 1 - 2*(i-1)/(num-1)，所以从上到下是 1 到 -1）
                j = int(round((rel_x + 1) / 2 * (num_lines - 1)))
                i = int(round((1 - rel_y) / 2 * (num_lines - 1)))
                
                if 0 <= i < num_lines and 0 <= j < num_lines:
                    paraxial_grid[i, j] = [parax_x, parax_y]
                    actual_grid[i, j] = [real_x, real_y]
            except (ValueError, IndexError):
                continue
    
    return paraxial_grid, actual_grid

def plot_all_zoom_grids(grids_dict, num_lines=21, output_path=None):
    """
    绘制所有变焦位置的畸变网格在同一张图上
    
    grids_dict: dict, key=zoom_pos, value=grid array shape=(num_lines, num_lines, 2)
    """
    fig, ax = plt.subplots(figsize=(12, 12))
    
    # 绘制每个变焦位置的网格
    for zoom_pos, grid in grids_dict.items():
        color = ZOOM_COLORS.get(zoom_pos, 'gray')
        label = f'Z{zoom_pos}'
        plot_single_grid(ax, grid, color, label, num_lines)
    
    # 设置图形属性
    ax.set_aspect('equal')
    ax.set_xlabel('X (mm)', fontsize=12)
    ax.set_ylabel('Y (mm)', fontsize=12)
    ax.set_title(f'All Zoom Positions Distortion Grid\nX/Y Semi-FOV = {X_SEMI_FOV}°, Grid = {num_lines}x{num_lines}', fontsize=14)
    ax.legend(loc='upper right', fontsize=10)
    ax.grid(True, alpha=0.3)
    
    plt.tight_layout()
    
    if output_path:
        plt.savefig(output_path, dpi=150, bbox_inches='tight')
        print(f"\n所有变焦位置畸变网格图已保存: {output_path}")
    
    return fig, ax

def remove_outliers(mag_flat, method='iqr', factor=1.5):
    """
    检测并标记位移量中的奇异值（异常点）。

    method='iqr': 四分位距法 — 超出 [Q1-factor*IQR, Q3+factor*IQR] 的为奇异值
    method='zscore': 标准差法 — |z| > factor（默认3σ）的为奇异值
    返回: (mask, n_removed, threshold_lo, threshold_hi)
           mask=True 表示正常点，mask=False 表示奇异值（需剔除）
    """
    mag = mag_flat.copy()
    q1 = np.percentile(mag, 25)
    q3 = np.percentile(mag, 75)
    iqr = q3 - q1

    if method == 'iqr':
        lo = q1 - factor * iqr
        hi = q3 + factor * iqr
    elif method == 'zscore':
        mean = np.mean(mag)
        std = np.std(mag)
        lo = mean - factor * std
        hi = mean + factor * std
    else:
        raise ValueError(f"未知方法: {method}")

    mask = (mag >= lo) & (mag <= hi)
    n_removed = int(np.sum(~mask))
    return mask, n_removed, lo, hi


def plot_distortion_grids(grid_ref, grid_compare, num_lines=21, output_path=None, 
                          label_ref='Reference', label_compare='Compare',
                          color_ref='blue', color_compare='red',
                          title_suffix='', ax=None):
    """
    绘制两个畸变网格在同一张图上，带偏移矢量
    
    grid_ref, grid_compare: shape=(num_lines, num_lines, 2) 的数组
    ax: 如果提供，则在指定ax上绘制；否则创建新图
    """
    if ax is None:
        fig, ax = plt.subplots(figsize=(10, 10))
    else:
        fig = ax.figure
    
    # 计算位移
    displacement = grid_compare - grid_ref
    displacement_magnitude = np.sqrt(displacement[:, :, 0]**2 + displacement[:, :, 1]**2)
    
    # 绘制参考网格
    plot_single_grid(ax, grid_ref, color_ref, label_ref, num_lines)
    
    # 绘制对比网格
    plot_single_grid(ax, grid_compare, color_compare, label_compare, num_lines)
    
    # 在每个顶点处绘制偏移矢量（短线段）
    X = grid_ref[:, :, 0]
    Y = grid_ref[:, :, 1]
    U = displacement[:, :, 0]
    V = displacement[:, :, 1]
    
    # 使用quiver绘制偏移矢量，用箭头长度表示位移大小
    scale_factor = 0.1  # 放大倍数
    
    # 使用实际U,V分量，箭头长度与位移大小成正比
    q = ax.quiver(X, Y, U, V,
                  scale=scale_factor, scale_units='xy', angles='xy',
                  color='black', width=0.002, headwidth=4, headlength=5, 
                  headaxislength=4, minshaft=1, minlength=0)
    
    # 添加图例说明比例
    ax.quiverkey(q, X=0.85, Y=1.02, U=0.05, label='0.05 mm', labelpos='E', fontproperties={'size': 9})
    
    # 设置图形属性
    ax.set_aspect('equal')
    ax.set_xlabel('X (mm)', fontsize=12)
    ax.set_ylabel('Y (mm)', fontsize=12)
    title = f'Distortion Grid Comparison\n{title_suffix}, Grid = {num_lines}x{num_lines}'
    ax.set_title(title, fontsize=14)
    ax.legend(loc='upper right', fontsize=10)
    ax.grid(True, alpha=0.3)
    
    if ax is None:
        plt.tight_layout()
    
    if output_path and ax is None:
        plt.savefig(output_path, dpi=150, bbox_inches='tight')
        print(f"\n畸变网格对比图已保存: {output_path}")
    
    return fig, ax

def plot_rgb_distortion_comparison(grids_dict, fov_26, fov_35, num_lines=21, output_path=None):
    """
    图1：两个子图，分别是Z1-Z3和Z7-Z9的RGB畸变网格
    体现系统的畸变和色差
    """
    fig, axes = plt.subplots(1, 2, figsize=(16, 8))
    
    # 左图：Z1-Z3 (RGB @ 26.565° FOV, 0mm offset)
    ax1 = axes[0]
    for zoom_pos in [1, 2, 3]:
        if zoom_pos in grids_dict:
            color = ZOOM_COLORS[zoom_pos]
            channel = {1: 'R', 2: 'G', 3: 'B'}[zoom_pos]
            label = f'Z{zoom_pos} ({channel})'
            plot_single_grid(ax1, grids_dict[zoom_pos], color, label, num_lines)
    
    ax1.set_aspect('equal')
    ax1.set_xlabel('X (mm)', fontsize=12)
    ax1.set_ylabel('Y (mm)', fontsize=12)
    ax1.set_title(f'RGB Distortion Grid (Z1-Z3)\nFOV = {fov_26}°, 0mm offset', fontsize=14)
    ax1.legend(loc='upper right', fontsize=10)
    ax1.grid(True, alpha=0.3)
    
    # 右图：Z7-Z9 (RGB @ 35.265° FOV, 0mm offset)
    ax2 = axes[1]
    for zoom_pos in [7, 8, 9]:
        if zoom_pos in grids_dict:
            color = ZOOM_COLORS[zoom_pos]
            channel = {7: 'R', 8: 'G', 9: 'B'}[zoom_pos]
            label = f'Z{zoom_pos} ({channel})'
            plot_single_grid(ax2, grids_dict[zoom_pos], color, label, num_lines)
    
    ax2.set_aspect('equal')
    ax2.set_xlabel('X (mm)', fontsize=12)
    ax2.set_ylabel('Y (mm)', fontsize=12)
    ax2.set_title(f'RGB Distortion Grid (Z7-Z9)\nFOV = {fov_35}°, 0mm offset', fontsize=14)
    ax2.legend(loc='upper right', fontsize=10)
    ax2.grid(True, alpha=0.3)
    
    plt.tight_layout()
    
    if output_path:
        plt.savefig(output_path, dpi=150, bbox_inches='tight')
        print(f"\nRGB畸变网格对比图已保存: {output_path}")
    
    return fig, axes

def plot_green_channel_pupil_swim_grids(grids_dict, fov_26, fov_35, num_lines=21,
                                        output_path=None, outlier_method='iqr', outlier_factor=1.5):
    """
    图2：两个视场角下的G通道pupil swim网格对比（带偏移矢量）
    - Z2 vs Z5 (FOV=26.565°, 0mm vs 3mm偏移)
    - Z8 vs Z11 (FOV=35.265°, 0mm vs 3mm偏移)

    新增: 自动剔除位移量中的奇异值（边缘光线失败导致的异常大偏移）
    """
    fig, axes = plt.subplots(1, 2, figsize=(16, 8))

    # 左图：Z2 vs Z5 (FOV=26.565°)
    if 2 in grids_dict and 5 in grids_dict:
        ax1 = axes[0]
        # 绘制Z2 (参考) - 用深色
        plot_single_grid(ax1, grids_dict[2], 'darkblue', 'Z2 (G, 0mm)', num_lines)
        # 绘制Z5 (对比) - 用亮色，反差大
        plot_single_grid(ax1, grids_dict[5], 'orange', 'Z5 (G, 3mm)', num_lines)

        # 计算位移 + 奇异值剔除
        displacement = grids_dict[5] - grids_dict[2]
        disp_mag = np.sqrt(displacement[:, :, 0]**2 + displacement[:, :, 1]**2)
        mag_flat = disp_mag.flatten()
        mask, n_rm, lo, hi = remove_outliers(mag_flat, method=outlier_method, factor=outlier_factor)
        mask_2d = mask.reshape(num_lines, num_lines)
        print(f"\n[Z2 vs Z5] 剔除 {n_rm}/{len(mag_flat)} 个奇异点 "
              f"(阈值: {lo:.4f} ~ {hi:.4f} mm, 方法={outlier_method})")

        X = grids_dict[2][:, :, 0]
        Y = grids_dict[2][:, :, 1]
        U = displacement[:, :, 0].copy()
        V = displacement[:, :, 1].copy()
        # 奇异点置零（不画箭头）
        U[~mask_2d] = 0
        V[~mask_2d] = 0

        # 正常点的 quiver
        q = ax1.quiver(X, Y, U, V,
                       scale=0.1, scale_units='xy', angles='xy',
                       color='red', width=0.002, headwidth=4, headlength=5,
                       headaxislength=4, minshaft=1, minlength=0)
        ax1.quiverkey(q, X=0.85, Y=1.02, U=0.05, label='0.05 mm', labelpos='E', fontproperties={'size': 9})
        # 标记被剔除的奇异点
        if n_rm > 0:
            ax1.scatter(X[~mask_2d], Y[~mask_2d], c='red', s=80, marker='x',
                       linewidths=2, label=f'Outlier ({n_rm})', zorder=5)

        ax1.set_aspect('equal')
        ax1.set_xlabel('X (mm)', fontsize=12)
        ax1.set_ylabel('Y (mm)', fontsize=12)
        ax1.set_title(f'G-Channel Pupil Swim Grid (Z2 vs Z5)\nFOV = {fov_26}°, 0mm → 3mm offset', fontsize=14)
        ax1.legend(loc='upper right', fontsize=10)
        ax1.grid(True, alpha=0.3)

    # 右图：Z8 vs Z11 (FOV=35.265°)
    if 8 in grids_dict and 11 in grids_dict:
        ax2 = axes[1]
        plot_single_grid(ax2, grids_dict[8], 'darkblue', 'Z8 (G, 0mm)', num_lines)
        plot_single_grid(ax2, grids_dict[11], 'orange', 'Z11 (G, 3mm)', num_lines)

        # 计算位移 + 奇异值剔除
        displacement = grids_dict[11] - grids_dict[8]
        disp_mag = np.sqrt(displacement[:, :, 0]**2 + displacement[:, :, 1]**2)
        mag_flat = disp_mag.flatten()
        mask, n_rm, lo, hi = remove_outliers(mag_flat, method=outlier_method, factor=outlier_factor)
        mask_2d = mask.reshape(num_lines, num_lines)
        print(f"\n[Z8 vs Z11] 剔除 {n_rm}/{len(mag_flat)} 个奇异点 "
              f"(阈值: {lo:.4f} ~ {hi:.4f} mm, 方法={outlier_method})")

        X = grids_dict[8][:, :, 0]
        Y = grids_dict[8][:, :, 1]
        U = displacement[:, :, 0].copy()
        V = displacement[:, :, 1].copy()
        U[~mask_2d] = 0
        V[~mask_2d] = 0

        q = ax2.quiver(X, Y, U, V,
                       scale=0.1, scale_units='xy', angles='xy',
                       color='red', width=0.002, headwidth=4, headlength=5,
                       headaxislength=4, minshaft=1, minlength=0)
        ax2.quiverkey(q, X=0.85, Y=1.02, U=0.05, label='0.05 mm', labelpos='E', fontproperties={'size': 9})
        if n_rm > 0:
            ax2.scatter(X[~mask_2d], Y[~mask_2d], c='red', s=80, marker='x',
                       linewidths=2, label=f'Outlier ({n_rm})', zorder=5)

        ax2.set_aspect('equal')
        ax2.set_xlabel('X (mm)', fontsize=12)
        ax2.set_ylabel('Y (mm)', fontsize=12)
        ax2.set_title(f'G-Channel Pupil Swim Grid (Z8 vs Z11)\nFOV = {fov_35}°, 0mm → 3mm offset', fontsize=14)
        ax2.legend(loc='upper right', fontsize=10)
        ax2.grid(True, alpha=0.3)
    
    plt.tight_layout()
    
    if output_path:
        plt.savefig(output_path, dpi=150, bbox_inches='tight')
        print(f"\nG通道Pupil Swim网格对比图已保存: {output_path}")
    
    return fig, axes

def plot_single_grid(ax, grid, color, label, num_lines):
    """绘制单个畸变网格"""
    # 绘制水平线
    for i in range(num_lines):
        x_vals = grid[i, :, 0]
        y_vals = grid[i, :, 1]
        ax.plot(x_vals, y_vals, color=color, linewidth=1.0, alpha=0.7, 
                label=label if i == 0 else "")
    
    # 绘制垂直线
    for j in range(num_lines):
        x_vals = grid[:, j, 0]
        y_vals = grid[:, j, 1]
        ax.plot(x_vals, y_vals, color=color, linewidth=1.0, alpha=0.7)
    
    # 绘制网格点
    ax.scatter(grid[:, :, 0], grid[:, :, 1], c=color, s=10, alpha=0.5)

def plot_pupil_swim_heatmap(grid_ref, grid_compare, ax, title,
                             outlier_method='iqr', outlier_factor=1.5):
    """
    在指定的ax上绘制单个Pupil Swim热力图（含奇异值剔除）

    grid_ref, grid_compare: shape=(num_lines, num_lines, 2) 的数组
    ax: matplotlib axes对象
    title: 子图标题
    """
    from matplotlib.tri import Triangulation
    from matplotlib.tri import LinearTriInterpolator

    # 计算位移
    displacement = grid_compare - grid_ref
    displacement_magnitude = np.sqrt(displacement[:, :, 0]**2 + displacement[:, :, 1]**2)

    # 展平数组
    X = grid_ref[:, :, 0]
    Y = grid_ref[:, :, 1]
    x_flat = X.flatten()
    y_flat = Y.flatten()
    mag_flat = displacement_magnitude.flatten()

    # 奇异值剔除
    mask, n_rm, lo, hi = remove_outliers(mag_flat, method=outlier_method, factor=outlier_factor)
    print(f"  [{title}] 剔除 {n_rm}/{len(mag_flat)} 个奇异点 "
          f"(阈值: {lo:.4f} ~ {hi:.4f} mm)")

    # 只用正常点做插值
    x_clean = x_flat[mask]
    y_clean = y_flat[mask]
    mag_clean = mag_flat[mask]

    # 创建三角剖分（仅正常点）
    triang = Triangulation(x_clean, y_clean)

    # 使用线性插值创建平滑的热力图
    x_min, x_max = X.min(), X.max()
    y_min, y_max = Y.min(), Y.max()

    xi = np.linspace(x_min, x_max, 200)
    yi = np.linspace(y_min, y_max, 200)
    Xi, Yi = np.meshgrid(xi, yi)

    interpolator = LinearTriInterpolator(triang, mag_clean)
    Zi = interpolator(Xi, Yi)

    # 绘制热力图
    im = ax.pcolormesh(Xi, Yi, Zi, shading='gouraud', cmap='hot')
    plt.colorbar(im, ax=ax, label='Displacement (mm)')

    # 标记被剔除的奇异点位置
    if n_rm > 0:
        ax.scatter(x_flat[~mask], y_flat[~mask], c='cyan', s=30,
                  marker='x', linewidths=1.0, alpha=0.7, zorder=5,
                  label=f'Outlier ({n_rm})')

    ax.set_aspect('equal')
    ax.set_xlabel('X (mm)', fontsize=11)
    ax.set_ylabel('Y (mm)', fontsize=11)
    ax.set_title(title + f'\n(outliers removed: {n_rm})', fontsize=12)

    # 打印统计信息（仅正常点）
    mag_valid = mag_clean
    print(f"  有效数据 — 最大位移: {np.max(mag_valid):.4f} mm")
    print(f"  有效数据 — 平均位移: {np.mean(mag_valid):.4f} mm")
    print(f"  有效数据 — RMS 位移: {np.sqrt(np.mean(mag_valid**2)):.4f} mm")
    
    return displacement_magnitude

def plot_green_channel_pupil_swim(grids_dict, fov_26, fov_35, num_lines=21, output_path=None):
    """
    只基于G通道的变焦生成Pupil Swim热力图
    G通道pupil swim: 
    - Z2 vs Z5 (FOV=26.565°, 0mm vs 3mm偏移)
    - Z8 vs Z11 (FOV=35.265°, 0mm vs 3mm偏移)
    """
    fig, axes = plt.subplots(1, 2, figsize=(16, 7))
    
    # 左图：Z2 vs Z5 (FOV=26.565°, 同FOV不同偏移)
    if 2 in grids_dict and 5 in grids_dict:
        plot_pupil_swim_heatmap(grids_dict[2], grids_dict[5], axes[0], 
                                f'G-Channel: Z2 vs Z5 Pupil Swim\n(FOV={fov_26}°, 0mm→3mm offset)')
    
    # 右图：Z8 vs Z11 (FOV=35.265°, 同FOV不同偏移)
    if 8 in grids_dict and 11 in grids_dict:
        plot_pupil_swim_heatmap(grids_dict[8], grids_dict[11], axes[1], 
                                f'G-Channel: Z8 vs Z11 Pupil Swim\n(FOV={fov_35}°, 0mm→3mm offset)')
    
    plt.tight_layout()
    
    if output_path:
        plt.savefig(output_path, dpi=150, bbox_inches='tight')
        print(f"\nG通道Pupil Swim热力图已保存: {output_path}")
    
    return fig, axes

def main():
    """主函数 - 处理12个变焦位置 (4变焦 × 3颜色RGB)"""
    print("=" * 60)
    print("畸变网格绘制与 Pupil Swim 分析 (12 Zoom Positions)")
    print("=" * 60)
    
    if not _HAS_WIN32:
        print("错误: 需要安装 pywin32")
        return
    
    # 加载 SEQ 文件
    load_seq(SEQ_PATH)
    
    output_dir = os.path.dirname(SEQ_PATH)
    
    # ========== 获取所有12个变焦位置数据 ==========
    fov_26 = 40
    fov_35 = 40
    
    grids_dict = {}
    
    # Z1-Z3: RGB @ 26.565° FOV (0mm offset)
    print("\n" + "=" * 60)
    print("获取 Z1-Z3 数据 (RGB @ FOV=26.565°, 0mm offset)")
    print("=" * 60)
    for z in [1, 2, 3]:
        channel = {1: 'R', 2: 'G', 3: 'B'}[z]
        print(f"\n正在获取 Z{z} ({channel}) 畸变网格数据 (FOV={fov_26}°)...")
        _, grids_dict[z] = run_dist_macro(z, fov_26, 0, NUM_LINES)
    
    # Z4-Z6: RGB @ 26.565° FOV (3mm offset)
    print("\n" + "=" * 60)
    print("获取 Z4-Z6 数据 (RGB @ FOV=26.565°, 3mm offset)")
    print("=" * 60)
    for z in [4, 5, 6]:
        channel = {4: 'R', 5: 'G', 6: 'B'}[z]
        print(f"\n正在获取 Z{z} ({channel}) 畸变网格数据 (FOV={fov_26}°)...")
        _, grids_dict[z] = run_dist_macro(z, fov_26, 0, NUM_LINES)
    
    # Z7-Z9: RGB @ 35.265° FOV (0mm offset)
    print("\n" + "=" * 60)
    print("获取 Z7-Z9 数据 (RGB @ FOV=40°, 0mm offset)")
    print("=" * 60)
    for z in [7, 8, 9]:
        channel = {7: 'R', 8: 'G', 9: 'B'}[z]
        print(f"\n正在获取 Z{z} ({channel}) 畸变网格数据 (FOV={fov_35}°)...")
        _, grids_dict[z] = run_dist_macro(z, fov_35, 0, NUM_LINES)
    
    # Z10-Z12: RGB @ 35.265° FOV (3mm offset)
    print("\n" + "=" * 60)
    print("获取 Z10-Z12 数据 (RGB @ FOV=40°, 3mm offset)")
    print("=" * 60)
    for z in [10, 11, 12]:
        channel = {10: 'R', 11: 'G', 12: 'B'}[z]
        print(f"\n正在获取 Z{z} ({channel}) 畸变网格数据 (FOV={fov_35}°)...")
        _, grids_dict[z] = run_dist_macro(z, fov_35, 0, NUM_LINES)
    
    # ========== 图1：RGB畸变网格对比 (Z1-Z3 和 Z7-Z9) ==========
    print("\n" + "=" * 60)
    print("图1：绘制RGB畸变网格对比 (Z1-Z3 和 Z7-Z9)")
    print("=" * 60)
    
    print("\n正在绘制RGB畸变网格对比图...")
    fig1, _ = plot_rgb_distortion_comparison(grids_dict, fov_26, fov_35, NUM_LINES,
                                              os.path.join(output_dir, "fig1_rgb_distortion_comparison.png"))
    
    # ========== 图2：G通道Pupil Swim网格对比 ==========
    print("\n" + "=" * 60)
    print("图2：绘制G通道Pupil Swim网格对比")
    print("=" * 60)
    
    print("\n正在绘制G通道Pupil Swim网格对比图...")
    fig2, _ = plot_green_channel_pupil_swim_grids(grids_dict, fov_26, fov_35, NUM_LINES,
                                                   os.path.join(output_dir, "fig2_green_pupil_swim_grids.png"))
    
    # ========== 图3：G通道Pupil Swim热力图 ==========
    print("\n" + "=" * 60)
    print("图3：绘制G通道Pupil Swim热力图")
    print("=" * 60)
    
    print("\n正在绘制G通道Pupil Swim热力图...")
    fig3, _ = plot_green_channel_pupil_swim(grids_dict, fov_26, fov_35, NUM_LINES,
                                             os.path.join(output_dir, "fig3_green_pupil_swim_heatmap.png"))
    
    print("\n" + "=" * 60)
    print("完成! 已生成三张图:")
    print("  图1: fig1_rgb_distortion_comparison.png")
    print("  图2: fig2_green_pupil_swim_grids.png")
    print("  图3: fig3_green_pupil_swim_heatmap.png")
    print("=" * 60)
    
    # 显示图形
    plt.show()

if __name__ == "__main__":
    main()
