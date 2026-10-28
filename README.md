# OpenSchedule · 每日安排

一个**单文件、离线可用**的日程应用：左边月历，中间当天时间线，右边 DDL 看板 + 任务安排 + 常用入口 + 草稿。

> 截图走 jsDelivr CDN 加载（`raw.githubusercontent.com` 在部分网络下不可达，走 CDN 保证都能看到；
> 图片本体仍在仓库的 `docs/` 目录里）。

![主界面](https://cdn.jsdelivr.net/gh/Traveller-deng/OpenSchedule@main/docs/screenshot-main.png)

左栏收起后是「歌词式」竖排日号：滚动即换日，当前日居中、上下渐隐，有截止的日子在星期两侧带红点。

![收起态](https://cdn.jsdelivr.net/gh/Traveller-deng/OpenSchedule@main/docs/screenshot-collapsed.png)

右栏和 DDL 看板并列的第二个标签页是**任务安排**：没有明确 DDL、靠自己推进的事（套磁、写论文等），一行一条、可按 `##` 分组。

![任务安排](https://cdn.jsdelivr.net/gh/Traveller-deng/OpenSchedule@main/docs/screenshot-task.png)

## 30 秒上手

### 方式一：免安装包（推荐，什么也不用装）

去 [Releases](../../releases) 下载 `OpenSchedule-x.y.z-win64.zip`，解压后双击 **OpenSchedule.exe**：

- 第一次运行自动初始化数据目录（`%LOCALAPPDATA%\OpenSchedule\`，从内置示例播种，绝不覆盖已有数据）；
- 之后每次双击直接进入页面，再次双击不会起第二个服务，只会把浏览器带到已打开的页面；
- 退出用系统托盘图标（打开页面 / 数据文件夹 / 重建页面 / 卸载 / 退出）；
- 不想用了就运行同目录的 **uninstall.exe**：自动停服务、可选删除个人数据、清掉整个程序文件夹（不写注册表，没有别的残留）；
- 机器上**不需要装 Python 或任何依赖**，也不写注册表、不碰防火墙（只绑 127.0.0.1）。

### 方式二：从源码跑（适合改代码）

```bash
git clone https://github.com/Traveller-deng/OpenSchedule.git
cd OpenSchedule
python serve.py        # 自动复制示例数据、构建页面并打开浏览器
```

或分步：`python build/build.py` 生成 `dist/OpenSchedule.html`（双击即用，纯 file:// 也能看），要 DDL 双向同步和左栏助手时再跑 `python serve.py`。

**用命令行管理日程**（也方便 AI 助手代操作）：

```bash
python cli.py day show                    # 看今天（= 页面实际显示）
python cli.py block add 2026-10-26 20:00 论文修改 research --d 2h
python cli.py ddl add 10.28 交实验报告
python cli.py plan add 整理导师清单 --group 套磁
python cli.py --help                      # 全部命令
```

**只想看看**：直接用浏览器打开 `docs/example.html`。这是脱敏示例，不需要装任何东西，也不需要联网。

> 想让 dsh / Claude Code 这类 AI 助手直接帮你改日程？它们进目录会自动读 [AGENTS.md](AGENTS.md)：首选 CLI，服务运行时改动自动同步到页面。

运行时只依赖 **Python 3.8+ 标准库**；换图标（`build/make_icon.py`）和打包 exe 才需要额外库。

## 从源码打包 exe

```bash
pip install pyinstaller pystray pillow
python build/package.py
# 产物：release/dist/OpenSchedule/（OpenSchedule.exe + schedule.exe + uninstall.exe + 使用说明.txt）
#       release/OpenSchedule-<版本>-win64.zip（直接发布用的压缩包）
```

也可以直接推 tag（如 `v1.0.1`），GitHub Actions 会自动构建并把 zip 挂到 Release（见 `.github/workflows/release.yml`）。

## 功能

| 区域 | 能力 |
|---|---|
| 左栏 | 月历（点击跳转）、今天回中、前后翻月、有安排的日浅灰、有截止的在数字下加红点；可收起成竖排日号：滚轮滑动即换日，当前日居中放大、上下渐隐，左侧一条与日期同高的赤陶竖条；顶部显示所在月份 |
| 中间 | 「今日主要任务」可编辑、点一下即勾选完成，上方进度条随之增长；「时间安排」按时间块展示，含类型色标、说明、子项、产出、资料链接；hover 出现 ＋ 插入 |
| 类型 | 四种：**学习 / 生活 / 科研 / 缓冲** |
| 右栏 | 上下两栏、分隔条可拖：上栏是 **DDL 看板 / 任务安排 / 常用入口**，下栏是**草稿**（自动保存） |
| DDL 看板 | 勾选、新增、✎ 改名、× 删除；用 `serve.py` 打开时**直接读写 `data/todo.md`** |
| 任务安排 | 没有明确 DDL、靠自己推进的事（套磁、写论文等）：按 `##` 分组，一行一条；勾选、新增、✎ 改（事项 / 分组）、× 删除；用 `serve.py` 打开时**直接读写 `data/tasks.md`** |
| 常用入口 | 悬停 ✎ 改 / × 删、右上 ＋ 新增 |
| 侧栏 | 左右都能拖拽调宽（左 212–470px，右 220–560px）；收起按钮是边缘一个实心三角小胶囊，平时很淡 |
| 助手 | 左栏底部的聊天框，⚙ 里可配置**多个模型**随时切换；服务端会把今天的任务 / 时间表 / 未完成 DDL 拼进上下文 |
| 资料链接 | 类型（PDF / DOCX / 文件夹 / 网页…）按路径自动识别；本地文件/文件夹用**系统默认程序**打开（由本地服务代开，可执行/脚本类型一律拒绝），网页直接跳转 |
| 全局快捷键 | 默认 `Alt+S`（可改）：按一下**唤起**独立窗口的日程页面并回到最上方，再按一次**收进托盘**（进程不关、位置尺寸不变）；组合键在「⚙ 设置」里录制保存 |
| 自动更新 | 页面代码更新后，已打开的窗口 4 秒内自动换成新版本（正在输入或弹窗开着就等你改完再刷），不用手动刷新 |

## 目录结构

```
Schedule/
├─ app/launcher.py         桌面启动器：单实例 / 首跑初始化 / 托盘（打包入口）
├─ app/uninstall.py        卸载器
├─ cli.py                  命令行：日程全量读写（schedule.exe 同源）
├─ frontend/               通用前端
│  ├─ index.html
│  └─ assets/{app.css, app.js}
├─ build/
│  ├─ build.py             schedule.md + data/ → 单文件 HTML
│  ├─ package.py           一键出完整发布包（exe+卸载器+zip）
│  ├─ selftest.py          CLI 自测
│  └─ make_icon.py         app-icon.png → app-icon.ico（10 个尺寸）
├─ serve.py                本地服务：页面托管 + todo/草稿/覆盖层同步 + 助手 + /api/open
├─ OpenSchedule.spec       PyInstaller 打包配置（OpenSchedule.exe + schedule.exe）
├─ AGENTS.md               给 AI 助手的操作说明
├─ .github/workflows/      自动构建发布（推 tag 触发）
├─ examples/               脱敏示例数据（随仓库公开）
├─ docs/                   示例产物与截图
├─ data/                   ← 你的个人数据（已 gitignore；exe 版在 %LOCALAPPDATA%\OpenSchedule\data）
├─ dist/                   构建产物（已 gitignore）
├─ app-icon.png / .ico     图标源文件与多尺寸版本
└─ README.md
```

## 数据格式

数据目录下全部是**人可直接看/改**的文件（exe 版在 `%LOCALAPPDATA%\OpenSchedule\data\`）：

**`schedule.md`** —— 时间表+任务明细（数据源）：

```markdown
## 2026-10-26
任务: 写论文 →DOCX
- 20:00 论文修改 [research] @2h | 改两节 | 定稿 | DOCX,CH4
  - 子项一
```

时间块行按 `|` 顺序为：说明 / 产出 / 资料键（可省略段，顺序固定）。类型：`study` 学习 / `life` 生活 / `research` 科研 / `rest` 缓冲。资料键写 `links.json → paths` 的键名。旧的 `schedule.json` 首次构建时自动迁移（原文件改名 `.imported` 留档）。

**`todo.md`**（DDL 的数据源）：

```markdown
- [ ] 10.25 论文改稿完成
- [x] 10.19 课程作业提交
- [ ] 12.25 期末论文投稿
```

**`tasks.md`**（任务安排的数据源：没有明确 DDL、靠自己推进的事）：

```markdown
## 方向
- [ ] 整理导师清单
- [x] 简历定稿
```

一行一条，`##` 是分组标题（可省略），`[x]` 表示已完成。

**`draft.md`** 草稿、**`links.json`** 资料路径/入口、**`edits.json`** 页面增改覆盖层（页面⇄文件自动双向同步）、**`agent.json`** 模型池——都可直接查看；结构见 [AGENTS.md](AGENTS.md)。

## License

MIT
