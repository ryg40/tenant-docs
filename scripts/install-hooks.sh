#!/bin/sh
# Install the Git hooks of this repository.
#
# Usage: scripts/install-hooks.sh [--force | --remove]
#   --force   replace a hook that this script did not write
#   --remove  remove the hooks that this script wrote
#
# The hooks:
#   pre-commit  runs scripts/check.sh before each commit
#   commit-msg  runs scripts/scan.py on the commit message
#
# The hooks directory belongs to the repository. So each linked worktree of
# the repository uses the same hooks. A hook does nothing in a checkout that
# has no scripts/check.sh.
# To skip the hooks for one commit: git commit --no-verify
#
# Exit: 0 done, 1 a hook of another origin exists, 2 usage error.
set -eu

MARKER='tenant-docs hook, written by scripts/install-hooks.sh'

mode=install
case ${1:-} in
    '') ;;
    --force) mode=force ;;
    --remove) mode=remove ;;
    *) echo "usage: $0 [--force | --remove]" >&2; exit 2 ;;
esac
[ $# -le 1 ] || { echo "usage: $0 [--force | --remove]" >&2; exit 2; }

cd "$(dirname "$0")/.."
hooks=$(git rev-parse --git-path hooks)
mkdir -p "$hooks"

# hook_body <name>: print the text of one hook.
hook_body() {
    printf '#!/bin/sh\n# %s\n' "$MARKER"
    case $1 in
        pre-commit) cat <<'EOF'
# Run each check before a commit.
top=$(git rev-parse --show-toplevel) || exit 1
[ -x "$top/scripts/check.sh" ] || exit 0
# Git gives GIT_DIR and GIT_INDEX_FILE to a hook. A check that runs git in
# a different directory would then write into this repository.
unset $(git rev-parse --local-env-vars)
cd "$top" || exit 1
exec "$top/scripts/check.sh"
EOF
            ;;
        commit-msg) cat <<'EOF'
# Scan the commit message for host values and credentials.
# The lines after the scissors line and the comment lines are not part of the message.
top=$(git rev-parse --show-toplevel) || exit 1
[ -f "$top/scripts/scan.py" ] || exit 0
sed -n '/^. -\{24\} >8 -\{24\}$/q;p' "$1" | git stripspace --strip-comments |
    python3 "$top/scripts/scan.py" - && exit 0
echo 'commit-msg: the commit message holds a host value or a credential. Change the message.' >&2
exit 1
EOF
            ;;
    esac
}

status=0
for name in pre-commit commit-msg; do
    target=$hooks/$name
    if [ -e "$target" ] && ! grep -q "$MARKER" "$target"; then
        if [ "$mode" != force ]; then
            echo "install-hooks: $target exists and this script did not write it. Use --force to replace it." >&2
            status=1
            continue
        fi
    fi
    if [ "$mode" = remove ]; then
        if [ -e "$target" ]; then
            rm -f "$target"
            echo "install-hooks: removed $target"
        fi
        continue
    fi
    hook_body "$name" >"$target"
    chmod +x "$target"
    echo "install-hooks: wrote $target"
done
exit "$status"
