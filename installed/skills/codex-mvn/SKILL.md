---
name: codex-mvn
description: Use when validating Java or Maven project changes, including compile, test, package, verify, install, clean install, or module-scoped Maven checks.
---

# codex-mvn

## Default Flow

1. 根据本 `SKILL.md` 的位置，将 `scripts/codex_mvn.py` 解析为绝对路径。
2. 使用 `python3 <script-path> <maven-args>` 执行验证，不要直接执行裸 `mvn` 或 `mvnw`。
3. 以命令输出的 `status` 和产物路径为准。
4. `SUCCESS`：立即结束，不读取任何运行产物。
5. 失败时按 `next_step` 读取 `errors.txt`、`reports/`；证据不足时才读 `mvn.log`。
6. 仅当命令输出缺失或恢复历史运行时读取 `summary.txt`。

## Command Pattern

```bash
python3 <skill-dir>/scripts/codex_mvn.py test
python3 <skill-dir>/scripts/codex_mvn.py install
python3 <skill-dir>/scripts/codex_mvn.py verify
python3 <skill-dir>/scripts/codex_mvn.py -pl module-a test
python3 <skill-dir>/scripts/codex_mvn.py clean install -Dmaven.test.skip=true
```

## Startup Failure

如果脚本在生成 `run_dir` 前失败，例如 Python 无法启动或脚本文件缺失：

- 将其视为适配器启动错误，不要查找不存在的运行产物。
- 报告原始错误和实际脚本路径。
- 不要因此退回裸 `mvn` 或 `mvnw`。

## Runtime Notes

脚本只依赖 Python 3.9+ 标准库，不需要 Python 第三方运行依赖。
不再使用项目级配置文件；默认参数内置在脚本内。
脚本优先使用项目根目录的 `mvnw`，否则使用 `PATH` 中的 `mvn`。
每次运行写完 `summary.txt` 后，默认仅保留最近 5 个标准运行目录。
默认会尝试执行 `sdk env`。
只有项目存在 `.sdkmanrc` 且环境里有 `SDKMAN_DIR` 时，才会实际生成 `sdkman-env.log` 并带着该环境继续执行 Maven。

## Forbidden

- 验证型 Maven 调用直接执行裸 `mvn`
- 一上来就展开 `mvn.log`
- 把摘要产物当成最终根因；用户要求诊断时仍需基于产物继续分析
