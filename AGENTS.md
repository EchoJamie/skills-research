# 仓库协作约定

## 沟通

- 始终使用中文回复用户。
- 先给结论，再给必要证据；明确区分静态校验、测试结果和真实 Codex 会话验证。
- 不猜测 Skill 或子智能体已经被 Codex 正确发现、触发或执行；结构校验通过不等于运行时验证通过。

## 文档与图示

- 面向使用与协作的说明文档直接描述当前有效的结构、规则和操作，不以变更过程作为正文；`research/` 中的 Skill 调研、实验和迭代遵循 [研究记录规范](docs/research-records.md)，按时间追加并保留阶段快照。
- 不使用 ASCII 字符、Unicode 线条或 `text` 代码块绘制流程图、关系图、架构图或目录树。
- 简单结构优先使用普通列表或 Markdown 表格，不为装饰而增加图示。
- 关系或流程确实需要可视化时，统一使用 Mermaid，并保证节点名称和连线语义能够独立理解。

## 事实源与目录边界

- `skills/`、`agents/` 保存仓库内正在开发和 QA 的 Skill 与自定义子智能体源码。
- `installed/skills/`、`installed/agents/` 保存正式纳管、需要跨设备恢复的源码集合；目录不存在表示尚未纳管对应类型资源。
- 开发区和正式集合是两个独立事实源，同名资源可以同时存在；QA 接入临时覆盖正式集合，解除后必须恢复正式资源。
- `research/` 保存调研、实验和未达到 QA 条件的原型，禁止被管理器接入设备。
- `skills/<name>/agents/openai.yaml` 是 Skill 元数据，不是自定义子智能体；不要与根目录 `agents/*.toml` 混用。
- 本机 `~/.agents/skills`、`${CODEX_HOME:-~/.codex}/agents` 及旧版 `~/.codex/skills` 都是安装结果，不得在未获用户明确授权时反向覆盖仓库源文件。

## Skill 开发

- 创建或大幅修改 Skill 时，优先使用当前环境提供的 `skill-creator` 并完整遵循其规范；不要重新初始化已有 Skill。
- 新增、删除、重命名系列 Skill 或改变阶段衔接时，同步更新 `docs/skill-series.md`。
- Skill 目录名和 `SKILL.md` 中的 `name` 使用小写字母、数字和连字符，且保持一致。
- `SKILL.md` 必须包含 `name`、`description` 和完成任务所需的最少指令。
- 仅在确有用途时增加 `scripts/`、`references/`、`assets/` 或 `agents/openai.yaml`；不要机械生成空目录或重复文档。
- Skill 或 Agent 存在 `openai.yaml` 时，`interface.display_name` 使用对应资源的英文原名称，不使用中文本地化名称。
- 大段条件化说明放入 `references/`，并从 `SKILL.md` 明确说明何时读取。
- 修改 Skill 后运行 `make validate`；新增或修改脚本时还要执行对应测试或实际命令验证。

## 自定义子智能体开发

- 根目录 `agents/*.toml` 必须定义非空的 `name`、`description` 和 `developer_instructions`。
- 新增、删除、重命名配套角色或改变文件所有权时，同步更新 `docs/skill-series.md`。
- 角色职责要窄、边界清楚。若角色依赖某个 Skill，在 `developer_instructions` 中明确写出 Skill 名称和使用时机。
- 不在角色文件中写入个人 Token、私有端点或只适用于单台设备的绝对路径。
- 不固定未经用户指定的模型；确需固定时，说明原因并验证目标设备支持该模型。

## 安装与变更安全

- 管理器命令、资源选择器和标准操作流程统一参考 [资源管理器使用指南](docs/manager-usage.md)；本文件只维护协作约束，不重复使用文档内容。
- 仓库资源与设备既有资源是两个边界；设备盘点只读，只有用户显式点名时才允许把普通设备资源迁入正式集合。
- 统一通过 `scripts/manage.py` 或 `make` 入口接入和管理 QA 资源，不直接修改设备目标。
- QA 接入必须显式指定资源，不得默认接入仓库全部内容。Skill 逐项建立目录软链接；Agent 接管整个设备目录，QA 时只把显式选中的开发 Agent 与已同步的正式 Agent 聚合为普通 TOML 文件。
- 正式集合通过 `sync` 或 `bootstrap` 统一恢复到设备；Skill 使用逐项软链接，Agent 使用父目录软链接，不在设备安装目录产生副本。
- `adopt` 只允许处理显式指定、通过校验且不是软链接或嵌套 Git 仓库的普通资源；它执行一次性迁移并建立标准软链接，不处理系统 Skill 或插件 Skill。单文件 Agent 只有在设备 Agent 目录没有其他资源时才能纳管。
- 覆盖同名设备资源必须显式传入 `--force`，并保留管理器创建的可恢复备份。
- 解除 QA 接入只允许处理管理清单中登记且指向预期挂载目标的链接，并按清单恢复正式链接或设备备份；发生漂移时停止并报告。
- 不改写用户现有的 `~/.codex/config.toml`、全局 `AGENTS.md` 或其他无关 Codex 配置。
- 写入前检查 `git status`，保留用户和其他智能体的无关改动，不回退、不覆盖。

## 验证与交付

- 最低验证为 `make validate test` 和 `git diff --check`。
- 安装管理逻辑变更还应在隔离的临时目录中覆盖正式同步、显式纳管、QA 临时覆盖与恢复、冲突备份、设备盘点和安全解除路径。
- 交付时列出新增或修改的关键文件、已执行验证及尚未执行的真实运行时验证。
