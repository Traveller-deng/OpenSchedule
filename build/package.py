#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""一条命令出完整发布包：build/package.py

流程：
  1. PyInstaller onedir 构建 OpenSchedule.exe（OpenSchedule.spec）
  2. PyInstaller onefile 构建 uninstall.exe（uninstall.spec）
  3. uninstall.exe + 使用说明.txt 放进 OpenSchedule 程序文件夹
  4. 整个文件夹压成 release/OpenSchedule-<版本>-win64.zip

产物结构：
  release/dist/OpenSchedule/OpenSchedule.exe   双击即用
  release/dist/OpenSchedule/schedule.exe       命令行（可选）
  release/dist/OpenSchedule/uninstall.exe      卸载器
  release/dist/OpenSchedule/使用说明.txt        给拿到包的人看的
"""
import os
import shutil
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORK = os.path.join(ROOT, "release", "work")
DIST = os.path.join(ROOT, "release", "dist")

README = """OpenSchedule · 每日安排  v%(ver)s
====================================

怎么用
------
1. 把整个文件夹解压出来（别只把 exe 拖走，页面资源在 _internal 里）
2. 双击 OpenSchedule.exe —— 自动起本地服务并打开浏览器页面
3. 以后再双击不会起第二个服务，直接把浏览器带到已打开的页面
4. 退出：右下角系统托盘图标（打开页面 / 数据文件夹 / 重建页面 / 卸载 / 退出）

页面三个区
----------
左栏  月历：点日期跳转，回「今」回今天，左边箭头可以收起成竖排日号
中间  当天安排：「今日主要任务」勾一勾就完成，下面是具体时间块
右栏  DDL 看板（有截止日的）／ 任务安排（没有 DDL、靠自己推进的）／ 常用入口

数据在哪
--------
%%LOCALAPPDATA%%\\OpenSchedule\\data\\
  todo.md       DDL 看板（- [ ] 10.25 论文改稿完成）
  tasks.md      任务安排（- [ ] 整理导师清单，## 开头是分组）
  schedule.md   每天的时间表与主要任务
  links.json    资料路径 / 常用入口 / 左栏入口
  edits.json    页面上做过的增改
  draft.md      草稿
全是纯文本，记事本或 Typora 直接改；改完页面几秒内自己跟上。
想放别处也行：在 exe 旁边建一个 data\\ 文件夹，就变成便携模式。

命令行（可选，需要的话）
------------------------
schedule.exe ddl list                 看 DDL
schedule.exe plan list                看任务安排
schedule.exe day show                 看今天
schedule.exe plan add 整理导师清单 --group 套磁
schedule.exe --help                   全部命令

隐私
----
全程离线运行，只监听 127.0.0.1，不联网、不写注册表、不碰防火墙。
只有你在左下角聊天框里配了模型 API Key 并主动发问时，才会请求那个接口。

卸载
----
双击 uninstall.exe：停掉服务，并可选删掉个人数据目录；不写注册表。
"""


def app_version():
    sys.path.insert(0, ROOT)
    import serve
    return serve.APP_VERSION


def write_readme(app_dir, ver):
    """给拿到包的人看的一页说明（纯文本，Windows 记事本直接能开）。"""
    path = os.path.join(app_dir, "使用说明.txt")
    with open(path, "w", encoding="utf-8-sig", newline="\r\n") as f:
        f.write(README % {"ver": ver})
    return path


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
    write_readme(app_dir, ver)
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
