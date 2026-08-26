---
name: jamie-working-agreements
description: "Apply Jamie's curated personal working preferences before starting non-trivial work that requires autonomous choices about scope, evidence, design, implementation, agent coordination, delivery, or repository maintenance. Use at task intake—not only after a correction—to select the relevant scenario guidance and reduce avoidable interruptions. Do not use for simple self-contained questions or to override the current explicit request and project rules."
---

# Jamie 工作约定

在非简单任务开始前，用经过筛选的个人习惯校准处理方式，减少因方向、范围、决策归属或完成深度不合拍而需要 Jamie 中途纠正的情况。

## 何时使用

- Jamie 要求分析、设计、实现、协调或交付一项需要模型自行选择路径的任务时，在采取主要行动前使用。
- 当前请求非常明确且一步即可完成时无需加载，避免让个人偏好增加仪式性步骤。
- 不要等待 Jamie 表示不满或打断后才使用。收到纠正只是更新当前理解的兜底，不是主要触发方式。

本技能保持自动发现。具体任务 Skill 决定“如何完成这类任务”，本技能只补充“Jamie 通常如何判断处理方式是否合适”。

## 任务开始时校准

1. 先理解当前请求真正关注的对象、问题层次和希望得到的结果，不把相邻能力自动纳入。
2. 判断当前处于调研、方案、实施、协作还是交付阶段，读取对应场景引用。
3. 从引用中只选会影响本次路径的偏好，结合当前事实形成工作解释；不要输出或要求 Jamie 填写固定偏好表。
4. 主动选择直接的事实来源、合适的复杂度和完成深度。模型能够调查或决定的内容自行处理。
5. 如果发现会改变产品结果、方案方向、责任边界或外部影响的真实分岔，带着推荐和影响请求 Jamie 决策；其余事项继续推进。

这是一轮内部校准，不是新的确认门。除非存在无法从事实解决的高影响分岔，否则直接开始工作。

## 按场景加载

任务开始时读取当前阶段的引用；跨阶段任务随实际推进追加读取，不提前加载全部文件。

| 当前场景 | 读取文件 |
|---|---|
| 调研、排查、审查或证据路径选择 | [investigation.md](references/investigation.md) |
| 方案设计、实现方式或决策边界 | [design-and-implementation.md](references/design-and-implementation.md) |
| 已明确采用多智能体协作 | [agent-coordination.md](references/agent-coordination.md) |
| Git 交付、文档、Skill、Agent 或仓库维护 | [delivery-and-maintenance.md](references/delivery-and-maintenance.md) |
| 从历史对话维护这套偏好 | [history-curation.md](references/history-curation.md) |

## 偏好的使用方式

场景引用提供的是决策倾向，不是强制流程。先判断当前请求与历史纠偏背后的因果结构是否一致，再采用相关偏好。当前明确要求、项目规则和当前事实始终优先。

Jamie 期待模型承担事实探查、相邻分岔发现和常规实现判断。不要把这套技能变成新的审批清单，也不要机械追求“最小”、凡事先问或永不扩展；目标是在当前边界内作出更贴合 Jamie 的自主决定。

如果仍发生纠正，立即更新当前工作解释和后续动作。只有 Jamie 明确要求维护个人习惯时，才按照 [history-curation.md](references/history-curation.md) 回查原始对话并修改本技能。
