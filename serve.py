#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""OpenSchedule 本地服务。

作用：
  1. 托管 dist/ 里的页面（用 http:// 打开，file:// 的限制就没有了）
  2. /api/todo    GET 读 data/todo.md ／ POST 写回
  3. /api/config  模型池的读写（data/agent.json，Key 不出现在响应里）
  4. /api/chat    用模型池里选中的模型回答问题，并带上当前日程作上下文

用法：
    python serve.py            启动并打开浏览器
    python serve.py --no-open  只启动服务
"""
import io, os, sys, json, threading, webbrowser, urllib.request, urllib.error
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

ROOT = os.path.dirname(os.path.abspath(__file__))
DIST = os.path.join(ROOT, "dist")
TODO = os.environ.get("SCHED_TODO") or os.path.join(ROOT, "data", "todo.md")
CONFIG = os.path.join(ROOT, "data", "agent.json")
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
        sys.path.insert(0, os.path.join(ROOT, "build"))
        import build as B
        baked = B.build_schedule(os.path.join(ROOT, "data"))
        today = __import__("datetime").date.today().isoformat()
        plan = baked.get(today) or {}
        if plan.get("tasks"):
            lines.append("今天主要任务：" + "；".join([t if isinstance(t, str) else t.get("t", "") for t in plan["tasks"]]))
        items = plan.get("items") or []
        if items:
            lines.append("今天时间安排：" + "；".join("%s %s" % (i.get("t", ""), i.get("title", "")) for i in items))
    except Exception:
        pass
    return "\n".join(lines)


def chat_reply(message, history):
    cfg = load_cfg()
    prov = active_provider(cfg)
    if not prov or not prov.get("apiKey"):
        return {"error": "还没有可用的模型，点输入框右边的 ⚙ 配一个。"}
    ctx = context_text()
    system = ("你是「每日安排」这个日程应用里的助手。今天是 %s。\n%s\n"
              "回答用中文，简短、具体、直接给结论；需要调整安排时给出可执行的建议（时间点 + 事项）。"
              "不要编造数据里没有的条目。") % (
              __import__("datetime").date.today().isoformat(), ctx or "（暂无数据）")
    msgs = [{"role": "system", "content": system}]
    for m in (history or [])[-8:]:
        if m.get("role") in ("user", "assistant") and m.get("content"):
            msgs.append({"role": m["role"], "content": m["content"]})
    msgs.append({"role": "user", "content": message})
    url = (prov.get("baseUrl") or "").rstrip("/") + "/chat/completions"
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
PORT = int(os.environ.get("SCHED_PORT") or 8123)
URL = "http://127.0.0.1:%d/" % PORT


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


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        kw["directory"] = DIST
        super().__init__(*a, **kw)

    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="text/plain; charset=utf-8"):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/api/todo":
            return self._send(200, read_todo())
        if path == "/api/health":
            return self._send(200, json.dumps({"ok": True, "todo": os.path.exists(TODO)}), "application/json")
        if path == "/api/config":
            cfg = load_cfg()
            pool = [{"id": p.get("id", ""), "name": p.get("name", ""),
                     "baseUrl": p.get("baseUrl", ""), "model": p.get("model", ""),
                     "hasKey": bool(p.get("apiKey"))} for p in cfg["providers"]]
            return self._send(200, json.dumps({"active": cfg.get("active", ""), "providers": pool},
                                              ensure_ascii=False), "application/json")
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
            return self._send(200, json.dumps({"ok": True, "count": len(pool)}),
                              "application/json")
        if path == "/api/chat":
            try:
                incoming = json.loads(body or "{}")
            except Exception:
                return self._send(400, json.dumps({"error": "bad json"}, ensure_ascii=False), "application/json")
            out = chat_reply((incoming.get("message") or "").strip(), incoming.get("history") or [])
            return self._send(200, json.dumps(out, ensure_ascii=False), "application/json")
        return self._send(404, "not found")


def main():
    open_browser = "--no-open" not in sys.argv and os.environ.get("SCHED_NO_OPEN") != "1"
    try:
        httpd = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    except OSError:
        if open_browser:
            webbrowser.open(URL)
        return
    if open_browser:
        threading.Timer(0.5, lambda: webbrowser.open(URL)).start()
    print("OpenSchedule:", URL)
    httpd.serve_forever()


if __name__ == "__main__":
    main()
