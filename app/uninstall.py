#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""OpenSchedule 卸载器。

放在 OpenSchedule.exe 旁边运行（安装包已自带）。卸载内容：
  1. 正在运行的实例（先请求 /api/shutdown，无效再结束进程）
  2. 个人数据目录 %LOCALAPPDATA%\\OpenSchedule\\（可选，默认询问）
  3. 程序文件夹内容（运行中的 uninstall.exe 自身除外；
     它和空文件夹注册为“重启自动删除”，也可在结束后手动删）

不写注册表、不装服务、不生成其它文件，因此无需清理更多内容。
便携模式（数据在 exe 旁）时，数据随程序文件夹一起删除。

命令行：uninstall.exe [--yes] [--keep-data]   （自动化/静默用）
"""
import ctypes
import http.client
import json
import os
import shutil
import sys
import tempfile
import time

APP_NAME = "OpenSchedule"
SELF_NAME = "uninstall.exe"
DEFAULT_PORT = 8123

MB_OK, MB_OKCANCEL, MB_YESNO = 0x00, 0x01, 0x04
MB_ICONINFO, MB_ICONWARN, MB_ICONQUESTION = 0x40, 0x30, 0x20
IDOK, IDYES = 1, 6
MOVEFILE_DELAYED_UNTIL_REBOOT = 4


def msg(text, flags):
    return ctypes.windll.user32.MessageBoxW(0, text, APP_NAME + " 卸载", flags)


def log(text):
    sys.stderr.write("[uninstall] %s\n" % text)


# ---------------------------------------------------------------- 路径净化
def clean_dir(path):
    """只接受不含 .. 的已存在目录；返回规范化后的绝对路径，否则 None。"""
    if not isinstance(path, str) or not path.strip() or ".." in path:
        return None
    real = os.path.realpath(path)
    return real if os.path.isdir(real) else None


def validated_app_dir(path):
    """进一步要求目录里确实装着本程序（存在 OpenSchedule.exe）。"""
    real = clean_dir(path)
    if not real:
        return None
    for marker in (os.path.join(real, APP_NAME + ".exe"),
                   os.path.join(real, "_internal", APP_NAME + ".exe")):
        if os.path.exists(marker):
            return real
    return None


def validated_data_dir(path):
    real = clean_dir(path)
    if real and os.path.basename(real).lower() == APP_NAME.lower():
        return real
    return None


# ---------------------------------------------------------------- 基础操作
def http_call(port, method, path):
    """固定回环地址 + 已校验整数端口，只用于本机控制接口。"""
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=3)
    try:
        conn.request(method, path, body=b"{}" if method == "POST" else None,
                     headers={"Content-Type": "application/json",
                              "Origin": "http://127.0.0.1:%d/" % port})
        resp = conn.getresponse()
        return resp.status, resp.read()
    finally:
        conn.close()


def read_port(base):
    try:
        with open(os.path.join(base, "state.json"), encoding="utf-8") as f:
            port = int(json.load(f).get("port") or 0)
        return port if 1 <= port <= 65535 else DEFAULT_PORT
    except Exception:
        return DEFAULT_PORT


def stop_app(base):
    """停掉正在运行的 OpenSchedule；返回是否确实停了。"""
    port = read_port(base)
    try:
        http_call(port, "POST", "/api/shutdown")
    except Exception:
        pass
    for _ in range(10):                       # 等优雅退出，最多 5 秒
        try:
            http_call(port, "GET", "/api/health")
        except Exception:
            return True
        time.sleep(0.5)
    subprocess_run_taskkill()
    time.sleep(0.8)
    try:
        http_call(port, "GET", "/api/health")
        return False
    except Exception:
        return True


def subprocess_run_taskkill():
    import subprocess
    subprocess.run(["taskkill", "/IM", APP_NAME + ".exe", "/F"],
                   capture_output=True)


def data_base(app_dir):
    """个人数据位置；返回 (路径, 是否便携模式)。"""
    if any(os.path.exists(os.path.join(app_dir, "data", n))
           for n in ("schedule.md", "schedule.json")):
        return os.path.join(app_dir, "data"), True
    return os.path.join(os.environ.get("LOCALAPPDATA") or app_dir, APP_NAME), False


def remove_retry(path, seconds=6):
    """删除文件或目录，失败重试；返回是否删掉。"""
    for _ in range(int(seconds / 0.4)):
        try:
            if os.path.isdir(path) and not os.path.islink(path):
                shutil.rmtree(path)
            elif os.path.exists(path) or os.path.islink(path):
                os.remove(path)
            return True
        except OSError:
            time.sleep(0.4)
    return not os.path.exists(path)


def delete_on_reboot(path):
    """注册“重启时由系统删除”；用于删不掉的运行中自身与残留空文件夹。"""
    try:
        ctypes.windll.kernel32.MoveFileExW(path, None, MOVEFILE_DELAYED_UNTIL_REBOOT)
    except Exception:
        pass


# ---------------------------------------------------------------- 主流程
def main():
    app_dir = validated_app_dir(os.path.dirname(os.path.abspath(sys.executable)))
    if not app_dir:
        msg("请把 uninstall.exe 放在 OpenSchedule 程序文件夹（OpenSchedule.exe 旁边）运行。",
            MB_OK | MB_ICONWARN)
        return 1

    auto = "--yes" in sys.argv
    if not auto:
        if msg("确定要卸载 OpenSchedule 吗？", MB_OKCANCEL | MB_ICONQUESTION) != IDOK:
            return 0

    base, portable = data_base(app_dir)
    if portable:
        del_data = True                          # 数据在程序文件夹里，随文件夹一起删
    elif auto:
        del_data = "--keep-data" not in sys.argv
    else:
        del_data = msg("是否同时删除个人数据（日程、DDL、助手配置）？\n\n%s" % base,
                       MB_YESNO | MB_ICONQUESTION) == IDYES

    log("stop app…")
    if not stop_app(base):
        msg("OpenSchedule 仍在运行，请先从托盘退出后重试。", MB_OK | MB_ICONWARN)
        return 1

    if del_data and not portable:
        target = validated_data_dir(base)
        if not target:
            log("refuse to delete data dir: %r" % (base,))
        elif not remove_retry(target):
            msg("部分个人数据未能删除，请手动删除：\n%s" % target, MB_OK | MB_ICONWARN)

    # 程序文件夹：删掉除 uninstall.exe 自身以外的一切
    log("remove program folder contents: %s" % app_dir)
    failed = []
    for name in os.listdir(app_dir):
        if name.lower() == SELF_NAME:
            continue
        if not remove_retry(os.path.join(app_dir, name)):
            failed.append(name)
    # 自身：同盘时可先改名挪到临时目录（Windows 允许移动运行中的 exe），
    # 这样程序文件夹能当场删干净；跨盘或失败则注册重启删除。
    self_path = os.path.join(app_dir, SELF_NAME)
    moved = False
    try:
        dest = os.path.join(tempfile.gettempdir(), APP_NAME + "-uninstall.exe")
        os.rename(self_path, dest)
        moved = True
        delete_on_reboot(dest)                  # 临时副本重启时清掉
    except OSError:
        pass
    if moved:
        try:
            os.rmdir(app_dir)                   # 文件夹已空，当场删除
        except OSError:
            delete_on_reboot(app_dir)
    else:
        delete_on_reboot(self_path)
        delete_on_reboot(app_dir)

    if not failed and not os.path.exists(app_dir):
        if not auto:
            msg("OpenSchedule 已卸载。", MB_OK | MB_ICONINFO)
    elif not failed:
        if not auto:
            msg("OpenSchedule 已卸载。空文件夹将在下次重启时自动清除（也可手动删除）。",
                MB_OK | MB_ICONINFO)
    else:
        log("failed to remove: %s" % ", ".join(failed))
        if not auto:
            msg("OpenSchedule 已卸载，但以下文件被占用未能删除（重启后会自动清除"
                "，或手动删除）：\n\n" + "\n".join(failed), MB_OK | MB_ICONWARN)
        for name in failed:
            delete_on_reboot(os.path.join(app_dir, name))
    return 0


if __name__ == "__main__":
    sys.exit(main())
