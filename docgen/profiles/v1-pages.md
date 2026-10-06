# The tenant-pi pages and the templates of the profile `v1`

This file is the record of phase 1 of the doc generator (issue 13, slice issue 16). It lists each page type and each section of the tenant-pi pages in `src/content/docs/tenant-pi/`. For each one, it names the template of the profile `v1` that gives it, or the gap.

The tenant-pi pages are the prototype of the doc set of version one. A person wrote them. The templates keep the shapes that a script and a small model can make again for another project.

Status: final. The owner approved the tenant-pi pages and the doc set of version one on 2026-10-05 (issue 13).

## How to read the tables

| Word | Meaning |
| --- | --- |
| Slot | A text that the small model writes. The table gives the slot id, the form and the word range. |
| Script | The generator writes this part from the facts of the survey. The small model does not change it. |
| Diagram, second pass | The small model writes a numbered list. A large model draws the diagram from the list. |
| Gap | The template does not give this section. The table gives the reason. |

The slot form of the profile `v1` changed on 2026-10-05, before the first generated doc set (owner decision, issue 13). The name `v1` and the status `final` did not change.

- A command slot is a comment of the page. The page shows the command only in the frame of its capture.
- The Install page has eleven slots: the slots `stage-3-command` and `stage-4-command` are new.
- A stage of the Install page with no command has one sentence and no frame.

No doc set of the old form is in the repository. `check` reports such a doc set, and docgen has no code that converts it. To get the new form, a person starts a new branch, removes the pages, the capture specs and the state file of the project, and runs the skill `tenant-docs-generate` again.

A slot has one of six forms: `text`, `list`, `numbered`, `table`, `steps` and `command`. `docgen.py next` prints the rules of the form with each slot.

## Page types

| # | Page type | Pages of tenant-pi | Template of `v1` | State |
| --- | --- | --- | --- | --- |
| 1 | Overview | `index.mdx` | `overview` | Template |
| 2 | Install summary | `install/index.mdx` | `install`, the top part | Template. The summary and the stages are one page. |
| 3 | Install stage | `install/stage-1-obtain-the-sources.mdx` to `install/stage-9-test.mdx`, nine pages | `install`, one `Stage` block for each stage | Template. Four fixed stages on one page. |
| 4 | Command summary | `use/commands/index.mdx` | `commands` | Template |
| 5 | Command page | `use/commands/<action>.mdx`, nine pages | `command` | Template. One page for each action of the command line. |
| 6 | Task guide | `use/candidate-update.mdx` | None | Gap |
| 7 | Concept page | `use/modules-and-privacy.mdx` | None | Gap |
| 8 | Development workflow | `develop/workflow.mdx` | `workflow` | Template |
| 9 | Repository layout | `develop/repository.mdx` | `workflow`, the section "The branches" | One section only |
| 10 | Worked example | `develop/issue-to-merge.mdx` | None | Gap |
| 11 | Release gates | `develop/gates.mdx` | `workflow`, the section "The checks before a merge" | One section only |
| 12 | Portable release | `develop/release.mdx` | `workflow`, the section "The release" | One section only |
| 13 | Reference | `reference/index.mdx` | `reference` | Template. A script writes the whole page. |

The tenant-pi doc set has 29 pages. A generated doc set has five pages, and one more page for each action of the command line.

## 1. Overview

Page: `index.mdx`. Template: `overview`. The page describes the release.

| Section of the tenant-pi page | Content | In the template |
| --- | --- | --- |
| Top of the page | `DocVersion` | Script: `DocVersion`. |
| Introduction, no heading | Two paragraphs: what the project is, and each special word with its meaning. | Slot `what-it-is`, text, 30 to 90 words. |
| How the parts fit | One flowchart. One table with the columns Part, What it is, Who owns it. | Diagram `parts`, second pass. Slot `parts`, table, 30 to 220 words, with the columns Part and What it is. Slot `parts-flow`, numbered, 8 to 150 words: the list for the diagram. |
| Who it is for | A list of users and tasks. One sentence on what the reader must know. | Slot `audience`, list, 15 to 90 words. |
| What the kit never does | A list of limits. Two paragraphs. | Slot `limits`, list, 5 to 140 words, below the heading "What it does not do". |
| Status of this release | A list. | Slot `status`, text, 5 to 80 words, below the heading "Status". |
| Platforms that are not qualified | A table of platforms. | Gap. A README does not always have this fact. It goes into `status` or `limits` when the README states it. |
| Where to go next | `CardGrid` with one `LinkCard` for each part of the doc set. | Script: one card for each planned page of the project. In an overview-only doc set, the script writes one sentence instead. |

Gap in the table of the parts: the column "Who owns it". The reason is that only a project with a private directory needs it.

## 2. Install summary

Page: `install/index.mdx`. Template: `install`, the part above the first `Stage` block.

| Section of the tenant-pi page | Content | In the template |
| --- | --- | --- |
| Top of the page | `DocVersion` | Script: `DocVersion`. |
| Introduction, no heading | Three sentences on the stages. | Slot `goal`, text, 15 to 50 words. Script: two fixed sentences. |
| The stages at a glance | One flowchart of the nine stages. One table with the columns Stage, What you get, Commands, State. | Script: one fixed flowchart of the four stages. The table is a gap, because the stages are on the same page. |
| Requirements | A table with the columns Item, Required, Notes. | Slot `requirements`, table, 10 to 150 words, with the columns Item, Required version, Notes. |
| Words in this guide | A table of the special words. | Gap. The slot `what-it-is` of the overview gives the meaning of each special word. |
| Rules for each command | A list of rules for paths and quotes. | Gap. Stage 1 has two fixed sentences on the directory of the clone. |
| The command line of the kit | Text, a list, and the `Capture` of the help text. | The template `commands`: slot `summary` and the capture `help`. |
| Before Stage 1 | Three steps in `Steps`, notes and one warning. | Gap. The steps are special to tenant-pi. |
| Start | `CardGrid` with one card for each stage. | Not necessary: the stages are on the same page. |

## 3. Install stage

Pages: nine pages `install/stage-<n>-<name>.mdx`. Template: `install`, one `Stage` block for each stage.

The tenant-pi pages do not use the `Stage` component, because each stage has its own page. The template uses it, because a generated install is one page. The four fixed stages are: Get the sources, Configure, Install and start, Check.

| Section of the tenant-pi pages | Content | In the template |
| --- | --- | --- |
| Frontmatter | The title `Stage <n>: <name>`, the sidebar label and the order. | Script: `<Stage n={n}>` and the heading of the stage. |
| Top of the page | `DocVersion`. Stages 6 to 9 have an `Aside` with the title "Not verified on a clean client". | `DocVersion` one time for the page. The `Aside` is a gap: the script does not know which stage is verified. |
| Goal | One sentence. One flowchart of the stage. | Script: one fixed sentence for each stage. The flowchart of one stage is a gap. The page has one flowchart of all stages. |
| Before you start | A list, or a table with the columns Item, How to check. | Gap. The slot `requirements` holds the items one time for the page. |
| Steps | `Steps`. Each step has one sentence with one action, the command in a code block and a line that starts with `Result:`. Some steps have a `Capture`. Stages 6 to 8 use `Tabs`. | Stage 1: the script writes the two steps (clone, change the directory). The step of the clone holds the frame and no code block. Stages 2 to 4: slots `stage-2-steps`, `stage-3-steps` and `stage-4-steps`, form steps, 5 to 250 or 300 words, inside `Steps`. In stages 3 and 4, the script writes the last step with the frame of its capture. When the sources state no such command, the stage has one sentence in the place of that step, and no frame. The slots `stage-3-command` and `stage-4-command`, form command, 1 to 40 words, hold the command of that frame and do not show on the page. `Tabs` is a gap. |
| The run | The `Cast` of the main command of the stage, on some pages also the `Capture`. | No section. The frame is inside its step: `stage1-clone` in step 1 of stage 1 (script), `stage3-start` and `stage4-check` in the last step of stages 3 and 4 (the command of the slots `stage-3-command` and `stage-4-command`). `Cast` is a gap: a person can change `Capture` to `Cast` after the capture has a recording. |
| Sections on one subject, for example "What the check covers", "Options", "What the action writes" | Text, tables and the `Capture` of `help-<action>`. | Gap in the install page. The template `command` has the options and the help text of each action. |
| The result | One sentence, or a list. | Stage 1: script. Slots `stage-2-result`, `stage-3-result` and `stage-4-result`, text, 4 to 40 words. Each starts with `**Result:**`. |
| What can go wrong | A table with the columns What you see or Error, Cause, What to do. | Slot `problems`, table, 6 to 250 words, one time for the page. |
| After the install, on the page of stage 9 | `CardGrid` | Gap. The sidebar gives the next page. |
| Lines that start with `Warning:` | Zero to four on a page. | No slot. A small model writes a warning only when a source file has it. The lint of the site checks the form. |

## 4. Command summary

Page: `use/commands/index.mdx`. Template: `commands`.

| Section of the tenant-pi page | Content | In the template |
| --- | --- | --- |
| Top of the page | `DocVersion` | Script: `DocVersion`. |
| Introduction, no heading | Three sentences, the start command in a code block, the `Capture` of `help`. | Slot `summary`, text, 15 to 70 words. Script: the capture `help`, when the project has a Python command line. |
| Find an action | A table with the columns Action, Use it to, What it writes. Each action is a link to its page. | Script: a list of links to the action pages. Slot `command-table`, table, 20 to 450 words. The instruction names each command of the survey. |
| Words on these pages | A table of the special words. | Gap. See the overview. |
| Output | Text on the form of the output. | Slot `output`, text, 8 to 140 words, below the heading "Output and exit codes". |
| Exit codes | A table, a JSON block and the `Capture` of a refused action. | The same slot `output`. The capture of a refusal is a gap: the script does not know a command that fails in a known way. |
| Rules of each action | A list of limits. | Gap. See the slot `limits` of the overview. |
| More help | The path of the troubleshooting guide. | The template `reference` names the troubleshooting guide. |
| Not in tenant-pi | | Slot `examples`, text, 8 to 250 words. The script adds it only when the project has no action page. |

## 5. Command page

Pages: nine pages `use/commands/<action>.mdx`. Template: `command`. The generator plans one page for each action of the Python command line with the most actions.

| Section of the tenant-pi pages | Content | In the template |
| --- | --- | --- |
| Frontmatter | The title is the action. The description. The order. | Script: the title, a fixed description and the order. |
| Top of the page | `DocVersion` | Script: `DocVersion`. |
| Introduction, no heading | Two or three sentences, and a link to the section `Output`, which shows the command. | Slot `what-it-does`, text, 15 to 70 words. Script: the sentence with the link. |
| Options | The `Capture` of `help-<action>`, a table with the columns Option, Meaning, and notes. | Script: the capture `help-<action>`. Slot `options`, table, 5 to 300 words. |
| What it reads, What it writes, What it creates, What it runs | Tables and lists. Each page has one or two of these sections. | Slot `reads-writes`, table, 6 to 180 words, below the one heading "What it reads and writes". |
| Output | The `Capture` of `cmd-<action>` and text. Some pages have subsections. | Slot `example-command`, command, 1 to 60 words. The slot is a comment and does not show on the page. The capture `cmd-<action>` shows its command. Slot `output`, text, 6 to 120 words. |
| Exit codes | A table. | Slot `exit-codes`, table, 6 to 120 words. |
| Common refusals | A table with the columns Diagnostic, Cause. | Slot `errors`, table, 6 to 200 words, below the heading "Common errors". |
| Limits, on five of the nine pages | A list. | Gap. The slot `what-it-does` holds the most important limit. |
| Apply the patches, on the page `carry` only | Steps. | Gap. The section is special to one action. |
| Reference file | The paths of the files that describe the action. | Slot `reference-file`, text, 6 to 60 words. |

## 6. Task guide

Page: `use/candidate-update.mdx`. Template: none.

The page has these sections: an introduction, "The loop" with a flowchart and a numbered list, "The old and the new directory" with a flowchart, "One pass in a recording" with a `Cast`, "Before you start", five sections "Step 1" to "Step 5" with commands and `Capture` frames, "After Pi changes a profile" and "Reference files".

Gap. The reason: the survey cannot find the tasks of a project. A person must name the task and its steps. The proposal for the owner decision has this page type after version one.

## 7. Concept page

Page: `use/modules-and-privacy.mdx`. Template: none.

The page has these sections: an introduction, "What the kit separates" with a flowchart and a table, "Status labels", "The modules" with one table for each group, "What the kit never does", "Credentials", "What the scanner checks" and "Reference files". It has no capture.

Gap. The reason is the same as for the task guide: the subject is special to one project.

## 8. Development workflow

Page: `develop/workflow.mdx`. Template: `workflow`. The page describes the develop branch, so it has no `DocVersion`.

| Section of the tenant-pi page | Content | In the template |
| --- | --- | --- |
| Introduction, no heading | Two paragraphs on the loop. | Script: one sentence that names the branch. Slot `loop`, text, 30 to 110 words. |
| The loop | One flowchart with one group for each phase. Two paragraphs. | Diagram `loop`, second pass. Slot `flow-steps`, numbered, 20 to 170 words: the list for the diagram. |
| The roles | One flowchart, a table with the columns Role, Task, Limit, and two paragraphs. | Slot `roles`, table, 5 to 150 words. The flowchart is a gap. |
| Each step | A table with the columns Step, Role, Action, Result, Page. | The slot `flow-steps` has the same steps. The table is a gap. |
| The rules of the loop | A list. | Gap. The sources of most projects have no such list. |
| Where to read next | A table of the other Develop pages. | Not necessary: a generated doc set has one Develop page. |

## 9. Repository layout

Page: `develop/repository.mdx`. Template: one section of `workflow`.

| Section of the tenant-pi page | Content | In the template |
| --- | --- | --- |
| The two branches | One flowchart and three tables. | Slot `branches`, table, 20 to 170 words, with the columns Branch, What it holds, Who writes to it. The flowchart is a gap. |
| The files on `main` | Two tables of paths. | Gap. The template `reference` lists the documentation files. |
| The remotes | One flowchart and text. | Gap. A remote can be a value of one host. |
| The private files | Text and one warning. | Gap. |
| Set up a development clone | Steps and two warnings. | Gap. |

## 10. Worked example

Page: `develop/issue-to-merge.mdx`. Template: none.

The page has these sections: "The example on one diagram", "The issue", "The branch and the commits" with a flowchart, "The steps" with one part for each role and four `Capture` frames, "The record" and "The hooks in this flow" with a flowchart.

Gap. The reason: a worked example needs a choice of one real change, and neutral values in place of the real ones. A script and a small model cannot make that choice.

## 11. Release gates

Page: `develop/gates.mdx`. Template: one section of `workflow`.

| Section of the tenant-pi page | Content | In the template |
| --- | --- | --- |
| The gates on one diagram | One flowchart and a table. | Gap. |
| The commands | A table with the columns Gate, Command, Passes when, Required. | Slot `checks`, table, 8 to 220 words, with the columns Check, Command, Passes when. |
| The four results | One flowchart. | Gap. |
| Gate 1 to Gate 7 | One section for each gate, five of them with a `Capture`. | Script: the capture `dev-tests` of the first test command of the survey. The other sections are a gap. |
| Record the gates | A table and a list. | Gap. |

## 12. Portable release

Page: `develop/release.mdx`. Template: one section of `workflow`.

| Section of the tenant-pi page | Content | In the template |
| --- | --- | --- |
| The release on one diagram | One flowchart. | Gap. |
| The steps | Steps and two warnings. | Slot `release`, numbered, 6 to 170 words. |
| What the command does, The publish set, The scanner level, The tag, The push, The options, The release record, The limits | Text, tables and code blocks. | Gap. These sections describe one release script. |

## 13. Reference

Page: `reference/index.mdx`. Template: `reference`. A script writes the whole page, and writes it again at each `scaffold`.

| Section of the tenant-pi page | Content | In the template |
| --- | --- | --- |
| Top of the page | `DocVersion` | Script: `DocVersion`. |
| Introduction, no heading | Three sentences. | Script: fixed sentences. |
| Troubleshooting | The path of the guide, and a table of its sections. | Script: the path, when a documentation file has "troubleshoot" in its name. The table is a gap. |
| Guides, Command line, Overlay, Modules, Concepts, Safety and release | One table for each subject, with the columns File, Topic, and for the command line also Page on this site. | Script: one table for each directory, with the columns File and Title. The title is the first heading of the file. The groups by subject and the column Topic are a gap. |
| Pages on this site | A list of links. | Script: one link for each planned page. |

## Components

| Component | In the tenant-pi pages | In the templates |
| --- | --- | --- |
| `DocVersion` | Each Overview, Install, Use and Reference page. No Develop page. | The same rule: each page of the release branch. The page needs the release of the project in `src/data/versions.json`. |
| `Capture` | The Install summary, Install stages 1 to 5, each command page, the task guide and two Develop pages. | One for each command slot. See "Command slots" in `docgen/README.md`. |
| `Cast` | Install stages 1 to 5 and the task guide. | Gap. |
| `Stage` | Not used. Each stage is a page. | Four blocks in `install`. |
| `Steps` | Each Install page. | In `install`: stage 1 from the script, stages 2 to 4 around a steps slot. |
| `Tabs`, `Aside` | Install stages 6 to 9. | Gap. |
| `CardGrid`, `LinkCard` | The overview, the Install summary, stage 9. | The overview. |
| `Shot` | Not used. | Not used. |
| A `mermaid` block | 24 blocks on 18 pages. | One script-made flowchart in `install`. Two diagrams for the second pass: `parts` in `overview` and `loop` in `workflow`. |

## Gaps in one list

| Gap | Reason | Proposal |
| --- | --- | --- |
| Task guide and concept page | The survey cannot find the subject. | After version one. A person names the page and its sources in the profile. |
| Worked example | It needs a choice of one real change. | A person writes it. |
| Repository layout, release gates and release as their own pages | The sources of most projects are too small for three pages. | One section each in `workflow`. Split them when a project has the sources. |
| One page for each install stage | A generated install has four short stages. | One page with four `Stage` blocks. |
| The diagram of one stage, of the roles, of the branches, of the gates | Each diagram is a second pass of a large model. | Two diagrams for each doc set in version one. |
| `Cast`, `Tabs`, `Aside` | Each needs a decision that a script cannot make. | A person adds them at the review. |
| Tables of special words | The overview gives the meaning of each word. | No change. |
| One page for each shell script or npm script | The survey has no help text and no action list for them. | The command summary has one row for each. |
