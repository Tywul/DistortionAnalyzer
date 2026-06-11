"""
Build Distortion Analyzer V1.2 into standalone .exe
Requires: pyinstaller, PyQt5, matplotlib, numpy, pywin32
"""
import os
import shutil
import subprocess
import sys
import argparse
from pathlib import Path

ROOT = Path(__file__).parent
DIST_DIR = ROOT / "dist" / "DistortionAnalyzer"

def clean() -> None:
    """Remove previous build artifacts."""
    for d in ["build", "dist", "__pycache__"]:
        p = ROOT / d
        if p.exists():
            shutil.rmtree(p)
    for f in ROOT.iterdir():
        if f.suffix == ".spec":
            f.unlink()

def cleanup_dist() -> None:
    """Post-build: remove unnecessary files to reduce package size."""
    internal = DIST_DIR / "_internal"
    removed = []

    # Patterns of files/dirs to remove (safe — not used by our app)
    patterns = [
        # AVIF image plugin (Pillow) — not needed
        "_avif",
        # Qt Quick / QML — not used by our app
        "Qt5Quick",
        "Qt5Qml",
        "Qt5QmlModels",
        "Qt5QmlWorkerScript",
        # Qt Network — not used
        "Qt5Network",
        # OpenSSL — not used (no web requests from app)
        "libssl-3-x64",
        "libcrypto-3-x64",
        # libEGL (bundled by Qt, not needed for our widget-only use)
        "libEGL",
    ]

    total_saved = 0
    for fp in internal.rglob("*"):
        if fp.is_file():
            f = fp.name
            for pat in patterns:
                if f.lower().startswith(pat.lower()):
                    try:
                        sz = fp.stat().st_size
                        fp.unlink()
                        total_saved += sz
                        removed.append(f)
                    except OSError:
                        pass

    if removed:
        print(f"[CLEANUP] Removed {len(removed)} files, saved ~{total_saved//1024//1024} MB")
    else:
        print("[CLEANUP] Nothing to clean up")

def build(skip_cleanup: bool = False) -> None:
    clean()

    data_files = [
        f"dist_real_pro.seq{os.pathsep}.",
        f"dist_polar_pro.seq{os.pathsep}.",
        f"displays.json{os.pathsep}.",
    ]

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onedir",
        "--windowed",
        "--name", "DistortionAnalyzer",
        "--icon", str(ROOT / "icon.ico"),
        "--clean",
        "--noconfirm",
        # Hidden imports
        "--hidden-import", "win32com.client",
        "--hidden-import", "win32com",
        "--hidden-import", "pythoncom",
        "--hidden-import", "matplotlib.backends.backend_qt5agg",
        "--hidden-import", "PIL",
        # Exclude heavy / unused modules
        "--exclude-module", "IPython",
        "--exclude-module", "jupyter",
        "--exclude-module", "notebook",
        "--exclude-module", "tkinter",
        "--exclude-module", "PySide2",
        "--exclude-module", "PySide6",
        "--exclude-module", "scipy",
        "--exclude-module", "pandas",
        "--exclude-module", "PIL._avif",
        "--exclude-module", "asyncio",
        "--exclude-module", "test",
        "--exclude-module", "setuptools",
        "--exclude-module", "lib2to3",
        "--exclude-module", "xmlrpc",
        "--exclude-module", "http.server",
        # Exclude matplotlib test data & unused backends
        "--exclude-module", "matplotlib.tests",
        "--exclude-module", "matplotlib.testing",
        "--exclude-module", "numpy.tests",
        "--exclude-module", "numpy.testing",
        # Exclude Tk backend (PyQt5 is our backend)
        "--exclude-module", "matplotlib.backends.backend_tkagg",
        "--exclude-module", "matplotlib.backends.backend_tkcairo",
        "--exclude-module", "matplotlib.backends.backend_wx",
        "--exclude-module", "matplotlib.backends.backend_wxagg",
        "--exclude-module", "matplotlib.backends.backend_gtk3agg",
        "--exclude-module", "matplotlib.backends.backend_gtk3cairo",
        "--exclude-module", "matplotlib.backends.backend_gtk4agg",
        "--exclude-module", "matplotlib.backends.backend_gtk4cairo",
        "--exclude-module", "matplotlib.backends.backend_cairo",
        "--exclude-module", "matplotlib.backends.backend_webagg",
        "--exclude-module", "matplotlib.backends.backend_nbagg",
        "--exclude-module", "matplotlib.backends.backend_svg",
        "--exclude-module", "matplotlib.backends.backend_pgf",
        "--exclude-module", "matplotlib.backends.backend_ps",
        "--exclude-module", "matplotlib.backends.backend_pdf",
        "--exclude-module", "matplotlib.backends.backend_template",
    ]

    for df in data_files:
        cmd.extend(["--add-data", df])

    cmd.append(str(ROOT / "distortion_gui_app.py"))

    print(f"[BUILD] Running PyInstaller...")
    result = subprocess.run(cmd, cwd=ROOT)
    if result.returncode != 0:
        print("[BUILD] FAILED")
        sys.exit(1)

    # Copy macro files and icon into dist root as fallback
    for filename in ["dist_real_pro.seq", "dist_polar_pro.seq", "displays.json", "icon.ico"]:
        src = ROOT / filename
        dst = DIST_DIR / filename
        if src.exists() and not dst.exists():
            shutil.copy2(src, dst)

    # Post-build cleanup
    if not skip_cleanup:
        cleanup_dist()

    # Report
    total_mb = sum(
        fp.stat().st_size
        for fp in DIST_DIR.rglob("*")
        if fp.is_file()
    ) / (1024 * 1024)

    print(f"[BUILD] Done → {DIST_DIR}")
    print(f"[BUILD] Total size: {total_mb:.0f} MB")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build Distortion Analyzer standalone executable")
    parser.add_argument("--clean", action="store_true", help="Clean before building")
    parser.add_argument("--no-cleanup", action="store_true", help="Skip post-build cleanup")
    args, _unknown = parser.parse_known_args()

    if args.clean:
        clean()

    build(skip_cleanup=args.no_cleanup)
