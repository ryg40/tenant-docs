# Captures

A capture is the real output of one command, recorded for a doc page. Pages never hold typed-in output.

Each capture has an id of the form `<project>/<name>`, for example `tenant-pi/validate`. It has up to three files in this directory:

| File | Content | Written by |
| --- | --- | --- |
| `<id>.json` | The spec: what to run. | A person or an agent |
| `<id>.txt` | The output of the command. ANSI colors are permitted. | The capture script, or by hand for a manual capture |
| `<id>.cast` | The asciinema recording of the same run. | The capture script |

Each project also has the record `captures/<project>.record.json`. The capture script writes it. See [The record](#the-record).

## The spec

```json
{
  "title": "Validate the overlay",
  "stage": 3,
  "order": 300,
  "command": "python3 scripts/tenant_pi.py validate",
  "setup": [],
  "replace": [],
  "mode": "scripted"
}
```

| Field | Meaning |
| --- | --- |
| `title` | The title of the terminal frame. |
| `stage` | The stage of the project workflow that the command belongs to. Optional. |
| `order` | The position of the capture in the run of its project. The capture script runs the scripted captures of one ref in one session, in ascending order, so a later capture sees the results of an earlier one. |
| `ref` | A branch of the project source, for example `main`. The command runs on that branch. Without the field, the command runs on the documented release. Optional. |
| `command` | The command line that the page shows. |
| `setup` | Shell commands that run before `command`. The page does not show them. The capture fails when a setup command fails. Optional. |
| `exit` | The exit code that `command` must give. The default is 0. Optional. |
| `replace` | The rules for the values that change from run to run. See [Stable output](#stable-output). Optional. |
| `mode` | `scripted`: the capture script runs it in a clean container. `manual`: a person records it and redacts it. |

## Names and order ranges for tenant-pi

| Name | Order | Content |
| --- | --- | --- |
| `stage1-*` to `stage5-*` | 100 to 599 | The install stages that the kit runs. |
| `help-*` | 150 to 199 | `--help` of the command line and of each action. |
| `cmd-*`, `update-*` | 600 to 799 | The Use pages: single actions and the candidate update loop. |
| `dev-*` | 800 to 999 | The Develop pages. Each spec has `"ref": "main"`. |

`captures/demo/` holds the captures of the style guide. Their specs have `"mode": "manual"`, so the capture script does not run them.

### Captures of stages 1 to 5

These captures exist. The kit commands come from `docs/guides/setup.md` of the release.

| Name | Order | Content |
| --- | --- | --- |
| `stage1-clone` | 100 | `git clone` with the placeholder `<the URL of the tenant-pi repository>`. |
| `stage1-clone-checks` | 110 | The unit tests, the publish check and `check-runtime`, in one command line. The exit code is 1, because Pi is absent. |
| `help` | 150 | `--help` of the command line. It lists 17 actions. |
| `help-<action>` | 152 to 184 | `--help` of each of the 17 actions. The orders 152 to 168 are `check-runtime`, `init-private`, `validate`, `plan`, `generate`, `compare`, `carry`, `inventory` and `list`. The orders 170 to 184 are `baseline`, `check-baseline`, `check-herdr`, `check-wiki-vault`, `components`, `remote-plan`, `compose-plan` and `results`. |
| `stage2-init-private` | 200 | `init-private` with `--dir` and `--target`. |
| `stage2-overlay` | 220 | The overlay of the new private directory. The setup makes the parent of the target. |
| `stage2-json-check` | 230 | The syntax check of the overlay with `python3 -m json.tool`. |
| `stage2-components` | 240 | `components --format text`: the checklist of the 27 components. |
| `stage2-components-core` | 250 | `components --select core`: the selection of the sample overlay. |
| `stage2-components-select` | 260 | `components --select core,ops-footer`. The action adds `context-meter`. |
| `stage2-check-wiki-vault` | 270 | `check-wiki-vault`. The result is `no_vault`. |
| `stage3-validate` | 300 | `validate`. |
| `stage4-runtime-report` | 400 | `check-runtime` with its output in the file `runtime.json`. The output is empty. The exit code is 1, because Pi is absent. |
| `stage4-runtime-report-file` | 405 | The file `runtime.json`. |
| `stage4-plan` | 410 | `plan` with `--launcher` and `--runtime-report`. |
| `stage5-generate` | 500 | `generate` without a launcher and without a runtime report. |
| `stage5-generate-launcher` | 510 | `generate` with `--launcher`. The setup removes the profile of `stage5-generate` first. |
| `stage5-profile-files` | 520 | The paths of the new profile. |
| `stage5-launcher-file` | 530 | The launcher file. |

No capture of stages 1 to 5 changes the overlay. The `components` and `check-wiki-vault` captures write nothing.

After order 530, the session has this state. A later capture can use it.

- The working directory is the kit clone `/home/alex/tenant-pi`.
- The private directory is `/home/alex/.config/tenant-pi`. It holds the overlay, `runtime.json` and `launch-main.sh`.
- `runtime.json` is the runtime report of order 400: Node `match`, Pi `missing`, Python `match`.
- The generated profile is `/home/alex/.pi/profiles/main`. It is core-only.
- Pi is not installed. `npm` has no network access.

### Captures of the Use pages

These captures exist. They run in the release session, after the captures of stages 1 to 5.

| Name | Order | Content |
| --- | --- | --- |
| `cmd-check-runtime` | 600 | `check-runtime`. Pi is `missing`. |
| `cmd-refusal` | 610 | `generate` with a target that exists. The command prints the exit code 2. |
| `cmd-init-private` | 620 | `init-private` without `--target`, for the second private directory `tenant-pi-work`. |
| `cmd-inventory` | 630 | `inventory` of the directory `hand-made`. The setup makes that directory. |
| `cmd-baseline` | 640 | `baseline` of the directory `hand-made`. It writes `hand-made-baseline.json` into the private directory. |
| `cmd-check-baseline` | 645 | `check-baseline` of the same directory. The setup adds one file below `prompts`, so the result is `changed`. |
| `cmd-check-herdr` | 650 | `check-herdr`. The container has no `herdr` command, so the status is `missing`. The command prints the exit code 1. |
| `cmd-check-wiki-vault` | 655 | `check-wiki-vault`. The setup makes `~/.llm-wiki` with a file `config.json`, so the result is `vault_exists`. |
| `cmd-components` | 660 | `components --format text` with the overlay of the session. Only `core` has a mark. |
| `cmd-remote-plan` | 665 | `remote-plan` with the target `build-host` and the account `alex`. |
| `cmd-compose-plan` | 670 | `compose-plan` without `--write`. The setup writes a public key file with an example key line. The command stops the output at the first command line of the plan. |
| `cmd-results` | 675 | `results` without `--out-dir`. The setup writes the facts file. The command stops the output at the heading of the second section. |
| `update-target` | 700 | The new target in the overlay. The setup sets it. |
| `cmd-validate` | 710 | `validate`. |
| `cmd-plan` | 720 | `plan` with `--launcher` and without a runtime report. |
| `cmd-generate` | 730 | `generate` with `--launcher`, into the candidate `main-2026-10-05`. |
| `cmd-list` | 740 | `list` of the parent of the candidates. |
| `update-compare`, `update-report`, `update-carry`, `update-launcher` | 750 to 756 | The steps of the candidate update loop: the saved report, its content, the patches and the launcher file. |
| `cmd-compare` | 760 | `compare` after an edit by hand of `settings.json` in the right side. The setup makes the edit. |
| `cmd-carry` | 770 | `carry` with one patch. The setup makes the candidate `main-trial` from a copy of the overlay. |
| `update-pass` | 780 | One pass of the loop as one command: `validate`, `generate`, `compare` and `carry`. |

Rules for a new capture of the Use pages:

- An action that needs a file of an install gets the file from `setup`: a facts file, a baseline file or a public key file.
- An action that prints command lines for another machine runs as each other action. The capture shows the printed lines. The kit runs none of them.
- The home path in an option value is `/home/alex`, and the account is `alex`. The scan refuses a home path of another user.

After order 675, the session also has this state:

- The private directory holds `hand-made-baseline.json`, `seat-key.pub` and `results-facts.json`.
- The directory `~/.llm-wiki` exists with the file `config.json`. No capture after order 655 reads it. The target of each later capture is outside it.
- The directory `hand-made` holds the file `prompts/plan.md`.

### Captures of the Develop pages

These captures exist. Each one has `"ref": "main"`, so it runs in a clone of the branch `main` of tenant-pi. That session has its own container. It does not see the state of the release session.

| Name | Order | Content |
| --- | --- | --- |
| `dev-unit-tests` | 810 | Gate 1. The setup clones `/srv/tenant-pi.git` into `/home/alex/tenant-pi` and goes into the clone. |
| `dev-examples` | 820 | Gate 2. |
| `dev-sample-overlay` | 830 | Gate 3. |
| `dev-publish-check` | 840 | Gate 4. |
| `dev-public-reader-check` | 845 | The public reader check: `publish_check.py --public`. The container has no local deny list. |
| `dev-doc-check` | 850 | The documentation check. |
| `dev-scan-selftest` | 860 | The negative control of the scanner. The setup adds `/usr/local/scanner` to `PATH`. |

`main` of tenant-pi is a private branch. The site shows no commit ID and no issue number of that branch.

- Give `"ref": "main"` only to a command whose output holds no commit ID, no issue number and no value of a host.
- For a command such as `git log`, put an example block with neutral values into the page. Do not make a capture. The block has the language `text` and the title `Example`. The line before it says "It is not a capture." The lint checks this form.
- Read the `.txt` file of each new `dev-*` capture before a commit. The scan finds a commit ID of the branch. It does not find an issue number.

### Manual captures of stages 6 to 9

The kit runs no command of stages 6 to 9, and Stage 6 needs the network. So these captures are manual. The capture script does not run them.

| Name | Order | Content | Run |
| --- | --- | --- | --- |
| `stage6-check-runtime` | 1000 | `check-runtime` before the install. `node` and `pi` are `missing`, and the exit code is 1. | Third |
| `stage6-node-nvm` | 1010 | `nvm install 24 && nvm use 24`. | Third |
| `stage6-npm-prefix` | 1020 | The test of the global npm prefix. | Third |
| `stage6-install-pi` | 1030 | The global install of the Pi pin `1.1.0`. The command reads the pin from `config/manifest.json`. | Third |
| `stage6-check-runtime-again` | 1040 | `check-runtime` after the install. | Third |
| `stage7-login` | 1100 | The Pi screen after `/login`: the `.txt` file, a recording and the image `stage7-login.png`. | Third |
| `stage7-login-result` | 1110 | The Pi screen after a login with an API key: the `.txt` file and the image `stage7-login-result.png`. It has no recording. | Second |
| `stage8-baseline` | 1190 | `baseline` of `~/.pi/agent` before the first launch. | Third |
| `stage8-launch` | 1200 | The first launch with the launcher file: the Pi screen as the `.txt` file, a recording and the image `stage8-launch.png`. | Third |
| `stage9-pi-version` | 1300 | `pi --version` with the profile. | Third |
| `stage9-prompt` | 1305 | A launch after the login, one prompt and the reply of the model: the Pi screen as the `.txt` file, a recording and the image `stage9-prompt.png`. | Second |
| `stage9-target-files` | 1310 | The target after the first launch and three more launches, with no login. | Third |
| `stage9-live-profile` | 1320 | The directory `~/.pi`. It has no live profile. | Third |
| `stage9-check-baseline` | 1325 | `check-baseline` of `~/.pi/agent` after the launches. | Third |
| `stage9-session-dir` | 1330 | The directory in `PI_CODING_AGENT_SESSION_DIR` after a launch with the launcher file and one prompt. | Second |
| `stage9-install-log` | 1340 | The install log with one entry. | Third |
| `stage9-results` | 1350 | `results`, which writes `INSTALLER_KIT_RESULTS.md`. | Third |

The column "Run" names the record below that each capture comes from.

The record of the first run on 2026-10-05, with no credential. No capture of this run stays: the second and the third run replaced each one.

| Item | Value |
| --- | --- |
| Release | `portable/20261005-592105f`, as a Git clone with the release tag |
| Client | A new container from the image `debian:12`, with Python 3.11, Git, `curl` and `vi` from Debian |
| User, home and host name | `alex`, `/home/alex`, `example` |
| Profile | Core only. Stages 1 to 5 ran first in the same container, as the pages say. |
| Node and Pi | Node 22 from nvm `0.40.3`, then Pi `1.0.2` from the npm registry |
| Credential | None. No prompt went to Pi, so Pi sent no request to a model. |
| Terminal | 80 columns and 24 rows for a command. 100 columns and 30 rows for the Pi screen. |
| Tools of the recording | asciinema records each command. tmux types the keys into Pi and reads the Pi screen. |

The record of the second run on 2026-10-05, with a credential. Its captures are `stage7-login-result`, `stage9-prompt` and `stage9-session-dir`.

| Item | Value |
| --- | --- |
| Client | A new container from the client image of the first run after Stage 6. Pi started in it for the first time. |
| Credential | An API key of the provider OpenRouter. The owner typed it into Pi by hand, with the method `Sign in with an API key`. |
| Model | `moonshotai/kimi-k2.6`. Pi selected it after the login. |
| Prompt | One prompt of one line. The status line shows a cost of 0.001 USD. |
| Captures | `stage7-login-result`, `stage9-prompt` and `stage9-session-dir`. |

- No recording and no capture exists of the screens where the owner selected the provider and typed the key.
- No command of the run read the file `auth.json`. The captures show its size only.
- The container was removed after the run, so the file with the key does not exist now.
- The captures show the name of the provider and of the model. They show no account name, no key and no balance.
- For `stage9-prompt`, the shell had `PI_CODING_AGENT_SESSION_DIR`. `stage9-session-dir` shows that the directory stayed empty after the prompt.

The record of the third run on 2026-10-08, with no credential. Its captures are each capture of the table with the value "Third".

| Item | Value |
| --- | --- |
| Release | `portable/20261008-b54a5f8`, as a Git bundle of the release tag. The container cloned it from a bare repository. |
| Client | A new container from the image `debian:12`, with Python 3.11, Git, `curl` and `vi` from Debian |
| User, home and host name | `alex`, `/home/alex`, `example` |
| Profile | Core only. Stages 1 to 5 of `docs/guides/setup.md` of the release ran first in the same container. |
| Node and Pi | Node 24.21.0 and npm 11.19.0 from nvm `0.40.3`, then Pi `1.1.0` from the npm registry |
| Credential | None. No prompt went to Pi, so Pi sent no request to a model. |
| Terminal | 80 columns and 24 rows for a command. 100 columns and 30 rows for the Pi screen. |
| Tools of the recording | asciinema 2.2.0 records each command. tmux 3.3a types the keys into Pi and reads the Pi screen. |

- The method of the third run is the method of the first run. A script of that run cuts each recording with the functions of `scripts/capture.py`, and it draws each image. The script is not in this repository.
- The image method of the third run drew the `.txt` files of the first run again. The two images were identical to the old images, byte for byte.
- The install script of nvm ran first, with no `PROFILE` setting. It added the nvm lines to `~/.bashrc`. The capture does not show it.
- After the captures, a start of Pi with `PI_CODING_AGENT_SESSION_DIR` and without `env -u` wrote nothing into that directory. A start with no prompt writes no session file. So `stage9-session-dir` stays from the second run.

These notes apply to each run:

- Redaction: no value was replaced. The container has only the neutral values, so no output holds a value of a host.
- For `stage6-install-pi`, the shell had `npm_config_progress=false` and `npm_config_update_notifier=false`. The output then has no progress display and no notice about a newer npm.
- For `stage6-node-nvm`, the install script of nvm ran first. The capture does not show it.
- A `.txt` file of a Pi screen holds the text of the screen with its colors. The recording has the real timing, and a long wait is cut to 2 seconds.
- An image shows the same text as its `.txt` file. A headless browser draws the text with the Soft Night ground color. The image holds no other data.
- The time in `stage6-install-pi`, the time `recordedAt` in `stage8-baseline` and `stage9-check-baseline`, and each file date in the `stage9-*` captures change with each run.
- A person must look at each image for a secret before a release. The scanner cannot read the text of an image.

## Use in a page

```mdx
import Capture from '@/components/Capture.astro';
import Cast from '@/components/Cast.astro';

<Capture id="tenant-pi/validate" />
<Cast id="tenant-pi/validate" />
```

`Capture` shows a static terminal frame. `Cast` shows the same frame with a button that plays the recording. A capture without a `.txt` file shows a "not recorded" note, and the build does not fail.

## The capture script

`scripts/capture.py` runs each scripted capture of one project. It writes the `.txt` and `.cast` files and the record.

```sh
scripts/capture.py --project tenant-pi --source <the path of a local clone of the project>
```

| Option | Meaning |
| --- | --- |
| `--project` | The directory below `captures/`. The default is `tenant-pi`. |
| `--source` | The path of a local clone of the project. Without the option, the script reads `TENANT_PI_SOURCE` from the environment or from the untracked `.env`. The variable name is the project name in capital letters with `_SOURCE`. |
| `--out` | Another directory for the output files and the record. Use it to compare a run with the tracked files. |
| `--timeout` | The time limit of one session in seconds. The default is 900. |

The clone must hold the tag of the documented release and each branch that a spec names in `ref`. The script reads the clone. It does not change it.

The host needs Python 3.9 or later, Git, Node and Docker. The script uses no Python package.

### What the script does

1. It runs `scripts/check-version.sh`. The run stops when the source has a newer release than `src/data/versions.json`.
2. It builds the image of `scripts/capture.Dockerfile`.
3. It puts the specs into groups: one group for the documented release, and one group for each branch that a spec names in `ref`.
4. It writes the history of the release tag, or of the branch, into a bundle file with `git bundle create`.
5. It starts one container without network access for the group.
6. It copies the bundle into the container and makes the Git repository `/srv/<project>.git` from it. The run stops when the commit in the container is not the commit in the source.
7. It runs the specs of the group in ascending `order` in one shell session. asciinema records the session.
8. It cuts the recording into the output of each capture, and it replaces each value that a rule of `replace` declares.
9. It makes one `.txt` and one `.cast` file for each capture.
10. It removes the container, also after a failure. Then it does steps 4 to 10 for the next group.
11. It checks the exit codes and scans the files.
12. It writes the files and the record.
13. It prints one line for each capture: `new`, `same`, `changed` or `FAILED` with the reason.

The source location is not in a capture, a message or a tracked file.

### A failed capture

A capture fails in each of these cases:

- A setup command fails.
- The exit code of the command is not the expected one.
- The command does not end before the time limit, or the session stops before the command.
- A rule of `replace` finds no value in the output.
- The scan has a finding in the output or in the spec.

The script writes no file for a failed capture. The old files and the old record entry of that capture do not change. The session goes on, and the script writes the other captures. Then the script exits with 1.

Warning: the old files of a failed capture can come from an older release. Correct the capture and run the script again before a commit.

### The container

| Item | Value |
| --- | --- |
| Base image | `node:24.21.0-bookworm-slim`, with `python3`, `git` and `asciinema` from Debian |
| User and home | `alex`, `/home/alex` |
| Host name | `example` |
| Network | None. Only the loopback interface exists. |
| Terminal | 80 columns, 24 rows, `TERM=xterm-256color` |
| Repository | `/srv/<project>.git`, from the release or from one branch |
| Scanner | `/usr/local/scanner/gitleaks`, version v8.28.0. The directory is not in `PATH`. |

The container holds no Pi profile, no credential and no value of the host. Each group of specs gets a new container.

The repository has this content:

| Group | Content of `/srv/<project>.git` |
| --- | --- |
| The release | The branch `main` at the commit of the release tag, the history of that commit, and the release tag. |
| A branch | The branch with its history. The branch is the `HEAD` of the repository. The repository has no tag. |

The commit of the release in the container is the commit of the release tag in the source. Thus a value such as `kitCommit` in a capture is the real release commit. A reader who clones the release gets the same value.

The scanner binary comes from the scanner image that `scripts/scan.sh` of tenant-pi pins. `SCANNER_IMAGE` in `scripts/capture.Dockerfile` holds the same name and the same digest. A clean client does not have the scanner, so only the setup of `dev-scan-selftest` adds its directory to `PATH`.

When tenant-pi pins a new scanner version, `dev-scan-selftest` fails with the exit code 2. Then set `SCANNER_IMAGE` to the new pin, and set the version in the table.

The build of the image needs the base image and the scanner image. Docker pulls an image that is absent, so the first build needs network access.

### The session

- Each group has one session. One `bash` process runs each `setup` command and each `command` of the group. A later capture sees the directory, the variables and the files of an earlier one.
- The session starts in `/home/alex` with a clean environment: `HOME`, `USER`, `LOGNAME`, `SHELL`, `PATH`, `TERM`, `LANG`, `TZ`, `PAGER` and `GIT_PAGER`.
- `PAGER` and `GIT_PAGER` are `cat`, so no command waits for a key.
- A command gets no input. Standard input is `/dev/null`.
- The output of a `setup` command goes to a log. The script prints the last lines of the log when a `setup` command fails.
- Do not use `exit` in a command. It stops the session.

The page shows `command` exactly as the script runs it. A command with a placeholder must run as written. See `stage1-clone`: its setup makes a link with the name of the placeholder, so `git clone` finds a repository.

### The output files

- `.txt` holds the output of `command` only. The `Capture` component adds the command line. The script keeps color sequences and removes other terminal sequences. For a progress line, it keeps the last state.
- `.cast` is an asciicast v2 file. It shows the prompt, the typed command and the recorded output.
- The script replaces the recorded timing with a fixed timing. A second run then gives the same `.cast` file when the output is the same.
- A value that changes from run to run needs a rule in `replace`. Without a rule, each run changes both files.

### Stable output

Some commands print a value that changes from run to run, for example a run time or the time of day. A second run then changes the files, although the project did not change. A spec declares each such value in `replace`:

```json
"replace": [
  {
    "what": "the run time of the tests",
    "match": "Ran \\d+ tests? in ([0-9.]+)s",
    "with": "<seconds>"
  }
]
```

| Field | Meaning |
| --- | --- |
| `what` | The name of the value. The record shows it. |
| `match` | A Python regular expression with exactly one group. The group is the value. The text around the group finds the correct place. |
| `with` | The placeholder that replaces the value. It starts with `<` and ends with `>`. |

With this rule, the output `Ran 363 tests in 27.268s` becomes `Ran 363 tests in <seconds>s`.

- The script replaces the value in the `.txt` file and in the `.cast` file.
- The angle brackets show a reader that the placeholder is not real output. The script refuses a `with` text without them.
- A rule that finds no value fails the capture. The form of the output changed then, and the rule needs a correction.
- The record names each rule and the number of values that it replaced.
- A page that shows such a capture names the placeholder in a sentence near the frame.

Two runs of the script, one after the other, leave `git diff captures/` empty. If a file changes, the output holds a value without a rule.

These rules exist for tenant-pi:

| Capture | Value | Placeholder |
| --- | --- | --- |
| `stage1-clone-checks`, `dev-unit-tests` | The run time of the unit tests. | `<seconds>` |
| `cmd-list` | `generatedAt` of each candidate. | `<UTC time>` |
| `cmd-baseline`, `cmd-check-baseline` | `recordedAt`: the time of the baseline. | `<UTC time>` |

`cmd-results` shows no generation time: the command stops the output before the table that holds it. A capture of the full text needs a rule for the text `Generated at`.

### The record

The script writes `captures/<project>.record.json`. The file has one entry for each scripted capture. It is beside the project directory, so no tool takes it for a spec.

```json
{
  "project": "tenant-pi",
  "captures": {
    "dev-unit-tests": {
      "ref": "main",
      "exit": 0,
      "replaced": [
        { "what": "the run time of the tests", "with": "<seconds>", "count": 1 }
      ]
    },
    "stage3-validate": {
      "ref": "portable/20260103-3c4d5e6",
      "commit": "9c0d1e2f3a4b5c6d7e8f9a0b1c2d3e4f5a6b7c8d",
      "exit": 0,
      "replaced": []
    }
  }
}
```

| Field | Meaning |
| --- | --- |
| `ref` | The release tag or the branch that the capture ran on. |
| `commit` | The commit of the release tag. Only a capture of the release has this field. |
| `exit` | The exit code of the command. |
| `replaced` | One entry for each rule of `replace`: the name of the value, the placeholder, and the number of replaced values. |

A release commit is public. A branch can be private, so the record holds no commit ID of a branch. The script prints the first characters of that commit on the terminal, for the person who runs it.

Do not edit the record by hand. A capture that fails keeps its old entry.

### The scan

A capture fails when its output or its spec holds one of these values:

- the source location, a host name, the user name or the home path of the host that runs the script
- the value of an environment variable of that host with a name such as `*_TOKEN`, `*_KEY` or `*_PASSWORD`
- a private network address
- a home path of a user other than `alex`, except a placeholder in capital letters
- for a capture with `ref`: a commit ID of that branch, with 7 characters or more

The script learns the values of the host and the commit IDs at run time. It stores none of them.

When `scripts/scan.py` exists, the script also runs it on the written files and on the record. That scanner has the rules of the repository. The script exits with 1 when the scanner has a finding. Do not commit the files then.

## Rules

- Output comes from a clean environment. It holds no host name, user name, home path, internal URL or credential.
- A scripted capture shows the neutral values of the container: the user `alex`, the host `example` and the home `/home/alex`.
- In a manual capture, replace each value of the host with the same neutral values. Page text uses placeholders such as `~/tenant-pi` and `~/.pi-candidate`.
- A capture shows no clone URL of a project. Use the placeholder `<the URL of the tenant-pi repository>`.
- One file set for each capture. Do not edit a `.txt` or `.cast` file of a scripted capture by hand. Run the capture script again.
- A value that the script replaces is a placeholder in angle brackets. The spec declares it, and the record names it.
- A capture of a branch shows no commit ID and no issue number of that branch.
- One capture is one command line. Put each step that the page does not show into `setup`.
