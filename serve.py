#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""OpenSchedule 本地服务。

作用：
  1. 托管 dist/ 里的页面（用 http:// 打开，file:// 的限制就没有了）
  2. /api/todo    GET 读 data/todo.md ／ POST 写回（文件不存在时 GET 返回 404，前端退回构建内副本）
  3. /api/config  模型池的读写（data/agent.json，Key 不出现在响应里）
  4. /api/chat    用模型池里选中的模型回答问题，并带上当前日程作上下文
  5. /api/open    用系统默认程序打开本地文件/文件夹（替代旧的自定义协议方案）

用法：
    python serve.py            启动并打开浏览器
    python serve.py --no-open  只启动服务
    python serve.py --port N   指定端口（或环境变量 SCHED_PORT）

路径规则（源码运行 / PyInstaller 打包后一致）：
    源码运行   data = <仓库>/data            dist = <仓库>/dist
    打包-便携  exe 旁有 data/schedule.json 时用 exe 目录下的 data/dist
    打包-安装  %LOCALAPPDATA%/OpenSchedule/{data,dist}
    环境变量 SCHED_DATA / SCHED_DIST 可强制覆盖。
"""
import io, os, sys, json, logging, subprocess, threading, webbrowser
import urllib.request, urllib.error
import http.client
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse
import ipaddress

APP_NAME = "OpenSchedule"
APP_VERSION = "1.0.0"

log = logging.getLogger("openschedule")


# ---------------------------------------------------------------- 路径
def _resolve_paths():
    """返回 (资源目录, 数据目录, dist 目录)。资源目录只读（打包后指向解包目录）。"""
    frozen = getattr(sys, "frozen", False)
    if frozen:
        res = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(sys.executable)))
        exe_dir = os.path.dirname(os.path.abspath(sys.executable))
        if os.path.exists(os.path.join(exe_dir, "data", "schedule.json")):
            base = exe_dir                                    # 便携模式：数据跟 exe 走
        else:
            base = os.path.join(os.environ.get("LOCALAPPDATA") or exe_dir, APP_NAME)
    else:
        res = os.path.dirname(os.path.abspath(__file__))
        base = res
    data = os.environ.get("SCHED_DATA") or os.path.join(base, "data")
    dist = os.environ.get("SCHED_DIST") or os.path.join(base, "dist")
    return res, data, dist


RES, DATA, DIST = _resolve_paths()
TODO = os.path.join(DATA, "todo.md")
CONFIG = os.path.join(DATA, "agent.json")
PORT = int(os.environ.get("SCHED_PORT") or 8123)
HOST = "127.0.0.1"                      # 只绑回环，不触发防火墙
URL = "http://127.0.0.1:%d/" % PORT

# /api/shutdown 触发时依次调用的回调（启动器用它停托盘、清理状态文件）
ON_SHUTDOWN = []


# ---------------------------------------------------------------- 配置读写
def load_cfg():
    """模型池：{"active": <id>, "providers": [{id,name,baseUrl,model,apiKey}]}。
    旧的单供应商结构会自动迁移过来。"""
    d = {}
    try:
        with io.open(CONFIG, encoding="utf-8") as f:
            d = json.load(f)
    except Exception:
        pass
    if not isinstance(d, dict):
        d = {}
    if "providers" not in d:
        prov = []
        if d.get("apiKey") or d.get("provider"):
            prov = [{"id": "p1", "name": d.get("provider") or "默认",
                     "baseUrl": d.get("baseUrl") or "https://api.deepseek.com/v1",
                     "model": d.get("model") or "deepseek-chat",
                     "apiKey": d.get("apiKey") or ""}]
        d = {"active": "p1" if prov else "", "providers": prov}
    d["providers"] = [p for p in (d.get("providers") or []) if isinstance(p, dict)]
    if d["providers"] and not any(p.get("id") == d.get("active") for p in d["providers"]):
        d["active"] = d["providers"][0].get("id", "")
    return d


def active_provider(cfg):
    for p in cfg.get("providers") or []:
        if p.get("id") == cfg.get("active"):
            return p
    provs = cfg.get("providers") or []
    return provs[0] if provs else None


def save_cfg(d):
    os.makedirs(os.path.dirname(CONFIG), exist_ok=True)
    with io.open(CONFIG, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------- 助手
def _provider_url_error(u):
    """校验模型 baseUrl：仅允许 http/https，且 host 不能是本机/内网/保留地址。"""
    try:
        p = urlparse(u or "")
    except Exception:
        return "URL 无法解析"
    if p.scheme not in ("http", "https"):
        return "仅支持 http/https 的接口地址"
    host = (p.hostname or "").strip()
    if not host:
        return "URL 缺少主机名"
    if host.lower() in ("localhost",) or host.endswith(".localhost"):
        return "不允许指向本机"
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return None                                          # 域名，放行
    if (ip.is_loopback or ip.is_private or ip.is_reserved or ip.is_link_local
            or ip.is_multicast or ip.is_unspecified):
        return "不允许指向本机或内网地址"
    return None


def context_text():
    """把当前数据拼进 system prompt，让回答有据可依。"""
    lines = []
    try:
        todo = read_todo()
        pend = [l.strip()[6:].strip() for l in todo.splitlines()
                if l.strip().startswith("- [ ]")]
        if pend:
            lines.append("待办 DDL：" + "；".join(pend[:20]))
    except Exception:
        pass
    try:
        build_dir = os.path.join(RES, "build")
        if build_dir not in sys.path:
            sys.path.insert(0, build_dir)
        import build as B
        baked = B.build_schedule(DATA)
        import datetime
        today = datetime.date.today().isoformat()
        plan = baked.get(today) or {}
        if plan.get("tasks"):
            lines.append("今天主要任务：" + "；".join([t if isinstance(t, str) else t.get("t", "") for t in plan["tasks"]]))
        items = plan.get("items") or []
        if items:
            lines.append("今天时间安排：" + "；".join("%s %s" % (i.get("t", ""), i.get("title", "")) for i in items))
    except Exception:
        log.exception("context_text 构建失败")
    return "\n".join(lines)


def chat_reply(message, history):
    cfg = load_cfg()
    prov = active_provider(cfg)
    if not prov or not prov.get("apiKey"):
        return {"error": "还没有可用的模型，点输入框右边的 ⚙ 配一个。"}
    base = (prov.get("baseUrl") or "").rstrip("/")
    err = _provider_url_error(base)
    if err:
        return {"error": "接口地址不合规：%s" % err}
    ctx = context_text()
    import datetime
    system = ("你是「每日安排」这个日程应用里的助手。今天是 %s。\n%s\n"
              "回答用中文，简短、具体、直接给结论；需要调整安排时给出可执行的建议（时间点 + 事项）。"
              "不要编造数据里没有的条目。") % (
              datetime.date.today().isoformat(), ctx or "（暂无数据）")
    msgs = [{"role": "system", "content": system}]
    for m in (history or [])[-8:]:
        if m.get("role") in ("user", "assistant") and m.get("content"):
            msgs.append({"role": m["role"], "content": m["content"]})
    msgs.append({"role": "user", "content": message})
    url = base + "/chat/completions"
    body = json.dumps({"model": prov.get("model") or "deepseek-chat", "messages": msgs,
                       "temperature": 0.3, "stream": False}).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers={
        "Content-Type": "application/json",
        "Authorization": "Bearer " + prov["apiKey"]})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            data = json.loads(r.read().decode("utf-8"))
        return {"reply": data["choices"][0]["message"]["content"]}
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "ignore")[:300]
        return {"error": "接口返回 %s：%s" % (e.code, detail)}
    except Exception as e:
        return {"error": "调用失败：%s" % e}


def read_todo():
    try:
        with io.open(TODO, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


def write_todo(text):
    os.makedirs(os.path.dirname(TODO), exist_ok=True)
    tmp = TODO + ".tmp"
    with io.open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    os.replace(tmp, TODO)


# ---------------------------------------------------------------- 用系统默认程序打开
# os.startfile 即 ShellExecute：按系统默认关联打开，文件夹自动开资源管理器。
# 可执行/脚本类型一律拒绝（“系统默认打开”对它们等于直接执行）。
DANGEROUS_EXT = {
    ".exe", ".bat", ".cmd", ".com", ".ps1", ".vbs", ".vbe", ".js", ".jse",
    ".wsf", ".wsh", ".msi", ".msp", ".mst", ".scr", ".hta", ".cpl", ".jar",
    ".lnk", ".url", ".reg", ".pif", ".sh", ".py", ".pyw", ".application", ".gadget",
}


def open_path(path):
    """返回 (ok:bool, err:str|None)。"""
    path = str(path or "").strip().strip('"').strip("'")
    if not path:
        return False, "路径为空"
    if not os.path.exists(path):
        return False, "路径不存在：%s" % path
    ext = os.path.splitext(path)[1].lower()
    if ext in DANGEROUS_EXT:
        return False, "出于安全考虑，不能打开可执行文件或脚本（%s）" % (ext or "该类型")
    try:
        os.startfile(path)
        return True, None
    except OSError as e:
        if getattr(e, "winerror", None) == 1155:            # 没有关联程序
            sysroot = os.environ.get("SystemRoot", r"C:\Windows")
            try:
                subprocess.Popen([
                    os.path.join(sysroot, "System32", "rundll32.exe"),
                    "shell32.dll,OpenAs_RunDLL", path],
                    close_fds=True)
                return True, None
            except Exception:
                return False, "%s 没有默认打开程序，请先在资源管理器里为它设置关联" % (ext or "该文件")
        return False, "打开失败：%s" % e


def _origin_allowed(handler):
    """同源校验：Origin/Referer 若存在，必须还是本服务自己。"""
    import re
    for h in ("Origin", "Referer"):
        v = (handler.headers.get(h) or "").strip()
        if not v or v == "null":
            return not v                      # 缺头放行（同源 GET 场景）；"null" 拒绝
        if not re.match(r"^https?://(127\.0\.0\.1|localhost|\[::1\])(:\d+)?/", v + "/"):
            return False
    return True


# ---------------------------------------------------------------- HTTP
class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        kw["directory"] = DIST
        super().__init__(*a, **kw)

    def log_message(self, fmt, *a):
        log.debug("%s %s", self.address_string(), fmt % a)

    def _send(self, code, body, ctype="text/plain; charset=utf-8"):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code, obj):
        self._send(code, json.dumps(obj, ensure_ascii=False), "application/json")

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/api/todo":
            if not os.path.exists(TODO):
                return self._send(404, "todo.md not found")   # 前端会退回构建内副本
            return self._send(200, read_todo())
        if path == "/api/health":
            return self._json(200, {"ok": True, "app": APP_NAME, "version": APP_VERSION,
                                    "todo": os.path.exists(TODO)})
        if path == "/api/config":
            cfg = load_cfg()
            pool = [{"id": p.get("id", ""), "name": p.get("name", ""),
                     "baseUrl": p.get("baseUrl", ""), "model": p.get("model", ""),
                     "hasKey": bool(p.get("apiKey"))} for p in cfg["providers"]]
            return self._json(200, {"active": cfg.get("active", ""), "providers": pool})
        if path in ("/", "/index.html"):
            self.path = "/OpenSchedule.html"
        return super().do_GET()

    def do_POST(self):
        path = urlparse(self.path).path
        n = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(n).decode("utf-8") if n else ""
        if path == "/api/todo":
            try:
                write_todo(body)
            except OSError as e:
                return self._send(500, "写入失败: %s" % e)
            return self._send(200, read_todo())
        if path in ("/api/open", "/api/shutdown"):
            # 跨站防护：只收 application/json（跨站表单/纯文本发不进来），
            # 且 Origin/Referer 若存在必须指向本服务。
            ctype = (self.headers.get("Content-Type") or "").split(";")[0].strip().lower()
            if ctype != "application/json":
                return self._send(415, json.dumps({"error": "bad content-type"}), "application/json")
            if not _origin_allowed(self):
                return self._send(403, json.dumps({"error": "bad origin"}), "application/json")
            try:
                incoming = json.loads(body or "{}")
            except Exception:
                return self._send(400, json.dumps({"error": "bad json"}), "application/json")
            if path == "/api/open":
                ok, err = open_path(incoming.get("path"))
                return self._json(200 if ok else 400, {"ok": ok, "error": err})

            def _go():
                for cb in ON_SHUTDOWN:
                    try:
                        cb()
                    except Exception:
                        log.exception("shutdown 回调失败")
                self.server.shutdown()
            threading.Thread(target=_go, daemon=True).start()
            return self._json(200, {"ok": True})
        if path == "/api/config":
            try:
                incoming = json.loads(body or "{}")
            except Exception:
                return self._send(400, json.dumps({"error": "bad json"}), "application/json")
            old = {p.get("id"): p for p in load_cfg()["providers"]}
            pool = []
            for p in (incoming.get("providers") or []):
                if not isinstance(p, dict):
                    continue
                pid = p.get("id") or ("p%d" % (len(pool) + 1))
                key = (p.get("apiKey") or "").strip()
                if not key and pid in old:          # 留空 = 沿用已存的 Key
                    key = old[pid].get("apiKey") or ""
                pool.append({"id": pid, "name": p.get("name") or "",
                             "baseUrl": (p.get("baseUrl") or "").rstrip("/"),
                             "model": p.get("model") or "", "apiKey": key})
            cfg = {"active": incoming.get("active") or (pool[0]["id"] if pool else ""),
                   "providers": pool}
            save_cfg(cfg)
            return self._json(200, {"ok": True, "count": len(pool)})
        if path == "/api/chat":
            try:
                incoming = json.loads(body or "{}")
            except Exception:
                return self._send(400, json.dumps({"error": "bad json", }), "application/json")
            out = chat_reply((incoming.get("message") or "").strip(), incoming.get("history") or [])
            return self._json(200, out)
        return self._send(404, "not found")


class Server(ThreadingHTTPServer):
    # Windows 下默认的 SO_REUSEADDR 允许多个进程绑同一端口（多个实例互相抢流量），
    # 必须关掉，第二个实例才会绑定失败、走“已有实例”分支。
    allow_reuse_address = 0
    daemon_threads = True


def bind(port=None):
    """绑定端口，返回 httpd；失败抛 OSError。"""
    return Server((HOST, port or PORT), Handler)


def is_ours_running(port=None):
    """探测端口上是不是 OpenSchedule 自己的实例。

    固定回环地址 + 只接受整数端口（内部传参），不做任何外部 URL 请求。"""
    try:
        port = int(port or PORT)
    except (TypeError, ValueError):
        return False
    if not 1 <= port <= 65535:
        return False
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
    try:
        conn.request("GET", "/api/health")
        resp = conn.getresponse()
        d = json.loads(resp.read().decode("utf-8"))
        return bool(d.get("ok") and d.get("app") == APP_NAME)
    except Exception:
        return False
    finally:
        conn.close()


def main():
    open_browser = "--no-open" not in sys.argv and os.environ.get("SCHED_NO_OPEN") != "1"
    port = PORT
    if "--port" in sys.argv:
        try:
            port = int(sys.argv[sys.argv.index("--port") + 1])
        except (IndexError, ValueError):
            pass
    try:
        httpd = bind(port)
    except OSError:
        if is_ours_running(port):
            print("OpenSchedule 已在运行:", URL)
            if open_browser:
                webbrowser.open(URL)
            return 0
        print("端口 %d 被其他程序占用（不是 OpenSchedule）。" % port)
        print("关闭占用它的程序后重试，或用环境变量 SCHED_PORT / 参数 --port 换一个端口。")
        return 1
    if open_browser:
        threading.Timer(0.5, lambda: webbrowser.open("http://127.0.0.1:%d/" % port)).start()
    print("OpenSchedule: http://127.0.0.1:%d/  (data: %s)" % (port, DATA))
    httpd.serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
