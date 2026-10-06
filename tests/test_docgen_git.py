"""Tests of the actions of docgen/docgen.py that use Git in the site: `branch`, `commit` and the guard of `main`.

Each test makes its own site in a temporary directory. The site is a Git repository with a copy of the
generator. Its remote `origin`, when a test needs one, is a bare repository in the same temporary directory.
No test uses the network, and no test writes into the repository that holds this file.
"""

import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_docgen as base  # noqa: E402  The fixture project and the helpers of the other docgen tests.

ROOT = Path(__file__).resolve().parent.parent
FIRST, UPDATE = 'topic/docgen-demo', 'topic/docgen-update-demo'
STATE = 'docgen/state/demo.json'


class GitSiteCase(unittest.TestCase):
    remote = True

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix='docgen-git-test-')).resolve()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.repo = self.tmp / 'demo'
        base.make_project(self.repo)

        # A site: the generator, an empty project list and one page of a person. Git ignores the work files.
        self.site = self.tmp / 'site'
        shutil.copytree(ROOT / 'docgen', self.site / 'docgen', ignore=shutil.ignore_patterns('state', '__pycache__'))
        (self.site / 'src' / 'content' / 'docs').mkdir(parents=True)
        (self.site / 'src' / 'data').mkdir()
        (self.site / 'src' / 'data' / 'projects.json').write_text('[]\n')
        (self.site / 'src' / 'data' / 'versions.json').write_text('{}\n')
        (self.site / 'README.md').write_text('# The site\n')
        (self.site / '.gitignore').write_text('.docgen/\n__pycache__/\n')
        self.docgen = str(self.site / 'docgen' / 'docgen.py')
        self.git('init', '-q', '-b', 'main')
        for name, value in (('user.name', 't'), ('user.email', 't@example.com'), ('commit.gpgsign', 'false'),
                            ('core.hooksPath', str(self.site / '.git' / 'hooks'))):
            self.git('config', name, value)
        self.git('add', '-A')
        self.git('commit', '-q', '-m', 'The site')
        self.origin = self.tmp / 'origin.git'
        if self.remote:
            self.assertEqual(base.run('git', 'init', '-q', '--bare', '-b', 'main', str(self.origin), cwd=self.tmp).returncode, 0)
            self.git('remote', 'add', 'origin', str(self.origin))
            self.git('push', '-q', 'origin', 'main')

    # ----- helpers -----

    def git(self, *words, cwd=None):
        done = base.run('git', *words, cwd=cwd or self.site)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        return done.stdout.rstrip()

    def docgen_run(self, *words):
        """Run one action in the project repository, as an agent does."""
        return base.run('python3', self.docgen, *words, cwd=self.repo)

    def ok(self, *words):
        done = self.docgen_run(*words)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        return done.stdout

    def command(self, action, *words):
        return ' '.join(('python3', self.docgen, action, '--project', 'demo', *words))

    def commit_of(self, ref, cwd=None):
        return self.git('rev-parse', ref, cwd=cwd)

    def branch(self):
        return base.run('git', 'symbolic-ref', '--quiet', '--short', 'HEAD', cwd=self.site).stdout.strip()

    def refs(self, cwd=None):
        return self.git('for-each-ref', '--format=%(refname) %(objectname)', cwd=cwd)

    def tree(self):
        """Each file of the site outside its Git directory and its work files, with its bytes."""
        return {str(path.relative_to(self.site)): path.read_bytes() for path in sorted(self.site.rglob('*'))
                if path.is_file() and not {'.git', '.docgen'} & set(path.relative_to(self.site).parts)}

    def page(self, path):
        return self.site / 'src' / 'content' / 'docs' / 'demo' / path

    def files_of(self, ref, cwd=None):
        return sorted(self.git('show', '--name-only', '--format=', ref, cwd=cwd).splitlines())

    def doc_set(self):
        """A full doc set with each slot written, on the branch of the run. Nothing is committed."""
        self.ok('survey', '--repo', '.')
        self.ok('branch', '--project', 'demo')
        self.ok('plan', '--project', 'demo')
        self.ok('scaffold', '--project', 'demo')
        for path in base.PAGES:
            base.fill(self.page(path))
        self.ok('scaffold', '--project', 'demo')
        self.ok('register', '--project', 'demo')

    def merged_doc_set(self):
        """The state after the review: the doc set is in `main`, here and on origin."""
        self.doc_set()
        self.ok('commit', '--project', 'demo')
        self.git('switch', '-q', 'main')
        self.git('merge', '-q', '--no-ff', FIRST, '-m', 'Merge the doc set of demo')
        if self.remote:
            self.git('push', '-q', 'origin', 'main')

    def hook(self, name, text, where=None):
        path = (where or self.site / '.git') / 'hooks' / name
        path.parent.mkdir(exist_ok=True)
        path.write_text('#!/bin/sh\n' + text)
        path.chmod(0o755)


RECORDER = '''#!/usr/bin/env python3
import json, os, sys
try:
    closed = os.path.samestat(os.fstat(0), os.stat(os.devnull))
except OSError:
    closed = True
with open(os.environ['GIT_RECORD'], 'a') as log:
    log.write(json.dumps({'words': sys.argv[1:], 'locks': os.environ.get('GIT_OPTIONAL_LOCKS'), 'no_input': closed}) + '\\n')
os.execv(os.environ['GIT_REAL'], ['git', *sys.argv[1:]])
'''


def recorded_git(case, words, cwd):
    """Run one action with a `git` program that records each of its calls, then runs the real Git.

    Each record holds the words of the call, the value of GIT_OPTIONAL_LOCKS and if the input of Git is closed.
    The action gets an open pipe as its input, as a hook and an agent program give it.
    """
    tools = case.tmp / 'tools'
    tools.mkdir(exist_ok=True)
    (tools / 'git').write_text(RECORDER)
    (tools / 'git').chmod(0o755)
    record = case.tmp / 'git-calls.jsonl'
    record.write_text('')
    env = {name: value for name, value in os.environ.items()
           if name not in (*base.GIT_LOCAL, 'SCAN_LOCAL_DENY', 'GIT_OPTIONAL_LOCKS')}
    env.update(PATH=f"{tools}{os.pathsep}{env['PATH']}", GIT_REAL=shutil.which('git'), GIT_RECORD=str(record))
    done = base.subprocess.run(['python3', case.docgen, *words], cwd=cwd, input='', capture_output=True, text=True, env=env)
    return done, [json.loads(line) for line in record.read_text().splitlines()]


class BranchTest(GitSiteCase):
    def test_branch_starts_at_the_main_of_origin_and_a_second_run_changes_nothing(self):
        # Another clone pushes one commit. The local `main` of the site is behind `origin/main`.
        other = self.tmp / 'other'
        self.git('clone', '-q', str(self.origin), str(other), cwd=self.tmp)
        self.git('-c', 'user.name=t', '-c', 'user.email=t@example.com', 'commit', '-q', '--allow-empty', '-m', 'Newer', cwd=other)
        self.git('push', '-q', 'origin', 'main', cwd=other)
        newest = self.commit_of('main', cwd=other)
        self.assertNotEqual(self.commit_of('main'), newest)

        out = self.ok('survey', '--repo', '.')
        self.assertEqual(base.next_command(out), self.command('branch'))
        out = self.ok('branch', '--project', 'demo')
        self.assertEqual(out.splitlines(), ['fetched  origin', f'started  {FIRST} at origin/main',
                                            'next     ' + self.command('plan')])
        self.assertEqual(self.branch(), FIRST)
        self.assertEqual(self.commit_of('HEAD'), newest)
        # The new branch has no upstream: `origin/main` is not the place of its push.
        self.assertNotEqual(base.run('git', 'rev-parse', '--abbrev-ref', '@{upstream}', cwd=self.site).returncode, 0)
        # `branch` moves no other branch.
        self.assertNotEqual(self.commit_of('main'), newest)

        refs, tree = self.refs(), self.tree()
        out = self.ok('branch', '--project', 'demo')
        self.assertEqual(out.splitlines(), ['fetched  origin', f'kept     {FIRST}: the site checkout is on this branch',
                                            'next     ' + self.command('plan')])
        self.assertEqual((self.refs(), self.tree()), (refs, tree))

    def test_branch_changes_to_a_branch_that_exists(self):
        self.git('switch', '-q', '-c', FIRST)
        self.git('commit', '-q', '--allow-empty', '-m', 'A run before this one')
        made = self.commit_of('HEAD')
        self.git('switch', '-q', 'main')
        out = self.ok('branch', '--project', 'demo')
        self.assertIn(f'resumed  {FIRST}: the branch exists', out.splitlines())
        self.assertEqual((self.branch(), self.commit_of('HEAD')), (FIRST, made))
        self.assertNotIn('note ', out)

    def test_branch_takes_a_branch_that_is_only_on_origin(self):
        other = self.tmp / 'other'
        self.git('clone', '-q', str(self.origin), str(other), cwd=self.tmp)
        self.git('switch', '-q', '-c', FIRST, cwd=other)
        self.git('-c', 'user.name=t', '-c', 'user.email=t@example.com', 'commit', '-q', '--allow-empty', '-m', 'Pushed', cwd=other)
        self.git('push', '-q', 'origin', FIRST, cwd=other)
        out = self.ok('branch', '--project', 'demo')
        self.assertIn(f'resumed  {FIRST}: the branch exists on origin', out.splitlines())
        self.assertEqual((self.branch(), self.commit_of('HEAD')), (FIRST, self.commit_of('HEAD', cwd=other)))
        self.assertEqual(self.git('rev-parse', '--abbrev-ref', '@{upstream}'), f'origin/{FIRST}')

    def test_branch_starts_from_a_detached_head(self):
        self.git('switch', '-q', '--detach', 'main')
        out = self.ok('branch', '--project', 'demo')
        self.assertIn(f'started  {FIRST} at origin/main', out.splitlines())
        self.assertEqual(self.branch(), FIRST)

    def test_branch_stops_in_a_checkout_that_is_not_clean(self):
        draft = self.site / 'src' / 'content' / 'docs' / 'demo' / 'draft.mdx'
        cases = (
            ('a changed tracked file', self.site / 'README.md', 'README.md'),
            ('a page that is not tracked', draft, 'src/content/docs/demo/draft.mdx'),
            ('a spec that is not tracked', self.site / 'captures' / 'demo' / 'help.json', 'captures/demo/help.json'),
            ('a state that is not tracked', self.site / 'docgen' / 'state' / 'other.json', 'docgen/state/other.json'),
        )
        for case, path, name in cases:
            with self.subTest(case):
                before = path.read_bytes() if path.exists() else None
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('A change of a person.\n')
                refs, tree = self.refs(), self.tree()
                done = self.docgen_run('branch', '--project', 'demo')
                self.assertEqual(done.returncode, 2, done.stdout)
                self.assertEqual(done.stderr.strip(), f'error: the site checkout has changes that are not committed: {name}. '
                                 '`branch` changes the branch only in a clean checkout. Nothing changed. '
                                 'Stop and tell the user this line.')
                self.assertNotIn('next ', done.stdout)
                self.assertEqual((self.refs(), self.tree(), self.branch()), (refs, tree, 'main'))
                if before is None:
                    path.unlink()
                else:
                    path.write_bytes(before)
        # A file that is not tracked and is no part of a doc set does not stop the run.
        (self.site / 'notes.txt').write_text('A note of a person.\n')
        self.ok('branch', '--project', 'demo')
        self.assertEqual(self.branch(), FIRST)

    def test_branch_keeps_the_open_work_of_a_run_that_stopped(self):
        # A run stopped after `scaffold`. Its pages are not committed. A second start continues on the branch.
        self.ok('survey', '--repo', '.')
        self.ok('branch', '--project', 'demo')
        self.ok('plan', '--project', 'demo')
        self.ok('scaffold', '--project', 'demo')
        refs, tree = self.refs(), self.tree()
        out = self.ok('branch', '--project', 'demo')
        self.assertIn(f'kept     {FIRST}: the site checkout is on this branch', out.splitlines())
        self.assertEqual((self.refs(), self.tree()), (refs, tree))

    def test_branch_stops_when_origin_does_not_answer(self):
        shutil.rmtree(self.origin)
        refs, tree = self.refs(), self.tree()
        done = self.docgen_run('branch', '--project', 'demo')
        self.assertEqual(done.returncode, 2, done.stdout)
        # Git prints four lines. The first one names the cause. The last one is the end of a hint.
        self.assertEqual(done.stderr.strip(), f"error: Git cannot fetch from the remote origin of the site: '{self.origin}' does "
                         'not appear to be a git repository. Nothing changed. Stop and tell the user this line.')
        self.assertEqual((self.refs(), self.tree(), self.branch()), (refs, tree, 'main'))

    def test_a_stop_names_the_cause_that_git_gives(self):
        cause = base.docgen.git_cause
        self.assertEqual(cause("fatal: 'x.git' does not appear to be a git repository\nfatal: Could not read from remote "
                               'repository.\n\nPlease make sure you have the correct access rights\nand the repository exists.\n'),
                         "'x.git' does not appear to be a git repository")
        self.assertEqual(cause('error: The following untracked working tree files would be overwritten by checkout:\n'
                               '\tnotes.txt\n\tmore notes.txt\nPlease move or remove them before you switch branches.\nAborting\n'),
                         'The following untracked working tree files would be overwritten by checkout: notes.txt, more notes.txt')
        self.assertEqual(cause('The following paths are ignored by one of your .gitignore files:\nnotes.txt\n'
                               'hint: Use -f if you really want to add them.\nhint: "git config advice.addIgnoredFile false"\n'),
                         'The following paths are ignored by one of your .gitignore files: notes.txt')
        self.assertEqual(cause('warning: a warning\nfatal: Not possible to fast-forward, aborting.\n'),
                         'Not possible to fast-forward, aborting')
        self.assertEqual(cause('hint: only a hint\n\n'), 'Git gives no message')
        # A remote over SSH: Git prints its general line, and the line of SSH before it names the cause.
        general = ('fatal: Could not read from remote repository.\n\nPlease make sure you have the correct access rights\n'
                   'and the repository exists.\n')
        self.assertEqual(cause('ssh: connect to host git.example.com port 22: Connection refused\n' + general),
                         'ssh: connect to host git.example.com port 22: Connection refused. Could not read from remote repository')
        self.assertEqual(cause("Warning: Permanently added 'git.example.com' (ED25519) to the list of known hosts.\n"
                               'git@git.example.com: Permission denied (publickey).\n' + general),
                         'git@git.example.com: Permission denied (publickey). Could not read from remote repository')
        # With no line before it, or with a hint or a warning only, the general line is the cause.
        self.assertEqual(cause(general), 'Could not read from remote repository')
        self.assertEqual(cause('hint: a hint\n\nWarning: a warning of SSH\n' + general), 'Could not read from remote repository')

        # A file that is not tracked is in the way of the branch: the line names the cause and the file.
        self.git('switch', '-q', '-c', FIRST)
        (self.site / 'notes.txt').write_text('In the branch.\n')
        self.git('add', 'notes.txt')
        self.git('commit', '-q', '-m', 'A file of the branch')
        self.git('switch', '-q', 'main')
        (self.site / 'notes.txt').write_text('Not tracked.\n')
        done = self.docgen_run('branch', '--project', 'demo')
        self.assertEqual(done.returncode, 2, done.stdout)
        self.assertEqual(done.stderr.strip(), f'error: git switch --quiet {FIRST}: The following untracked working tree files '
                         'would be overwritten by checkout: notes.txt. Stop and tell the user this line.')
        self.assertEqual(self.branch(), 'main')

    def test_a_clone_that_fetches_only_main_takes_the_branch_of_origin(self):
        # `git clone --single-branch` gives this fetch rule. A plain fetch then brings `main` and no other branch.
        self.git('config', 'remote.origin.fetch', '+refs/heads/main:refs/remotes/origin/main')
        other = self.tmp / 'other'
        self.git('clone', '-q', str(self.origin), str(other), cwd=self.tmp)
        self.git('switch', '-q', '-c', FIRST, cwd=other)
        self.git('-c', 'user.name=t', '-c', 'user.email=t@example.com', 'commit', '-q', '--allow-empty', '-m', 'Pushed', cwd=other)
        self.git('push', '-q', 'origin', FIRST, cwd=other)
        out = self.ok('branch', '--project', 'demo')
        self.assertIn(f'resumed  {FIRST}: the branch exists on origin', out.splitlines())
        self.assertEqual((self.branch(), self.commit_of('HEAD')), (FIRST, self.commit_of('HEAD', cwd=other)))
        # A second run keeps the branch, and a branch that origin does not have starts at `main`.
        self.assertIn(f'kept     {FIRST}: the site checkout is on this branch', self.ok('branch', '--project', 'demo').splitlines())
        self.git('switch', '-q', 'main')
        self.git('branch', '-q', '-D', FIRST)
        self.git('push', '-q', 'origin', f':refs/heads/{FIRST}')
        self.git('update-ref', '-d', f'refs/remotes/origin/{FIRST}')
        self.assertIn(f'started  {FIRST} at origin/main', self.ok('branch', '--project', 'demo').splitlines())

    def test_a_tag_with_the_name_of_a_branch_does_not_hide_the_branch(self):
        # With a tag `main`, the short name of the branch is `heads/main`. The guard reads the full name.
        self.ok('survey', '--repo', '.')
        self.ok('plan', '--project', 'demo')
        self.git('tag', 'main', 'HEAD')
        tree = self.tree()
        done = self.docgen_run('scaffold', '--project', 'demo')
        self.assertEqual(done.returncode, 2, done.stdout)
        self.assertEqual(done.stderr.strip(), 'error: the site checkout is on the branch main, and `scaffold` writes a tracked '
                         'file. Nothing changed. Run first: ' + self.command('branch'))
        self.assertEqual(self.tree(), tree)
        # A tag with the name of the branch of the run: `branch` keeps the branch, and `commit` works on it.
        self.ok('branch', '--project', 'demo')
        self.git('tag', FIRST, 'HEAD')
        self.assertIn(f'kept     {FIRST}: the site checkout is on this branch', self.ok('branch', '--project', 'demo').splitlines())
        self.doc_set()
        out = self.ok('commit', '--project', 'demo')
        self.assertIn(f'pushed   {FIRST} to origin', out.splitlines())
        self.assertEqual(self.commit_of(f'refs/heads/{FIRST}'), self.commit_of(f'refs/heads/{FIRST}', cwd=self.origin))
        self.assertEqual(self.git('tag', '--list', cwd=self.origin), '')

    def test_branch_stops_for_a_name_that_is_no_project_and_in_a_site_with_no_git(self):
        # The word of a code block that the agent did not replace. Each of these actions checks the name first.
        for words in (('branch',), ('branch', '--update'), ('status',), ('diagrams',), ('commit',)):
            with self.subTest(action=words[0]):
                done = self.docgen_run(words[0], '--project', 'PROJECT', *words[1:])
                self.assertEqual(done.returncode, 2)
                self.assertEqual(done.stderr.strip(), "error: 'PROJECT' is not a project name of the site. Use the name of the "
                                 'project: `survey` prints it in its line `project`, and the directory of the project below '
                                 'src/content/docs/ of the site has this name.')
        shutil.rmtree(self.site / '.git')
        done = self.docgen_run('branch', '--project', 'demo')
        self.assertEqual(done.returncode, 2)
        self.assertIn('error: the site directory is no Git checkout', done.stderr)

    def test_a_first_doc_set_stops_when_the_doc_set_is_in_main(self):
        self.merged_doc_set()
        for start in ('main', FIRST):
            with self.subTest(start=start):
                self.git('switch', '-q', start)
                refs, tree = self.refs(), self.tree()
                done = self.docgen_run('branch', '--project', 'demo')
                self.assertEqual(done.returncode, 2, done.stdout)
                # The line says what each skill does: one skill stops, and two skills run the command at its end.
                self.assertEqual(done.stderr.strip(), "error: the doc set of 'demo' is in main already, so this is no first doc "
                                 'set. Nothing changed. In the skill tenant-docs-generate, stop and tell the user this line. '
                                 'In the skill tenant-docs-update and in the skill tenant-docs-diagrams, run: '
                                 + self.command('branch', '--update'))
                self.assertEqual((self.refs(), self.tree(), self.branch()), (refs, tree, start))
        # The first command of a skill says which run it is: `survey --update` names the branch of an update.
        self.assertEqual(base.next_command(self.ok('survey', '--repo', '.')), self.command('branch'))
        self.assertEqual(base.next_command(self.ok('survey', '--repo', '.', '--update')), self.command('branch', '--update'))

    def test_an_update_stops_when_the_doc_set_is_not_in_main(self):
        refs, tree = self.refs(), self.tree()
        done = self.docgen_run('branch', '--project', 'demo', '--update')
        self.assertEqual(done.returncode, 2, done.stdout)
        # The project list of the site does not have the name: the clone can have another name than the project.
        self.assertEqual(done.stderr.strip(), "error: the doc set of 'demo' is not in main, so an update is not possible. "
                         "The project list of the site has no project 'demo'. The names of the list are: (none). For a "
                         'project of the list, the first command of the skill needs the option `--project` with that name. '
                         'For a project that the list does not have, the skill tenant-docs-generate makes the first doc set. '
                         'Do not choose a name. Nothing changed. Stop and tell the user this line.')
        self.assertEqual((self.refs(), self.tree(), self.branch()), (refs, tree, 'main'))
        # The list has the name, and no branch holds a doc set: a person wrote the overview page of the project.
        projects = self.site / 'src' / 'data' / 'projects.json'
        projects.write_text(json.dumps([{'slug': 'demo', 'name': 'demo', 'summary': 'A thing.', 'docs': 'overview'}]) + '\n')
        self.git('commit', '-q', '-am', 'A project with an overview page')
        self.git('push', '-q', 'origin', 'main')
        done = self.docgen_run('branch', '--project', 'demo', '--update')
        self.assertEqual(done.stderr.strip(), "error: the doc set of 'demo' is not in main, so an update is not possible. "
                         'No branch holds it: the skill tenant-docs-generate makes it. Nothing changed. '
                         'Stop and tell the user this line.')
        projects.write_text('[]\n')
        self.git('commit', '-q', '-am', 'An empty project list')
        self.git('push', '-q', 'origin', 'main')

        # The doc set waits for its review on its branch: local, or only on origin.
        self.doc_set()
        self.ok('commit', '--project', 'demo')
        for where in ('local', 'origin'):
            with self.subTest(where=where):
                self.git('switch', '-q', 'main')
                if where == 'origin':
                    self.git('branch', '-q', '-D', FIRST)
                refs, tree = self.refs(), self.tree()
                done = self.docgen_run('branch', '--project', 'demo', '--update')
                self.assertEqual(done.returncode, 2, done.stdout)
                self.assertEqual(done.stderr.strip(), "error: the doc set of 'demo' is not in main, so an update is not "
                                 f'possible. The branch {FIRST} holds it: it waits for the review. Nothing changed. '
                                 'Stop and tell the user this line.')
                self.assertEqual((self.refs(), self.tree(), self.branch()), (refs, tree, 'main'))
                # `status` and `diagrams` name the same cause, and no `scaffold`.
                for words in (('status', '--project', 'demo', '--repo', '.'), ('diagrams', '--project', 'demo')):
                    done = self.docgen_run(*words)
                    self.assertEqual(done.returncode, 2, done.stdout)
                    self.assertEqual(done.stderr.strip(), "error: this checkout of the site has no doc set of 'demo': the "
                                     f'file docgen/state/demo.json is absent. The branch {FIRST} holds it: it waits for the '
                                     'review. Stop and tell the user this line.')

    def test_an_update_starts_its_branch_and_moves_a_merged_branch_forward(self):
        self.merged_doc_set()
        # With the doc set in `main`, a checkout of an old commit has no state. `status` names the branch step.
        self.git('switch', '-q', '--detach', 'main~1')
        done = self.docgen_run('status', '--project', 'demo', '--repo', '.')
        self.assertEqual(done.returncode, 2, done.stdout)
        self.assertEqual(done.stderr.strip(), "error: this checkout of the site has no doc set of 'demo': the file "
                         'docgen/state/demo.json is absent. The doc set is in main. Run first: '
                         + self.command('branch', '--update'))
        out = self.ok('branch', '--project', 'demo', '--update')
        self.assertEqual(out.splitlines(), ['fetched  origin', f'started  {UPDATE} at origin/main',
                                            'next     ' + self.command('plan')])
        self.assertEqual((self.branch(), self.commit_of('HEAD')), (UPDATE, self.commit_of('main')))

        # The owner merges the update. `main` gets one more commit. The next update moves the old branch forward.
        self.git('commit', '-q', '--allow-empty', '-m', 'The first update')
        self.git('switch', '-q', 'main')
        self.git('merge', '-q', '--no-ff', UPDATE, '-m', 'Merge the first update')
        self.git('commit', '-q', '--allow-empty', '-m', 'One more commit')
        self.git('push', '-q', 'origin', 'main')
        for start in ('main', UPDATE):
            with self.subTest(start=start):
                self.git('switch', '-q', start)
                out = self.ok('branch', '--project', 'demo', '--update')
                self.assertIn(f'moved    {UPDATE} to the newest commit of origin/main, with a fast-forward', out.splitlines())
                self.assertEqual((self.branch(), self.commit_of('HEAD')), (UPDATE, self.commit_of('main')))
                self.assertNotIn('note ', out)
                self.git('switch', '-q', 'main')
                self.git('commit', '-q', '--allow-empty', '-m', 'A later commit')
                self.git('push', '-q', 'origin', 'main')

    def test_branch_never_moves_a_branch_that_has_its_own_commit(self):
        self.merged_doc_set()
        self.ok('branch', '--project', 'demo', '--update')
        self.git('commit', '-q', '--allow-empty', '-m', 'An update that waits for the review')
        own = self.commit_of('HEAD')
        self.git('switch', '-q', 'main')
        self.git('commit', '-q', '--allow-empty', '-m', 'A later commit')
        self.git('push', '-q', 'origin', 'main')
        for start in ('main', UPDATE):
            with self.subTest(start=start):
                self.git('switch', '-q', start)
                out = self.ok('branch', '--project', 'demo', '--update')
                self.assertEqual((self.branch(), self.commit_of('HEAD')), (UPDATE, own))
                self.assertNotIn('moved', out)
                self.assertIn(f'note     {UPDATE} does not hold 1 commit(s) of origin/main. The scripts of this checkout can '
                              'be old. Continue, and put this line into your report.', out.splitlines())
        # No branch is gone, and `main` is where it was.
        self.assertIn(FIRST, self.git('branch', '--list', FIRST))


class NoRemoteTest(GitSiteCase):
    remote = False

    def test_branch_starts_at_the_local_main_of_a_site_with_no_remote(self):
        out = self.ok('branch', '--project', 'demo')
        self.assertEqual(out.splitlines(), [f'started  {FIRST} at main', 'next     ' + self.command('plan')])
        self.assertEqual((self.branch(), self.commit_of('HEAD')), (FIRST, self.commit_of('main')))
        refs, tree = self.refs(), self.tree()
        out = self.ok('branch', '--project', 'demo')
        self.assertEqual(out.splitlines(), [f'kept     {FIRST}: the site checkout is on this branch',
                                            'next     ' + self.command('plan')])
        self.assertEqual((self.refs(), self.tree()), (refs, tree))

    def test_commit_makes_the_commit_and_stops_at_the_push(self):
        self.doc_set()
        done = self.docgen_run('commit', '--project', 'demo')
        self.assertEqual(done.returncode, 1, done.stdout)
        self.assertEqual(done.stderr.strip(), f'error: the site has no remote origin, so the branch {FIRST} is not pushed. '
                         'Stop and tell the user this line.')
        self.assertEqual(self.git('log', '-1', '--format=%s'), 'Docs of demo: first doc set from docgen')
        # With the option, the action ends with no push and no error.
        out = self.ok('commit', '--project', 'demo', '--no-push')
        self.assertIn(f'kept     {FIRST}: the last commit holds each file of the doc set. Nothing to commit.', out.splitlines())
        self.assertIn(f'done     the branch {FIRST} is not pushed (--no-push). Tell the user the result. Do not merge.',
                      out.splitlines())


class GuardTest(GitSiteCase):
    def test_scaffold_and_register_stop_on_main_and_on_a_detached_head(self):
        self.ok('survey', '--repo', '.')
        self.ok('plan', '--project', 'demo')
        for where, words in (('is on the branch main', ()), ('has a detached HEAD', ('--detach',))):
            self.git('switch', '-q', *words, 'main')
            for action, more in (('scaffold', ()), ('register', ('--docs', 'overview', '--summary', 'A project.'))):
                with self.subTest(where=where, action=action):
                    tree = self.tree()
                    done = self.docgen_run(action, '--project', 'demo', *more)
                    self.assertEqual(done.returncode, 2, done.stdout)
                    self.assertEqual(done.stderr.strip(), f'error: the site checkout {where}, and `{action}` writes a tracked '
                                     'file. Nothing changed. Run first: ' + self.command('branch'))
                    self.assertEqual(self.tree(), tree)
                    self.assertEqual(self.git('status', '--porcelain'), '')
        # On the branch of the run, both actions work. The line of the guard names the command that goes there.
        self.ok('branch', '--project', 'demo')
        self.ok('scaffold', '--project', 'demo')
        self.assertTrue(self.page('index.mdx').exists())
        self.ok('register', '--project', 'demo')

    def test_the_guard_names_the_update_branch_when_the_doc_set_is_in_main(self):
        self.merged_doc_set()
        self.assertEqual(self.branch(), 'main')
        done = self.docgen_run('scaffold', '--project', 'demo')
        self.assertEqual(done.returncode, 2, done.stdout)
        self.assertTrue(done.stderr.strip().endswith('Run first: ' + self.command('branch', '--update')), done.stderr)

    def test_a_person_can_register_a_project_on_another_topic_branch(self):
        self.git('switch', '-q', '-c', 'topic/i20-new-project')
        self.page('index.mdx').parent.mkdir(parents=True)
        self.page('index.mdx').write_text('---\ntitle: demo\ndescription: "The page of demo."\n---\n\nThe text.\n')
        out = self.ok('register', '--project', 'demo', '--docs', 'overview')
        self.assertIn('added    demo', out)


class CommitTest(GitSiteCase):
    def doc_set_files(self):
        state = json.loads((self.site / STATE).read_text())
        return sorted([f'src/content/docs/demo/{path}' for path in state['pages']]
                      + [f'captures/demo/{name}.json' for name in state['captures']]
                      + [STATE, 'src/data/projects.json', 'src/data/versions.json'])

    def test_the_next_lines_go_from_survey_to_commit_and_a_second_run_changes_nothing(self):
        elsewhere = self.tmp / 'elsewhere'
        elsewhere.mkdir()

        def follow(line):
            """Run the command of each `next` line in a new shell and in another directory. Write each slot."""
            actions = []
            while len(actions) < 80:
                words = line.split()
                done = base.run('sh', '-c', line, cwd=elsewhere)
                self.assertEqual(done.returncode, 0, f'{line}\n{done.stdout}{done.stderr}')
                actions.append(words[2])
                if words[2] == 'check':
                    # The site of this test has no checks of its own, so `check` prints no `next` line.
                    # tests/test_docgen_register.py reads that line: it names `commit`.
                    return actions
                found = base.re.search(r'(?m)^page +(.+)\nslot +([\w-]+) ', done.stdout)
                if found:
                    page = Path(found.group(1))
                    slot = next(slot for slot in base.docgen.slots_of(page.read_text()) if slot['id'] == found.group(2))
                    base.fill(page, slot['id'], base.sample(slot))
                line = base.next_command(done.stdout)

        first = base.next_command(self.ok('survey', '--repo', '.'))
        actions = follow(first)
        slots = sum(len(base.docgen.slots_of(self.page(path).read_text())) for path in base.PAGES)
        self.assertEqual(actions, ['branch', 'plan', 'scaffold'] + ['next'] * (slots + 1) + ['scaffold', 'register', 'check'])
        out = self.ok('commit', '--project', 'demo')
        self.assertEqual(self.git('status', '--porcelain', '--untracked-files=all'), '')
        self.assertEqual(self.commit_of(FIRST), self.commit_of(f'refs/heads/{FIRST}', cwd=self.origin))
        self.assertIn(f'pushed   {FIRST} to origin', out.splitlines())

        # A second start of the run: each command ends with 0, and no file, no branch and no commit changes.
        refs, tree, remote = self.refs(), self.tree(), self.refs(cwd=self.origin)
        self.assertEqual(follow(base.next_command(self.ok('survey', '--repo', '.'))),
                         ['branch', 'plan', 'scaffold', 'register', 'check'])
        out = self.ok('commit', '--project', 'demo')
        self.assertEqual(out.splitlines(), [
            f'kept     {FIRST}: the last commit holds each file of the doc set. Nothing to commit.',
            f'kept     origin has each commit of {FIRST}. Nothing to push.',
            f'done     the branch {FIRST} waits for the review. Tell the user the result. Do not merge.'])
        self.assertEqual((self.refs(), self.tree(), self.refs(cwd=self.origin)), (refs, tree, remote))

    def test_commit_holds_only_the_files_of_the_doc_set(self):
        self.doc_set()
        # A draft of a person in the directory of the project, a changed tracked file, and a file that a person staged.
        self.page('draft.mdx').write_text('---\ntitle: Draft\n---\n\nA draft of a person.\n')
        (self.site / 'captures' / 'demo' / 'help.txt').write_text('Output that a person recorded.\n')
        (self.site / 'README.md').write_text('# The site\n\nA change of a person.\n')
        (self.site / 'notes.md').write_text('A note of a person.\n')
        self.git('add', 'notes.md')
        main, remote_main = self.commit_of('main'), self.commit_of('refs/heads/main', cwd=self.origin)

        out = self.ok('commit', '--project', 'demo')
        files = self.doc_set_files()
        self.assertEqual(len(files), 7 + 9 + 3)
        self.assertEqual(self.files_of('HEAD'), files)
        self.assertEqual(self.git('log', '-1', '--format=%B'), 'Docs of demo: first doc set from docgen')
        self.assertEqual([line.split()[1] for line in out.splitlines() if line.startswith('staged ')], files)
        for path in ('src/content/docs/demo/draft.mdx', 'captures/demo/help.txt'):
            self.assertIn(f'skipped  {path}: docgen did not write it. It is not in the commit.', out.splitlines())
        self.assertRegex(out, r'(?m)^commit   [0-9a-f]{7,} Docs of demo: first doc set from docgen$')
        # The work of the person is where it was: not in the commit, and the staged file is staged.
        self.assertEqual(sorted(self.git('status', '--porcelain', '--untracked-files=all').splitlines()),
                         sorted([' M README.md', 'A  notes.md', '?? captures/demo/help.txt', '?? src/content/docs/demo/draft.mdx']))
        # The push: the branch of the run and no other ref.
        self.assertEqual(self.refs(cwd=self.origin).splitlines(),
                         [f'refs/heads/main {remote_main}', f'refs/heads/{FIRST} {self.commit_of("HEAD")}'])
        self.assertEqual(self.commit_of('main'), main)
        self.assertEqual(self.git('rev-parse', '--abbrev-ref', '@{upstream}'), f'origin/{FIRST}')
        self.assertEqual(out.splitlines()[-2:], [
            f'pushed   {FIRST} to origin',
            f'done     the branch {FIRST} waits for the review. Tell the user the result. Do not merge.'])

    def test_commit_pushes_no_tag(self):
        self.doc_set()
        self.git('tag', '-a', '-m', 'A tag of a person', 'v9', 'main')
        self.git('config', 'push.followTags', 'true')
        self.ok('commit', '--project', 'demo')
        self.assertEqual(self.git('tag', '--list', cwd=self.origin), '')

    def test_commit_stops_on_a_branch_that_is_not_the_branch_of_the_run(self):
        self.doc_set()
        for where, words in (('is on the branch topic/i20-other', ('-c', 'topic/i20-other')),
                             ('is on the branch main', ('main',)), ('has a detached HEAD', ('--detach', 'main'))):
            with self.subTest(where=where):
                self.git('switch', '-q', *words)
                refs, remote = self.refs(), self.refs(cwd=self.origin)
                done = self.docgen_run('commit', '--project', 'demo')
                self.assertEqual(done.returncode, 2, done.stdout)
                self.assertEqual(done.stderr.strip(), f'error: the site checkout {where}. `commit` works only on the branch '
                                 f'{FIRST} or {UPDATE}. Nothing changed. Run first: ' + self.command('branch'))
                self.assertEqual((self.refs(), self.refs(cwd=self.origin)), (refs, remote))
                # Nothing is staged.
                self.assertEqual(self.git('diff', '--cached', '--name-only'), '')

    def test_the_message_of_an_update_names_a_new_release(self):
        self.merged_doc_set()
        self.ok('branch', '--project', 'demo', '--update')
        # A change of a page with no new release.
        page = self.page('install/index.mdx')
        page.write_text(page.read_text().replace('word word word', 'word word text', 1))
        out = self.ok('commit', '--project', 'demo')
        self.assertEqual(self.git('log', '-1', '--format=%B'), 'Docs of demo: update')
        self.assertEqual(self.files_of('HEAD'), ['src/content/docs/demo/install/index.mdx'])
        self.assertIn(f'pushed   {UPDATE} to origin', out.splitlines())
        # The project gets a release. `scaffold` records it, and `register` sets it.
        self.git('-c', 'user.name=t', '-c', 'user.email=t@example.com', 'tag', 'portable-v0.2.0', 'portable', cwd=self.repo)
        self.ok('survey', '--repo', '.')
        self.ok('plan', '--project', 'demo')
        self.ok('scaffold', '--project', 'demo')
        self.ok('register', '--project', 'demo')
        self.ok('commit', '--project', 'demo')
        self.assertEqual(self.git('log', '-1', '--format=%B'), 'Docs of demo: update to portable-v0.2.0')
        self.assertEqual(self.files_of('HEAD'), [STATE, 'src/data/versions.json'])
        self.assertEqual(self.commit_of(UPDATE), self.commit_of(f'refs/heads/{UPDATE}', cwd=self.origin))

    def test_the_commit_of_the_diagram_pass(self):
        self.doc_set()
        self.ok('commit', '--project', 'demo')
        page = self.page('index.mdx')
        page.write_text(page.read_text().replace('{/* docgen:diagram parts | pending |', '{/* docgen:diagram parts | done |'))
        self.ok('commit', '--project', 'demo', '--diagrams')
        self.assertEqual(self.git('log', '-1', '--format=%B'), 'Docs of demo: diagrams')
        self.assertEqual(self.files_of('HEAD'), ['src/content/docs/demo/index.mdx'])

    def test_commit_holds_the_removal_of_a_spec_that_scaffold_removed(self):
        self.doc_set()
        self.ok('commit', '--project', 'demo')
        # The sources state no test of the install. `scaffold` removes the frame and the spec of that stage.
        page = self.page('install/index.mdx')
        page.write_text(page.read_text().replace(
            '{/* docgen:command\npython3 scripts/cli.py build\n*/}\n{/* docgen:end */}\n\n{/* docgen:with stage-4-command',
            '{/* docgen:command\nThe sources state no test of the install.\n*/}\n{/* docgen:end */}\n\n{/* docgen:with stage-4-command'))
        out = self.ok('scaffold', '--project', 'demo')
        self.assertIn('removed  captures/demo/stage4-check.json', out)
        out = self.ok('commit', '--project', 'demo')
        self.assertEqual(self.files_of('HEAD'), ['captures/demo/stage4-check.json', STATE, 'src/content/docs/demo/install/index.mdx'])
        self.assertEqual(self.git('show', '--format=', '--diff-filter=D', '--name-only', 'HEAD'), 'captures/demo/stage4-check.json')
        self.assertEqual(self.git('status', '--porcelain', '--untracked-files=all'), '')

    def test_commit_holds_the_removal_of_a_spec_when_a_new_spec_has_a_near_text(self):
        # Stage 3 has no command, and stage 4 has one. So the first commit holds the spec of stage 4 only.
        self.ok('survey', '--repo', '.')
        self.ok('branch', '--project', 'demo')
        self.ok('plan', '--project', 'demo')
        self.ok('scaffold', '--project', 'demo')
        for path in base.PAGES:
            base.fill(self.page(path))
        page = self.page('install/index.mdx')
        commands = '{/* docgen:command\n%s\n*/}\n{/* docgen:end */}\n\n{/* docgen:with stage-%d-command'
        no_start, no_test = 'The sources state no command that starts the project.', 'The sources state no test of the install.'
        build = 'python3 scripts/cli.py build'
        text = page.read_text()
        self.assertEqual((text.count(commands % (build, 3)), text.count(commands % (build, 4))), (1, 1))
        page.write_text(text.replace(commands % (build, 3), commands % (no_start, 3)))
        self.ok('scaffold', '--project', 'demo')
        self.ok('register', '--project', 'demo')
        self.ok('commit', '--project', 'demo')
        specs = ('captures/demo/stage3-start.json', 'captures/demo/stage4-check.json')
        self.assertEqual([path for path in self.git('ls-files', 'captures/demo').splitlines() if 'stage' in path and path in specs],
                         [specs[1]])

        # An update gives the command to stage 3 and takes it from stage 4. The new spec and the removed spec
        # hold the same command, so Git reads the two files as one file with a new name.
        text = page.read_text()
        page.write_text(text.replace(commands % (no_start, 3), commands % (build, 3))
                        .replace(commands % (build, 4), commands % (no_test, 4)))
        out = self.ok('scaffold', '--project', 'demo')
        self.assertIn('removed  captures/demo/stage4-check.json: the page has no frame for this capture', out.splitlines())
        self.assertRegex(out, r'(?m)^wrote    captures/demo/stage3-start\.json: scripted$')
        self.git('add', '-A', 'captures/demo')
        self.assertRegex(self.git('diff', '--cached', '--name-status', 'HEAD', '--', 'captures'), r'^R\d+\t')
        self.git('reset', '-q')
        out = self.ok('commit', '--project', 'demo')
        for spec in specs:
            self.assertIn(f'staged   {spec}', out.splitlines())
        self.assertEqual(self.git('show', '--format=', '--no-renames', '--name-status', 'HEAD', '--', 'captures'),
                         f'A\t{specs[0]}\nD\t{specs[1]}')
        self.assertEqual(self.git('status', '--porcelain', '--untracked-files=all'), '')
        # The commit holds each spec that the state lists, and no other spec of a stage.
        state = json.loads((self.site / STATE).read_text())
        self.assertIn('stage3-start', state['captures'])
        self.assertNotIn('stage4-check', state['captures'])
        self.assertEqual([path for path in self.git('ls-files', 'captures/demo').splitlines() if path in specs], [specs[0]])

    def test_a_clone_that_fetches_only_main_reads_the_result_of_the_push(self):
        # The checkout has no remote-tracking ref for the branch of the run. The result line of Git says what the push did.
        self.git('config', 'remote.origin.fetch', '+refs/heads/main:refs/remotes/origin/main')
        self.doc_set()
        out = self.ok('commit', '--project', 'demo')
        self.assertEqual(out.splitlines()[-2:], [
            f'pushed   {FIRST} to origin',
            f'done     the branch {FIRST} waits for the review. Tell the user the result. Do not merge.'])
        self.assertEqual(self.commit_of(FIRST), self.commit_of(f'refs/heads/{FIRST}', cwd=self.origin))
        out = self.ok('commit', '--project', 'demo')
        self.assertEqual(out.splitlines()[-2:], [
            f'kept     origin has each commit of {FIRST}. Nothing to push.',
            f'done     the branch {FIRST} waits for the review. Tell the user the result. Do not merge.'])

    def test_a_state_that_names_a_file_outside_the_doc_set_stops_each_action(self):
        # The state is a tracked file, and `branch` takes a branch of origin with its state. Its names are no trust.
        self.doc_set()
        (self.site / 'notes.txt').write_text('A note of a person.\n')
        state_file = self.site / STATE
        good = state_file.read_text()
        outside = (('pages', '../../../../notes.txt', "the page name '../../../../notes.txt' is not a path below the directory of "
                    'the project'),
                   ('pages', '/notes.txt', "the page name '/notes.txt' is not a path below the directory of the project"),
                   ('captures', '../../notes', "the capture name '../../notes' is not the name of a capture mark"))
        for key, name, fault in outside:
            with self.subTest(name=name):
                state = json.loads(good)
                state[key][name] = dict(next(iter(state[key].values())))
                state_file.write_text(json.dumps(state, indent=1, sort_keys=True) + '\n')
                head, tree = self.commit_of('HEAD'), self.tree()
                for words in (('commit', '--no-push'), ('scaffold',), ('check',), ('next',), ('status', '--repo', '.')):
                    done = self.docgen_run(words[0], '--project', 'demo', *words[1:])
                    self.assertEqual(done.returncode, 2, done.stdout)
                    self.assertEqual(done.stderr.strip(), f"error: the state of 'demo' does not have the form of a state: "
                                     f'{state_file}: {fault}. The script writes this file. Do not edit it. Stop and tell the '
                                     'user this line.')
                self.assertEqual((self.commit_of('HEAD'), self.tree(), self.git('diff', '--cached', '--name-only')),
                                 (head, tree, ''))
        # A state of the last commit with such a name gives no file to `commit`: the file of the person stays tracked.
        self.git('add', 'notes.txt')
        state = json.loads(good)
        state['pages']['../../../../notes.txt'] = dict(next(iter(state['pages'].values())))
        state_file.write_text(json.dumps(state, indent=1, sort_keys=True) + '\n')
        self.git('add', '-f', STATE)
        self.git('commit', '-q', '-m', 'A state with a name outside the doc set')
        state_file.write_text(good)
        (self.site / 'notes.txt').unlink()
        out = self.ok('commit', '--project', 'demo', '--no-push')
        self.assertNotIn('notes.txt', out)
        self.assertIn('notes.txt', self.git('ls-files', 'notes.txt'))

    def test_commit_stops_when_the_state_lists_a_file_that_is_absent(self):
        # A branch whose state lists a capture spec that it does not hold passes each check of the site.
        self.doc_set()
        (self.site / 'captures' / 'demo' / 'help.json').unlink()
        head = self.commit_of('HEAD')
        done = self.docgen_run('commit', '--project', 'demo')
        self.assertEqual(done.returncode, 2, done.stdout)
        self.assertEqual(done.stderr.strip(), 'error: the state lists a file that is absent: captures/demo/help.json. '
                         'Nothing changed. Run first: ' + self.command('scaffold'))
        self.assertEqual((self.commit_of('HEAD'), self.git('diff', '--cached', '--name-only')), (head, ''))
        # The command of the line writes the spec again.
        self.ok('scaffold', '--project', 'demo')
        self.ok('commit', '--project', 'demo')
        self.assertIn('captures/demo/help.json', self.files_of('HEAD'))

    def test_a_hook_that_refuses_the_commit(self):
        self.doc_set()
        self.hook('pre-commit', ''.join(f"echo 'hook line {n}'\n" for n in range(1, 31)) + 'exit 1\n')
        head, remote = self.commit_of('HEAD'), self.refs(cwd=self.origin)
        done = self.docgen_run('commit', '--project', 'demo')
        self.assertEqual(done.returncode, 1, done.stdout)
        # The last lines of the hook, then one line with the cause.
        self.assertEqual(done.stdout.splitlines()[-20:], [f'hook line {n}' for n in range(11, 31)])
        self.assertNotIn('hook line 10\n', done.stdout)
        self.assertEqual(done.stderr.strip(), 'error: Git made no commit: a hook refused it, or Git gives the cause in the '
                         'lines above. Stop and tell the user these lines.')
        self.assertEqual((self.commit_of('HEAD'), self.refs(cwd=self.origin)), (head, remote))
        self.assertNotIn('pushed', done.stdout)

        # The hook of the site runs each check. The line names the checks that fail and the two next commands.
        self.hook('pre-commit', "printf '== lint: python3 scripts/lint_ste.py\\nsrc/data/projects.json:1: a finding\\n'\n"
                                "printf '\\n== summary\\n  tests  ok\\n  build  ok\\n  lint   FAIL\\ncheck: FAILED\\n'\nexit 1\n")
        done = self.docgen_run('commit', '--project', 'demo')
        self.assertEqual(done.returncode, 1, done.stdout)
        self.assertIn(f"{self.site / 'src' / 'data' / 'projects.json'}:1: a finding", done.stdout.splitlines())
        self.assertEqual(done.stderr.strip(), 'error: the pre-commit hook of the site refused the commit: lint failed. No commit '
                         f"exists. Run `{self.command('check')}`, correct each finding, then run again: {self.command('commit')}")
        self.assertEqual((self.commit_of('HEAD'), self.refs(cwd=self.origin)), (head, remote))

        # After the correction, the same command makes the commit.
        (self.site / '.git' / 'hooks' / 'pre-commit').unlink()
        self.ok('commit', '--project', 'demo')
        self.assertEqual(self.git('status', '--porcelain', '--untracked-files=all'), '')

    def test_a_push_that_fails(self):
        self.doc_set()
        self.hook('pre-receive', "echo 'origin: the push is not permitted'\nexit 1\n", where=self.origin)
        remote = self.refs(cwd=self.origin)
        done = self.docgen_run('commit', '--project', 'demo')
        self.assertEqual(done.returncode, 1, done.stdout)
        self.assertIn('origin: the push is not permitted', done.stdout)
        self.assertEqual(done.stderr.strip(), f'error: Git did not push the branch {FIRST} to origin. The commit is in the '
                         'local branch. Stop and tell the user these lines.')
        self.assertEqual(self.git('log', '-1', '--format=%s'), 'Docs of demo: first doc set from docgen')
        self.assertEqual(self.refs(cwd=self.origin), remote)
        # When origin takes the push, the same command pushes the commit that exists.
        (self.origin / 'hooks' / 'pre-receive').unlink()
        out = self.ok('commit', '--project', 'demo')
        self.assertEqual(out.splitlines()[:2], [
            f'kept     {FIRST}: the last commit holds each file of the doc set. Nothing to commit.',
            f'pushed   {FIRST} to origin'])
        self.assertEqual(self.commit_of(FIRST), self.commit_of(f'refs/heads/{FIRST}', cwd=self.origin))

    def test_status_names_register_while_a_file_of_the_doc_set_waits_for_a_commit(self):
        self.merged_doc_set()
        self.ok('branch', '--project', 'demo', '--update')
        out = self.ok('status', '--project', 'demo')
        self.assertEqual(out.splitlines()[-2:], [
            '0 stale item(s)',
            'The pages of demo are current, and no file of the doc set waits for a commit. Nothing to do.'])
        # A corrected page that is not committed: the work does not end at `0 stale item(s)`.
        page = self.page('install/index.mdx')
        page.write_text(page.read_text().replace('word word word', 'word word text', 1))
        out = self.ok('status', '--project', 'demo')
        self.assertEqual(out.splitlines()[-2:], ['0 stale item(s)', 'next     ' + self.command('register')])
        self.assertEqual(base.next_command(self.ok('register', '--project', 'demo')), self.command('check'))
        # In an update, `scaffold` names `status`.
        self.ok('plan', '--project', 'demo')
        self.assertEqual(base.next_command(self.ok('scaffold', '--project', 'demo')), self.command('status'))


class HookVariablesTest(GitSiteCase):
    def test_no_action_writes_into_the_repository_of_a_hook(self):
        # A second repository stands for the repository of a hook. Git gives its location to the hook.
        # Here the docgen process gets the variables: the test does not remove them.
        other = self.tmp / 'other'
        other.mkdir()
        self.git('init', '-q', '-b', 'main', cwd=other)
        self.git('-c', 'user.name=t', '-c', 'user.email=t@example.com', 'commit', '-q', '--allow-empty', '-m', 'The hook', cwd=other)
        before = (self.refs(cwd=other), self.git('status', '--porcelain', cwd=other),
                  sorted(str(path.relative_to(other)) for path in other.rglob('*') if path.is_file()))
        hook = {'GIT_DIR': str(other / '.git'), 'GIT_INDEX_FILE': str(other / '.git' / 'index'), 'GIT_WORK_TREE': str(other)}

        def docgen(*words):
            done = base.subprocess.run(['python3', self.docgen, *words], cwd=self.repo, capture_output=True, text=True,
                                       env={**os.environ, **hook})
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
            return done.stdout

        docgen('survey', '--repo', '.')
        docgen('branch', '--project', 'demo')
        docgen('plan', '--project', 'demo')
        docgen('scaffold', '--project', 'demo')
        for path in base.PAGES:
            base.fill(self.page(path))
        docgen('scaffold', '--project', 'demo')
        docgen('register', '--project', 'demo')
        docgen('commit', '--project', 'demo')
        after = (self.refs(cwd=other), self.git('status', '--porcelain', cwd=other),
                 sorted(str(path.relative_to(other)) for path in other.rglob('*') if path.is_file()))
        self.assertEqual(after, before)
        self.assertEqual(self.git('log', '-1', '--format=%s'), 'Docs of demo: first doc set from docgen')
        self.assertEqual(self.commit_of(FIRST), self.commit_of(f'refs/heads/{FIRST}', cwd=self.origin))
        facts = json.loads((self.site / '.docgen' / 'demo' / 'facts.json').read_text())
        self.assertEqual(facts['release']['name'], 'portable-v0.1.0')

    def test_a_trace_line_of_git_is_no_file_of_the_site(self):
        # With GIT_TRACE, Git writes one line or more for each command to the error output. No such line is a path.
        def docgen(*words):
            return base.subprocess.run(['python3', self.docgen, *words], cwd=self.repo, capture_output=True, text=True,
                                       env={**os.environ, 'GIT_TRACE': '1'})

        done = docgen('branch', '--project', 'demo')
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertEqual(done.stdout.splitlines(), ['fetched  origin', f'started  {FIRST} at origin/main',
                                                    'next     ' + self.command('plan')])
        self.doc_set()
        done = docgen('commit', '--project', 'demo')
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertEqual([line for line in done.stdout.splitlines() if line.startswith(('staged', 'skipped'))],
                         [f'staged   {path}' for path in sorted(self.files_of('HEAD'))])

    def test_git_in_the_site_never_asks_for_input(self):
        # An agent cannot answer a question of Git. With this variable, Git fails with a message and does not wait.
        self.doc_set()
        self.hook('pre-commit', 'echo "prompt=$GIT_TERMINAL_PROMPT"\nexit 1\n')
        done = self.docgen_run('commit', '--project', 'demo')
        self.assertEqual(done.returncode, 1, done.stdout)
        self.assertIn('prompt=0', done.stdout.splitlines())

    def test_git_in_the_site_gets_no_input(self):
        # An agent program and a hook give an open input to the script. Git in the site gets a closed input,
        # so a question of Git or of a credential helper ends at once.
        self.ok('survey', '--repo', '.')
        for words in (('branch', '--project', 'demo'), ('plan', '--project', 'demo'), ('scaffold', '--project', 'demo')):
            done, calls = recorded_git(self, words, self.repo)
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
            in_site = [call for call in calls if call['words'][:2] == ['-C', str(self.site)]]
            self.assertTrue(in_site, calls)
            self.assertEqual([call['words'] for call in in_site if not call['no_input']], [])

    def test_the_tests_of_this_file_get_no_variable_of_a_hook(self):
        # `base.run` removes the variables, so a `git` command of a test works in its own directory.
        with mock.patch.dict(os.environ, {'GIT_DIR': str(self.tmp / 'absent' / '.git')}):
            self.assertEqual(self.git('rev-parse', '--show-toplevel'), str(self.site))


if __name__ == '__main__':
    unittest.main()
