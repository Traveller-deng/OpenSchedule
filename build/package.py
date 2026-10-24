#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""一条命令出完整发布包：build/package.py

流程：
  1. PyInstaller onedir 构建 OpenSchedule.exe（OpenSchedule.spec）
  2. PyInstaller onefile 构建 uninstall.exe（uninstall.spec）
  3. uninstall.exe 放进 OpenSchedule 程序文件夹
  4. 整个文件夹压成 release/OpenSchedule-<版本>-win64.zip

产物结构：
  release/dist/OpenSchedule/OpenSchedule.exe   双击即用
  release/dist/OpenSchedule/uninstall.exe     卸载器
"""
import os
import shutil
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORK = os.path.join(ROOT, "release", "work")
DIST = os.path.join(ROOT, "release", "dist")


def app_version():
    sys.path.insert(0, ROOT)
    import serve
    return serve.APP_VERSION


def main():
    try:
        import PyInstaller.__main__ as pyi
    except ImportError:
        raise SystemExit("请先安装：pip install pyinstaller pystray pillow")

    pyi.run(["--workpath", os.path.join(WORK, "app"),
             "--distpath", DIST, "--noconfirm", "OpenSchedule.spec"])
    pyi.run(["--workpath", os.path.join(WORK, "uninstall"),
             "--distpath", os.path.join(ROOT, "release", "uninstall"),
             "--noconfirm", "uninstall.spec"])

    app_dir = os.path.join(DIST, "OpenSchedule")
    shutil.copy2(os.path.join(ROOT, "release", "uninstall", "uninstall.exe"),
                 os.path.join(app_dir, "uninstall.exe"))

    ver = app_version()
    zip_path = os.path.join(ROOT, "release", "OpenSchedule-%s-win64.zip" % ver)
    if os.path.exists(zip_path):
        os.remove(zip_path)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for base, _dirs, files in os.walk(app_dir):
            for name in files:
                full = os.path.join(base, name)
                z.write(full, os.path.relpath(full, DIST))
    print("written:", zip_path, os.path.getsize(zip_path), "bytes")
    print("folder :", app_dir)


if __name__ == "__main__":
    main()
