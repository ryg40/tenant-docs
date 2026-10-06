#!/usr/bin/env python3
"""docgen: the deterministic part of the doc generator of tenant-docs.

The scripts find the facts and check the pages. An agent writes only the sentences.

  survey    Read one project repository through git. Write facts.json.
  branch    Start the branch of the run in the site, or change to it. Stop when the site has open changes.
  plan      Choose the pages of the doc set from the facts and a profile. Write plan.json.
  scaffold  Write a page skeleton with slots for each planned page. Never overwrite a page.
            Write one capture spec for each command slot.
  next      Print the next open slot, with its instruction, its form and its source files.
  check     Check the pages of one project. Print one line for each finding, with the fix.
  diagrams  List the diagrams that wait for the second pass of a larger model.
  status    Compare the recorded sources of each page with the project repository. List each stale item with its command.
  register  Add the project to the project list of the site, or change it to a full doc set. Set its release.
  commit    Commit the files of the doc set on the branch of the run. Push that branch.

When the pages have no finding, `check` also runs the checks of the site: scripts/check.sh.
Each action prints its next command as one complete line that runs from each directory.

Python 3 standard library and the git command only. The checks of the site also need Node.js. See docgen/README.md.
"""
from __future__ import annotations

import argparse
import difflib
import fnmatch
import json
import re
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path

sys.dont_write_bytecode = True  # An action writes no cache file into the site.
sys.path.insert(0, str(Path(__file__).resolve().parent))
import release_tag  # noqa: E402  The forms of a release tag and the rule for the newest release.

SCRIPT = Path(__file__).resolve()
SITE = SCRIPT.parent.parent
DOCS = SITE / "src" / "content" / "docs"
WORK = SITE / ".docgen"  # untracked: facts can hold values of the host
STATE = SITE / "docgen" / "state"
PROFILES = SITE / "docgen" / "profiles"
CAPTURES = SITE / "captures"

MAX_READ = 200_000
SLOT_OPEN = re.compile(r"\{/\* docgen:slot (?P<id>[\w-]+) \| (?P<min>\d+)-(?P<max>\d+) words \| "
                       r"(?:(?P<form>text|list|numbered|table|steps|command) \| )?(?P<text>.*?) \*/\}")
SLOT_END = "{/* docgen:end */}"
# A command slot holds its command between these two lines. The page does not show the command there:
# the frame of the capture is the one place of a command on a page.
COMMAND_OPEN, COMMAND_END = "{/* docgen:command", "*/}"
TODO = re.compile(r"TODO\(docgen:([\w-]+)\)")
DIAGRAM = re.compile(r"\{/\* docgen:diagram (?P<id>[\w-]+) \| (?P<state>pending|done) \| (?P<text>.*?) \*/\}")
# The own list of docgen for a value of one host. It is the fallback for a directory with no scanner of the
# site (scripts/scan.py), and `register` uses it for its four values. Generic patterns only. The list follows
# the scanner: a loopback address and a documentation address are not values of one host.
# Each entry: a rule name in the form of the scanner, and the pattern.
HOST_VALUES = [
    ("private-ip-", re.compile(r"(?<![\w.])(?:10\.\d{1,3}\.\d{1,3}\.\d{1,3}|192\.168\.\d{1,3}\.\d{1,3}"
                               r"|172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3}|100\.(?:6[4-9]|[7-9]\d|1[01]\d|12[0-7])\.\d{1,3}\.\d{1,3}"
                               r"|169\.254\.\d{1,3}\.\d{1,3})(?![\w-])(?!\.\w)")),
    ("home-path-", re.compile(r"(?<![\w~.-])/(?:(?:home|Users)/[\w.-]+|root(?![\w.-]))")),
    ("opt-path", re.compile(r"(?<![\w~.-])/opt/[\w.-]+")),
    ("internal-url-", re.compile(r"https?://(?!(?:[\w-]+\.)*example(?:\.com|\.org|\.net)?\b)[\w.-]+\.(?:lan|local|internal|home)\b")),
]
# What a rule of the scanner finds, and the fix that fits. The first entry whose name starts the rule name counts.
# `{project}` is the name of the project.
HOST_KINDS = (
    ("private-ip-ula", "a private IP address", "write the example address `2001:db8::1` in its place."),
    ("private-ip-fe80", "a private IP address", "write the example address `2001:db8::1` in its place."),
    ("private-ip-", "a private IP address",
     "write the example address `192.0.2.10` in its place. If the files of the project give an example host, write that host."),
    ("home-path-windows", "an absolute path of one host", "write `%USERPROFILE%` in place of the home directory."),
    ("home-path-", "an absolute path of one host",
     "write `~` in place of the home directory, for example `~/{project}`."),
    ("opt-path", "an absolute path of one host",
     "write the path from the directory of the clone, with no `/` at its start. For the directory of the clone, write `~/{project}`."),
    ("internal-url-", "an internal URL",
     "write the example host `docs.example` in place of the host name, for example `https://docs.example`."),
    ("credential-", "a credential",
     "remove the value. Write the name of the variable or of the file that holds it, and never the value."),
    ("local-", "a value of this machine that the local deny list of the site names",
     "the scanner does not show the value. Find the host name, the user name, the address or the path of this machine "
     "at that column. Write a placeholder in its place: `docs.example` for a host, `~` for a home directory."),
)


def fail(message: str) -> None:
    print(f"error: {message}", file=sys.stderr)
    sys.exit(2)


def command(action: str, *words: str) -> str:
    """One complete command line of this script. It runs in a new shell and from each directory."""
    return shlex.join(["python3", str(SCRIPT), action, *words])


# ---------- git ----------

# Git gives these variables to a hook. With them, a Git command in another directory reads and writes
# the repository of the hook. `git rev-parse --local-env-vars` prints the list of the installed Git.
GIT_LOCAL = ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR", "GIT_OBJECT_DIRECTORY",
             "GIT_ALTERNATE_OBJECT_DIRECTORIES", "GIT_PREFIX", "GIT_NAMESPACE", "GIT_CONFIG", "GIT_CONFIG_COUNT",
             "GIT_CONFIG_PARAMETERS", "GIT_GRAFT_FILE", "GIT_IMPLICIT_WORK_TREE", "GIT_NO_REPLACE_OBJECTS",
             "GIT_REPLACE_REF_BASE", "GIT_SHALLOW_FILE", "GIT_INTERNAL_SUPER_PREFIX")


def drop_git_variables() -> None:
    """Remove the variables of a Git hook from the environment of this process and of each command that it starts."""
    try:
        listed = subprocess.run(["git", "rev-parse", "--local-env-vars"], capture_output=True, text=True).stdout.split()
    except OSError:
        listed = []
    for name in {*GIT_LOCAL, *listed}:
        os.environ.pop(name, None)


def keep_project_repository() -> None:
    """Git writes no file into a project repository that an action reads.

    A Git command that reads the index can write it again, to save time at its next read. With this variable
    it does not. docgen runs no command that needs to write into the project repository.
    """
    os.environ["GIT_OPTIONAL_LOCKS"] = "0"


def git(repo: Path, *args: str, check: bool = True) -> str:
    result = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, errors="replace")
    if check and result.returncode != 0:
        fail(f"git {' '.join(args)}: {result.stderr.strip()}")
    return result.stdout


def ref_exists(repo: Path, ref: str) -> bool:
    return subprocess.run(["git", "-C", str(repo), "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"],
                          capture_output=True).returncode == 0


def tree(repo: Path, ref: str) -> dict[str, str]:
    """Path to blob hash of each file at one ref. The paths start at the top of the repository, from each directory."""
    files = {}
    for line in git(repo, "ls-tree", "-r", "--full-tree", ref).splitlines():
        meta, _, path = line.partition("\t")
        parts = meta.split()
        if len(parts) == 3 and parts[1] == "blob":
            files[path] = parts[2]
    return files


def release_tags(repo: Path, ref: str) -> list[str]:
    """The release tags of the branch `ref`, newest first. scripts/check-version.sh uses the same rule."""
    try:
        return release_tag.release_tags(str(repo), ref)
    except (subprocess.CalledProcessError, OSError, ValueError):
        fail(f"Git cannot read the tags of {repo}")


def show(repo: Path, ref: str, path: str) -> str:
    return git(repo, "show", f"{ref}:{path}", check=False)[:MAX_READ]


def top_of(start: Path) -> Path:
    """The top directory of the repository that holds one path. An action gives the same result from each sub-directory."""
    if not start.is_dir():
        fail(f"'{start}' is not a directory. Give the path of the project repository.")
    done = subprocess.run(["git", "-C", str(start), "rev-parse", "--show-toplevel"], capture_output=True,
                          text=True, errors="replace")
    if done.returncode != 0 or not done.stdout.strip():
        fail(f"the directory {start} is not in the working tree of a Git repository. "
             "Run the command in the project repository.")
    return Path(done.stdout.strip())


def commits_after(repo: Path, tag: str, ref: str) -> int:
    """The number of commits of a branch that come after one tag."""
    count = git(repo, "rev-list", "--count", f"refs/tags/{tag}..{ref}", check=False).strip()
    return int(count) if count.isdigit() else 0


def after_release(count: int, ref: str, tag: str) -> str:
    """The note for a release branch whose tip is not its newest release tag. The pages read the tip."""
    return (f"the branch {ref} has {count} commit(s) after the release tag {tag}. The pages describe the newest commit "
            "of the branch, and the release name is older. Continue, and put this line into your report.")


# ---------- the site checkout ----------

RUN_BRANCH = "topic/docgen-{}"            # The branch of a first doc set. The owner reviews it and merges it.
UPDATE_BRANCH = "topic/docgen-update-{}"  # The branch of an update.
SLUG = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
GIT_TAIL = 20  # the last lines of a failed Git command or of a hook that an action prints


def site_git(*args: str, messages: bool = False) -> subprocess.CompletedProcess:
    """Run one Git command in the site directory. The caller reads the exit code.

    The output is the data of the command, with no warning and no trace line of Git in it.
    With `messages`, the output also holds each message of Git and of a hook, in the order of the terminal.
    Git never asks for a name or a password: an agent cannot answer. The command then fails with a message.
    """
    return subprocess.run(["git", "-C", str(SITE), *args], stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT if messages else subprocess.DEVNULL, stdin=subprocess.DEVNULL,
                          text=True, errors="replace", env={**os.environ, "GIT_TERMINAL_PROMPT": "0"})


def site_checkout() -> bool:
    """True when the site directory is the top directory of a Git checkout. The tests use a site that is none."""
    done = site_git("rev-parse", "--show-toplevel")
    return done.returncode == 0 and Path(done.stdout.strip()).resolve() == SITE


def site_branch() -> str:
    """The branch of the site checkout. An empty text says that the HEAD is detached.

    The full name of the ref gives the branch. The short name is `heads/<branch>` when a tag has the name of the branch.
    """
    done = site_git("symbolic-ref", "--quiet", "HEAD")
    name = done.stdout.strip()
    return name.removeprefix("refs/heads/") if done.returncode == 0 and name.startswith("refs/heads/") else ""


def site_ref(ref: str) -> bool:
    return site_git("rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}").returncode == 0


def site_paths(*args: str) -> list[str]:
    """The paths that one Git command prints with `-z`, relative to the site."""
    done = site_git(*args)
    return [path for path in done.stdout.split("\0") if path] if done.returncode == 0 else []


def holds_doc_set(ref: str, project: str) -> bool:
    """True when the commit `ref` of the site holds the state file of the project, and so its doc set."""
    return site_git("cat-file", "-e", f"{ref}:docgen/state/{project}.json").returncode == 0


def known_base() -> str:
    """The base of a run as the checkout knows it now, with no fetch: `origin/main`, or the local `main`."""
    return next((ref for ref in ("refs/remotes/origin/main", "refs/heads/main") if site_ref(ref)), "")


def branch_command(project: str) -> str:
    """The `branch` command of the run that is possible: an update when the doc set of the project is in `main`."""
    base = known_base() if site_checkout() else ""
    update = ["--update"] if base and holds_doc_set(base, project) else []
    return command("branch", "--project", project, *update)


GIT_CAUSE = re.compile(r"(?:fatal|error): (.+)")
# What Git says when the program of the connection fails, for example SSH. That program prints the cause before it.
NO_REMOTE = "Could not read from remote repository"


def git_cause(output: str) -> str:
    """The line of a failed Git command that names the cause, with no point at its end.

    Git prints the cause in its first line that starts with `fatal:` or `error:`. The lines after it are a second
    message or a hint. With no such line, the first line that is no hint and no warning is the cause.
    A cause that ends with `:` continues: the lines after it name the files.
    The general line of a remote that does not answer gets the line before it: that line names the cause.
    """
    lines = [line for line in output.splitlines() if line.strip()]
    said = [at for at, line in enumerate(lines) if not line.startswith(("hint:", "warning:"))]
    at = next((at for at in said if GIT_CAUSE.match(lines[at])), said[0] if said else None)
    if at is None:
        return "Git gives no message"
    found = GIT_CAUSE.match(lines[at])
    cause = (found.group(1) if found else lines[at]).strip()
    if cause.rstrip(".") == NO_REMOTE:
        before = next((lines[other].strip().rstrip(".: ") for other in reversed(said) if other < at
                       and not lines[other].lower().startswith("warning:")), "")
        cause = f"{before}. {cause}" if before else cause
    if cause.endswith(":"):
        names = []
        for line in lines[at + 1:]:
            # A file name has blanks before it, or it is one word. A sentence of Git ends the list.
            if line.startswith(("hint:", "warning:", "fatal:", "error:")) or not (line[:1].isspace() or " " not in line.strip()):
                break
            names.append(line.strip())
        more = f" and {len(names) - 5} more" if len(names) > 5 else ""
        cause = f"{cause} {', '.join(names[:5])}{more}" if names else cause
    return cause.rstrip(".: ")


def project_name(project: str) -> None:
    """Stop for a text that is no project name. The usual cause is the word `PROJECT` of a code block of a skill."""
    if not SLUG.fullmatch(project):
        fail(f"'{project}' is not a project name of the site. Use the name of the project: `survey` prints it in its line "
             "`project`, and the directory of the project below src/content/docs/ of the site has this name.")


def fetch_by_name(*branches: str) -> bool:
    """Fetch each of these branches of origin by its name. True when the fetch rule of the checkout holds each branch.

    A clone of one branch (`git clone --single-branch`) fetches that branch only. A plain fetch then does not bring
    the branch of a run that a second machine pushed. So the script asks origin for the branch by its name.
    """
    if "+refs/heads/*:refs/remotes/origin/*" in site_git("config", "--get-all", "remote.origin.fetch").stdout.split():
        return True
    for branch in dict.fromkeys(branches):
        listed = site_git("ls-remote", "--heads", "origin", f"refs/heads/{branch}")
        if listed.returncode == 0 and listed.stdout.strip():
            site_git("fetch", "origin", f"+refs/heads/{branch}:refs/remotes/origin/{branch}")
    return False


def need_run_branch(project: str, action: str) -> None:
    """Stop an action that writes a tracked file while the site is on `main` or has a detached HEAD.

    A generated doc set goes to the branch of its run. Nothing goes to `main` without the review of the owner.
    """
    if not site_checkout():
        return
    branch = site_branch()
    if branch and branch != "main":
        return
    where = "is on the branch main" if branch else "has a detached HEAD"
    fail(f"the site checkout {where}, and `{action}` writes a tracked file. Nothing changed. "
         f"Run first: {branch_command(project)}")


def site_status(*paths: str, untracked: bool = True) -> list[str]:
    """Each file of the site that is changed, staged or not tracked. With `paths`, only the files at these paths."""
    found = []
    entries = site_paths("status", "--porcelain", "-z", f"--untracked-files={'all' if untracked else 'no'}", "--", *paths)
    while entries:
        entry = entries.pop(0)
        found.append(entry[3:])
        if entries and ("R" in entry[:2] or "C" in entry[:2]):
            entries.pop(0)  # the old path of a renamed file
    return found


def site_changes(project: str) -> list[str]:
    """Each file that stops a change of the branch: a changed tracked file, and an untracked file of a doc set."""
    tracked = site_status(untracked=False)
    untracked = site_status(f"src/content/docs/{project}", f"captures/{project}", "docgen/state")
    return sorted({*tracked, *untracked})


def cmd_branch(args: argparse.Namespace) -> None:
    project = args.project
    project_name(project)
    if not site_checkout():
        fail("the site directory is no Git checkout, so it has no branch. Stop and tell the user this line.")
    name = (UPDATE_BRANCH if args.update else RUN_BRANCH).format(project)
    lines = []

    remote = "origin" in site_git("remote").stdout.split()
    tracked = True  # The fetch rule of the checkout holds the branch of the run.
    if remote:
        done = site_git("fetch", "origin", messages=True)
        if done.returncode != 0:
            fail(f"Git cannot fetch from the remote origin of the site: {git_cause(done.stdout)}. Nothing changed. "
                 "Stop and tell the user this line.")
        tracked = fetch_by_name(name, RUN_BRANCH.format(project))
        lines.append("fetched  origin")
    base, base_name = ("refs/remotes/origin/main", "origin/main") if remote else ("refs/heads/main", "main")
    if not site_ref(base):
        fail(f"the site has no branch {base_name}, and a run starts there. Nothing changed. Stop and tell the user this line.")

    in_main = holds_doc_set(base, project)
    if in_main and not args.update:
        fail(f"the doc set of '{project}' is in main already, so this is no first doc set. Nothing changed. "
             "In the skill tenant-docs-generate, stop and tell the user this line. In the skill tenant-docs-update and "
             "in the skill tenant-docs-diagrams, run: " + command("branch", "--project", project, "--update"))
    if args.update and not in_main:
        first = RUN_BRANCH.format(project)
        holder = next((ref for ref in (f"refs/heads/{first}", f"refs/remotes/origin/{first}")
                       if site_ref(ref) and holds_doc_set(ref, project)), None)
        listed = listed_projects()
        if holder:
            where = f"The branch {first} holds it: it waits for the review."
        elif listed is not None and project not in listed:
            # The usual cause: the clone is in a directory with another name than the project has on the site.
            where = (f"The project list of the site has no project '{project}'. The names of the list are: "
                     f"{', '.join(listed) or '(none)'}. For a project of the list, the first command of the skill needs "
                     "the option `--project` with that name. For a project that the list does not have, the skill "
                     "tenant-docs-generate makes the first doc set. Do not choose a name.")
        else:
            where = "No branch holds it: the skill tenant-docs-generate makes it."
        fail(f"the doc set of '{project}' is not in main, so an update is not possible. {where} Nothing changed. "
             "Stop and tell the user this line.")

    def do(*words: str) -> None:
        done = site_git(*words, messages=True)
        if done.returncode != 0:
            fail(f"git {' '.join(words)}: {git_cause(done.stdout)}. Stop and tell the user this line.")

    def behind() -> bool:
        """True when each commit of the branch is in the base, and the base has more commits."""
        return (site_git("merge-base", "--is-ancestor", f"refs/heads/{name}", base).returncode == 0
                and site_git("rev-parse", f"refs/heads/{name}").stdout != site_git("rev-parse", base).stdout)

    changes = site_changes(project)
    if site_branch() == name:
        # The checkout is on the branch of the run. The open changes are the work of that run.
        if args.update and behind() and not changes:
            do("merge", "--quiet", "--ff-only", base)
            lines.append(f"moved    {name} to the newest commit of {base_name}, with a fast-forward")
        else:
            lines.append(f"kept     {name}: the site checkout is on this branch")
    else:
        if changes:
            shown = ", ".join(changes[:5]) + (f" and {len(changes) - 5} more" if len(changes) > 5 else "")
            fail(f"the site checkout has changes that are not committed: {shown}. `branch` changes the branch only in "
                 "a clean checkout. Nothing changed. Stop and tell the user this line.")
        if site_ref(f"refs/heads/{name}"):
            do("switch", "--quiet", name)
            lines.append(f"resumed  {name}: the branch exists")
        elif site_ref(f"refs/remotes/origin/{name}"):
            # Git sets the upstream only for a branch of the fetch rule. `commit` sets it at its push.
            do("switch", "--quiet", "--create", name, *(("--track", f"origin/{name}") if tracked
                                                         else ("--no-track", f"refs/remotes/origin/{name}")))
            lines.append(f"resumed  {name}: the branch exists on origin")
        else:
            do("switch", "--quiet", "--create", name, "--no-track", base)
            lines.append(f"started  {name} at {base_name}")
        if args.update and behind():
            do("merge", "--quiet", "--ff-only", base)
            lines.append(f"moved    {name} to the newest commit of {base_name}, with a fast-forward")
    absent = site_git("rev-list", "--count", f"refs/heads/{name}..{base}").stdout.strip()
    if absent.isdigit() and int(absent):
        lines.append(f"note     {name} does not hold {absent} commit(s) of {base_name}. The scripts of this checkout "
                     "can be old. Continue, and put this line into your report.")
    for line in lines:
        print(line)
    # `plan` comes next in each run. In an update, the plan must be as new as the facts before a page gets its record.
    print("next     " + command("plan", "--project", project))


# ---------- survey ----------

def markdown_outline(text: str) -> dict:
    title, status, summary, headings = "", "", "", []
    paragraph: list[str] = []
    fenced = False
    for line in text.splitlines():
        if line.startswith("```"):
            fenced = not fenced
            continue
        if fenced:
            continue
        if line.startswith("# ") and not title:
            title = line[2:].strip()
        elif line.startswith("## "):
            headings.append(line[3:].strip())
        elif title and not headings and not summary:
            if line.strip() and not line.lstrip().startswith(("|", "-", "!", "<", "[!")):
                if line.startswith("Status:"):
                    status = line[7:].strip()
                else:
                    paragraph.append(line.strip())
            elif paragraph:
                summary = " ".join(paragraph)
    if not summary and paragraph:
        summary = " ".join(paragraph)
    return {"title": title, "status": status, "summary": summary, "headings": headings}


def survey_tree(repo: Path, ref: str) -> dict:
    files = tree(repo, ref)
    paths = sorted(files)

    readme = markdown_outline(show(repo, ref, "README.md")) if "README.md" in files else {}

    docs = []
    for path in paths:
        if path.endswith(".md") and (("/" not in path) or path.startswith("docs/")):
            if path.count("/") > 3 or len(docs) >= 150:
                continue
            outline = markdown_outline(show(repo, ref, path))
            docs.append({"path": path, "title": outline["title"], "headings": outline["headings"][:12]})

    extensions = Counter(Path(p).suffix or Path(p).name for p in paths)
    manifests = [p for p in paths if Path(p).name in {
        "package.json", "pyproject.toml", "Cargo.toml", "go.mod", "Dockerfile", "compose.yaml", "compose.yml",
        "docker-compose.yml", "docker-compose.yaml", "Makefile", "requirements.txt"} and p.count("/") <= 1]

    entry_points = []
    for path in paths:
        top = path.split("/")[0]
        if path.endswith(".py") and (top in {"scripts", "bin", "src"} or "/" not in path) and path.count("/") <= 2:
            text = show(repo, ref, path)
            if "argparse" in text and "__main__" in text:
                actions = sorted(set(re.findall(r"add_parser\(\s*['\"]([\w-]+)['\"]", text)))
                entry_points.append({"path": path, "kind": "python-cli", "run": f"python3 {path} --help", "actions": actions})
        elif path.endswith(".sh") and top in {"scripts", "bin"} and path.count("/") == 1:
            lines = show(repo, ref, path).splitlines()
            comment = next((l[1:].strip() for l in lines[1:6] if l.startswith("#") and len(l) > 2), "")
            entry_points.append({"path": path, "kind": "shell", "run": path, "purpose": comment})
    if "package.json" in files:
        try:
            scripts = json.loads(show(repo, ref, "package.json")).get("scripts", {})
        except json.JSONDecodeError:
            scripts = {}
        for name in scripts:
            entry_points.append({"path": "package.json", "kind": "npm-script", "run": f"npm run {name}"})
    for manifest in manifests:
        if Path(manifest).name.startswith(("compose", "docker-compose")):
            services, inside = [], False
            for line in show(repo, ref, manifest).splitlines():
                if re.match(r"^services:\s*$", line):
                    inside = True
                elif inside and re.match(r"^\S", line):
                    inside = False
                elif inside and (found := re.match(r"^  ([\w.-]+):\s*$", line)):
                    services.append(found.group(1))
            entry_points.append({"path": manifest, "kind": "compose", "run": "docker compose up -d", "services": services})

    tests = []
    if any(re.match(r"tests?/test_.*\.py$", p) for p in paths):
        tests.append("python3 -m unittest discover -s tests -q")
    if "package.json" in files and '"test"' in show(repo, ref, "package.json"):
        tests.append("npm test")
    if "Cargo.toml" in files:
        tests.append("cargo test")

    def named(*patterns: str) -> list[str]:
        return [p for p in paths if any(fnmatch.fnmatch(p, pattern) for pattern in patterns)][:20]

    workflow = {
        "hooks": named("scripts/git-hooks/*", "scripts/install-hooks.sh", ".githooks/*"),
        "ci": named(".gitea/workflows/*", ".github/workflows/*"),
        "release_scripts": named("scripts/publish*", "scripts/release*", "scripts/promote*"),
        "scanner": named("scripts/scan*", "scripts/host-values.*"),
        "process_docs": named("docs/**/release*.md", "docs/release*.md", "docs/publishing.md", "docs/branches.md",
                              "docs/remotes.md", "CONTRIBUTING.md", "HANDOFF.md", "docs/tasks.md"),
    }

    return {
        "ref": ref,
        "commit": git(repo, "rev-parse", "--short", ref).strip(),
        "file_count": len(paths),
        "top_level": sorted({p.split("/")[0] + ("/" if "/" in p else "") for p in paths}),
        "readme": readme,
        "docs": docs,
        "extensions": dict(extensions.most_common(8)),
        "manifests": manifests,
        "entry_points": entry_points,
        "tests": tests,
        "workflow": workflow,
        "files": files,
    }


def run_help(repo: Path, ref: str, entry_points: list[dict], out: Path) -> None:
    """Run `--help` of each Python command line in a clean container without network. Save the text.

    The container gets a temporary export of the ref, read-only, a neutral host name and a neutral home.
    Code of the project never runs on the host.
    """
    image = os.environ.get("DOCGEN_HELP_IMAGE", "python:3.12-slim")
    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="docgen-") as tmp:
        archive = subprocess.Popen(["git", "-C", str(repo), "archive", ref], stdout=subprocess.PIPE)
        subprocess.run(["tar", "-x", "-C", tmp], stdin=archive.stdout, check=True)
        archive.wait()
        os.chmod(tmp, 0o755)
        container = ["docker", "run", "--rm", "--network", "none", "--hostname", "docs", "--user", "1000:1000",
                     "--read-only", "--tmpfs", "/tmp", "--cap-drop", "ALL", "--memory", "512m", "--pids-limit", "64",
                     "-e", "HOME=/tmp", "-e", "PYTHONDONTWRITEBYTECODE=1", "-e", "COLUMNS=100",
                     "-v", f"{tmp}:/project:ro", "-w", "/project", image, "python3"]

        def helped(*words: str) -> str:
            try:
                done = subprocess.run([*container, *words, "--help"], capture_output=True,
                                      text=True, errors="replace", timeout=60)
            except subprocess.TimeoutExpired:
                return ""
            return done.stdout if done.returncode == 0 else ""

        for entry in entry_points:
            if entry["kind"] != "python-cli":
                continue
            text = helped(entry["path"])
            if not text:
                continue
            name = entry["path"].replace("/", "__")
            (out / f"{name}.txt").write_text(text)
            entry["help_file"] = f"help/{name}.txt"
            listed = re.search(r"\{([\w,-]+)\}", text)
            if listed:
                entry["actions"] = listed.group(1).split(",")
            entry["action_help_files"] = {}
            for action in entry["actions"][:20]:
                action_text = helped(entry["path"], action)
                if action_text:
                    (out / f"{name}__{action}.txt").write_text(action_text)
                    entry["action_help_files"][action] = f"help/{name}__{action}.txt"


def survey_history(repo: Path, ref: str) -> dict:
    merges = []
    for line in git(repo, "log", "--merges", "--first-parent", "-n", "40", "--date=short",
                    "--format=%h%x09%ad%x09%s", ref).splitlines():
        commit, date, subject = line.split("\t", 2)
        branch = re.search(r"\b((?:topic|feature|fix|rehearsal)/[\w./-]+)", subject)
        issue = re.search(r"\bissue[ #]*(\d+)\b|\bi(\d+)[-_]", subject, re.I)
        merges.append({"commit": commit, "date": date, "subject": subject,
                       "branch": branch.group(1).rstrip(":.") if branch else None,
                       "issue": int(next(g for g in issue.groups() if g)) if issue else None})
    dates = git(repo, "log", "--date=short", "--format=%ad", ref).splitlines()
    prefixes = Counter(m["branch"].split("/")[0] for m in merges if m["branch"])
    return {
        "ref": ref,
        "commits": len(dates),
        "first_commit": dates[-1] if dates else None,
        "last_commit": dates[0] if dates else None,
        "merge_count_sampled": len(merges),
        "branch_prefixes": dict(prefixes),
        "uses_topic_branches": bool(prefixes),
        "uses_issue_numbers": sum(1 for m in merges if m["issue"]) >= max(1, len(merges) // 3),
        "recent_merges": merges[:15],
    }


def docker_answers() -> bool:
    """True when the program `docker` exists and its server answers."""
    try:
        return subprocess.run(["docker", "version"], capture_output=True).returncode == 0
    except OSError:
        return False  # The program is absent, or the system cannot start it.


def survey_command(repo: Path | str, options: dict, **changed) -> str:
    """The complete `survey` command for one project repository: the options of one survey, with the changed ones."""
    chosen = {**options, **changed}
    words = ["--repo", str(repo)]
    for name in ("project", "release_ref", "develop_ref"):
        if chosen.get(name):
            words += ["--" + name.replace("_", "-"), chosen[name]]
    words += ["--" + name.replace("_", "-") for name in ("run_help", "update") if chosen.get(name)]
    return command("survey", *words)


def listed_projects() -> list[str] | None:
    """The project names of the project list of the site. None when the site has no list that the script can read."""
    try:
        projects = json.loads(PROJECTS.read_text())
        return [str(item.get("slug")) for item in projects]
    except (OSError, ValueError, AttributeError, TypeError):
        return None


def cmd_survey(args: argparse.Namespace) -> None:
    repo = top_of(Path(args.repo))
    options = {"project": args.project, "release_ref": args.release_ref, "develop_ref": args.develop_ref,
               "run_help": bool(args.run_help), "update": bool(args.update)}
    if repo.resolve() == SITE:
        fail("this directory is the tenant-docs repository, and not the repository of a project. Nothing changed. "
             f"Start the skill in the repository of the project. {TELL_USER}")
    project = args.project or repo.name
    if not SLUG.fullmatch(project):
        fail(f"'{project}' is not a project name of the site: a name has lowercase letters, digits and '-' only, and it "
             "starts and ends with a letter or a digit. Nothing changed. The option `--project` gives the name of the "
             f"project on the site. {TELL_USER}")
    branches = git(repo, "for-each-ref", "--format=%(refname:short)", "refs/heads").split()
    develop = args.develop_ref or next((b for b in ("main", "master") if b in branches), None)
    checked_out = ""
    if not develop:
        # The rule: `main`, else `master`, else the branch that is checked out. A detached HEAD is no branch.
        checked_out = develop = git(repo, "symbolic-ref", "--quiet", "--short", "HEAD", check=False).strip()
        if not develop:
            fail("the project has no branch main and no branch master, and its checkout has a detached HEAD. So the survey "
                 "does not know the branch that the Develop pages describe. Nothing changed. The option `--develop-ref` "
                 f"gives that branch. Do not choose a branch. {TELL_USER}")
    release = args.release_ref or ("portable" if "portable" in branches else develop)
    for ref in (develop, release):
        if not ref_exists(repo, ref):
            fail(f"the ref '{ref}' does not exist in {repo}")
    if args.run_help and not docker_answers():
        fail("--run-help needs Docker, and Docker does not answer. Nothing changed. Run the survey without --run-help: "
             + survey_command(repo, options, run_help=False))

    tags = release_tags(repo, release)
    release_tree = survey_tree(repo, release)
    # A help text of an earlier survey can describe an older release. `next` prints each saved text as a real help text.
    shutil.rmtree(WORK / project / "help", ignore_errors=True)
    if args.run_help:
        run_help(repo, release, release_tree["entry_points"], WORK / project / "help")
    facts = {
        "docgen": 1,
        "project": project,
        "options": options,
        "branches": branches,
        "has_release_branch": release != develop,
        "release": {"ref": release, "name": tags[0] if tags else release_tree["commit"], "recent_tags": tags[:8]},
        "history": survey_history(repo, develop),
        "trees": {
            "release": release_tree,
            "develop": release_tree if release == develop else survey_tree(repo, develop),
        },
    }
    out = WORK / facts["project"]
    out.mkdir(parents=True, exist_ok=True)
    (out / "facts.json").write_text(json.dumps(facts, indent=1) + "\n")
    (out / "repo").write_text(str(repo) + "\n")

    r = facts["trees"]["release"]
    print(f"project        {facts['project']}")
    listed = listed_projects()
    if listed is not None and project not in listed and args.update:
        # An update needs a doc set, and a doc set has a name of the list. The next command stops for another name.
        print(f"note           the project list of the site has no project '{project}', and an update needs the name that "
              f"the project has in that list. The names of the list are: {', '.join(listed) or '(none)'}. The option "
              "`--project` gives the name. Do not choose a name: the user gives it. With the name in place of the word "
              f"PROJECT, the survey is: {survey_command(repo, options, project='PROJECT')} Put this line into your report.")
    elif listed is not None and project not in listed:
        print(f"note           the project list of the site has no project '{project}'. `register` adds a new project with "
              f"this name. The option `--project` gives another name. The names of the list are: "
              f"{', '.join(listed) or '(none)'}. Continue, and put this line into your report.")
    print(f"release        {facts['release']['name']} (ref {release}, commit {r['commit']})")
    if not facts["release"]["recent_tags"]:
        print(f"note           the project has no release tag of the branch {release}, so the release is a commit.")
        print(f"               The capture script needs a tag of the form {release_tag.FORMS.format(release)}.")
        print("               A full doc set needs a release tag: `plan` stops without it.")
    elif commits_after(repo, tags[0], release):
        print(f"note           {after_release(commits_after(repo, tags[0], release), release, tags[0])}")
    print(f"develop        ref {develop}, {facts['history']['commits']} commits, "
          f"{facts['history']['merge_count_sampled']} merges sampled")
    if checked_out:
        print(f"note           the project has no branch main and no branch master. So the develop ref is the branch that is "
              f"checked out now: {checked_out}. The option `--develop-ref` gives another branch. Continue, and put this "
              "line into your report.")
    print(f"files          {r['file_count']} at the release ref")
    print(f"docs           {len(r['docs'])} markdown files")
    print(f"entry points   {len(r['entry_points'])}")
    print(f"wrote          {out / 'facts.json'}")
    # The first command of a skill says which run it is. So a doc set in the wrong state stops at `branch`.
    print("next           " + command("branch", "--project", facts["project"], *(["--update"] if args.update else [])))


# ---------- plan ----------

SURVEY_AGAIN = "Run the survey again in the project repository: it is the first command of the skill."
TELL_USER = "Stop and tell the user this line."


def read_json(path: Path, what: str, then: str):
    """Read one JSON file. An absent file and a file that is not valid JSON give one `error:` line that says what to do."""
    if not path.exists():
        fail(f"{what} is absent: {path}. {then}")
    try:
        return json.loads(path.read_text())
    except ValueError as error:  # no valid JSON, or no valid text
        fail(f"{what} is not valid JSON: {path}: {error}. {then}")


def facts_of(project: str, needed: bool = True) -> dict | None:
    """The facts of the last survey. With `needed` False, an absent file gives None: the action then runs without the facts."""
    path = WORK / project / "facts.json"
    if not needed and not path.exists():
        return None
    return read_json(path, f"the facts of '{project}' (run survey first)", SURVEY_AGAIN)


def plan_of(project: str) -> dict:
    return read_json(WORK / project / "plan.json", f"the plan of '{project}'",
                     f"Run first: {command('plan', '--project', project)}")


PATH_PART = re.compile(r"[\w.-]+")
CAPTURE_NAME = r"[A-Za-z0-9][\w.-]*"  # the name of a capture, as a capture mark gives it


def state_fault(state) -> str:
    """What is wrong with the form of a state. An empty text when each action can read it.

    The state names the files of the doc set. `commit` stages each of them, and `scaffold` removes a capture spec
    by its name. So a page name stays below the directory of the project, and a capture name is one file name.
    """
    if not isinstance(state, dict) or not isinstance(state.get("pages"), dict):
        return "the file does not hold an object with the key `pages`"
    for path, record in state["pages"].items():
        parts = path.split("/")
        if not all(PATH_PART.fullmatch(part) and part.strip(".") for part in parts):
            return f"the page name '{path}' is not a path below the directory of the project"
        if not isinstance(record, dict) or not isinstance(record.get("sources"), dict) \
                or not all(isinstance(record.get(key), str) for key in ("ref", "tree", "template")):
            return f"the record of the page '{path}' does not have the keys `ref`, `tree`, `template` and `sources`"
    captures = state.get("captures", {})
    if not isinstance(captures, dict):
        return "the key `captures` does not hold an object"
    for name in captures:
        if not re.fullmatch(CAPTURE_NAME, name):
            return f"the capture name '{name}' is not the name of a capture mark"
    return ""


def state_of(project: str) -> dict | None:
    """The state of the doc set of one project. None when the checkout has no state file.

    The script writes this file, and Git can leave conflict marks in it. An agent cannot merge it.
    """
    path = STATE / f"{project}.json"
    if not path.exists():
        return None
    then = "The script writes this file. Do not edit it. " + TELL_USER
    state = read_json(path, f"the state of '{project}'", then)
    if state_fault(state):
        fail(f"the state of '{project}' does not have the form of a state: {path}: {state_fault(state)}. {then}")
    return state


def kept_refs(project: str, facts: dict) -> None:
    """Stop when the last survey read another branch than the pages of the doc set describe.

    A survey takes its develop ref from the checkout of the project when the project has no `main` and no `master`.
    With another branch checked out, an update writes that branch into the tracked state, or it loses a page.
    The owner reviewed a doc set that is in `main`: its pages keep their branch, and the line gives the command.
    For a doc set with no review, the agent does not choose between the two branches.
    """
    state = state_of(project) or {}
    for name, option in (("release", "release_ref"), ("develop", "develop_ref")):
        recorded = sorted({record["ref"] for record in state.get("pages", {}).values() if record.get("tree") == name})
        now = facts["trees"][name]["ref"]
        if not recorded or now in recorded:
            continue
        message = (f"the pages of '{project}' describe the branch {recorded[0]}, and the last survey read the branch {now} "
                   "for them. Nothing changed. ")
        base = known_base() if site_checkout() else ""
        if base and holds_doc_set(base, project):
            repo = (WORK / project / "repo").read_text().strip() if (WORK / project / "repo").is_file() else "."
            fail(message + "Run first: " + survey_command(repo, facts.get("options") or {}, **{option: recorded[0]}))
        fail(message + f"The option `--{option.replace('_', '-')}` of `survey` gives the branch. Do not choose a branch. "
             + TELL_USER)


def condition(facts: dict, tree_facts: dict, when: str, sources: list[str]) -> tuple[bool, str]:
    if when == "always":
        return True, ""
    if when == "sources":
        return bool(sources), "no source file matches"
    if when == "entry_points":
        return bool(tree_facts["entry_points"]), "the project has no entry point"
    if when == "history":
        return facts["history"]["commits"] >= 5, "the history is too short"
    fail(f"the profile has an unknown condition '{when}'")
    return False, ""


def main_cli(tree_facts: dict) -> dict | None:
    """The command line of the project: the Python command line with the most actions.

    A workflow file, for example a scanner or a release script, is not the command line of the project.
    """
    workflow = {path for group in tree_facts["workflow"].values() for path in group}
    found = [e for e in tree_facts["entry_points"] if e["kind"] == "python-cli" and e["path"] not in workflow]
    return max(found, key=lambda e: len(e.get("actions") or []), default=None)


def actions_of(tree_facts: dict) -> list[str]:
    return list((main_cli(tree_facts) or {}).get("actions") or [])


def commands_of(tree_facts: dict) -> list[str]:
    """Each command that a reader can start, as a page names it. An action of the command line has its name only."""
    cli, found = main_cli(tree_facts), []
    for entry in tree_facts["entry_points"]:
        if entry is cli and entry.get("actions"):
            found += entry["actions"]
        elif entry["kind"] == "python-cli":
            found.append(f"python3 {entry['path']}")
        elif entry["kind"] == "compose" and "/" in entry["path"]:
            found.append(f"docker compose -f {entry['path']} up -d")
        else:
            found.append(entry["run"])
    return list(dict.fromkeys(found))


def expand(page: dict, tree_facts: dict) -> list[tuple[dict, dict]]:
    """The pages of one profile entry: one page, or one page for each action of the command line."""
    if page.get("each") != "action":
        return [(page, {})]
    return [({**page, "id": f"{page['id']}:{action}", "path": page["path"].replace("{action}", action.lower())},
             {"action": action, "index": index})
            for index, action in enumerate(actions_of(tree_facts)[: page.get("max_pages", 20)])]


def no_release_tag(release: str, branch: str) -> str:
    """The message for a full doc set of a project whose release is no release tag. Each release gets a tag."""
    return (f"'{release}' is not a release tag of the branch {branch}. A project with a full doc set needs a tag of the form "
            f"{release_tag.FORMS.format(branch)}. Do not make the tag. Stop and tell the user this line.")


def cmd_plan(args: argparse.Namespace) -> None:
    facts = facts_of(args.project)
    profile = read_json(PROFILES / f"{args.profile}.json", f"the profile '{args.profile}'", TELL_USER)
    kept_refs(args.project, facts)
    doc_set = args.doc_set
    release = facts["release"]
    if doc_set == "full" and release_tag.release_key(release["name"], release["ref"]) is None:
        # `register` stops for this project. So the run stops here, before the agent writes a slot.
        fail(no_release_tag(release["name"], release["ref"]))
    pages, skipped = [], []
    for entry in profile["pages"]:
        if doc_set not in entry["doc_sets"]:
            continue
        tree_facts = facts["trees"][entry["tree"]]
        expanded = expand(entry, tree_facts)
        if not expanded:
            skipped.append({"id": entry["id"], "reason": "the project has no command line with actions"})
        for page, page_vars in expanded:
            cli = main_cli(tree_facts)
            sources = []
            for pattern in page.get("sources", []):
                pattern = pattern.replace("{action}", page_vars.get("action", ""))
                if pattern == "@entry_points":
                    matches = [e["path"] for e in tree_facts["entry_points"] if e["kind"] in ("python-cli", "shell")][:12]
                elif pattern == "@cli":
                    matches = [cli["path"]] if cli else []
                elif pattern == "@process_docs":
                    matches = [p for group in tree_facts["workflow"].values() for p in group]
                else:
                    matches = [p for p in sorted(tree_facts["files"]) if fnmatch.fnmatch(p, pattern)]
                sources += [m for m in matches if m not in sources]
            if page.get("generated"):
                # A page that the script writes in full lists the documentation files of the survey, and no other
                # file. So only these files are its sources: a change of another file does not make the page stale.
                listed = {doc["path"] for doc in tree_facts["docs"]}
                sources = [source for source in sources if source in listed]
            sources = sources[: page.get("max_sources", 12)]
            ok, reason = condition(facts, tree_facts, page["when"], sources)
            if not ok:
                skipped.append({"id": page["id"], "reason": reason})
                continue
            pages.append({
                "id": page["id"], "path": page["path"], "template": page["template"], "tree": page["tree"],
                "ref": tree_facts["ref"], "generated": page.get("generated", False),
                "sources": {s: tree_facts["files"][s] for s in sources},
                "vars": page_vars, "nav": page.get("nav"),
            })
    plan = {"docgen": 1, "project": args.project, "profile": args.profile, "profile_status": profile["status"],
            "doc_set": doc_set, "pages": pages, "skipped": skipped}
    (WORK / args.project / "plan.json").write_text(json.dumps(plan, indent=1) + "\n")
    for page in pages:
        print(f"page     {page['path']:<28} {len(page['sources'])} sources at {page['ref']}")
    for item in skipped:
        print(f"skipped  {item['id']:<28} {item['reason']}")
    if profile["status"] != "final":
        print(f"note     the profile '{args.profile}' is {profile['status']}")
    # In an update, `status` comes next: it lists each page that the change of the project makes stale.
    following = "status" if site_checkout() and site_branch() == UPDATE_BRANCH.format(args.project) else "scaffold"
    print("next     " + command(following, "--project", args.project))


# ---------- templates ----------

IF_BLOCK = re.compile(r"^\{\{#if (\w+)\}\}\n(.*?)^\{\{/if\}\}\n", re.S | re.M)
NO_PAGE_SET = "This site has one overview page for this project."


def page_url(project: str, path: str) -> str:
    path = re.sub(r"\.mdx?$", "", re.sub(r"(^|/)index\.mdx?$", "", path))
    return f"/{project}/{path}/".replace("//", "/")


def description_of(project: str, summary: str) -> str:
    """The first sentence of the README summary, when it fits the rules of the site. If not, a fixed sentence."""
    text = " ".join(summary.replace("\\", " ").replace('"', "'").split())
    first = re.split(r"(?<=[.!?])\s", text, maxsplit=1)[0]
    if first and len(first.split()) <= 25 and len(first) <= 160 and not re.search(r"[<{\[`*]", first):
        return first
    return f"What {project} is, who it is for and what its status is."


def mdx_text(text: str) -> str:
    """Text of a project file as plain text of an MDX page: no tag, no expression, no table cell end."""
    return text.replace("|", "/").replace("<", "&lt;").replace("{", "&#123;").replace("}", "&#125;")


def docs_sections(tree_facts: dict) -> str:
    """One table for each directory that holds documentation files."""
    groups: dict[str, list[dict]] = {}
    for doc in tree_facts["docs"]:
        groups.setdefault(str(Path(doc["path"]).parent), []).append(doc)
    if not groups:
        return "This project has no documentation files."
    sections = []
    for directory in sorted(groups, key=lambda name: (name != ".", name)):
        heading = "## Top-level files" if directory == "." else f"## Files in `{directory}/`"
        rows = "\n".join(f"| `{d['path']}` | {mdx_text(d['title'] or '(no title)')} |" for d in groups[directory])
        sections.append(f"{heading}\n\n| File | Title |\n| --- | --- |\n{rows}")
    return "\n\n".join(sections)


def page_values(facts: dict, plan: dict, page: dict) -> dict[str, str]:
    """The values that a template can name as `{{name}}`. An empty value makes an `{{#if name}}` block absent."""
    project, tree_facts = facts["project"], facts["trees"][page["tree"]]
    readme = tree_facts.get("readme") or {}
    cli, actions = main_cli(tree_facts), actions_of(tree_facts)
    page_vars = page.get("vars") or {}
    index = page_vars.get("index", 0)
    others = [p for p in plan["pages"] if p["path"] != page["path"]]
    cards = "\n".join(f'\t<LinkCard title="{p["nav"]["title"]}" description="{p["nav"]["text"]}" '
                      f'href="{page_url(project, p["path"])}" />' for p in others if p.get("nav"))
    action_pages = {p["vars"]["action"]: p["path"] for p in plan["pages"] if (p.get("vars") or {}).get("action")}
    troubleshooting = next((d["path"] for d in tree_facts["docs"] if "troubleshoot" in d["path"].lower()), "")
    return {
        "project": project,
        "summary": description_of(project, readme.get("summary") or ""),
        "ref": page["ref"],
        "release": facts["release"]["name"],
        "sources": "\n".join(f"  {s}" for s in page["sources"]) or "  (none)",
        "docs_sections": docs_sections(tree_facts),
        "troubleshooting": troubleshooting,
        "site_pages": "\n".join(f"- [{p['nav']['title']}]({page_url(project, p['path'])}): {p['nav']['text']}"
                                for p in others if p.get("nav")),
        "where_next": f"## Where to go next\n\n<CardGrid>\n{cards}\n</CardGrid>" if cards else NO_PAGE_SET,
        "cli": f"python3 {cli['path']}" if cli else "",
        "cli_path": cli["path"] if cli else "",
        "actions": ", ".join(f"`{a}`" for a in actions),
        "action_links": "\n".join(f"- [`{a}`]({page_url(project, action_pages[a])})" for a in actions if a in action_pages),
        "no_actions": "" if actions else "yes",
        "command_list": ", ".join(f"`{c}`" for c in commands_of(tree_facts)),
        "test_command": (tree_facts["tests"] or [""])[0],
        "action": page_vars.get("action", ""),
        "order": str(index + 2),
        "help_order": str(152 + 2 * index),
        "cmd_order": str(600 + 10 * index),
    }


def render(template: str, facts: dict, plan: dict, page: dict) -> str:
    values = page_values(facts, plan, page)
    text = IF_BLOCK.sub(lambda m: m.group(2) if values.get(m.group(1)) else "", template)
    return re.sub(r"\{\{(\w+)\}\}", lambda m: values.get(m.group(1), m.group(0)), text)


# ---------- capture specs ----------

CAPTURE_MARK = re.compile(r"\{/\* docgen:capture (?P<name>" + CAPTURE_NAME + r") \| (?P<order>\d+) \| (?P<title>[^|]+?) \| "
                          r"(?P<kind>clone|run|slot)(?: (?P<value>.+?))? \*/\}")


def slot_command(slot: dict) -> tuple[str, str]:
    """The command line that a command slot gives to its capture, and the problem if the slot has no single one.

    A line that ends with a backslash continues. The sentence that the instruction gives for the case
    that the files have no answer is no command.
    """
    if slot["open"]:
        return "", ""
    lines = [line.strip() for line in slot["written"] if line.strip() and not line.strip().startswith("```")]
    if "\n".join(lines) == fallback_of(slot):
        return "", ""
    lines = [re.sub(r"^\$ ", "", line) for line in lines]
    if any(not line.endswith("\\") for line in lines[:-1]):
        return "", "the slot holds more than one command line. Keep one command line."
    return "\n  ".join(lines), ""


def capture_spec(project: str, mark: dict, slots: dict[str, dict]) -> tuple[dict | None, str]:
    """The spec of one capture mark, in the form that scripts/capture.py reads. See captures/README.md."""
    clone_dir = f'"$HOME/{project}"'
    setup, mode = [f"cd {clone_dir}"], "scripted"
    if mark["kind"] == "clone":
        # A capture shows no clone URL. The setup makes a link with the name of the placeholder.
        url = f"<the URL of the {project} repository>"
        command, setup = f"git clone '{url}' {clone_dir}", [f'ln -s /srv/{project}.git "$HOME/{url}"']
    elif mark["kind"] == "run":
        command = mark["value"] or ""
    else:
        slot = slots.get(mark["value"] or "")
        if slot is None:
            return None, f"the page has no slot '{mark['value']}'"
        if (slot.get("form") or "text") != "command":
            # The frame is the one place of a command. A slot that shows its command gives no capture.
            return None, f"the slot '{mark['value']}' does not have the form `command`"
        command, problem = slot_command(slot)
        if problem:
            return None, problem
        if not command:
            mode = "manual"  # The capture script skips the spec until the slot has its command.
    spec: dict = {"title": mark["title"].strip()}
    stage = re.match(r"stage(\d+)-", mark["name"])
    if stage:
        spec["stage"] = int(stage.group(1))
    spec.update({"order": int(mark["order"]), "command": command, "setup": setup, "mode": mode})
    return spec, ""


def sync_captures(project: str, state: dict) -> None:
    """Write one spec for each capture mark of the pages. Copy the command of a command slot into its spec.

    A spec that exists keeps each field that a person can change. Only the command of a command slot follows the page.
    """
    known = state.setdefault("captures", {})
    marks = written = 0
    read, found_names = set(), set()
    for path, _ in sorted(state["pages"].items(), key=lambda item: item[1].get("order", 0)):
        page = DOCS / project / path
        if not page.exists():
            continue
        text = page.read_text()
        read.add(path)
        slots = {slot["id"]: slot for slot in slots_of(text)}
        for found in CAPTURE_MARK.finditer(text):
            mark = found.groupdict()
            marks += 1
            found_names.add(mark["name"])
            file = CAPTURES / project / f"{mark['name']}.json"
            label = f"captures/{project}/{file.name}"
            if file.exists() and mark["name"] not in known:
                print(f"kept     {label}: the spec exists and docgen did not write it")
                continue
            spec, problem = capture_spec(project, mark, slots)
            if spec is None:
                print(f"skipped  {label}: {path}: {problem}")
                continue
            source = mark["kind"] if mark["kind"] != "slot" else f"slot {mark['value']}"
            if not file.exists():
                state_word = "wrote"
            else:
                current = json.loads(file.read_text())
                if mark["kind"] != "slot" or not spec["command"] or current.get("command") == spec["command"]:
                    known[mark["name"]] = {"page": path, "source": source}
                    continue
                # The slot has a new command. A spec that waited for its command becomes a scripted capture.
                waited = not current.get("command") and current.get("mode") == "manual"
                spec = {**current, "command": spec["command"], "mode": "scripted" if waited else current.get("mode", "scripted")}
                state_word = "updated"
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_text(json.dumps(spec, indent=2, ensure_ascii=False) + "\n")
            known[mark["name"]] = {"page": path, "source": source}
            written += 1
            waits = "" if spec["command"] else " (it waits for the command of the slot)"
            print(f"{state_word:<8} {label}: {spec['mode']}{waits}")
    # A page can lose a frame: its slot states that the sources have no such command. No source, no spec.
    for name in sorted(known):
        if known[name].get("page") in read and name not in found_names:
            file = CAPTURES / project / f"{name}.json"
            if file.exists():
                file.unlink()
            del known[name]
            print(f"removed  captures/{project}/{name}.json: the page has no frame for this capture")
    if marks:
        print(f"captures {marks} command slot(s), {written} spec(s) written")


# ---------- parts of a page that depend on a slot ----------

# A template marks a part that the page has only while a slot holds a command, and a part that the page has
# only while that slot holds its sentence for "the sources state no such command":
#   {/* docgen:with <slot> */} ... {/* docgen:end-with */}
#   {/* docgen:without <slot> */} ... {/* docgen:end-without */}
# The marker lines stay on the page. `scaffold` takes the lines between them from the template.
PART_OPEN = re.compile(r"^\s*\{/\* docgen:(?P<kind>with|without) (?P<slot>[\w-]+) \*/\}\s*$")
PART_END = re.compile(r"^\s*\{/\* docgen:end-(?P<kind>with|without) \*/\}\s*$")


def parts_of(text: str) -> list[dict]:
    """Each marked part of a page or of a template: its kind, its slot, and its lines between the marker lines.

    A part ends at its own end line only. A part with no end line is not complete: its `end` is None, and its
    lines stop before the next docgen line that no part holds: a line of a slot, a marker of a part or a diagram
    comment. No action changes a part that is not complete, because the lines after it are not lines of the part.
    """
    parts, current = [], None
    for index, line in enumerate(text.splitlines()):
        opened, closed = PART_OPEN.match(line), PART_END.match(line)
        if current and closed and closed.group("kind") == current["kind"]:
            current["end"] = index
            parts.append(current)
            current = None
            continue
        if current and (opened or closed or SLOT_OPEN.search(line) or SLOT_END in line or DIAGRAM.search(line)
                        or line.strip() == DIAGRAM_END):
            parts.append({**current, "end": None})
            current = None
        if opened:
            current = {**opened.groupdict(), "start": index, "body": []}
        elif current:
            current["body"].append(line)
    if current:
        parts.append({**current, "end": None})
    return parts


def states_no_answer(slot: dict | None) -> bool:
    """True when the slot holds the sentence that its instruction gives for "the files have no answer"."""
    if slot is None or slot["open"] or not fallback_of(slot):
        return False
    return "\n".join(line.strip() for line in slot["written"] if line.strip()) == fallback_of(slot)


def part_faults(text: str) -> list[tuple[dict, bool]]:
    """Each part of a page that does not agree with its slot, and if the page must have the part."""
    slots = {slot["id"]: slot for slot in slots_of(text)}
    faults = []
    for part in parts_of(text):
        if part["end"] is None:
            continue  # The part has no end line. `docgen-line` reports that line, and `scaffold` does not change the part.
        wanted = (part["kind"] == "with") != states_no_answer(slots.get(part["slot"]))
        if wanted != any(line.strip() for line in part["body"]):
            faults.append((part, wanted))
    return faults


def sync_parts(text: str, template: str) -> str:
    """The page with each marked part as its slot needs it. A part that comes back has the lines of the template."""
    source: dict[tuple, list] = {}
    for part in parts_of(template):
        source.setdefault((part["kind"], part["slot"]), []).append(part["body"])
    wanted_of = {part["start"]: wanted for part, wanted in part_faults(text)}
    lines, count, changes = text.splitlines(), {}, []
    for part in parts_of(text):
        key = (part["kind"], part["slot"])
        bodies = source.get(key) or []
        body = bodies[count.get(key, 0)] if count.get(key, 0) < len(bodies) else None
        count[key] = count.get(key, 0) + 1
        if part["end"] is not None and part["start"] in wanted_of and (body is not None or not wanted_of[part["start"]]):
            changes.append((part, body if wanted_of[part["start"]] else []))
    # From the last part to the first, so the line numbers of the earlier parts stay correct.
    for part, body in reversed(changes):
        lines[part["start"] + 1:part["end"]] = body
    return "\n".join(lines) + ("\n" if text.endswith("\n") else "")


# ---------- scaffold ----------

def open_slots(project: str, state: dict) -> int:
    """The number of open slots in the pages of the state."""
    return sum(1 for path in state["pages"] if (DOCS / project / path).exists()
               for slot in slots_of((DOCS / project / path).read_text()) if slot["open"])


# The `Planned` note of a page of the site skeleton: one line that holds the component and no other text.
STUB = re.compile(r"(?m)^<Planned\b[^>]*/>[ \t]*$")


def page_name(project: str, value: str) -> str:
    """The path of a page as the state names it, from each form in which the script prints a page."""
    for start in (f"{DOCS / project}/", f"src/content/docs/{project}/", "./"):
        if value.startswith(start):
            value = value[len(start):]
    return value


def not_older(project: str, facts: dict, pages: list[dict]) -> None:
    """Stop when the plan of a page is older than the project repository.

    `scaffold --refresh` records the sources of the plan as the current sources of a page. With an old plan,
    it records old sources, and the page is stale again at the next `status`.
    """
    repo = project_repo(project)
    if repo is None:
        return  # No repository to compare with. `status` reads the same repository and says so.
    trees: dict[str, dict[str, str]] = {}
    for page in pages:
        ref = page["ref"]
        if ref not in trees:
            trees[ref] = tree(repo, ref)
        old = sorted(source for source, blob in page["sources"].items() if trees[ref].get(source) != blob)
        if not old:
            continue
        known = facts["trees"][page["tree"]]["files"]
        if all(known.get(source) == trees[ref].get(source) for source in old):
            fail(f"the plan of '{project}' is older than the facts of the last survey: the file {old[0]} of the project "
                 f"changed after `plan` ran. Nothing changed. Run first: {command('plan', '--project', project)}")
        fail(f"the facts of '{project}' are older than the project repository: the file {old[0]} changed after the "
             f"survey. Nothing changed. Run first: {survey_command(repo, facts.get('options') or {})}")


def cmd_scaffold(args: argparse.Namespace) -> None:
    project = args.project
    need_run_branch(project, "scaffold")
    facts = facts_of(project)
    plan = plan_of(project)
    state_path = STATE / f"{project}.json"
    state = state_of(project) or {"docgen": 1, "project": project, "pages": {}}

    # Each stop comes before the first write. A run that stops leaves each file as it was.
    kept_refs(project, facts)
    versions = SITE / "src" / "data" / "versions.json"
    released = read_data(versions, "the list of releases") if versions.exists() else None
    for name in state.get("captures", {}):
        spec = CAPTURES / project / f"{name}.json"
        if spec.exists():
            read_json(spec, f"the capture spec captures/{project}/{name}.json",
                      "`scaffold` cannot read this file. Do not edit it. " + TELL_USER)
    planned = {page["path"]: page for page in plan["pages"]}
    refresh = args.refresh
    if refresh is not None and refresh != "all":
        refresh = page_name(project, refresh)
        if refresh not in state["pages"]:
            # The names of the list are the pages that `status` lists: the pages of the state. `--refresh` records
            # the sources of such a page only. A page that a person wrote has no record, and an empty text names no page.
            fail(f"'{args.refresh}' is no page of the doc set of '{project}'. Nothing changed. The pages are: "
                 f"{', '.join(sorted(state['pages'])) or '(none)'}. Give one of these names after `--refresh`. "
                 "`status` prints the complete command below each stale page.")
        if refresh not in planned:
            # The state lists the page, and the plan does not: the project lost each source file of the page.
            reason = next((f" ({item['reason']})" for item in plan.get("skipped", [])
                           if item["id"] == state["pages"][refresh].get("template")), "")
            fail(f"the plan of '{project}' does not have the page {refresh}{reason}, so `scaffold` cannot record its "
                 f"sources. Nothing changed. Do not delete the page. {TELL_USER}")
    if refresh:
        not_older(project, facts, [page for page in plan["pages"] if page["path"] in state["pages"]
                                   and (refresh in ("all", page["path"]) or page["generated"])])

    state.update({"profile": plan["profile"], "doc_set": plan["doc_set"], "release": facts["release"]["name"],
                  "release_ref": facts["release"]["ref"]})
    for page in plan["pages"]:
        path = page["path"]
        target = DOCS / project / path
        record = {"order": plan["pages"].index(page), "template": page["template"], "tree": page["tree"], "ref": page["ref"],
                  "generated": page["generated"], "sources": page["sources"]}
        if page.get("vars"):
            record["vars"] = page["vars"]
        known = path in state["pages"]
        text = target.read_text() if target.exists() else None
        template = (PROFILES / plan["profile"] / f"{page['template']}.mdx").read_text()
        if known and text is not None and refresh in ("all", path) and not page["generated"]:
            # The agent corrected the page. Record the sources as they are now.
            before = state["pages"][path].get("sources") or {}
            lost = [source for source in before if source not in record["sources"]]
            new = [source for source in record["sources"] if source not in before]
            state["pages"][path] = record
            print(f"recorded {path:<28} the sources of the page are current")
            if len(lost) > len(new):
                # A file with a new name, or a file that is gone. The plan names no file in its place.
                print(f"note     {path}: the record of the page does not hold {' and '.join(lost)} now, and the plan gives "
                      "no file in its place. A later change of that text does not make this page stale. "
                      "Put this line into your report.")
            continue
        if known and page["generated"]:
            # The script writes this page in full. Its record follows the plan, also when the text does not change.
            rendered = render(template, facts, plan, page)
            rendered = sync_parts(rendered, rendered)
            state["pages"][path] = record
            if text == rendered and refresh in ("all", path):
                print(f"recorded {path:<28} the sources of the page are current")
            elif text == rendered:
                print(f"kept     {path:<28} the page exists")
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(rendered)
                print(f"wrote    {path:<28} complete")
            continue
        # A page of the site skeleton with the `Planned` note has no content. Docgen replaces it.
        # A page that docgen wrote is no such page, also when a slot names the component.
        stub = text is not None and not known and bool(STUB.search(text))
        if text is not None and not stub:
            if not known:
                print(f"kept     {path:<28} the page exists and docgen did not write it")
                continue
            # A slot can state that the sources have no command. The page then has a sentence and no frame.
            synced = sync_parts(text, render(template, facts, plan, page))
            if synced != text:
                target.write_text(synced)
                print(f"updated  {path:<28} the parts of the page agree with its command slots")
            else:
                print(f"kept     {path:<28} the page exists")
            for part in parts_of(synced):
                if part["end"] is None:
                    print(f"skipped  {path:<28} the part `docgen:{part['kind']} {part['slot']}` has no line "
                          f"`{{/* docgen:end-{part['kind']} */}}`, so the script does not change this part. Continue: "
                          "`check` prints the line to put back.")
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        rendered = render(template, facts, plan, page)
        target.write_text(sync_parts(rendered, rendered))  # An open slot states nothing: the page has each frame.
        state["pages"][path] = record
        print(f"wrote    {path:<28} {'complete' if page['generated'] else 'has open slots'}")
    sync_captures(project, state)
    STATE.mkdir(parents=True, exist_ok=True)
    recorded = json.dumps(state, indent=1, sort_keys=True) + "\n"
    if not state_path.exists() or state_path.read_text() != recorded:
        state_path.write_text(recorded)
    if isinstance(released, dict) and project not in released:
        print(f"note     src/data/versions.json has no release of {project}. A page with `DocVersion` does not build "
              "without it. `register` sets the release. Continue.")
    # The order of a run: write each open slot, then run `scaffold` again, then `register`.
    # In an update, `status` comes after `scaffold`: it lists the pages that are stale then.
    if open_slots(project, state):
        following = "next"
    elif args.refresh or (site_checkout() and site_branch() == UPDATE_BRANCH.format(project)):
        following = "status"
    else:
        following = "register"
    print("next     " + command(following, "--project", project))


# ---------- slots ----------

def slots_of(text: str) -> list[dict]:
    lines, slots, current = text.splitlines(), [], None
    for number, line in enumerate(lines, 1):
        opened = SLOT_OPEN.search(line)
        if opened:
            current = {**opened.groupdict(), "line": number, "body": []}
        elif SLOT_END in line and current:
            marks = [line.strip() for line in current["body"]]
            current["hidden"] = COMMAND_OPEN in marks and COMMAND_END in marks[marks.index(COMMAND_OPEN):]
            current["written"] = [line for line in current["body"]
                                  if not (current["hidden"] and line.strip() in (COMMAND_OPEN, COMMAND_END))]
            body = "\n".join(current["written"])
            current.update(open=bool(TODO.search(body)), words=len(re.findall(r"[\w'-]+", re.sub(r"`[^`]*`|<[^>]+>", "x", body))),
                           end=line)
            slots.append(current)
            current = None
        elif current:
            current["body"].append(line)
    return slots


def project_state(project: str, doc_set_exists: bool = False) -> dict:
    """The state of the doc set of one project.

    `next` and `check` are steps of a first doc set: with no state, the next step is `scaffold`.
    `doc_set_exists` is for an action that needs a doc set that a run before this one made (`status`, `diagrams`).
    With no state, this checkout has no doc set, and `scaffold` here makes a second, empty doc set.
    """
    state = state_of(project)
    if state is not None:
        return state
    if not doc_set_exists:
        fail(f"the state of '{project}' (run scaffold first) is absent: {STATE / f'{project}.json'}. "
             f"Run first: {command('scaffold', '--project', project)}")
    message = f"this checkout of the site has no doc set of '{project}': the file docgen/state/{project}.json is absent. "
    first = RUN_BRANCH.format(project)
    base = known_base() if site_checkout() else ""
    if base and holds_doc_set(base, project):
        fail(message + f"The doc set is in main. Run first: {command('branch', '--project', project, '--update')}")
    if base and any(site_ref(ref) and holds_doc_set(ref, project) for ref in (f"refs/heads/{first}", f"refs/remotes/origin/{first}")):
        fail(message + f"The branch {first} holds it: it waits for the review. Stop and tell the user this line.")
    fail(message + "No branch holds it: the skill tenant-docs-generate makes it. Stop and tell the user this line.")


# What `next` prints for each form of a slot. A small model reads only these lines.
FORMS = {
    "text": ["Plain sentences in one or more paragraphs. No heading and no table."],
    "list": ["A list. Each item is one line that starts with `- `."],
    "numbered": ["A numbered list. Each item is one line that starts with a number and a point: `1. `, then `2. `."],
    "table": ["A Markdown table. Line 1 has the column names. Line 2 is `| --- | --- |`, with one `---` for each column.",
              "Each later line is one row. Each line starts with `|` and ends with `|`."],
    "steps": ["A numbered list of steps, nine steps at most. The first line of a step is `1. ` and one sentence with one action.",
              "Then an empty line, then the exact command in a code block. Then an empty line, then one line that starts with `Result:`.",
              "When the files give no command for a step, the step has no code block. Do not build a command.",
              "Put three spaces before each line of a step that is not its first line. Example:",
              "",
              "1. Copy the example file.",
              "",
              "   ```sh",
              "   cp .env.example .env",
              "   ```",
              "",
              "   Result: the file `.env` exists."],
    "command": ["One command line and no other text. Do not put it in backticks.",
                "Keep the line `{/* docgen:command` above it and the line `*/}` below it.",
                "The page shows the command in the frame of its capture, not at this place."],
}
RULES = [
    "Write only what the files say. One idea in each sentence. A sentence has 25 words at most, and 20 in a step.",
    "Use the active voice and the present tense. Put each command, path, option and file name in backticks.",
    "Write no host name, no IP address, no user name, no home path, no internal URL, no password and no key.",
    "Do not copy terminal output into the page. A capture shows the output.",
]
# A command slot holds no sentence, and its command has no backticks. So it has its own rules.
COMMAND_RULES = [
    "Copy the command from one of the files. Do not build a command, and do not change it.",
    RULES[2],
]


# The text for one part of a slot that has no answer in the files. The form of the slot stays.
NO_ANSWER = "The sources do not state this."
NO_ANSWER_PART = {
    "text": "For one fact that the files do not state, write one sentence that starts with `The sources do not state`.",
    "list": "For one item that the files do not state, write in that item: {}",
    "numbered": "For one item that the files do not state, write in that item: {}",
    "table": "For one cell that the files do not state, write in that cell: {}",
    "steps": "For a result that the files do not state, write the line: Result: {}",
}


def no_answer_lines(slot: dict) -> list[str]:
    """What `next` prints for the case that the files have no answer: for one part of the slot, and for the full slot.

    A slot keeps its form. The text of the full slot is the `write:` sentence of its instruction, and only that
    sentence passes the form check and the length check. A slot with no such sentence has no text for this case.
    """
    form, instruction = slot.get("form") or "text", slot["text"]
    lines = []
    # An instruction can give its own words for one part, for example: Write "Not stated" in a cell when ...
    own = re.search(r'\bWrite "([^"]+)" (?:in a cell )?when ', instruction)
    one_sentence = form == "text" and re.search(r"\bone sentence that starts with `", instruction)
    if form != "command" and not one_sentence:
        lines.append("Keep the form. " + NO_ANSWER_PART[form].format(own.group(1) if own else NO_ANSWER))
    whole = "the files give no such command" if form == "command" else "the files have no answer for the full slot"
    if fallback_of(slot):
        return lines + [f"When {whole}, write only this text: {fallback_of(slot)}"]
    return lines + [f"When {whole}, stop. Tell the user the page and the slot."]


def fallback_of(slot: dict) -> str:
    """The sentence that the instruction gives for the case that the files have no answer."""
    found = re.search(r"\bwrite: (.+)$", slot["text"])
    return found.group(1).strip() if found else ""


NEAR = 0.85  # two sentences are near to each other from this ratio of equal characters
# The first words of a sentence that says "no answer". No command starts with them.
SENTENCE = re.compile(r"the (?:sources?|readme|repository|files?|project) ", re.I)
# A placeholder in angle brackets, for example `<your host>`. A redirect such as `<in >out` is none.
PLACEHOLDER = re.compile(r"<[A-Za-z](?:[^<>|&;]*[A-Za-z0-9])?>")
# Words that say "no answer" in the place of a command. No command line is one of these texts.
NO_COMMAND = {"n/a", "na", "none", "not stated", "no command", "no test", "unknown", "tbd", "-"}


def placeholder_of(command_line: str) -> str:
    """The first placeholder in angle brackets of a command line. An empty text when it has none.

    Two redirects with no blank are no placeholder: `sort <in.txt>out.txt`. There the text in the brackets has
    the form of a file name: no blank, and a point or a `/`. And the name of the output file follows the `>` directly.
    """
    for found in PLACEHOLDER.finditer(command_line):
        inside, after = found.group(0)[1:-1], command_line[found.end():found.end() + 1]
        if not (" " not in inside and re.search(r"[./]", inside) and re.match(r"[\w./~$-]", after)):
            return found.group(0)
    return ""


def sentence_count(text: str) -> int:
    return len([part for part in re.split(r"(?<=[.!?])\s+", text.strip()) if part])


def bare(text: str) -> str:
    """A sentence with no case, no backticks, no quotes, no emphasis marks and no point. Two sentences compare in this form."""
    return " ".join(re.sub(r"[`*\"'.]", "", text.lower()).split())


def near_fallback(slot: dict, text: str) -> bool:
    """True when the text is a sentence for "no answer" that is not the exact `write:` sentence of the slot.

    The text is the `write:` sentence with a small change (a letter, a word, the last point, backticks),
    or it is the general sentence for one part of a slot. In a command slot, each such sentence counts.
    """
    fallback = fallback_of(slot)
    if text == fallback or not text:
        return False
    command_slot = (slot.get("form") or "text") == "command"
    if command_slot and (SENTENCE.match(bare(text)) or bare(text) in {bare(NO_ANSWER), *NO_COMMAND}):
        return True
    if not fallback:
        return False
    if bare(text) in (bare(fallback), bare(NO_ANSWER)):
        return True
    # A text with more sentences is an answer for one part: one fact that the files do not state, and one that they state.
    if not command_slot and sentence_count(text) != sentence_count(fallback):
        return False
    return difflib.SequenceMatcher(None, bare(text), bare(fallback)).ratio() >= NEAR


def blanks_before(line: str) -> int:
    return len(line) - len(line.lstrip())


def blank_count(count: int) -> str:
    return "no blank" if not count else f"{count} blank{'s' if count > 1 else ''}"


def first_line_changed(slot: dict, model: dict | None) -> bool:
    """True when the first line of a slot does not have the word range and the form that its template gives."""
    return bool(model) and any(slot[key] != model[key] for key in ("min", "max")) \
        or bool(model) and (slot.get("form") or "text") != (model.get("form") or "text")


def slot_problems(slot: dict, model: dict | None = None) -> list[str]:
    """The faults in the form of one written slot. Each fault stops the build or breaks the page.

    `model` is the same slot in the template of the page. It gives the word range, the form and the end line
    that the script wrote. Without it, the lines of the page are the only source.
    """
    form, body = slot.get("form") or "text", slot["body"]
    if slot["open"]:
        return []
    if first_line_changed(slot, model):
        # The form and the word range of the page are not the ones of the template. No other check can use them.
        return [f"the comment line above the slot is not the line that the script wrote. It must hold "
                f"`| {model['min']}-{model['max']} words | {model.get('form') or 'text'} |`. Put these values back."]
    text = "\n".join(slot["written"]).strip()
    fallback = fallback_of(slot)
    problems, fenced, prose = [], False, []
    if form == "command" and not slot["hidden"]:
        # The text of a command slot is not text of the page. Only the two lines around it make it a comment.
        # This is true also for the `write:` sentence: without the two lines, the page shows it two times.
        return [f"the text of the slot is not between the line `{COMMAND_OPEN}` and the line `{COMMAND_END}`. "
                "Put these two lines back: one above the text and one below it. Use no backticks."]
    if form == "command":
        marks = [line.strip() for line in body]
        for mark in (COMMAND_OPEN, COMMAND_END):
            if marks.count(mark) > 1:
                # The page shows the second line as text, or the second line ends the comment at a wrong place.
                second = slot["line"] + 1 + [at for at, line in enumerate(marks) if line == mark][1]
                problems.append(f"the slot has {marks.count(mark)} lines `{mark}`, and it needs one. Remove line {second} "
                                f"of the page: it is the second line `{mark}`.")
                break  # One line at a time: the number of each later line changes when this line goes.
    end = model["end"] if model else None
    if form == "steps" and end is not None and blanks_before(slot["end"]) != blanks_before(end):
        # With the wrong blanks, the line ends the list of steps at the wrong place, and the build stops.
        problems.append(f"the line `{SLOT_END}` below the slot has {blank_count(blanks_before(slot['end']))} before it, "
                        f"and the script wrote it with {blank_count(blanks_before(end))}. Write that line with exactly "
                        f"{blank_count(blanks_before(end))} before it.")
    if fallback and text == fallback:
        return problems
    if near_fallback(slot, text):
        # The exact sentence is the one text that says "no answer" for the full slot. A form fault is not the cause.
        needs = "it needs one command line" if form == "command" else "it is not the exact sentence of this slot for that case"
        exact = (f"write exactly this text and no other text: {fallback}" if fallback
                 else "stop. Tell the user the page and the slot.")
        other = ("If the files give the command, write that command line." if form == "command"
                 else "If the files have an answer, write the answer in the form of the slot.")
        return problems + [f"the slot holds a sentence for \"no answer\", and {needs}. If the files have no answer, {exact} {other}"]
    if form == "command":
        if "*/" in text:
            problems.append("the command holds `*/`. These two characters end the comment and stop the build. "
                            "Write the path without `*/`.")
        if any(line.strip().startswith("```") for line in slot["written"]):
            problems.append("the command is in a code block. Remove each line with ``` and keep the command line. "
                            "The command has no code block.")
        command_line = slot_command(slot)[0]
        if len(command_line) > 1 and command_line.startswith("`") and command_line.endswith("`"):
            problems.append("the command is in backticks. Remove the backtick before it and the backtick after it.")
        placeholder = placeholder_of(command_line)
        if placeholder:
            problems.append(f"the command holds the placeholder `{placeholder}`. The command must run as it is. "
                            "Write the example value of the files in its place.")
        body = []
    for line in body:
        if line.strip().startswith("```"):
            fenced = not fenced
        elif not fenced:
            prose.append(line)
    if fenced:
        problems.append("a code block has no closing line. Add a line with ``` after the code.")
    plain = [line for line in prose if line.strip()]
    named = re.compile(rf"(?<![\w-]){re.escape(slot['id'])}(?![\w-])")
    for line in plain:
        if line.strip().startswith("{/* docgen"):
            # A docgen comment is no text of a slot. In backticks, the page shows the instruction of the script.
            problems.append(f"the line `{line.strip()[:40]}` is a docgen comment line inside the text of the slot. "
                            "Remove this line. Do not put it in backticks.")
            break
        inner = line.strip().strip("`").strip()
        # A word after the end of the comment: the comment in backticks is a part of a sentence. That is text of the page.
        sentence = re.search(r"\w", inner.partition("*/}")[2])
        if inner.startswith("{/* docgen") and named.search(inner) and not sentence:
            # The agent put the line of this slot in backticks. The build passes, and the page shows the line.
            problems.append(f"the line `{inner[:40]}` is a docgen comment line in backticks inside the text of the slot. "
                            "The page shows it as text. Remove this line.")
            break
        if re.search(r"[<{]", re.sub(r"`[^`]*`", "", line)):
            problems.append(f"the line `{line.strip()[:40]}` has `<` or `{{` outside backticks. Put that word in backticks.")
            break
    if any(re.match(r"\s{0,3}#{1,6} ", line) for line in plain):
        problems.append("the slot has a heading. Remove the line that starts with `#`.")
    # An instruction can give the first words of the text, for example the start of a command line.
    start = re.search(r"starts with `([^`]+)`", slot["text"])
    written = slot_command(slot)[0] if form == "command" else text
    if start and written and not written.startswith(start.group(1)):
        problems.append(f"the text does not start with `{start.group(1)}`. Start it with these words.")
    if form == "command":
        problem = slot_command(slot)[1]
        if problem:
            problems.append(problem)
    elif form == "table":
        if len(plain) < 3 or not all(line.strip().startswith("|") for line in plain) or not re.match(r"\s*\|[\s:|-]+\|\s*$", plain[1]):
            problems.append("the slot is not one Markdown table. Write the column names, then `| --- | --- |`, then one line for each row.")
    elif form in ("list", "numbered"):
        start = r"- \S" if form == "list" else r"\d+\. \S"
        if not all(re.match(start, line) or line.startswith("  ") for line in plain) or not re.match(start, plain[0] if plain else ""):
            problems.append("the slot is not one list. Start each item with " + ("`- `." if form == "list" else "a number and a point."))
    elif form == "steps":
        lines = [line for line in body if line.strip()]
        if not lines or not re.match(r"1\. \S", lines[0]):
            problems.append("the slot does not start with the step `1. `.")
        for line in lines:
            if not re.match(r"\d+\. \S", line) and not line.startswith("   "):
                problems.append(f"the line `{line.strip()[:40]}` is not inside a step. Put three spaces before it.")
                break
        if sum(1 for line in lines if re.match(r"\d+\. \S", line)) > 9:
            problems.append("the slot has more than nine steps. Put two small steps into one step, or remove a step.")
    elif any(line.strip().startswith("|") for line in plain):
        problems.append("the slot has a table. Write plain sentences.")
    return problems


def fact_lines(template: str, facts: dict, record: dict) -> list[str]:
    """The facts of the survey that one page needs. The agent does not read facts.json."""
    tree_facts = facts["trees"][record["tree"]]
    history, workflow = facts["history"], tree_facts["workflow"]
    if template == "install":
        lines = [f"manifest files: {', '.join(tree_facts['manifests']) or 'none'}"]
        # One line for each Compose file. A project can have a second Compose file that is no source of the page.
        compose = [entry for entry in tree_facts["entry_points"] if entry["kind"] == "compose"]
        for entry in compose:
            services = ", ".join(entry.get("services", [])) or "none"
            other = "" if entry["path"] in (record.get("sources") or {}) else " This file is not a source file of this page."
            lines.append(f"services of the Compose file {entry['path']}: {services}.{other}")
        if not compose:
            lines.append("services of a Compose file: none. The project has no Compose file.")
        return lines + [f"test commands: {', '.join(tree_facts['tests']) or 'none'}"]
    if template == "commands":
        return [f"commands: {', '.join(commands_of(tree_facts)) or 'none'}"]
    if template == "workflow":
        lines = [f"branches: {', '.join(facts['branches'])}",
                 f"release branch: {facts['release']['ref']}. Develop branch: {history['ref']}.",
                 f"topic branches in the merges: {'yes' if history['uses_topic_branches'] else 'no'}. "
                 f"Issue numbers in the merges: {'yes' if history['uses_issue_numbers'] else 'no'}.",
                 f"test commands: {', '.join(tree_facts['tests']) or 'none'}"]
        lines += [f"{name.replace('_', ' ')}: {', '.join(paths)}" for name, paths in workflow.items() if paths]
        lines += [f"merge: {m['subject']}" for m in history["recent_merges"][:5]]
        return lines
    return []


# One read command prints this much at most. The shell tool of an agent shows a longer output only in part:
# one tool keeps the last 2000 lines or 50 KB, and another tool shows the first 30000 characters.
READ_BYTES = 20_000
READ_LINES = 400


def file_parts(data: bytes) -> list[tuple[int, int]]:
    """The line ranges that hold one file in parts, first line and last line. Each part is below the size of one read."""
    lines = data.split(b"\n")
    if lines and not lines[-1]:
        lines.pop()
    parts, first, size = [], 1, 0
    for number, line in enumerate(lines, 1):
        if number > first and (size + len(line) + 1 > READ_BYTES or number - first >= READ_LINES):
            parts.append((first, number - 1))
            first, size = number, 0
        size += len(line) + 1
    return parts + [(first, len(lines))] if lines else []


def size_text(data: bytes) -> str:
    lines = data.count(b"\n") + (1 if data and not data.endswith(b"\n") else 0)
    size = f"{len(data)} bytes" if len(data) < 1024 else f"{-(-len(data) // 1024)} KB"
    return f"{lines} line{'s' if lines != 1 else ''}, {size}"


def read_lines(repo: str, ref: str, source: str) -> list[str]:
    """What `next` prints for one file to read: its name with its size, and one read command for each part.

    A small file has one command. A large file has one command for each part, so that no tool cuts the output.
    """
    name = f"{ref}:{source}"
    whole = f"git -C {shlex.quote(repo)} show {shlex.quote(name)}"
    done = subprocess.run(["git", "-C", repo, "show", name], capture_output=True) if Path(repo).is_dir() else None
    if done is None or done.returncode != 0:
        return [f"{source}:", f"  {whole}"]  # Git cannot read the file here. The command is the one of each survey.
    parts = file_parts(done.stdout)
    if len(parts) <= 1:
        return [f"{source} ({size_text(done.stdout)}):", f"  {whole}"]
    return [f"{source} ({size_text(done.stdout)}). The file is large. Read it in {len(parts)} parts, "
            "with one command for each part:", *(f"  {whole} | sed -n {first},{last}p" for first, last in parts)]


def cmd_next(args: argparse.Namespace) -> None:
    state = project_state(args.project)
    repo = (WORK / args.project / "repo").read_text().strip() if (WORK / args.project / "repo").exists() else "<repo>"
    again = command("next", "--project", args.project)
    facts = facts_of(args.project, needed=False)
    remaining = 0
    first = faulty = None
    ordered = [(path, DOCS / args.project / path, record)
               for path, record in sorted(state["pages"].items(), key=lambda item: item[1].get("order", 0))]
    ordered = [entry for entry in ordered if entry[1].exists()]
    # A value of one host in a written slot is a problem of that slot. The agent corrects it while it knows the slot.
    hosts: dict[tuple[Path, int], list[str]] = {}
    for item in host_values(args.project, [page for _, page, _ in ordered]):
        hosts.setdefault((item["file"], item["line"]), []).append(
            f"line {item['line']} holds {host_message(item)}. {item['fix'][0].upper()}{item['fix'][1:]}")

    def problems_of(page: Path, record: dict, slot: dict) -> list[str]:
        lines = range(slot["line"] + 1, slot["line"] + 1 + len(slot["body"]))
        return slot_problems(slot, template_slots(state, record).get(slot["id"])) \
            + [problem for number in lines for problem in hosts.get((page, number), [])]

    for path, page, record in ordered:
        for slot in slots_of(page.read_text()):
            if slot["open"]:
                remaining += 1
                first = first or (path, page, record, slot)
            elif not faulty and problems_of(page, record, slot):
                faulty = (page, record, slot)
    if faulty:
        # A fault in a written slot comes first. The agent corrects it while it knows the slot.
        page, record, slot = faulty
        print(f"correct      the slot {slot['id']} (line {slot['line']}) of {page}")
        for problem in problems_of(page, record, slot):
            print(f"problem      {problem}")
        print(f"next         {again}")
        return
    if not first:
        print("No open slot.")
        print("             The next command copies the command of each command slot into its capture spec.")
        print(f"next         {command('scaffold', '--project', args.project)}")
        return
    path, page, record, slot = first
    form = slot.get("form") or "text"
    placeholder = next(line for line in slot["body"] if TODO.search(line))
    print(f"open slots   {remaining}")
    print(f"page         {page}")
    print(f"slot         {slot['id']} (line {slot['line']})")
    print(f"write        {slot['text']}")
    print(f"form         {form}")
    for line in FORMS[form]:
        print(f"             {line}".rstrip())
    print(f"length       {slot['min']} to {slot['max']} words")
    for index, line in enumerate(no_answer_lines(slot)):
        print(f"{'no answer' if index == 0 else '':<12} {line}")
    for index, line in enumerate(COMMAND_RULES if form == "command" else RULES):
        print(f"{'rules' if index == 0 else '':<12} {line}")
    print("read first   these files of the project, at the ref that the page describes:")
    if any(not other["open"] and other["line"] < slot["line"] for other in slots_of(page.read_text())):
        # Each slot of a page names the same files. An agent that has their text does not read them again.
        print("             These are the same files as for the slot before of this page. "
              "Read a file again only when you do not have its text.")
    for source in record["sources"] or {"README.md": ""}:
        for line in read_lines(repo, record["ref"], source):
            print(f"             {line}")
    help_dir = WORK / args.project / "help"
    if record["template"] in ("commands", "command") and help_dir.is_dir():
        action = (record.get("vars") or {}).get("action")
        texts = sorted(t for t in help_dir.glob("*.txt") if not action or "__" not in t.stem or t.stem.endswith(f"__{action}"))
        if texts:
            print("             and the real help texts of the commands:")
        for text in texts:
            print(f"             cat {shlex.quote(str(text))}")
    for index, line in enumerate(fact_lines(record["template"], facts, record) if facts else []):
        print(f"{'facts' if index == 0 else '':<12} {line}")
    print("then         replace this one line of the page with your text:")
    print(f"             {placeholder.strip()}")
    print("             Keep the docgen comment line above the slot and the docgen comment line below it.")
    print(f"next         {again}")


# ---------- values of one host ----------

SCANNER = "scripts/scan.py"
SCAN_LINE = re.compile(r"FAIL  (?:host value|credential)  (?P<file>.+?)(?::(?P<line>\d+):(?P<column>\d+))?  "
                       r"rule (?P<rule>[\w-]+)(?:  (?P<rest>.*))?$")


def host_kind(rule: str, project: str) -> tuple[str, str]:
    """What a rule of the scanner finds, and the fix that fits."""
    for start, what, fix in HOST_KINDS:
        if rule.startswith(start):
            return what, fix.replace("{project}", project)
    return "a value of one host", "write a placeholder in its place."


def scanner_findings(files: list[Path]) -> list[tuple[Path, int, int, str, str]] | None:
    """What the scanner of the site finds in these files: the file, the line, the column, the rule and the value.

    The scanner reads a file by its path, also while Git does not track the file. It does not show a credential
    and a value of the local deny list: the value is then empty.
    None when the directory of docgen has no scanner, or when the scanner does not print its count line.
    """
    script = SITE / SCANNER
    if not script.is_file():
        return None
    if not files:
        return []
    done = subprocess.run([sys.executable, str(script), *map(str, files)], cwd=SITE, capture_output=True,
                          text=True, errors="replace")
    if not re.search(r"^scan: \d+ finding\(s\)", done.stdout, re.M):
        return None
    found = []
    for line in done.stdout.splitlines():
        match = SCAN_LINE.match(line)
        if match:
            rest = match.group("rest") or ""
            value = "" if rest.startswith("(") else rest.split("  (")[0]
            found.append((Path(match.group("file")), int(match.group("line") or 1), int(match.group("column") or 1),
                          match.group("rule"), value))
    return found


def own_paths(project: str) -> list[tuple[str, str, str]]:
    """The two paths of this machine that the script knows, each one also as its real path: the path, what it is, the fix.

    These are the site directory and the project clone of the last survey. `next` prints both. A generic rule
    does not find them in each directory, for example below a temporary directory.
    """
    site = {str(SITE), os.path.abspath(str(Path(__file__).parent.parent))}
    named = os.environ.get("TENANT_DOCS_DIR")
    if named and os.path.realpath(named) == str(SITE):
        site.add(os.path.abspath(named))
    clone = set()
    recorded = WORK / project / "repo"
    if recorded.is_file() and recorded.read_text().strip():
        clone = {recorded.read_text().strip(), os.path.realpath(recorded.read_text().strip())}
    found = [(path, "the path of the project clone on this machine",
              "remove the path. A command of a page runs in the directory of the clone, so it needs no absolute path. "
              f"For the directory of the clone, write `~/{project}`.") for path in sorted(clone)]
    found += [(path, "the path of the tenant-docs checkout on this machine",
               "remove the path. A page does not name the tenant-docs checkout.") for path in sorted(site - clone)]
    # A path with one part, for example `/srv`, is too general: a page of another project can hold it.
    return [entry for entry in found if entry[0].count("/") >= 2]


def host_values(project: str, files: list[Path]) -> list[dict]:
    """Each value of one host in these files: the file, the line, the column, what it is, the value and the fix.

    The scanner of the site finds the values, so `check` and the commit hook have one rule. In a directory with
    no scanner, the own list of docgen is the fallback. The two paths that the script knows come in addition.
    """
    found, taken = [], set()
    known = own_paths(project)
    for file in files:
        try:
            lines = file.read_text(errors="replace").splitlines()
        except OSError:
            continue
        for number, line in enumerate(lines, 1):
            for path, what, fix in known:
                # The path starts a word, or it is the path of a URL such as `file://<path>`.
                for match in re.finditer(r"(?:(?<![\w.~/-])|(?<=://))" + re.escape(path) + r"(?![\w-])(?!\.\w)", line):
                    if not any((file, number, column) in taken for column in range(match.start(), match.end())):
                        taken.update((file, number, column) for column in range(match.start(), match.end()))
                        found.append({"file": file, "line": number, "column": match.start() + 1, "what": what,
                                      "value": path, "fix": fix})
    scanned = scanner_findings(files)
    if scanned is None:
        scanned = []
        for file in files:
            try:
                lines = file.read_text(errors="replace").splitlines()
            except OSError:
                continue
            scanned += [(file, number, match.start() + 1, rule, match.group(0))
                        for number, line in enumerate(lines, 1) for rule, pattern in HOST_VALUES
                        for match in pattern.finditer(line)]
    for file, number, column, rule, value in scanned:
        if (file, number, column - 1) in taken:
            continue  # A part of a path that the script knows. That finding says more.
        what, fix = host_kind(rule, project)
        found.append({"file": file, "line": number, "column": column, "what": what, "value": value, "fix": fix})
    order = {file: index for index, file in enumerate(files)}
    return sorted(found, key=lambda item: (order.get(item["file"], len(order)), item["line"], item["column"]))


def host_message(item: dict) -> str:
    """What one line holds. The scanner does not show each value."""
    return f"{item['what']}: `{item['value']}`" if item["value"] else f"{item['what']} at column {item['column']}"


# ---------- the project files that `check` compares a page with ----------

SOURCE_READ = 2_000_000  # characters of one source file that `check` reads


def norm(text: str) -> str:
    """One line with its blanks made equal: one blank between two words, and no blank at its ends."""
    return " ".join(text.split())


def lines_made_equal(text: str) -> str:
    """A text with the blanks of each line made equal. A line that ends with a backslash is one line with its next line."""
    return "\n".join(norm(line) for line in re.sub(r"\\\r?\n", " ", text).splitlines())


def project_repo(project: str) -> Path | None:
    """The project repository of the last survey. None when no path is recorded, or when Git cannot read it now."""
    recorded = WORK / project / "repo"
    if not recorded.is_file() or not recorded.read_text().strip():
        return None
    repo = Path(recorded.read_text().strip())
    readable = repo.is_dir() and subprocess.run(["git", "-C", str(repo), "rev-parse", "--git-dir"],
                                                capture_output=True).returncode == 0
    return repo if readable else None


def source_texts(repo: Path, record: dict) -> dict[str, str] | None:
    """The text of each source file of one page, as the state records it. None when Git cannot read one of them."""
    texts = {}
    for path, blob in (record.get("sources") or {}).items():
        done = subprocess.run(["git", "-C", str(repo), "cat-file", "blob", str(blob)], capture_output=True)
        if done.returncode != 0:
            return None
        texts[path] = done.stdout.decode("utf-8", errors="replace")[:SOURCE_READ]
    return texts


def states_path(text: str, path: str) -> bool:
    """True when a text holds a path as literal text: the complete path, or the path with `/` and more parts after it.

    A longer name is another path: `scripts/hook` is not in `scripts/hooks.sh`. A `./` before the path is the same path.
    """
    at = text.find(path)
    while at >= 0:
        before, after = text[:at].removesuffix("./")[-1:], text[at + len(path):at + len(path) + 2]
        if not re.match(r"[\w./-]", before) and not re.match(r"[\w-]|\.\w", after):
            return True
        at = text.find(path, at + 1)
    return False


def tree_holds(repo: Path, ref: str, line: str) -> bool | None:
    """True when one line of a file of the project at the ref holds this text, with the blanks made equal.

    Git searches the tree of the ref, so the size of the project sets no limit. None when Git cannot search.
    """
    pattern = "[[:space:]]+".join(re.sub(r"([\\^$.\[\]|()*+?{}])", r"\\\1", word) for word in line.split())
    done = subprocess.run(["git", "-C", str(repo), "grep", "-I", "-q", "-E", "-e", pattern, ref, "--"], capture_output=True)
    return {0: True, 1: False}.get(done.returncode)


def fact_commands(tree_facts: dict) -> set[str]:
    """Each command that the facts hold, and each command that the script builds from them for a frame."""
    found = {*commands_of(tree_facts), *tree_facts.get("tests", []), *(entry.get("run", "") for entry in tree_facts["entry_points"])}
    cli = main_cli(tree_facts)
    if cli:
        start = f"python3 {cli['path']}"
        found |= {start, f"{start} --help"}
        for action in cli.get("actions") or []:
            found |= {f"{start} {action}", f"{start} {action} --help"}
    return {norm(command_line) for command_line in found if command_line}


# ---------- the lines of a page ----------

def page_lines(text: str) -> list[dict]:
    """Each line of a page with its kind, and the slot that holds it.

    `text`     a line that the page shows as text.
    `code`     a line of a code block.
    `diagram`  a line of a `mermaid` code block.
    `command`  a line of the command of a command slot. The page does not show it at that place.
    `fence`    a line with ``` that starts or ends a code block.
    `comment`  a docgen comment line, and a line of the comment with the source files of the page.
    """
    owner = {}
    for slot in slots_of(text):
        for number in range(slot["line"] + 1, slot["line"] + 1 + len(slot["body"])):
            owner[number] = slot
    found, fenced, comment, language = [], False, "", ""
    for number, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        if comment and stripped.startswith("{/*"):
            comment = ""  # A comment that has no end line. The next docgen line ends it.
        if fenced and "{/* docgen:" in stripped:
            fenced = False  # A code block that has no closing line. The next docgen line ends it.
        if comment == "command":
            kind = "comment" if stripped == COMMAND_END else "fence" if stripped.startswith("```") else "command"
            comment = "" if stripped == COMMAND_END else comment
        elif comment:
            kind, comment = "comment", "" if "*/}" in stripped else comment
        elif stripped.startswith("```"):
            kind, fenced = "fence", not fenced
            language = stripped.strip("`").split()[0] if fenced and stripped.strip("`").split() else ""
        elif fenced:
            # A diagram is a drawing, not a command that a reader runs. The rules for a command do not read it.
            kind = "diagram" if language == "mermaid" else "code"
        elif stripped == COMMAND_OPEN:
            kind, comment = "comment", "command"
        elif stripped.startswith("{/*"):
            kind, comment = "comment", "" if "*/}" in stripped else "other"
        else:
            kind = "text"
        found.append({"number": number, "line": line, "kind": kind, "slot": owner.get(number)})
    return found


def code_commands(items: list[dict]) -> list[tuple[int, str, dict | None]]:
    """Each command line of the code blocks of a page: the number of its first line, its text and its slot.

    The text has its blanks made equal. A line that ends with a backslash is one command line with its next line.
    A `$ ` prompt is no part of a command.
    """
    found, parts, first, slot = [], [], 0, None
    for item in [*items, {"kind": "end", "line": "", "number": 0, "slot": None}]:
        line = item["line"].strip()
        if item["kind"] == "code" and line:
            if not parts:
                first, slot, line = item["number"], item["slot"], re.sub(r"^\$ ", "", line)
            parts.append(line.removesuffix("\\"))
            if line.endswith("\\"):
                continue
        if parts:
            found.append((first, norm(" ".join(parts)), slot))
            parts = []
    return found


# ---------- the docgen lines of a page ----------

DIAGRAM_END = "{/* docgen:end-diagram */}"
FRAME = re.compile(r"\s*<(?:Capture|Cast)\s[^>]*\bid=(?P<quote>[\"'])(?P<id>[^\"']+)(?P=quote)")
# A complete tag of a frame alone on its line, also one that `FRAME` does not read.
FRAME_ALONE = re.compile(r"\s*<(?:Capture|Cast)\b[^<>]*>\s*$")


def docgen_lines(text: str) -> list[dict]:
    """Each line of a page, or of a rendered template, that the script wrote and that an action reads.

    These are the first line and the end line of each slot, the two lines of a command slot, each capture mark
    with its `Capture` line, each marker of a part, and each diagram comment.
    The key of a line holds what must be equal on the page and in the template. The instruction text of a slot,
    the order and the title of a capture and the status of a diagram are no part of the key.
    A person can change `Capture` to `Cast`: both give the same key.
    """
    found, slot, command = [], None, False
    for number, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        opened, mark, diagram, frame = SLOT_OPEN.search(line), CAPTURE_MARK.search(line), DIAGRAM.search(line), FRAME.match(line)
        part, part_end = PART_OPEN.match(line), PART_END.match(line)
        key, what, owner = None, "", slot["id"] if slot else None
        if opened:
            slot, command = opened.groupdict(), False
            owner = slot["id"]
            key, what = ("slot", owner, slot["min"], slot["max"], slot["form"] or "text"), f"the first line of the slot '{owner}'"
        elif SLOT_END in line:
            key, what = ("end",), f"the line `{SLOT_END}`" + (f" of the slot '{owner}'" if owner else "")
            slot, command = None, False
        elif slot and stripped == COMMAND_OPEN:
            key, what, command = ("command-open",), f"the line `{COMMAND_OPEN}` of the slot '{owner}'", True
        elif slot and command and stripped == COMMAND_END:
            key, what, command = ("command-end",), f"the line `{COMMAND_END}` of the slot '{owner}'", False
        elif mark:
            source = f"slot {mark.group('value')}" if mark.group("kind") == "slot" else mark.group("kind")
            key, what = ("capture", mark.group("name"), source), f"the capture mark '{mark.group('name')}'"
        elif frame:
            key, what = ("frame", frame.group("id")), f"the `Capture` line of the capture '{frame.group('id')}'"
        elif part:
            key, what = (part.group("kind"), part.group("slot")), f"the marker `docgen:{part.group('kind')} {part.group('slot')}`"
        elif part_end:
            key, what = (f"end-{part_end.group('kind')}",), f"the marker `docgen:end-{part_end.group('kind')}`"
        elif diagram:
            key, what = ("diagram", diagram.group("id")), f"the comment of the diagram '{diagram.group('id')}'"
        elif stripped == DIAGRAM_END:
            key, what = ("end-diagram",), f"the line `{DIAGRAM_END}`"
        if key:
            found.append({"key": key, "kind": key[0], "what": what, "number": number, "line": line, "slot": owner})
    return found


def rendered_template(state: dict, path: str, record: dict, facts: dict | None) -> str | None:
    """The template of one page with the facts of this checkout. None when the template or the facts are absent.

    The state gives what the plan gave at the first `scaffold`: the pages of the doc set and the values of the page.
    """
    file = PROFILES / str(state.get("profile") or "v1") / f"{record.get('template')}.mdx"
    if facts is None or not file.is_file():
        return None
    plan = {"pages": [{"path": other, "vars": entry.get("vars"), "nav": None} for other, entry in state["pages"].items()]}
    try:
        page = {"path": path, "tree": record["tree"], "ref": record["ref"], "sources": record.get("sources") or {},
                "vars": record.get("vars")}
        return render(file.read_text(), facts, plan, page)
    except (KeyError, TypeError):
        return None  # The state or the facts do not have the form that this template reads.


def template_slots(state: dict, record: dict) -> dict[str, dict]:
    """Each slot of the template of one page: its word range, its form and its end line. It needs no facts."""
    file = PROFILES / str(state.get("profile") or "v1") / f"{record.get('template')}.mdx"
    return {slot["id"]: slot for slot in slots_of(file.read_text())} if file.is_file() else {}


def absent_part_lines(rendered: str, text: str) -> set[int]:
    """The line numbers of a rendered template that are inside a marked part that the page does not have.

    A marked part gives its lines only while the page has that part. `stale-part` reports a part that does not
    agree with its slot, and `scaffold` corrects it. A part of the page with no end line has the part when it
    holds a line of the part of the template: the lines after it can be lines of the page below the part.
    """
    slots = {slot["id"]: slot for slot in slots_of(text)}
    on_page: dict[tuple, list[dict]] = {}
    for part in parts_of(text):
        on_page.setdefault((part["kind"], part["slot"]), []).append(part)
    seen: dict[tuple, int] = {}
    absent = set()
    for part in parts_of(rendered):
        key = (part["kind"], part["slot"])
        index = seen.get(key, 0)
        seen[key] = index + 1
        if part["end"] is None:
            continue  # A template whose part has no end line gives each of its lines.
        if index < len(on_page.get(key, [])):
            found = on_page[key][index]
            given = {line.strip() for line in part["body"] if line.strip()}
            has = any(line.strip() and (found["end"] is not None or line.strip() in given) for line in found["body"])
        else:
            has = (part["kind"] == "with") != states_no_answer(slots.get(part["slot"]))
        if not has:
            absent.update(range(part["start"] + 2, part["end"] + 1))
    return absent


def template_docgen_lines(rendered: str, text: str) -> list[dict]:
    """The docgen lines that the template gives for one page, with no line of a part that the page does not have."""
    absent = absent_part_lines(rendered, text)
    return [item for item in docgen_lines(rendered) if item["number"] not in absent]


def exact_line(line: str) -> str:
    """One line as a fix text gives it: the line, and the number of blanks before it when it has some."""
    return line.strip() + (f" Put {blank_count(blanks_before(line))} before it." if blanks_before(line) else "")


def docgen_line_faults(rendered: str, text: str) -> list[tuple[int, str, str]]:
    """Each docgen line that the template gives and that the page does not have at its place: the line, the message, the fix."""
    expected, actual = template_docgen_lines(rendered, text), docgen_lines(text)
    template, page = rendered.splitlines(), text.splitlines()
    not_on_page = absent_part_lines(rendered, text)
    slots = {slot["id"]: slot for slot in slots_of(text)}
    matcher = difflib.SequenceMatcher(None, [item["key"] for item in expected], [item["key"] for item in actual], autojunk=False)
    same: dict[int, int] = {}
    lost: list[tuple[int, list[int]]] = []  # an expected line with no equal line, and the page lines of its block
    spare: list[int] = []
    for tag, e1, e2, a1, a2 in matcher.get_opcodes():
        if tag == "equal":
            same.update({e1 + offset: a1 + offset for offset in range(e2 - e1)})
        else:
            lost += [(index, list(range(a1, a2))) for index in range(e1, e2)]
            spare += range(a1, a2)

    def place(index: int) -> tuple[int, str]:
        """Where an absent line goes: the line that it follows in the template, with the number of that line on the page."""
        held = max((other for other in range(index) if other in same), default=None)
        low = actual[same[held]]["number"] if held is not None else 0
        at, gap = expected[index]["number"] - 2, False
        # A line of a part that the page does not have is no place on the page.
        while at >= 0 and (not template[at].strip() or at + 1 in not_on_page):
            at, gap = at - 1, gap or at + 1 not in not_on_page
        if at < 0:
            return 1, " as the first line of the page"
        before = template[at]
        slot_text = TODO.search(before)
        if slot_text:
            return low, f" directly below the last line of the text of the slot '{slot_text.group(1)}'"
        earlier = next((other for other in range(index - 1, -1, -1) if expected[other]["number"] == at + 1), None)
        if earlier is not None:
            number = actual[same[earlier]]["number"] if earlier in same else place(earlier)[0]
        else:
            number = next((n for n in range(low + 1, len(page) + 1) if page[n - 1].strip() == before.strip()), 0)
        if earlier is None and not number and held is not None:
            # The page does not have that line of the template: the template gave it only after the script wrote
            # the page. The place is the nearest docgen line before it that the page has.
            return low, f" below line {low} of the page ({page[low - 1].strip()[:70]}), with one empty line between them"
        where = f"line {number} of the page" if number and (earlier is None or earlier in same) else "the line"
        between = "with one empty line between them" if gap else "with no line between them"
        return number or low, f" below {where} ({before.strip()[:70]}), {between}"

    known = {item["number"] for item in actual}
    taken: set[int] = set()

    def damaged(index: int) -> int:
        """The page line that is the absent line with a change that the script does not read. 0 when the page has none.

        Such a line starts as a docgen comment, holds the name of the slot, of the capture or of the diagram, and
        is between the docgen lines around the place of the absent line.
        For a `Capture` line, it is the line directly below its capture mark that holds one tag of a frame and no
        other text, for example with no quotes around the `id`.
        """
        item = expected[index]
        if item["kind"] == "frame":
            mark = index - 1 if index and expected[index - 1]["kind"] == "capture" else None
            number = actual[same[mark]]["number"] + 1 if mark in same else 0
            if number and number <= len(page) and number not in known | taken and FRAME_ALONE.match(page[number - 1]):
                taken.add(number)
                return number
            return 0
        if item["kind"] not in ("slot", "capture", "diagram"):
            return 0
        low = max((actual[same[other]]["number"] for other in range(index) if other in same), default=0)
        high = min((actual[same[other]]["number"] for other in range(index + 1, len(expected)) if other in same),
                   default=len(page) + 1)
        name = re.compile(rf"(?<![\w-]){re.escape(item['key'][1])}(?![\w-])")
        for number in range(low + 1, high):
            line = page[number - 1].strip()
            if number not in known and number not in taken and line.startswith("{/* docgen") \
                    and not line.startswith("{/* docgen: sources of this page") and name.search(line):
                taken.add(number)
                return number
        return 0

    faults = []
    for index, block in lost:
        item = expected[index]
        if item["kind"] in ("command-open", "command-end") and (slots.get(item["slot"]) or {}).get("form") == "command":
            continue  # The form check of the command slot reports its two lines.
        # A line with the same name and another content: the agent changed it.
        changed = next((a for a in spare if actual[a]["kind"] == item["kind"] and item["kind"] in ("slot", "capture", "diagram")
                        and actual[a]["key"][1] == item["key"][1]), None)
        if changed is None:
            changed = next((a for a in block if a in spare and actual[a]["kind"] == item["kind"]
                            and item["kind"] in ("slot", "capture", "frame", "diagram", "with", "without")), None)
        moved = next((a for a in spare if actual[a]["key"] == item["key"]), None)
        number, where = place(index)
        if moved is not None:
            spare.remove(moved)
            faults.append((index, actual[moved]["number"], f"{item['what']} is at a wrong place.", f"move this line. Put it{where}."))
        elif changed is not None:
            spare.remove(changed)
            faults.append((index, actual[changed]["number"], f"this line is not {item['what']} as the script wrote it.",
                           f"write this exact line in its place: {exact_line(item['line'])}"))
        elif (broken := damaged(index)):
            faults.append((index, broken, f"this line is not {item['what']} as the script wrote it.",
                           f"write this exact line in its place: {exact_line(item['line'])}"))
        else:
            faults.append((index, number or 1, f"the page does not have {item['what']}.",
                           f"put this exact line back{where}: {exact_line(item['line'])}"))
    for index, other in sorted(same.items()):
        wanted, found = expected[index], actual[other]
        if blanks_before(wanted["line"]) == blanks_before(found["line"]):
            continue
        if wanted["kind"] == "end" and (slots.get(found["slot"]) or {}).get("form") == "steps":
            continue  # The form check of the steps slot reports this line.
        faults.append((index, found["number"], f"{wanted['what']} has {blank_count(blanks_before(found['line']))} before it, and "
                       f"the script wrote it with {blank_count(blanks_before(wanted['line']))}.",
                       f"write the line with exactly {blank_count(blanks_before(wanted['line']))} before it."))
    # In the order of the template: the agent puts an earlier line back first, and a later line names it.
    return [fault[1:] for fault in sorted(faults)]


def structure_faults(text: str, ends: dict[str, str]) -> list[tuple[int, str, str]]:
    """The faults of the docgen lines that need no template: a slot with no end line, an end line with no slot,
    and a `TODO` text that is in no slot. `check` uses this while the checkout has no facts."""
    faults, slot = [], None
    later = "run `survey` in the project repository, then run `check` again. It then prints the exact line to put back."

    def no_end() -> None:
        end = ends.get(slot["id"])
        fix = (f"put this exact line back directly below the last line of the text of the slot: {exact_line(end)}"
               if end else later)
        faults.append((slot["line"], f"the slot '{slot['id']}' has no line `{SLOT_END}` below its text.", fix))

    for number, line in enumerate(text.splitlines(), 1):
        opened = SLOT_OPEN.search(line)
        if opened:
            if slot:
                no_end()
            slot = {**opened.groupdict(), "line": number}
        elif SLOT_END in line:
            if not slot:
                faults.append((number, f"this line `{SLOT_END}` ends no slot: the first line of its slot is absent.", later))
            slot = None
        elif TODO.search(line) and not slot:
            faults.append((number, f"the text `{TODO.search(line).group(0)}` is in no slot: the first line of the slot "
                           f"'{TODO.search(line).group(1)}' is absent, and the page shows this text.", later))
    if slot:
        no_end()
    return faults


def diagram_faults(text: str) -> list[tuple[int, str]]:
    """Each diagram comment that says `done` while no diagram is below it."""
    lines, faults = text.splitlines(), []
    for number, line in enumerate(lines, 1):
        marker = DIAGRAM.search(line)
        if marker and marker.group("state") == "done":
            below = []
            for later in lines[number:]:
                if later.strip() == DIAGRAM_END or "{/* docgen:" in later:
                    break
                below.append(later.strip())
            if not any(entry.startswith("```mermaid") for entry in below):
                faults.append((number, marker.group("id")))
    return faults


# ---------- check ----------

# Each rule of `check` that gives a note and no finding, with the last sentence of its line in the summary.
NOTE_RULES = {
    "unverified-command": "The reviewer reads those commands first.",
    "unused-fact": "The reviewer decides if a test command of the facts tests the install.",
}
PATH_SPLIT = re.compile(r"[\s\"'`=()\[\]{};|&<>,]+")
# `unknown-path` read a code block only below these directories. It reads them still, also in a project with no such directory.
PATH_DIRS = ("scripts", "docs", "config", "src", "tests")


def path_words(text: str, top: set[str], alone: bool) -> list[str]:
    """The words of one code line, or of one inline code text, that are a path of the project by their form.

    A word is such a path when its first part is a directory at the top of the project. In a code line and in a
    command, a word below one of the directories of `PATH_DIRS` counts too. An inline code text of one word
    (`alone`) counts too when its last part has a point, as a file name has.
    """
    found = []
    for word in PATH_SPLIT.split(text):
        if "://" in word or "@" in word:
            continue  # A URL or an address of a remote, not a path of the project.
        for part in word.split(":"):
            part = part.rstrip(".,;").removeprefix("./")
            if "/" not in part or part.startswith(("/", "-", "http")) or not re.fullmatch(r"[\w./-]+", part):
                continue
            first = part.split("/", 1)[0]
            named = alone and not part.startswith(".") and "." in part.rsplit("/", 1)[-1]
            if first + "/" in top or (not alone and first in PATH_DIRS) or named:
                found.append(part)
    return list(dict.fromkeys(found))


def cmd_check(args: argparse.Namespace) -> None:
    project = args.project
    state = project_state(project)
    facts_path = WORK / project / "facts.json"
    facts = facts_of(project, needed=False)
    repo = project_repo(project) if facts else None
    findings, notes, unread = [], [], []
    run_next, run_scaffold = (command(action, "--project", project) for action in ("next", "scaffold"))
    help_dir = WORK / project / "help"
    help_texts = [lines_made_equal(file.read_text(errors="replace")) for file in sorted(help_dir.glob("*.txt"))] if help_dir.is_dir() else []

    def finding(page: Path, line: int, rule: str, message: str, fix: str) -> None:
        # The agent works in the project repository. So a finding names the absolute path of the file to open.
        findings.append(f"{page}:{line}: {rule}: {message} Fix: {fix}")

    def note(page: Path, line: int, rule: str, message: str) -> None:
        # A note never changes the exit code. The summary counts the notes of each rule.
        notes.append((rule, f"{page}:{line}: note: {rule}: {message} This is no finding. Put this line into your report."))

    pages = {}
    for path, record in sorted(state["pages"].items()):
        page = DOCS / project / path
        if not page.exists():
            finding(page, 1, "missing-page", "the state lists this page, and the file is absent.", f"run `{run_scaffold}`.")
            continue
        pages[path] = (page, record, page.read_text())

    # A value of one host: in each page, in the state file and in each capture spec, also while Git does not track them.
    doc_set = [SITE / file for file in doc_set_files(project, state)[:-2] if (SITE / file).is_file()]
    page_files = {page for page, _, _ in pages.values()}
    for item in host_values(project, doc_set):
        if item["file"] in page_files:
            fix = item["fix"]
        elif item["file"].parent == STATE:
            fix = "do not edit this file. The script writes it. Stop and tell the user this line."
        else:
            fix = (f"do not edit this file. Correct the command slot of the page that holds the value. Then run `{run_scaffold}`: "
                   "it writes the command into this file again. If the finding stays, stop and tell the user this line.")
        finding(item["file"], item["line"], "host-value", f"the line holds {host_message(item)}.", fix)

    for path, (page, record, text) in pages.items():
        items = page_lines(text)
        page_slots = slots_of(text)
        slots = {slot["id"]: slot for slot in page_slots}
        models = template_slots(state, record)
        rendered = rendered_template(state, path, record, facts)

        # The two lines of the frontmatter that the script wrote.
        front = text.split("\n---", 1)[0].splitlines() if text.startswith("---") else []
        for name in ("title", "description"):
            if re.search(rf"^{name}: \S", text, re.M):
                continue
            wrote = re.search(rf"^{name}: \S.*$", rendered or "", re.M)
            # A line `title:` with no text is on the page. A second line with that key stops the build.
            empty = next((number for number, line in enumerate(front, 1) if re.fullmatch(rf"{name}:\s*", line)), 0)
            where = "as line 2, directly below the first line `---`" if name == "title" else "directly below the line `title:`"
            if empty:
                fix = (f"write this exact line in place of line {empty}: {wrote.group(0)}" if wrote
                       else f"write one short text after `{name}:` in line {empty}.")
            else:
                fix = (f"put this exact line back {where}: {wrote.group(0)}" if wrote
                       else f"write the line `{name}:` with one short text {where}.")
            finding(page, empty or 1, "frontmatter", f"the frontmatter has no line `{name}:` with a text.", fix)

        # The lines that the script wrote and that each action reads.
        if rendered is not None:
            for number, message, fix in docgen_line_faults(rendered, text):
                finding(page, number, "docgen-line", message, fix)
        else:
            for number, message, fix in structure_faults(text, {name: model["end"] for name, model in models.items()}):
                finding(page, number, "docgen-line", message, fix)
        for number, name in diagram_faults(text):
            finding(page, number, "docgen-line", f"the comment of the diagram '{name}' says `done`, and no `mermaid` code block "
                    f"is between this line and the line `{DIAGRAM_END}`.",
                    "change the word `done` in this line back to `pending`. A larger model draws the diagram.")

        for slot in page_slots:
            if slot["open"]:
                finding(page, slot["line"], "open-slot", f"the slot '{slot['id']}' has no text.",
                        f"run `{run_next}` and write the slot.")
                continue
            model = models.get(slot["id"])
            if rendered is not None and first_line_changed(slot, model):
                continue  # `docgen-line` reports the first line of this slot, with the exact line to write.
            for problem in slot_problems(slot, model):
                finding(page, slot["line"], "slot-form", f"the slot '{slot['id']}' has a fault of its form: {problem}",
                        f"correct the slot. `{run_next}` prints the rules of the form.")
            if not first_line_changed(slot, model) and not int(slot["min"]) <= slot["words"] <= int(slot["max"]):
                finding(page, slot["line"], "slot-length", f"the slot '{slot['id']}' has {slot['words']} words.",
                        f"write {slot['min']} to {slot['max']} words.")

        tree_facts = facts["trees"][record["tree"]] if facts else None
        # The one slot where the facts of the survey can have the answer that the slot says is absent. The script does
        # not know what a test command of the facts tests: the unit tests of a project are no test of its install.
        # So this is a note, and the sentence of the slot passes.
        tested = slots.get("stage-4-command")
        if tree_facts and tree_facts.get("tests") and states_no_answer(tested):
            tests = ", ".join(f"`{test}`" for test in tree_facts["tests"])
            one = len(tree_facts["tests"]) == 1
            note(page, tested["line"], "unused-fact", f"the slot 'stage-4-command' says that the sources state no test of the "
                 f"install, and the facts of the survey hold {'this test command' if one else 'these test commands'}: {tests}. "
                 f"If a source file of this page says that {'this command' if one else 'one of these commands'} tests the "
                 f"install, write {'the' if one else 'that'} command into the slot in place of the sentence. Then correct the "
                 f"slot 'stage-4-result', and run `{run_scaffold}`. If no source file says so, the sentence is correct, and "
                 "you change nothing.")

        # A path of the project, and a command that no source states. Both rules read the project through Git.
        sources = source_texts(repo, record) if repo and tree_facts else None
        if tree_facts and repo and sources is None:
            unread.append(path)
        if sources is not None:
            files = tree_facts["files"]
            folders = {name[:at] for name in files for at in range(len(name)) if name[at] == "/"}
            top = set(tree_facts.get("top_level") or [])
            for item in items:
                if item["kind"] == "text":
                    words = [word for span in re.findall(r"`([^`]+)`", item["line"])
                             for word in path_words(span, top, alone=not re.search(r"\s", span.strip()))]
                elif item["kind"] in ("code", "command"):
                    words = path_words(item["line"], top, alone=False)
                elif item["kind"] == "diagram":
                    # A label of a diagram is text for a reader. Only a word with the form of a file name is a path.
                    words = [word for word in path_words(item["line"], top, alone=False)
                             if "." in word.rstrip("/").rsplit("/", 1)[-1]]
                else:
                    continue
                for word in dict.fromkeys(words):
                    name = word.rstrip("/")
                    if name in files or name in folders or any(states_path(source, name) for source in sources.values()):
                        continue
                    finding(page, item["number"], "unknown-path", f"`{word}` is not a file of the project at {record['ref']}, "
                            "and no source file of this page holds this path.",
                            "write the path of a file of the project, or a path that a source file of this page states. "
                            "The top of the page lists its source files. If no file states the path, remove the sentence or "
                            "the command that holds it.")

            known = fact_commands(tree_facts)
            stated = [lines_made_equal(source) for source in sources.values()] + help_texts
            lines = [(number, line) for number, line, slot in code_commands(items) if slot]
            for slot in page_slots:
                # A command slot with a fault of its form has its finding. A note for the same line says no more.
                if (slot.get("form") or "text") == "command" and not slot_problems(slot, models.get(slot["id"])):
                    first = next((item["number"] for item in items if item["kind"] == "command" and item["slot"]
                                  and item["slot"]["line"] == slot["line"]), slot["line"])
                    lines.append((first, norm(slot_command(slot)[0].replace("\\\n", " "))))
            for number, line in sorted(lines):
                if len(line) < 4 or line.startswith("#"):
                    continue
                if any(line in entry for entry in known) or any(line in entry for entry in stated):
                    continue
                held = tree_holds(repo, record["ref"], line)
                if held is None:
                    unread.append(path)
                    break
                if not held:
                    note(page, number, "unverified-command", f"no file of the project at {record['ref']}, no saved help text "
                         f"and no command of the facts holds this command line: `{line}`.")

        for part, wanted in part_faults(text):
            slot_state = "states no command" if wanted == (part["kind"] == "without") else "does not state \"no command\""
            what = "the step with the frame" if part["kind"] == "with" else "the sentence for \"no command\""
            message = (f"the slot '{part['slot']}' {slot_state}, and the page "
                       f"{'does not have' if wanted else 'still has'} {what}.")
            finding(page, part["start"] + 1, "stale-part", message,
                    f"run `{run_scaffold}`. It changes this part of the page.")

        # The frame of a capture is the one place of its command. A code block with the same command is a second place.
        # The blanks, a `$ ` prompt and a backslash at the end of a line make no other command.
        shown: dict[str, int] = {}
        for number, line, _ in code_commands(items):
            shown.setdefault(line, number)
        twice: dict[int, list[dict]] = {}
        # The capture marks that the template gives. `docgen-line` reports each other mark of the page.
        given = {item["key"] for item in template_docgen_lines(rendered, text)} if rendered is not None else None
        for found in CAPTURE_MARK.finditer(text):
            mark = found.groupdict()
            spec, _ = capture_spec(project, mark, slots)
            whole = norm(spec["command"].replace("\\\n", " ")) if spec else ""
            if whole and whole in shown:
                twice.setdefault(shown[whole], []).append(mark)
            # The frame shows the command of the spec file. `scaffold` copies the command of the slot into that file.
            slot = slots.get(mark["value"] or "") if mark["kind"] == "slot" else None
            file = CAPTURES / project / f"{mark['name']}.json"
            listed = mark["name"] in state.get("captures", {})
            source = f"slot {mark['value']}" if mark["kind"] == "slot" else mark["kind"]
            if spec is not None and not listed and not file.exists() and (given is None or ("capture", mark["name"], source) in given):
                # The page got this mark after the last `scaffold`. A commit of this state has a frame with no spec.
                finding(page, text[:found.start()].count("\n") + 1, "stale-spec", f"the capture '{mark['name']}' has no "
                        f"capture spec: the file {file} is absent, so its frame shows nothing.",
                        f"run `{run_scaffold}`. It writes the spec.")
                continue
            if spec is None or slot is None or slot["open"] or states_no_answer(slot) or not listed \
                    or slot_problems(slot, models.get(slot["id"])):
                continue  # Another rule reports the slot or the capture mark, or docgen did not write the spec.
            try:
                recorded = json.loads(file.read_text()).get("command") if file.exists() else None
            except (json.JSONDecodeError, AttributeError):
                continue  # No valid spec. `scaffold` cannot read it, so its run is no fix. A check of the site reports the file.
            if recorded != spec["command"]:
                number = text[:found.start()].count("\n") + 1
                finding(page, number, "stale-spec", f"the capture spec {file} "
                        + ("is absent" if not file.exists() else f"does not hold the command of the slot '{slot['id']}'")
                        + ", so the frame does not show that command.",
                        f"run `{run_scaffold}`. It copies the command of the slot into the spec.")
        for number, marks in sorted(twice.items()):
            names = " and ".join(f"'{mark['name']}'" for mark in marks)
            message = (f"this code block and the frame of the capture {names} show the same command."
                       if len(marks) == 1 else f"this code block and the frames of the captures {names} show the same command.")
            written = next((slot for slot in page_slots if slot["line"] < number <= slot["line"] + len(slot["body"])), None)
            from_slots = [mark["value"] for mark in marks if mark["kind"] == "slot"]
            if written:
                # The agent wrote the code block. The frame stays, and the step goes.
                fix = f"remove the step with this code block from the slot '{written['id']}'. The frame shows the command."
                if fallback_of(written):
                    fix += f" If the slot has no step then, write: {fallback_of(written)}"
            elif from_slots:
                # The script wrote the code block. The command of the command slot is the second place.
                fix = (f"do not change this code block. The script wrote it. Write in the slot '{from_slots[0]}' "
                       "a command that this page does not show in a code block.")
                if fallback_of(slots[from_slots[0]]):
                    fix += f" If the sources state no other command, write: {fallback_of(slots[from_slots[0]])}"
            else:
                fix = "do not change the page. The script wrote both places. Stop and tell the user this line."
            finding(page, number, "command-twice", message, fix)

    for line in findings:
        print(line)
    for _, line in notes:
        print(line)
    pending = pending_diagrams(project, state)
    for page, number, found in pending:
        print(f"{page}:{number}: note: the diagram '{found['id']}' is not drawn yet. A larger model draws it.")
    print(f"{len(findings)} finding(s) in {len(state['pages'])} page(s) of {project}")
    for rule, reader in NOTE_RULES.items():
        count = sum(1 for name, _ in notes if name == rule)
        if count:
            print(f"{count} note(s) with `{rule}`: a note is no finding. Put each of these lines into your report. {reader}")
    if pending:
        print(f"{len(pending)} diagram(s) wait for the second pass: {command('diagrams', '--project', project)}")
    # A rule that did not run is no finding, and it is no pass of that rule. The line says so.
    again = "`survey` in the project repository writes the facts and records the repository."
    if facts is None:
        print(f"note     the rules `unknown-path`, `unverified-command` and `unused-fact` did not run, and `docgen-line` did not "
              f"compare the pages with their templates: this checkout has no facts of '{project}' ({facts_path} is absent). "
              f"The other rules ran. This is no finding. {again}")
    elif repo is None:
        print("note     the rules `unknown-path` and `unverified-command` did not run: Git cannot read the project repository "
              f"of the last survey. The other rules ran. This is no finding. {again}")
    elif unread:
        print(f"note     the rules `unknown-path` and `unverified-command` did not run for {len(set(unread))} page(s) "
              f"({', '.join(sorted(set(unread)))}): Git cannot read a source file of the page or its ref in the project "
              f"repository. The other rules ran. This is no finding. {again}")
    sys.exit(site_checks(project, len(findings)))


# ---------- diagrams ----------

def pending_diagrams(project: str, state: dict) -> list[tuple[Path, int, dict]]:
    found = []
    for path in sorted(state["pages"]):
        page = DOCS / project / path
        if page.exists():
            for number, line in enumerate(page.read_text().splitlines(), 1):
                marker = DIAGRAM.search(line)
                if marker and marker.group("state") == "pending":
                    found.append((page, number, marker.groupdict()))
    return found


def cmd_diagrams(args: argparse.Namespace) -> None:
    project_name(args.project)
    pending = pending_diagrams(args.project, project_state(args.project, doc_set_exists=True))
    for page, number, found in pending:
        print(f"page      {page}")
        print(f"diagram   {found['id']} (line {number})")
        print(f"draw      {found['text']}")
        print("then      put one fenced mermaid block between this comment line and the `docgen:end-diagram` line,")
        print("          and change the word `pending` in the comment line to `done`.")
        print()
    print(f"{len(pending)} diagram(s) to draw")
    if pending:
        print(f"check     {command('check', '--project', args.project)}")
        print(f"commit    {command('commit', '--project', args.project, '--diagrams')}")


# ---------- status ----------

def capture_again(project: str, release: str) -> str:
    """The sentence for the user after a new release. No agent runs the capture script: it needs the source and Docker."""
    return (f"the capture script must run for the new release {release}: `scripts/capture.py --project {project}` "
            "records the output of each command again. Put this line into your report.")


def cmd_status(args: argparse.Namespace) -> None:
    project = args.project
    project_name(project)
    state = project_state(project, doc_set_exists=True)
    if args.repo:
        start = Path(args.repo)
    else:
        recorded = WORK / project / "repo"
        if not recorded.is_file() or not recorded.read_text().strip():
            fail(f"the project repository of '{project}' (run survey first) is not known: no survey ran in this checkout of "
                 f"the site. {SURVEY_AGAIN} The option `--repo` gives the path of the project repository.")
        start = Path(recorded.read_text().strip())
    repo = top_of(start)

    # Each stop comes before the first line of the list.
    for ref in sorted({record["ref"] for record in state["pages"].values()}):
        if not ref_exists(repo, ref):
            fail(f"the project repository {repo} has no branch {ref}, and pages of '{project}' describe that branch. "
                 f"Do not make the branch. {TELL_USER}")
    release_ref, described = state.get("release_ref"), state.get("release")
    newest = release_tags(repo, release_ref) if release_ref else []
    if described and described not in newest and release_tag.release_key(described, release_ref) is not None:
        # The pages are newer than this repository. A model that goes on moves the pages back to an older release.
        has = f"Its newest release tag is {newest[0]}" if newest else f"It has no release tag of the branch {release_ref}"
        fail(f"the project repository {repo} does not have the release tag {described} that the pages of '{project}' "
             f"describe. {has}. The repository is older than the pages, or it does not have each tag. "
             f"Do not change the project repository. {TELL_USER}")

    stale = 0
    if newest and newest[0] != described:
        stale += 1
        print(f"release  the pages describe {described}, the newest release is {newest[0]}")
        print("           Set the new release: "
              + command("register", "--project", project, "--release", newest[0], "--branch", release_ref))
        print(f"           For the user: {capture_again(project, newest[0])}")
    trees: dict[str, dict[str, str]] = {}
    for path, record in sorted(state["pages"].items()):
        ref = record["ref"]
        if ref not in trees:
            trees[ref] = tree(repo, ref)
        files = trees[ref]
        page = DOCS / project / path
        changed = [source for source, blob in record["sources"].items() if files.get(source) != blob]
        waiting = sum(1 for slot in slots_of(page.read_text()) if slot["open"]) if page.exists() else 0
        if not changed and not waiting:
            print(f"current  {path}")
            continue
        stale += 1
        print(f"{'stale' if changed else 'open':<8} {path}")
        print(f"           The page is the file {page}")
        if waiting:
            print(f"           The page has {waiting} open slot(s). Write each open slot first: "
                  + command("next", "--project", project))
        if not changed:
            continue
        generated = record.get("generated")
        if generated:
            print("           The script writes this page. Do not edit it.")
        for source in changed:
            blob = record["sources"][source]
            if source not in files:
                # The same text at one other path: the file has a new name.
                moved = [other for other, held in files.items() if held == blob and other not in record["sources"]]
                if len(moved) == 1:
                    print(f"           {source} was renamed to {moved[0]}. The text of the file is the same.")
                else:
                    print(f"           {source} was removed")
            elif generated:
                print(f"           {source} changed")
            elif subprocess.run(["git", "-C", str(repo), "cat-file", "-e", blob], capture_output=True).returncode != 0:
                # A clone with a part of the history does not hold the old text.
                print(f"           {source} changed. The project repository does not hold the old text of this file. "
                      "Read the file as it is now:")
                print(f"             git -C {shlex.quote(str(repo))} show {shlex.quote(ref + ':' + source)}")
            else:
                # Two blobs: the output has the lines that changed, and no line about the mode of the file.
                print(f"           {source} changed. Read the change:")
                print(f"             git -C {shlex.quote(str(repo))} diff {blob} {files[source]}")
        again = command("scaffold", "--project", project, "--refresh", path)
        print(f"           {'Write the page again' if generated else 'After you correct the page'}: {again}")
    after = commits_after(repo, newest[0], release_ref) if newest else 0
    if after:
        print(f"note     {after_release(after, release_ref, newest[0])}")
    print(f"{stale} stale item(s)")
    if not stale:
        # The loop of an update ends here. The work ends only when no file of the doc set waits for a commit.
        if site_checkout() and doc_set_changes(project, state):
            print("next     " + command("register", "--project", project))
        else:
            print(f"The pages of {project} are current, and no file of the doc set waits for a commit. Nothing to do.")
    sys.exit(1 if stale else 0)


# ---------- register ----------

PROJECTS = SITE / "src" / "data" / "projects.json"
VERSIONS = SITE / "src" / "data" / "versions.json"
TEXT_MAX = {"name": 60, "summary": 160}  # characters


def read_data(path: Path, what: str):
    """Read one data file of the site."""
    if not path.exists():
        fail(f"{what} is absent: {path.relative_to(SITE)}")
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError as error:
        fail(f"{path.relative_to(SITE)} is not valid JSON: {error}. The script cannot correct this file. {TELL_USER}")


def write_data(path: Path, data) -> bool:
    """Write one data file of the site in the format of the tracked files. Do not write a file that holds this data."""
    if json.loads(path.read_text()) == data:
        return False
    path.write_text(json.dumps(data, indent="\t", ensure_ascii=False) + "\n")
    return True


def page_description(page: Path) -> str:
    """The description in the frontmatter of a page, on one line, without its quotes."""
    block = re.match(r"---\n(.*?)\n---", page.read_text(), re.S)
    found = re.search(r"^description:[ \t]*(.*?)[ \t]*$", block.group(1), re.M) if block else None
    value = found.group(1) if found else ""
    if len(value) >= 2 and value[0] == value[-1] == '"':
        return value[1:-1].replace('\\"', '"')
    if len(value) >= 2 and value[0] == value[-1] == "'":
        return value[1:-1].replace("''", "'")
    return "" if value[:1] in (">", "|") else value


def registration(project: str, docs: str | None = None, name: str | None = None, summary: str | None = None,
                 release: str | None = None, branch: str | None = None) -> tuple[list, dict, list[str], dict | None]:
    """Find what `register` writes: the project list, the releases, one line for each change, and the state.

    The defaults come from the state of the last scaffold and from the overview page. Nothing is written here.
    The state is None when it does not change.
    """
    if not SLUG.fullmatch(project):
        fail(f"'{project}' is not a project name of the site. Use lowercase letters, digits and '-'.")
    overview = next((DOCS / project / page for page in ("index.mdx", "index.md") if (DOCS / project / page).exists()), None)
    if overview is None:
        fail(f"the project '{project}' has no overview page src/content/docs/{project}/index.mdx. "
             f"Run first: {command('scaffold', '--project', project)}")
    state = state_of(project) or {}
    projects = read_data(PROJECTS, "the project list")
    versions = read_data(VERSIONS, "the list of releases")
    if not isinstance(projects, list) or not isinstance(versions, dict):
        fail("src/data/projects.json must hold a list, and src/data/versions.json must hold an object.")
    entry = next((item for item in projects if item.get("slug") == project), None)
    changes = []

    if entry and entry.get("docs") == "full":
        if docs == "overview":
            fail(f"the project '{project}' has a full doc set. `register` does not change a full doc set to an overview.")
        docs = "full"
    docs = docs or state.get("doc_set") or (entry or {}).get("docs")
    if docs not in ("full", "overview"):
        fail(f"the size of the doc set of '{project}' is not known. The option `--docs` gives it, and `scaffold` records it. "
             f"Run first: {command('scaffold', '--project', project)}")

    if entry is None:
        entry = {"slug": project, "name": name or project, "summary": summary or page_description(overview), "docs": docs}
        projects.append(entry)
        changes.append(f"added    {project} to src/data/projects.json, doc set: {docs}")
    else:
        if entry.get("docs") != docs:
            changes.append(f"changed  {project} from {entry.get('docs')} to {docs} in src/data/projects.json")
            entry["docs"] = docs
        for key, value in (("name", name), ("summary", summary)):
            if value is not None and value != entry.get(key):
                changes.append(f"changed  the {key} of {project} in src/data/projects.json")
                entry[key] = value
    if not entry.get("summary"):
        fail(f"the project '{project}' has no summary: its overview page has no description on one line. "
             "Give --summary with one short sentence.")
    for key, limit in TEXT_MAX.items():
        text = entry.get(key)
        if not isinstance(text, str) or not text.strip() or "\n" in text or len(text) > limit:
            fail(f"the {key} of '{project}' must be one line of 1 to {limit} characters. Give --{key}.")

    known = versions.get(project) or {}
    release = release or state.get("release") or known.get("release")
    branch = branch or state.get("release_ref") or known.get("branch")
    notes, recorded = [], None
    if release and branch:
        wanted = {**known, "branch": branch, "release": release}
        if wanted != known:
            versions[project] = wanted
            changes.append(f"release  {project} is at {release} of the branch {branch} in src/data/versions.json")
            if known.get("release") and known["release"] != release:
                # The frames of the pages show the output of the release before.
                notes.append(f"note     {capture_again(project, release)}")
        if state and (state.get("release"), state.get("release_ref")) != (release, branch):
            # An option gives another release than the last `scaffold` recorded. The state follows, so that
            # `status`, `check` and `commit` read the same release.
            recorded = {**state, "release": release, "release_ref": branch}
            changes.append(f"recorded {project} is at {release} of the branch {branch} in docgen/state/{project}.json")
    elif docs == "full":
        fail(f"the release of '{project}' is not known. The options `--release` and `--branch` give it, and `scaffold` "
             f"records it. Run first: {command('scaffold', '--project', project)}")
    if docs == "full" and release_tag.release_key(release, branch) is None:
        # Each release gets a tag. A commit is not a release.
        fail(no_release_tag(release, branch))

    # The data files are tracked and the site is public.
    for what, value in (("name", entry["name"]), ("summary", entry["summary"]), ("release", release), ("branch", branch)):
        for rule, pattern in HOST_VALUES:
            if value and pattern.search(value):
                kind, fix = host_kind(rule, project)
                fail(f"the {what} of '{project}' holds {kind}. Give another text: {fix}")
    return projects, versions, changes + notes, recorded


def cmd_register(args: argparse.Namespace) -> None:
    project = args.project
    need_run_branch(project, "register")
    projects, versions, changes, recorded = registration(project, args.docs, args.name, args.summary, args.release,
                                                        args.branch)
    if changes:
        write_data(PROJECTS, projects)
        write_data(VERSIONS, versions)
        if recorded:
            (STATE / f"{project}.json").write_text(json.dumps(recorded, indent=1, sort_keys=True) + "\n")
    for line in changes:
        print(line)
    if not changes and (versions.get(project) or {}).get("release"):
        print(f"kept     {project} is in the project list and its release is current. No file changed.")
    elif not changes:
        print(f"kept     {project} is in the project list. The site has no release of {project}. No file changed.")
    elif any(line.startswith(("added", f"changed  {project} from")) for line in changes):
        print("note     the text and the diagram of the home page src/content/docs/index.mdx name each project. "
              "`register` does not change them. Do not change the home page. Put this line into your report.")
    if state_of(project) is None:
        # A person wrote the pages, or `register` ran before `scaffold`. `check` reads the state, so it is no next step.
        print(f"note     this checkout has no state of '{project}' (docgen/state/{project}.json is absent), so `check` cannot "
              f"run for it. In a run of docgen, `scaffold` comes before `register`: {command('scaffold', '--project', project)}")
        return
    # In an update, `status` prints the command that sets a new release. A page can be stale still, so `status` comes next.
    update = site_checkout() and site_branch() == UPDATE_BRANCH.format(project)
    print("next     " + command("status" if update and args.release else "check", "--project", project))


def add_register_action(actions) -> None:
    register = actions.add_parser("register", help="add the project to the project list of the site and set its release")
    register.add_argument("--project", required=True)
    register.add_argument("--docs", choices=["full", "overview"],
                          help="the size of the doc set (default: the doc set of the last scaffold)")
    register.add_argument("--name", help="the name that the site shows (default: the project name)")
    register.add_argument("--summary", help="one short sentence for the home page and the project menu "
                                            "(default: the description of the overview page)")
    register.add_argument("--release", help="the release that the pages describe (default: the release of the last scaffold)")
    register.add_argument("--branch", help="the branch of that release (default: the release ref of the last scaffold)")
    register.set_defaults(run=cmd_register)


# ---------- commit ----------

def doc_set_files(project: str, state: dict) -> list[str]:
    """The files of a doc set, as paths of the site: each page and each capture spec of the state, the state, the site data."""
    files = [f"src/content/docs/{project}/{path}" for path in state.get("pages", {})]
    files += [f"captures/{project}/{name}.json" for name in state.get("captures", {})]
    return files + [f"docgen/state/{project}.json", "src/data/projects.json", "src/data/versions.json"]


def committed_state(project: str) -> dict:
    """The state of the project in the last commit of the site checkout. Empty when that commit has none."""
    done = site_git("show", f"HEAD:docgen/state/{project}.json")
    try:
        state = json.loads(done.stdout) if done.returncode == 0 else {}
    except json.JSONDecodeError:
        return {}
    return {} if state_fault(state) else state  # A state with another form names no file that `commit` can trust.


def doc_set_work(project: str, state: dict) -> tuple[list[str], list[str]]:
    """The files of the doc set that exist, and the files that the last commit lists and that docgen removed after it.

    `scaffold` removes the capture spec of a frame that a page lost. That removal is a part of the doc set.
    """
    files = doc_set_files(project, state)
    present = [path for path in files if (SITE / path).is_file()]
    removed = [path for path in doc_set_files(project, committed_state(project))
               if path not in files and not (SITE / path).exists()]
    return present, removed


def doc_set_changes(project: str, state: dict) -> list[str]:
    """Each file of the doc set that is not in the last commit as it is now."""
    present, removed = doc_set_work(project, state)
    return site_status(*present, *removed) if present or removed else []


def stop(message: str) -> None:
    """End an action that did a part of its work and cannot do the rest. `fail` is for an action that changed nothing."""
    sys.stdout.flush()
    print(f"error: {message}", file=sys.stderr)
    sys.exit(1)


def cmd_commit(args: argparse.Namespace) -> None:
    project = args.project
    project_name(project)
    if not site_checkout():
        fail("the site directory is no Git checkout, so `commit` has no branch. Stop and tell the user this line.")
    branch, first, update = site_branch(), RUN_BRANCH.format(project), UPDATE_BRANCH.format(project)
    if branch not in (first, update):
        where = f"is on the branch {branch}" if branch else "has a detached HEAD"
        fail(f"the site checkout {where}. `commit` works only on the branch {first} or {update}. Nothing changed. "
             f"Run first: {branch_command(project)}")
    state = project_state(project)
    present, removed = doc_set_work(project, state)
    absent = [path for path in doc_set_files(project, state) if path not in present]
    if absent:
        # A commit with a state that lists an absent file passes each check of the site.
        fail(f"the state lists a file that is absent: {', '.join(absent[:5])}. Nothing changed. "
             f"Run first: {command('scaffold', '--project', project)}")

    # Only the files of the doc set. A file that a person staged is not a part of this commit.
    done = site_git("add", "--", *present, messages=True)
    if done.returncode == 0 and removed:
        done = site_git("rm", "--cached", "--quiet", "--ignore-unmatch", "--", *removed, messages=True)
    if done.returncode != 0:
        fail(f"Git cannot stage the files of the doc set: {git_cause(done.stdout)}. Stop and tell the user this line.")
    # With no search for a renamed file: a removed spec and a new spec with a near text are two files of the commit.
    staged = site_paths("diff", "--cached", "--name-only", "--no-renames", "-z", "HEAD", "--", *present, *removed)
    for path in staged:
        print(f"staged   {path}")
    for path in site_status(f"src/content/docs/{project}", f"captures/{project}"):
        if path not in present and path not in removed:
            print(f"skipped  {path}: docgen did not write it. It is not in the commit.")

    if args.diagrams:
        message = f"Docs of {project}: diagrams"
    elif branch == update:
        old, new = committed_state(project).get("release"), state.get("release")
        message = f"Docs of {project}: update to {new}" if new and new != old else f"Docs of {project}: update"
    else:
        message = f"Docs of {project}: first doc set from docgen"
    again = command("commit", "--project", project, *(["--diagrams"] if args.diagrams else []),
                    *(["--no-push"] if args.no_push else []))
    if not staged:
        print(f"kept     {branch}: the last commit holds each file of the doc set. Nothing to commit.")
    else:
        # The pre-commit hook of the site runs each check. It can take some minutes.
        done = site_git("commit", "--quiet", "-m", message, "--only", "--", *staged, messages=True)
        if done.returncode != 0:
            for line in done.stdout.strip().splitlines()[-GIT_TAIL:]:
                print(site_paths_of(line))
            failed = [name for name, result in site_results(done.stdout)[0].items() if result.startswith("FAIL")]
            if failed:
                stop(f"the pre-commit hook of the site refused the commit: {', '.join(failed)} failed. No commit exists. "
                     f"Run `{command('check', '--project', project)}`, correct each finding, then run again: {again}")
            stop("Git made no commit: a hook refused it, or Git gives the cause in the lines above. "
                 "Stop and tell the user these lines.")
        made = site_git("log", "-1", "--format=%h %s").stdout.strip()
        print(f"commit   {made}")

    if args.no_push:
        print(f"done     the branch {branch} is not pushed (--no-push). Tell the user the result. Do not merge.")
        return
    if "origin" not in site_git("remote").stdout.split():
        stop(f"the site has no remote origin, so the branch {branch} is not pushed. Stop and tell the user this line.")
    # One branch and no other ref: no tag, and never `main`. Git prints one result line for the ref of the push.
    pushed = f"refs/heads/{branch}:refs/heads/{branch}"
    done = site_git("push", "--porcelain", "--no-follow-tags", "--set-upstream", "origin", pushed, messages=True)
    if done.returncode != 0:
        for line in done.stdout.strip().splitlines()[-GIT_TAIL:]:
            print(line)
        stop(f"Git did not push the branch {branch} to origin. The commit is in the local branch. "
             "Stop and tell the user these lines.")
    if re.search(rf"(?m)^=\t{re.escape(pushed)}\t", done.stdout):
        # The result of the push says it. A checkout can have no remote-tracking ref for this branch.
        print(f"kept     origin has each commit of {branch}. Nothing to push.")
    else:
        print(f"pushed   {branch} to origin")
    print(f"done     the branch {branch} waits for the review. Tell the user the result. Do not merge.")


# ---------- site checks ----------

CHECK_SCRIPT = "scripts/check.sh"
SITE_TAIL = 30  # the last lines of a failed check that `check` prints
SITE_CAUSES = 8  # the error lines before these last lines that `check` prints


def site_results(output: str) -> tuple[dict[str, str], dict[str, list[str]]]:
    """Read the output of scripts/check.sh: the result of each check in the summary, and the output lines of each check."""
    body, _, summary = output.rpartition("\n== summary\n")
    results = {}
    for line in summary.splitlines():
        found = re.match(r"\s+(\S+)\s+(\S.*)$", line)
        if found:
            results[found.group(1)] = found.group(2)
    sections: dict[str, list[str]] = {}
    current = None
    for line in body.splitlines():
        head = re.match(r"== (\w+): ", line)
        if head and head.group(1) in results:
            current = sections.setdefault(head.group(1), [])
        elif current is not None and line.strip():
            current.append(re.sub(r"\x1b\[[0-9;]*m", "", line))
    return results, sections


# A check of the site prints a path that is relative to the site. The agent works in the project repository.
SITE_PATH = re.compile(r"(?<![\w./~-])((?:src|captures|docgen|scripts|public|dist)/[\w./@-]*[\w@-])")


def error_lines(lines: list[str]) -> list[str]:
    """The lines of a failed check that name the cause: a line with `[ERROR]`, and the place that a `Location:` line gives.

    The build prints the cause first and a long text after it. So the last lines of its output do not hold the cause.
    """
    found = []
    for index, line in enumerate(lines):
        if "[ERROR]" in line or line.strip().startswith("Location:"):
            found.append(line.strip()[:400])
            if line.strip() == "Location:" and index + 1 < len(lines):
                found.append(lines[index + 1].strip()[:400])
    return list(dict.fromkeys(found))[:SITE_CAUSES]


def site_paths_of(line: str) -> str:
    """One output line of a check of the site, with the absolute path of each file of the site that it names."""
    return SITE_PATH.sub(lambda found: str(SITE / found.group(1)) if (SITE / found.group(1)).exists() else found.group(1), line)


def site_checks(project: str, page_findings: int) -> int:
    """Run the checks of the site after the checks of the pages. Print one line for each check. Return the exit code."""
    if page_findings:
        print("site     not run: correct the findings of the pages first")
        return 1
    if not (SITE / "astro.config.mjs").exists():
        print("site     not run: the directory of docgen holds no site (no astro.config.mjs)")
        return 0
    if not (SITE / CHECK_SCRIPT).exists():
        fail(f"the site has no {CHECK_SCRIPT}. `check` runs the checks of the site with this script.")
    if registration(project)[2]:
        print(f"{PROJECTS}:1: not-registered: the project list or the release of '{project}' is not current. "
              f"Fix: run `{command('register', '--project', project)}`.")
        return 1
    sys.stdout.flush()
    done = subprocess.run(["sh", CHECK_SCRIPT], cwd=SITE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                          text=True, errors="replace")
    results, sections = site_results(done.stdout)
    failed = [name for name, result in results.items() if result.startswith("FAIL")]
    for name, result in results.items():
        print(f"site     {name:<6} {result}")
        if name in failed:
            lines = sections.get(name, [])
            if len(lines) > SITE_TAIL:
                for line in error_lines(lines[:-SITE_TAIL]):
                    print(site_paths_of(line))
                print(f"... {len(lines) - SITE_TAIL} line(s) before these. This command prints each line of each check: "
                      + shlex.join(["sh", str(SITE / CHECK_SCRIPT)]))
            for line in lines[-SITE_TAIL:]:
                print(site_paths_of(line))
    if done.returncode == 0:
        print("next     " + command("commit", "--project", project))
        return 0
    if not failed:
        # The script stopped before the summary, for example because node_modules is absent.
        for line in done.stdout.strip().splitlines()[-SITE_TAIL:]:
            print(line)
        print(f"check failed: {CHECK_SCRIPT} stopped with the exit code {done.returncode}.")
        return 2
    print(f"check failed: {', '.join(failed)}. Correct each finding above. Then run again: {command('check', '--project', project)}")
    return 1


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    actions = parser.add_subparsers(dest="action", required=True)

    survey = actions.add_parser("survey", help="read a project repository and write its facts")
    survey.add_argument("--repo", default=".", help="a path inside the project repository (default: the current directory)")
    survey.add_argument("--project", help="the project name on the site (default: the name of the repository directory)")
    survey.add_argument("--release-ref", help="the ref that Install and Use pages describe (default: portable, or the develop ref)")
    survey.add_argument("--develop-ref", help="the ref that Develop pages describe "
                                              "(default: main, else master, else the branch that is checked out)")
    survey.add_argument("--run-help", action="store_true",
                        help="run `--help` of each Python command line in a clean container without network, and save the text")
    survey.add_argument("--update", action="store_true",
                        help="the run is an update of a doc set: the `next` line names `branch --update`")
    survey.set_defaults(run=cmd_survey)

    branch = actions.add_parser("branch", help="start the branch of the run in the site, or change to it")
    branch.add_argument("--project", required=True)
    branch.add_argument("--update", action="store_true",
                        help="the branch of an update, topic/docgen-update-<project> (default: topic/docgen-<project>)")
    branch.set_defaults(run=cmd_branch)

    plan = actions.add_parser("plan", help="choose the pages of the doc set")
    plan.add_argument("--project", required=True)
    plan.add_argument("--profile", default="v1")
    plan.add_argument("--doc-set", default="full", choices=["full", "overview"])
    plan.set_defaults(run=cmd_plan)

    for name, run, text in (("scaffold", cmd_scaffold, "write the page skeletons"),
                            ("next", cmd_next, "print the next open slot"),
                            ("check", cmd_check, "check the pages of one project"),
                            ("diagrams", cmd_diagrams, "list the diagrams that a larger model draws")):
        sub = actions.add_parser(name, help=text)
        sub.add_argument("--project", required=True)
        sub.set_defaults(run=run)

    actions.choices["scaffold"].add_argument(
        "--refresh", metavar="PAGE", help="record the current sources of one corrected page, and write a page of the "
                                          "script again (a page path as `status` prints it, or `all`)")
    for name in ("next", "check", "diagrams"):
        actions.choices[name].set_defaults(refresh=None)

    status = actions.add_parser("status", help="list the pages whose sources changed")
    status.add_argument("--project", required=True)
    status.add_argument("--repo", help="the project repository (default: the path of the last survey)")
    status.set_defaults(run=cmd_status)
    add_register_action(actions)

    commit = actions.add_parser("commit", help="commit the files of the doc set on the branch of the run, and push the branch")
    commit.add_argument("--project", required=True)
    commit.add_argument("--diagrams", action="store_true", help="the commit of the diagram pass")
    commit.add_argument("--no-push", action="store_true", help="make the commit, and do not push the branch")
    commit.set_defaults(run=cmd_commit)

    args = parser.parse_args()
    drop_git_variables()
    keep_project_repository()
    args.run(args)


if __name__ == "__main__":
    main()
