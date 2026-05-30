# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['D:\\BaiduSyncdisk\\My Optics\\OpticsClaw\\DistortionAnalyzer\\distortion_gui_app.py'],
    pathex=[],
    binaries=[],
    datas=[('dist_real_pro.seq', '.'), ('dist_polar_pro.seq', '.')],
    hiddenimports=['win32com.client', 'win32com', 'pythoncom', 'matplotlib.backends.backend_qt5agg', 'PIL'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['IPython', 'jupyter', 'notebook', 'tkinter', 'PySide2', 'PySide6', 'scipy', 'pandas', 'PIL._avif', 'asyncio', 'test', 'setuptools', 'lib2to3', 'xmlrpc', 'http.server', 'matplotlib.tests', 'matplotlib.testing', 'numpy.tests', 'numpy.testing', 'matplotlib.backends.backend_tkagg', 'matplotlib.backends.backend_tkcairo', 'matplotlib.backends.backend_wx', 'matplotlib.backends.backend_wxagg', 'matplotlib.backends.backend_gtk3agg', 'matplotlib.backends.backend_gtk3cairo', 'matplotlib.backends.backend_gtk4agg', 'matplotlib.backends.backend_gtk4cairo', 'matplotlib.backends.backend_cairo', 'matplotlib.backends.backend_webagg', 'matplotlib.backends.backend_nbagg', 'matplotlib.backends.backend_svg', 'matplotlib.backends.backend_pgf', 'matplotlib.backends.backend_ps', 'matplotlib.backends.backend_pdf', 'matplotlib.backends.backend_template'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='DistortionAnalyzer',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['D:\\BaiduSyncdisk\\My Optics\\OpticsClaw\\DistortionAnalyzer\\icon.ico'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='DistortionAnalyzer',
)
