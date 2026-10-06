# docgen

docgen makes and maintains the doc set of one project from the git history and the files of its repository. It is built for an agent with a small model. The scripts find the facts, choose the pages, name each file to read and check the result. The agent writes one short text at a time.

Status: the templates of the profile `v1` have the page shapes of the tenant-pi pages (issue 16). The profile is final: the owner approved the tenant-pi pages and the doc set of version one on 2026-10-05 (issue 13).

## Change of the slot form

The slot form of the profile `v1` changed on 2026-10-05, before the first generated doc set (owner decision, issue 13). The name `v1` and the status `final` did not change.

- A command slot is a comment of the page. The page shows the command only in the frame of its capture.
- The Install page has eleven slots: the slots `stage-3-command` and `stage-4-command` are new.
- A stage of the Install page with no command has one sentence and no frame.

No doc set of the old form is in the repository. `check` reports such a doc set, and docgen has no code that converts it. To get the new form, a person starts a new branch. On it, the person removes the pages, the capture specs and the state file of the project. Then the skill `tenant-docs-generate` runs again.

## Parts

| Part | Path | What it is |
| --- | --- | --- |
| Script | `docgen/docgen.py` | Ten actions. Python 3 standard library and `git` only. The checks of the site also need Node.js. |
| Release rule | `docgen/release_tag.py` | The two forms of a release tag and the rule for the newest release. `scripts/check-version.sh` uses the same file. See "New release of a project" in `README.md`. |
| Profile | `docgen/profiles/v1.json` | The pages of a doc set, the condition of each page, and the patterns of its source files. |
| Templates | `docgen/profiles/v1/*.mdx` | One page skeleton for each page type, with slots: `overview`, `install`, `commands`, `command`, `workflow` and `reference`. |
| Record | `docgen/profiles/v1-pages.md` | Each page type and each section of the tenant-pi pages, and the template that gives it or the gap. |
| State | `docgen/state/<project>.json` | Tracked. For each page: its template, its ref, and the blob hash of each source file. For each capture spec that docgen wrote: its page and its source. |
| Work files | `.docgen/<project>/` | Not tracked. `facts.json`, `plan.json` and the saved help texts. They can hold values of the host. |
| Site data | `src/data/projects.json`, `src/data/versions.json` | Tracked. The project list of the site, and the release of each project. `register` writes them. |
| Skills | `skills/tenant-docs-generate`, `skills/tenant-docs-update` | The procedure for the small model, in small steps. |
| Skill | `skills/tenant-docs-diagrams` | The second pass for a large model: draw each diagram from its list of steps. |

## Actions

Run each action as `python3 <tenant-docs>/docgen/docgen.py <action>`. The directory of the script sets the site, so the command works from each project repository.

Before a skill runs, the user sets `TENANT_DOCS_DIR` to the path of the tenant-docs checkout.

| Action | Reads | Writes |
| --- | --- | --- |
| `survey --repo .` | The project repository, through `git` only. It never reads the working tree, and it writes no file there. | `.docgen/<project>/facts.json` |
| `branch --project P` | The branches of the site and its remote `origin`. | The branch of the run in the site checkout. See "The branch of a run". |
| `plan --project P` | The facts and the profile. | `.docgen/<project>/plan.json` |
| `scaffold --project P` | The plan, the templates and the pages. | New pages under `src/content/docs/P/`, one capture spec `captures/P/<name>.json` for each command slot, and the state. |
| `next --project P` | The pages. | Nothing. It prints the next open slot with the rules of its form. A fault in a written slot comes first. |
| `check --project P` | The pages, the state, the capture specs and the facts. Through `git`: the source files of each page in the project repository of the last survey. | Nothing. It prints the findings and exits with 1 if there is one. A note is no finding. |
| `diagrams --project P` | The pages. | Nothing. It prints the diagrams that wait for the second pass. |
| `status --project P` | The state, the pages and the project repository. | Nothing. It prints each stale item with its command, and exits with 1 if there is one. See "The list of `status`". |
| `register --project P` | The state, the overview page and the site data. | `src/data/projects.json` and `src/data/versions.json`, only when a value changes. With `--release`, also the release of the state. |
| `commit --project P` | The state and the site checkout. | One commit with the files of the doc set, and the push of the branch of the run. See "The commit of a run". |

`survey --run-help` also runs `--help` of each Python command line of the project and saves the text. The code runs in a throwaway container with no network, a read-only export of the release ref, a neutral user, host name and home path. Code of the project never runs on the host, and the saved text can hold no value of the host. It needs Docker. `DOCGEN_HELP_IMAGE` sets the image (default `python:3.12-slim`).

`check` has two parts. First it checks the pages of the project: see "Checks of `check`". When the pages have no finding, it runs the checks of the site: see "Checks of the site".

## The commands that the script prints

The shell tool of an agent starts a new shell for each command, in the project repository. A shell variable and a `cd` of an earlier command are gone. So the script prints each command in a complete form.

- Each command that the script prints is one line: `python3 <the absolute path of docgen.py> <action> --project P`. It runs from each directory and needs no variable. The script quotes a path for the shell when the path needs it.
- Each action that has a step after it ends with one line that starts with `next`. The text after the word `next` is the command of that step.
- A fix text of `check`, a line of `status` and a note use the same complete form.
- `next`, `check`, `diagrams` and `status` print the absolute path of each file that the agent opens.

The `next` lines follow the steps of the skills. No two actions name each other in a circle.

| Action | Its `next` line names |
| --- | --- |
| `survey` | `branch`. After `survey --update`: `branch --update`. The first command of a skill says which run it is. |
| `branch` | `plan`. |
| `plan` | `scaffold`. On the branch of an update: `status`. |
| `scaffold` | `next` while a slot is open. If not: `register`. In an update, `status` comes first: after `scaffold --refresh`, and on the branch of an update. |
| `next` | `next` again, after the agent writes or corrects the slot. With no open slot: `scaffold`. |
| `register` | `check`. On the branch of an update, with `--release`: `status`. With no state of the project, it prints a `note` and no `next` line. |
| `check` | `commit`, only when each check passes. |
| `status` | `register`, when the list has no stale item and a file of the doc set waits for a commit. With no such file, it prints "Nothing to do." and no `next` line. With a stale item, it prints the command for each item and no `next` line. |
| `commit` | Nothing. Its last line starts with `done`: the agent tells the user the result. |

`diagrams` prints the `check` command and the `commit --diagrams` command below its list.

The order of a first doc set: `survey`, `branch`, `plan`, `scaffold`, `next` for each slot, `scaffold`, `register`, `check`, `commit`.

The order of an update: `survey --update`, `branch --update`, `plan`, `status`, then the command of each stale item and `status` again, then `register`, `check`, `commit`. `plan` comes before `status`, so the plan is as new as the facts when a page gets its record.

## An action that stops

An action that stops before its work prints one line that starts with `error:`, and its exit code is 2. The line says what is wrong and what to do. No state of this table ends with a trace of the program.

| The line ends with | Meaning |
| --- | --- |
| `Run first:` and one complete command | A step before this one did not run, or its result is old. The agent runs that command, then the command that stopped. |
| `Run the survey again in the project repository: it is the first command of the skill.` | The facts of the survey are absent or not valid, or the checkout does not know the project repository. The line holds the words `run survey first`. The script cannot print this command for each case: the survey starts in the project repository. |
| `Stop and tell the user this line.` | The agent cannot correct the cause. |

| State | The line |
| --- | --- |
| `.docgen/<project>/facts.json` is absent or is not valid JSON | `the facts of '<project>' (run survey first) ...` |
| `.docgen/<project>/plan.json` is absent or is not valid JSON | `the plan of '<project>' ... Run first:` with the `plan` command. |
| `docgen/state/<project>.json` is not valid JSON, for example with conflict marks of Git | `the state of '<project>' is not valid JSON ... Do not edit it. Stop and tell the user this line.` An agent cannot merge this file. |
| `docgen/state/<project>.json` is valid JSON with another form: no object with the key `pages`, or a page record with no `ref`, `tree`, `template` or `sources` | `the state of '<project>' does not have the form of a state ...`, with the fault and the same end. |
| `docgen/state/<project>.json` names a file outside the doc set. This is a page name with a part `..` or a `/` at its start. It is also a capture name that is no name of a capture mark. | The same line. `commit` stages each file that the state names, and `scaffold` removes a capture spec by its name. So no action reads such a state. |
| `--project` gets a text that is no project name, for example the word `PROJECT` of a code block of a skill | `branch`, `status`, `diagrams` and `commit`: `'<text>' is not a project name of the site`, and where the agent finds the name. `register` and `survey` have their own line with the same first words. |
| `src/data/projects.json` or `src/data/versions.json` is not valid JSON | `... is not valid JSON ... Stop and tell the user this line.` |
| A capture spec that the state lists is not valid JSON | `scaffold` stops with `the capture spec ... is not valid JSON`. |
| `status` with no `--repo`, in a checkout with no work files of a survey | `the project repository of '<project>' (run survey first) is not known ...` |
| `--repo` names a directory that is absent, or that is in no Git repository | One line that names the directory. |
| `survey --run-help`, and the program `docker` is absent or its server does not answer | `--run-help needs Docker ...`, with the complete `survey` command that has no `--run-help`. |

`scaffold` makes each of its stops before its first write. A run that stops leaves each file as it was.

## The branch of a run: `branch`

A generated doc set goes to a branch of its own in the site. The owner reviews that branch and merges it. `branch` prepares the branch, and a second run changes nothing.

| Run | Branch |
| --- | --- |
| A first doc set: `branch --project P` | `topic/docgen-P` |
| An update: `branch --project P --update` | `topic/docgen-update-P` |

1. `branch` fetches from the remote `origin` when the site has that remote.
2. The base is `origin/main`. In a site with no remote, the base is the local `main`.
3. `branch` then does one of these things and prints one line for it.

| Line | The state | What `branch` does |
| --- | --- | --- |
| `started` | No such branch exists. | It makes the branch at the base and changes to it. |
| `resumed` | The branch exists in the checkout or on `origin`. | It changes to the branch. A branch that is only on `origin` gets a local branch that follows it. |
| `kept` | The checkout is on the branch. | Nothing. The open changes of a run that stopped stay. |
| `moved` | An update, the branch exists, and each of its commits is in the base. | It moves the branch to the base with a fast-forward. |
| `note` | The branch does not hold each commit of the base. | Nothing. The scripts of the checkout can be old. The agent puts the line into its report. |

`branch` stops with the exit code 2 and one line, and changes nothing, in these cases:

- The checkout is not on the branch of the run, and it has a change of a tracked file that is not committed. The same is true for an untracked file below `src/content/docs/P/`, `captures/P/` or `docgen/state/`. The line names the files.
- A first doc set, and the base holds `docgen/state/P.json`. The doc set is in `main`. The line says what each skill does. `tenant-docs-generate` stops. `tenant-docs-update` and `tenant-docs-diagrams` run the `branch --update` command at the end of the line.
- An update, and the base does not hold `docgen/state/P.json`. The line says that the doc set is not in `main`. When the branch `topic/docgen-P` holds it, the line says that the doc set waits for the review.
- The same, and the project list of the site has no project `P`. The line says so and lists the names of the list. A clone in a directory with another name gives such a name. The agent does not choose a name.
- Git cannot fetch from `origin`. The line holds the cause that Git gives.

A stop that comes from Git holds the cause, and not the last line of Git. The cause is the first line of Git that starts with `fatal:` or `error:`. A cause that ends with `:` gets the file names of the lines after it. A line that starts with `hint:` is never the cause. For a remote over SSH, that first line is the general line `Could not read from remote repository`. The line of SSH before it names the cause, for example `Connection refused`. The stop then holds the line of SSH first, and the general line after it.

`branch`, `commit` and the guard of `main` read the full name of the ref that is checked out. So a tag with the name of a branch does not hide that branch.

A clone of one branch (`git clone --single-branch`) fetches that branch only. `branch` then asks `origin` for the branch of the run by its name. So it finds a branch that a second machine pushed, and it does not start a second branch with the same name. The local branch then gets its upstream at the push of `commit`.

`branch` never deletes a branch, never resets a branch and never uses force.

Git never asks for a name or a password in `branch` and in `commit`: an agent cannot answer. A fetch or a push that needs an answer fails with a message of Git.

### The guard of `main`

`scaffold` and `register` write tracked files. Both stop with the exit code 2 in a Git checkout of the site that is on the branch `main`. They stop also in a checkout with a detached HEAD. The line names the `branch` command to run first. In a directory that is no Git repository, the guard does nothing. The tests of docgen use such a directory.

## The commit of a run: `commit`

`commit --project P` makes one commit on the branch of the run and pushes that branch. It works only on `topic/docgen-P` and on `topic/docgen-update-P`. On another branch it stops with the exit code 2 and names the `branch` command.

- It stages only the files of the doc set: each page and each capture spec that the state lists, `docgen/state/P.json`, `src/data/projects.json` and `src/data/versions.json`. It prints `staged` for each file of the commit.
- A capture spec that `scaffold` removed after the last commit is a part of the commit, as a removed file. This is true also when the same commit adds a spec with a near text. `commit` does not let Git read the two files as one file with a new name.
- It never stages each file of a directory. For another changed or untracked file below `src/content/docs/P/` or `captures/P/`, it prints `skipped ... docgen did not write it`. A file that a person staged stays staged and is not in the commit.
- It stops with the exit code 2 when the state lists a file that is absent. The line names the `scaffold` command, which writes the file again.
- With nothing to commit, it prints `kept` and makes no commit.
- Then it pushes the branch with `git push --set-upstream origin <branch>`. It pushes no other branch and no tag. `--no-push` leaves the push out.
- It prints `pushed` or `kept` from the result line that Git prints for the push. So the line is true also in a clone that has no remote-tracking ref for the branch.

| Branch and option | Commit message |
| --- | --- |
| `topic/docgen-P` | `Docs of P: first doc set from docgen` |
| `topic/docgen-update-P`, and the release of the state changed | `Docs of P: update to <release>` |
| `topic/docgen-update-P`, and the release is the same | `Docs of P: update` |
| `--diagrams` | `Docs of P: diagrams` |

The exit code is 1 when a part of the work is not done:

- A Git hook refuses the commit. `commit` prints the last 20 lines of the hook. When the pre-commit hook of the site prints its summary, the last line names the checks that fail, the `check` command and the `commit` command.
- Git does not push the branch. The commit stays in the local branch. A second run pushes it.
- The site has no remote `origin`.

`commit` does not run the checks of the pages. Run `check` before it. The pre-commit hook of the site runs the checks of the site again.

## The project list: `register`

The site shows a project when `src/data/projects.json` lists it. `register` adds the project `P` to that list. It also sets the release of `P` in `src/data/versions.json`. No person edits `astro.config.mjs`: the sidebar of a project comes from its directory `src/content/docs/P/`.

| Value | Option | Default |
| --- | --- | --- |
| The size of the doc set, `full` or `overview` | `--docs` | The doc set of the last `scaffold`. |
| The name that the site shows | `--name` | The project name. |
| One short sentence for the home page and the project menu | `--summary` | The description of the overview page `index.mdx`. |
| The release that the pages describe | `--release` | The release of the last `scaffold`. |
| The branch of that release | `--branch` | The release ref of the last `scaffold`. |

- A new project goes to the end of the list.
- A project in the list keeps its place, its name and its summary. Its doc set changes from `overview` to `full` when the state has a full doc set.
- `register` never changes a full doc set to an overview.
- With no state of a `scaffold`, give `--docs`. For a full doc set, give also `--release` and `--branch`.
- `register` stops for a full doc set when the release is not a release tag of the branch. Each release gets a tag, and a commit is not a release. A project with no release tag has a commit as its release, so `register` stops for it. The message names the two forms of a tag. The agent makes no tag: it stops and tells the user.
- `plan` stops with the same message for a full doc set of such a project. So the run stops before the agent writes a slot. `plan --doc-set overview` does not stop.
- For a project with an overview only, `register` keeps the release of the survey, also when it is a commit. `survey` prints a note in this case.
- `register` stops when the project has no overview page, or when the size of the doc set is not known. It stops also when a full doc set has no release. Each of these lines ends with `Run first:` and the complete `scaffold` command.
- `register` stops when the name, the summary, the release or the branch holds a value of one host.
- A second run with the same input changes no file.
- With `--release` or `--branch`, and a state of the project: `register` writes that release into the state too, and prints `recorded`. So `status`, `check` and `commit` read the same release. `status` prints this command for a new release.
- When the release of a project changes from one release to another, `register` prints a `note`: the capture script must run for the new release. The frames of the pages show the output of the release before. The agent puts the line into its report.
- With nothing to change, `register` prints `kept`. The line says "its release is current" only when the site has a release of the project.
- With no state of the project, `register` prints a `note` in place of its `next` line: `check` reads the state, so it cannot run. The note gives the `scaffold` command of a run of docgen.

`register` does not change the home page. The text and the diagram of `src/content/docs/index.mdx` name each project. For a new project and for a project that gets a full doc set, `register` prints a `note` about it. The note tells the agent not to change the home page, and to put the line into its report.

Run `register` after `scaffold` and before the last `check`. When the list is not current, `check` prints the finding `not-registered` with this fix.

## Checks of the site

`check` does not copy a check of the site. It runs `scripts/check.sh` in the site directory and reads its summary. The script runs the tests, the build, the link check, the scanner and the Simplified English lint.

The scanner runs two times. The checks of the pages give the files of the doc set to it by their paths: see "Values of one host". Then `scripts/check.sh` runs it on each tracked file, on `captures/` and on the built site.

- `check` prints one line for each check of the site: `site`, the name of the check and the result.
- Below a check that fails, it prints the last 30 lines of the output of that check. These lines hold the findings. A check of the site prints a path that is relative to the site. `check` prints the absolute path of each such file that exists. A line of a check of the site can have no fix text.
- The tests run through `scripts/run_tests.py`. That script prints the output of each test file that fails last, and then a short list of the failed tests. So the last 30 lines of the tests hold the failed test.
- A failed build prints its cause first and a long text after it. So `check` prints, above the last 30 lines, each earlier line that holds `[ERROR]`, and the place that a `Location:` line gives. It prints eight such lines at most.
- For a check with more than 30 lines, one line gives the number of lines before these. It also gives the complete command that prints each line: `sh <the absolute path of scripts/check.sh>`.
- The last line names each check that fails, for example `check failed: links, lint.`, and gives the `check` command again. The exit code is 1.
- When each check passes, the last line starts with `next` and gives the `commit` command.
- The exit code is 2 when `scripts/check.sh` cannot run, for example when `node_modules` is absent.
- The checks of the site do not run while a page has a finding, or while the project list is not current.
- In a directory with no `astro.config.mjs`, `check` runs only the checks of the pages. The tests of docgen use such a directory.

## Diagrams: two passes

The small model does not draw. A template marks each diagram with a `docgen:diagram ... | pending | ...` comment, and a slot asks the small model for a numbered list of the steps. `docgen.py diagrams --project P` lists the pending diagrams. A large model draws each one from its list with the skill `tenant-docs-diagrams`, and sets the comment to `done`. The list stays on the page as the text alternative. `check` prints a pending diagram as a note, not as a finding.

## Review

`commit` pushes the branch `topic/docgen-<project>`, and the agent stops. The owner reviews and merges. No generated doc set goes to `main` without that review. An update goes the same way on the branch `topic/docgen-update-<project>`, and it needs the doc set in `main`.

## What the survey finds

- The release ref (`portable` if it exists, else the develop ref) and the newest release tag of that branch. A tag of another form, for example `portable-validated`, is not a release. With no release tag, the release is a commit, and `survey` prints a note: the capture script needs a tag.
- The develop ref: `main`, else `master`, else the current branch. For it: the number of commits, and the first-parent merges with the topic branch and the issue number of each.
- For each ref: the README outline, the documentation files with their headings and the manifests.
- For each ref: the entry points. These are the Python command lines with their actions, the shell scripts, the npm scripts and the Compose services.
- For each ref: the test commands and the workflow files. These are the hooks, the CI files, the release scripts, the scanner and the process documents.
- `survey` writes only the untracked work files. So it runs before the branch of the run exists, and it prints the project name that each later command needs.
- `--repo` takes a path inside the project repository. `survey` and `status` find the top directory, so a start in a sub-directory gives the same result.
- `survey` removes the help texts of an earlier survey. Only `--run-help` writes them again. So `next` and `check` never read a help text of an older release.

The pages read the newest commit of the release branch, and the release has the name of the newest release tag. When the branch has commits after that tag, `survey` and `status` print a `note` with the number of commits. The owner decides if the pages read the tag or the branch.

### The project repository stays as it is

No Git command of docgen writes into the project repository. `survey` runs no command that reads the working tree. Each Git command runs with `GIT_OPTIONAL_LOCKS=0`, so Git does not write the index again after a read. The commands that the script prints for the agent read objects only: `git show <ref>:<file>` and `git diff <blob> <blob>`.

### The project name

The project name is the name of the directory of the repository. The option `--project` gives another name.

- `survey` stops when the repository is the tenant-docs repository itself.
- `survey` stops for a name that is not a project name of the site. A name has lowercase letters, digits and `-`, and it starts and ends with a letter or a digit.
- `survey` prints a `note` when the project list `src/data/projects.json` does not have the name. The note says that `register` adds a new project with this name, and it lists the names of the list. A clone in a directory with another name, and a linked working tree, give such a name. It is no stop.
- `survey --update` prints another `note` for such a name. An update makes no new project, so the note says that an update needs a name of the list. It gives the complete `survey` command with `--project PROJECT`, and it tells the agent not to choose a name. `branch --update` then stops for the name.

### The develop ref

A project with no `main` and no `master` has the branch that is checked out as its develop ref. So the result depends on the checkout of the project.

- `survey` prints a `note` that names the branch and the option `--develop-ref`.
- With a detached HEAD, `survey` stops. The agent does not choose a branch: it tells the user.
- When a doc set exists, its pages keep their branch. `plan` and `scaffold` stop when the last survey read another branch than the pages of the state describe. Without this stop, an update writes the other branch into the state, or it loses the Develop page.
- For a doc set that is in `main`, the owner reviewed the branch of the pages. The line then ends with `Run first:` and the complete `survey` command with `--develop-ref` or `--release-ref` and that branch.
- For a doc set that is not in `main`, the agent does not choose between the two branches. The line names the option and tells the agent to stop.

## Pages of a doc set

The profile lists the pages. `plan` keeps a page when its condition is true for the project.

| Page | Template | Condition | Who writes it |
| --- | --- | --- | --- |
| `index.mdx` | `overview` | Always. | The agent, six slots. |
| `install/index.mdx` | `install` | A source file for the install exists. | The agent, eleven slots. The script writes stage 1. |
| `use/commands/index.mdx` | `commands` | The project has an entry point. | The agent, three or four slots. |
| `use/commands/<action>.mdx` | `command` | One page for each action of the command line of the project. | The agent, eight slots. |
| `develop/workflow.mdx` | `workflow` | The history has five commits or more. | The agent, six slots. |
| `reference/index.mdx` | `reference` | Always. | The script. |

The page `reference/index.mdx` lists the documentation files of the survey: each Markdown file at the top of the project and below `docs/`. Only these files are its sources. A pattern of the profile can find a Markdown file in another directory. That file is no source of the page, so its change does not make the page stale.

The command line of the project is the Python command line with the most actions. A workflow file, for example a scanner or a release script, is not the command line of the project. A project with no such command line has no action page.

The doc set `overview` (`plan --doc-set overview`) has the page `index.mdx` only.

A page of the release branch shows its release with `DocVersion`. The build of such a page needs the release of the project in `src/data/versions.json`. `scaffold` prints a note when the release is absent.

`docgen/profiles/v1-pages.md` compares these pages with the tenant-pi pages.

## Slots

A template marks each text that the agent writes:

```mdx
{/* docgen:slot what-it-is | 30-90 words | text | Say what the project is and what it does. */}
TODO(docgen:what-it-is)
{/* docgen:end */}
```

The agent replaces the `TODO` line and keeps the two comment lines. The comments do not show on the page. `check` reports an open slot, a slot of a wrong form and a slot outside its word range.

The third field is the form of the slot. Without it, the form is `text`.

| Form | The agent writes | `next` and `check` report a fault when |
| --- | --- | --- |
| `text` | Plain sentences. | The slot has a table. |
| `list` | A list with `- ` before each item. | A line is not an item. |
| `numbered` | A numbered list with one line for each item. | A line is not an item. |
| `table` | One Markdown table. | The slot is not one table with a rule line and one row or more. |
| `steps` | A numbered list of nine steps at most. Each step has a sentence, a command in a code block and a `Result:` line. A step with no command in the sources has no code block. | A line of a step has less than three spaces before it, or the list has more than nine steps. Or the end line of the slot does not have the blanks of its template. |
| `command` | One command line between the lines `{/* docgen:command` and `*/}`, with no code block. | The slot has more than one command line, a code block or the characters `*/`. The command is in backticks, or it holds a placeholder in angle brackets. One of the two lines is absent, or the slot has one of them two times. |

`next` prints the rules of the form with each slot. `next` and `check` use the same form check: `check` prints each fault as a finding of the rule `slot-form`. They also report these faults in each form:

- A `<` or a `{` outside backticks. Such a character stops the build of an MDX page.
- A line that starts with `{/* docgen` inside the text of a slot. The problem line tells the agent to remove the line. In backticks, such a line passes the build and the page shows the instruction of the script.
- The same line with backticks at its two ends, when it holds the name of the slot. The problem line tells the agent to remove the line. A docgen comment in backticks inside a sentence is text of the page, and it passes.
- A heading.
- A text that does not start with the words that the instruction gives after "starts with".
- A sentence for "no answer" that is not the exact `write:` sentence of the slot. See below.
- A first line of the slot that does not have the word range and the form of its template. The problem line gives both values.

`next` also reports a value of one host in a written slot as a `problem`. See "Values of one host".

An instruction can end with `write: <sentence>`. That sentence is the text for the case that the files have no answer for the full slot. It passes each form check. In a `command` slot, the two lines around the sentence stay.

The form check reports a sentence that is near to the `write:` sentence and not equal to it: a changed word, a changed letter, no last point, backticks around it. It reports also the general sentence `The sources do not state this.` as the text of a full slot that has a `write:` sentence. The problem line gives the exact sentence to write, and no fault of the form. In a `command` slot, each sentence that starts with `The sources`, `The README`, `The repository`, `The files` or `The project` counts: no command starts with these words. These short texts count too, with each case of the letters and with a point at the end: `n/a`, `na`, `none`, `not stated`, `no command`, `no test`, `unknown`, `tbd` and `-`. Without this rule, the capture spec gets such a text as its command. For a `command` slot with no `write:` sentence, the problem line tells the agent to stop.

In a slot of another form, a text with another number of sentences than the `write:` sentence is no near copy. Such a text is the answer for one part: one fact that the files do not state, and one fact that they state.

A placeholder in angle brackets is a text such as `<your host>`. Two redirects with no blank between them are no placeholder: `sort <in.txt>out.txt`. There the text in the brackets has no blank and has a point or a `/`, and a file name follows the `>` directly.

The end line of a `steps` slot can have three blanks before it: it is then a part of the last step, and the step with the frame comes after it in the same list. With other blanks than the template has, the list ends at the wrong place and the build of the site stops. So the form check compares the blanks of that line with the template.

### A part with no answer

The files can have an answer for a part of a slot only. The slot then keeps its form, and only that part says so. `next` prints these rules in the lines `no answer`, below the length of the slot.

| Form | The part | The agent writes in that part |
| --- | --- | --- |
| `table` | One cell. | `The sources do not state this.` When the instruction gives its own words for a cell, for example `Write "Not stated" in a cell when`, the agent writes those words. |
| `list`, `numbered` | One item. | `The sources do not state this.` |
| `steps` | The `Result:` line of one step. | `Result: The sources do not state this.` |
| `text` | One fact. | One sentence that starts with `The sources do not state`. |

- A slot of one sentence and a `command` slot have one part. They have no rule for a part.
- When the files have no answer for the full slot, the agent writes the `write:` sentence of the instruction, and no other text.
- When the instruction has no `write:` sentence, the agent stops and tells the user the page and the slot. Twelve slots of the profile `v1` have none.
- The checks do not accept `The sources do not state this.` as the text of a full slot. The form check and the length check of a slot stay as they are.

A `command` slot is a comment of the page:

```mdx
{/* docgen:slot example-command | 1-60 words | command | Give one complete command line. */}
{/* docgen:command
TODO(docgen:example-command)
*/}
{/* docgen:end */}
```

The page does not show the command at that place. The frame of the capture shows it. In a `command` slot, the `write:` sentence is no command. See "A stage with no command".

## A stage with no command

No source, no frame. A project can have no command that starts it, or no test of the install. The agent then writes the `write:` sentence of the slot `stage-3-command` or `stage-4-command`. The next `scaffold` changes the stage: it has one sentence that says so. It has no step with a frame, no capture spec and no text about a frame.

A template marks each part of a page that depends on a command slot:

```mdx
{/* docgen:with stage-3-command */}
The frame of the last step shows its command in a clean container.
{/* docgen:end-with */}
{/* docgen:without stage-3-command */}
The sources state no command that starts the project.
{/* docgen:end-without */}
```

- The page has a `with` part while the slot is open or holds a command. It has a `without` part while the slot holds its `write:` sentence. The other part is empty: the two marker lines stay, with no line between them.
- The slot `stage-4-command` can hold its `write:` sentence while the facts of the survey hold a test command. The script does not know what such a command tests: the unit tests of a project are no test of its install. `check` then prints the note `unused-fact`, and the sentence passes. See "Notes of `check`".
- `scaffold` sets each part of a page that it wrote. The lines of a part come from the template. It prints `updated` for a page that it changes. A second run changes no file.
- `scaffold` removes the capture spec of a frame that the page lost, and prints `removed`. It removes only a spec that it wrote.
- When the slot gets a command later, the next `scaffold` puts the step, the frame and the spec back.
- `check` prints the finding `stale-part` when a part does not agree with its slot. The fix is one more run of `scaffold`.
- A part ends at its own end line only. A part with no end line is not complete: an agent removed the marker. The lines after it are lines of the page, for example the slots of the next stage.
- `scaffold` does not change a part that is not complete. It prints `skipped` with the name of the absent marker. `check` prints no `stale-part` for such a part: `docgen-line` gives the exact marker line to put back.

## Command slots

A command slot is a place in a page that shows one command and its real output. The template marks it with a capture mark above a `Capture` component:

```mdx
{/* docgen:capture help | 150 | The help text of the command line | run python3 scripts/cli.py --help */}
<Capture id="demo/help" />
```

The fields are the name of the capture and its order in the capture run. Then come the title of the terminal frame and the source of the command.

| Source | The command | The spec that `scaffold` writes |
| --- | --- | --- |
| `clone` | `git clone` with the placeholder `<the URL of the P repository>`. | A scripted spec. Its setup makes a link with the name of the placeholder. |
| `run <command>` | A command that the script knows from the facts: a help text or the tests. | A scripted spec. Its setup goes to the clone `"$HOME/P"`. |
| `slot <id>` | The command that the agent writes into the slot `<id>`. The slot must have the form `command`. When the slot holds its `write:` sentence, the page loses the frame and `scaffold` removes the spec. | While the slot is open: a spec with an empty command and `"mode": "manual"`, so the capture script skips it. A later `scaffold` copies the command into the spec and sets `"mode": "scripted"`. |

- The frame of a capture is the one place of its command on a page (issue 19). A step with a capture holds the frame and no code block for the same command. In a list of steps, the capture mark and the `Capture` component have three spaces before them.
- A `steps` slot gives no command to a capture, because its code blocks show on the page. In stages 3 and 4 of the install page, the `steps` slot holds the steps before the last command. The script writes the last step with the frame, and a `command` slot holds its command.
- `check` prints the finding `command-twice` when a code block of a page holds the command of a capture of that page. One line gets one finding, which names each such capture. The fix depends on who wrote the code block. For a code block in a slot, the agent removes that step. For a code block of the script, the agent writes another command into the command slot. Each fix names the sentence for the case that nothing stays.
- For this comparison, the blanks of both commands are made equal. A line that ends with a backslash is one command with its next line. A `$ ` prompt is no part of a command. `check` does not read inline code for this rule. A code block in a `command` slot is a fault of the form of that slot, and it gives no `command-twice` finding.
- `scaffold` writes one spec `captures/P/<name>.json` for each capture mark. `captures/README.md` describes the spec.
- The page is the source of a command. The agent does not edit a spec.
- `scaffold` changes only the field `command` of a spec that exists. A person can change `setup`, `exit` and `mode`.
- `scaffold` keeps a spec that it did not write.
- `check` prints the finding `stale-spec` when the spec of a `slot` capture does not hold the command of its slot. It prints the finding also when that spec is absent. The frame then shows another command than the page holds. The fix is one more run of `scaffold`.
- This part of the rule reads only a spec that the state lists: a spec of a person gives no finding. A spec that is not valid JSON gives no finding of this rule. `scaffold` cannot read such a file, and the tests and the build of the site report it.
- `check` prints `stale-spec` also for a capture mark of the template that has no spec, while the state does not list its capture. A page gets such a mark after the last `scaffold`: an agent puts back a line that `docgen-line` names. Without the finding, the commit holds a frame with no spec. A mark that the template does not give has no such finding: `docgen-line` reports it.
- `scripts/capture.py --project P` records the output. A capture with no output shows a "not recorded" frame, and the build does not fail.

| Capture | Order | Page |
| --- | --- | --- |
| `stage1-clone` | 100 | Install, stage 1. |
| `help` | 150 | Command summary. |
| `help-<action>` | 152, 154 and so on | The page of the action. |
| `stage3-start`, `stage4-check` | 300, 400 | Install, stages 3 and 4. |
| `cmd-<action>` | 600, 610 and so on | The page of the action. |
| `dev-tests` | 800 | Development workflow. |

## Templates

A template is an MDX page with slots, capture marks and names in two braces. `scaffold` replaces each name with a fact.

| Name | Value |
| --- | --- |
| `{{project}}`, `{{ref}}`, `{{release}}` | The project, the ref of the page and the name of the release. |
| `{{summary}}` | The first sentence of the README summary, when it has 25 words at most. If not, a fixed sentence. |
| `{{sources}}` | The source files of the page. |
| `{{cli}}`, `{{cli_path}}` | The start of the command line, for example `python3 scripts/cli.py`, and its path. |
| `{{action}}`, `{{order}}`, `{{help_order}}`, `{{cmd_order}}` | The action of an action page, its place in the sidebar and the order of its two captures. |
| `{{action_links}}`, `{{command_list}}` | The links to the action pages, and each command of the survey. |
| `{{test_command}}` | The first test command of the survey. |
| `{{where_next}}`, `{{site_pages}}` | The cards and the links to the other planned pages. |
| `{{docs_sections}}`, `{{troubleshooting}}` | The tables of the documentation files, and the path of the troubleshooting guide. |

A block between a line `{{#if name}}` and a line `{{/if}}` stays only when the value of `name` is not empty. A block cannot hold another block.

A page entry of the profile can have these fields:

| Field | Meaning |
| --- | --- |
| `each` | `"action"`: one page for each action. The path and the source patterns can hold `{action}`. |
| `max_pages` | The largest number of such pages. The default is 20. |
| `nav` | The title and the text of the card that other pages show for this page. |
| `sources` | Patterns of source files. `@cli` is the command line, `@entry_points` is each command line and script, `@process_docs` is each workflow file. |

## Rules of the design

1. A script finds each fact. The agent writes sentences, and takes each command and path from a named file.
2. One slot for each step. Each slot names its files, its form, its length and what to write when the files have no answer.
3. Each finding of a check is one line with the file, the line, the rule and the fix. Each command that a script prints is complete: it runs in a new shell and from each directory.
4. Each decision has a default. The agent chooses nothing about the structure.
5. Each action is safe to run again. `scaffold` never overwrites a page with content. It replaces only a skeleton stub that holds the `Planned` note, and a page that a script writes in full. A stub is a page that the state does not list. It has the `Planned` component on a line of its own. A page that docgen wrote is never a stub. For a page of the script with the same text, `scaffold` prints `kept` and writes no file.
6. No source, no page. A page whose condition is not met is skipped, not invented.
7. Each page records the hash of each source file. A page is stale when a hash differs. An update changes only stale pages.

## What `next` prints for the files to read

Each slot of a page names the same source files. `next` prints them below `read first`.

- Each file has its name and its size: the number of lines, and the bytes or kilobytes.
- A small file has one read command: `git -C <repository> show <ref>:<file>`.
- A large file has one command for each part: the same command with `| sed -n <first>,<last>p`. A part has 20 000 bytes and 400 lines at most. The shell tool of an agent cuts a longer output. One tool keeps the last 2000 lines or 50 KB, and another tool shows the first 30 000 characters.
- For the second and each later slot of a page, `next` says that the files are the same as for the slot before. The agent reads a file again only when it does not have its text.
- For the Install page, the facts name each Compose file with its services, one line for each file. A line says so when the file is no source of the page.

## The list of `status`

`status` compares the state with the project repository. It prints one item for each thing that the update must do, and the complete command of that item. The last line of the list is `N stale item(s)`. The exit code is 1 while `N` is not 0.

| First word | The item | Its lines |
| --- | --- | --- |
| `release` | The project has a newer release tag than the state records. It comes first. | `Set the new release:` with the complete `register --release ... --branch ...` command, and `For the user:` with the sentence that the capture script must run for the new release. |
| `stale` | A source file of the page has another blob than the state records. | The absolute path of the page, one line for each changed file, and `After you correct the page:` with the `scaffold --refresh <page>` command. |
| `stale`, a page that the script writes in full | The same. | `The script writes this page. Do not edit it.`, the changed files, and `Write the page again:` with the `scaffold --refresh <page>` command. It has no command that shows a change. |
| `open` | No source file changed, and the page has a slot with no text. | The absolute path of the page and `Write each open slot first:` with the `next` command. A stale page with an open slot has this line too. |
| `current` | Nothing to do for the page. | None. |
| `note` | The release branch has commits after its newest release tag. It is no stale item. | One line. |

One line for each changed source file:

| Line | Meaning |
| --- | --- |
| `<file> changed. Read the change:` | The next line is `git -C <repository> diff <old blob> <new blob>`. Two blobs give the changed lines, and no line about the mode of the file. |
| `<file> changed. The project repository does not hold the old text of this file.` | The clone has a part of the history only. The next line is the command that prints the file as it is now. |
| `<file> was renamed to <new path>.` | The file is not at its path, and one other file of the ref holds the same text. With two such files, the line says `was removed`. |
| `<file> was removed` | The file is not at the ref. |

- After `register --release`, the state records the new release, and `status` does not list the release again. `scaffold` also records the release of the facts.
- `scaffold --refresh <page>` records the sources of the plan for the page. For a page of the script, it writes the page again, or prints `recorded` when the text is the same. Each run of `scaffold` records the pages of the script, so such a page can be current after the command of another page.
- `status` stops with the exit code 2, before its list, when the project repository does not have the release tag that the pages describe. It stops also when the repository does not have a branch that a page describes. The repository is then older than the pages. The line tells the agent to stop.

### The stops of `scaffold --refresh`

| State | The line |
| --- | --- |
| The value is no page of the state, or it is empty | `'<value>' is no page of the doc set`, with the pages of the state: these are the pages that `status` lists. The value can have each form in which the script prints a page: `install/index.mdx`, the path from the site directory, or the absolute path. A page that a person wrote is a page of the plan and no page of the state: `--refresh` records nothing for it. |
| The state lists the page, and the plan does not have it | `the plan ... does not have the page`. The project has no source file for the page now. The agent does not delete the page: it tells the user. |
| A source file of the page changed after `plan` ran, and the facts are current | `the plan ... is older than the facts of the last survey ... Run first:` with the `plan` command. |
| A source file of the page changed after the survey | `the facts ... are older than the project repository ... Run first:` with the complete `survey` command. |

Without the last two stops, `scaffold --refresh` records old sources as current, and the page is stale again at the next `status`.

The record of a page can lose a source file. The file has a new name that the plan does not take, or the file is gone. When the plan gives no file in its place, `scaffold --refresh` prints one `note` below its `recorded` line. The note names the file. A later change of that text does not make the page stale, so the agent puts the line into its report.

## Checks of `check`

Each finding starts with the absolute path of the file and the line. A fix text gives each command in its complete form.

| Rule | Finding |
| --- | --- |
| `frontmatter` | The frontmatter has no `title:` line or no `description:` line with a text. The finding names the line that is absent. With the facts, the fix gives the exact line that the script wrote. For a line with the key and no text, the fix gives the number of that line and the line to write in its place. A second line with the same key stops the build. |
| `docgen-line` | A line that the script wrote, and that an action reads, is absent, changed or at a wrong place. The fix gives the exact line and the line that it follows. See "The docgen lines of a page". |
| `open-slot` | A slot still holds its `TODO` line. |
| `slot-form` | A written slot does not have its form. The finding names the file, the line of the slot, the slot and the fault. `next` prints the same fault. |
| `slot-length` | A slot is outside its word range. |
| `command-twice` | A code block of the page holds the command of a capture of the same page. |
| `stale-part` | A command slot states no command and the page still has the step with the frame, or the reverse. The fix is one more run of `scaffold`. |
| `stale-spec` | The capture spec of a `slot` capture does not hold the command of its slot, or the spec is absent. Or a capture mark of the template has no spec and the state does not list its capture. The fix is one more run of `scaffold`. |
| `host-value` | A page, the state file or a capture spec holds a value of one host or a credential. See "Values of one host". |
| `unknown-path` | A path in the page is not a file or a directory of the project at the ref of the page. And no source file of the page holds it as literal text. See "Paths and commands of a page". |
| `missing-page` | The state lists a page that does not exist. The fix is one more run of `scaffold`. |
| `not-registered` | The project is not in the project list of the site, or its doc set or its release is not current there. |

### Notes of `check`

A note is a line with the word `note`. It is no finding, and it never changes the exit code.

| Note | Meaning |
| --- | --- |
| `<file>:<line>: note: unverified-command: ...` | No source states this command line. See "Paths and commands of a page". The agent puts each such line into its report, so the reviewer reads those commands first. |
| `<file>:<line>: note: unused-fact: ...` | The slot `stage-4-command` says that the sources state no test of the install, and the facts of the survey hold a test command. The note names each test command of the facts. A source file of the page can say that one of them tests the install: the agent then writes that command into the slot. If no source file says so, the sentence is correct, and the agent changes nothing. No other slot has this rule. The agent puts the line into its report, so the reviewer decides. |
| `<file>:<line>: note: the diagram ... is not drawn yet` | A larger model draws the diagram in the second pass. |
| `note     the rules ... did not run` | A rule did not run, and the line gives the cause. See below. |

Below the findings and the notes, `check` prints its summary. First comes the number of findings. Then comes the number of `unverified-command` notes when there is one, and in the next line the number of `unused-fact` notes when there is one. Then come the number of diagrams that wait and the rules that did not run.

### A rule that did not run

`check` needs the work files and the project repository for some rules. The work files in `.docgen/` are not tracked, so a new clone of the site has none. The skill `tenant-docs-diagrams` and a reviewer can run `check` in such a checkout. `check` then runs each rule that it can, and it prints one line that names each rule that did not run, with the cause. That line is no finding. A pass with this line is not a pass of those rules.

| The checkout has | Rules that do not run |
| --- | --- |
| No `.docgen/<project>/facts.json` | `unknown-path`, `unverified-command` and `unused-fact`. `docgen-line` does not compare a page with its template. It reports only a slot with no end line, an end line with no slot, and a `TODO` text in no slot. `frontmatter` names the absent line and cannot give its text. |
| The facts, and Git cannot read the project repository of the last survey | `unknown-path` and `unverified-command`. |
| The facts and the repository, and Git cannot read a source file of a page or the ref of the page | `unknown-path` and `unverified-command`, for that page. |

`survey` in the project repository writes the facts and records the path of the repository.

## Values of one host

The site is public. A page, the state file and a capture spec hold no value of one host and no credential.

- `check` gives the files of the doc set to the scanner of the site, `scripts/scan.py`, by their paths. These files are each page and each capture spec that the state lists, and the state file. So `check` and the commit hook have one rule, and `check` finds a value also while Git does not track the file. `README.md` describes the rule files of the scanner.
- The rule follows the scanner. A loopback address and an address of a documentation range are no values of one host. A value of the allow list gives no finding.
- The scanner does not show a credential and a value of the local deny list. The finding then names the column.
- `check` also finds two paths of this machine that the script knows. They are the path of the site directory and the path of the project clone of the last survey. It finds each one also as its real path. `next` prints both paths, and a generic rule does not know a path below each directory. A path with one part, for example `/srv`, is not such a value. The path counts at the start of a word, and as the path of a URL such as `file://<path>`.
- `next` reports a value of one host in a written slot as a `problem`, with the line and the fix.
- In a directory with no `scripts/scan.py`, the own list of docgen is the fallback. It has private IPv4 addresses, home paths, paths below `/opt` and URLs with an internal top-level name. The tests of docgen use such a directory. `register` uses this list for its four values.

Each kind of value has its own fix text.

| The line holds | The fix text tells the agent to write |
| --- | --- |
| A private IP address | The example address `192.0.2.10`, or `2001:db8::1` for an IPv6 address. |
| A home path | `~` in place of the home directory. |
| A path below `/opt` | The path from the directory of the clone, or `~/<project>` for the clone. |
| An internal URL | The example host `docs.example`. |
| A credential | The name of the variable or of the file, and never the value. |
| A value of the local deny list | A placeholder at the column that the finding names. |
| The path of the project clone | No path: a command of a page runs in the directory of the clone. |
| The path of the site directory | No path: a page does not name the tenant-docs checkout. |

For a value in the state file, the fix tells the agent to stop: the script writes that file. For a value in a capture spec, the fix names the command slot of the page and `scaffold`.

## The docgen lines of a page

A page that docgen wrote has lines that the script wrote and that an action reads. `next` and `check` find the slots by them, `scaffold` finds the frames and the parts by them, and `diagrams` finds the diagrams by them. An agent that writes a page again can remove or change such a line. The slot then has no check, or the page has two parts that do not agree.

`check` renders the template of the page again with the facts of the checkout. Each of these lines of the template must be on the page, in the order of the template:

| Line | What `check` compares |
| --- | --- |
| The first line of a slot | The name, the word range and the form. Not the instruction text. |
| `{/* docgen:end */}` | That the line is there, and the blanks before it. |
| The lines `{/* docgen:command` and `*/}` of a `command` slot | That both lines are there. The form check of the slot reports them. |
| A capture mark | The name and the source: `clone`, `run`, or `slot` with the name of the slot. Not the order, the title and the command of a `run` source. |
| The `Capture` line below a capture mark | The `id`, in double quotes or in single quotes. A person can change `Capture` to `Cast` at the review: both pass. |
| A marker of a part: `docgen:with`, `docgen:without` and their end lines | The kind and the slot. |
| A diagram comment and `{/* docgen:end-diagram */}` | The name. The status can be `pending` or `done`. |

- The finding `docgen-line` gives the exact line to put back and the line that it follows in the template. It also gives the number of that line on the page. For a changed line, it gives the exact line to write in its place. For a line at a wrong place, it tells the agent to move the line. For a line with other blanks than the template has, it gives the number of blanks.
- The findings of one page come in the order of the template. So the agent puts an earlier line back first.
- The line that a fix names as the place is a line that the page has. A line of a part that the page does not have is no place: the fix then names the first marker of that part. When the page never had the text line of the template, the fix names the nearest docgen line before it, with its number.
- An agent can change a docgen line so that the script does not read it, for example `docgen-slot` in place of `docgen:slot`. Such a line starts with `{/* docgen` and holds the name of the slot, of the capture or of the diagram. The finding is at that line, and the fix gives the exact line to write in its place. A fix that puts a second line above it leaves the changed line in the text of the slot.
- A `Capture` line that the script does not read gets the same finding. Examples: the `id` has no quotes, or its two quotes are not equal. Such a line is directly below its capture mark. It holds one tag `<Capture ... />` or `<Cast ... />` and no other text. The finding is at that line, and the fix gives the exact line to write in its place. A fix that puts a second `Capture` line above it leaves a line that stops the build.
- A part that the page does not have gives no finding for the lines in it: a stage with no command has no frame. `stale-part` reports a part that does not agree with its slot.
- A line of the page that the template does not give is no finding. A person can add a frame.
- A diagram comment that says `done` needs a `mermaid` code block between it and its end line. Without the block, the fix tells the agent to write `pending` again. A `mermaid` block between the two lines passes with each status.
- `check` compares with the facts of this checkout. A change of the project can change these lines, for example a first command line or a first test command. `check` then asks for the new lines on a page that `scaffold` does not write again.

## Paths and commands of a page

`check` compares each path and each command of a page with the project. It reads the project through `git` only, in the repository of the last survey.

### `unknown-path`

The rule reads each word that is a path of the project by its form. It reads these places: inline code, each code block and the command of a `command` slot. The code block of a step, with blanks before it, is such a code block.

| Place | A word is read when |
| --- | --- |
| Each place | Its first part is a directory at the top of the project, for example `scripts/` in `scripts/build.sh`. |
| Inline code of one word | Also when it has a `/` and its last part has a point, as a file name has. |
| A code block, a command in inline code, a `command` slot | Also when it is below `scripts/`, `docs/`, `config/`, `src/` or `tests/`. |

A word with `://`, `@`, `$`, `*` or `~`, and a word that starts with `/` or `-`, is not read. A file name with no `/` is not read: a page names files that a command makes.

A line of a `mermaid` code block is a label for a reader. There the rule reads only a word whose last part has a point, as a file name has. Two words with a slash between them, for example `docs/tests`, are no path.

A path passes for one of two reasons, and for no other:

1. It is a file or a directory of the project at the ref of the page.
2. A source file of the page holds it as literal text. The text is the complete path, or the path with `/` and more parts after it. A longer name is another path.

The fix text names both reasons. The comment at the top of a page lists its source files.

### `unverified-command`

A command that no source states is a note, not a finding. `check` reads each line of each code block in a slot, and the command of each `command` slot. A line that ends with a backslash is one command line with its next line. The blanks are made equal, and a `$ ` prompt is no part of a command. A line passes when it is a part of one line of one of these:

- A source file of the page.
- A saved help text in `.docgen/<project>/help/`.
- A command of the facts: each command of the command list and each test command. Also each command that the script builds for a frame from the command line and its actions.
- Each other file of the project at the ref of the page. Git searches the tree, so the size of the project sets no limit.

For each other line, `check` prints one `note` with the rule name `unverified-command`. A shorter command passes when it is a part of a longer line of a file. The rule does not read inline code, and it does not read a `mermaid` code block: a diagram is no command. A `command` slot with a fault of its form gets no note: it has its finding.

## A checkout with no doc set

The state file `docgen/state/<project>.json` is absent in a checkout that has no doc set of the project. The message depends on the action.

| Action | Message |
| --- | --- |
| `next`, `check`, `commit` | `the state of '<project>' (run scaffold first) is absent`. These actions are steps of a first doc set, and `scaffold` is the step before them. The line ends with `Run first:` and the complete `scaffold` command. |
| `status`, `diagrams` | `this checkout of the site has no doc set of '<project>'`. The line then gives the cause. The doc set is in `main`: the line has the `branch --update` command. Or the branch `topic/docgen-<project>` holds it and it waits for the review. Or no branch holds it. The line does not name `scaffold`: that action makes a second, empty doc set here. Both actions check the form of the name first, so the word `PROJECT` gives the line for a name. |
