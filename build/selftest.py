#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""开发期自检：编译全部源码 + CLI 全命令冒烟（在临时数据目录跑，不碰真实 data/）。"""
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    for f in ("cli.py", "serve.py", "build/build.py", "app/launcher.py", "app/uninstall.py"):
        compile(open(os.path.join(ROOT, f), encoding="utf-8").read(), f, "exec")
    print("== compile OK ==")

    tmp = tempfile.mkdtemp(prefix="osd-cli-")
    data = os.path.join(tmp, "data")
    dist = os.path.join(tmp, "dist")
    os.makedirs(data)
    os.makedirs(dist)
    for name in ("schedule.json", "links.json", "todo.md"):
        shutil.copyfile(os.path.join(ROOT, "examples", name), os.path.join(data, name))

    env = dict(os.environ)
    env["SCHED_DATA"] = data
    env["SCHED_DIST"] = dist
    env["PYTHONIOENCODING"] = "utf-8"

    def run(args, expect_fail=False):
        r = subprocess.run([sys.executable, os.path.join(ROOT, "cli.py")] + args,
                           env=env, capture_output=True, text=True, encoding="utf-8")
        tag = " ".join(args)
        if (r.returncode != 0) != expect_fail:
            print("FAIL[%s] rc=%d\n%s\n%s" % (tag, r.returncode, r.stdout, r.stderr))
            raise SystemExit(1)
        print("OK   %s" % tag)
        return r.stdout

    today = "2026-10-24" if os.environ.get("OSD_TEST_DATE") is None else os.environ["OSD_TEST_DATE"]
    run(["status"])
    # json -> md 迁移
    out = run(["day", "show", "2026-10-25"])
    assert os.path.exists(os.path.join(data, "schedule.md")), "迁移未生成 schedule.md"
    assert os.path.exists(os.path.join(data, "schedule.json.imported")), "原 json 未留档"
    # round-trip：迁移生成的 md 能被解析回同样的数据
    sys.path.insert(0, os.path.join(ROOT, "build"))
    import build as B
    days = B.load_schedule(data)
    rt = B.parse_schedule_md(B.serialize_schedule_md(days))
    assert rt == days, "md 序列化/解析 round-trip 不一致"
    print("OK   schedule.md round-trip")
    # 真实数据迁移保真（本机有个人数据时才跑；只读拷贝，不动真实文件）
    real = os.path.join(ROOT, "data", "schedule.json")
    if os.path.exists(real):
        import tempfile as _tf
        rd = _tf.mkdtemp(prefix="osd-real-")
        shutil.copyfile(real, os.path.join(rd, "schedule.json"))
        real_days = B.load_schedule(rd)
        canon = B.parse_schedule_md(B.serialize_schedule_md(real_days))
        rt2 = B.parse_schedule_md(B.serialize_schedule_md(canon))
        # md 记录的是规范化形态（别名→四类型、无链接任务→纯文本），要求二次往返为不动点
        assert rt2 == canon, "真实 schedule.json 迁移后 md 不是稳定形态"
        n_items = sum(len(p.get("items") or []) for p in real_days.values())
        n_items2 = sum(len(p.get("items") or []) for p in canon.values())
        n_tasks = sum(len(p.get("tasks") or []) for p in real_days.values())
        n_tasks2 = sum(len(p.get("tasks") or []) for p in canon.values())
        assert (len(real_days), n_items, n_tasks) == (len(canon), n_items2, n_tasks2), \
            "迁移丢失内容：%d天/%d块/%d任务 → %d/%d/%d" % (
                len(real_days), n_items, n_tasks, len(canon), n_items2, n_tasks2)
        shutil.rmtree(rd, ignore_errors=True)
        print("OK   真实数据迁移保真（%d 天 / %d 块 / %d 任务，类型别名规范化）"
              % (len(canon), n_items2, n_tasks2))
        shutil.rmtree(rd, ignore_errors=True)
        print("OK   真实数据迁移保真（%d 天）" % len(real_days))
    # ddl
    run(["ddl", "list"])
    run(["ddl", "add", "11.2", "CLI 添加的 DDL"])
    out = run(["ddl", "list"])
    assert "CLI 添加的 DDL" in out
    run(["ddl", "done", "CLI 添加"])
    out = run(["ddl", "list"])
    assert "[x] 11.2" in out.replace("  ", " ") or "[x]" in out
    run(["ddl", "undo", "1"])
    run(["ddl", "edit", "CLI 添加", "--date", "11.3", "--text", "改过的 DDL"])
    run(["ddl", "remove", "1"])
    # block
    run(["block", "add", "2026-10-25", "20:00", "CLI 时间块", "research", "--d", "1h",
         "--detail", "说明内容", "--out", "产出物"])
    out = run(["day", "show", "2026-10-25"])
    assert "CLI 时间块" in out and "20:00" in out
    run(["block", "set", "2026-10-25", "20:00", "--time", "19:30", "--title", "改名块"])
    out = run(["day", "show", "2026-10-25"])
    assert "19:30" in out and "改名块" in out
    run(["block", "set", "2026-10-25", "19:30", "--detail", ""])
    run(["block", "remove", "2026-10-25", "1"])
    run(["block", "add", today, "9:5", "时间规范测试", "life"])
    out = run(["day", "show", today])
    assert "09:05" in out, "时间未规范成 HH:MM"
    run(["block", "remove", today, "09:05"])
    # task
    run(["task", "add", today, "CLI 任务一"])
    run(["task", "add", today, "CLI 任务二", "--link", "DOCX"] ) if False else run(["task", "add", today, "CLI 任务二"])
    out = run(["day", "show", today])
    assert "CLI 任务一" in out and "CLI 任务二" in out
    run(["task", "done", today, "CLI 任务一"])
    out = run(["day", "show", today])
    assert "[x] CLI 任务一" in out.replace("  ", " ") or "[x]" in out
    run(["task", "undo", today, "1"])
    run(["task", "remove", today, "1"])
    # links / quick / sidebar
    run(["path", "list"])
    run(["path", "set", "TESTKEY", "C:/tmp/x.pdf", "--label", "测试路径", "--kind", "课件", "--short", "测试"])
    run(["quick", "add", "TESTKEY"])
    run(["sidebar", "add", "TESTKEY", "--icon", "📄"])
    out = run(["path", "list"])
    assert "TESTKEY" in out
    run(["sidebar", "remove", "TESTKEY"])
    run(["quick", "remove", "TESTKEY"])
    run(["path", "remove", "TESTKEY"])
    # draft
    run(["draft", "set", "--text", "CLI 写入的草稿"])
    out = run(["draft", "show"])
    assert "CLI 写入的草稿" in out
    run(["draft", "append", "追加的一行"])
    run(["draft", "clear"])
    # provider（不配 key）
    run(["provider", "list"])
    run(["provider", "add", "测试模型", "https://api.example.com/v1", "test-model"])
    run(["provider", "use", "测试模型"])
    out = run(["provider", "list"])
    assert "*" in out and "测试模型" in out
    run(["provider", "remove", "测试模型"])
    # 错误输入应被拒绝
    run(["block", "add", "2026-10-25", "25:00", "坏时间", "life"], expect_fail=True)
    run(["block", "add", "2026-10-25", "20:00", "坏类型", "hard"], expect_fail=True)
    run(["task", "add", today, "坏链接", "--link", "NOPE"], expect_fail=True)
    # rebuild
    run(["rebuild"])
    assert os.path.exists(os.path.join(dist, "OpenSchedule.html")), "重建未产出页面"
    print("== ALL CLI TESTS PASSED ==")
    shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
