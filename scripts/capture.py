#!/usr/bin/env python3
"""Run the scripted captures of one project in a clean container.

Usage: scripts/capture.py [--project tenant-pi] [--source <path>] [--out <directory>] [--timeout <seconds>]

The script reads each spec `captures/<project>/*.json` with `"mode": "scripted"`. A spec without
`ref` runs on the documented release. A spec with `ref` runs on that branch of the source. Each ref
has its own container and its own shell session, and the commands run in ascending `order`. The
script writes `<name>.txt` and `<name>.cast` beside each spec, and the record
`captures/<project>.record.json`. See `captures/README.md` for the spec, the container and the rules.

Needs on the host: Python 3.9 or later, Git, Node and Docker. It uses the standard library only.
A message of this script never holds the source location.
VERSIONS_FILE replaces the path of versions.json. Use it for a test only.
"""
import argparse
import json
import os
import re
import shlex
import shutil
import socket
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VERSIONS = Path(os.environ.get("VERSIONS_FILE") or ROOT / "src/data/versions.json")
DOCKERFILE = ROOT / "scripts/capture.Dockerfile"
IMAGE = "tenant-docs-capture:local"

# The neutral values of the container. `scripts/capture.Dockerfile` makes the user.
USER = "alex"
HOME = "/home/alex"
HOSTNAME = "example"
COLS, ROWS = 80, 24
SESSION_ENV = {
    "HOME": HOME, "USER": USER, "LOGNAME": USER, "SHELL": "/bin/bash", "TERM": "xterm-256color",
    "LANG": "C.UTF-8", "TZ": "UTC", "PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
    # No command waits for a key: a pager prints its input and ends.
    "PAGER": "cat", "GIT_PAGER": "cat",
    # asciinema writes its own files here, and not into the home directory.
    "ASCIINEMA_CONFIG_HOME": "/capture/asciinema",
}

# The session shell prints these marks into the recording. An OSC sequence shows nothing in a terminal.
MARK = "\x1b]7770;"
MARK_END = "\x07"

# Fixed timing of a written recording, in seconds. A second run gives the same file.
PROMPT = "$ "
TYPE_STEP = 0.03
OUTPUT_STEP = 0.05
OUTPUT_TOTAL = 3.0

NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*\Z")
BRANCH = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*(?:/[A-Za-z0-9][A-Za-z0-9._-]*)*\Z")
# The text that replaces a value. Angle brackets show a reader that it is not real output.
PLACEHOLDER = re.compile(r"<[^<>\r\n]+>\Z")
COMMIT_ID = re.compile(r"(?<![0-9A-Za-z])[0-9a-f]{7,40}(?![0-9A-Za-z])")
CSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
OSC = re.compile(r"\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)")
OTHER_ESCAPE = re.compile(r"\x1b[()][0-9A-Za-z]|\x1b[=>78]")
PRIVATE_IP = re.compile(
    r"(?<![0-9.])(?:10\.\d{1,3}|192\.168|172\.(?:1[6-9]|2\d|3[01])|100\.(?:6[4-9]|[7-9]\d|1[01]\d|12[0-7]))"
    r"\.\d{1,3}\.\d{1,3}(?![0-9])")
HOME_PATH = re.compile(r"/(?:home|Users)/([A-Za-z0-9._-]+)")
SECRET_NAME = re.compile(r"TOKEN|SECRET|PASSWORD|PASSWD|CREDENTIAL|API_?KEY|_KEY\Z", re.I)


# The source location, as given and as resolved. No message and no capture holds one of them.
SOURCE_FORMS = set()


class CaptureError(Exception):
    """A failure with a message for the person who runs the script."""

    def __str__(self):
        text = super().__str__()
        for form in sorted(SOURCE_FORMS, key=len, reverse=True):
            text = text.replace(form, "<source>")
        return text


def note(text):
    print(text, flush=True)


def run(command, **options):
    """Run one host command. The caller reads `returncode`."""
    return subprocess.run(command, text=True, capture_output=True, **options)


def must(command, what, **options):
    result = run(command, **options)
    if result.returncode != 0:
        raise CaptureError(f"{what} failed.\n{(result.stderr or result.stdout).strip()}")
    return result.stdout


def source_variable(project):
    return re.sub(r"[^A-Z0-9]", "_", project.upper()) + "_SOURCE"


def env_file_value(name):
    env_file = ROOT / ".env"
    if not env_file.is_file():
        return None
    value = None
    for line in env_file.read_text(encoding="utf-8").splitlines():
        if line.startswith(name + "="):
            value = line[len(name) + 1:].strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
    return value or None


def source_location(project, argument):
    """The source of the project: the argument, else the environment, else the untracked `.env`."""
    name = source_variable(project)
    source = argument or os.environ.get(name) or env_file_value(name)
    if not source:
        raise CaptureError(f"no source for {project}. Give --source, or set {name} in .env.")
    if not Path(source).is_dir():
        raise CaptureError(f"the source of {project} is not a directory.")
    resolved = str(Path(source).resolve())
    SOURCE_FORMS.update({source.rstrip("/"), resolved})
    return resolved


def documented_release(project):
    try:
        entry = json.loads(VERSIONS.read_text(encoding="utf-8"))[project]
        return entry["release"]
    except (OSError, ValueError, KeyError, TypeError):
        raise CaptureError(f"src/data/versions.json has no release for {project}.") from None


def load_specs(project):
    """The scripted specs of the project in run order, and the names of the other specs."""
    directory = ROOT / "captures" / project
    scripted, manual = [], []
    for file in sorted(directory.glob("*.json")):
        name = file.stem
        try:
            spec = json.loads(file.read_text(encoding="utf-8"))
        except ValueError as error:
            raise CaptureError(f"captures/{project}/{file.name} is not JSON: {error}") from None
        if not isinstance(spec, dict):
            raise CaptureError(f"captures/{project}/{file.name} is not a JSON object.")
        where = f"captures/{project}/{file.name}"
        if spec.get("mode") != "scripted":
            if spec.get("mode") != "manual":
                note(f"warning: {where} has no `mode` of `scripted` or `manual`. The script does not run it.")
            manual.append(name)
            continue
        if not NAME.match(name):
            raise CaptureError(f"{where}: the name has a character that is not a letter, a digit, '.', '_' or '-'.")
        command = spec.get("command")
        if not isinstance(command, str) or not command.strip():
            raise CaptureError(f"{where}: `command` is absent or empty.")
        setup = spec.get("setup", [])
        if not isinstance(setup, list) or not all(isinstance(item, str) for item in setup):
            raise CaptureError(f"{where}: `setup` is not a list of strings.")
        order = spec.get("order")
        if isinstance(order, bool) or not isinstance(order, (int, float)):
            note(f"warning: {where} has no `order`. It runs last.")
            order = float("inf")
        expected = spec.get("exit")
        if expected is not None and (isinstance(expected, bool) or not isinstance(expected, int)):
            raise CaptureError(f"{where}: `exit` is not a whole number.")
        ref = spec.get("ref")
        if ref is not None and (not isinstance(ref, str) or not BRANCH.match(ref) or ".." in ref):
            raise CaptureError(f"{where}: `ref` is not the name of a branch.")
        scripted.append({"name": name, "command": command, "setup": setup, "order": order,
                         "exit": expected, "title": str(spec.get("title") or name), "ref": ref,
                         "replace": replace_rules(spec.get("replace", []), where)})
    scripted.sort(key=lambda spec: (spec["order"], spec["name"]))
    return scripted, manual


def replace_rules(value, where):
    """The declared rules of one spec. Each rule replaces one value that changes from run to run."""
    if not isinstance(value, list):
        raise CaptureError(f"{where}: `replace` is not a list.")
    rules = []
    for index, item in enumerate(value, 1):
        rule = f"{where}: rule {index} of `replace`"
        if not isinstance(item, dict) or not all(isinstance(item.get(key), str) and item[key] for key in ("what", "match", "with")):
            raise CaptureError(f"{rule} needs the text fields `what`, `match` and `with`.")
        try:
            pattern = re.compile(item["match"])
        except re.error as error:
            raise CaptureError(f"{rule}: `match` is not a regular expression: {error}") from None
        if pattern.groups != 1:
            raise CaptureError(f"{rule}: `match` must have one group. The group is the value that the script replaces.")
        if not PLACEHOLDER.match(item["with"]):
            raise CaptureError(f"{rule}: `with` must be a placeholder in angle brackets, for example <seconds>.")
        rules.append({"what": item["what"], "pattern": pattern, "with": item["with"]})
    return rules


def apply_rules(raw, rules):
    """Replace the group of each rule in the raw output. Return the new output and one count for each rule."""
    replaced = []
    for rule in rules:
        count = 0

        def swap(found):
            nonlocal count
            start, end = found.span(1)
            if start < 0:
                return found.group(0)
            count += 1
            return found.string[found.start():start] + rule["with"] + found.string[end:found.end()]

        raw = rule["pattern"].sub(swap, raw)
        replaced.append({"what": rule["what"], "with": rule["with"], "count": count})
    return raw, replaced


def source_groups(specs, release):
    """The specs of each ref in run order. The release is first. Each group gets its own container."""
    groups = [{"kind": "release", "ref": release, "full": f"refs/tags/{release}", "specs": []}]
    for spec in specs:
        if spec["ref"] is None:
            groups[0]["specs"].append(spec)
            continue
        group = next((group for group in groups[1:] if group["ref"] == spec["ref"]), None)
        if group is None:
            group = {"kind": "branch", "ref": spec["ref"], "full": f"refs/heads/{spec['ref']}", "specs": []}
            groups.append(group)
        group["specs"].append(spec)
    return [group for group in groups if group["specs"]]


def session_script(specs):
    """The one shell script that runs every capture. A later capture sees the state of an earlier one."""
    lines = [
        "#!/bin/bash",
        "# Generated by scripts/capture.py. One shell runs every capture of the project.",
        "unset ASCIINEMA_REC ASCIINEMA_CONFIG_HOME",
        f"cd {shlex.quote(HOME)} || exit 1",
        "__capture_mark() { printf '\\033]7770;%s\\007' \"$1\"; }",
    ]
    for spec in specs:
        name = spec["name"]
        lines.append(f"\n# {name}")
        lines.append(f"echo '## {name}' >>/capture/setup.log")
        lines.append("__capture_ready=1")
        for index, command in enumerate(spec["setup"], 1):
            # A setup command that fails skips the rest of this capture. The session goes on.
            lines.append(
                f"[ $__capture_ready = 1 ] && {{ eval {shlex.quote(command)} >>/capture/setup.log 2>&1 </dev/null"
                f" || {{ __capture_ready=0; __capture_mark 'setup-failed;{name};{index}'; }}; }}")
        lines.append("if [ $__capture_ready = 1 ]; then")
        lines.append(f"  __capture_mark 'begin;{name}'")
        lines.append(f"  eval {shlex.quote(spec['command'])} </dev/null")
        lines.append("  __capture_rc=$?")
        lines.append(f"  __capture_mark \"end;{name};$__capture_rc\"")
        lines.append("fi")
    return "\n".join(lines) + "\n"


def prepare_script(project, group):
    """Runs as root in the container: make the Git repository `/srv/<project>.git` from the bundle."""
    repository = shlex.quote(f"/srv/{project}.git")
    full = group["full"]
    lines = [
        "set -eu",
        "umask 022",
        f"git init -q --bare -b main {repository}",
        f"cd {repository}",
        f"git fetch -q --no-tags /capture/source.bundle {shlex.quote(full + ':' + full)}",
    ]
    if group["kind"] == "release":
        # A clone of the public repository has the release on the branch `main`, and it has the release tag.
        lines.append(f"git update-ref refs/heads/main {shlex.quote(full + '^{commit}')}")
    else:
        lines.append(f"git symbolic-ref HEAD {shlex.quote(full)}")
    lines += [
        "git rev-parse HEAD",
        "rm -f FETCH_HEAD /capture/source.bundle",
        f"chown -R {USER}:{USER} {repository}",
    ]
    return "\n".join(lines) + "\n"


def recorded_output(cast):
    """The size of the recording and its whole output as one string."""
    lines = cast.splitlines()
    if not lines:
        raise CaptureError("the recording is empty.")
    header = json.loads(lines[0])
    output = []
    for line in lines[1:]:
        try:
            event = json.loads(line)
        except ValueError:
            continue  # A run that stopped can leave a part of a line.
        if isinstance(event, list) and len(event) == 3 and event[1] == "o":
            output.append(event[2])
    return header.get("width", COLS), header.get("height", ROWS), "".join(output)


def split_output(output, specs):
    """The raw output and the exit code of each capture, cut at the marks. A failed capture has a reason."""
    results = {}
    for spec in specs:
        name = re.escape(spec["name"])
        begin = re.escape(MARK) + f"begin;{name}" + MARK_END
        found = re.search(begin + r"(.*?)" + re.escape(MARK) + f"end;{name};(\\d+)" + MARK_END, output, re.S)
        setup = re.search(re.escape(MARK) + f"setup-failed;{name};(\\d+)" + MARK_END, output)
        if found:
            results[spec["name"]] = {"raw": found.group(1), "code": int(found.group(2)), "reason": None}
        elif setup:
            results[spec["name"]] = {"reason": f"setup command {setup.group(1)} failed"}
        elif re.search(begin, output):
            results[spec["name"]] = {"reason": "the command did not end"}
        else:
            results[spec["name"]] = {"reason": "the command did not start, because the session stopped before it"}
    return results


def setup_log(log, name):
    """The last lines that the setup commands of one capture wrote."""
    section = re.search(r"^## " + re.escape(name) + r"\n(.*?)(?=^## |\Z)", log, re.S | re.M)
    lines = section.group(1).rstrip().splitlines() if section else []
    return ["    " + line for line in lines[-8:]]


def to_text(raw):
    """The static frame: the output with line ends of a file and with color sequences only."""
    text = OSC.sub("", raw.replace("\r\n", "\n"))
    text = CSI.sub(lambda found: found.group(0) if found.group(0).endswith("m") else "", text)
    text = OTHER_ESCAPE.sub("", text).replace("\x07", "")
    # A carriage return starts the line again, for example in a progress line. Keep the last state.
    text = "\n".join(line.rstrip("\r").rsplit("\r", 1)[-1] for line in text.split("\n"))
    return text if not text or text.endswith("\n") else text + "\n"


def to_cast(spec, raw, width, height):
    """One asciicast v2 file: the prompt, the typed command and the recorded output, with a fixed timing."""
    events, clock = [], 0.0

    def emit(delay, data):
        nonlocal clock
        clock += delay
        events.append([round(clock, 3), "o", data])

    emit(0.0, PROMPT)
    clock += 0.5
    for character in spec["command"]:
        if character == "\n":
            emit(TYPE_STEP, "\r\n")
            emit(TYPE_STEP, "> ")
        else:
            emit(TYPE_STEP, character)
    emit(0.4, "\r\n")
    chunks = re.findall(r"[^\n]*\n|[^\n]+", raw)
    step = min(OUTPUT_STEP, OUTPUT_TOTAL / len(chunks)) if chunks else 0.0
    clock += 0.3
    for chunk in chunks:
        emit(step, chunk)
    if raw and not raw.endswith("\n"):
        emit(0.0, "\r\n")
    emit(0.3, PROMPT)
    emit(2.0, "")  # Hold the last frame.
    header = {"version": 2, "width": width, "height": height, "title": spec["title"],
              "env": {"SHELL": SESSION_ENV["SHELL"], "TERM": SESSION_ENV["TERM"]}}
    lines = [json.dumps(header, ensure_ascii=False)]
    lines += [json.dumps(event, ensure_ascii=False) for event in events]
    return "\n".join(lines) + "\n"


def forbidden_values():
    """Values of this host that no capture can hold. The script learns them at run time and stores none."""
    values = {"the source location": set(SOURCE_FORMS)}
    names = {socket.gethostname(), socket.getfqdn()}
    # Also the first label of each name, and the domain when it has two labels or more.
    names |= {name.split(".")[0] for name in names} | {name.split(".", 1)[1] for name in names if name.count(".") >= 2}
    values["a host name of this host"] = {name for name in names if len(name) >= 4 and name != "localhost"}
    user = os.environ.get("USER") or os.environ.get("LOGNAME") or ""
    home = os.path.expanduser("~")
    values["the user name of this host"] = {user} if len(user) >= 4 and user != "root" else set()
    values["the home path of this host"] = {home} if len(home) > 1 else set()
    values["a credential of this host"] = {
        value for name, value in os.environ.items() if SECRET_NAME.search(name) and len(value) >= 12}
    return values


def scan(files, history=None):
    """Find each value of this host, private address and home path of another user. A finding is `<file>:<line>: <label>`.

    `history` gives the commit IDs of a branch for the files of that branch: `{file name: (branch, IDs)}`.
    """
    forbidden = forbidden_values()
    findings = []
    for name, text in sorted(files.items()):
        branch, commits = (history or {}).get(name, (None, ()))
        for number, line in enumerate(text.splitlines(), 1):
            for label, values in forbidden.items():
                if any(value in line for value in values):
                    findings.append(f"{name}:{number}: {label}")
            if PRIVATE_IP.search(line):
                findings.append(f"{name}:{number}: a private network address")
            for found in HOME_PATH.finditer(line):
                user = found.group(1)
                if user != USER and not user.isupper() and "EXAMPLE" not in user:
                    findings.append(f"{name}:{number}: a home path of another user")
            # A branch can be private. The site shows no commit ID of such a branch.
            if any(commit.startswith(found.group(0)) for found in COMMIT_ID.finditer(line) for commit in commits):
                findings.append(f"{name}:{number}: a commit ID of the branch {branch}")
    return findings


def docker(*arguments, **options):
    return run(["docker", *arguments], **options)


def export_source(source, group, work):
    """Write the history of one ref into a bundle file. This reads the source and changes nothing in it."""
    what = f"the {group['kind']} {group['ref']}"
    found = run(["git", "-C", source, "rev-parse", "--quiet", "--verify", group["full"] + "^{commit}"])
    if found.returncode != 0:
        raise CaptureError(f"the source does not hold {what}.")
    group["commit"] = found.stdout.strip()
    # Only a release commit is public. The record and the files hold no commit ID of a branch.
    group["history"] = set()
    if group["kind"] == "branch":
        group["history"] = set(must(["git", "-C", source, "rev-list", group["full"]], "git rev-list").split())
    must(["git", "-C", source, "bundle", "create", str(work / "source.bundle"), group["full"]], f"git bundle of {what}")


def capture_group(project, source, group, timeout, container):
    """Run the session of one ref in a new container. Return the files and the result of each capture."""
    specs = group["specs"]
    work = Path(tempfile.mkdtemp(prefix="tenant-docs-capture-"))
    try:
        note(f"\nExport the {group['kind']} {group['ref']} with git bundle.")
        export_source(source, group, work)
        note(f"  commit {group['commit'][:12]}")

        note("Start the container without network access.")
        must(["docker", "run", "-d", "--name", container, "--network", "none", "--hostname", HOSTNAME,
              "--security-opt", "no-new-privileges", IMAGE], "docker run")
        (work / "prepare.sh").write_text(prepare_script(project, group), encoding="utf-8")
        (work / "session.sh").write_text(session_script(specs), encoding="utf-8")
        for name in ("source.bundle", "prepare.sh", "session.sh"):
            must(["docker", "cp", "-q", str(work / name), f"{container}:/capture/{name}"], f"docker cp of {name}")
        made = must(["docker", "exec", "-u", "root", container, "sh", "/capture/prepare.sh"],
                    "the preparation of the repository in the container").strip()
        if made != group["commit"]:
            raise CaptureError(f"the commit in the container differs from the commit of the {group['kind']}.")

        note(f"Record {len(specs)} captures in one session.")
        session = ["docker", "exec", "-u", USER, "-w", HOME, container, "env", "-i",
                   *[f"{key}={value}" for key, value in SESSION_ENV.items()],
                   "asciinema", "rec", "--quiet", "--overwrite", "--cols", str(COLS), "--rows", str(ROWS),
                   "--command", "bash --noprofile --norc /capture/session.sh", "/capture/session.cast"]
        timed_out, recorder = False, ""
        try:
            recorder = run(session, stdin=subprocess.DEVNULL, timeout=timeout).stderr.strip()
        except subprocess.TimeoutExpired:
            timed_out = True
        copied = docker("cp", "-q", f"{container}:/capture/session.cast", str(work / "session.cast"))
        if copied.returncode != 0:
            raise CaptureError(f"the session wrote no recording.\n{recorder}")
        width, height, output = recorded_output((work / "session.cast").read_text(encoding="utf-8"))
        results = split_output(output, specs)
        log = docker("exec", container, "cat", "/capture/setup.log").stdout
        files = {}
        for spec in specs:
            result = results[spec["name"]]
            result["ref"] = group["ref"]
            # Only the commit of a release goes into the record.
            result["commit"] = group["commit"] if group["kind"] == "release" else None
            if result["reason"] is None:
                raw, result["replaced"] = apply_rules(result["raw"], spec["replace"])
                unused = [rule["what"] for rule in result["replaced"] if rule["count"] == 0]
                if unused:
                    # The form of the output changed. The value can be in the output in another form.
                    result["reason"] = f"a rule of `replace` found no value: {unused[0]}"
                    result["detail"] = ["    " + line for line in to_text(raw).splitlines()[-5:]]
                    continue
                files[spec["name"] + ".txt"] = to_text(raw)
                files[spec["name"] + ".cast"] = to_cast(spec, raw, width, height)
            else:
                if timed_out and "did not" in result["reason"]:
                    result["reason"] += f" (the session passed the time limit of {timeout} s)"
                result["detail"] = setup_log(log, spec["name"]) if "setup" in result["reason"] else []

        # asciinema reads each written recording. This proves that a player can read the file.
        check = work / "check"
        check.mkdir()
        for name, text in files.items():
            if name.endswith(".cast"):
                (check / name).write_text(text, encoding="utf-8")
        if any(check.iterdir()):
            must(["docker", "cp", "-q", str(check), f"{container}:/capture/check"], "docker cp of the recordings")
            # `asciinema cat` needs a terminal, so this one command gets a pseudo-terminal.
            must(["docker", "exec", "-t", container, "sh", "-c",
                  "for file in /capture/check/*.cast; do asciinema cat \"$file\" >/dev/null || exit 1; done"],
                 "the asciinema read of the written recordings", stdin=subprocess.DEVNULL)
        return files, results
    finally:
        docker("rm", "-f", container)
        shutil.rmtree(work, ignore_errors=True)


def capture(project, source, groups, timeout):
    """Run each group in its own container. Return the files, the results and the branch history of each file."""
    note("Build the container image.")
    with DOCKERFILE.open("rb") as dockerfile:
        build = subprocess.run(["docker", "build", "-q", "-t", IMAGE, "-"], stdin=dockerfile, capture_output=True)
    if build.returncode != 0:
        raise CaptureError(f"docker build failed.\n{build.stderr.decode(errors='replace').strip()}")
    files, results, history = {}, {}, {}
    for index, group in enumerate(groups, 1):
        container = f"tenant-docs-capture-{project}-{os.getpid()}-{index}"
        group_files, group_results = capture_group(project, source, group, timeout, container)
        files.update(group_files)
        results.update(group_results)
        if group["history"]:
            for spec in group["specs"]:
                for suffix in (".txt", ".cast", ".json"):
                    history[spec["name"] + suffix] = (group["ref"], group["history"])
    return files, results, history


def record_text(project, old, results, written, names):
    """The record of the project: the ref of each capture and each value that the script replaced.

    A capture that failed keeps its old entry, as it keeps its old files.
    """
    entries = {}
    for name in sorted(names):
        if name in written:
            result = results[name]
            entry = {"ref": result["ref"]}
            if result["commit"]:
                entry["commit"] = result["commit"]
            entry["exit"] = result["code"]
            entry["replaced"] = result["replaced"]
            entries[name] = entry
        elif isinstance(old.get(name), dict):
            entries[name] = old[name]
    return json.dumps({"project": project, "captures": entries}, indent=2, ensure_ascii=False) + "\n"


def main():
    parser = argparse.ArgumentParser(description="Run the scripted captures of one project in a clean container.")
    parser.add_argument("--project", default="tenant-pi", help="a directory of captures/ (default: tenant-pi)")
    parser.add_argument("--source", help="the path of a local clone of the project (default: <PROJECT>_SOURCE)")
    parser.add_argument("--out", help="write the files into this directory, and not into captures/")
    parser.add_argument("--timeout", type=int, default=900,
                        help="time limit of one session in seconds (default: 900)")
    arguments = parser.parse_args()
    project = arguments.project

    try:
        source = source_location(project, arguments.source)
        release = documented_release(project)
        specs, manual = load_specs(project)
        if not specs:
            raise CaptureError(f"captures/{project}/ has no spec with \"mode\": \"scripted\".")
        for tool in ("git", "docker", "node"):
            if shutil.which(tool) is None:
                raise CaptureError(f"the command `{tool}` is absent.")

        # Drift control: stop when the source has a newer release than the pages describe.
        checked = subprocess.run([str(ROOT / "scripts/check-version.sh"), project, source])
        if checked.returncode != 0:
            return checked.returncode

        files, results, history = capture(project, source, source_groups(specs, release), arguments.timeout)

        # A capture fails on an exit code that its spec does not expect, and on a finding of the scan.
        # The spec text is on the page and in the recording, so the scan reads it too.
        spec_text = {spec["name"] + ".json": "\n".join([spec["title"], spec["command"], *spec["setup"]]) for spec in specs}
        findings = scan({**files, **spec_text}, history)
        for spec in specs:
            name, result = spec["name"], results[spec["name"]]
            if result["reason"] is not None:
                continue
            expected = spec["exit"] or 0
            mine = [finding for finding in findings if finding.split(":")[0].rsplit(".", 1)[0] == name]
            if result["code"] != expected:
                result["reason"] = f"exit code {result['code']}, the spec expects {expected}"
                result["detail"] = ["    " + line for line in files[name + ".txt"].splitlines()[-5:]]
            elif mine:
                result["reason"] = "a finding of the scan"
                result["detail"] = ["    " + finding for finding in mine]

        target = Path(arguments.out) if arguments.out else ROOT / "captures" / project
        target.mkdir(parents=True, exist_ok=True)
        note(f"\n{'capture':<34} {'exit':>4}  state")
        failed, written = [], []
        for spec in specs:
            name, result = spec["name"], results[spec["name"]]
            if result["reason"] is not None:
                failed.append(name)
                note(f"{name:<34} {result.get('code', '-'):>4}  FAILED: {result['reason']}")
                for line in result.get("detail", []):
                    note(line)
                continue
            text_file = target / f"{name}.txt"
            if not text_file.exists():
                state = "new"
            else:
                state = "same" if text_file.read_text(encoding="utf-8") == files[name + ".txt"] else "changed"
            for suffix in (".txt", ".cast"):
                (target / (name + suffix)).write_text(files[name + suffix], encoding="utf-8")
                written.append(str(target / (name + suffix)))
            note(f"{name:<34} {result['code']:>4}  {state}")
        known = {file.stem for file in (ROOT / "captures" / project).glob("*.json")}
        for file in sorted(target.glob("*.txt")) + sorted(target.glob("*.cast")):
            if file.stem not in known:
                note(f"warning: {file.name} has no spec.")

        # The record is beside the project directory, so no reader takes it for a spec.
        record_file = (Path(arguments.out) if arguments.out else ROOT / "captures") / f"{project}.record.json"
        try:
            old = json.loads(record_file.read_text(encoding="utf-8"))["captures"]
        except (OSError, ValueError, KeyError, TypeError):
            old = {}
        done = {Path(file).stem for file in written}
        record = record_text(project, old if isinstance(old, dict) else {}, results, done, [spec["name"] for spec in specs])
        state = "new" if not record_file.exists() else "same" if record_file.read_text(encoding="utf-8") == record else "changed"
        record_file.write_text(record, encoding="utf-8")
        note(f"\n{record_file.name}: {state}")
        note(f"{project} {release}: {len(specs) - len(failed)} captures written, {len(failed)} failed,"
             f" {len(manual)} other specs skipped.")
        if failed:
            print("error: the script wrote no file for a failed capture. Its old files, if any, did not change.",
                  file=sys.stderr)

        # The host-value scanner of the repository (issue 4) has more rules. It reads the written files.
        scanner = ROOT / "scripts/scan.py"
        found = False
        if scanner.is_file() and written:
            note("\nRun scripts/scan.py on the written files.")
            found = subprocess.run([sys.executable, str(scanner), *written, str(record_file)]).returncode != 0
            if found:
                print("error: scripts/scan.py has a finding in the written files. Do not commit them.", file=sys.stderr)
        return 1 if failed or found else 0
    except CaptureError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
