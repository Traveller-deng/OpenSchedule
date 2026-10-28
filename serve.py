#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""OpenSchedule 本地服务。

作用：
  1. 托管 dist/ 里的页面（用 http:// 打开，file:// 的限制就没有了）
  2. /api/todo    GET 读 data/todo.md（DDL）／ POST 写回（文件不存在时 GET 返回 404，前端退回构建内副本）
  3. /api/tasks   GET 读 data/tasks.md（任务安排）／ POST 写回
  4. /api/config  模型池的读写（data/agent.json，Key 不出现在响应里）
  5. /api/chat    用模型池里选中的模型回答问题，并带上当前日程作上下文
  6. /api/open    用系统默认程序打开本地文件/文件夹（替代旧的自定义协议方案）

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
import io, os, sys, json, logging, subprocess, threading, webbrowser, shutil, time
import urllib.request, urllib.error
import http.client
import re
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse
import ipaddress

APP_NAME = "OpenSchedule"
APP_VERSION = "1.1.1"
APP_TITLE = "OpenSchedule · 每日安排"

log = logging.getLogger("openschedule")


# ---------------------------------------------------------------- 路径
def _resolve_paths():
    """返回 (资源目录, 数据目录, dist 目录)。资源目录只读（打包后指向解包目录）。"""
    frozen = getattr(sys, "frozen", False)
    if frozen:
        res = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(sys.executable)))
        exe_dir = os.path.dirname(os.path.abspath(sys.executable))
        # 便携模式：exe 旁边有 data\ 就算（当前数据源是 schedule.md，旧的 schedule.json 也认）
        if any(os.path.exists(os.path.join(exe_dir, "data", n))
               for n in ("schedule.md", "schedule.json")):
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
TASKS = os.path.join(DATA, "tasks.md")
CONFIG = os.path.join(DATA, "agent.json")
EDITS = os.path.join(DATA, "edits.json")
DRAFT = os.path.join(DATA, "draft.md")
PORT = int(os.environ.get("SCHED_PORT") or 8123)
HOST = "127.0.0.1"                      # 只绑回环，不触发防火墙
URL = "http://127.0.0.1:%d/" % PORT

# /api/shutdown 触发时依次调用的回调（启动器用它停托盘、清理状态文件）
ON_SHUTDOWN = []

if not getattr(sys, "frozen", False) and os.path.isdir(os.path.join(RES, "build")):
    # 保证后续任何 `import build` 命中 build/build.py 模块，
    # 而不是根目录下同名 build/ 目录的命名空间包
    _BUILD_DIR = os.path.join(RES, "build")
    if _BUILD_DIR not in sys.path:
        sys.path.insert(0, _BUILD_DIR)


def load_edits():
    """页面本地增补层（浏览器 localStorage 的服务端副本）。

    页面每次编辑都会 POST 到 /api/edits 存到这里；agent / CLI 也可以改它，
    页面轮询发现变化后会自动采纳。结构见前端 emptyEdits()：
    adds/ovr/hides（时间块）、sections（任务组替换）、tasksDone（任务完成标记）、
    ddl/ddlDone（file:// 兜底用）、links（入口增改）。"""
    try:
        with io.open(EDITS, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def save_edits(d):
    os.makedirs(DATA, exist_ok=True)
    tmp = EDITS + ".tmp"
    with io.open(tmp, "w", encoding="utf-8", newline="\n") as f:
        json.dump(d, f, ensure_ascii=False)
    os.replace(tmp, EDITS)


def effective_schedule():
    """data 文件 + 页面覆盖层 → 页面实际展示的数据（各工具读它才和用户看到的一致）。

    时间块：hides 藏起 baked 条目 → ovr 按字段覆盖 → adds 追加/插入；
    任务组：sections[k].tasks 存在时整组替换；tasksDone 按任务文本标记完成。
    与前端 buildList/daySections 的语义保持一致。"""
    build_dir = os.path.join(RES, "build")
    if build_dir not in sys.path:
        sys.path.insert(0, build_dir)
    import build as B
    baked = B.build_schedule(DATA)
    ed = load_edits()
    adds_all, ovr_all, hides_all = ed.get("adds") or {}, ed.get("ovr") or {}, ed.get("hides") or {}
    sections, tasks_done = ed.get("sections") or {}, ed.get("tasksDone") or {}
    keys = set(baked) | {k for k in adds_all if isinstance(adds_all.get(k), list) and adds_all[k]} \
        | {k for k in sections if isinstance(sections.get(k), dict) and sections[k].get("tasks") is not None}
    out = {}
    for k in keys:
        plan = baked.get(k) or {}
        items = [dict(it, id="b%d" % i) for i, it in enumerate(plan.get("items") or [])]
        hidden = set(hides_all.get(k) or [])
        items = [it for it in items if it["id"] not in hidden]
        for it in items:
            o = (ovr_all.get(k) or {}).get(it["id"])
            if isinstance(o, dict):
                for f in ("t", "d", "title", "type", "detail", "out", "list", "links"):
                    if o.get(f) is not None:
                        it[f] = o[f]
                it["edited"] = True
        for a in (adds_all.get(k) or []):
            if not isinstance(a, dict):
                continue
            it = dict(a)
            it.setdefault("src", "user")
            after = it.get("after")
            pos = next((i for i, x in enumerate(items) if x.get("id") == after), None)
            if not after or after == "__tail__" or pos is None:
                items.append(it)
            else:
                items.insert(pos + 1, it)
        sec = sections.get(k)
        tasks = sec.get("tasks") if isinstance(sec, dict) and sec.get("tasks") is not None \
            else plan.get("tasks") or []
        done = tasks_done.get(k) if isinstance(tasks_done.get(k), dict) else {}
        out[k] = {"tasks": tasks, "tasksDone": done, "items": items}
    return out


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
    """把当前数据拼进 system prompt，让回答有据可依（含页面上的本地增补）。"""
    import datetime
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
        pend = [l.strip()[6:].strip() for l in read_tasks().splitlines()
                if l.strip().startswith("- [ ]")]
        if pend:
            lines.append("任务安排（无 DDL，自己推进）：" + "；".join(pend[:20]))
    except Exception:
        pass
    try:
        eff = effective_schedule()
        today = datetime.date.today().isoformat()
        plan = eff.get(today) or {}
        done = plan.get("tasksDone") or {}

        def task_text(t):
            return t if isinstance(t, str) else t.get("t", "")
        tasks = plan.get("tasks") or []
        if tasks:
            marks = ["%s%s" % ("[x] " if done.get(task_text(t)) else "", task_text(t))
                     for t in tasks]
            lines.append("今天主要任务：" + "；".join(marks))
        items = plan.get("items") or []
        if items:
            lines.append("今天时间安排：" + "；".join(
                "%s %s%s" % (i.get("t", ""), i.get("title", ""),
                             "（已勾）" if isinstance(i, dict) and i.get("done") else "")
                for i in items))
    except Exception:
        log.exception("context_text 合并失败")
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


def read_tasks():
    """任务安排（data/tasks.md）原文。文件不存在返回空串。"""
    try:
        with io.open(TASKS, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


def write_tasks(text):
    os.makedirs(os.path.dirname(TASKS), exist_ok=True)
    tmp = TASKS + ".tmp"
    with io.open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    os.replace(tmp, TASKS)


def ensure_data():
    """数据目录为空时，用 examples/ 的示例播种（已存在的文件一律不动）。

    源码运行时 data/ 被 .gitignore 排除，干净克隆里并没有它；没有这一步，
    页面只有构建内副本，DDL 与任务安排也写不回文件（只有 localStorage）。"""
    examples = os.path.join(RES, "examples")
    if not os.path.isdir(examples):
        return
    os.makedirs(DATA, exist_ok=True)
    for name in ("schedule.md", "todo.md", "tasks.md", "links.json"):
        src = os.path.join(examples, name)
        dst = os.path.join(DATA, name)
        if os.path.exists(dst) or not os.path.exists(src):
            continue
        try:
            shutil.copyfile(src, dst)
            log.info("播种 %s", name)
        except OSError:
            log.exception("播种 %s 失败", name)


def read_draft():
    try:
        with io.open(DRAFT, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return None                             # 文件不存在与空内容要区分


def write_draft(text):
    os.makedirs(DATA, exist_ok=True)
    tmp = DRAFT + ".tmp"
    with io.open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    os.replace(tmp, DRAFT)


# ---------------------------------------------------------------- 数据变更自动重建
# agent 等外部工具直接改了 data/ 里的文件时，页面在下一次请求前现场重建，
# 浏览器刷新（或按 /api/poll 的提示）即可看到，不需要托盘里手动“重建页面”。
BUILD_LOCK = threading.Lock()


_code_id_seen = {"v": ""}


def _check_code_change():
    """前端代码变了 → 通知所有页面刷新（浏览器里跑的旧代码自己换新）。"""
    cid = built_code_id()
    if not cid:
        return
    old = _code_id_seen["v"]
    _code_id_seen["v"] = cid
    if old and old != cid:
        log.info("frontend code changed %s -> %s, asking pages to reload", old, cid)
        notice_bump(reload=True)


def _data_is_stale():
    html = os.path.join(DIST, "OpenSchedule.html")
    try:
        html_m = os.path.getmtime(html)
    except OSError:
        return True
    for name in ("schedule.md", "schedule.json", "todo.md", "tasks.md", "links.json", "profile.json"):
        try:
            if os.path.getmtime(os.path.join(DATA, name)) > html_m:
                return True
        except OSError:
            pass
    return False


def rebuild_if_stale():
    if not _data_is_stale():
        return False
    with BUILD_LOCK:
        if not _data_is_stale():
            return False
        try:
            build_dir = os.path.join(RES, "build")
            if build_dir not in sys.path:
                sys.path.insert(0, build_dir)
            import build as B
            B.build(profile="personal", out=os.path.join(DIST, "OpenSchedule.html"),
                    data_dir=DATA, root=RES)
            log.info("data changed, page rebuilt")
            return True
        except Exception:
            log.exception("auto rebuild failed")
            return False


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


# ---------------------------------------------------------------- 全局快捷键
# 任何软件里按一下快捷键就把日程窗口拉到前台，再按一下切回刚才那个窗口。
# Windows 用 RegisterHotKey 注册系统级热键；其它系统不支持（页面上会说明）。
HOTKEY = os.path.join(DATA, "hotkey.json")
DEFAULT_HOTKEY = "Alt+S"
WM_HOTKEY, WM_QUIT = 0x0312, 0x0012
MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_WIN, MOD_NOREPEAT = 0x0001, 0x0002, 0x0004, 0x0008, 0x4000
HOTKEY_ID = 0xB5F1
VK_NAMES = {"space": 0x20, "tab": 0x09, "enter": 0x0D, "return": 0x0D, "esc": 0x1B, "escape": 0x1B,
            "up": 0x26, "down": 0x28, "left": 0x25, "right": 0x27, "home": 0x24, "end": 0x23,
            "pageup": 0x21, "pagedown": 0x22, "insert": 0x2D, "delete": 0x2E, "backspace": 0x08}
for _i in range(1, 13):
    VK_NAMES["f%d" % _i] = 0x6F + _i
VK_PUNCT = {"-": 0xBD, "=": 0xBB, "[": 0xDB, "]": 0xDD, "\\": 0xDC, ";": 0xBA,
            "'": 0xDE, ",": 0xBC, ".": 0xBE, "/": 0xBF, "`": 0xC0}
BROWSER_EXES = ("msedge.exe", "chrome.exe", "brave.exe", "vivaldi.exe", "opera.exe",
                "chromium.exe", "firefox.exe")
KNOWN_BROWSER_PATHS = [
    r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe",
    r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe",
    r"%LocalAppData%\Microsoft\Edge\Application\msedge.exe",
    r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe",
    r"%ProgramFiles%\Google\Chrome\Application\chrome.exe",
    r"%LocalAppData%\Google\Chrome\Application\chrome.exe",
]


def default_browser_exe():
    """系统默认浏览器的 exe（先查注册表 UserChoice，再试常见安装位置）。"""
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                             r"Software\Microsoft\Windows\Shell\Associations"
                             r"\UrlAssociations\http\UserChoice") as k:
            progid = str(winreg.QueryValueEx(k, "ProgId")[0])
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                             r"SOFTWARE\Classes\%s\shell\open\command" % progid) as k:
            cmd = str(winreg.QueryValueEx(k, "")[0])
        exe = cmd.split('"')[1] if '"' in cmd else cmd.split(" ")[0]
        if exe and os.path.exists(exe):
            return exe
    except Exception:
        pass
    for p in KNOWN_BROWSER_PATHS:
        p = os.path.expandvars(p)
        if os.path.exists(p):
            return p
    return None


# ---- 页面通知（长轮询）：快捷键唤起时让页面滚回最上方 ----
NOTICE_SEQ = 0
NOTICE_RELOAD = 0           # 递增的"请刷新页面"代号
NOTICE_CV = threading.Condition()


def notice_bump(reload=False):
    """通知所有页面：日程被唤起了（reload=True 时顺便让页面自己刷新）。"""
    global NOTICE_SEQ, NOTICE_RELOAD
    with NOTICE_CV:
        NOTICE_SEQ += 1
        if reload:
            NOTICE_RELOAD += 1
        NOTICE_CV.notify_all()


def notice_wait(since, timeout=20):
    """等一个通知；超时也返回当前序号（客户端会立刻续订）。"""
    global NOTICE_SEQ
    deadline = time.time() + timeout
    with NOTICE_CV:
        while NOTICE_SEQ <= since:
            left = deadline - time.time()
            if left <= 0:
                break
            NOTICE_CV.wait(min(left, 5))
        return NOTICE_SEQ


def parse_hotkey(s):
    """'Alt+S' → (修饰键掩码, 虚拟键码)。解析不出来返回 (0, 0)。"""
    mods, vk = 0, 0
    for p in [x.strip().lower() for x in str(s or "").split("+") if x.strip()]:
        if p in ("alt", "option"):
            mods |= MOD_ALT
        elif p in ("ctrl", "control"):
            mods |= MOD_CONTROL
        elif p == "shift":
            mods |= MOD_SHIFT
        elif p in ("win", "meta", "super", "cmd"):
            mods |= MOD_WIN
        elif len(p) == 1:
            vk = VK_PUNCT.get(p) or ord(p.upper())
        else:
            vk = VK_NAMES.get(p, 0)
    return mods, vk


_page_title_cache = {"v": "", "t": 0.0}


def page_title():
    """页面标题：独立窗口（--app）的窗口标题和它完全一样，标签页窗口会多一截浏览器后缀。"""
    now = time.time()
    if now - _page_title_cache["t"] < 5:
        return _page_title_cache["v"]
    v = APP_TITLE
    try:
        with io.open(os.path.join(DIST, "OpenSchedule.html"), encoding="utf-8") as f:
            head = f.read(4096)
        m = re.search(r"<title>(.*?)</title>", head, re.S)
        if m:
            v = m.group(1).strip() or v
    except Exception:
        pass
    _page_title_cache["v"] = v
    _page_title_cache["t"] = now
    return v


_build_id_cache = {"id": "", "t": 0.0}


def built_code_id():
    """当前页面前端的代码指纹（只有前端源码变了才会变，数据变化不会）。

    页面拿它和自己的指纹比对：不一样说明浏览器里跑的是旧代码 → 自动刷新。"""
    p = os.path.join(DIST, "OpenSchedule.html")
    try:
        mt = os.path.getmtime(p)
    except OSError:
        return ""
    if _build_id_cache["t"] != mt:
        _build_id_cache["t"] = mt
        _build_id_cache["id"] = ""
        try:
            with io.open(p, encoding="utf-8") as f:
                html = f.read()
            m = re.search(r'const BUILD_ID\s*=\s*"([^"]*)"', html)
            if m:
                _build_id_cache["id"] = m.group(1)
        except Exception:
            pass
    return _build_id_cache["id"]


class HotkeyManager(object):
    """全局快捷键：唤起日程窗口 / 再按一次切回上一个窗口。"""

    def __init__(self):
        self.keys = DEFAULT_HOTKEY
        self.enabled = False
        self.error = ""
        self.paused = False
        self.supported = (sys.platform == "win32")
        self._thread = None
        self._stop = threading.Event()
        self._hwnd = 0            # 我们自己开的那扇独立窗口
        self._rect = None         # 上次关闭/隐藏时的窗口位置尺寸，重开时还原
        self._last = ""           # 最近一次判定，调试用
        self._opening = False     # 正在开窗（互斥，防止连按开一堆）
        self._pending = ""        # 开窗期间的按键意图（"hide"）
        self._focused_at = 0.0    # 最近一次把它拉到前台的时刻
        self._trace = []          # 最近几次操作轨迹，调试用

    # ---------- 配置 ----------
    def load(self):
        try:
            with io.open(HOTKEY, encoding="utf-8") as f:
                d = json.load(f)
            k = str(d.get("keys") or "").strip()
            if k:
                self.keys = k
        except Exception:
            pass
        return self.keys

    def save(self, keys):
        keys = str(keys or "").strip()
        if not keys:
            raise ValueError("快捷键不能为空")
        mods, vk = parse_hotkey(keys)
        if not mods or not vk:
            raise ValueError("快捷键写法不对，例如 Alt+S / Ctrl+Shift+K")
        os.makedirs(DATA, exist_ok=True)
        with io.open(HOTKEY, "w", encoding="utf-8", newline="\n") as f:
            json.dump({"keys": keys}, f, ensure_ascii=False, indent=2)
        self.keys = keys
        self.paused = False
        self.restart()
        return self.state()

    def state(self):
        return {"keys": self.keys, "enabled": self.enabled, "error": self.error,
                "paused": self.paused, "supported": self.supported, "url": URL,
                "last": self._last, "hwnd": self._hwnd, "opening": self._opening,
                "trace": list(self._trace)}

    # ---------- 生命周期 ----------
    def start(self):
        self.load()
        if not self.supported:
            self.error = "当前系统不支持全局快捷键（仅 Windows 可用）"
            return False
        self.paused = False
        self._spawn()
        return True

    def restart(self):
        self._shutdown()
        if not self.supported:
            self.error = "当前系统不支持全局快捷键（仅 Windows 可用）"
            return
        self.paused = False
        self._spawn()

    def pause(self):
        """临时取消注册（页面在录制新快捷键时用），配置不动。"""
        self.paused = True
        self._shutdown()

    def resume(self):
        if not self.paused:
            return
        self.paused = False
        if self.supported:
            self._spawn()

    def _spawn(self):
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _shutdown(self):
        self._stop.set()
        t = self._thread
        if t and t.is_alive():
            t.join(timeout=2)
        self._thread = None
        self.enabled = False

    def stop(self):
        """停止注册（程序退出时调用）。"""
        self._shutdown()

    # ---------- Windows 底层 ----------
    @staticmethod
    def _user32():
        import ctypes
        return ctypes.windll.user32

    @staticmethod
    def _proc_image(hwnd):
        """窗口所属进程的可执行文件路径（判断它是不是浏览器窗口）。

        注意：WinDLL 不会自动补 A/W 后缀，必须自己写 QueryFullProcessImageNameW，
        并且要显式声明 argtypes/restype，否则 64 位下句柄会被截断。"""
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.windll.user32
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(wintypes.HWND(hwnd), ctypes.byref(pid))
        if not pid.value:
            return ""
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        k32.OpenProcess.restype = wintypes.HANDLE
        k32.QueryFullProcessImageNameW.argtypes = [
            wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR,
            ctypes.POINTER(wintypes.DWORD)]
        k32.QueryFullProcessImageNameW.restype = wintypes.BOOL
        k32.CloseHandle.argtypes = [wintypes.HANDLE]
        h = k32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
        if not h:
            return ""
        try:
            size = wintypes.DWORD(1024)
            buf = ctypes.create_unicode_buffer(size.value)
            if not k32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
                return ""
            return buf.value
        finally:
            k32.CloseHandle(h)

    def _browser_windows(self):
        """标题带 OpenSchedule 的浏览器窗口（排除别的软件的同名标题）。

        独立窗口（--app）标题和页面标题完全一样，标签页窗口会多出浏览器后缀，
        所以同名的多个窗口里优先认独立窗口。"""
        import ctypes
        from ctypes import wintypes
        user32 = self._user32()
        found = []
        title = page_title()
        proc = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)

        def cb(hwnd, _lparam):
            if not user32.IsWindowVisible(hwnd):
                return True
            n = user32.GetWindowTextLengthW(hwnd)
            if n <= 0:
                return True
            buf = ctypes.create_unicode_buffer(n + 1)
            user32.GetWindowTextW(hwnd, buf, n + 1)
            if APP_NAME not in buf.value:
                return True
            img = self._proc_image(hwnd)
            if os.path.basename(img).lower() in BROWSER_EXES:
                found.append((0 if buf.value.strip() == title else 1, hwnd))
            return True

        user32.EnumWindows(proc(cb), 0)
        found.sort()
        return [h for _rank, h in found]

    def _find_browser_window(self):
        ws = self._browser_windows()
        return ws[0] if ws else 0

    @staticmethod
    def _focus(hwnd):
        """把窗口拉到前台。

        注意：不要无条件 ShowWindow(SW_RESTORE)——那会把最大化/分屏的窗口还原成
        之前的窄样子（用户原来最大化着的别的窗口会被拽到左边变窄）。
        只有窗口确实处于最小化时才恢复。"""
        import ctypes
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        cur = kernel32.GetCurrentThreadId()
        # 前台锁：光 SetForegroundWindow 不一定管用，要跟前台窗口、目标窗口
        # 的线程都建立输入关联才能真正抢到前台。
        tids = []
        for h in (user32.GetForegroundWindow(), hwnd):
            tid = user32.GetWindowThreadProcessId(h, None) if h else 0
            if tid and tid != cur and tid not in tids:
                tids.append(tid)
        for tid in tids:
            user32.AttachThreadInput(cur, tid, True)
        try:
            if user32.IsIconic(hwnd):
                user32.ShowWindow(hwnd, 9)          # SW_RESTORE：只处理"最小化"
            user32.BringWindowToTop(hwnd)
            user32.SetForegroundWindow(hwnd)
            user32.SetActiveWindow(hwnd)
        finally:
            for tid in tids:
                user32.AttachThreadInput(cur, tid, False)
        if user32.GetForegroundWindow() != hwnd:
            # 还是没抢到前台：硬切（不改窗口大小位置，所以不会把别的窗口拽窄）
            try:
                user32.SwitchToThisWindow(hwnd, True)
            except Exception:
                pass

    def _trace_add(self, msg):
        """记一条操作轨迹（调试用，页面/接口都能看）。"""
        self._trace.append("%s %s" % (time.strftime("%H:%M:%S"), msg))
        del self._trace[:-40]

    def _is_foreground(self, hwnd):
        """这扇窗是不是当前前台窗口（容忍 owner / root 包装）。"""
        import ctypes
        user32 = self._user32()
        fg = user32.GetForegroundWindow()
        if not fg:
            return False
        if fg == hwnd:
            return True
        if user32.GetAncestor(fg, 2) == hwnd:        # GA_ROOT
            return True
        if user32.GetWindow(hwnd, 4) == fg:          # GW_OWNER
            return True
        return False

    def _hide(self, hwnd):
        """收进托盘：窗口整个隐藏（任务栏也不再显示），进程还在，尺寸位置不变。"""
        import ctypes
        from ctypes import wintypes
        user32 = self._user32()
        rect = wintypes.RECT()
        if user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            self._rect = (rect.left, rect.top,
                          rect.right - rect.left, rect.bottom - rect.top)
        user32.ShowWindow(hwnd, 0)                  # SW_HIDE
        self._focused_at = 0.0

    def _show(self, hwnd):
        import ctypes
        user32 = self._user32()
        if not user32.IsWindowVisible(hwnd):
            user32.ShowWindow(hwnd, 5)              # SW_SHOW：原样显示，尺寸位置不变
        self._focus(hwnd)
        self._focused_at = time.time()

    def _launch_window(self):
        """开一个独立窗口（应用模式），不占用其它页面的标签页。"""
        exe = default_browser_exe()
        if not exe:
            try:
                webbrowser.open(URL)
            except Exception:
                logging.exception("快捷键打开浏览器失败")
            return
        name = os.path.basename(exe).lower()
        if name == "firefox.exe":
            args = ["-new-window", URL]
        else:
            args = ["--app=" + URL]
            if self._rect:
                x, y, w, h = self._rect
                args = ["--window-position=%d,%d" % (x, y),
                        "--window-size=%d,%d" % (w, h)] + args
        try:
            subprocess.Popen([exe] + args, close_fds=True)
        except Exception:
            logging.exception("启动独立窗口失败")

    def _open_dedicated(self):
        """打开独立窗口并记住它（下次只操作这一扇窗）。"""
        before = set(self._browser_windows())
        self._launch_window()
        deadline = time.time() + 10
        while time.time() < deadline:
            new = [h for h in self._browser_windows() if h not in before]
            if new:
                self._hwnd = new[0]
                return self._hwnd
            time.sleep(0.25)
        self._hwnd = self._find_browser_window()
        return self._hwnd

    def _open_async(self):
        """异步开窗：开窗要一两秒，期间再按快捷键不能又开一扇。"""
        if self._opening:
            self._pending = "hide"       # 正在开的时候又按了 → 等开出来直接收进托盘
            self._last += " (opening, pending hide)"
            return
        self._opening = True

        def worker():
            try:
                self._trace_add("open: launching (pending=%s)" % self._pending)
                hwnd = self._open_dedicated()
                if hwnd:
                    if self._pending == "hide":
                        self._pending = ""
                        self._hide(hwnd)
                        self._last = "open:%s → hide(pending)" % hwnd
                        self._trace_add("open: %s → hide(pending)" % hwnd)
                    else:
                        self._show(hwnd)
                        notice_bump()
                        self._last = "open:%s → show" % hwnd
                        self._trace_add("open: %s → show" % hwnd)
                else:
                    self._trace_add("open: 失败，没找到窗口")
            except Exception:
                logging.exception("打开独立窗口失败")
            finally:
                self._opening = False

        threading.Thread(target=worker, daemon=True).start()

    def _toggle(self):
        """按一次：唤起（跳到最上方）；再按一次：收进托盘。"""
        user32 = self._user32()
        hwnd = self._hwnd
        if not hwnd or not user32.IsWindow(hwnd):
            hwnd = self._find_browser_window()      # 之前开过但没记住 → 复用，别再开新的
            self._hwnd = hwnd
        if not hwnd:
            self._last = "open (launching)"
            self._open_async()
            return
        visible = bool(user32.IsWindowVisible(hwnd))
        fg = user32.GetForegroundWindow()
        fore = self._is_foreground(hwnd)
        recent = (time.time() - self._focused_at) < 2.0
        self._last = "toggle hwnd=%s vis=%s fg=%s fore=%s recent=%s" % (
            hwnd, visible, fg, fore, recent)
        self._trace_add(self._last)
        if visible and (fore or recent):
            self._hide(hwnd)                    # 正在看着它 → 收进托盘
            self._last += " → hide"
            self._trace_add("hide hwnd=%s visible_now=%s" % (
                hwnd, bool(user32.IsWindowVisible(hwnd))))
            return
        self._show(hwnd)                        # 唤起：原样显示 + 置前
        notice_bump()                           # 页面滚回最上方
        self._last += " → show"
        self._trace_add("show hwnd=%s visible_now=%s fg=%s" % (
            hwnd, bool(user32.IsWindowVisible(hwnd)), user32.GetForegroundWindow()))

    def _run(self):
        import ctypes
        from ctypes import wintypes
        user32 = self._user32()
        mods, vk = parse_hotkey(self.keys)
        if not mods or not vk:
            self.error = "快捷键写法不对，例如 Alt+S"
            return
        if not user32.RegisterHotKey(None, HOTKEY_ID, mods | MOD_NOREPEAT, vk):
            try:
                err = ctypes.WinError()
            except Exception:
                err = "未知错误"
            self.error = "注册失败：%s（可能已被别的程序占用）" % err
            self.enabled = False
            return
        self.enabled = True
        self.error = ""
        msg = wintypes.MSG()
        try:
            while not self._stop.is_set():
                r = user32.MsgWaitForMultipleObjects(0, None, False, 50, 0x0001)  # QS_ALLINPUT
                if r == 0xFFFFFFFF:
                    break
                while user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):      # PM_REMOVE
                    if msg.message == WM_HOTKEY:
                        try:
                            self._toggle()
                        except Exception:
                            logging.exception("快捷键处理失败")
                    elif msg.message == WM_QUIT:
                        self._stop.set()
        finally:
            try:
                user32.UnregisterHotKey(None, HOTKEY_ID)
            except Exception:
                pass
            self.enabled = False


HOTKEYS = HotkeyManager()


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
        if path == "/api/tasks":
            if not os.path.exists(TASKS):
                return self._send(404, "tasks.md not found")   # 前端会退回构建内副本
            return self._send(200, read_tasks())
        if path == "/api/draft":
            txt = read_draft()
            if txt is None:
                return self._send(404, "draft.md not found")
            return self._send(200, txt)
        if path == "/api/health":
            return self._json(200, {"ok": True, "app": APP_NAME, "version": APP_VERSION,
                                    "todo": os.path.exists(TODO)})
        if path == "/api/hotkey":
            return self._json(200, HOTKEYS.state())
        if path == "/api/notice":
            # 长轮询：快捷键唤起日程时通知页面滚回最上方
            q = urlparse(self.path).query
            since = 0
            for part in q.split("&"):
                if part.startswith("since="):
                    try:
                        since = int(part[6:])
                    except ValueError:
                        since = 0
            return self._json(200, {"seq": notice_wait(since), "reload": NOTICE_RELOAD})
        if path == "/api/config":
            cfg = load_cfg()
            pool = [{"id": p.get("id", ""), "name": p.get("name", ""),
                     "baseUrl": p.get("baseUrl", ""), "model": p.get("model", ""),
                     "hasKey": bool(p.get("apiKey"))} for p in cfg["providers"]]
            return self._json(200, {"active": cfg.get("active", ""), "providers": pool})
        if path == "/api/edits":
            d = load_edits()
            try:
                m = os.path.getmtime(EDITS)
            except OSError:
                m = 0
            return self._json(200, {"edits": d, "mtime": m})
        if path == "/api/schedule":
            # agent / 外部工具读这里：data 文件 + 页面增补合并后的有效数据
            return self._json(200, effective_schedule())
        if path == "/api/poll":
            # 页面每 4 秒来一次：todo 有变就重读；数据文件有变就先重建再报新页面时间戳
            rebuild_if_stale()
            _check_code_change()

            def mtime(p):
                try:
                    return os.path.getmtime(p)
                except OSError:
                    return 0
            return self._json(200, {"todo": mtime(TODO), "tasks": mtime(TASKS),
                                    "edits": mtime(EDITS),
                                    "draft": mtime(DRAFT),
                                    "code": built_code_id(),
                                    "html": mtime(os.path.join(DIST, "OpenSchedule.html"))})
        if path in ("/", "/index.html"):
            rebuild_if_stale()
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
        if path == "/api/tasks":
            try:
                write_tasks(body)
            except OSError as e:
                return self._send(500, "写入失败: %s" % e)
            return self._send(200, read_tasks())
        if path == "/api/draft":
            try:
                write_draft(body)
            except OSError as e:
                return self._send(500, "写入失败: %s" % e)
            return self._send(200, read_draft() or "")
        if path in ("/api/open", "/api/shutdown", "/api/edits", "/api/hotkey"):
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
            if path == "/api/edits":
                if not isinstance(incoming, dict) or len(body) > 1024 * 1024:
                    return self._json(400, {"ok": False, "error": "bad edits"})
                save_edits(incoming)
                try:
                    m = os.path.getmtime(EDITS)
                except OSError:
                    m = 0
                return self._json(200, {"ok": True, "mtime": m})
            if path == "/api/hotkey":
                if incoming.get("pause"):
                    HOTKEYS.pause()
                    st = HOTKEYS.state(); st["ok"] = True
                    return self._json(200, st)
                if incoming.get("resume"):
                    HOTKEYS.resume()
                    st = HOTKEYS.state(); st["ok"] = True
                    return self._json(200, st)
                try:
                    st = HOTKEYS.save(incoming.get("keys") or "")
                except ValueError as e:
                    return self._json(400, {"ok": False, "error": str(e)})
                st["ok"] = True
                return self._json(200, st)

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
    ensure_data()                          # 干净克隆/首跑：没有 data/ 就用示例播种
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
    if HOTKEYS.start():
        print("全局快捷键：%s（在任何软件里按一下唤起日程，再按一次切回）" % HOTKEYS.keys)
    print("OpenSchedule: http://127.0.0.1:%d/  (data: %s)" % (port, DATA))
    httpd.serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
