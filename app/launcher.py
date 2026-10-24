#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""OpenSchedule 桌面启动器（PyInstaller 打包入口）。

双击 OpenSchedule.exe 后自动完成：
  1. 单实例检查——已在运行就把浏览器带到已有页面，不再起第二个服务
  2. 首次运行初始化——建数据目录、从内置 examples 播种、现场构建页面
     （绝不覆盖已有数据；数据变动或程序升级后自动重建）
  3. 启动本地服务（127.0.0.1，打包内置 Python 运行时，机器上什么都不用装）
  4. 打开默认浏览器进入页面；托盘常驻（打开页面 / 数据文件夹 / 重建页面 / 退出）

命令行：OpenSchedule.exe [--port N] [--data DIR] [--no-open] [--quit]
"""
import io
import json
import logging
import os
import shutil
import sys
import threading
import time
import webbrowser
from contextlib import redirect_stdout

# 源码运行时保证能 import 到仓库根目录的 serve.py（打包后 serve 已打进去，此路径不存在也无妨）
_DEV_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if not getattr(sys, "frozen", False) and os.path.exists(os.path.join(_DEV_ROOT, "serve.py")):
    if _DEV_ROOT not in sys.path:
        sys.path.insert(0, _DEV_ROOT)

APP_NAME = "OpenSchedule"
MUTEX_NAME = "Local\\OpenSchedule.SingleInstance"

log = logging.getLogger("openschedule")


# ---------------------------------------------------------------- 基础工具
def parse_args(argv):
    opts = {"port": None, "data": None, "no_open": False, "quit": False}
    i = 1
    while i < len(argv):
        a = argv[i]
        if a == "--port" and i + 1 < len(argv):
            opts["port"] = argv[i + 1]
            i += 2
        elif a == "--data" and i + 1 < len(argv):
            opts["data"] = argv[i + 1]
            i += 2
        elif a == "--no-open":
            opts["no_open"] = True
            i += 1
        elif a == "--quit":
            opts["quit"] = True
            i += 1
        else:
            i += 1
    return opts


def alert(msg):
    """无控制台环境下的报错弹窗。"""
    log.error(msg)
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(0, msg, APP_NAME, 0x10)
    except Exception:
        pass


def acquire_single_instance():
    """返回 (互斥句柄, 是否已有实例)。"""
    import ctypes
    k32 = ctypes.windll.kernel32
    handle = k32.CreateMutexW(None, False, MUTEX_NAME)
    already = (handle and k32.GetLastError() == 183)   # ERROR_ALREADY_EXISTS
    return handle, bool(already)


def read_state(base):
    try:
        with io.open(os.path.join(base, "state.json"), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def write_state(base, port):
    try:
        with io.open(os.path.join(base, "state.json"), "w", encoding="utf-8") as f:
            json.dump({"app": APP_NAME, "port": port, "pid": os.getpid(),
                       "started": time.strftime("%Y-%m-%d %H:%M:%S")}, f, ensure_ascii=False)
    except Exception:
        log.exception("写 state.json 失败")


def clear_state(base):
    try:
        os.remove(os.path.join(base, "state.json"))
    except OSError:
        pass


def setup_logging(base):
    logs = os.path.join(base, "logs")
    os.makedirs(logs, exist_ok=True)
    path = os.path.join(logs, "openschedule.log")
    try:
        if os.path.getsize(path) > 2 * 1024 * 1024:     # 超 2MB 清空重来
            os.remove(path)
    except OSError:
        pass
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.FileHandler(path, encoding="utf-8"),
                  logging.StreamHandler(sys.stderr)])
    return logs


# ---------------------------------------------------------------- 初始化与构建
def seed_data(examples_dir, data_dir):
    """首次运行：从内置示例播种数据文件。已存在的文件一律不动。"""
    os.makedirs(data_dir, exist_ok=True)
    for name in ("schedule.json", "todo.md", "links.json"):
        dst = os.path.join(data_dir, name)
        if os.path.exists(dst):
            continue
        src = os.path.join(examples_dir, name)
        if os.path.exists(src):
            shutil.copyfile(src, dst)
            log.info("播种 %s", name)


def page_is_stale(serve, html_path, version):
    """页面缺失 / 数据或程序更新过 → 需要重建。"""
    if not os.path.exists(html_path):
        return True
    html_mtime = os.path.getmtime(html_path)
    for name in ("schedule.md", "schedule.json", "todo.md", "links.json", "profile.json"):
        p = os.path.join(serve.DATA, name)
        if os.path.exists(p) and os.path.getmtime(p) > html_mtime:
            return True
    # 程序自身比页面新（升级 / 前端变化）→ 重建
    if getattr(sys, "frozen", False):
        refs = [sys.executable]
    else:
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        refs = [os.path.join(root, serve.RES, "frontend", "index.html"),
                os.path.join(root, serve.RES, "frontend", "assets", "app.js"),
                os.path.join(root, serve.RES, "frontend", "assets", "app.css"),
                os.path.join(root, serve.RES, "build", "build.py")]
    for p in refs:
        if os.path.exists(p) and os.path.getmtime(p) > html_mtime:
            return True
    state = read_state(os.path.dirname(serve.DATA.rstrip("\\/")))
    return state.get("built_version") != version


def build_page(serve, html_path):
    os.makedirs(serve.DIST, exist_ok=True)
    build_dir = os.path.join(serve.RES, "build")
    if build_dir not in sys.path:
        sys.path.insert(0, build_dir)
    import build as B
    buf = io.StringIO()
    with redirect_stdout(buf):
        B.build(profile="personal", out=html_path, data_dir=serve.DATA, root=serve.RES)
    for line in buf.getvalue().splitlines():
        if line.strip():
            log.info("build: %s", line.strip())


# ---------------------------------------------------------------- 托盘
def make_tray(serve, icon_path, url, on_rebuild, on_quit):
    """成功返回 pystray Icon（已在后台线程运行），失败返回 None。"""
    try:
        from pystray import Icon, Menu, MenuItem
        from PIL import Image
    except Exception:
        log.warning("pystray/PIL 不可用，托盘不显示（服务仍在后台运行）")
        return None

    def open_page(icon=None, item=None):
        webbrowser.open(url)

    def open_data(icon=None, item=None):
        serve.open_path(serve.DATA)

    items = [
        MenuItem("打开页面", open_page, default=True),
        MenuItem("数据文件夹", open_data),
        MenuItem("重建页面", lambda ic, it: on_rebuild()),
    ]
    uninstaller = os.path.join(os.path.dirname(os.path.abspath(sys.executable)),
                               "uninstall.exe")
    if getattr(sys, "frozen", False) and os.path.exists(uninstaller):
        items.append(Menu.SEPARATOR)
        items.append(MenuItem("卸载 OpenSchedule…",
                              lambda ic, it: os.startfile(uninstaller)))
    items.append(Menu.SEPARATOR)
    items.append(MenuItem("退出", lambda ic, it: on_quit()))

    icon = Icon(
        APP_NAME,
        Image.open(icon_path),
        APP_NAME,
        Menu(*items),
    )
    icon.run_detached()
    return icon


# ---------------------------------------------------------------- 主流程
def main():
    opts = parse_args(sys.argv)
    if opts["data"]:
        os.environ["SCHED_DATA"] = os.path.abspath(opts["data"])
    if opts["port"]:
        os.environ["SCHED_PORT"] = opts["port"]

    import serve          # 在设置好环境变量之后导入，路径/端口才正确

    base = os.path.dirname(serve.DATA.rstrip("\\/"))
    os.makedirs(base, exist_ok=True)
    setup_logging(base)
    log.info("启动：%s %s | frozen=%s data=%s", APP_NAME, serve.APP_VERSION,
             getattr(sys, "frozen", False), serve.DATA)

    handle, already = acquire_single_instance()

    if opts["quit"]:
        port = read_state(base).get("port") or serve.PORT
        try:
            port = int(port)
        except (TypeError, ValueError):
            port = serve.PORT
        if not 1 <= port <= 65535:
            port = serve.PORT
        # 固定回环地址 + 已校验的整数端口，只发给自己进程的关闭指令
        import http.client
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=3)
        try:
            conn.request("POST", "/api/shutdown", body=b"{}",
                         headers={"Content-Type": "application/json",
                                  "Origin": "http://127.0.0.1:%d/" % port})
            resp = conn.getresponse()
            resp.read()
            log.info("已请求退出 (port %s, status %s)", port, resp.status)
        except Exception as e:
            log.warning("退出请求失败：%s", e)
        finally:
            conn.close()
        return 0

    if already:
        # 已有实例：把浏览器带到它那里，然后退出
        port = read_state(base).get("port") or serve.PORT
        if serve.is_ours_running(port):
            log.info("已有实例在 port %s，直接打开页面", port)
            webbrowser.open("http://127.0.0.1:%d/" % port)
            return 0
        log.warning("互斥量存在但端口 %s 上不是本应用", port)

    # 首次运行初始化
    seed_data(os.path.join(serve.RES, "examples"), serve.DATA)
    html_path = os.path.join(serve.DIST, "OpenSchedule.html")
    try:
        if page_is_stale(serve, html_path, serve.APP_VERSION):
            build_page(serve, html_path)
            st = read_state(base)
            st["built_version"] = serve.APP_VERSION
            with io.open(os.path.join(base, "state.json"), "w", encoding="utf-8") as f:
                json.dump(st, f, ensure_ascii=False)
        else:
            log.info("页面是最新的，跳过构建")
    except Exception:
        log.exception("页面构建失败")
        alert("页面构建失败，请查看日志：\n%s" % os.path.join(base, "logs", "openschedule.log"))
        return 1

    # 起服务
    try:
        httpd = serve.bind(serve.PORT)
    except OSError:
        if serve.is_ours_running(serve.PORT):
            log.info("端口 %s 上已是本应用，直接打开页面", serve.PORT)
            webbrowser.open(serve.URL)
            return 0
        alert("端口 %d 被其他程序占用，OpenSchedule 无法启动。\n\n"
              "请关闭占用该端口的程序后重试；或用命令行参数 --port 换一个端口。"
              % serve.PORT)
        return 1
    server_thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    server_thread.start()
    write_state(base, serve.PORT)
    log.info("服务就绪 http://127.0.0.1:%d/", serve.PORT)

    url = "http://127.0.0.1:%d/" % serve.PORT
    if not opts["no_open"]:
        threading.Timer(0.4, lambda: webbrowser.open(url)).start()

    stop_event = threading.Event()

    def rebuild():
        try:
            build_page(serve, html_path)
            log.info("页面已重建")
        except Exception:
            log.exception("手动重建失败")

    def quit_app():
        stop_event.set()

    serve.ON_SHUTDOWN.append(quit_app)   # /api/shutdown 或托盘退出走同一条清理路径

    tray = make_tray(serve, os.path.join(serve.RES, "app-icon.png"), url, rebuild, quit_app)

    try:
        stop_event.wait()                 # 没有托盘时进程也常驻，靠 --quit / 日志排查
    finally:
        log.info("退出")
        try:
            httpd.shutdown()
        except Exception:
            pass
        if tray:
            try:
                tray.stop()
            except Exception:
                pass
        clear_state(base)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception:
        log.exception("启动器崩溃")
        alert("OpenSchedule 启动失败，请查看日志。")
        sys.exit(1)
