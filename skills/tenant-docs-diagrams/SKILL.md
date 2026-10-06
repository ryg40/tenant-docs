---
name: tenant-docs-diagrams
description: Draw the diagrams of a generated doc set on the tenant-docs site. This is the second pass after tenant-docs-generate or tenant-docs-update, and it is for a large model. Use when `docgen.py check` prints "diagram(s) wait for the second pass". Use also when the user says "draw the diagrams" or "second pass" for a docgen branch, or runs /tenant-docs-diagrams.
---

# Draw the diagrams of a generated doc set

A small model wrote the pages and, for each diagram, a numbered list of steps. You draw each diagram from its list and check the list against the sources.

## Rules

- Work on the branch of the doc set in the tenant-docs repository. Step 1 changes to that branch.
- Do not make a branch, a commit or a push by hand. The script makes them. Do not merge.
- A diagram shows only steps that the sources of the page state. The sources are in the comment at the top of the page and in `docgen/state/<project>.json`.
- If the list of the small model is wrong, correct the list first, then draw.
- No host name, IP address, user name, absolute path of one host, or internal URL in a label.

## How to run a command

- Each code block is one complete command. It runs in a new shell and from each directory.
- In a code block, replace the word `PROJECT` with the name of the project. The name is the name of its directory below `src/content/docs/` of the tenant-docs repository.
- If the shell prints `TENANT_DOCS_DIR is not set`, nothing changed. Ask the user for the path of the tenant-docs repository. Then write that path in place of `${TENANT_DOCS_DIR:?TENANT_DOCS_DIR is not set}`.

## Steps

1. Change to the branch of the doc set.

   ```bash
   python3 "${TENANT_DOCS_DIR:?TENANT_DOCS_DIR is not set}/docgen/docgen.py" branch --project PROJECT
   ```

   This command is for a doc set that waits for its review. The script prints `resumed` or `kept` and the name of the branch. A line `fetched` before it is correct too.

   If the script prints `is in main already`, the doc set is in `main`. You then run the command at the end of that line. It has the option `--update`, and it starts or takes the branch of an update.

   Do not run the command of the `next` line of this step. That line is for the small model.

2. List the diagrams.

   ```bash
   python3 "${TENANT_DOCS_DIR:?TENANT_DOCS_DIR is not set}/docgen/docgen.py" diagrams --project PROJECT
   ```

   The script prints each diagram with the full path of its page. It also prints the line of the diagram comment and what to draw. Below the list, the line `check` and the line `commit` hold the complete commands of steps 6 and 7.

3. Read the numbered list below the comment line of each diagram, and the sources of the page.

4. Put one fenced `mermaid` block between the `docgen:diagram` comment line and the `docgen:end-diagram` line.

5. Change the word `pending` in the comment line to `done`.

   The numbered list stays. It is the text alternative of the diagram.

6. Check the pages.

   ```bash
   python3 "${TENANT_DOCS_DIR:?TENANT_DOCS_DIR is not set}/docgen/docgen.py" check --project PROJECT
   ```

   The script checks the pages. After that, it runs the checks of the site. It builds the site, so you do not build the site yourself. A finding of a page has a fix text. Below a line `site ... FAIL`, the script prints the lines of that check. The build stops for a diagram type that the site does not support.

   A line with the word `note` is not a finding. The line `note ... did not run` says that this checkout has no work files of a survey, so some rules did not run. Continue.

   A line `note: unverified-command` or `note: unused-fact` is about a text of the small model. You change no page for it. Put the line into your report.

   The check passes only when the last line starts with `next`. Do not run the command of that line: step 7 has the command of this pass.

7. Commit the diagrams.

   ```bash
   python3 "${TENANT_DOCS_DIR:?TENANT_DOCS_DIR is not set}/docgen/docgen.py" commit --project PROJECT --diagrams
   ```

   The script commits the files of the doc set with the message `Docs of <project>: diagrams`. Then it pushes the branch. The step is complete when the last line starts with `done`.

8. Tell the user the result: the branch name, each diagram that you drew, each list that you corrected, and each `note` line that tells you to put it into your report.

## Diagram style

The site renders these types: flowchart, state diagram, sequence diagram, class diagram, ER diagram and XY chart. A block of another type, for example `gitGraph`, stops the build.

| Diagram of a generated page | Mermaid type |
| --- | --- |
| `parts` in the overview: the parts and what one part gives to another | `flowchart LR`, one node for each row of the table of the parts |
| `loop` in the development workflow: steps in order, with roles | `flowchart TD`, one node for each step, a `subgraph` for each phase when the list has more than six steps |
| Branches and merges | `flowchart LR`, one `subgraph` for each branch |
| Messages between two or more parts | `sequenceDiagram` |

- Nine nodes at most. Group steps if the list is longer.
- A label has five words at most. The first line of a node in the diagram `loop` names who does the step.
- Write a line `accTitle:` with the name of the diagram as the first line below the type.
- Do not set colors. The site gives each diagram the Soft Night colors.
- The install page has one flowchart of its four stages. A script wrote it. Do not change it.

## When something fails

| What you see | What to do |
| --- | --- |
| `error: 'PROJECT' is not a project name of the site` | You did not replace the word `PROJECT`. Use the name of the directory of the project below `src/content/docs/` of the tenant-docs repository. |
| An `error:` line that ends with `Run first:` and a command | Run that command. Then run again the command that stopped. |
| `error: this checkout of the site has no doc set` and no `Run first:` in the line | The checkout is not on the branch of the doc set. Stop. Tell the user that line. |
| `error: the site checkout has changes that are not committed` in step 1 | Do not remove or change a file. Stop. Tell the user that line. |
| `0 diagram(s) to draw` in step 2 | Each diagram is drawn. Your work ends. Tell the user that line. |
| `error: the pre-commit hook of the site refused the commit` in step 7 | No commit exists. Do step 6 again and correct each finding. Then do step 7 again. |
| Another line that starts with `error:` | Stop. Tell the user that line. |
| A command fails with a line that this table does not have, or the shell does not run the command | Stop. Change no setting of the shell or of the agent program. Give the user the command and the last 20 lines of its output. |
