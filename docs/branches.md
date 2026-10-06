# Branches, tags and promotion

## Model

| Item | Role | Rule |
| --- | --- | --- |
| `origin` | Private development server | Holds `main`, topic branches and release refs. |
| `github` | GitHub copy in the owner account | Holds local `portable` as `main`, and release tags. |
| `main` | Development branch | Holds the spec work, tests and development history. |
| `topic/i<number>-<short-name>` | One work issue | Starts from `main` and returns through review. |
| `portable` | Release branch | Holds an orphan snapshot chain, not development commits. |
| `portable-v<major>.<minor>.<patch>` | Release tag | An unsigned annotated tag that never moves. |

This is a first-party repository. It has no `upstream` remote.
The GitHub repository has the name `tenant-docs` in the owner account.
The promotion command does not create that repository or change its visibility.

Warning: never push local `main` or a topic branch to GitHub.

## Snapshot chain

The first promotion creates an empty, parentless commit with the message `Bootstrap portable`.
The bootstrap is not a release. Each promotion adds one snapshot commit with the previous portable commit as its only parent.
The first release tag is `portable-v0.1.0`. Later tags have a higher version.

A snapshot copies the tree of `main`, except the paths in `scripts/portable-exclude`.
The list holds only `docs/agents/` and `.gitea/`. Directory entries remove each child.
`AGENTS.md` and `CLAUDE.md` stay in the snapshot. They point to the development tracker without an issue number.
The snapshot drops files that `main` removed. A temporary index leaves the checkout and its index unchanged.

The commit message is `Promote main <revision>`, with the full source revision.
The source revision is text only. It is not a parent of the snapshot.
The author, committer and tagger use `tenant-docs portable <portable@example.invalid>`.
The command makes unsigned objects even when Git has signing enabled.

`git commit-tree` creates the snapshot. `git mktag` creates the annotated tag object.
One guarded `git update-ref --stdin` transaction moves `portable` and creates the tag.
A concurrent ref change refuses the whole transaction.
A dry run can leave unreachable candidate objects. It changes no ref.

## Promotion

Run the command from a clean checkout with the tree of local `main`.
A topic checkout works only when its committed tree equals `main`.
A changed topic tree must reach `main` through review before promotion.
The command never checks out `portable`. No worktree can hold `portable` during promotion.

Run a dry run:

```sh
sh scripts/promote.sh
```

The dry run prints the candidate tree and the plan. It scans the snapshot and all candidate ancestors.
It needs a nonempty local deny list. A linked worktree uses the main checkout list when its own list is absent.
The dry run needs no remote access unless `--remote` is present.

Create the local release:

```sh
sh scripts/promote.sh --version 0.1.0
```

The version must match `package.json` and both root version fields of `package-lock.json` on `main`.
This command does not push. Check a clean clone of the tag with the repository checks before the push.

Push the same release to a public GitHub repository:

```sh
sh scripts/promote.sh --allow-public --version 0.1.0 --push --remote github
```

When the annotated tag names the current snapshot tree, `--push` resumes without writing local refs.
The tag must have the neutral tagger and the exact release message.
A later release uses a new version and the same command.
There is no new-root or force mode. A release never rewrites the chain.

Warning: promotion and publication need the maintainer's approval.

## Remote rules

| Remote | Branch sent | Tags sent |
| --- | --- | --- |
| `origin` | Local `portable` as `portable` | Only the named release tag. |
| `github` or another shared remote | Local `portable` as `main` | Only the named release tag. |

An explicit `--remote` checks the remote even in a dry run.
For a GitHub URL, `gh repo view` checks visibility. A public repository needs `--allow-public`.
A missing repository, a failed visibility check or an unknown result refuses the run.
A shared URL of unknown visibility also needs `--allow-public`.
`origin` must stay on the private development server. It must not have a GitHub URL.

A shared remote can hold only `main` and `portable-v*` tags.
The command also checks pull refs because they can retain history.
The remote branch must be an ancestor of the candidate.
Remote tags and pull refs must name ancestors in the same release chain.
An unknown remote object needs a fetch and a check before promotion.

The push uses two explicit refspecs. It disables automatic following of tags.
It runs `git push --dry-run` before the real push.
It never uses `--force`, `--all`, `--tags`, `--follow-tags` or `--mirror`.
The command does not read or print a credential.

## Refusals

The command refuses these states:

- A dirty tree, an untracked file, a shallow repository, grafts or replacement refs.
- A missing development branch or a checkout tree that differs from `main`.
- A worktree that holds `portable`, a remote named `upstream`, or a push URL named `DISABLED`.
- A missing origin, multiple origin push URLs, or a GitHub origin.
- A missing or invalid exclude list, or an excluded path that remains in the snapshot.
- A package version mismatch, an existing tag, or a version that does not increase.
- A missing local deny list or a scanner finding in the snapshot or any ancestor.
- A non-neutral identity, a signature, a nonempty bootstrap root, a merge, or an invalid snapshot message.
- `--push` without `--version`, or a missing push remote.
- URL userinfo, multiple push URLs, a public remote without `--allow-public`, or a remote ancestry failure.

The command reads the existing scanner rules in `scripts/host-values.regex` and `scripts/host-values.allow`.
It reads private patterns from the untracked `scripts/host-values.local.deny`.
It checks object content, file names, deploy-value files, submodules and excluded paths.
The scan reports rule names without matched values.
Every run scans the whole candidate chain, not a remote-relative range.

The existing hooks run the repository checks before a commit and scan the commit message.
They do not install a release push guard. The promotion command applies the release rules itself.

Warning: a manual Git push can bypass the promotion rules. Use the promotion command for release pushes.

## Checks

| Check | Command | Result |
| --- | --- | --- |
| Offline tests | `npm test` | Includes the temporary-repository promotion tests. |
| Repository gates | `bash scripts/check.sh` | Tests, build, links, scanner and Simplified English lint pass. |
| Local candidate | `sh scripts/promote.sh` | Excluded paths are absent and no ref changes. |
| Remote dry run | `sh scripts/promote.sh --allow-public --remote github` | Checks visibility and ancestry without a push. |

The offline tests use temporary local repositories and synthetic values.
They do not prove a real GitHub repository's visibility or the owner's acceptance.
