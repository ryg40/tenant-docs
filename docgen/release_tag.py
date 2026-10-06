#!/usr/bin/env python3
"""The release tags of a project: the two forms, and the rule for the newest release.

`docgen.py` and `scripts/check-version.sh` use this one file, so both give the same release.

A release tag of a branch has one of two forms:
  <branch>-v<major>.<minor>.<patch>   three numbers with no leading zero, for example portable-v1.2.0
  <branch>/<date>-<hash>              a date of 8 digits and a hexadecimal hash of 7 to 40 characters,
                                      for example portable/20260103-3c4d5e6
A tag of another form is not a release.

The newest release:
  1. When a tag of the version form exists, it is the highest version. The numbers are compared one by one,
     so 1.10.0 is higher than 1.9.1. A tag of the date form is then not the newest release.
  2. If not, it is the tag with the latest date in its name. For the same date, it is the tag that was
     made last. For the same time, it is the last name in the order of the characters.

Usage: release_tag.py <repository> <branch>
Prints the newest release tag. Exit: 0 a tag is printed, 3 the repository has no release tag of the branch,
2 Git cannot read the tags.
"""

import re
import subprocess
import sys

NUMBER = r"(0|[1-9][0-9]*)"
VERSION = re.compile(rf"-v{NUMBER}\.{NUMBER}\.{NUMBER}")
DATED = re.compile(r"/([0-9]{8})-([0-9a-f]{7,40})")
FORMS = "{0}-v<major>.<minor>.<patch> and {0}/<date>-<hash>"


def release_key(tag: str, branch: str, made: int = 0) -> tuple | None:
    """The sort key of a release tag of the branch. A higher key is a newer release. None: the tag is not a release."""
    if not tag.startswith(branch):
        return None
    rest = tag[len(branch):]
    version = VERSION.fullmatch(rest)
    if version:
        return (1, *(int(number) for number in version.groups()))
    dated = DATED.fullmatch(rest)
    if dated:
        return (0, int(dated.group(1)), made, tag)
    return None


def newest_first(tags: list[tuple[str, int]], branch: str) -> list[str]:
    """The release tags of the branch, newest first. Each item of `tags` is a name and the time when the tag was made."""
    keyed = [(release_key(name, branch, made), name) for name, made in tags]
    return [name for key, name in sorted((item for item in keyed if item[0] is not None), reverse=True)]


def release_tags(repository: str, branch: str) -> list[str]:
    """The release tags of the branch in one repository, newest first. Git must read the tags, or the call fails."""
    done = subprocess.run(["git", "-C", str(repository), "for-each-ref", "--format=%(creatordate:unix) %(refname:strip=2)",
                           "refs/tags"], capture_output=True, text=True, check=True)
    tags = []
    for line in done.stdout.splitlines():
        made, _, name = line.partition(" ")
        tags.append((name, int(made or 0)))
    return newest_first(tags, branch)


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: release_tag.py <repository> <branch>", file=sys.stderr)
        return 2
    try:
        tags = release_tags(sys.argv[1], sys.argv[2])
    except (subprocess.CalledProcessError, OSError, ValueError):
        return 2
    if not tags:
        return 3
    print(tags[0])
    return 0


if __name__ == "__main__":
    sys.exit(main())
