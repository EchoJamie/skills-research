# Echo 技能组命名决策

> 记录日期：2026-08-13<br>
> 状态：已确认并实施，替代首版技能英文名称。

## 1. 背景

用户计划把本系列逐步打磨为 Echo 技能组，需要所有技能使用统一的 `echo-` 前缀。同时，首版名称 `feature-implementation-planning` 和 `feature-planning-review` 过长，不利于频繁显式调用。

讨论中排除了以下方向：

- `echo-develop-bag` / `echo-develop-bag-review`：能够表达“开发包”，但 `develop bag` 不是自然英文，而且容易把技能误解为实际代码包。
- `echo-devpack` / `echo-devpack-review`：较短，但容易暗示技能直接开发代码。
- `echo-plan` / `echo-review`：很短，但在未来 Echo 技能组扩展后语义过宽。

## 2. 最终命名

| 职责 | 首版名称 | 当前名称 |
|---|---|---|
| 实施规划 | `feature-implementation-planning` | `echo-planpack` |
| 独立审核 | `feature-planning-review` | `echo-planpack-review` |

`PlanPack` 在 Echo 技能组中表示把已确定需求转换为“版本化实施方案、开发工具包与最终实施边界”的完整规划包。它不表示实际代码包。

## 3. 名称一致性

每个技能统一以下四处名称，避免形成机器名和展示名两套概念：

```text
技能目录名 = SKILL.md name = openai.yaml display_name = $显式调用名
```

因此当前调用方式为：

```text
$echo-planpack
$echo-planpack-review
```

中文“功能实施规划”和“功能规划独立审核”继续作为 `SKILL.md` 正文标题和职责说明，不作为 `display_name`。

## 4. 迁移约束

- 源码目录、技能间引用、审核交接模板、默认提示词和安装脚本全部使用当前名称。
- 研究过程文档保留首版名称，明确其为历史事实，不回写成仿佛从未存在过的新名称。
- 安装脚本识别两个首版旧名称。默认遇到旧安装就停止；只有显式 `--force` 才安装新名称并移除旧名称，避免同一能力重复触发。
- 旧安装在实际迁移前保存到 `.codex-tmp` 可恢复备份目录。

## 5. 实施结果

- 两个技能源码目录、`SKILL.md name`、`openai.yaml display_name`、默认提示词和相互调用已经统一使用当前名称。
- `echo-planpack-review` 继续保持 `allow_implicit_invocation: false`。
- 安装脚本通过旧名称迁移测试，并加入 Finder `.DS_Store` 元数据拒绝检查，避免无关文件污染技能和目录摘要。
- 旧安装完整备份到 `.codex-tmp/echo-planpack-old-install-backup.ursTof/`。
- 个人 Codex 技能目录中只保留 `echo-planpack` 与 `echo-planpack-review`，两个首版旧名称已经移除。
