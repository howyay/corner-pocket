#!/usr/bin/env bash
# pool-render-units.sh: render the systemd unit files under deploy/systemd/.
#
# WHAT THIS SCRIPT IS FOR
#   deploy/systemd/ is the source of truth for the user units of this project.
#   Two files there are templates and hold @NAME@ placeholders.  This script is
#   the one renderer for all of them.  It walks deploy/systemd/ and writes the
#   same layout into the directory that --to names.  A file that holds no
#   placeholder is copied byte for byte.
#
# WHAT THIS SCRIPT REFUSES
#   1. A missing --to flag.  The script then prints the usage and exits 2.
#   2. A --to directory that is the live user unit directory of this machine
#      (${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user, or $HOME/.config/systemd/user).
#      The live units are not this script's business.  Render into a scratch
#      directory instead.
#   3. A missing value for --repo-dir, --backup-dir or --podman, when the
#      environment variable of the same name supplies no value either.  The
#      message names the placeholder and the flag.
#   4. A placeholder name in a file that this script does not support.  The
#      message names the file and the line number.  The script checks every file
#      before it writes the first one, so a refusal leaves the target empty.
#   5. A rendered file that still holds a placeholder.  The script exits 0 only
#      when every rendered file holds no placeholder.
#
# USAGE
#   scripts/pool-render-units.sh --to DIR [--repo-dir DIR] [--backup-dir DIR]
#                                [--podman PATH]
#
#   --to DIR          the target directory.  The script creates it.
#   --repo-dir DIR    the value for @REPO_DIR@   (environment REPO_DIR)
#   --backup-dir DIR  the value for @BACKUP_DIR@ (environment BACKUP_DIR)
#   --podman PATH     the value for @PODMAN@     (environment PODMAN)
#
#   A flag wins over the environment variable of the same name.
#
# The source tree is deploy/systemd/ next to this script.  The script finds it
# from its own path, so a copy of the script renders its own copy of the tree.
set -euo pipefail

SUPPORTED_PLACEHOLDERS=(REPO_DIR BACKUP_DIR PODMAN)
PLACEHOLDER_PATTERN='@[A-Za-z_][A-Za-z0-9_]*@'

PROG='pool-render-units.sh'
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_DIR="${SCRIPT_DIR}/../deploy/systemd"

usage() {
  cat <<'EOF'
usage: pool-render-units.sh --to DIR [--repo-dir DIR] [--backup-dir DIR] [--podman PATH]

Render every file under deploy/systemd/ into DIR and keep the layout.
The three drop-ins land in DIR/pool-workbench.service.d/.

  --to DIR          the target directory (required)
  --repo-dir DIR    the value for the placeholder @REPO_DIR@ (environment REPO_DIR)
  --backup-dir DIR  the value for the placeholder @BACKUP_DIR@ (environment BACKUP_DIR)
  --podman PATH     the value for the placeholder @PODMAN@ (environment PODMAN)

The script refuses to write the live user unit directory of this machine.
EOF
}

fail() {
  printf '%s: %s\n' "$PROG" "$1" >&2
  exit 1
}

# is_supported NAME: exit 0 when NAME is one of the three supported placeholders.
is_supported() {
  local name="$1" candidate
  for candidate in "${SUPPORTED_PLACEHOLDERS[@]}"; do
    if [[ "$candidate" == "$name" ]]; then
      return 0
    fi
  done
  return 1
}

# supported_names: print the three names on one line, for the messages.
supported_names() {
  local IFS=' '
  printf '%s' "${SUPPORTED_PLACEHOLDERS[*]}"
}

# count_placeholders FILE: print the number of @NAME@ occurrences in FILE.
count_placeholders() {
  local file="$1" line rest count=0
  while IFS= read -r line || [[ -n "$line" ]]; do
    rest="$line"
    while [[ "$rest" =~ $PLACEHOLDER_PATTERN ]]; do
      count=$((count + 1))
      rest="${rest#*"${BASH_REMATCH[0]}"}"
    done
  done < "$file"
  printf '%s' "$count"
}

# check_file SOURCE RELATIVE: refuse an unsupported placeholder name.
# RELATIVE is the name of SOURCE below deploy/systemd/, for the message.
check_file() {
  local src="$1" rel="$2"
  local line rest name match lineno=0
  while IFS= read -r line || [[ -n "$line" ]]; do
    lineno=$((lineno + 1))
    rest="$line"
    while [[ "$rest" =~ $PLACEHOLDER_PATTERN ]]; do
      match="${BASH_REMATCH[0]}"
      name="${match:1:${#match} - 2}"
      if ! is_supported "$name"; then
        printf '%s: %s:%s: unknown placeholder %s\n' "$PROG" "$rel" "$lineno" "$match" >&2
        printf '%s: supported names: %s\n' "$PROG" "$(supported_names)" >&2
        return 1
      fi
      rest="${rest#*"$match"}"
    done
  done < "$src"
  return 0
}

# render_file SOURCE DEST RELATIVE: write DEST and print one line with the
# number of placeholders that remain in DEST.
render_file() {
  local src="$1" dst="$2" rel="$3"
  local line rest match name found=0
  local -A value=()

  value[REPO_DIR]="$repo_dir"
  value[BACKUP_DIR]="$backup_dir"
  value[PODMAN]="$podman"

  found="$(count_placeholders "$src")"

  if [[ "$found" -eq 0 ]]; then
    # No placeholder in this file: copy it byte for byte.
    cp -- "$src" "$dst"
    printf 'rendered %s placeholders=%s\n' "$rel" "$(count_placeholders "$dst")"
    return 0
  fi

  : > "$dst"
  while IFS= read -r line || [[ -n "$line" ]]; do
    rest="$line"
    while [[ "$rest" =~ $PLACEHOLDER_PATTERN ]]; do
      match="${BASH_REMATCH[0]}"
      name="${match:1:${#match} - 2}"
      line="${line//"$match"/"${value[$name]}"}"
      rest="${rest#*"$match"}"
    done
    printf '%s\n' "$line" >> "$dst"
  done < "$src"

  printf 'rendered %s placeholders=%s\n' "$rel" "$(count_placeholders "$dst")"
}

to_dir=''
repo_dir="${REPO_DIR:-}"
backup_dir="${BACKUP_DIR:-}"
podman="${PODMAN:-}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --to)
      [[ $# -ge 2 ]] || { usage >&2; exit 2; }
      to_dir="$2"
      shift 2
      ;;
    --repo-dir)
      [[ $# -ge 2 ]] || { usage >&2; exit 2; }
      repo_dir="$2"
      shift 2
      ;;
    --backup-dir)
      [[ $# -ge 2 ]] || { usage >&2; exit 2; }
      backup_dir="$2"
      shift 2
      ;;
    --podman)
      [[ $# -ge 2 ]] || { usage >&2; exit 2; }
      podman="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      printf '%s: unknown argument: %s\n' "$PROG" "$1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [[ -z "$to_dir" ]]; then
  printf '%s: the flag --to is absent\n' "$PROG" >&2
  usage >&2
  exit 2
fi

if [[ ! -d "$SOURCE_DIR" ]]; then
  fail "the source directory is absent: ${SOURCE_DIR}"
fi

# The live user unit directory.  Two candidate paths, because either variable
# can point at it.  A target that matches one of them is refused.
live_unit_dirs=(
  "${XDG_CONFIG_HOME:-${HOME}/.config}/systemd/user"
  "${HOME}/.config/systemd/user"
)
to_resolved="$to_dir"
if [[ -d "$to_dir" ]]; then
  to_resolved="$(cd -- "$to_dir" && pwd)"
fi
for live_unit_dir in "${live_unit_dirs[@]}"; do
  if [[ "$to_resolved" == "$live_unit_dir" ]]; then
    fail "refusing ${to_dir}: that is the live user unit directory of this machine"
  fi
done

if [[ -z "$repo_dir" ]]; then
  fail "missing value for @REPO_DIR@: give --repo-dir or set REPO_DIR"
fi
if [[ -z "$backup_dir" ]]; then
  fail "missing value for @BACKUP_DIR@: give --backup-dir or set BACKUP_DIR"
fi
if [[ -z "$podman" ]]; then
  fail "missing value for @PODMAN@: give --podman or set PODMAN"
fi

sources=()
while IFS= read -r src; do
  sources+=("$src")
done < <(find "$SOURCE_DIR" -type f | LC_ALL=C sort)

if [[ "${#sources[@]}" -eq 0 ]]; then
  fail "no file found under ${SOURCE_DIR}"
fi

# First check every file.  A refusal here leaves the target directory empty.
for src in "${sources[@]}"; do
  rel="${src#"$SOURCE_DIR"/}"
  if ! check_file "$src" "$rel"; then
    exit 1
  fi
done

mkdir -p -- "$to_dir"

# Then render every file.
total_remaining=0
for src in "${sources[@]}"; do
  rel="${src#"$SOURCE_DIR"/}"
  dst="${to_dir}/${rel}"
  mkdir -p -- "$(dirname -- "$dst")"
  render_file "$src" "$dst" "$rel"
  remaining="$(count_placeholders "$dst")"
  total_remaining=$((total_remaining + remaining))
done

printf '%s: rendered %s file(s) into %s\n' "$PROG" "${#sources[@]}" "$to_dir"

if [[ "$total_remaining" -ne 0 ]]; then
  fail "${total_remaining} placeholder(s) remain after rendering"
fi

exit 0
