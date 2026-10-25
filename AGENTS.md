# AGENTS.md — 给 AI 助手（dsh / Claude Code / ZCode 等）

OpenSchedule：本地日程应用。**改日程用 CLI，不要手改文件**；数据文件本身全部人可读，供直接查看或精细修改。

## CLI

源码：`python cli.py …`；安装版：程序目录下 `schedule.exe …`（任何命令加 `--help` 看用法）。

```text
schedule status                                 # 环境/服务状态        schedule rebuild 立即重建页面
schedule day show [today|YYYY-MM-DD]            # 看某天（= 页面实际显示，含页面上的增改与勾选）
schedule ddl list | add <MM.DD> <文本> | done|undo|edit|remove <序号|关键词>
schedule plan list|add <文本> [--group 组名] | done|undo|edit|remove <序号|关键词>   # 任务安排（tasks.md）
schedule block add <日期> <HH:MM> <标题> <类型> [--d 1h] [--detail …] [--out …] [--link 键]
schedule block set <日期> <序号|HH:MM> [--time --title --type --d --detail --out]
schedule block remove <日期> <序号|HH:MM>
schedule task add <日期> <文本> [--link 键] | task remove|done|undo <日期> <序号|关键词>
schedule path list|set <键> <路径> [--label --kind --short] | path remove <键>
schedule quick add|remove <键>                  # 常用入口      schedule sidebar add|remove <键>
schedule provider list|use|add|remove           # 模型池（Key 用 --key-stdin，不进 shell 历史）
schedule draft show|set|append|clear            # 草稿          schedule open <路径>
```

类型：`study` 学习 / `life` 生活 / `research` 科研 / `rest` 缓冲。日期 `MM.DD`=当年，跨年写 `YYYY.M.D`。
资料键是 `links.json → paths` 的键名（`path list` 可查），不是路径本身。

构建与发布：`python build/build.py` 出单文件页面（`--profile public` 出脱敏示例版）；
`python build/package.py` 出免安装发布包（exe + 卸载器 + 使用说明 + zip，产物在 `release/`，已 gitignore）；
`python build/selftest.py` 跑 CLI 自检（改完代码先跑它）。

## 数据文件（数据目录 data\ 下，人可直接看/改）

| 文件 | 内容 |
|---|---|
| `schedule.md` | 时间表+任务明细（**数据源**）。每天一节 `## YYYY-MM-DD`；任务行 `任务: 文本 →资料键`；时间块行 `- HH:MM 标题 [类型] @时长 \| 说明 \| 产出 \| 键1,键2`（\| 段可省、顺序固定，段内不要用 \|）；子项写在下一行缩进 `- 文本` |
| `todo.md` | DDL：`- [ ] MM.DD 文本`（`[x]`=已完成） |
| `tasks.md` | 任务安排（没有明确 DDL、靠自己推进的事）：`- [ ] 文本`，`## 标题`=分组 |
| `draft.md` | 草稿（页面上那份的实体） |
| `links.json` | 资料路径表 / 常用入口 / 左栏入口 |
| `edits.json` | 页面增改覆盖层（页面⇄文件双向同步，一般不用手改） |
| `agent.json` | 模型池（**不要读取 apiKey**） |

位置探测：环境变量 `SCHED_DATA` → exe 旁 `data\` → `%LOCALAPPDATA%\OpenSchedule\data`。
服务在跑与否：`GET http://127.0.0.1:8123/api/health`。有效日程也可直接 `GET /api/schedule`。

## 生效与规则

- CLI 写完自动重建页面；服务运行时页面约 4 秒自动感知（todo/任务安排/草稿/勾选直接并入，schedule 改动弹提示刷新）。
- 直接手改文件同样有效：改完跑 `schedule rebuild`，或等页面下次构建。
- 用户曾在页面上增改的条目存于 `edits.json`（优先于数据文件）；CLI 的 task done/undo 也写它，两边自动同步。
- 「任务安排」（tasks.md）是**没有明确 DDL、靠自己推进的事**（套磁、写论文等），和 DDL 看板并列；一行一条，`## 标题` 分组。
- `schedule.json` 已迁移为 `schedule.json.imported`，不要再写它；不要改 `dist/`、`docs/example.html`、`release/`；一律 UTF-8。

## 发布前检查（推 GitHub / 出包前必做）

1. `git add -A --dry-run` 看上传清单：`data/`、`dist/`、`release/`、`logs/` 必须全程被 gitignore。
2. 隐私扫描（区分大小写）：姓名 / 学校 / 保研目标 / 课程与场地 / 同学姓名 / 论文与项目代号 / 本机绝对路径 / 邮箱 / 手机号段 —— 对**将上传的每个文件**扫，命中就改脱敏。
3. 干净克隆验证：只把会上传的文件拷到临时目录（没有 `data/`），跑 `build/build.py`、`build/selftest.py`，再起服务实测「勾选能否写回文件」。
4. 打包产物实跑：解压后双击 exe，验证首跑播种 / 页面三个标签页 / 勾选落盘 / `schedule.exe` 与页面同源。
5. 文档里的示例一律用脱敏内容（public 版与 README 都不写真实目标与真实截止日）。
