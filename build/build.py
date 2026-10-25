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
import io, os, re, sys, json, argparse, base64, datetime
from urllib.parse import quote

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# PyInstaller 打包后资源在解包目录里
if getattr(sys, "frozen", False):
    ROOT = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(sys.executable)))


def f(path):
    """本地路径 → file:// URL。"""
    p = os.path.abspath(path).replace("\\", "/")
    if not p.startswith("/"):
        p = "/" + p
    return "file://" + quote(p, safe="/:&=%#?~+,;")


# ---------------------------------------------------------------- schedule.md（数据源）
# 人可读、人可改的精炼格式；schedule.json 只在首次迁移时被读取（随后改名 .imported 留存）。
#
#   ## 2026-10-24
#   任务: 写论文 →DOCX
#   - 20:00 论文修改 [research] @2h | 改两节 | 定稿 | DOCX,CH4
#     - 子项一
#
# 段落按 | 顺序为：说明 / 产出 / 资料键（可省略段，但顺序固定）。
SCHED_HEADER = (
    "# OpenSchedule 日程数据源（本文件为人可编辑的最终数据源）\n"
    "# 每天一节：## YYYY-MM-DD\n"
    "# 任务行：任务: 文本 →资料键（→可省）\n"
    "# 时间块行：- HH:MM 标题 [类型] @时长 | 说明 | 产出 | 资料键1,键2（| 段可省，顺序固定；段内不要用 |）\n"
    "# 类型：study/life/research/rest；子项：时间块下一行缩进 \"- 文本\"\n")

_MD_TASK = re.compile(r"^任务[:：]\s*(.+?)\s*$")
_MD_TASK_LINK = re.compile(r"^(.*?)\s*→\s*([A-Za-z0-9_\-]+)$")
_MD_ITEM = re.compile(r"^[-*]\s+(\d{1,2})[:：](\d{2})\s+(.+)$")
_MD_SUB = re.compile(r"^[-*]\s+(.+)$")
_MD_HEAD = re.compile(r"^#{2,3}\s*(\d{4})-(\d{1,2})-(\d{1,2})\b")
_MD_TAIL = re.compile(r"^(.*?)(?:\s+\[([A-Za-z]+)\])?(?:\s+@(\S+))?$")


def parse_schedule_md(text):
    days = {}
    cur = None
    for raw in text.splitlines():
        s = raw.strip()
        if not s:
            continue
        m = _MD_HEAD.match(s)                    # 日期头要先于注释判断（## 也是 # 开头）
        if m:
            try:
                cur = datetime.date(int(m[1]), int(m[2]), int(m[3])).isoformat()
            except ValueError:
                cur = None
            if cur:
                days[cur] = {}
            continue
        if s.startswith("#"):
            continue
        tm = _MD_TASK.match(s)
        if tm and not re.match(r"^\d{1,2}[:：]\d{2}\s", tm[1]):
            t = tm[1]
            lk = _MD_TASK_LINK.match(t)
            if lk:
                days[cur].setdefault("tasks", []).append({"text": lk[1].strip(), "link": lk[2]})
            else:
                days[cur].setdefault("tasks", []).append(t)
            continue
        im = _MD_ITEM.match(s)
        if im:
            it = {"t": "%02d:%s" % (int(im[1]), im[2]),
                  "title": "", "type": "rest"}
            segs = [x.strip() for x in im[3].split("|")]
            hm = _MD_TAIL.match(segs[0])
            it["title"] = hm[1].strip() or "（无标题）"
            if hm[2]:
                it["type"] = TYPE_MD.get(hm[2], hm[2])
            if hm[3]:
                it["d"] = hm[3]
            if len(segs) > 1 and segs[1]:
                it["detail"] = segs[1]
            if len(segs) > 2 and segs[2]:
                it["out"] = segs[2]
            if len(segs) > 3 and segs[3]:
                it["links"] = [x for x in (y.strip() for y in segs[3].split(",")) if x]
            days[cur].setdefault("items", []).append(it)
            continue
        sm = _MD_SUB.match(s)
        if sm and days[cur].get("items"):
            days[cur]["items"][-1].setdefault("list", []).append(sm[1].strip())
    return days


TYPE_MD = {"study": "study", "life": "life", "research": "research", "rest": "rest",
           "class": "study", "must": "study", "gold": "research",
           "push": "research", "meet": "research", "red": "research"}


def _md_tmin(it):
    m = re.match(r"^(\d{1,2}):(\d{2})$", str(it.get("t", "")))
    return (int(m[1]) * 60 + int(m[2])) if m else 99999


def serialize_schedule_md(days):
    out = SCHED_HEADER.rstrip("\n").splitlines()
    for k in sorted(days):
        plan = days[k] or {}
        out.append("")
        out.append("## %s" % k)
        for t in plan.get("tasks") or []:
            if isinstance(t, dict):
                out.append("任务: %s%s" % (t.get("text", ""),
                                           (" →" + t["link"]) if t.get("link") else ""))
            else:
                out.append("任务: " + t)
        for it in sorted(plan.get("items") or [], key=_md_tmin):
            ty = TYPE_MD.get(str(it.get("type", "rest")), "rest")
            seg = "- %s %s [%s]" % (it.get("t", "??:??"), it.get("title", "（无标题）"), ty)
            if it.get("d"):
                seg += " @%s" % it["d"]
            tail = [it.get("detail", ""), it.get("out", ""),
                    ",".join(it.get("links") or [])]
            while tail and not tail[-1]:
                tail.pop()
            if tail:
                seg += " | " + " | ".join(x if x else "" for x in tail)
            out.append(seg)
            for s in it.get("list") or []:
                out.append("  - " + str(s))
    return "\n".join(out).rstrip("\n") + "\n"


def schedule_md_path(data_dir):
    return os.path.join(data_dir, "schedule.md")


def load_schedule(data_dir):
    """schedule.md 为数据源；只有它不存在时才从 schedule.json 一次性迁移。"""
    md = schedule_md_path(data_dir)
    if os.path.exists(md):
        return parse_schedule_md(io.open(md, encoding="utf-8").read())
    js = os.path.join(data_dir, "schedule.json")
    if os.path.exists(js):
        days = json.load(io.open(js, encoding="utf-8"))
        os.makedirs(data_dir, exist_ok=True)
        tmp = md + ".tmp"
        io.open(tmp, "w", encoding="utf-8", newline="\n").write(serialize_schedule_md(days))
        os.replace(tmp, md)
        os.replace(js, js + ".imported")     # 旧文件留档，避免回退到过期数据
        print("schedule.json 已迁移为 schedule.md（原文件改名 schedule.json.imported）")
        return days
    return {}


def save_schedule(data_dir, days):
    md = schedule_md_path(data_dir)
    os.makedirs(data_dir, exist_ok=True)
    tmp = md + ".tmp"
    io.open(tmp, "w", encoding="utf-8", newline="\n").write(serialize_schedule_md(days))
    os.replace(tmp, md)


# ---------------------------------------------------------------- 数据加载
def load_ddl(todo_path):
    """从 TODO LIST.md 解析 DDL。格式：- [ ] 10.25 任务名 / - [x] 12.25 任务名"""
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
        this_year = datetime.date.today().year
        if md:
            y, mo, da, task = int(md.group(1)), int(md.group(2)), int(md.group(3)), md.group(4)
        elif md2:
            y, mo, da, task = this_year, int(md2.group(1)), int(md2.group(2)), md2.group(3)
        else:
            continue
        ddl.append({
            "date": "%04d-%02d-%02d" % (y, mo, da),
            "ym": ("%d.%d" % (mo, da)) if y == this_year else ("%d.%d.%d" % (y, mo, da)),
            "task": task, "done": done,
        })
    return ddl


# ---------------------------------------------------------------- 任务安排（tasks.md）
# 没有明确 DDL、靠自己推进的事。一行一条，## 开头是分组标题。
#
#   ## 方向
#   - [ ] 整理导师清单
#   - [x] 简历定稿
_TASK_ITEM = re.compile(r"^\s*-\s*\[( |x|X)\]\s*(.+?)\s*$")


def load_tasks(tasks_path):
    """tasks.md → 任务安排列表 [{group, text, done}]；文件不存在就当空列表。"""
    out = []
    if not os.path.exists(tasks_path):
        return out
    group = ""
    for raw in io.open(tasks_path, encoding="utf-8").read().splitlines():
        s = raw.strip()
        if not s:
            continue
        if s.startswith("## "):
            group = s[3:].strip()
            continue
        if s.startswith("#"):
            continue
        m = _TASK_ITEM.match(s)
        if not m:
            continue
        out.append({"group": group, "text": m[2], "done": m[1].lower() == "x"})
    return out


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
    """schedule.md（或迁移前的 schedule.json）→ 前端 BAKED 结构。"""
    sched = load_schedule(data_dir)
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


def favicon_tag(root=None):
    """app-icon.png → data:image/png;base64，让浏览器标签页也使用同一个图标。"""
    p = os.path.join(root or ROOT, "app-icon.png")
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
def build(profile="personal", out=None, data_dir=None, root=None):
    """profile=personal 用 data_dir（默认 <root>/data），public 用 <root>/examples。

    data/root 也可以显式传入，供打包后的 exe 在任意数据目录上现场构建。"""
    root = root or ROOT
    data_dir = data_dir or os.path.join(root, "data" if profile == "personal" else "examples")
    auto_public = False
    # 干净 clone（没有数据源）时自动退到示例数据；md 与 json 任一存在即算有数据
    has_source = (os.path.exists(os.path.join(data_dir, "schedule.md"))
                  or os.path.exists(os.path.join(data_dir, "schedule.json")))
    if profile == "personal" and not has_source:
        print("data/ 不存在或不完整，改用 examples/ 生成脱敏示例版")
        profile, auto_public = "public", True
        data_dir = os.path.join(root, "examples")
    if not os.path.isdir(data_dir):
        raise SystemExit("找不到数据目录: " + data_dir)

    baked = build_schedule(data_dir)
    sidebar, quick, todo = build_links(data_dir)
    ddl = load_ddl(os.path.join(data_dir, "todo.md"))
    for d in ddl:
        d["link"] = f(todo) if todo else ""
    tasks = load_tasks(os.path.join(data_dir, "tasks.md"))

    tpl = io.open(os.path.join(root, "frontend", "index.html"), encoding="utf-8").read()
    css = io.open(os.path.join(root, "frontend", "assets", "app.css"), encoding="utf-8").read()
    app = io.open(os.path.join(root, "frontend", "assets", "app.js"), encoding="utf-8").read()

    baked_js = "const BAKED = " + json.dumps(baked, ensure_ascii=False, indent=1) + ";"
    ddl_js = "const DDL = " + json.dumps(ddl, ensure_ascii=False, indent=1) + ";"
    tasks_js = "const TASKS = " + json.dumps(tasks, ensure_ascii=False, indent=1) + ";"
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
    app = app.replace("/*__TASKS_BLOCK__*/", tasks_js)
    app = app.replace("/*__LINKS_BLOCK__*/", links_js)
    assert ("__BAKED_BLOCK__" not in app and "__DDL_BLOCK__" not in app
            and "__TASKS_BLOCK__" not in app and "__LINKS_BLOCK__" not in app)

    tpl = tpl.replace("<!--__FAVICON__-->", favicon_tag(root))
    assert "__FAVICON__" not in tpl
    tpl = tpl.replace("/*__CSS__*/", css).replace("/*__APP__*/", app)

    # 只有显式 --profile public 才写到 docs/example.html；
    # “缺 data 自动降级”必须仍写 dist/OpenSchedule.html，否则 serve.py 首页 404。
    if out is None:
        out = (os.path.join(root, "docs", "example.html")
               if profile == "public" and not auto_public
               else os.path.join(root, "dist", "OpenSchedule.html"))
    os.makedirs(os.path.dirname(out), exist_ok=True)
    tmp = out + ".tmp"
    io.open(tmp, "w", encoding="utf-8").write(tpl)
    os.replace(tmp, out)                    # 原子替换：CLI 与服务并发重建也不会写坏
    print("written:", out, os.path.getsize(out), "bytes")
    print("profile:", profile, "| days:", len(baked),
          "| 详细排期天数:", sum(1 for p in baked.values() if p.get("items")),
          "| ddl:", len(ddl), "| 任务安排:", len(tasks))
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="构建 OpenSchedule 单文件 HTML")
    ap.add_argument("--profile", choices=["personal", "public"], default="personal",
                    help="personal = 用 data/；public = 用 examples/（脱敏示例）")
    ap.add_argument("--out", help="输出路径，默认 dist/OpenSchedule.html")
    a = ap.parse_args()
    build(a.profile, a.out)
