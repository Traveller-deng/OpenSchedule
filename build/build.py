#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""OpenSchedule 构建器：frontend/ (通用前端) + data/ (个人数据) → dist/ 单文件 HTML。

用法：
    python build/build.py                     # 用 data/ 构建个人版
    python build/build.py --profile personal  # 同上
    python build/build.py --profile public    # 用 examples/ 构建脱敏示例版
    python build/build.py --out D:\\path\\x.html

设计要点：
  - frontend/ 完全不含个人信息，可以直接开源；
  - data/    是个人数据（课表、DDL、资料路径、习惯画像），已 .gitignore；
  - examples/ 是脱敏后的示例数据，随仓库公开。
"""
import io, os, re, json, argparse, base64
from urllib.parse import quote

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def f(path):
    """本地路径 → file:// URL。"""
    p = os.path.abspath(path).replace("\\", "/")
    if not p.startswith("/"):
        p = "/" + p
    return "file://" + quote(p, safe="/:&=%#?~+,;")


# ---------------------------------------------------------------- 数据加载
def load_ddl(todo_path):
    """从 TODO LIST.md 解析 DDL。格式：- [ ] 10.25 任务名 / - [x] 2027.1.4 任务名"""
    ddl = []
    if not os.path.exists(todo_path):
        return ddl
    for line in io.open(todo_path, encoding="utf-8").read().splitlines():
        m = re.match(r"^\s*-\s*\[( |x)\]\s*(.+?)\s*$", line)
        if not m:
            continue
        done = m.group(1).lower() == "x"
        rest = m.group(2)
        md = re.match(r"^(\d{4})\.(\d{1,2})\.(\d{1,2})\s+(.*)$", rest)
        md2 = re.match(r"^(\d{1,2})\.(\d{1,2})\s+(.*)$", rest)
        if md:
            y, mo, da, task = int(md.group(1)), int(md.group(2)), int(md.group(3)), md.group(4)
        elif md2:
            y, mo, da, task = 2026, int(md2.group(1)), int(md2.group(2)), md2.group(3)
        else:
            continue
        ddl.append({
            "date": "%04d-%02d-%02d" % (y, mo, da),
            "ym": ("%d.%d" % (mo, da)) if y == 2026 else ("%d.%d.%d" % (y, mo, da)),
            "task": task, "done": done,
        })
    return ddl


def resolve_links(spec, paths):
    """schedule.json 里的 links 数组 → 前端可直接用的 link 对象数组。"""
    out = []
    for l in spec or []:
        if isinstance(l, str):
            p = paths.get(l)
            if not p:
                continue
            out.append({"url": f(p["path"]), "path": p["path"],
                        "label": p.get("label", l), "kind": p.get("kind", "资料"), "mode": "app"})
        elif isinstance(l, dict) and l.get("inline"):
            out.append({"url": f(l.get("path", "")), "path": l.get("path", ""),
                        "label": l.get("label", ""), "kind": l.get("kind", "资料"),
                        "mode": l.get("mode", "app")})
    return out


def build_schedule(data_dir):
    """schedule.json → 前端 BAKED 结构。"""
    sched = json.load(io.open(os.path.join(data_dir, "schedule.json"), encoding="utf-8"))
    links_cfg = json.load(io.open(os.path.join(data_dir, "links.json"), encoding="utf-8"))
    paths = links_cfg.get("paths", {})

    out = {}
    for date, plan in sched.items():
        d = {}
        tasks = []
        for t in plan.get("tasks", []):
            if isinstance(t, str):
                tasks.append(t)
            else:
                lk = resolve_links([t["link"]] if t.get("link") else [], paths)
                if lk:
                    tasks.append({"t": t.get("text", ""), "link": lk[0]})
                else:
                    tasks.append(t.get("text", ""))
        if tasks:
            d["tasks"] = tasks
        items = []
        for it in plan.get("items", []):
            o = {"t": it["t"], "title": it["title"], "type": it["type"]}
            for k in ("d", "detail", "out", "list"):
                if it.get(k):
                    o[k] = it[k]
            lk = resolve_links(it.get("links"), paths)
            if lk:
                o["links"] = lk
            items.append(o)
        if items:
            d["items"] = items
        out[date] = d
    return out


def build_links(data_dir):
    """links.json → LINKS / QUICK_LINKS / P_TODO_URL。"""
    cfg = json.load(io.open(os.path.join(data_dir, "links.json"), encoding="utf-8"))
    paths = cfg.get("paths", {})

    sidebar = []
    for l in cfg.get("sidebar", []):
        p = paths.get(l.get("key"))
        if p:
            sidebar.append({"icon": l.get("icon", "🔗"), "label": l.get("label", ""),
                            "url": f(p["path"]), "path": p["path"], "mode": "app"})
        elif l.get("path"):
            sidebar.append({"icon": l.get("icon", "🔗"), "label": l.get("label", ""),
                            "url": f(l["path"]), "path": l["path"], "mode": l.get("mode", "app")})

    quick = []
    for k in cfg.get("quick", []):
        p = paths.get(k)
        if not p:
            continue
        quick.append({"short": p.get("short") or p.get("label", k),
                      "label": p.get("label", k),
                      "kind": p.get("kind", "资料"),
                      "url": f(p["path"]), "path": p["path"], "mode": "app"})

    todo = cfg.get("todo", "")
    return sidebar, quick, todo


def favicon_tag():
    """app-icon.png → data:image/png;base64，让浏览器标签页也使用同一个图标。"""
    p = os.path.join(ROOT, "app-icon.png")
    if not os.path.exists(p):
        return ""
    b64 = base64.b64encode(open(p, "rb").read()).decode("ascii")
    return ('<link rel="icon" type="image/png" sizes="256x256" '
            'href="data:image/png;base64,%s">' % b64)


def build_profile(data_dir):
    """profile.json → 前端 PROFILE 常量（个人习惯画像，供页面与维护者参考）。"""
    p = os.path.join(data_dir, "profile.json")
    if not os.path.exists(p):
        return {}
    return json.load(io.open(p, encoding="utf-8"))


# ---------------------------------------------------------------- 组装
def build(profile="personal", out=None):
    data_dir = os.path.join(ROOT, "data" if profile == "personal" else "examples")
    # 干净 clone（没有 data/）时自动退到示例数据，保证第一条命令就能跑通
    if profile == "personal" and not os.path.exists(os.path.join(data_dir, "schedule.json")):
        print("data/ 不存在或不完整，改用 examples/ 生成脱敏示例版")
        profile, data_dir = "public", os.path.join(ROOT, "examples")
    if not os.path.isdir(data_dir):
        raise SystemExit("找不到数据目录: " + data_dir)

    baked = build_schedule(data_dir)
    sidebar, quick, todo = build_links(data_dir)
    ddl = load_ddl(os.path.join(data_dir, "todo.md"))
    for d in ddl:
        d["link"] = f(todo) if todo else ""

    tpl = io.open(os.path.join(ROOT, "frontend", "index.html"), encoding="utf-8").read()
    css = io.open(os.path.join(ROOT, "frontend", "assets", "app.css"), encoding="utf-8").read()
    app = io.open(os.path.join(ROOT, "frontend", "assets", "app.js"), encoding="utf-8").read()

    baked_js = "const BAKED = " + json.dumps(baked, ensure_ascii=False, indent=1) + ";"
    ddl_js = "const DDL = " + json.dumps(ddl, ensure_ascii=False, indent=1) + ";"
    anchor = ""
    if profile == "public" and baked:
        anchor = sorted(baked.keys())[0]
    links_js = ("const BAKED_ANCHOR = " + json.dumps(anchor) + ";\n"
                "const P_TODO_URL = " + json.dumps(f(todo) if todo else "") + ";\n"
                "const LINKS = " + json.dumps(sidebar, ensure_ascii=False, indent=1) + ";\n"
                "const QUICK_LINKS = " + json.dumps(quick, ensure_ascii=False, indent=1) + ";\n"
                "const PROFILE = " + json.dumps(build_profile(data_dir), ensure_ascii=False, indent=1) + ";")

    app = app.replace("/*__BAKED_BLOCK__*/", baked_js)
    app = app.replace("/*__DDL_BLOCK__*/", ddl_js)
    app = app.replace("/*__LINKS_BLOCK__*/", links_js)
    assert "__BAKED_BLOCK__" not in app and "__DDL_BLOCK__" not in app and "__LINKS_BLOCK__" not in app

    tpl = tpl.replace("<!--__FAVICON__-->", favicon_tag())
    assert "__FAVICON__" not in tpl
    tpl = tpl.replace("/*__CSS__*/", css).replace("/*__APP__*/", app)

    out = out or (os.path.join(ROOT, "docs", "example.html") if profile == "public"
                  else os.path.join(ROOT, "dist", "OpenSchedule.html"))
    os.makedirs(os.path.dirname(out), exist_ok=True)
    io.open(out, "w", encoding="utf-8").write(tpl)
    print("written:", out, os.path.getsize(out), "bytes")
    print("profile:", profile, "| days:", len(baked),
          "| 详细排期天数:", sum(1 for p in baked.values() if p.get("items")),
          "| ddl:", len(ddl))
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="构建 OpenSchedule 单文件 HTML")
    ap.add_argument("--profile", choices=["personal", "public"], default="personal",
                    help="personal = 用 data/；public = 用 examples/（脱敏示例）")
    ap.add_argument("--out", help="输出路径，默认 dist/OpenSchedule.html")
    a = ap.parse_args()
    build(a.profile, a.out)
