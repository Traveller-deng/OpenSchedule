# -*- mode: python ; coding: utf-8 -*-
# OpenSchedule 卸载器：onefile、纯标准库、无控制台。
# 由 build/package.py 统一构建并放进 OpenSchedule 主程序文件夹。

a = Analysis(
    ['app/uninstall.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'unittest', 'pydoc_data'],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    name='uninstall',
    icon='app-icon.ico',
    debug=False,
    strip=False,
    upx=False,
    console=False,
)
