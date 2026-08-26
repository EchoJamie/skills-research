#!/bin/sh
set -eu

printf '%s\n' 'This installer is a disabled historical snapshot.' >&2
printf '%s\n' 'Run make install from the skills-research repository root instead.' >&2
exit 2

skill_names="echo-planpack echo-planpack-review"
legacy_skill_names="feature-implementation-planning feature-planning-review"
installer_dir=$(CDPATH= cd -- "$(dirname "$0")" && pwd -P)
source_root="$installer_dir/skills"
dry_run=0
force=0
destination_override=""

usage() {
  cat <<EOF
Usage: $(basename "$0") [--dry-run] [--force] [--dest DIR]

Install the plan-feature-execution skill group for Codex.

Options:
  --dry-run   Show source and destination paths without changing files.
  --force     Replace existing installations of both skills.
  --dest DIR  Install into DIR instead of the default Codex skills directory.
  -h, --help  Show this help.

Destination priority:
  1. --dest DIR
  2. CODEX_SKILL_HOME
  3. CODEX_HOME/skills
  4. HOME/.codex/skills

Skills:
  echo-planpack
  echo-planpack-review

Legacy migration:
  Existing feature-implementation-planning or feature-planning-review installs
  are only removed when --force is used.
EOF
}

codex_skill_home() {
  if [ -n "$destination_override" ]; then
    printf '%s\n' "$destination_override"
    return
  fi
  if [ -n "${CODEX_SKILL_HOME:-}" ]; then
    printf '%s\n' "$CODEX_SKILL_HOME"
    return
  fi
  if [ -n "${CODEX_HOME:-}" ]; then
    printf '%s\n' "$CODEX_HOME/skills"
    return
  fi
  if [ -z "${HOME:-}" ]; then
    printf 'Cannot determine Codex skills directory: HOME is unset.\n' >&2
    exit 1
  fi
  printf '%s\n' "$HOME/.codex/skills"
}

path_exists() {
  [ -e "$1" ] || [ -L "$1" ]
}

canonical_existing_dir() {
  (CDPATH= cd -- "$1" && pwd -P)
}

preflight() {
  install_root="$1"

  if [ ! -d "$source_root" ]; then
    printf 'Skill source root not found: %s\n' "$source_root" >&2
    exit 1
  fi

  unwanted_file=$(find "$source_root" -name '.DS_Store' -print -quit)
  if [ -n "$unwanted_file" ]; then
    printf 'Skill source contains an unwanted Finder metadata file: %s\n' "$unwanted_file" >&2
    exit 1
  fi

  if [ -e "$install_root" ] && [ ! -d "$install_root" ]; then
    printf 'Codex skill home exists but is not a directory: %s\n' "$install_root" >&2
    exit 1
  fi

  for skill_name in $skill_names; do
    source_dir="$source_root/$skill_name"
    target_dir="$install_root/$skill_name"

    if [ ! -f "$source_dir/SKILL.md" ]; then
      printf 'Skill source is incomplete: %s/SKILL.md\n' "$source_dir" >&2
      exit 1
    fi

    if [ -d "$target_dir" ]; then
      source_path=$(canonical_existing_dir "$source_dir")
      target_path=$(canonical_existing_dir "$target_dir")
      if [ "$source_path" = "$target_path" ]; then
        printf 'Refusing to install: source and target skill directories are the same: %s\n' "$source_path" >&2
        exit 1
      fi
    fi

    if path_exists "$target_dir" && [ "$force" -ne 1 ]; then
      printf 'Skill is already installed: %s\n' "$target_dir" >&2
      printf 'Re-run with --force to replace both installed skills.\n' >&2
      exit 1
    fi
  done

  for legacy_skill_name in $legacy_skill_names; do
    legacy_target="$install_root/$legacy_skill_name"
    if path_exists "$legacy_target" && [ "$force" -ne 1 ]; then
      printf 'Legacy skill is still installed: %s\n' "$legacy_target" >&2
      printf 'Re-run with --force to migrate to the Echo skill names.\n' >&2
      exit 1
    fi
  done
}

install_skills() {
  requested_root="$1"

  if [ "$dry_run" -eq 1 ]; then
    for skill_name in $skill_names; do
      printf '[dry-run] %s -> %s\n' "$source_root/$skill_name" "$requested_root/$skill_name"
    done
    return
  fi

  mkdir -p "$requested_root"
  install_root=$(canonical_existing_dir "$requested_root")
  staging_root=$(mktemp -d "$install_root/.plan-feature-execution-install.XXXXXX")
  committed=0

  cleanup() {
    if [ "$committed" -ne 1 ]; then
      for cleanup_name in $skill_names; do
        installed_marker="$staging_root/.installed-$cleanup_name"
        backup_path="$staging_root/.backup-$cleanup_name"
        cleanup_target="$install_root/$cleanup_name"
        if [ -f "$installed_marker" ]; then
          rm -rf -- "$cleanup_target"
          if path_exists "$backup_path"; then
            mv -- "$backup_path" "$cleanup_target"
          fi
        fi
      done
      for legacy_cleanup_name in $legacy_skill_names; do
        legacy_cleanup_backup="$staging_root/.legacy-$legacy_cleanup_name"
        legacy_cleanup_target="$install_root/$legacy_cleanup_name"
        if path_exists "$legacy_cleanup_backup" && ! path_exists "$legacy_cleanup_target"; then
          mv -- "$legacy_cleanup_backup" "$legacy_cleanup_target"
        fi
      done
    fi
    rm -rf -- "$staging_root"
  }
  trap cleanup 0 HUP INT TERM

  for skill_name in $skill_names; do
    cp -R "$source_root/$skill_name" "$staging_root/$skill_name"
    if [ ! -f "$staging_root/$skill_name/SKILL.md" ]; then
      printf 'Failed to stage skill: %s\n' "$skill_name" >&2
      exit 1
    fi
  done

  for skill_name in $skill_names; do
    target_dir="$install_root/$skill_name"
    backup_dir="$staging_root/.backup-$skill_name"

    if path_exists "$target_dir"; then
      mv -- "$target_dir" "$backup_dir"
    fi
    if ! mv -- "$staging_root/$skill_name" "$target_dir"; then
      if path_exists "$backup_dir"; then
        mv -- "$backup_dir" "$target_dir"
      fi
      printf 'Failed to install skill: %s\n' "$skill_name" >&2
      exit 1
    fi
    : > "$staging_root/.installed-$skill_name"
  done

  for legacy_skill_name in $legacy_skill_names; do
    legacy_target="$install_root/$legacy_skill_name"
    legacy_backup="$staging_root/.legacy-$legacy_skill_name"
    if path_exists "$legacy_target"; then
      mv -- "$legacy_target" "$legacy_backup"
    fi
  done

  committed=1
  for skill_name in $skill_names; do
    printf 'Installed %s to %s\n' "$skill_name" "$install_root/$skill_name"
  done
  printf 'The installed skills will be available to Codex on the next turn or in a new session.\n'
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --dry-run)
      dry_run=1
      ;;
    --force)
      force=1
      ;;
    --dest)
      shift
      if [ "$#" -eq 0 ]; then
        printf 'Missing directory after --dest.\n\n' >&2
        usage >&2
        exit 2
      fi
      destination_override="$1"
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      printf 'Unknown argument: %s\n\n' "$1" >&2
      usage >&2
      exit 2
      ;;
  esac
  shift
done

destination=$(codex_skill_home)
preflight "$destination"
install_skills "$destination"
