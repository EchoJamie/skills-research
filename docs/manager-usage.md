# 资源管理器使用指南

本仓库通过 `scripts/manage.py` 管理开发资源、正式集合与设备安装目录之间的关系。日常操作优先使用 `make` 入口；管理器只处理独立 Skill 和根目录自定义 Agent，系统 Skill 与插件 Skill 由 Codex 自身机制管理。

需要直接调用脚本时，可先查看命令帮助：

```bash
python3 scripts/manage.py --help
python3 scripts/manage.py <command> [KIND:NAME ...] [--force]
```

直接调用脚本与对应的 `make` 入口使用同一套校验和安全规则。

## 目录与设备路径

| 类型 | 仓库路径 | 默认设备路径 |
|---|---|---|
| 开发 Skill | `skills/<name>/` | `~/.agents/skills/<name>`，仅在 QA 接入时链接 |
| 开发 Agent | `agents/<name>.toml` | QA 时进入管理器聚合目录，由 `${CODEX_HOME:-~/.codex}/agents` 整体链接 |
| 正式 Skill | `installed/skills/<name>/` | `~/.agents/skills/<name>`，正式同步后链接 |
| 正式 Agent | `installed/agents/<name>.toml` | 无 Agent QA 时由 `${CODEX_HOME:-~/.codex}/agents` 整体链接到该目录 |

`installed/` 是需要版本管理和跨设备恢复的正式源码集合，不是设备目录的复制快照。Skill 逐项建立目录软链接；Agent 以整个设备目录为挂载单元。`sync` 和 `bootstrap` 不运行后台同步。

Agent 挂载分为两种状态：

- 没有 Agent QA 时，`${CODEX_HOME:-~/.codex}/agents` 直接链接到 `installed/agents/`；
- 存在 Agent QA 时，管理器把已同步的正式 Agent 与显式选中的 QA Agent 合并为普通 TOML 文件聚合目录，再让整个 `agents` 目录链接到该聚合目录。QA 同名文件覆盖正式文件，未选中的开发 Agent 不会进入聚合目录。

管理器状态、冲突备份和恢复信息默认保存在：

```text
${CODEX_HOME:-~/.codex}/.skills-research/
```

其中 `agent-overlays/` 是 Agent QA 聚合目录。它是可重建的管理状态，不是正式源码；不要直接编辑其中的 TOML。

## 资源选择器

会修改资源或设备关联的命令必须显式指定资源：

```text
skill:<skill-name>
agent:<agent-file-name-without-toml>
```

多个资源以空格分隔，例如：

```bash
make qa-link RESOURCES="skill:solution-to-development-toolkit agent:toolkit-architect"
```

## 只读检查

在接入、同步或解除资源前，先检查仓库和设备状态：

```bash
make doctor
make status
make device-list
```

- `doctor` 检查 Python、Codex、安装目录和仓库结构。
- `status` 对照开发区、正式集合、管理清单与设备目标，报告未接入、已同步、临时覆盖或链接漂移。
- `device-list` 只读盘点标准 Skill 目录、旧版 Skill 目录、系统 Skill 目录和自定义 Agent 目录。
- 插件不在管理器盘点和接管范围内，使用 `codex plugin list` 单独查看。

## 新设备恢复正式集合

克隆仓库后执行：

```bash
make bootstrap
```

`bootstrap` 依次执行运行条件检查、正式集合软链接、状态检查和设备盘点。它只恢复 `installed/` 中的正式资源，不会接入 `skills/`、`agents/` 中的开发资源。

如需单独恢复正式链接：

```bash
make sync
```

同步时的差异处理规则如下：

| 设备状态 | 默认处理 |
|---|---|
| 缺少正式集合中的资源 | 建立正式软链接 |
| 已正确指向正式源码 | 保持不变 |
| 存在其他名称的设备资源 | 保留，不删除 |
| 同名目标不是预期软链接 | 停止整次同步并报告冲突 |
| 正在进行 QA 临时覆盖 | 保持 QA 链接，并登记 QA 结束后恢复正式资源 |

上表中的“同名目标”适用于 Skill。Agent 以整个 `${CODEX_HOME}/agents` 目录为冲突边界：目录已有未纳管内容时，默认停止，不会只替换其中某个文件。

确认需要接管同名设备资源时：

```bash
make sync FORCE=1
```

管理器会先把冲突 Skill 或整个 Agent 设备目录移动到状态目录下的 `backups/`，再建立链接。不要把 `FORCE=1` 作为默认选项。

## 开发资源接入 QA

只接入本次需要验证的资源：

```bash
make qa-link RESOURCES="skill:<name>"
make qa-link RESOURCES="skill:<name> agent:<name>"
```

如果同名正式 Skill 正在生效，QA 接入会临时把设备链接切换到开发源码。Agent QA 会重建普通文件聚合目录，并把整个 Agent 设备目录切换到该聚合目录。若设备目标属于其他来源，默认停止；确认临时接管时才使用：

```bash
make qa-link RESOURCES="skill:<name>" FORCE=1
```

QA 完成后显式解除：

```bash
make qa-unlink RESOURCES="skill:<name> agent:<name>"
```

解除时，管理器按清单恢复正式链接或设备备份。设备目标与清单登记不一致时，管理器停止并保留现场。

Agent QA 聚合不是后台同步。开发 TOML 修改后，再次执行对应的 `qa-link agent:<name>` 才会刷新聚合文件；`status` 会把尚未刷新的内容报告为“QA 聚合待刷新”。

Skill 是否被发现、自动触发，以及自定义 Agent 是否能被正确启动，需要在新的真实 Codex 会话中验证；仓库结构校验和软链接存在不能代替运行时验证。

## 开发资源晋级正式集合

先完成本地校验：

```bash
make validate test
```

首次将开发资源复制到正式集合：

```bash
make promote RESOURCES="skill:<name> agent:<name>"
```

如果正式集合已经存在内容不同的同名版本，管理器默认停止。确认用开发版本更新正式版本时：

```bash
make promote RESOURCES="skill:<name> agent:<name>" FORCE=1
```

`promote` 只更新仓库内的 `installed/`，不主动接管设备目标。晋级后执行：

```bash
make sync
make status
```

正确链接到正式集合的设备资源会读取更新后的内容。Codex 会话的资源加载结果需要通过真实会话验证。

## 纳管设备既有资源

`adopt` 用于一次性迁移一个明确点名的普通设备资源：

```bash
make adopt RESOURCES="skill:<name>"
make adopt RESOURCES="agent:<name>"
```

执行成功后，原设备资源会移动到 `installed/`。Skill 的标准设备路径改为资源软链接；Agent 的父目录改为指向整个 `installed/agents/` 的目录软链接。以下资源不会被纳管：

- 已经是符号链接的资源；
- 系统 Skill 或插件 Skill；
- 含嵌套 Git 仓库的 Skill；
- 正式集合中已经存在同名目标的资源；
- 同时出现在标准目录和旧版目录的同名 Skill。
- Agent 目录中还存在其他未纳管资源时的单文件 Agent。

`adopt` 会移动设备资源，不是只读盘点命令。执行前必须确认资源名称、来源和正式集合目标。

## 解除正式同步

只解除明确指定的正式资源：

```bash
make unsync RESOURCES="skill:<name> agent:<name>"
```

`unsync` 删除设备上的正式软链接，但保留仓库 `installed/` 源码；如果清单登记了设备备份，则恢复该备份。执行 `sync` 或 `bootstrap` 会建立正式链接。

Skill 可以逐项解除。Agent 以目录为同步单元：命令必须一次列出正式集合中的全部 Agent，且设备中不能存在 Agent QA；管理器整体解除 Agent 目录，并按清单恢复设备目录备份。

`installed/` 中缺少已登记的正式源码时，`status` 报告“仓库源已移除”，管理器不删除设备残留链接。处理顺序应为解除登记，再删除正式源码。

## 命令速查

| 命令 | 用途 | 是否可能写入 |
|---|---|---|
| `make help` | 查看命令入口 | 否 |
| `make validate` | 校验仓库、Skill 与 Agent 结构 | 否 |
| `make test` | 在隔离临时目录运行管理器测试 | 仅临时目录 |
| `make doctor` | 检查运行条件和仓库结构 | 否 |
| `make status` | 查看开发区、正式集合和链接状态 | 否 |
| `make device-list` | 只读盘点设备资源 | 否 |
| `make bootstrap` | 校验并恢复全部正式链接 | 是 |
| `make sync` | 恢复全部正式链接 | 是 |
| `make unsync RESOURCES="..."` | 解除指定正式链接 | 是 |
| `make promote RESOURCES="..."` | 复制指定开发资源到正式集合 | 是 |
| `make qa-link RESOURCES="..."` | 临时链接指定开发资源 | 是 |
| `make qa-unlink RESOURCES="..."` | 解除指定 QA 链接并恢复原目标 | 是 |
| `make adopt RESOURCES="..."` | 将一个设备普通资源迁入正式集合 | 是 |

## 环境路径覆盖

管理器默认使用当前用户目录，也支持通过环境变量覆盖路径：

| 环境变量 | 用途 |
|---|---|
| `CODEX_HOME` | Codex 主目录，默认 `~/.codex` |
| `SKILLS_RESEARCH_SKILLS_HOME` | Skill 设备挂载目录，默认 `~/.agents/skills` |
| `SKILLS_RESEARCH_AGENTS_HOME` | Agent 设备挂载目录，默认 `${CODEX_HOME}/agents` |
| `SKILLS_RESEARCH_STATE_HOME` | 管理清单与备份目录，默认 `${CODEX_HOME}/.skills-research` |

路径覆盖主要用于隔离验证或非默认安装环境。使用前应确认所有目标都是预期的具体目录，避免把管理命令指向宽泛路径。

## 交付检查

修改仓库资源或管理逻辑后，至少执行：

```bash
make validate test
git diff --check
```

交付说明应区分仓库静态校验、管理器测试和真实 Codex 会话验证，不将其中一种证据替代另一种。
