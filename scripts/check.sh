#!/bin/sh
# Run each check of the site. The CI workflow and the pre-commit hook call this script.
#
# Usage: scripts/check.sh [--gate-lint] [--skip-build]
#   --gate-lint   a finding of the Simplified English lint fails the check
#   --skip-build  do not build; check the dist/ directory that exists
#
# The checks, in this order:
#   tests  scripts/run_tests.py: the tests in tests/ (the tests of the check scripts).
#          Each test file runs in its own process, some files at the same time.
#   build  npm run build
#   links  scripts/check_links.py: no broken internal link or anchor in dist/
#   scan   scripts/scan.py: no host value and no credential in the tracked
#          files, in captures/ and in dist/
#   lint   scripts/lint_ste.py: the Simplified English rules for the pages
#
# Each check runs, also after a failure. So one run shows each finding.
#
# Environment: STE_LINT_GATE=1 is the same as --gate-lint.
# Exit: 0 each check passes, 1 a check fails, 2 usage error or missing tool.
set -u

# The mode of the lint: "report" prints the findings and passes, "gate" fails
# on a finding. Change this line to "gate" when the pages pass the lint.
LINT_MODE=gate

usage() {
    echo "usage: $0 [--gate-lint] [--skip-build]"
}

skip_build=0
[ "${STE_LINT_GATE:-0}" != 1 ] || LINT_MODE=gate
while [ $# -gt 0 ]; do
    case $1 in
        --gate-lint) LINT_MODE=gate ;;
        --skip-build) skip_build=1 ;;
        -h|--help) usage; exit 0 ;;
        *) usage >&2; exit 2 ;;
    esac
    shift
done

cd "$(dirname "$0")/.." || exit 2
# A Git hook gives GIT_DIR and GIT_INDEX_FILE to this script. With them, a test
# that runs git in a different directory writes into this repository.
unset $(git rev-parse --local-env-vars 2>/dev/null)
# No bytecode cache: a cache file holds the absolute path of the checkout.
export PYTHONDONTWRITEBYTECODE=1

for tool in python3 node npm; do
    command -v "$tool" >/dev/null 2>&1 || { echo "check: error: $tool is not installed." >&2; exit 2; }
done
if [ "$skip_build" -eq 0 ] && [ ! -d node_modules ]; then
    echo 'check: error: node_modules is absent. Run "npm ci" first.' >&2
    exit 2
fi

newline='
'
failed=0
summary=

# note <name> <result>: add one line to the summary.
note() {
    summary="$summary$(printf '  %-6s %s' "$1" "$2")$newline"
}

# run <name> <command>...: run one check and record its result.
run() {
    name=$1
    shift
    printf '\n== %s: %s\n' "$name" "$*"
    if "$@"; then
        note "$name" ok
        return 0
    fi
    note "$name" FAIL
    failed=1
    return 1
}

run tests python3 scripts/run_tests.py

built=1
if [ "$skip_build" -eq 1 ]; then
    note build 'skipped (--skip-build)'
else
    run build npm run build || built=0
fi

if [ "$built" -eq 1 ]; then
    run links python3 scripts/check_links.py
else
    note links 'skipped (no build)'
fi

run scan python3 scripts/scan.py

if [ "$LINT_MODE" = gate ]; then
    run lint python3 scripts/lint_ste.py --gate
else
    printf '\n== lint: python3 scripts/lint_ste.py\n'
    if python3 scripts/lint_ste.py; then
        note lint 'ok (report mode: a finding does not fail the check)'
    else
        note lint FAIL
        failed=1
    fi
fi

printf '\n== summary\n%s' "$summary"
if [ "$failed" -eq 0 ]; then
    echo 'check: passed'
else
    echo 'check: FAILED'
fi
exit "$failed"
