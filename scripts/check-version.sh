#!/bin/sh
# Compare the newest release tag of a project source with the documented release.
# The documented release is in src/data/versions.json. See "New release of a project" in README.md.
#
# Usage: scripts/check-version.sh [<project> [<source>]]
#   <project>  a key of src/data/versions.json. Default: tenant-pi.
#   <source>   the path of a local clone of the project. Default: the variable
#              <PROJECT>_SOURCE, for example TENANT_PI_SOURCE, of the environment
#              or of the untracked file .env.
#
# Exit: 0  the documented release is the newest release of the source.
#       1  the source is ahead. The message names both releases.
#       2  usage error, or the source has no release tag, or it does not hold the documented release.
#
# Needs: sh, git, node and python3.
#
# A message never holds the source location.
# VERSIONS_FILE replaces the path of versions.json. Use it for a test only.
set -eu

root=$(cd "$(dirname "$0")/.." && pwd)
versions=${VERSIONS_FILE:-$root/src/data/versions.json}

if [ "$#" -gt 2 ]; then
  echo "usage: scripts/check-version.sh [<project> [<source>]]" >&2
  exit 2
fi
project=${1:-tenant-pi}
source=${2:-}

variable=$(printf '%s' "$project" | tr '[:lower:]' '[:upper:]' | tr -c 'A-Z0-9' '_')_SOURCE
if [ -z "$source" ]; then
  eval "source=\${$variable:-}"
fi
if [ -z "$source" ] && [ -f "$root/.env" ]; then
  source=$(sed -n "s/^$variable=//p" "$root/.env" | tail -n 1 | sed -e 's/^"\(.*\)"$/\1/' -e "s/^'\(.*\)'\$/\1/")
fi
if [ -z "$source" ]; then
  echo "error: no source for $project. Give the path as an argument, or set $variable in .env." >&2
  exit 2
fi

field() {
  node -e '
    const entry = JSON.parse(require("fs").readFileSync(process.argv[1], "utf8"))[process.argv[2]];
    const value = entry && entry[process.argv[3]];
    if (typeof value !== "string" || value === "") process.exit(1);
    console.log(value);
  ' "$versions" "$project" "$1"
}
if ! release=$(field release) || ! branch=$(field branch); then
  echo "error: src/data/versions.json has no release and branch for $project." >&2
  exit 2
fi

if ! git -C "$source" rev-parse --git-dir >/dev/null 2>&1; then
  echo "error: the source of $project is not a Git repository." >&2
  exit 2
fi

# docgen/release_tag.py holds the two forms of a release tag and the rule for the newest release.
# `docgen.py survey` uses the same file.
status=0
newest=$(python3 -B "$root/docgen/release_tag.py" "$source" "$branch") || status=$?
if [ "$status" -eq 3 ]; then
  echo "error: the source of $project has no release tag of the branch $branch." >&2
  echo "  accepted forms: $branch-v<major>.<minor>.<patch> and $branch/<date>-<hash>" >&2
  exit 2
fi
if [ "$status" -ne 0 ] || [ -z "$newest" ]; then
  echo "error: Git cannot read the tags of the source of $project." >&2
  exit 2
fi

if [ "$newest" = "$release" ]; then
  echo "$project: the documented release $release is the newest release of the source."
  exit 0
fi

if ! git -C "$source" rev-parse --quiet --verify "refs/tags/$release^{commit}" >/dev/null; then
  echo "error: the source of $project does not hold the documented release." >&2
  echo "  documented release (src/data/versions.json): $release" >&2
  echo "  newest release of the source:                $newest" >&2
  exit 2
fi

echo "error: the source of $project is ahead of the documented release." >&2
echo "  documented release (src/data/versions.json): $release" >&2
echo "  newest release of the source:                $newest" >&2
echo "See the section \"New release of a project\" in README.md." >&2
exit 1
