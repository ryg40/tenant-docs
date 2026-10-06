#!/bin/sh
# Promote main to portable: a bootstrap root and one snapshot per release.
# Adapted from tenant-web. See docs/branches.md for the model and checks.
# No option: scan the candidate and print the plan without changing refs.
# --version X.Y.Z: write the snapshot and its annotated tag, without a push.
# --push: push portable as main and the named tag; needs --version.
# --remote <name>: select the push remote (default github), or check it in a dry run.
# --allow-public: allow a public GitHub remote or a remote of unknown visibility.
# Never use --force, --all, --tags, --follow-tags or --mirror.
# Exit: 0 done, 1 refused or finding, 2 usage or tool error.
set -eu
export GIT_NO_REPLACE_OBJECTS=1
export PYTHONDONTWRITEBYTECODE=1
DEV=main
BRANCH=portable
TAG_PREFIX=portable-v
ID_NAME='tenant-docs portable'
ID_EMAIL=portable@example.invalid

usage() {
    echo "usage: $0 [--allow-public] [--version X.Y.Z] [--push] [--remote <name>]" >&2
    exit 2
}
refuse() { echo "promote: refused: $*" >&2; exit 1; }
die() { echo "promote: error: $*" >&2; exit 2; }
version=
push=no
remote=github
remote_given=no
allow_public=no
while [ $# -gt 0 ]; do
    case $1 in
        --version) [ $# -ge 2 ] || usage; version=$2; shift 2 ;;
        --version=*) version=${1#--version=}; shift ;;
        --push) push=yes; shift ;;
        --allow-public) allow_public=yes; shift ;;
        --remote) [ $# -ge 2 ] || usage; remote=$2; remote_given=yes; shift 2 ;;
        --remote=*) remote=${1#--remote=}; remote_given=yes; shift ;;
        *) usage ;;
    esac
done
[ "$push" != yes ] || [ -n "$version" ] || refuse '--push needs --version X.Y.Z'
[ -n "$remote" ] && [ "${remote#-}" = "$remote" ] || usage
if [ -n "$version" ]; then
    printf '%s\n' "$version" | grep -Eq '^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$' ||
        refuse "version '$version' is not X.Y.Z"
fi
tag=
[ -z "$version" ] || tag=$TAG_PREFIX$version
top=$(git rev-parse --show-toplevel 2>/dev/null) || die 'not inside a Git working tree'
cd -- "$top"
. "$top/scripts/release-policy.sh"
check_graph || refuse 'remove Git grafts and replacement refs before promotion'
[ "$(git rev-parse --is-shallow-repository)" = false ] ||
    refuse 'the repository is shallow; fetch the full history first'
[ -z "$(git status --porcelain --untracked-files=all)" ] || refuse 'the working tree is not clean'
check_origin || refuse 'invalid development origin'
if git worktree list --porcelain | grep -qx "branch refs/heads/$BRANCH"; then
    refuse "a worktree has $BRANCH checked out"
fi
for r in $(git remote); do
    [ "$r" != upstream ] || refuse 'a remote named upstream exists; this repository is first-party'
    [ "$(git remote get-url --push "$r")" != DISABLED ] || refuse "remote $r has the push URL DISABLED"
done
dev=$(git rev-parse --verify "refs/heads/$DEV^{commit}") || die "no branch $DEV"
dev_tree=$(git rev-parse "$dev^{tree}")
[ "$(git rev-parse 'HEAD^{tree}')" = "$dev_tree" ] || refuse "the checkout does not hold the tree of $DEV"

# Filter a temporary index. Never change the checkout or its real index.
tmp_index=$(mktemp) || die 'mktemp failed'
trap 'rm -f "$tmp_index" "$tmp_index.lock"' EXIT
trap 'exit 130' INT TERM
rm -f "$tmp_index"
GIT_INDEX_FILE=$tmp_index git read-tree "$dev_tree" || die 'read-tree failed'
excludes=$(python3 - <<'PY'
import re
from pathlib import Path

paths = [line.strip() for line in Path('scripts/portable-exclude').read_text().splitlines()
         if line.strip() and not line.lstrip().startswith('#')]
for path in paths:
    if not re.fullmatch(r'[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*/?', path) or any(
            part in ('.', '..') for part in path.rstrip('/').split('/')):
        raise SystemExit('exclude: invalid relative path')
    print(path)
PY
) || refuse 'invalid exclude list'
for path in $excludes; do
    GIT_INDEX_FILE=$tmp_index git --literal-pathspecs rm -r -q --cached --ignore-unmatch -- "$path" || die 'exclude failed'
done
snap_tree=$(GIT_INDEX_FILE=$tmp_index git write-tree) || die 'write-tree failed'
rm -f "$tmp_index"
for path in $excludes; do
    [ -z "$(git --literal-pathspecs ls-tree -r --name-only "$snap_tree" -- "$path")" ] || refuse 'excluded path remains in snapshot'
done

# Read both package versions from the source commit, not the checkout.
package_version=$(git show "$dev:package.json" | node --input-type=module -e '
let text = ""; for await (const chunk of process.stdin) text += chunk;
console.log(JSON.parse(text).version);
') || die 'cannot read package.json'
lock_versions=$(git show "$dev:package-lock.json" | node --input-type=module -e '
let text = ""; for await (const chunk of process.stdin) text += chunk;
const lock = JSON.parse(text); console.log(lock.version); console.log(lock.packages[""].version);
') || die 'cannot read package-lock.json'
printf '%s\n' "$package_version" | grep -Eq '^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$' || refuse 'package.json holds no valid version'
[ "$lock_versions" = "$(printf '%s\n%s' "$package_version" "$package_version")" ] || refuse 'package.json and package-lock.json versions differ'
[ -z "$version" ] || [ "$version" = "$package_version" ] || refuse "--version $version differs from package version $package_version"

old=$(git rev-parse -q --verify "refs/heads/$BRANCH^{commit}" || true)
bootstrap=no
if [ -z "$old" ]; then
    bootstrap=yes
    old=$(GIT_AUTHOR_NAME=$ID_NAME GIT_AUTHOR_EMAIL=$ID_EMAIL GIT_COMMITTER_NAME=$ID_NAME GIT_COMMITTER_EMAIL=$ID_EMAIL \
        git -c commit.gpgSign=false commit-tree "$(git mktree </dev/null)" -m 'Bootstrap portable') || die 'cannot create bootstrap'
fi
check_history "$old" || refuse 'invalid portable history'
old_tree=$(git rev-parse "$old^{tree}")
resume=no
highest=$(git tag --list "$TAG_PREFIX*" | sed "s/^$TAG_PREFIX//" |
    grep -E '^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$' | sort -t. -k1,1n -k2,2n -k3,3n | tail -n 1)
if [ -n "$tag" ]; then
    if git rev-parse -q --verify "refs/tags/$tag" >/dev/null; then
        if [ "$push" = yes ] && [ "$(git cat-file -t "refs/tags/$tag")" = tag ] &&
            [ "$(git rev-parse "refs/tags/$tag^{commit}")" = "$old" ] && [ "$old_tree" = "$snap_tree" ]; then
            resume=yes
            check_release_tag "refs/tags/$tag" "$old" "$version" || refuse 'invalid release tag'
        else
            refuse "tag $tag exists"
        fi
    elif [ -n "$highest" ]; then
        last=$(printf '%s\n%s\n' "$highest" "$version" | sort -t. -k1,1n -k2,2n -k3,3n | tail -n 1)
        [ "$last" = "$version" ] && [ "$version" != "$highest" ] || refuse "version $version does not increase over $TAG_PREFIX$highest"
    fi
fi

# Remote checks run only with --push or an explicit --remote.
url=
remote_portable=
remote_branch=main
[ "$remote" != origin ] || remote_branch=$BRANCH
if [ "$push" = yes ] || [ "$remote_given" = yes ]; then
    url=$(git remote get-url --push "$remote" 2>/dev/null) || refuse "remote $remote does not exist"
    case $(printf '%s' "$url" | tr '[:upper:]' '[:lower:]') in
        http://*@*|https://*@*) refuse "the URL of remote $remote holds userinfo; use the credential store or gh auth" ;;
    esac
    [ "$(git remote get-url --push --all "$remote" | wc -l)" -eq 1 ] || refuse "remote $remote has multiple push URLs"
    if is_github "$url"; then
        slug=$(printf '%s\n' "$url" | sed -e 's#^.*[Gg][Ii][Tt][Hh][Uu][Bb]\.[Cc][Oo][Mm][:/]##' -e 's#\.git$##' -e 's#/$##')
        printf '%s\n' "$slug" | grep -Eq '^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$' || refuse 'cannot read owner/repository from the remote URL'
        command -v gh >/dev/null 2>&1 || refuse 'gh is not installed; cannot check repository visibility'
        private=$(gh repo view "$slug" --json isPrivate --jq .isPrivate 2>/dev/null) || refuse "gh repo view $slug failed"
        case $private in
            true) visibility=private ;;
            false) [ "$allow_public" = yes ] || refuse "$slug is not private; public releases need --allow-public"; visibility=public ;;
            *) refuse "cannot determine visibility of $slug" ;;
        esac
    else
        visibility='not checked (not a GitHub URL)'
        [ "$remote" = origin ] || [ "$allow_public" = yes ] || refuse 'shared remote visibility is unknown; use --allow-public'
    fi
    refs=$(git ls-remote "$url" 2>/dev/null) || refuse "git ls-remote $remote failed"
    remote_portable=$(printf '%s\n' "$refs" | awk -v r="refs/heads/$remote_branch" '$2 == r { print $1 }')
    if [ "$remote" != origin ]; then
        foreign=$(printf '%s\n' "$refs" | awk -v b="refs/heads/$remote_branch" -v t="refs/tags/$TAG_PREFIX" \
            'NF == 2 && $2 != b && $2 != "HEAD" && index($2, "refs/pull/") != 1 && index($2, t) != 1 { print $2 }')
        [ -z "$foreign" ] || refuse "remote $remote holds other refs"
    fi
    [ -z "$remote_portable" ] || git cat-file -e "$remote_portable^{commit}" 2>/dev/null || refuse "fetch and check $remote/$remote_branch first"
fi

echo 'promote: plan'
echo "  source        $DEV $dev"
echo "  mode          snapshot, orphan chain (parent $old)"
echo "  bootstrap     $bootstrap (empty root, not a release)"
echo "  snapshot tree $snap_tree"
echo "  excludes      $(printf '%s' "$excludes" | tr '\n' ' ')"
echo "  version       $package_version (package.json and package-lock.json)"
echo "  tag           ${tag:-none (no --version)}"
echo "  identity      $ID_NAME <$ID_EMAIL> (no signature)"
echo "  public opt-in $allow_public"
[ -z "$url" ] || echo "  remote        $remote ($visibility); branch $remote_branch"
scan_release tree "$snap_tree" || refuse 'the public snapshot scan failed'
if [ "$resume" = yes ]; then
    new=$old
    echo "promote: tag $tag exists on $BRANCH; push only"
else
    new=$(GIT_AUTHOR_NAME=$ID_NAME GIT_AUTHOR_EMAIL=$ID_EMAIL GIT_COMMITTER_NAME=$ID_NAME GIT_COMMITTER_EMAIL=$ID_EMAIL \
        git -c commit.gpgSign=false commit-tree "$snap_tree" -p "$old" -m "Promote $DEV $dev") || die 'cannot create snapshot'
fi
check_history "$new" || refuse 'invalid candidate history'
scan_release history "$new" || refuse 'the complete candidate history scan failed'
if [ -n "$remote_portable" ]; then
    git merge-base --is-ancestor "$remote_portable" "$new" || refuse 'remote branch is not an ancestor; no force push is allowed'
fi
if [ -n "$url" ] && [ "$remote" != origin ]; then
    printf '%s\n' "$refs" | while read -r object remote_ref; do
        case $remote_ref in
            refs/tags/*|refs/pull/*)
                commit=$(git rev-parse -q --verify "$object^{commit}") || refuse "fetch and check remote ref $remote_ref first"
                git merge-base --is-ancestor "$commit" "$new" || refuse "remote ref $remote_ref is outside the release chain"
                ;;
        esac
    done || exit 1
fi
if [ -z "$version" ]; then
    echo 'promote: dry run; no refs changed. Give --version X.Y.Z to write the snapshot and the tag.'
    exit 0
fi
if [ "$resume" = no ]; then
    # Build unsigned objects, then move the branch and tag in one guarded transaction.
    tag_object=$(printf 'object %s\ntype commit\ntag %s\ntagger %s <%s> %s\n\nportable v%s from %s %s\n' \
        "$new" "$tag" "$ID_NAME" "$ID_EMAIL" "$(GIT_COMMITTER_NAME=$ID_NAME GIT_COMMITTER_EMAIL=$ID_EMAIL git var GIT_COMMITTER_IDENT | sed 's/^.*> //')" \
        "$version" "$DEV" "$dev" | git mktag) || die 'cannot create release tag'
    check_release_tag "$tag_object" "$new" "$version" || refuse 'invalid candidate tag'
    {
        echo start
        if [ "$bootstrap" = yes ]; then
            echo "create refs/heads/$BRANCH $new"
        else
            echo "update refs/heads/$BRANCH $new $old"
        fi
        echo "create refs/tags/$tag $tag_object"
        echo prepare
        echo commit
    } | git update-ref --stdin || die 'release refs changed concurrently; no release refs written'
    echo "promote: $BRANCH -> $new, tag $tag"
fi
if [ "$push" = no ]; then
    echo "promote: no push. Check a clean clone of $tag before --push."
    exit 0
fi
echo 'promote: push plan'
echo "  remote $remote; branch $remote_branch; tag $tag"
git -c push.followTags=false push --dry-run "$remote" "refs/heads/$BRANCH:refs/heads/$remote_branch" "refs/tags/$tag"
git -c push.followTags=false push "$remote" "refs/heads/$BRANCH:refs/heads/$remote_branch" "refs/tags/$tag"
echo "promote: git ls-remote $remote"
git ls-remote "$remote"
