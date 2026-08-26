# Skills Research

个人 Skill 与自定义 Agent 的源码和安装管理仓库，用于日常研究、开发、QA、版本管理与跨设备恢复。

仓库中把“正在开发的资源”和“正式已安装集合”分开。设备安装目录只作为软链接挂载点：Skill 逐项链接，Agent 接管整个目录；Agent QA 所需的普通文件聚合只保存在管理状态目录。

## 目录

| 目录 | 用途 |
|---|---|
| `skills/` | 已整理、可以进入 QA 的 Skill 源码 |
| `agents/` | 已整理、可以进入 QA 的自定义 Agent 配置 |
| `installed/skills/` | 已正式纳管、需要跨设备恢复的 Skill 源码 |
| `installed/agents/` | 已正式纳管、需要跨设备恢复的 Agent 配置 |
| `research/` | 调研、实验和设计记录 |
| `docs/` | 仓库约定 |
| `scripts/` | 资源管理工具 |
| `tests/` | 管理工具测试 |

需要区分两类 Agent 配置：

- `skills/<name>/agents/openai.yaml`：Skill 自身的界面元数据与调用策略。
- `agents/*.toml`：可被 Codex 启动的自定义 Agent 角色。

## Skill 列表

本仓库自主开发的 Skill 及其所属系列如下。下表只提供快速定位，具体衔接关系见 [技能系列索引](docs/skill-series.md)，触发条件和执行规则以各 Skill 的 `SKILL.md` 为准。

| Skill | 所属系列 | 简介 |
|---|---|---|
| `jamie-working-agreements` |  | 在非简单任务开始时加载与场景相关的个人协作偏好。 |
| `code-governance-review` |  | 由 `code_governance_reviewer` 显式加载，基于完整业务逻辑执行代码结构与治理专项审查。 |
| `collaboration-workflow` | Solution | 为多步骤调研、设计、实施和交付提供通用的人机协作循环。 |
| `solution-step-alignment` | Solution | 从简短目标出发，对齐连续步骤并关闭影响主线的关键决策。 |
| `solution-refinement` | Solution | 在目标步骤已确认后补齐必要设计细节，形成完整方案。 |
| `solution-design-style` | Solution | 为非简单技术方案提供边界、不变量和可控演进约束。 |
| `solution-to-development-toolkit` | Solution | 把已确认方案转换为可独立执行的开发工具包。 |
| `echo-planpack` | Echo | 把确定的功能需求转换为经审核和确认的实施方案、工具包与最终边界。 |
| `echo-planpack-review` | Echo | 独立审核 Echo 方案或工具包，并生成可追溯的外部审核记录。 |

## 文档

- [资源与目录约定](docs/conventions.md)
- [技能系列索引](docs/skill-series.md)
- [资源管理器使用指南](docs/manager-usage.md)
