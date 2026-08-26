# 资源与目录约定

## 资源边界

仓库资源分成开发集合与正式已安装集合，设备目录只作为挂载点：

1. `research/` 保存问题调查、提示词试验和未达到 QA 条件的原型。
2. `skills/`、`agents/` 保存正在开发且可以进入 QA 的源码。
3. `installed/skills/`、`installed/agents/` 保存正式纳管并需要跨设备恢复的源码。
4. 设备目录保存当前机器的挂载结果，其中可以同时存在仓库正式链接、QA 临时链接、用户原有资源和系统资源。

从研究区进入 `skills/` 或 `agents/` 是一次明确的 QA 准备动作。开发资源不会随 `bootstrap` 自动接入设备；只有用户明确指定时，管理器才建立 QA 软链接。

已有 Skill 与配套 Agent 的系列关系见 [skill-series.md](skill-series.md)。

## Skill 布局

| 路径 | 用途 |
|---|---|
| `skills/<skill-name>/SKILL.md` | 必需的 Skill 入口 |
| `skills/<skill-name>/agents/openai.yaml` | 可选的界面元数据、策略和依赖 |
| `skills/<skill-name>/scripts/` | 可选的确定性工具 |
| `skills/<skill-name>/references/` | 可选的按需加载资料 |
| `skills/<skill-name>/assets/` | 可选的输出模板或静态资源 |

`SKILL.md` 的 `description` 决定自动发现是否准确，应清楚写明能力、适用场景和必要边界。不要把通用编码常识或单次故障经验堆进 Skill。

## 自定义子智能体布局

自定义子智能体配置位于 `agents/<agent-file>.toml`。

每个文件至少包含：

```toml
name = "agent_name"
description = "何时应使用这个角色。"
developer_instructions = """
这个角色的职责、证据要求、写入权限和停止边界。
"""
```

文件名用于管理，人机交互中的角色标识以 TOML 的 `name` 为准。推荐文件名与角色名语义一致，文件名使用连字符，角色名使用下划线。

若一个角色与某个 Skill 配套，保持资源分离，并在角色的 `developer_instructions` 中按名称说明何时使用该 Skill。这样 Skill 仍可被默认智能体独立使用，角色也能组合多个 Skill。

## 研究区布局

推荐按月份和主题组织为 `research/YYYY-MM/<topic>/`。

研究材料可以包含笔记、样本、对比结果和验证记录，但不得包含真实凭据。准备发布时，只把会改变智能体决策的稳定规则整理进 Skill 或 Agent，不要整目录复制。

## QA 接入模型

管理器分别发现：

- 开发区 `skills/`、`agents/` 中的 QA 候选资源；
- 正式集合 `installed/skills/`、`installed/agents/` 中需要跨设备恢复的资源。

`promote` 必须显式选择开发区的 `skill:<name>` 或 `agent:<name>`，校验后将所选版本复制到正式集合；它不直接修改设备，正式集合已有不同版本时必须显式使用 `--force`。`sync` 和 `bootstrap` 只同步正式集合。`qa-link` 必须显式选择开发区资源。同步和 QA 接入都逐项建立软链接，因此仓库修改能直接反映到设备，未被管理的设备资源保持不变。

开发区与正式集合允许存在同名资源。QA 接入同名开发资源时，管理器记录此前的正式链接并临时切换；`qa-unlink` 校验目标未漂移后恢复正式链接。若 QA 临时覆盖的是其他设备资源，只有显式 `--force` 才会先备份，解除 QA 时恢复备份。

`adopt` 用于把一个点名的设备普通资源一次性迁入正式集合，并在标准设备目录建立软链接。该操作不是日常同步，也不会批量执行；软链接、系统 Skill、插件 Skill 和嵌套 Git 仓库不进入这条迁移路径。

管理器不向设备复制安装，也不修改 `config.toml`。`promote` 只负责开发区到正式集合的版本晋级；设备普通资源只有在显式 `adopt` 时才成为仓库正式源。系统 Skill 和插件继续由 Codex 自身机制查看和管理。

正式链接、QA 临时覆盖和恢复信息记录在 `${CODEX_HOME:-~/.codex}/.skills-research/manifest.json`。发现同名设备资源时默认停止；`--force` 只在先完成备份后接管目标。解除时若设备目标不再是登记的仓库软链接，管理器停止并保留现场。

## 版本与验证

- Git 提交是资源版本；不在每个 Skill 内重复维护 Changelog。
- `make validate` 校验目录名、Skill frontmatter、Agent TOML 必填字段，并在本机存在官方 `quick_validate.py` 时继续调用它。
- `make test` 验证显式晋级、正式同步、显式纳管、选择性 QA 链接、临时覆盖恢复、冲突保护、只读盘点和安全解除行为。
- 真实触发、隐式匹配、工具权限和子智能体协作必须在新的 Codex 会话中另行验证，并记录证据边界。
