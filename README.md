# tenant-docs

tenant-docs is the documentation site for the tenant projects. It is a static site built with Astro Starlight in the Soft Night theme. tenant-pi is the first project with a full doc set. Each other project has one overview page.

Status: skeleton. The site builds, and the pages are stubs. The issues of this repository hold the spec (issue 1) and the work slices.

## Commands

| Command | Action |
| --- | --- |
| `npm ci` | Install the dependencies. |
| `npm run dev` | Start the local dev server. |
| `npm run build` | Build the site into `dist/`. |
| `npm run preview` | Serve `dist/` locally. |
| `scripts/deploy.sh` | Build the image and start the container on the proxy network. |

## Layout

| Path | Content |
| --- | --- |
| `src/content/docs/<project>/` | The pages of one project, in Markdown or MDX. The sidebar of the project comes from this directory. |
| `src/data/projects.json` | The project list. `docgen.py register` adds a project to it. |
| `src/data/projects.ts` | Reads and checks the project list. The home page, the project menu and the sidebar use it. |
| `src/data/versions.json` | The release of each project that the pages describe. |
| `src/components/` | The header with the project menu, and the page components. |
| `src/styles/soft-night.css` | The Soft Night tokens and their mapping to Starlight. |
| `src/sidebar.mjs` | Makes the sidebar entries of each project from its directory. |
| `src/routeData.ts` | Shows only the sidebar group of the current project. A page that belongs to no project shows no sidebar. |
| `captures/` | Real command output for the pages. See `captures/README.md`. |
| `compose.yaml`, `Dockerfile`, `deploy/` | The static-file container. |

## Projects and sidebar

`src/data/projects.json` lists the projects. Each entry has a `slug`, a `name`, a `summary` and the value `docs`. The value `docs` is `full` for a complete doc set and `overview` for one overview page. The slug is the name of the project directory in `src/content/docs/`.

To add a project, write its pages and run `python3 docgen/docgen.py register --project <project>`. Do this on a topic branch: `register` stops in a checkout that is on the branch `main`. See `docgen/README.md` for the variable `TENANT_DOCS_DIR` that the docgen skills need.

The sidebar of a project comes from its directory. A new page needs no change of `astro.config.mjs`.

| In the project directory | In the sidebar |
| --- | --- |
| `index.mdx` | The entry `Overview`. Each project must have this page. |
| A sub-directory that holds a page | A group. The groups `install`, `use`, `develop` and `reference` come first, in this order. Each other group follows, in the order of the names. |
| A page in a sub-directory | An entry of that group. The key `sidebar.order` of the page gives the position, and `sidebar.label` gives the label. |
| A sub-directory in a sub-directory | A group in the group. |
| Another page at the top of the directory | An entry after the groups. |

The label of a group is the name of its directory with a capital first letter: `how-to` gives `How to`. The directory `commands` has the label `Command reference`. `src/sidebar.mjs` holds these rules.

A page that belongs to no project shows no sidebar, for example `/style-guide/`.

## Page components

| Component | Use |
| --- | --- |
| `Capture` | A static terminal frame of one capture: the command with a copy button, and the output. |
| `Cast` | The same frame, with a button that plays the recording of the capture. |
| `Shot` | A screenshot with numbered callouts. |
| `Stage` | One numbered stage of a workflow, with a heading in the page outline. |
| `DocVersion` | A line that names the release that a page describes. |
| `Planned` | A note on a page that has no content yet. |

A fenced `mermaid` block is a diagram. The build renders it to inline SVG in the Soft Night colors. The supported types are flowchart, state, sequence, class, ER and XY chart. Another type stops the build. An arrow with a cross or a circle at its end, for example `--x`, also stops the build.

The build makes a second form of a flowchart and of a state diagram for a narrow column. That form goes from the top to the bottom, and no label in it is smaller than 11 px. So do not write "left" or "right" in the text about a diagram. The text form of a diagram shows the title of a subgraph, so the id of a subgraph can be short.

The page `/style-guide/` shows each component with an example.

## Content rules

The site is public. These rules apply to each page, capture, image and commit.

- No value of one host: no host name, user name, home path, internal URL, IP address or credential.
- Use placeholders, for example `docs.example` and `~/tenant-pi`.
- Deploy values come from `.env`. Git ignores `.env`. `.env.example` lists the variables.
- Write in Simplified English: one idea in each sentence, active voice, one action in each step. A warning is its own line and starts with `Warning:`.
- Terminal output comes from a capture. Do not type output into a page.
- One exception: output that names a commit, a tag or an issue of a private branch. Show it as a `text` block with the title `Example` and neutral values. The line before the block says "It is not a capture."
- A page shows each command one time. A command with a capture shows in the frame of the capture, and the step has no code block for it.
- Install and Use pages of a project describe its `portable` release and show the release with `DocVersion`. Develop pages describe the `main` branch.

## Checks

`scripts/check.sh` runs each check. The CI workflow `.gitea/workflows/check.yaml` runs it on each push and each pull request.

| Check | Command | The check fails when |
| --- | --- | --- |
| Tests | `npm test` | A test of the check scripts fails. |
| Build | `npm run build` | The build has an error. |
| Links | `scripts/check_links.py` | A page in `dist/` has a broken internal link or a broken anchor. |
| Scanner | `scripts/scan.py` | A tracked file, a capture or a file in `dist/` holds a host value or a credential. |
| Lint | `scripts/lint_ste.py` | A page breaks a Simplified English rule, and the lint is a gate. |

The checks need Python 3, Node.js and Git. They need no package.

### Tests

`npm test` runs `scripts/run_tests.py`. `scripts/check.sh` runs the same script.

- The runner starts each file `tests/test_*.py` in its own process.
- Some files run at the same time: one file for each processor, and 8 files at most. The option `--jobs` gives another number.
- The runner prints the output of each file that passes, in the order of the file names. Then it prints the output of each file that fails.
- Then it prints one line for each failed test, and 10 such lines at most. The line starts with `FAIL  test` and names the file.
- The last line gives the number of failed files, of files and of tests, and the time.
- The exit code is 1 when a file fails. It is 2 when the directory has no test file.

Two test files can run at the same time. So each test makes its own temporary directory, and no test writes to a fixed path.

`python3 -m unittest discover -s tests` runs the same tests in one process. That command takes more time. To run one file, give its name: `python3 -m unittest discover -s tests -p test_scan.py`.

### Hooks

Run `scripts/install-hooks.sh` one time in a clone. The script writes two Git hooks.

- `pre-commit` runs `scripts/check.sh` before each commit.
- `commit-msg` scans the commit message for host values and credentials.

Each linked worktree of the clone uses the same hooks.

Git gives the variables `GIT_DIR` and `GIT_INDEX_FILE` to a hook. The hook and `scripts/check.sh` remove them, so that a test with its own Git repository does not write into the clone. `docgen/docgen.py` removes them too, before it runs a Git command.

### Scanner

The scanner reads three rule files in `scripts/`.

| File | Content | Tracked |
| --- | --- | --- |
| `host-values.regex` | Generic regular expressions for private addresses, home paths, install paths, internal URLs and credentials. | Yes |
| `host-values.allow` | Exact values that a generic rule accepts. | Yes |
| `host-values.local.deny` | The literal values of your host, for example the machine name, a private domain and each user name. | No |

Make the local deny list before you write pages.

1. Copy `scripts/host-values.local.deny.example` to `scripts/host-values.local.deny`. Git ignores the copy.
2. Put one value of your host on each line of the copy. The report shows the rule number of such a value, not the value.

Warning: Do not put a value of your host into a tracked rule file.

- The character before a private IPv4 address decides if the scanner reports it: a version pin such as `pkg>=1.2.3.4` gives no finding. The built site writes inline code as a tag, then the address. So one rule reports an address directly after the end of a tag. Two more rules report an address after a tag that ends on a second line, and after the end of an HTML comment.
- A home path counts only at its start. A path directly after `://` is at its start too: a `file` URL has no host name before its path. So the scanner reports the home directory of a user, and of the administrator, in such a URL.
- The scan of `dist/` does not read `dist/.prerender`. A build that fails leaves the work files of the build tool there, and a build that passes removes them.
- `docgen.py check` gives the pages, the state file and the capture specs of one project to the scanner by their paths. So it finds a value before Git tracks the file. See `docgen/README.md`.

A linked worktree uses the local deny list of the main checkout. The CI job has no local deny list. To give it one, put the lines into the repository secret `HOST_VALUES_DENY`.

### Simplified English lint

The lint reads the pages in `src/content/docs/`. It prints the file and the line of each finding.

| Rule | Finding |
| --- | --- |
| `sentence-length` | A sentence has more than 20 words in a step, or more than 25 words in other text. |
| `warning-form` | A warning is not on its own line, or it does not start with `Warning:`. |
| `step-actions` | A step has more than one action. |
| `example-form` | A `text` block does not have the title `Example`, or the line before it does not say "It is not a capture." |

A step is an item of a numbered list. The lint does not read the content of a code block.

The lint is a gate: a finding fails the check. To make it a report again, set `LINT_MODE=report` in `scripts/check.sh`.

## Deploy

The site runs as one container with the name `tenant-docs`. The container serves the static files with nginx on port 8080 of the proxy network. It publishes no port on the host. TLS ends at the reverse proxy of the host.

| File | Content |
| --- | --- |
| `.env` | The deploy values `SITE_URL` and `DOCKER_PROXY_NETWORK`. Git ignores it. |
| `Dockerfile`, `compose.yaml` | The image and the container. |
| `deploy/nginx.conf` | The server: cache rules, compression and security headers. |
| `deploy/check-site.sh` | The checks of a site that runs. |
| `deploy/caddy-route.example` | The reverse proxy route, with `docs.example` as the host. |
| `scripts/deploy.sh` | The actions `deploy`, `check`, `rollback` and `route`. |

### Deploy the site

1. Copy `.env.example` to `.env`. Git ignores `.env`.
2. Set `SITE_URL` in `.env` to the public origin of the site. The build writes it into the canonical links and the sitemap.
3. Set `DOCKER_PROXY_NETWORK` in `.env` to the Docker network of the reverse proxy. This variable has no default.
4. Run `scripts/deploy.sh`. It builds the image, starts the container and runs the checks.
5. Read the output. Each check line starts with `ok`, and the exit status is 0.

Run `scripts/deploy.sh` again for each later change. The old container serves the site during the build. The site is absent only while the container restarts.

### Add the route

Do this one time, after the first deploy.

1. Run `scripts/deploy.sh route`. It prints the route: the host of `SITE_URL` goes to `tenant-docs:8080`.
2. Add the route to the configuration of the reverse proxy. The script does not change the reverse proxy.
3. Load the new configuration into the reverse proxy.
4. Run `sh deploy/check-site.sh https://docs.example` with your origin. The same checks then go through the reverse proxy.

Warning: many services can share the configuration of the reverse proxy. Get the approval of its owner before you change it.

The printed route is in Caddyfile syntax. For a different reverse proxy, write the same rule in its syntax. The public host name needs a DNS record that points to the reverse proxy.

### The checks

`scripts/deploy.sh check` runs `deploy/check-site.sh` in a second container on the proxy network. That container asks the site by its name, as the reverse proxy does.

| Request | Expected result |
| --- | --- |
| The home page | Status 200, the security headers, `Cache-Control: no-cache`, gzip compression. |
| A nested page | Status 200. |
| A missing page | Status 404, and the body is the 404 page. |
| A file under `/_astro/` | Status 200 and a cache time of one year. |
| A missing file under `/_astro/` | Status 404 and no cache time of one year. |

### Roll back

`scripts/deploy.sh` keeps the image of the deploy before as `tenantlab/tenant-docs:previous`. It keeps one such image.

1. Run `scripts/deploy.sh rollback`. It starts the image of the deploy before and runs the checks.
2. Correct the source, or go back to a good commit with Git.
3. Run `scripts/deploy.sh` again. The site then agrees with the checkout.

A second `scripts/deploy.sh rollback` returns to the newer image.

Warning: a rollback does not change the checkout. A deploy from the same source starts the faulty site again.

To stop the site, run `docker compose down`. The reverse proxy then gives an error for the host of the site.

## Public copy

`main` is the development branch. `portable` is the release branch. It has an empty bootstrap root and one snapshot commit per promotion. Development history stays on `main`.

The private remote `origin` holds development. The remote `github` points to `tenant-docs` in the owner account. It receives local `portable` as `main`. This first-party repository has no `upstream` remote.

Release tags have the form `portable-v<major>.<minor>.<patch>`. The first release is `portable-v0.1.0`. The snapshot and tag use a neutral identity and have no signature.

`scripts/portable-exclude` lists only `docs/agents/` and `.gitea/`. These paths stay out of each snapshot. `AGENTS.md` and `CLAUDE.md` stay in it.

Run the dry run in a clean checkout of `main`:

```sh
sh scripts/promote.sh
```

Create the local snapshot and tag:

```sh
sh scripts/promote.sh --version 0.1.0
```

Check a clean clone of the tag before the push. A public GitHub repository needs `--allow-public`:

```sh
sh scripts/promote.sh --allow-public --version 0.1.0 --push --remote github
```

Warning: do not push development branches or development history to GitHub.

See [docs/branches.md](docs/branches.md) for the promotion rules and checks.

## New release of a project

The Install and Use pages of a project describe one release. `src/data/versions.json` holds that release, and `DocVersion` shows it on a page. A release is a tag of the release branch of the project.

A release tag has one of two forms. A project uses one form.

| Form | Example | Rules of the form |
| --- | --- | --- |
| `<branch>-v<major>.<minor>.<patch>` | `portable-v1.2.0` | Three numbers. A number has no zero before it: `portable-v01.2.0` is not a release. |
| `<branch>/<date>-<hash>` | `portable/20260103-3c4d5e6` | A date of 8 digits, and a hexadecimal hash of 7 to 40 characters in lowercase. |

The value `branch` of the project in `src/data/versions.json` gives `<branch>`. A tag of another form is not a release, for example `portable/wip` or `portable-validated`.

Each release gets a tag. No script accepts a commit as a release.

The newest release of a source comes from the names of its tags:

| The source holds | The newest release |
| --- | --- |
| Tags of the version form | The highest version. The script compares the numbers one by one, so `1.10.0` is higher than `1.9.1`. The time of a tag has no effect. |
| Tags of the date form only | The tag with the latest date in its name. For the same date, the tag that was made last. For the same time, the last name in the order of the characters. |
| Tags of both forms | The highest version. A tag of the date form is then not the newest release. |

`docgen/release_tag.py` holds the two forms and this rule. `scripts/check-version.sh`, `docgen.py survey` and `docgen.py status` use that file, so each one gives the same release.

`scripts/check-version.sh` compares the newest release tag of a project source with `src/data/versions.json`.

| Exit code | Meaning |
| --- | --- |
| 0 | The documented release is the newest release of the source. |
| 1 | The source is ahead. The message names both releases. |
| 2 | The script has no source, the source has no release tag, Git cannot read the tags, or the source does not hold the documented release. |

The script needs `sh`, Git, Node.js and Python 3.

The source is a local clone of the project. Give its path as an argument, or set the variable `<PROJECT>_SOURCE` in `.env`, for example `TENANT_PI_SOURCE` or `TENANT_WEB_SOURCE`. The capture script runs this check first, so it does not record an old release.

Do these steps when a project has a new release:

1. Update the local clone of the project. The new release tag must be in the clone.
2. Run `scripts/check-version.sh tenant-pi`. It names the documented release and the newest release.
3. Set `release` in `src/data/versions.json` to the newest release.
4. Run `scripts/capture.py --project tenant-pi`. It records the captures of the Install and Use pages from the new release. It records the `dev-*` captures from the branch `main` of the clone.
5. Correct each capture that the script reports as failed. Then run the script again.
6. Read `git diff captures/`. Each changed line is a change that a reader sees. A second run of the script must change nothing.
7. Update each page that shows a changed capture, or that describes a changed command.
8. Record each manual capture again when its command or its output changed.
9. Run `npm run build`.
10. Commit `src/data/versions.json`, the captures and the pages together.

Warning: do not change `src/data/versions.json` without a new capture run. The pages then name a release that the captures do not show.

For a project with a doc set of docgen, the skill `tenant-docs-update` does steps 2, 3 and 7 on the branch `topic/docgen-update-<project>`. `docgen.py status` names the new release and prints the `register` command that sets it. The agent does not run the capture script. Its report says that the capture script must run for the new release. Do steps 4 to 6 on that branch before the merge.

See `captures/README.md` for the capture script.
