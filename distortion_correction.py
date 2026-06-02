# -*- coding: utf-8 -*-
"""
distortion_correction.py
畸变校正计算核心 — 多项式拟合 + svrapi_lens CSV 导出

移植自 MATLAB formatdist.m，已用 130072base 参考数据验证（误差 < 0.004%）。
纯 numpy 实现，无 CODE V 依赖。
"""

import json
import traceback
from pathlib import Path
from typing import Optional

import numpy as np

# ============================================================
#  数据解析
# ============================================================

def parse_dist_txt(path: str) -> np.ndarray:
    """
    解析 dist_real_pro 的输出文件（r.txt / g.txt / b.txt）。
    跳过头行和标题行，取第3~6列（Parax_X/Y Real_X/Y，单位 mm）。
    返回 (N, 4) array。
    """
    data = []
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"File not found: {path}")
    for line in p.read_text(errors='replace').splitlines():
        line = line.strip()
        if not line or line.startswith('Rel'):
            continue
        parts = line.split()
        if len(parts) >= 6:
            try:
                data.append([float(parts[2]), float(parts[3]),
                             float(parts[4]), float(parts[5])])
            except (ValueError, IndexError):
                continue
    return np.array(data, dtype=float)


# ============================================================
#  多项式畸变拟合（复刻 MATLAB formatdist.m）
# ============================================================

def fit_distortion(disdata: np.ndarray,
                   pixelsize: float,
                   Width0: int, Height0: int,
                   Width: int, Height: int,
                   NumCols: int, NumRows: int,
                   OffsetXPixel: float, OffsetYPixel: float,
                   sym_h: bool = True, sym_v: bool = False):
    """
    6阶多项式畸变拟合（3 个颜色通道），支持对称性控制。

    参数
    ----
    sym_h : 水平对称 → Y方向拟合只用偶次阶（默认 True）
    sym_v : 竖直对称 → X方向拟合只用偶次阶（默认 False）
    """
    results_x = []
    results_y = []

    OffsetX_px = OffsetXPixel
    OffsetY_px = OffsetYPixel

    for n in range(3):
        Para_X_px = disdata[:, 0, n] / pixelsize
        Para_Y_px = disdata[:, 1, n] / pixelsize
        Real_X_px = disdata[:, 2, n] / pixelsize
        Real_Y_px = disdata[:, 3, n] / pixelsize

        n_pts = int(round(len(Para_X_px) ** 0.5))
        if n_pts * n_pts != len(Para_X_px):
            raise ValueError(f"通道 {n}: 数据点数 {len(Para_X_px)} 不是完全平方数")

        PX = Para_X_px.reshape(n_pts, n_pts)
        PY = Para_Y_px.reshape(n_pts, n_pts)
        RX = Real_X_px.reshape(n_pts, n_pts)
        RY = Real_Y_px.reshape(n_pts, n_pts)
        nrow, ncol = RX.shape

        # ── X方向：每列6阶拟合 (Para_Y → Real_X) ──
        ax = np.empty(ncol); bx = np.empty(ncol); cx = np.empty(ncol); dx = np.empty(ncol)
        a1x = np.empty(ncol); b1x = np.empty(ncol); c1x = np.empty(ncol)
        for i in range(ncol):
            abcd = np.polyfit(PY[:, i], RX[:, i], 6)
            ax[i], bx[i], cx[i], dx[i] = abcd[0], abcd[2], abcd[4], abcd[6]
            a1x[i], b1x[i], c1x[i] = abcd[1], abcd[3], abcd[5]
        if sym_v:
            a1x[:] = 0; b1x[:] = 0; c1x[:] = 0

        # ── Y方向：每行6阶拟合 ──
        ay = np.empty(nrow); by = np.empty(nrow); cy = np.empty(nrow); dy = np.empty(nrow)
        a1y = np.empty(nrow); b1y = np.empty(nrow); c1y = np.empty(nrow)
        for j in range(nrow):
            abcd = np.polyfit(PX[j, :], RY[j, :], 6)
            ay[j], by[j], cy[j], dy[j] = abcd[0], abcd[2], abcd[4], abcd[6]
            a1y[j], b1y[j], c1y[j] = abcd[1], abcd[3], abcd[5]
        if sym_h:
            a1y[:] = 0; b1y[:] = 0; c1y[:] = 0

        # ── 元拟合 ──
        x_mid = PX[nrow // 2, :]
        y_mid = PY[:, ncol // 2]

        pax = np.polyfit(x_mid, ax, 5)
        pbx = np.polyfit(x_mid, bx, 5)
        pcx = np.polyfit(x_mid, cx, 5)
        pdx = np.polyfit(x_mid, dx, 5)

        pay = np.polyfit(y_mid, ay, 5)
        pby = np.polyfit(y_mid, by, 5)
        pcy = np.polyfit(y_mid, cy, 5)
        pdy = np.polyfit(y_mid, dy, 5)
        pa1y = np.polyfit(y_mid, a1y, 5) if not sym_h else None
        pb1y = np.polyfit(y_mid, b1y, 5) if not sym_h else None
        pc1y = np.polyfit(y_mid, c1y, 5) if not sym_h else None
        pa1x = np.polyfit(x_mid, a1x, 5) if not sym_v else None
        pb1x = np.polyfit(x_mid, b1x, 5) if not sym_v else None
        pc1x = np.polyfit(x_mid, c1x, 5) if not sym_v else None

        # ── 构建输出网格 ──
        para_xx, para_yy = np.meshgrid(
            np.linspace(-Width / 2, Width / 2, NumCols),
            np.linspace(Height / 2, -Height / 2, NumRows)
        )

        axx = np.polyval(pax, para_xx[0, :])
        bxx = np.polyval(pbx, para_xx[0, :])
        cxx = np.polyval(pcx, para_xx[0, :])
        dxx = np.polyval(pdx, para_xx[0, :])

        ayy = np.polyval(pay, para_yy[:, 0])
        byy = np.polyval(pby, para_yy[:, 0])
        cyy = np.polyval(pcy, para_yy[:, 0])
        dyy = np.polyval(pdy, para_yy[:, 0])

        real_xx = para_xx.copy()
        real_yy = para_yy.copy()

        if sym_v:
            xx_full = np.zeros((7, NumCols))
            xx_full[0], xx_full[2], xx_full[4], xx_full[6] = axx, bxx, cxx, dxx
        else:
            a1xx = np.polyval(pa1x, para_xx[0, :])
            b1xx = np.polyval(pb1x, para_xx[0, :])
            c1xx = np.polyval(pc1x, para_xx[0, :])
            xx_full = np.zeros((7, NumCols))
            xx_full[0], xx_full[1], xx_full[2] = axx, a1xx, bxx
            xx_full[3], xx_full[4], xx_full[5] = b1xx, cxx, c1xx
            xx_full[6] = dxx

        if sym_h:
            yy = np.column_stack([ayy, np.zeros(NumRows), byy, np.zeros(NumRows),
                                   cyy, np.zeros(NumRows), dyy])
        else:
            a1yy = np.polyval(pa1y, para_yy[:, 0])
            b1yy = np.polyval(pb1y, para_yy[:, 0])
            c1yy = np.polyval(pc1y, para_yy[:, 0])
            yy = np.column_stack([ayy, a1yy, byy, b1yy, cyy, c1yy, dyy])

        for i in range(NumCols):
            real_xx[:, i] = np.polyval(xx_full[:, i], para_yy[:, i]) + OffsetX_px

        for j in range(NumRows):
            real_yy[j, :] = np.polyval(yy[j, :], para_xx[j, :]) - OffsetY_px

        real_mat_x = np.flipud(real_xx)
        real_mat_y = np.flipud(real_yy)

        results_x.append(real_mat_x.ravel(order='F') * pixelsize)
        results_y.append(real_mat_y.ravel(order='F') * pixelsize)

    real_data_x = np.column_stack(results_x)
    real_data_y = np.column_stack(results_y)

    # ★ 参考网格：用 Width/Height（非 Width0/Height0）→ 匹配 MATLAB RefLoc
    para_xx_ref, para_yy_ref = np.meshgrid(
        np.linspace(-Width / 2, Width / 2, NumCols),
        np.linspace(Height / 2, -Height / 2, NumRows)
    )
    para_data_x = np.flipud(para_xx_ref).ravel(order='F') * pixelsize
    para_data_y = np.flipud(para_yy_ref).ravel(order='F') * pixelsize

    # ★ 索引：ravel('F') 匹配 MATLAB
    ix, iy = np.meshgrid(
        np.arange(-(NumCols - 1) // 2, (NumCols - 1) // 2 + 1),
        np.arange(-(NumRows - 1) // 2, (NumRows - 1) // 2 + 1)
    )
    index_x = ix.ravel(order='F')
    index_y = iy.ravel(order='F')

    return real_data_x, real_data_y, para_data_x, para_data_y, index_x, index_y


# ============================================================
#  CSV 导出
# ============================================================

def build_csv_content(SizeX: float, SizeY: float,
                      NumCols: int, NumRows: int, OffsetY: float,
                      index_x, index_y, para_data_x, para_data_y,
                      real_data_x, real_data_y) -> str:
    """按 svrapi_lens 格式生成 CSV 字符串"""
    lines = []
    lines.append("Version,1")
    lines.append("Distortion Method,0")
    lines.append(f"Width,{SizeX:.6g}")
    lines.append(f"Height,{SizeY:.6g}")
    lines.append(f"NumCols,{NumCols}")
    lines.append(f"NumRows,{NumRows}")
    lines.append("Center X,0")
    lines.append(f"Center Y,{-OffsetY:.6g}")
    for _ in range(5):
        lines.append(",")
    lines.append("IndexX,IndexY,RefLocX,RefLocY,R_DistX,R_DistY,G_DistX,G_DistY,B_DistX,B_DistY")
    for k in range(len(index_x)):
        lines.append(
            f"{index_x[k]},{index_y[k]},"
            f"{para_data_x[k]:.6g},{para_data_y[k]:.6g},"
            f"{real_data_x[k, 0]:.6g},{real_data_y[k, 0]:.6g},"
            f"{real_data_x[k, 1]:.6g},{real_data_y[k, 1]:.6g},"
            f"{real_data_x[k, 2]:.6g},{real_data_y[k, 2]:.6g}"
        )
    return "\n".join(lines)


# ============================================================
#  显示屏数据库加载
# ============================================================

def load_displays_db(json_path: str) -> list:
    """加载显示屏数据库 JSON"""
    try:
        return json.loads(Path(json_path).read_text(encoding='utf-8'))
    except Exception:
        return []
