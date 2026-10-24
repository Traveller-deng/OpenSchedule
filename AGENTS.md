# AGENTS.md — 给 AI 编码助手（dsh / Claude Code / ZCode 等）的操作说明

本仓库是 **OpenSchedule**：本地日程应用。用户会让你"把某天的安排改一下"之类——
你可以直接编辑数据文件完成，不需要改代码。

## 1. 数据在哪（按顺序探测）

1. 环境变量 `SCHED_DATA` / `SCHED_DIST`（存在则优先）
2. 安装态（OpenSchedule.exe 正常运行）：`%LOCALAPPDATA%\OpenSchedule\data\`
3. 便携态：exe 旁边有 `data\schedule.json` → 用 exe 旁的 `data\`
4. 源码运行：仓库根的 `data\`

服务是否在跑：`GET http://127.0.0.1:8123/api/health` → `{"app":"OpenSchedule"}` 即在。

## 2. 文件与格式

### data/todo.md — DDL（服务模式下页面的唯一真源）

```markdown
- [ ] 10.26 交实验报告
- [x] 10.25 论文改稿完成
- [ ] 2027.1.4 论文投稿
```

- `MM.DD` 短日期 = **当年**；跨年写全 `YYYY.M.D`
- 一行一条，`- [ ]` 未完成、`- [x]` 已完成；保持原有行不动，只改要求的

### data/schedule.json — 时间表 / 今日主要任务

```json
{ "2026-10-26": {
    "tasks": [{"text": "写论文", "link": "DOCX"}],
    "items": [
      {"t": "20:00", "title": "论文修改", "type": "research", "d": "2h",
       "detail": "改两节", "out": "定稿", "links": ["DOCX"]}
    ] } }
```

- 键为 `YYYY-MM-DD`；`items` 按时间排序；`t` 必须 `HH:MM`
- `type` 只能是 `study` / `life` / `research` / `rest`（旧值会自动映射，新写的用这四个）
- `tasks`、`d`、`detail`、`out`、`links` 都可省略
- `link` / `links` 里写 `links.json → paths` 的键名，不是路径本身

### data/links.json — 资料路径表 / 常用入口

`paths` 是"键名 → 本机绝对路径"的映射；`sidebar` / `quick` 引用这些键。只在用户明确要求时改。

## 3. 改完如何生效（服务在跑时全部自动，无需托盘操作）

| 改的文件 | 生效方式 |
|---|---|
| `todo.md` | 保存后约 4 秒页面自动并入 |
| `schedule.json` 等其它 data 文件 | 下次页面请求时服务自动重建（<0.5s），页面弹"刷新查看"提示，F5 即见 |
| 服务没在跑 | 用户下次启动时自动构建 |

## 4. 硬性约束

- 一律 UTF-8 编码写文件；保持 JSON 合法；不要重排/重写无关字段和日期键
- 不要改 `dist/`、`docs/example.html`（构建产物）、`release/`（打包产物）
- 不要读取或外传 `data/agent.json` 里的 `apiKey`
- **localStorage 覆盖规则**：用户曾在页面上手动增改过的条目存在浏览器本地、优先于文件——
  若你改的条目在页面上"没生效"，多半是被本地覆盖，如实告知用户即可，不要反复重写文件
- 改完用一次 `GET /api/poll` 可以立即触发服务端重建（省去等 4 秒）
