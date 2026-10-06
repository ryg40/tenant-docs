---
name: tenant-docs-generate
description: Write the first doc set of one project for the tenant-docs site, from the git history and the files of the project repository. Use when the user says "generate the docs", "document this project on tenant-docs" or "add this project to the docs site". Use also for /tenant-docs-generate inside a project repository. The scripts find the facts and name each file to read. You write one short text at a time.
---

# Generate the docs of one project

You write the pages of one project for the tenant-docs site. A script named `docgen.py` does the search work. You do only what the script tells you to do next.

## Rules

- Write only what the named files say. If the files do not say it, do not write it.
- Do one slot, then run the script again. Do not write two slots in one step.
- Never write a value of one machine: a host name, an IP address, a user name, a home directory or an internal URL.
- Never write a password or a key.
- Write short sentences. One idea in each sentence. Active voice. Present tense.
- Do not copy terminal output into a page. A capture shows the output.
- Do not change a file of the project repository. You change only pages of the tenant-docs repository.
- Do not make a branch, a commit or a push by hand. The script makes them.
- Do not merge.

## How to run a command

- Run each command in the project repository.
- Each command is complete. It needs no command before it and no variable of an earlier command.
- Step 1 has the first command. Run it as it is.
- Each later command is in the output of the command before it. That output has one line that starts with `next`. The text after the word `next` is the complete next command. Copy it and run it.
- The code block of a later step shows the same command in a second form. Use the code block only when you do not have the `next` line. In the code block, replace the word `PROJECT` with the project name of step 1.

## Steps

1. Read the project.

   ```bash
   python3 "${TENANT_DOCS_DIR:?error: TENANT_DOCS_DIR is not set; set it to the tenant-docs checkout}/docgen/docgen.py" survey --repo . --run-help
   ```

   The script prints the project name in the line `project`. It also prints the release and the number of files. The last line starts with `next`.

   - If the shell prints `error: TENANT_DOCS_DIR is not set; set it to the tenant-docs checkout`, nothing changed. Stop. Ask the user for the path of the tenant-docs repository. Use that path in place of `${TENANT_DOCS_DIR:?error: TENANT_DOCS_DIR is not set; set it to the tenant-docs checkout}`.
   - If the script prints `--run-help needs Docker`, nothing changed. Run the command at the end of that line. It is the same survey without `--run-help`.
   - A line that starts with `note` is no error. Find the line in the table "When something fails".

2. Start the branch of the run in the tenant-docs repository.

   ```bash
   python3 "${TENANT_DOCS_DIR:?error: TENANT_DOCS_DIR is not set; set it to the tenant-docs checkout}/docgen/docgen.py" branch --project PROJECT
   ```

   This is the command of the `next` line of step 1. The script prints `started`, `resumed` or `kept`, and the name of the branch. Each of these three words is correct. A line `fetched` before it is correct too.

3. Choose the pages.

   ```bash
   python3 "${TENANT_DOCS_DIR:?error: TENANT_DOCS_DIR is not set; set it to the tenant-docs checkout}/docgen/docgen.py" plan --project PROJECT
   ```

   The script prints each page that it plans and each page that it skips. A skipped page is correct. No one writes a skipped page.

4. Write the page skeletons.

   ```bash
   python3 "${TENANT_DOCS_DIR:?error: TENANT_DOCS_DIR is not set; set it to the tenant-docs checkout}/docgen/docgen.py" scaffold --project PROJECT
   ```

   The script also writes one capture spec for each command slot. A capture spec is a file in `captures/<project>/` of the tenant-docs repository. You do not edit a capture spec.

   If the `next` line of this step names the action `register`, no slot is open. Continue with step 10.

5. Ask for the next slot.

   ```bash
   python3 "${TENANT_DOCS_DIR:?error: TENANT_DOCS_DIR is not set; set it to the tenant-docs checkout}/docgen/docgen.py" next --project PROJECT
   ```

   The script prints one slot. The line `page` gives the full path of the file to change. The other lines give what to write, the form and the length. They also give the text for the case that the files have no answer. The script also prints the files to read and the one line to replace.

6. Read each file that the script names below `read first`.

   The script prints the name and the size of each file, and one exact command for it. A large file has one command for each part. You run each of these commands, in their order. The script also prints the facts that the page needs.

   For a later slot of the same page, the files are the same. The script says so. You read a file again only when you do not have its text.

7. Replace the one line that the script prints below `then` with your text.

   The line holds `TODO(docgen:<slot>)`. The comment line above the slot and the comment line below it stay.

8. Do steps 5 to 7 again until the script prints `No open slot`.

   When the script prints `correct` and `problem`, the slot that you wrote has a fault. The `correct` line gives the file and the line of the slot. The `problem` line says what to change.

9. Write the page skeletons again.

   ```bash
   python3 "${TENANT_DOCS_DIR:?error: TENANT_DOCS_DIR is not set; set it to the tenant-docs checkout}/docgen/docgen.py" scaffold --project PROJECT
   ```

   This is the command of the `next` line below `No open slot`. The script copies the command of each command slot into its capture spec.

   The script prints `updated captures/...` for a capture spec that gets the command of its slot. A stage can have no command. The script then prints `updated` for the Install page and `removed` for the capture spec of that stage. Each of these lines is correct. You change nothing by hand.

   Keep the line that starts with `captures`. It gives the number of command slots for your report.

10. Add the project to the project list of the site.

    ```bash
    python3 "${TENANT_DOCS_DIR:?error: TENANT_DOCS_DIR is not set; set it to the tenant-docs checkout}/docgen/docgen.py" register --project PROJECT
    ```

    The output has a line that starts with `added`, `changed` or `release`, or it has the line `kept`. Each of these lines is correct.

    - `added` says that the project is new in `src/data/projects.json`.
    - `changed` says that the project had an overview page only, and that it now has a full doc set.
    - `release` says that `src/data/versions.json` has the release of the project.
    - `kept ... No file changed.` says that the list was current.
    - `note` names the home page. You do not change the home page. Put that line into your report.

    You do not edit `src/data/projects.json` or `src/data/versions.json` by hand.

11. Check the pages.

    ```bash
    python3 "${TENANT_DOCS_DIR:?error: TENANT_DOCS_DIR is not set; set it to the tenant-docs checkout}/docgen/docgen.py" check --project PROJECT
    ```

    Each finding of a page is one line. It has the full path of the file, the line, the rule, the message and the fix. The text after `Fix:` says what to do. Correct each finding. Then run the command again. An exit code that is not 0 is correct while a page has a finding.

    A line with the word `note` is not a finding.

    - `note: the diagram ... is not drawn yet`: a larger model draws the diagram later, so its comment lines stay as they are.
    - `note: unverified-command`: the script did not find that command in the files of the project. You change nothing for this line. Put the line into your report.
    - `note: unused-fact`: the slot `stage-4-command` says that the sources state no test of the install, and the line names a test command of the project. The tests of the code are no test of the install. Write the command into the slot only if a source file of the page says that it tests the install. The line says how. If no file says so, the sentence is correct, and you change nothing. Put the line into your report.

    When the pages have no finding, the script runs the checks of the site. This part can take one minute. It builds the site, so you do not build the site yourself. Each result line starts with `site`. Below a line `site ... FAIL`, the script prints the lines of that check. Such a line names a file and says what is wrong. It can have no `Fix:` text.

    The check passes only when the last line starts with `next`.

12. Commit the doc set.

    ```bash
    python3 "${TENANT_DOCS_DIR:?error: TENANT_DOCS_DIR is not set; set it to the tenant-docs checkout}/docgen/docgen.py" commit --project PROJECT
    ```

    This is the command of the `next` line of step 11. The script commits only the files of the doc set, on the branch of the run. Then it pushes that branch. The Git hook of the site runs each check again, so this step can take one minute.

    - `staged` names a file of the commit.
    - `commit` gives the commit ID and the commit message.
    - `pushed` says that `origin` has the branch.
    - `skipped ... docgen did not write it` names a file that is not in the commit. Put that line into your report.
    - `kept` says that the last commit holds each file, or that the server has each commit. Both are correct.

    The step is complete when the last line starts with `done`.

13. Tell the user the result. The result has these parts:

    - The branch name. The `done` line of step 12 names it.
    - The pages that you wrote, and the pages that the script skipped.
    - Each slot where the files did not have the full answer: the page, the slot and the part.
    - The number of diagrams that wait for the second pass.
    - The number of command slots in the line `captures` of step 9. Each of them has a capture spec. The capture script `scripts/capture.py` records their output later.
    - Each line `kept ... the page exists and docgen did not write it`, with this sentence: a person must read that page again, because the project now has more pages.
    - Each `note` line that tells you to put it into your report. This includes each line `note: unverified-command` and each line `note: unused-fact` of the last run of step 11. The user reads the commands of those lines first.
    - Each `skipped ... docgen did not write it` line of step 12.

    The user reviews the branch. You do not merge it.

When you stop before step 12, tell the user the step, the line that stopped you and the branch name. The branch name is in the output of step 2.

## How to write a slot

The script prints the form of each slot and the rules of that form. This table is a summary.

| Form | Write |
| --- | --- |
| `text` | Plain sentences. No heading. |
| `list` | A list. Each item is one line that starts with `- `. |
| `numbered` | A numbered list. One line for each item. |
| `table` | A Markdown table with the columns that the slot names. |
| `steps` | A numbered list. Each step has one sentence with one action, the exact command in a code block, and one line that starts with `Result:`. Each line below the first line of a step has three spaces before it. A step with no command in the files has no code block. |
| `command` | One command line with no backticks and no placeholder in angle brackets. The line `{/* docgen:command` above it and the line `*/}` below it stay. The page shows the command in the frame of its capture. |

- A command in a page is a copy of a command in a named file or in a help text. Do not build a command from memory. The check prints a `note` for a command that it does not find in the files.
- A page shows each command one time in a code block or in a frame. Do not put the command of a `command` slot into a step or into a code block of the same page. A table can name a command in backticks when the slot asks for it.
- A path in a page is the path of a file of the project, or a path that a named file states. The check finds another path.
- Put each command, path, option and file name in backticks. A `<` or a `{` outside backticks stops the build.
- A slot for a diagram is a numbered list of steps. Do not draw the diagram. A larger model draws it later.
- A status is a copy of the words of the README. Do not make the status better.

When the files do not have the answer, the lines `no answer` of step 5 give the exact text. These are the rules:

- Keep the form of the slot.
- When the files have no answer for one part of the slot, write `The sources do not state this.` only in that part. A part is one cell of a table, one item of a list, or the `Result:` line of a step. When the slot gives its own words for a part, for example "Not stated", write those words.
- When the files have no answer for the full slot, write the sentence that the slot gives after `write:`, and no other text. Copy that sentence character by character: the script does not accept a changed word.
- When the slot gives no such sentence and the files have no answer for the full slot, stop. Tell the user the page and the slot.

## When something fails

Find the line in this table. A line of the script that starts with `error:` says what is wrong, and most such lines say what to do.

| What you see | What to do |
| --- | --- |
| `can't open file ... docgen.py` | The path is wrong. Stop. Ask the user for the path of the tenant-docs checkout. |
| An `error:` line with the words `run survey first` | Do step 1 again. Then continue with the command of its `next` line. If the name in the line is `PROJECT`, you did not replace that word. Use the project name of step 1. |
| `error: 'PROJECT' is not a project name of the site` | You did not replace the word `PROJECT`. Use the project name of step 1. |
| `error: this directory is the tenant-docs repository` in step 1 | The shell is not in the project repository. Stop. Tell the user that line. |
| `note ... the project has no release tag` in step 1 | A full doc set needs a release tag, and step 3 stops without it. Do not make a tag. Stop now. Tell the user that line. |
| Another line that starts with `note` and tells you to put it into your report | Continue. Put that line into your report. |
| `error: the pages of '<project>' describe the branch` and no `Run first:` in the line | The survey read another branch of the project than the pages describe. Do not choose a branch. Stop. Tell the user that line. |
| `error: '...' is not a release tag of the branch ...` | The project has no release tag. You cannot correct this. Do not make a tag. Stop. Tell the user that line. |
| `error: the site checkout has changes that are not committed` in step 2 | Do not remove or change a file. Stop. Tell the user that line. |
| `error: the doc set of '<project>' is in main already` in step 2 | The project has its doc set. This skill makes only a first doc set. Stop. Tell the user that line. |
| `error: Git cannot fetch` in step 2 | Stop. Tell the user that line. |
| `note ... does not hold ... commit(s) of` in step 2 | Continue. Put that line into your report. |
| An `error:` line that ends with `Run first:` and a command | Run that command. Then run again the command that stopped. |
| `kept ... the page exists and docgen did not write it` | A person wrote that page. Do not change it. Continue. Put that line into your report. |
| `kept ... the page exists` | The page has its text from this run or from a run before. Continue. |
| `kept ... the spec exists and docgen did not write it` | A person wrote that capture spec. Do not change it. Continue. |
| `skipped ... the slot holds more than one command line` | Open the page. Keep one command line in that slot. Then do step 9 again. |
| `skipped ... does not have the form` | The page has an old form. You cannot correct it. Stop. Tell the user that line. |
| `skipped ... has no line` and the words `so the script does not change this part` | A marker line of the page is absent. Continue. The check of step 11 prints the exact line to put back. |
| `note ... has no release of <project>` | Continue. Step 10 sets the release. |
| `not-registered` in the check of step 11 | Run the command after `Fix:`. It is the command of step 10. Then do step 11 again. |
| `slot-form` in the check of step 11 | The slot has a wrong form. Do step 5. The `problem` line says what to change. |
| `command-twice` in the check of step 11 | Do what the text after `Fix:` says. It names the slot to change, and the sentence to write when nothing stays. Do not change a code block that the script wrote. |
| `stale-part` or `stale-spec` in the check of step 11 | Do step 9 again. Then do step 11 again. |
| `site ... FAIL` and `check failed:` in step 11 | Read the lines below the line `site ... FAIL`. A line that names a page of the project names a fault in a slot that you wrote. Correct that slot. Then do step 11 again. When no line names a page of the project, stop. Give the user those lines. |
| `error: the release of '<project>' is not known` in step 10 | Do step 4 again. Then do step 10 again. |
| `error: the pre-commit hook of the site refused the commit` in step 12 | No commit exists. Run the `check` command of that line and correct each finding. Then do step 12 again. |
| `error: Git made no commit`, `error: Git did not push the branch` or `error: the site has no remote origin` in step 12 | Stop. Give the user that line and the lines above it. |
| The same `problem` line after three tries | Stop. Tell the user the `correct` line and the `problem` line. |
| A check finding stays after three tries | Stop. Tell the user the finding line. |
| Another line that starts with `error:` | Stop. Tell the user that line. |
| A command fails with a line that this table does not have, or the shell does not run the command | Stop. Change no setting of the shell or of the agent program. Give the user the command and the last 20 lines of its output. |
