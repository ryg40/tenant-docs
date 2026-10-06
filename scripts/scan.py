#!/usr/bin/env python3
"""Scan for host values and credentials before they go to a public place.

Usage: scripts/scan.py [--no-dist] [--local-deny <file>] [<path>...]

With no path, the scan covers:
  - each tracked file: the staged content, the working tree content when it
    is different, and the file name
  - each file in captures/
  - each file in dist/ (the built site), unless --no-dist is given. The scan does
    not read dist/.prerender: a build that fails leaves work files there
With one or more paths, the scan covers only these files and directories.
The path "-" is standard input.

Rules:
  scripts/host-values.regex       generic regular expressions (tracked)
  scripts/host-values.allow       exact values that a generic rule accepts (tracked)
  scripts/host-values.local.deny  literal values of one host (not tracked, optional)

A rule with the name credential-* is a credential rule. The allow list does not
apply to it, and the report does not show the value. The report does not show
a value of the local deny list.

A policy finding: the local deny list is tracked, or a .env file is tracked.

Environment:
  SCAN_LOCAL_DENY  path of the local deny list (default: scripts/host-values.local.deny
                   of this checkout, or of the main checkout for a linked worktree)

Exit: 0 clean, 1 finding, 2 usage or configuration error.
Needs: Python 3.8 or later, and Git for the scan of the tracked files.
"""

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REGEX_REL = 'scripts/host-values.regex'
ALLOW_REL = 'scripts/host-values.allow'
LOCAL_DENY_REL = 'scripts/host-values.local.deny'
# Directories that a directory walk does not enter.
SKIP_DIRS = {'.git', 'node_modules', '.astro'}
# A build that fails leaves the work files of the build tool in this directory of dist/.
# A build that passes removes it. It is no part of the built site, and no person can correct its files.
BUILD_WORK_DIR = '.prerender'

NAME_RE = re.compile(r'^[a-z0-9]+(?:-[a-z0-9]+)*$')
MACRO_RE = re.compile(r'\{([A-Z][A-Z_]*)\}')


class ConfigError(Exception):
    pass


class Rule:
    def __init__(self, name, regex, kind):
        self.name = name
        self.regex = regex
        # 'host value', 'credential' or 'local'
        self.kind = kind


def rule_lines(path):
    """The lines of a rule file, without comments and empty lines: (number, text)."""
    try:
        text = Path(path).read_text(encoding='utf-8')
    except OSError as error:
        raise ConfigError(f'cannot read {path}: {error.strerror}')
    for number, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        if line and not line.startswith('#'):
            yield number, line


def load_rules(path):
    """Read the generic rules: '<name> <regex>' and 'define <NAME> <regex>'."""
    rules, macros, seen = [], {}, set()

    def expand(pattern, where):
        def macro(match):
            if match.group(1) not in macros:
                raise ConfigError(f'{where}: the macro {match.group(1)} has no definition')
            return macros[match.group(1)]
        return MACRO_RE.sub(macro, pattern)

    for number, line in rule_lines(path):
        where = f'{path}:{number}'
        fields = line.split(None, 2 if line.startswith('define ') else 1)
        if fields[0] == 'define':
            if len(fields) != 3 or not re.fullmatch(r'[A-Z][A-Z_]*', fields[1]):
                raise ConfigError(f'{where}: a macro line is "define <NAME> <regex>"')
            macros[fields[1]] = expand(fields[2], where)
            continue
        if len(fields) != 2:
            raise ConfigError(f'{where}: a rule line is "<name> <regex>"')
        name, pattern = fields
        if not NAME_RE.match(name) or name.startswith('local-'):
            raise ConfigError(f'{where}: bad rule name {name}')
        if name in seen:
            raise ConfigError(f'{where}: the rule {name} exists two times')
        seen.add(name)
        try:
            regex = re.compile(expand(pattern, where))
        except re.error as error:
            raise ConfigError(f'{where}: the regex of {name} is not valid: {error}')
        if regex.search(''):
            raise ConfigError(f'{where}: the regex of {name} matches empty text')
        kind = 'credential' if name.startswith('credential-') else 'host value'
        rules.append(Rule(name, regex, kind))
    if not rules:
        raise ConfigError(f'{path}: no rule')
    return rules


def load_allow(path, rules):
    """Read the allow list: '<rule> <exact value>'."""
    allow = set()
    if not Path(path).is_file():
        return allow
    names = {rule.name: rule for rule in rules}
    for number, line in rule_lines(path):
        fields = line.split(None, 1)
        where = f'{path}:{number}'
        if len(fields) != 2:
            raise ConfigError(f'{where}: an allow line is "<rule> <exact value>"')
        if fields[0] not in names:
            raise ConfigError(f'{where}: no rule has the name {fields[0]}')
        if names[fields[0]].kind != 'host value':
            raise ConfigError(f'{where}: the allow list does not apply to the rule {fields[0]}')
        allow.add((fields[0], fields[1]))
    return allow


def load_local_deny(path):
    """Read the local deny list: one literal value for each line, case-insensitive."""
    rules = []
    for _, line in rule_lines(path):
        rules.append(Rule(f'local-{len(rules) + 1}', re.compile(re.escape(line), re.IGNORECASE), 'local'))
    return rules


def git(arguments, data=None):
    """Run git at the root. Return the output as bytes, or None when git fails."""
    try:
        result = subprocess.run(['git'] + arguments, cwd=ROOT, input=data,
                                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    except OSError:
        return None
    return result.stdout if result.returncode == 0 else None


def find_local_deny(option):
    """The path of the local deny list, or None. A path that the caller names must exist."""
    named = option or os.environ.get('SCAN_LOCAL_DENY')
    if named:
        if not Path(named).is_file():
            raise ConfigError(f'the local deny list {named} does not exist')
        return Path(named)
    own = ROOT / LOCAL_DENY_REL
    if own.is_file():
        return own
    # A linked worktree: use the list of the main checkout.
    common = git(['rev-parse', '--path-format=absolute', '--git-common-dir'])
    if common:
        common = Path(os.fsdecode(common.rstrip(b'\n')))
        if common.name == '.git' and (common.parent / LOCAL_DENY_REL).is_file():
            return common.parent / LOCAL_DENY_REL
    return None


def decode(data):
    try:
        return data.decode('utf-8')
    except UnicodeDecodeError:
        return data.decode('latin-1')


def scan_text(label, text, rules, allow, findings, where=None):
    """Add one finding for each match: (kind, label, line, column, rule, shown value, note)."""
    for rule in rules:
        for match in rule.regex.finditer(text):
            group = 1 if rule.regex.groups and match.group(1) is not None else 0
            value = match.group(group)
            if rule.kind == 'host value' and (rule.name, value) in allow:
                continue
            start = match.start(group)
            if where is None:
                line = text.count('\n', 0, start) + 1
                column = start - (text.rfind('\n', 0, start) + 1) + 1
                position = (line, column, '')
            else:
                position = (0, 0, where)
            shown = value if rule.kind == 'host value' else ''
            kind = 'host value' if rule.kind == 'local' else rule.kind
            findings.add((kind, label, position[0], position[1], rule.name, shown, position[2]))


def scan_bytes(label, data, rules, allow, findings):
    if b'\0' in data[:8192]:
        scan_text(label, data.decode('latin-1'), rules, allow, findings, where='binary file')
    else:
        scan_text(label, decode(data), rules, allow, findings)


def read_file(path):
    """The content of a file, or the target text of a symbolic link."""
    try:
        if os.path.islink(path):
            return os.fsencode(os.readlink(path))
        with open(path, 'rb') as handle:
            return handle.read()
    except OSError:
        return None


def walk(top):
    """Each file below a directory, sorted, without the skipped directories."""
    for folder, dirs, files in os.walk(top):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
        for name in sorted(files):
            yield os.path.join(folder, name)


def tracked_files():
    """The tracked files: {path: [content, ...]}. None when the root is no Git working tree."""
    listing = git(['ls-files', '-s', '-z'])
    if listing is None:
        return None
    entries = []
    for entry in listing.split(b'\0'):
        if not entry:
            continue
        meta, path = entry.split(b'\t', 1)
        mode, blob, _stage = meta.split()
        # 160000 is a submodule: it has no content in this repository.
        if mode != b'160000':
            entries.append((blob, os.fsdecode(path)))
    out = git(['cat-file', '--batch'], data=b''.join(blob + b'\n' for blob, _ in entries)) or b''
    files, offset = {}, 0
    for blob, path in entries:
        end = out.find(b'\n', offset)
        header = out[offset:end].split() if end >= 0 else []
        if len(header) != 3 or not header[2].isdigit():
            raise ConfigError('git cat-file gives no content for ' + path)
        size = int(header[2])
        files.setdefault(path, []).append(out[end + 1:end + 1 + size])
        offset = end + 1 + size + 1
    # The working tree copy, when it is different from the staged content.
    changed = git(['diff-files', '--name-only', '-z']) or b''
    for path in changed.split(b'\0'):
        path = os.fsdecode(path)
        if path in files:
            data = read_file(ROOT / path)
            if data is not None:
                files[path].append(data)
    return files


def scan_repository(rules, allow, findings, with_dist):
    """Scan the tracked files, captures/ and dist/. Return the number of files and the notes."""
    notes = []
    files = tracked_files()
    if files is None:
        notes.append('this directory is no Git working tree: the scan reads each file below it')
        files = {}
        for path in walk(ROOT):
            rel = os.path.relpath(path, ROOT)
            if rel != LOCAL_DENY_REL and rel.split(os.sep)[0] != 'dist':
                files[rel] = [read_file(path) or b'']
    else:
        for path in files:
            parts = path.split('/')
            if path == LOCAL_DENY_REL:
                findings.add(('policy', path, 0, 0, 'tracked-local-deny', '', 'the local deny list is tracked'))
            if parts[-1] == '.env' or (parts[-1].startswith('.env.') and parts[-1] != '.env.example'):
                findings.add(('policy', path, 0, 0, 'tracked-env-file', '', 'a file with deploy values is tracked'))
    extra = ['captures'] + (['dist'] if with_dist else [])
    for top in extra:
        if not (ROOT / top).is_dir():
            if top == 'dist':
                notes.append('dist/ does not exist: the scan does not cover the built site')
            continue
        if top == 'dist' and (ROOT / top / BUILD_WORK_DIR).is_dir():
            notes.append(f'dist/{BUILD_WORK_DIR} holds the work files of a build that failed: the scan does not read it')
        for path in walk(ROOT / top):
            rel = os.path.relpath(path, ROOT)
            if top == 'dist' and rel.split(os.sep)[1] == BUILD_WORK_DIR:
                continue
            if rel not in files:
                files[rel] = [read_file(path) or b'']
    for path in sorted(files):
        scan_text(path, path, rules, allow, findings, where='file name')
        for data in files[path]:
            scan_bytes(path, data, rules, allow, findings)
    return len(files), notes


def scan_paths(paths, rules, allow, findings):
    count = 0
    for given in paths:
        if given == '-':
            scan_bytes('(standard input)', sys.stdin.buffer.read(), rules, allow, findings)
            count += 1
        elif os.path.isdir(given):
            for path in walk(given):
                scan_bytes(path, read_file(path) or b'', rules, allow, findings)
                count += 1
        elif os.path.isfile(given):
            scan_bytes(given, read_file(given) or b'', rules, allow, findings)
            count += 1
        else:
            raise ConfigError(f'{given} does not exist')
    return count


def main(argv=None):
    parser = argparse.ArgumentParser(description='Scan for host values and credentials.',
                                     epilog='Exit: 0 clean, 1 finding, 2 usage or configuration error.')
    parser.add_argument('--no-dist', action='store_true', help='do not scan dist/')
    parser.add_argument('--local-deny', metavar='FILE', help='the local deny list')
    parser.add_argument('paths', nargs='*', metavar='path',
                        help='scan only these files and directories; "-" is standard input')
    options = parser.parse_args(argv)

    findings = set()
    try:
        rules = load_rules(ROOT / REGEX_REL)
        allow = load_allow(ROOT / ALLOW_REL, rules)
        local_file = find_local_deny(options.local_deny)
        local = load_local_deny(local_file) if local_file else []
        if options.paths:
            count, notes = scan_paths(options.paths, rules + local, allow, findings), []
        else:
            count, notes = scan_repository(rules + local, allow, findings, not options.no_dist)
    except ConfigError as error:
        print(f'scan: error: {error}', file=sys.stderr)
        return 2
    if not local:
        notes.append('no local deny list: only the generic rules apply')
    for note in notes:
        print(f'scan: note: {note}', file=sys.stderr)

    totals = {'credential': 0, 'host value': 0, 'policy': 0}
    for kind, label, line, column, rule, shown, note in sorted(findings, key=lambda f: (f[1], f[2], f[3], f[4], f[5])):
        totals[kind] += 1
        where = f'{label}:{line}:{column}' if line else label
        detail = f'  {shown}' if shown else ''
        if note:
            detail += f'  ({note})'
        elif not shown:
            detail += '  (value not shown)'
        print(f'FAIL  {kind}  {where}  rule {rule}{detail}')
    print(f'scan: {len(findings)} finding(s): {totals["credential"]} credential, '
          f'{totals["host value"]} host value, {totals["policy"]} policy. '
          f'{count} file(s), {len(rules)} generic rule(s), {len(local)} local rule(s).')
    return 1 if findings else 0


if __name__ == '__main__':
    sys.exit(main())
