---
name: tenant-docs-update
description: Bring the pages of one project on the tenant-docs site up to date after the project changed. Use when the user says "update the docs", "the docs are stale" or "sync tenant-docs", and after a new release of a project. Use also for /tenant-docs-update inside a project repository. A script lists each stale page, each source file that changed and a new release. You change only those pages.
---

# Update the docs of one project

A page is stale when a source file of the page changed in the project repository. The script `docgen.py` finds each stale item. You do one item at a time.

An update needs the doc set of the project in the branch `main` of the tenant-docs repository. The script stops in step 2 when the doc set is not there.

## Rules

- Change only a page that the script lists as `stale` or `open`.
- Do not edit a page that the script writes. The list of step 4 names such a page.
- Change only the sentences that the changed source makes wrong. Leave the other text.
- Write only what the named files say.
- Never write a value of one machine: a host name, an IP address, a user name, a home directory or an internal URL.
- Never write a password or a key.
- Do not change a file of the project repository.
- Do not make a branch, a commit or a push by hand. The script makes them.
- Do not merge.

## How to run a command

- Run each command in the project repository.
- Each command is complete. It needs no command before it and no variable of an earlier command.
- Step 1 has the first command. Run it as it is.
- A later step says where its command is in the output of the script. Copy the command from there and run it.
- The code block of a later step shows the same command in a second form. Use the code block only when you do not have the output. In the code block, replace the word `PROJECT` with the project name of step 1.
- A step with no code block has its command only in the output of step 4. When you do not have that output, do step 4 again.

## Steps

1. Read the project.

   ```bash
   python3 "${TENANT_DOCS_DIR:?error: TENANT_DOCS_DIR is not set; set it to the tenant-docs checkout}/docgen/docgen.py" survey --repo . --run-help --update
   ```

   The script prints the project name in the line `project`. The last line starts with `next`.

   - If the shell prints `error: TENANT_DOCS_DIR is not set; set it to the tenant-docs checkout`, nothing changed. Stop. Ask the user for the path of the tenant-docs repository. Use that path in place of `${TENANT_DOCS_DIR:?error: TENANT_DOCS_DIR is not set; set it to the tenant-docs checkout}`.
   - If the script prints `--run-help needs Docker`, nothing changed. Run the command at the end of that line. It is the same survey without `--run-help`.
   - A line that starts with `note` is no error. Continue. A note about the project list says that the name is not in that list. Step 2 then stops, and its line is for the user.

2. Start the branch of the update in the tenant-docs repository.

   ```bash
   python3 "${TENANT_DOCS_DIR:?error: TENANT_DOCS_DIR is not set; set it to the tenant-docs checkout}/docgen/docgen.py" branch --project PROJECT --update
   ```

   This is the command of the `next` line of step 1. The script prints `started`, `resumed`, `kept` or `moved`, and the name of the branch. Each of these four words is correct. A line `fetched` before it is correct too.

3. Choose the pages.

   ```bash
   python3 "${TENANT_DOCS_DIR:?error: TENANT_DOCS_DIR is not set; set it to the tenant-docs checkout}/docgen/docgen.py" plan --project PROJECT
   ```

   This is the command of the `next` line of step 2. The script prints each page that it plans and each page that it skips. A skipped page is correct.

4. List the stale items.

   ```bash
   python3 "${TENANT_DOCS_DIR:?error: TENANT_DOCS_DIR is not set; set it to the tenant-docs checkout}/docgen/docgen.py" status --project PROJECT
   ```

   This is the command of the `next` line of step 3. The exit code is 1 while the list has a stale item. That is correct.

   The first word of a line says what the line is. The lines below an item have blanks before them. They belong to that item.

   | First word | Meaning |
   | --- | --- |
   | `current` | The page is up to date. You do nothing for it. |
   | `release` | The project has a new release. This is one stale item. |
   | `stale` | A source file of the page changed. This is one stale item. |
   | `open` | The page has a slot with no text. This is one stale item. |
   | `note` | The line is no stale item. Put the line into your report when the line says so. |

   A line `N stale item(s)` comes after the list. `N` is the number of stale items.

   - With `0 stale item(s)` and a last line that starts with `next`, continue with step 10.
   - With `0 stale item(s)` and the sentence `Nothing to do.`, the pages are current. Your work ends. Tell the user that sentence.
   - With one stale item or more, find the first line that starts with `release`, `stale` or `open`. Do only that item now. This table gives its step.

   | The first stale item | Do |
   | --- | --- |
   | `release` | Step 5. |
   | `stale`, and a line of the item says `The page has ... open slot(s)` | The section "A page with open slots". |
   | `stale`, and a line of the item says `The script writes this page` | Step 6. |
   | `stale`, with none of these two lines | Steps 7 to 9. |
   | `open` | The section "A page with open slots". |

5. Set the new release.

   The line `Set the new release:` of the item holds one complete command. You copy that command, and you run it.

   The script prints a line `release` and a line `recorded`. It sets the release in `src/data/versions.json`. You do not edit that file by hand.

   Keep the line `For the user:` of the item for your report. It says that the capture script must run for the new release.

   The `next` line of this step holds the command of step 4. Do step 4 again.

6. Write a page of the script again.

   A script writes this page in full. You do not edit it. The line `Write the page again:` of the item holds one complete command. You copy that command, and you run it.

   The script prints `wrote` or `recorded` for the page. The `next` line of this step holds the command of step 4. Do step 4 again.

7. Read the change of each source file of the page.

   The item has one line for each source file that changed.

   - `changed. Read the change:` The next line is one `git ... diff` command. Run it. It shows the old lines and the new lines of the file.
   - `changed. The project repository does not hold the old text of this file.` The next line is one command that prints the file. Run it.
   - `was renamed to` The file has a new path. Its text is the same.
   - `was removed` The file is not in the project now.

8. Correct the page.

   The line `The page is the file` of the item gives the full path of the page. A change of a source file can make a sentence, a command or a table row of the page wrong. Change only those parts.

   - If the change makes no part of the page wrong, do not change the page. Continue with step 9.
   - For a file with a new path, write the new path in each place of the page that has the old path.
   - For a file that was removed, remove the sentences that came from that file.
   - Keep each docgen comment line of the page.

9. Record the new sources of the page.

   ```bash
   python3 "${TENANT_DOCS_DIR:?error: TENANT_DOCS_DIR is not set; set it to the tenant-docs checkout}/docgen/docgen.py" scaffold --project PROJECT --refresh PAGE
   ```

   The line `After you correct the page:` of the item holds this command in its complete form, and you copy it from there. In the code block, the word `PAGE` is the text after the word `stale`, for example `install/index.mdx`.

   The script prints `recorded` for the page. It also writes each page of the script again, and it adds a page that the project now needs. A command slot of a page can have a new command. The script then copies it into the capture spec and prints `updated captures/...`.

   A line `note` can come below the line `recorded`. It names a source file that the record of the page does not hold now. That line goes into your report.

   - If the `next` line of this step names the action `status`, do step 4 again.
   - If the `next` line names the action `next`, a page has open slots. Do the section "A page with open slots".

10. Set the project list and the release of the site.

    ```bash
    python3 "${TENANT_DOCS_DIR:?error: TENANT_DOCS_DIR is not set; set it to the tenant-docs checkout}/docgen/docgen.py" register --project PROJECT
    ```

    This is the command of the `next` line of step 4, below the line `0 stale item(s)`. A line that starts with `release`, `changed` or `kept` is correct. You do not edit `src/data/projects.json` or `src/data/versions.json` by hand.

    A line `note ... the capture script must run` goes into your report.

11. Check the pages.

    ```bash
    python3 "${TENANT_DOCS_DIR:?error: TENANT_DOCS_DIR is not set; set it to the tenant-docs checkout}/docgen/docgen.py" check --project PROJECT
    ```

    This is the command of the `next` line of step 10. Each finding of a page is one line. It has the full path of the file, the line, the rule, the message and the fix. The text after `Fix:` says what to do. Correct each finding. Then run the command again. An exit code that is not 0 is correct while a page has a finding.

    A line with the word `note` is not a finding.

    - `note: unverified-command`: the script did not find that command in the files of the project. You change nothing for this line. The line goes into your report.
    - `note: unused-fact`: the slot `stage-4-command` says that the sources state no test of the install, and the line names a test command of the project. The tests of the code are no test of the install. Write the command into the slot only if a source file of the page says that it tests the install. The line says how. If no file says so, the sentence is correct, and you change nothing. The line goes into your report.

    When the pages have no finding, the script runs the checks of the site. This part can take one minute. It builds the site, so you do not build the site yourself. Each result line starts with `site`. Below a line `site ... FAIL`, the script prints the lines of that check. Such a line names a file and says what is wrong. It can have no `Fix:` text.

    The check passes only when the last line starts with `next`.

12. Commit the update.

    ```bash
    python3 "${TENANT_DOCS_DIR:?error: TENANT_DOCS_DIR is not set; set it to the tenant-docs checkout}/docgen/docgen.py" commit --project PROJECT
    ```

    This is the command of the `next` line of step 11. The script commits only the files of the doc set, on the branch of the update. It writes the commit message: with a new release, the message names that release. Then it pushes the branch. The Git hook of the site runs each check again, so this step can take one minute.

    - `staged` names a file of the commit.
    - `commit` gives the commit ID and the commit message.
    - `pushed` says that `origin` has the branch.
    - `skipped ... docgen did not write it` names a file that is not in the commit. Put that line into your report.
    - `kept` says that the last commit holds each file, or that the server has each commit. Both are correct.

    The step is complete when the last line starts with `done`.

13. Tell the user the result. The result has these parts:

    - The branch name. The `done` line of step 12 names it.
    - The commit message. The line `commit` of step 12 holds it.
    - Each page that you changed, and each new page.
    - Each page that the script wrote again: each line `wrote` of step 6 and of step 9.
    - Each page whose source file changed and whose text you did not change, with the name of that file.
    - The new release, and the sentence that the capture script must run for it. Step 5 and step 10 print that sentence.
    - Each line `was removed` and each line `was renamed to` of step 4.
    - Each line `updated captures/...` of step 9, with this sentence: the recorded output is old, and `scripts/capture.py` must run again for the project.
    - Each line `kept ... the page exists and docgen did not write it`, with this sentence: a person must read that page again, because the project changed.
    - Each `note` line that tells you to put it into your report. This includes each line `note: unverified-command` and each line `note: unused-fact` of the last run of step 11. The user reads the commands of those lines first.
    - Each `docgen-line` finding that you corrected on a page that was not stale.
    - Each `skipped ... docgen did not write it` line of step 12.

    The user reviews the branch. You do not merge it.

When you stop before step 12, tell the user the step, the line that stopped you and the branch name. The branch name is in the output of step 2.

## A page with open slots

A page has an open slot when a slot holds its `TODO` line and no text. The project can need a page that the site does not have. The script then writes that page with open slots.

1. Ask for the next open slot.

   ```bash
   python3 "${TENANT_DOCS_DIR:?error: TENANT_DOCS_DIR is not set; set it to the tenant-docs checkout}/docgen/docgen.py" next --project PROJECT
   ```

   The line `Write each open slot first:` of step 4 holds this command. The `next` line of step 9 holds it too.

   The script prints one slot. The line `page` gives the full path of the file to change. The other lines give what to write, the form with its rules and the length. They also give the text for the case that the files have no answer. The script also prints the files to read and the one line to replace.

2. Read each file that the script names below `read first`.

   The script prints the size of each file and one command for it. A large file has one command for each part. You run each of these commands, in their order. For a later slot of the same page, the files are the same. You read a file again only when you do not have its text.

3. Replace the one line that the script prints below `then` with your text.

   The line holds `TODO(docgen:<slot>)`. The comment line above the slot and the comment line below it stay. You write one slot only. After it, you run the command of step 1 of this section again.

4. Do steps 1 to 3 of this section again until the script prints `No open slot`.

   When the script prints `correct` and `problem`, the slot that you wrote has a fault. The `problem` line says what to change.

5. Run the command of the `next` line below `No open slot`.

   ```bash
   python3 "${TENANT_DOCS_DIR:?error: TENANT_DOCS_DIR is not set; set it to the tenant-docs checkout}/docgen/docgen.py" scaffold --project PROJECT
   ```

   The script copies the command of each command slot into its capture spec. The `next` line of this command holds the command of step 4. Do step 4 of the steps above again.

- A command in a page is a copy of a command in a named file or in a help text. Do not build a command from memory.
- Put each command, path, option and file name in backticks.
- When the files have no answer for one part of a slot, keep the form and write `The sources do not state this.` only in that part. The lines `no answer` of the script give the exact text.
- When the files have no answer for the full slot and the slot gives no sentence after `write:`, stop. Tell the user the page and the slot.

## When something fails

Find the line in this table. A line of the script that starts with `error:` says what is wrong, and most such lines say what to do.

| What you see | What to do |
| --- | --- |
| `can't open file ... docgen.py` | The path is wrong. Stop. Ask the user for the path of the tenant-docs checkout. |
| An `error:` line with the words `run survey first` | Do step 1 again. Then do steps 2 and 3 again. If the name in the line is `PROJECT`, you did not replace that word. Use the project name of step 1. |
| `error: 'PROJECT' is not a project name of the site` | You did not replace the word `PROJECT`. Use the project name of step 1. |
| `error: this directory is the tenant-docs repository` in step 1 | The shell is not in the project repository. Stop. Tell the user that line. |
| `error: the doc set of '<project>' is not in main` in step 2 | An update is not possible. Do not run `scaffold`. Stop. Tell the user that line. |
| `error: the doc set of '<project>' is in main already` in step 2 | The command has no `--update`. Run the command at the end of that line. |
| `error: this checkout of the site has no doc set` and no `Run first:` in the line | Do not run `scaffold`. Stop. Tell the user that line. |
| `error: the site checkout has changes that are not committed` in step 2 | Do not remove or change a file. Stop. Tell the user that line. |
| `error: Git cannot fetch` in step 2 | Stop. Tell the user that line. |
| A line that starts with `note` and tells you to put it into your report | Continue. Put that line into your report. |
| `error: the pages of '<project>' describe the branch` and no `Run first:` in the line | The survey read another branch of the project than the pages describe. Do not choose a branch. Stop. Tell the user that line. |
| An `error:` line that ends with `Run first:` and a command | Run that command. Then run again the command that stopped. |
| `error: '...' is no page of the doc set` in step 6 or step 9 | The text after `--refresh` is wrong. Copy the command again from the line `After you correct the page:` or `Write the page again:` of step 4. |
| `error: the plan of '<project>' does not have the page` in step 9 | The project has no source file for that page now. Do not delete the page. Stop. Tell the user that line. |
| `error: the project repository ... does not have the release tag` or `has no branch` in step 4 | The project repository is older than the pages, or a branch is gone. Do not change the project repository. Stop. Tell the user that line. |
| The whole page came from a file that `was removed` | Do not delete the page. Stop. Tell the user the page and that line. |
| The same page is stale after step 9 | Stop. Tell the user the output of step 4. |
| The line `release` is in the list after step 5 | Stop. Tell the user the output of step 4. |
| `kept ... the page exists and docgen did not write it` | A person wrote that page. Do not change it. Continue. Put that line into your report. |
| `kept ... the page exists` | The page keeps its text. Continue. |
| `kept ... the spec exists and docgen did not write it` | A person wrote that capture spec. Do not change it. Continue. |
| `skipped ... the slot holds more than one command line` | Open the page. Keep one command line in that slot. Do step 9 again for a stale page. For an open slot, do step 5 of "A page with open slots". |
| `skipped ... does not have the form` | The page has an old form. You cannot correct it. Stop. Tell the user that line. |
| `skipped ... has no line` and the words `so the script does not change this part` | A marker line of the page is absent. Continue. The check of step 11 prints the exact line to put back. |
| `error: '...' is not a release tag of the branch ...` | The project has no release tag. You cannot correct this. Do not make a tag. Stop. Tell the user that line. |
| `not-registered` in the check of step 11 | Run the command after `Fix:`. It is the command of step 10. Then do step 11 again. |
| `slot-form` in the check of step 11 | The slot has a wrong form. Do step 1 of "A page with open slots". The `problem` line says what to change. |
| `command-twice` in the check of step 11 | Do what the text after `Fix:` says. It names the slot to change, and the sentence to write when nothing stays. Do not change a code block that the script wrote. |
| `stale-part` or `stale-spec` in the check of step 11 | Run the command after `Fix:`. Then do step 11 again. |
| `docgen-line` in the check of step 11 | A line that the script writes is absent or changed. The text after `Fix:` gives the exact line and its place. Put that line into the page. Then put the finding line into your report. |
| `site ... FAIL` and `check failed:` in step 11 | Read the lines below the line `site ... FAIL`. A line that names a page of the project names a fault in a text that you wrote. Correct that text. Then do step 11 again. When no line names a page of the project, stop. Give the user those lines. |
| `error: the pre-commit hook of the site refused the commit` in step 12 | No commit exists. Run the `check` command of that line and correct each finding. Then do step 12 again. |
| `error: Git made no commit`, `error: Git did not push the branch` or `error: the site has no remote origin` in step 12 | Stop. Give the user that line and the lines above it. |
| The same `problem` line after three tries | Stop. Tell the user the `correct` line and the `problem` line. |
| A check finding stays after three tries | Stop. Tell the user the finding line. |
| Another line that starts with `error:` | Stop. Tell the user that line. |
| A command fails with a line that this table does not have, or the shell does not run the command | Stop. Change no setting of the shell or of the agent program. Give the user the command and the last 20 lines of its output. |
