#!/bin/sh
# Object proofs and scans for scripts/promote.sh.
export GIT_NO_REPLACE_OBJECTS=1
RELEASE_NAME='tenant-docs portable'
RELEASE_EMAIL=portable@example.invalid

release_error() { echo "release: $*" >&2; return 1; }
is_github() {
    case $(printf '%s' "$1" | tr '[:upper:]' '[:lower:]') in
        *github.com[:/]*) return 0 ;;
        *) return 1 ;;
    esac
}
check_origin() {
    origin_urls=$(git remote get-url --push --all origin 2>/dev/null) || {
        release_error 'development origin is missing'; return 1;
    }
    [ "$(printf '%s\n' "$origin_urls" | wc -l)" -eq 1 ] || {
        release_error 'origin has multiple push URLs'; return 1;
    }
    if is_github "$origin_urls"; then
        release_error 'development origin must not be a GitHub URL'; return 1
    fi
    case $origin_urls in
        http://*@*|https://*@*) release_error 'origin URL holds userinfo'; return 1 ;;
    esac
}
check_graph() {
    graft_file=$(git rev-parse --git-path info/grafts) || return 1
    [ ! -s "$graft_file" ] || { release_error 'Git grafts refused'; return 1; }
    replacements=$(git for-each-ref --format='%(refname)' refs/replace/) || return 1
    [ -z "$replacements" ] || { release_error 'Git replacement refs refused'; return 1; }
}
check_identities() {
    ids=$(git log --format='%an <%ae>%n%cn <%ce>' "$1") || return 1
    [ "$(printf '%s\n' "$ids" | sort -u)" = "$RELEASE_NAME <$RELEASE_EMAIL>" ] ||
        release_error 'release history has a non-neutral identity'
}
check_release_tag() {
    [ "$(git cat-file -t "$1")" = tag ] || { release_error 'release tag must be annotated'; return 1; }
    tag_data=$(git cat-file tag "$1") || return 1
    [ "$(printf '%s\n' "$tag_data" | head -n 1)" = "object $2" ] || {
        release_error 'tag does not point directly to the release tip'; return 1;
    }
    tagger=$(printf '%s\n' "$tag_data" | sed -n '/^$/q; s/^tagger //p')
    [ "$(printf '%s\n' "$tagger" | sed 's/ [0-9][0-9]* [+-][0-9][0-9][0-9][0-9]$//')" = "$RELEASE_NAME <$RELEASE_EMAIL>" ] || {
        release_error 'release tagger is not neutral'; return 1;
    }
    message=$(printf '%s\n' "$tag_data" | sed '1,/^$/d')
    source=$(printf '%s\n' "$message" | sed -n 's/^portable v[^ ]* from main \([0-9a-f]\{40\}\)$/\1/p')
    [ -n "$source" ] && [ "$message" = "portable v$3 from main $source" ] || {
        release_error 'release tag message is invalid'; return 1;
    }
}
check_history() {
    check_identities "$1" || return 1
    roots=$(git rev-list --max-parents=0 "$1") || return 1
    [ "$(printf '%s\n' "$roots" | wc -l)" -eq 1 ] || {
        release_error 'release history must have one bootstrap root'; return 1;
    }
    [ "$(git show -s --format=%B "$roots")" = 'Bootstrap portable' ] &&
        [ "$(git rev-parse "$roots^{tree}")" = "$(git mktree </dev/null)" ] || {
        release_error 'invalid bootstrap root'; return 1;
    }
    for commit in $(git rev-list "$1"); do
        data=$(git cat-file commit "$commit") || return 1
        if printf '%s\n' "$data" | sed '/^$/q' | grep -Eq '^gpgsig(-sha256)? '; then
            release_error 'release commit has a signature'; return 1
        fi
        [ "$commit" != "$roots" ] || continue
        parents=$(git show -s --format=%P "$commit") || return 1
        [ "$(printf '%s\n' "$parents" | wc -w)" -eq 1 ] || {
            release_error 'snapshot must have one parent'; return 1;
        }
        message=$(git show -s --format=%B "$commit") || return 1
        printf '%s\n' "$message" | grep -Eq '^Promote main [0-9a-f]{40}$' &&
            [ "$(printf '%s\n' "$message" | wc -l)" -eq 1 ] || {
            release_error 'invalid snapshot message'; return 1;
        }
    done
}
# Scan Git objects with the existing rules, including names and policy paths.
# The history scan checks every ancestor, not only objects missing on a remote.
scan_release() {
    python3 - "$@" <<'PY'
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, 'scripts')
import scan

try:
    rules = scan.load_rules(scan.ROOT / scan.REGEX_REL)
    allow = scan.load_allow(scan.ROOT / scan.ALLOW_REL, rules)
    deny = scan.find_local_deny(None)
    local = scan.load_local_deny(deny) if deny else []
    if not local:
        raise scan.ConfigError('promotion needs a nonempty local deny list')
    excludes = [line.strip().rstrip('/') for line in Path('scripts/portable-exclude').read_text().splitlines()
                if line.strip() and not line.lstrip().startswith('#')]
    mode, tip = sys.argv[1:]
    refs = [tip] if mode == 'tree' else subprocess.check_output(['git', 'rev-list', tip], text=True).splitlines()
    findings = set()
    count = 0
    for ref in refs:
        listing = subprocess.check_output(['git', 'ls-tree', '-r', '-z', ref])
        for entry in listing.split(b'\0'):
            if not entry:
                continue
            meta, name = entry.split(b'\t', 1)
            file_mode, kind, blob = meta.split()
            path = name.decode('utf-8')
            label = f'{ref}:{path}'
            if any(path == item or path.startswith(item + '/') for item in excludes):
                findings.add(('policy', label, 0, 0, 'excluded-path', '', 'excluded path remains'))
            if Path(path).name == '.env' or (Path(path).name.startswith('.env.') and Path(path).name != '.env.example'):
                findings.add(('policy', label, 0, 0, 'tracked-env-file', '', 'deploy values are tracked'))
            if path == scan.LOCAL_DENY_REL or kind != b'blob':
                findings.add(('policy', label, 0, 0, 'private-or-submodule', '', 'private list or submodule is tracked'))
            scan.scan_text(label, path, rules + local, allow, findings, where='file name')
            if kind == b'blob':
                data = subprocess.check_output(['git', 'cat-file', 'blob', blob])
                scan.scan_bytes(label, data, rules + local, allow, findings)
            count += 1
    # Do not print matched values from release objects.
    for kind, label, line, column, rule, _, note in sorted(findings):
        print(f'FAIL  {kind}  {label}:{line}:{column}  rule {rule}  {note or "value not shown"}')
    print(f'release-scan: {mode}: {len(findings)} finding(s), {len(refs)} tree(s), {count} file(s).')
    sys.exit(1 if findings else 0)
except (scan.ConfigError, OSError, ValueError, subprocess.CalledProcessError) as error:
    print(f'release-scan: error: {error}', file=sys.stderr)
    sys.exit(2)
PY
}
