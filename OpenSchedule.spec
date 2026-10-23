# -*- mode: python ; coding: utf-8 -*-
# OpenSchedule 打包配置
# 构建：pyinstaller --workpath release/work --distpath release/dist --noconfirm OpenSchedule.spec
# 产物：release/dist/OpenSchedule/OpenSchedule.exe（onedir，杀软误报率低、启动快）

a = Analysis(
    ['app/launcher.py'],
    pathex=['.', 'build'],           # 根目录（serve.py）+ build/（import build）
    binaries=[],
    datas=[
        ('frontend', 'frontend'),    # 页面模板与前端资源
        ('build/build.py', 'build'), # 现场构建逻辑
        ('examples', 'examples'),    # 首次运行播种用的示例数据
        ('app-icon.png', '.'),       # 托盘图标 + favicon 源
        ('app-icon.ico', '.'),       # exe 图标源（保留一份方便快捷方式引用）
    ],
    hiddenimports=['build'],
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
    [],
    exclude_binaries=True,
    name='OpenSchedule',
    icon='app-icon.ico',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,                       # UPX 压缩显著提高杀软误报率，关闭
    console=False,                   # 无控制台窗口
    disable_windowed_traceback=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name='OpenSchedule',
)
