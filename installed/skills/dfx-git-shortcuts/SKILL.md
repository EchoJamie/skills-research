---
name: dfx-git-shortcuts
description: Use when working in a dfx-managed Git repository and the user needs status, branch, fetch, pull, checkout, or other non-interactive Git operations across the main repository and submodules, including requests that mention or propose git submodule foreach for repeated Git commands. Covers dfx g/gss/gb/gf/gl/gco/gcb, default all-repository execution, submodule-only scope, failure assessment, and dfx help commands.
---

# DFX Git Shortcuts

## Workflow

- Run from the intended repository root. The current directory must contain `.git`; its `.gitmodules` defines the target submodules.
- When a request uses or proposes `git submodule foreach` to run a Git command, prefer the matching dfx alias or `dfx g` with `--sub-only`. Omit `--sub-only` only when the main repository should also run; keep native `foreach` for non-Git shell commands.
- Use `dfx gss` when the user asks for concise status across repositories or when status is needed to assess risk, partial success, or failure. Do not treat it as an automatic pre- or post-step for other shortcuts.
- Ask before destructive operations such as `reset --hard`, `clean`, forced checkout, or commands that discard work.
- Use plain `git` when the user wants only the current repository or when the command requires interactive input.

## Command Map

| Need | Command |
| --- | --- |
| Inspect concise status everywhere | `dfx gss [status-args...]` |
| Inspect branches everywhere | `dfx gb [args...]` |
| Fetch submodules, then the main repository | `dfx gf [args...]` |
| Pull submodules, then the main repository | `dfx gl [args...]` |
| Checkout an existing branch everywhere | `dfx gco <branch> [args...]` |
| Create and checkout a branch everywhere | `dfx gcb <branch> [args...]` |
| Run another non-interactive Git command everywhere | `dfx g <git-command> [args...]` |

## Scope

- Run submodules concurrently first, then the main repository by default.
- Add `--sub-only` anywhere in the shortcut arguments to skip the main repository. `dfx` removes this scope flag before invoking Git and fails if no submodules exist.
- Use native Git directly for current-repository-only work, for example `git status --short` or `git pull`.
- If `.gitmodules` is absent, default execution runs only in the current repository.

## Status And Failure Semantics

- Treat `dfx gss` as `git status --short` plus any additional status arguments. For example, use `dfx gss --ignored` or `dfx gss --sub-only`.
- Interpret no `gss` output with exit code 0 as all selected repositories being clean. Dirty repositories still return exit code 0; a non-zero exit means a Git command failed.
- Expect default and submodule-only output to prefix non-empty lines with the repository path.
- Treat multi-repository commands as non-atomic. A failing repository does not roll back successful repositories, and the main repository still runs after submodule attempts.
- When diagnosing a partial or failed multi-repository operation, `dfx gss` can reveal working-tree or gitlink changes; use `dfx gb --show-current` when branch changes may have partially applied.

## Help

Use Cobra's help command for dfx shortcuts:

```bash
dfx help g
dfx help gss
dfx help gl
```

Use native Git help for the underlying Git command, for example `git help status`.
