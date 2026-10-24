#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""OpenSchedule CLI —— 页面里能改的数据，这里都能改，写完自动重建页面。

给 AI 编码助手（dsh / Claude Code / ZCode 等）与脚本使用。先 `day show` 看清现状，
再用具体命令修改；所有写操作都会校验格式，非法输入不会落盘。

源码运行： python cli.py <命令> …
安装版：   OpenSchedule 目录下 schedule.exe <命令> …

数据（人可直接看/改的文件，均在数据目录 data 目录下）：
  schedule.md  时间表+任务明细（数据源）   todo.md   DDL
  draft.md     草稿                        links.json 资料路径/入口
  edits.json   页面上的增改覆盖层           agent.json 模型池
服务运行时页面会自动感知这里的修改（todo/草稿/覆盖层约 4 秒并入，其余弹提示刷新）。

日期：today / tomorrow / YYYY-MM-DD；DDL 日期：MM.DD（当年）或 YYYY.M.D；
时间：HH:MM；类型：study 学习 / life 生活 / research 科研 / rest 缓冲。
"""
import argparse
import datetime
import io
import json
import os
import re
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

if not getattr(sys, "frozen", False):
    _ROOT = os.path.dirname(os.path.abspath(__file__))
    if _ROOT not in sys.path:
        sys.path.insert(0, _ROOT)
    # build/ 目录里有 build.py 模块；插到最前，避免被根目录同名目录当成命名空间包
    _BUILD_DIR = os.path.join(_ROOT, "build")
    if os.path.isdir(_BUILD_DIR):
        sys.path.insert(0, _BUILD_DIR)

import serve        # noqa: E402
import build as B   # noqa: E402

TYPE_ALIAS = {"class": "study", "must": "study", "gold": "research",
              "push": "research", "meet": "research", "red": "research"}
TYPES = {"study": "学习", "life": "生活", "research": "科研", "rest": "缓冲"}
WEEK = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]


def die(msg, code=2):
    print("错误：%s" % msg, file=sys.stderr)
    raise SystemExit(code)


def out(*a):
    print(*a)


# ---------------------------------------------------------------- 基础读写
def load_json(path, default):
    try:
        with io.open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def save_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with io.open(tmp, "w", encoding="utf-8", newline="\n") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def links_path():
    return os.path.join(serve.DATA, "links.json")


def sched_days():
    try:
        return B.load_schedule(serve.DATA)
    except Exception as e:
        die("读取 schedule.md 失败：%s" % e)


def save_sched_days(days):
    B.save_schedule(serve.DATA, days)


def after_write():
    """写操作收尾：数据变了就重建页面（服务在跑时页面会自动感知）。"""
    if serve.rebuild_if_stale():
        out("（页面已重建，打开中的页面会提示刷新）")


# ---------------------------------------------------------------- 解析
def norm_date(s):
    s = str(s).strip().lower()
    today = datetime.date.today()
    if s in ("today", "今天", "今"):
        return today.isoformat()
    if s in ("tomorrow", "明天", "明日"):
        return (today + datetime.timedelta(days=1)).isoformat()
    if s in ("yesterday", "昨天", "昨日"):
        return (today - datetime.timedelta(days=1)).isoformat()
    m = re.match(r"^(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})$", s)
    if not m:
        die("日期格式应为 YYYY-MM-DD（或 today/tomorrow），收到：%r" % s)
    try:
        return datetime.date(int(m[1]), int(m[2]), int(m[3])).isoformat()
    except ValueError as e:
        die("日期不合法：%r（%s）" % (s, e))


def norm_time(s):
    m = re.match(r"^(\d{1,2})[:：](\d{1,2})$", str(s).strip())
    if not m or not (0 <= int(m[1]) <= 23 and 0 <= int(m[2]) <= 59):
        die("时间格式应为 HH:MM，收到：%r" % s)
    return "%02d:%02d" % (int(m[1]), int(m[2]))


def norm_type(s):
    t = TYPE_ALIAS.get(str(s).strip().lower(), str(s).strip().lower())
    if t not in TYPES:
        die("类型只能是 %s，收到：%r" % ("/".join(TYPES), s))
    return t


def norm_ddl_date(s):
    s = str(s).strip()
    m = re.match(r"^(\d{4})\.(\d{1,2})\.(\d{1,2})$", s)
    if m:
        try:
            datetime.date(int(m[1]), int(m[2]), int(m[3]))
        except ValueError as e:
            die("日期不合法：%r（%s）" % (s, e))
        return "%d.%d.%d" % (int(m[1]), int(m[2]), int(m[3]))
    m = re.match(r"^(\d{1,2})\.(\d{1,2})$", s)
    if m:
        y = datetime.date.today().year
        try:
            datetime.date(y, int(m[1]), int(m[2]))
        except ValueError as e:
            die("日期不合法：%r（%s）" % (s, e))
        return "%d.%d" % (int(m[1]), int(m[2]))
    die("DDL 日期格式应为 MM.DD 或 YYYY.M.D，收到：%r" % s)


def task_text(t):
    return t if isinstance(t, str) else (t.get("text") or t.get("t") or "")


# ---------------------------------------------------------------- DDL（todo.md）
DDL_LINE = re.compile(r"^(\s*-\s*\[( |x|X)\]\s*)(.+?)\s*$")


def ddl_lines():
    try:
        return io.open(serve.TODO, encoding="utf-8").read().splitlines()
    except OSError:
        return ["# TODO LIST", ""]


def save_ddl_lines(lines):
    os.makedirs(os.path.dirname(serve.TODO), exist_ok=True)
    tmp = serve.TODO + ".tmp"
    with io.open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines).rstrip("\n") + "\n")
    os.replace(tmp, serve.TODO)


def ddl_entries(lines):
    ents = []
    for i, ln in enumerate(lines):
        m = DDL_LINE.match(ln)
        if not m:
            continue
        dm = re.match(r"^((?:\d{4})?(?:\.\d{1,2}){1,2}|\d{1,2}\.\d{1,2})\s+(.*)$", m[3])
        if not dm:
            continue
        ents.append((i, m[2].lower() == "x", dm[1], dm[2]))
    return ents


def pick_ddl(lines, ident):
    ents = ddl_entries(lines)
    if not ents:
        die("todo.md 里还没有 DDL")
    if str(ident).isdigit():
        n = int(ident)
        if not 1 <= n <= len(ents):
            die("序号超出范围 1-%d，先 ddl list 查看" % len(ents))
        return ents[n - 1]
    hits = [e for e in ents if str(ident) in e[3]]
    if len(hits) != 1:
        die("关键词 %r 匹配到 %d 条（需唯一），用 ddl list 查看后按序号选择" % (ident, len(hits)))
    return hits[0]


def cmd_ddl_list(a):
    ents = ddl_entries(ddl_lines())
    if not ents:
        return out("（todo.md 里还没有 DDL）")
    for n, (i, done, ds, text) in enumerate(ents, 1):
        out("%3d [%s] %s %s" % (n, "x" if done else " ", ds, text))


def cmd_ddl_add(a):
    ds = norm_ddl_date(a.date)
    lines = ddl_lines()
    lines.append("- [ ] %s %s" % (ds, a.text))
    save_ddl_lines(lines)
    out("已添加：%s %s" % (ds, a.text))
    after_write()


def cmd_ddl_setdone(a, done):
    lines = ddl_lines()
    i, _, ds, text = pick_ddl(lines, a.ident)
    lines[i] = "- [%s] %s %s" % ("x" if done else " ", ds, text)
    save_ddl_lines(lines)
    out("已标记为%s：%s %s" % ("已完成" if done else "未完成", ds, text))
    after_write()


def cmd_ddl_edit(a):
    lines = ddl_lines()
    i, _, ds, _ = pick_ddl(lines, a.ident)
    m = DDL_LINE.match(lines[i])
    new_date = norm_ddl_date(a.date) if a.date else ds
    parts = m[3].split(" ", 1)
    new_text = a.text if a.text is not None else (parts[1] if len(parts) > 1 else parts[0])
    box = "x" if m[2].lower() == "x" else " "
    lines[i] = "- [%s] %s %s" % (box, new_date, new_text)
    save_ddl_lines(lines)
    out("已改为：%s %s" % (new_date, new_text))
    after_write()


def cmd_ddl_remove(a):
    lines = ddl_lines()
    i, _, ds, text = pick_ddl(lines, a.ident)
    del lines[i]
    save_ddl_lines(lines)
    out("已删除：%s %s" % (ds, text))
    after_write()


# ---------------------------------------------------------------- 日视图 / 时间块
def effective():
    try:
        return serve.effective_schedule()
    except Exception as e:
        die("读取数据失败：%s" % e)


def fmt_item(n, it):
    s = "%d. %s  %s [%s]" % (n, it.get("t", "??:??"), it.get("title", "（无标题）"),
                             TYPES.get(it.get("type"), it.get("type", "?")))
    tags = []
    if it.get("d"):
        tags.append("时长=%s" % it["d"])
    if it.get("detail"):
        tags.append("说明=%s" % it["detail"])
    if it.get("out"):
        tags.append("产出=%s" % it["out"])
    if it.get("links"):
        tags.append("资料=%s" % ",".join(
            (l.get("label") or l.get("path", "?")) if isinstance(l, dict) else str(l)
            for l in it["links"]))
    if it.get("src") == "user":
        tags.append("页面添加")
    elif it.get("edited"):
        tags.append("页面修改过")
    if it.get("list"):
        tags.append("子项%d条" % len(it["list"]))
    return s + ("  " + "；".join(tags) if tags else "")


def cmd_day_show(a):
    k = norm_date(a.date) if a.date else datetime.date.today().isoformat()
    plan = effective().get(k)
    d = datetime.date.fromisoformat(k)
    out("%s %s" % (k, WEEK[d.weekday()]))
    if not plan or (not plan.get("tasks") and not plan.get("items")):
        return out("（这天没有安排）")
    done = plan.get("tasksDone") or {}
    tasks = plan.get("tasks") or []
    if tasks:
        out("主要任务：")
        for i, t in enumerate(tasks, 1):
            txt = task_text(t)
            lk = t.get("link") if isinstance(t, dict) else None
            out("  %d [%s] %s%s" % (i, "x" if done.get(txt) else " ", txt,
                                    "  →" + lk if lk else ""))
    else:
        out("主要任务：（无）")
    items = plan.get("items") or []
    if items:
        out("时间安排：")
        order = sorted(items, key=B._md_tmin)
        for n, it in enumerate(order, 1):
            out("  " + fmt_item(n, it))
    else:
        out("时间安排：（无）")


def find_item(items, ident):
    s = str(ident).strip()
    if re.match(r"^\d{1,2}:\d{2}$", s):
        t = norm_time(s)
        matches = [i for i, it in enumerate(items) if it.get("t") == t]
    elif s.isdigit():
        n = int(s)
        matches = [n - 1] if 1 <= n <= len(items) else []
    else:
        die("定位参数应为序号或 HH:MM，收到：%r" % ident)
        return None
    if len(matches) != 1:
        for n, it in enumerate(items, 1):
            out("  " + fmt_item(n, it))
        die("按 %r 定位到 %d 条（需唯一）" % (ident, len(matches)))
    return matches[0]


def check_link_keys(keys):
    if not keys:
        return []
    paths = load_json(links_path(), {}).get("paths") or {}
    for lk in keys:
        if lk not in paths:
            die("资料键名 %r 不在 links.json paths 里；可用：%s（用 path set 添加）"
                % (lk, "、".join(sorted(paths)) or "（空）"))
    return list(keys)


def cmd_block_add(a):
    k = norm_date(a.date)
    t = norm_time(a.time)
    ty = norm_type(a.type)
    days = sched_days()
    items = days.setdefault(k, {}).setdefault("items", [])
    if any(it.get("t") == t for it in items):
        die("%s 已有 %s 的时间块；要改它用 block set" % (k, t))
    it = {"t": t, "title": a.title, "type": ty}
    if a.d:
        it["d"] = a.d
    if a.detail:
        it["detail"] = a.detail
    if a.out:
        it["out"] = a.out
    links = check_link_keys(a.link)
    if links:
        it["links"] = links
    items.append(it)
    items.sort(key=B._md_tmin)
    save_sched_days(days)
    out("已添加：%s" % fmt_item(items.index(it) + 1, it))
    after_write()


def cmd_block_set(a):
    k = norm_date(a.date)
    days = sched_days()
    items = (days.get(k) or {}).get("items")
    if items is None:
        die("%s 没有时间块" % k)
    i = find_item(items, a.ident)
    it = items[i]
    changed = []
    if a.time:
        it["t"] = norm_time(a.time)
        changed.append("时间→%s" % it["t"])
    if a.title is not None:
        it["title"] = a.title
        changed.append("标题→%s" % a.title)
    if a.type:
        it["type"] = norm_type(a.type)
        changed.append("类型→%s" % it["type"])
    if a.d is not None:
        changed.append("时长→%s" % a.d if a.d else "时长清除")
        if a.d:
            it["d"] = a.d
        else:
            it.pop("d", None)
    if a.detail is not None:
        changed.append("说明→%s" % a.detail if a.detail else "说明清除")
        if a.detail:
            it["detail"] = a.detail
        else:
            it.pop("detail", None)
    if a.out is not None:
        changed.append("产出→%s" % a.out if a.out else "产出清除")
        if a.out:
            it["out"] = a.out
        else:
            it.pop("out", None)
    if not changed:
        die("没有提供要修改的字段（--time/--title/--type/--d/--detail/--out）")
    items.sort(key=B._md_tmin)
    save_sched_days(days)
    out("已修改：%s（%s）" % (it.get("title", ""), "，".join(changed)))
    after_write()


def cmd_block_remove(a):
    k = norm_date(a.date)
    days = sched_days()
    items = (days.get(k) or {}).get("items")
    if items is None:
        die("%s 没有时间块" % k)
    i = find_item(items, a.ident)
    it = items.pop(i)
    save_sched_days(days)
    out("已删除：%s %s %s" % (k, it.get("t", ""), it.get("title", "")))
    after_write()


# ---------------------------------------------------------------- 任务组
def strip_overlay_tasks(k):
    """CLI 写文件层后摘掉页面的任务覆盖，保证文件内容就是页面显示的内容。"""
    ed = serve.load_edits()
    sec = (ed.get("sections") or {}).get(k)
    if isinstance(sec, dict) and "tasks" in sec:
        del sec["tasks"]
        if not sec:
            ed["sections"].pop(k, None)
        serve.save_edits(ed)


def cmd_task_add(a):
    k = norm_date(a.date)
    check_link_keys([a.link] if a.link else [])
    days = sched_days()
    tasks = days.setdefault(k, {}).setdefault("tasks", [])
    tasks.append({"text": a.text, "link": a.link} if a.link else a.text)
    save_sched_days(days)
    strip_overlay_tasks(k)
    out("已添加任务：%s（%s）" % (a.text, k))
    after_write()


def cmd_task_remove(a):
    k = norm_date(a.date)
    days = sched_days()
    tasks = (days.get(k) or {}).get("tasks")
    if not tasks:
        die("%s 没有主要任务" % k)
    if str(a.ident).isdigit():
        n = int(a.ident)
        if not 1 <= n <= len(tasks):
            die("序号超出范围 1-%d" % len(tasks))
        i = n - 1
    else:
        hits = [j for j, t in enumerate(tasks) if str(a.ident) in task_text(t)]
        if len(hits) != 1:
            die("关键词 %r 匹配到 %d 条（需唯一）" % (a.ident, len(hits)))
        i = hits[0]
    txt = task_text(tasks[i])
    del tasks[i]
    if not tasks:
        del days[k]["tasks"]
    save_sched_days(days)
    strip_overlay_tasks(k)
    out("已删除任务：%s（%s）" % (txt, k))
    after_write()


def cmd_task_setdone(a, done):
    """完成标记按任务文本存于覆盖层（与页面同一存储，页面约 4 秒自动同步）。"""
    k = norm_date(a.date)
    plan = effective().get(k) or {}
    tasks = plan.get("tasks") or []
    if not tasks:
        die("%s 没有主要任务" % k)
    if str(a.ident).isdigit():
        n = int(a.ident)
        if not 1 <= n <= len(tasks):
            die("序号超出范围 1-%d" % len(tasks))
        txt = task_text(tasks[n - 1])
    else:
        hits = [task_text(t) for t in tasks if str(a.ident) in task_text(t)]
        if len(hits) != 1:
            die("关键词 %r 匹配到 %d 条（需唯一）" % (a.ident, len(hits)))
        txt = hits[0]
    ed = serve.load_edits()
    td = ed.setdefault("tasksDone", {}).setdefault(k, {})
    if done:
        td[txt] = True
    else:
        td.pop(txt, None)
        if not td:
            ed.get("tasksDone", {}).pop(k, None)
    serve.save_edits(ed)
    out("任务已标记为%s：%s（%s）" % ("已完成" if done else "未完成", txt, k))


# ---------------------------------------------------------------- links.json
def load_links():
    d = load_json(links_path(), {})
    for key in ("paths", "sidebar", "quick"):
        d.setdefault(key, {} if key == "paths" else [])
    return d


def cmd_path_list(a):
    paths = load_links()["paths"]
    if not paths:
        return out("（paths 为空，用 path set 键名 路径 添加）")
    for key, p in sorted(paths.items()):
        out("%-10s [%s] %s" % (key, p.get("kind", ""), p.get("path", "")))
        extra = ", ".join(x for x in ("label=%s" % p.get("label", ""),
                                      "short=%s" % p.get("short", "")) if not x.endswith("="))
        if extra:
            out("             %s" % extra)


def cmd_path_set(a):
    d = load_links()
    p = d["paths"].get(a.key) or {}
    p["path"] = a.path
    if a.label:
        p["label"] = a.label
    if a.kind:
        p["kind"] = a.kind
    if a.short:
        p["short"] = a.short
    p.setdefault("label", a.key)
    d["paths"][a.key] = p
    save_json(links_path(), d)
    out("已保存：%s → %s" % (a.key, a.path))
    after_write()


def cmd_path_remove(a):
    d = load_links()
    if a.key not in d["paths"]:
        die("paths 里没有 %r" % a.key)
    del d["paths"][a.key]
    refs = [k for k in d["quick"] if k == a.key] + \
           [s.get("key") for s in d["sidebar"] if s.get("key") == a.key]
    save_json(links_path(), d)
    out("已删除路径 %s" % a.key)
    if refs:
        out("注意：quick/sidebar 仍引用 %s，日程里引用它的链接将不再解析" % ",".join(map(str, refs)))
    after_write()


def cmd_quick_add(a):
    d = load_links()
    if a.key not in d["paths"]:
        die("paths 里没有 %r，先用 path set" % a.key)
    if a.key in d["quick"]:
        return out("%s 已在常用入口里" % a.key)
    d["quick"].append(a.key)
    save_json(links_path(), d)
    out("已加入常用入口：%s" % a.key)
    after_write()


def cmd_quick_remove(a):
    d = load_links()
    if a.key not in d["quick"]:
        die("常用入口里没有 %r" % a.key)
    d["quick"].remove(a.key)
    save_json(links_path(), d)
    out("已从常用入口移除：%s" % a.key)
    after_write()


def cmd_sidebar_add(a):
    d = load_links()
    if a.key not in d["paths"]:
        die("paths 里没有 %r，先用 path set" % a.key)
    if any(s.get("key") == a.key for s in d["sidebar"]):
        return out("%s 已在左栏入口里" % a.key)
    d["sidebar"].append({"icon": a.icon or "🔗", "label": a.label or
                         d["paths"][a.key].get("label", a.key), "key": a.key})
    save_json(links_path(), d)
    out("已加入左栏入口：%s" % a.key)
    after_write()


def cmd_sidebar_remove(a):
    d = load_links()
    before = len(d["sidebar"])
    d["sidebar"] = [s for s in d["sidebar"] if s.get("key") != a.key]
    if len(d["sidebar"]) == before:
        die("左栏入口里没有 %r" % a.key)
    save_json(links_path(), d)
    out("已从左栏入口移除：%s" % a.key)
    after_write()


# ---------------------------------------------------------------- 草稿（draft.md）
def draft_path():
    return os.path.join(serve.DATA, "draft.md")


def cmd_draft_show(a):
    try:
        out(io.open(draft_path(), encoding="utf-8").read().rstrip("\n"))
    except OSError:
        out("（draft.md 为空或不存在）")


def cmd_draft_set(a):
    text = None
    if a.text is not None:
        text = a.text
    elif a.file:
        text = io.open(a.file, encoding="utf-8").read()
    else:
        text = sys.stdin.read()
    if text is None:
        die("没有内容：用 --text、--file 或管道传入")
    os.makedirs(serve.DATA, exist_ok=True)
    tmp = draft_path() + ".tmp"
    with io.open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(text.rstrip("\n") + "\n")
    os.replace(tmp, draft_path())
    out("草稿已写入（页面约 4 秒内自动同步）")


def cmd_draft_append(a):
    old = ""
    try:
        old = io.open(draft_path(), encoding="utf-8").read()
    except OSError:
        pass
    os.makedirs(serve.DATA, exist_ok=True)
    tmp = draft_path() + ".tmp"
    with io.open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(old.rstrip("\n") + ("\n" if old.strip() else "") + a.text + "\n")
    os.replace(tmp, draft_path())
    out("已追加一行")


def cmd_draft_clear(a):
    try:
        os.remove(draft_path())
        out("草稿已清空")
    except OSError:
        out("草稿本就为空")


# ---------------------------------------------------------------- 模型池
def cmd_provider_list(a):
    cfg = serve.load_cfg()
    if not cfg["providers"]:
        return out("（模型池为空，页面聊天框 ⚙ 或 provider add 添加）")
    act = cfg.get("active")
    for p in cfg["providers"]:
        out("%s%-6s %-12s %-32s model=%-20s key=%s"
            % ("*" if p.get("id") == act else " ", p.get("id", ""),
               p.get("name", ""), p.get("baseUrl", ""),
               p.get("model", ""), "有" if p.get("apiKey") else "无"))


def cmd_provider_use(a):
    cfg = serve.load_cfg()
    p = next((x for x in cfg["providers"]
              if x.get("id") == a.ident or x.get("name") == a.ident), None)
    if not p:
        die("没有 id/名称为 %r 的模型，用 provider list 查看" % a.ident)
    cfg["active"] = p["id"]
    serve.save_cfg(cfg)
    out("已切换到：%s（%s）" % (p.get("name") or p["id"], p.get("model", "")))


def cmd_provider_add(a):
    base = (a.base_url or "").rstrip("/")
    if not re.match(r"^https?://", base):
        die("baseUrl 应以 http/https 开头，收到：%r" % a.base_url)
    err = serve._provider_url_error(base)
    if err:
        die("baseUrl 不合规：%s" % err)
    key = ""
    if a.key_stdin:
        import getpass
        out("粘贴 API Key 后回车（不回显）：")
        key = getpass.getpass("").strip() if sys.stdin.isatty() else sys.stdin.readline().strip()
    cfg = serve.load_cfg()
    n = 1
    while any(p.get("id") == "p%d" % n for p in cfg["providers"]):
        n += 1
    prov = {"id": "p%d" % n, "name": a.name, "baseUrl": base, "model": a.model, "apiKey": key}
    cfg["providers"].append(prov)
    if not cfg.get("active"):
        cfg["active"] = prov["id"]
    serve.save_cfg(cfg)
    out("已添加：%s（%s）%s" % (a.name, a.model, "并设为当前" if cfg["active"] == prov["id"] else ""))


def cmd_provider_remove(a):
    cfg = serve.load_cfg()
    p = next((x for x in cfg["providers"]
              if x.get("id") == a.ident or x.get("name") == a.ident), None)
    if not p:
        die("没有 id/名称为 %r 的模型" % a.ident)
    cfg["providers"].remove(p)
    if cfg.get("active") == p.get("id"):
        cfg["active"] = cfg["providers"][0]["id"] if cfg["providers"] else ""
    serve.save_cfg(cfg)
    out("已删除：%s" % (p.get("name") or p.get("id")))


# ---------------------------------------------------------------- 其它
def cmd_open(a):
    ok, err = serve.open_path(a.path)
    if not ok:
        die(err)
    out("已用系统默认程序打开：%s" % a.path)


def cmd_rebuild(a):
    out("页面已重建。" if serve.rebuild_if_stale() else "页面已是最新，无需重建。")


def cmd_status(a):
    out("OpenSchedule %s（%s）" % (serve.APP_VERSION,
                                  "exe" if getattr(sys, "frozen", False) else "源码"))
    out("数据目录: %s" % serve.DATA)
    for name in ("schedule.md", "todo.md", "draft.md", "links.json",
                 "edits.json", "agent.json", "schedule.json.imported"):
        p = os.path.join(serve.DATA, name)
        out("  %-24s %s" % (name, "%d B" % os.path.getsize(p) if os.path.exists(p) else "—"))
    html = os.path.join(serve.DIST, "OpenSchedule.html")
    out("页面: %s" % ("已构建" if os.path.exists(html) else "未构建（访问时自动构建）"))
    port = serve.PORT
    try:
        st = load_json(os.path.join(os.path.dirname(serve.DATA.rstrip("\\/")), "state.json"), {})
        if isinstance(st.get("port"), int):
            port = st["port"]
    except Exception:
        pass
    out("服务: %s" % ("运行中 http://127.0.0.1:%d/" % port if serve.is_ours_running(port)
                      else "未运行（启动 OpenSchedule.exe 或 python serve.py 开启）"))
    eff = effective()
    ddl = len(ddl_entries(ddl_lines()))
    out("数据: %d 天有安排，DDL %d 条" % (len(eff), ddl))


# ---------------------------------------------------------------- 参数装配
def sp(parent, name, help_):
    d = parent.add_subparsers(dest="action", required=True)
    return lambda: d.add_parser(name, help=help_)


def build_parser():
    p = argparse.ArgumentParser(prog="schedule", description="OpenSchedule 命令行",
                                formatter_class=argparse.RawDescriptionHelpFormatter,
                                epilog="数据文件都在 data\\ 下，人可直接编辑；"
                                       "本 CLI 的价值是校验格式+改完自动重建页面。")
    sub = p.add_subparsers(dest="group", required=True)

    g = sub.add_parser("ddl", help="DDL 看板（todo.md）").add_subparsers(dest="action", required=True)
    g.add_parser("list", help="列出全部").set_defaults(fn=cmd_ddl_list)
    x = g.add_parser("add", help="新增")
    x.add_argument("date", help="MM.DD 或 YYYY.M.D")
    x.add_argument("text")
    x.set_defaults(fn=cmd_ddl_add)
    for name, done, h in (("done", True, "标记完成"), ("undo", False, "取消完成标记")):
        x = g.add_parser(name, help=h)
        x.add_argument("ident", help="序号或文本关键词")
        x.set_defaults(fn=lambda a, _d=done: cmd_ddl_setdone(a, _d))
    x = g.add_parser("edit", help="改日期/文本")
    x.add_argument("ident")
    x.add_argument("--date", help="新日期")
    x.add_argument("--text", help="新文本")
    x.set_defaults(fn=cmd_ddl_edit)
    x = g.add_parser("remove", help="删除")
    x.add_argument("ident")
    x.set_defaults(fn=cmd_ddl_remove)

    g = sub.add_parser("day", help="查看某天（含页面上的本地增补）").add_subparsers(dest="action", required=True)
    x = g.add_parser("show")
    x.add_argument("date", nargs="?", help="默认 today")
    x.set_defaults(fn=cmd_day_show)

    g = sub.add_parser("block", help="时间块（schedule.md）").add_subparsers(dest="action", required=True)
    x = g.add_parser("add", help="新增")
    x.add_argument("date")
    x.add_argument("time", help="HH:MM")
    x.add_argument("title")
    x.add_argument("type", help="study/life/research/rest")
    x.add_argument("--d", help="时长，如 1h / 45min")
    x.add_argument("--detail", help="说明")
    x.add_argument("--out", help="产出")
    x.add_argument("--link", action="append", help="资料键名，可多次")
    x.set_defaults(fn=cmd_block_add)
    x = g.add_parser("set", help="修改")
    x.add_argument("date")
    x.add_argument("ident", help="序号（day show 里）或 HH:MM")
    x.add_argument("--time"), x.add_argument("--title")
    x.add_argument("--type"), x.add_argument("--d")
    x.add_argument("--detail"), x.add_argument("--out")
    x.set_defaults(fn=cmd_block_set)
    x = g.add_parser("remove", help="删除")
    x.add_argument("date")
    x.add_argument("ident")
    x.set_defaults(fn=cmd_block_remove)

    g = sub.add_parser("task", help="今日主要任务（schedule.md）").add_subparsers(dest="action", required=True)
    x = g.add_parser("add", help="添加")
    x.add_argument("date")
    x.add_argument("text")
    x.add_argument("--link", help="资料键名")
    x.set_defaults(fn=cmd_task_add)
    x = g.add_parser("remove", help="删除")
    x.add_argument("date")
    x.add_argument("ident", help="序号或关键词")
    x.set_defaults(fn=cmd_task_remove)
    for name, done, h in (("done", True, "标记完成（与页面共用存储）"),
                          ("undo", False, "取消完成标记")):
        x = g.add_parser(name, help=h)
        x.add_argument("date")
        x.add_argument("ident", help="序号或关键词")
        x.set_defaults(fn=lambda a, _d=done: cmd_task_setdone(a, _d))

    g = sub.add_parser("path", help="资料路径表（links.json paths）").add_subparsers(dest="action", required=True)
    g.add_parser("list").set_defaults(fn=cmd_path_list)
    x = g.add_parser("set", help="新增/修改")
    x.add_argument("key")
    x.add_argument("path")
    x.add_argument("--label"), x.add_argument("--kind"), x.add_argument("--short")
    x.set_defaults(fn=cmd_path_set)
    x = g.add_parser("remove")
    x.add_argument("key")
    x.set_defaults(fn=cmd_path_remove)

    g = sub.add_parser("quick", help="常用入口").add_subparsers(dest="action", required=True)
    x = g.add_parser("add")
    x.add_argument("key")
    x.set_defaults(fn=cmd_quick_add)
    x = g.add_parser("remove")
    x.add_argument("key")
    x.set_defaults(fn=cmd_quick_remove)

    g = sub.add_parser("sidebar", help="左栏入口").add_subparsers(dest="action", required=True)
    x = g.add_parser("add")
    x.add_argument("key")
    x.add_argument("--icon"), x.add_argument("--label")
    x.set_defaults(fn=cmd_sidebar_add)
    x = g.add_parser("remove")
    x.add_argument("key")
    x.set_defaults(fn=cmd_sidebar_remove)

    g = sub.add_parser("draft", help="草稿（draft.md）").add_subparsers(dest="action", required=True)
    g.add_parser("show").set_defaults(fn=cmd_draft_show)
    x = g.add_parser("set", help="整篇替换（--text/--file/管道）")
    x.add_argument("--text")
    x.add_argument("--file")
    x.set_defaults(fn=cmd_draft_set)
    x = g.add_parser("append", help="追加一行")
    x.add_argument("text")
    x.set_defaults(fn=cmd_draft_append)
    g.add_parser("clear").set_defaults(fn=cmd_draft_clear)

    g = sub.add_parser("provider", help="模型池（agent.json）").add_subparsers(dest="action", required=True)
    g.add_parser("list").set_defaults(fn=cmd_provider_list)
    x = g.add_parser("use", help="切换当前模型")
    x.add_argument("ident", help="id 或名称")
    x.set_defaults(fn=cmd_provider_use)
    x = g.add_parser("add", help="新增")
    x.add_argument("name")
    x.add_argument("base_url")
    x.add_argument("model")
    x.add_argument("--key-stdin", action="store_true", help="从 stdin 读 API Key")
    x.set_defaults(fn=cmd_provider_add)
    x = g.add_parser("remove")
    x.add_argument("ident")
    x.set_defaults(fn=cmd_provider_remove)

    x = sub.add_parser("open", help="用系统默认程序打开文件/文件夹")
    x.add_argument("path")
    x.set_defaults(fn=cmd_open)
    sub.add_parser("rebuild", help="立即重建页面").set_defaults(fn=cmd_rebuild)
    sub.add_parser("status", help="环境与服务状态").set_defaults(fn=cmd_status)
    return p


def main():
    a = build_parser().parse_args()
    a.fn(a)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except BrokenPipeError:
        sys.exit(0)
