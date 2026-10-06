"""Tests of docgen/docgen.py for the survey, `status` and the flow of an update.

Each test makes its own site and its own project in a temporary directory. A test that needs a branch of the
site uses the Git site of tests/test_docgen_git.py. No test needs the network or Docker.
"""

import hashlib
import json
import os
import shutil
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_docgen as base  # noqa: E402  The fixture project and the helpers of the other docgen tests.
import test_docgen_git as git_base  # noqa: E402  A site that is a Git repository with a stand-in origin.

docgen = base.docgen
UPDATE, STATE = git_base.UPDATE, git_base.STATE


def one_error_line(case, done, start):
    """An action that stops prints one `error:` line and no trace of the program."""
    case.assertEqual(done.returncode, 2, done.stdout + done.stderr)
    lines = done.stderr.strip().splitlines()
    case.assertEqual(len(lines), 1, done.stderr)
    case.assertTrue(lines[0].startswith('error: ' + start), lines[0])
    case.assertNotIn('Traceback', done.stderr)
    return lines[0]


def command_after(line, words):
    """The complete command that one line gives after some words."""
    return line.split(words, 1)[1].strip()


class Case(unittest.TestCase):
    """A site that is no Git repository, and the fixture project."""

    setUp = base.DocgenTest.setUp
    git = base.DocgenTest.git
    docgen_run = base.DocgenTest.docgen_run
    prepare = base.DocgenTest.prepare
    page = base.DocgenTest.page
    command = base.DocgenTest.command
    spec = base.DocgenTest.spec
    fill_all = base.DocgenTest.fill_all
    write_slot = base.DocgenTest.write_slot
    files = base.DocgenTest.files

    def ok(self, *words):
        done = self.docgen_run(*words)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        return done.stdout

    def written(self):
        """A doc set with each slot written."""
        self.prepare()
        self.fill_all()
        self.ok('scaffold', '--project', 'demo')

    def work(self, name):
        return self.site / '.docgen' / 'demo' / name

    def state(self):
        return json.loads((self.site / 'docgen' / 'state' / 'demo.json').read_text())

    def change(self, path, text, branches=('portable', 'main'), mode=None):
        """Write one file of the project and commit it on each of the branches. `main` is checked out at the end."""
        for branch in branches:
            self.git('switch', '-q', branch)
            (self.repo / path).parent.mkdir(parents=True, exist_ok=True)
            (self.repo / path).write_text(text)
            if mode:
                (self.repo / path).chmod(mode)
            self.git('add', path)
            self.git('commit', '-q', '-m', f'Change {path}')
        self.git('switch', '-q', 'main')

    def status(self, *words):
        return self.docgen_run('status', '--project', 'demo', *words)

    def shell(self, line):
        """Run one printed command in a new shell, in a directory that is not the project and not the site."""
        elsewhere = self.tmp / 'elsewhere'
        elsewhere.mkdir(exist_ok=True)
        return base.run('sh', '-c', line, cwd=elsewhere)


# ----- survey -----

class SurveyTest(Case):
    def test_survey_stops_for_a_name_that_is_no_project_name(self):
        line = one_error_line(self, self.docgen_run('survey', '--repo', '.', '--project', 'Demo_1'),
                              "'Demo_1' is not a project name of the site")
        self.assertIn('The option `--project` gives the name of the project on the site.', line)
        self.assertFalse((self.site / '.docgen').exists())
        # A name with the right characters and a `-` at its start: the line says the full rule.
        line = one_error_line(self, self.docgen_run('survey', '--repo', '.', '--project=-x'),
                              "'-x' is not a project name of the site: a name has lowercase letters, digits and '-' only, "
                              'and it starts and ends with a letter or a digit.')

    def test_survey_prints_a_note_for_a_name_that_the_project_list_does_not_have(self):
        # A site with no project list gives no note: the tests of the other files use such a site.
        self.assertNotIn('note ', self.ok('survey', '--repo', '.'))
        data = self.site / 'src' / 'data'
        data.mkdir()
        (data / 'projects.json').write_text(json.dumps([{'slug': 'alpha'}, {'slug': 'demo-site'}]))
        out = self.ok('survey', '--repo', '.')
        self.assertIn("note           the project list of the site has no project 'demo'. `register` adds a new project with this "
                      'name. The option `--project` gives another name. The names of the list are: alpha, demo-site. '
                      'Continue, and put this line into your report.', out.splitlines())
        # No stop: the line `next` is there, and the name of the list gives no note.
        self.assertEqual(base.next_command(out), self.command('branch'))
        out = self.ok('survey', '--repo', '.', '--project', 'demo-site')
        self.assertNotIn('note ', out)
        self.assertIn('project        demo-site', out.splitlines())

    def test_the_note_of_an_update_for_a_name_that_the_project_list_does_not_have(self):
        # The clone is in a directory with another name than the project has on the site. An update makes no new project.
        data = self.site / 'src' / 'data'
        data.mkdir()
        (data / 'projects.json').write_text(json.dumps([{'slug': 'alpha'}, {'slug': 'demo-site'}]))
        out = self.ok('survey', '--repo', '.', '--update')
        survey = f'python3 {self.docgen} survey --repo {self.repo} --project PROJECT --update'
        self.assertIn("note           the project list of the site has no project 'demo', and an update needs the name that "
                      'the project has in that list. The names of the list are: alpha, demo-site. The option `--project` '
                      'gives the name. Do not choose a name: the user gives it. With the name in place of the word PROJECT, '
                      f'the survey is: {survey} Put this line into your report.', out.splitlines())
        self.assertNotIn('`register` adds a new project', out)
        # The command of the note is complete: with a name of the list, it runs from each directory.
        done = self.shell(survey.replace('PROJECT', 'demo-site'))
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertNotIn('note ', done.stdout)
        self.assertEqual(base.next_command(done.stdout), f'python3 {self.docgen} branch --project demo-site --update')

    def test_the_develop_ref_of_a_project_with_no_main_and_no_master(self):
        # With `main`, the survey prints no note about the develop ref.
        self.assertNotIn('note ', self.ok('survey', '--repo', '.'))
        self.git('branch', '-m', 'main', 'local-dev')
        out = self.ok('survey', '--repo', '.')
        self.assertIn('develop        ref local-dev, 7 commits, 1 merges sampled', out.splitlines())
        self.assertIn('note           the project has no branch main and no branch master. So the develop ref is the branch '
                      'that is checked out now: local-dev. The option `--develop-ref` gives another branch. Continue, and '
                      'put this line into your report.', out.splitlines())
        # A detached HEAD is no branch. The survey does not write the name `HEAD` into the facts.
        facts = self.work('facts.json').read_bytes()
        self.git('switch', '-q', '--detach', 'local-dev')
        line = one_error_line(self, self.docgen_run('survey', '--repo', '.'),
                              'the project has no branch main and no branch master, and its checkout has a detached HEAD.')
        self.assertTrue(line.endswith('The option `--develop-ref` gives that branch. Do not choose a branch. '
                                      'Stop and tell the user this line.'), line)
        self.assertEqual(self.work('facts.json').read_bytes(), facts)
        # The option gives the branch, and then the survey has no note.
        out = self.ok('survey', '--repo', '.', '--develop-ref', 'local-dev')
        self.assertIn('develop        ref local-dev, 7 commits, 1 merges sampled', out.splitlines())
        self.assertNotIn('note ', out)

    def test_survey_and_status_say_so_when_the_branch_has_commits_after_its_release_tag(self):
        self.written()
        self.assertNotIn('note ', self.ok('survey', '--repo', '.'))
        self.assertNotIn('note ', self.status('--repo', '.').stdout)
        self.git('switch', '-q', 'portable')
        for _ in range(2):
            self.git('commit', '-q', '--allow-empty', '-m', 'After the release')
        self.git('switch', '-q', 'main')
        note = ('the branch portable has 2 commit(s) after the release tag portable-v0.1.0. The pages describe the newest '
                'commit of the branch, and the release name is older. Continue, and put this line into your report.')
        self.assertIn('note           ' + note, self.ok('survey', '--repo', '.').splitlines())
        done = self.status('--repo', '.')
        self.assertIn('note     ' + note, done.stdout.splitlines())
        # The note is no stale item.
        self.assertEqual(done.returncode, 0, done.stdout)
        self.assertIn('0 stale item(s)', done.stdout.splitlines())

    def test_survey_with_no_docker_program_gives_one_line(self):
        # A directory with the programs that the survey needs, and no `docker`.
        programs = self.tmp / 'programs'
        programs.mkdir()
        for name in ('python3', 'git'):
            (programs / name).symlink_to(shutil.which(name))
        env = {name: value for name, value in os.environ.items() if name not in base.GIT_LOCAL}
        done = base.subprocess.run(['python3', self.docgen, 'survey', '--repo', '.', '--run-help', '--update'], cwd=self.repo,
                                   capture_output=True, text=True, env={**env, 'PATH': str(programs)})
        line = one_error_line(self, done, '--run-help needs Docker, and Docker does not answer. Nothing changed. '
                                          'Run the survey without --run-help: ')
        self.assertFalse(self.work('facts.json').exists())
        # The line gives the complete command of the survey that runs with no Docker. It runs from each directory.
        again = command_after(line, 'Run the survey without --run-help: ')
        self.assertEqual(again, f'python3 {self.docgen} survey --repo {self.repo} --update')
        done = self.shell(again)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(base.next_command(done.stdout), self.command('branch', '--update'))

    def test_survey_removes_the_help_texts_of_an_earlier_survey(self):
        self.prepare()
        saved = self.work('help') / 'scripts__cli.py.txt'
        saved.parent.mkdir()
        saved.write_text('usage: cli.py {build,check,old-action}\n')
        self.ok('survey', '--repo', '.')
        # A survey with no `--run-help` has no help text. `next` then names no help text of an older release.
        self.assertFalse(saved.parent.exists())

    def test_survey_writes_no_file_of_the_project_repository(self):
        # A tracked file with a later change time. A Git command that reads the working tree then writes the index again.
        index, readme = self.repo / '.git' / 'index', self.repo / 'README.md'
        later = readme.stat().st_mtime + 100
        os.utime(readme, (later, later))
        before = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted((self.repo / '.git').rglob('*'))
                  if path.is_file()}
        env = {name: value for name, value in os.environ.items() if name not in (*base.GIT_LOCAL, 'GIT_OPTIONAL_LOCKS')}
        for words in (('survey', '--repo', '.'), ('plan', '--project', 'demo'), ('scaffold', '--project', 'demo'),
                      ('next', '--project', 'demo'), ('check', '--project', 'demo'), ('status', '--project', 'demo')):
            base.subprocess.run(['python3', self.docgen, *words], cwd=self.repo, capture_output=True, text=True, env=env)
        after = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted((self.repo / '.git').rglob('*'))
                 if path.is_file()}
        self.assertEqual(after[index], before[index])
        self.assertEqual(after, before)
        # The survey does not read the working tree, so the facts hold no count of its changed files.
        self.assertNotIn('worktree_dirty_files', json.loads(self.work('facts.json').read_text()))


    def test_each_git_command_of_the_survey_leaves_the_index_of_the_project(self):
        # With GIT_OPTIONAL_LOCKS=0, a Git command that reads the index does not write it again. Each call has the value.
        done, calls = git_base.recorded_git(self, ('survey', '--repo', '.'), self.repo)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        in_project = [call for call in calls if call['words'][:2] == ['-C', str(self.repo)]]
        self.assertGreater(len(in_project), 5, calls)
        self.assertEqual([call['words'] for call in calls if call['locks'] != '0' and 'rev-parse' not in call['words'][:1]], [])

    def test_the_files_of_a_ref_have_the_same_paths_from_each_directory(self):
        # Git lists the files of the current directory only, with short paths. The script asks for the full tree.
        top = docgen.tree(self.repo, 'main')
        self.assertIn('scripts/cli.py', top)
        self.assertEqual(docgen.tree(self.repo / 'scripts', 'main'), top)


class SiteItselfTest(git_base.GitSiteCase):
    remote = False

    def test_survey_stops_when_the_repository_is_the_site(self):
        for start in (self.site, self.site / 'docgen'):
            with self.subTest(start=start.name):
                done = base.run('python3', self.docgen, 'survey', '--repo', '.', cwd=start)
                line = one_error_line(self, done, 'this directory is the tenant-docs repository, and not the repository of '
                                                  'a project. Nothing changed.')
                self.assertTrue(line.endswith('Stop and tell the user this line.'), line)
                self.assertFalse((self.site / '.docgen').exists())


# ----- a file that is absent or is not valid JSON -----

class NoTraceTest(Case):
    def test_a_state_file_that_is_not_valid_json_gives_one_line(self):
        self.written()
        state = self.site / 'docgen' / 'state' / 'demo.json'
        state.write_text(state.read_text().replace('{\n', '{\n<<<<<<< HEAD\n', 1))
        data = self.site / 'src' / 'data'
        data.mkdir()
        (data / 'projects.json').write_text('[]\n')
        (data / 'versions.json').write_text('{}\n')
        before = self.files()
        for words in (('next',), ('check',), ('diagrams',), ('status', '--repo', '.'), ('scaffold',), ('register',)):
            with self.subTest(action=words[0]):
                line = one_error_line(self, self.docgen_run(words[0], '--project', 'demo', *words[1:]),
                                      "the state of 'demo' is not valid JSON: ")
                self.assertTrue(line.endswith('The script writes this file. Do not edit it. Stop and tell the user this line.'),
                                line)
        self.assertEqual(self.files(), before)

    def test_a_state_file_with_another_form_gives_one_line(self):
        # Valid JSON that is no state: an action that reads `pages` ends with a trace of the program.
        self.written()
        state = self.site / 'docgen' / 'state' / 'demo.json'
        good = json.loads(state.read_text())
        data = self.site / 'src' / 'data'
        data.mkdir()
        (data / 'projects.json').write_text('[]\n')
        (data / 'versions.json').write_text('{}\n')
        no_keys = dict(good, pages={**good['pages'], 'index.mdx': {'order': 0}})
        cases = (('{}', 'the file does not hold an object with the key `pages`'),
                 ('[]', 'the file does not hold an object with the key `pages`'),
                 ('{"pages": []}', 'the file does not hold an object with the key `pages`'),
                 (json.dumps(no_keys), "the record of the page 'index.mdx' does not have the keys `ref`, `tree`, `template` "
                                       'and `sources`'),
                 (json.dumps(dict(good, captures=[])), 'the key `captures` does not hold an object'))
        for text, fault in cases:
            state.write_text(text + '\n')
            before = self.files()
            for words in (('next',), ('check',), ('diagrams',), ('status', '--repo', '.'), ('scaffold',), ('register',)):
                with self.subTest(text=text[:20], action=words[0]):
                    line = one_error_line(self, self.docgen_run(words[0], '--project', 'demo', *words[1:]),
                                          f"the state of 'demo' does not have the form of a state: {state}: {fault}. ")
                    self.assertTrue(line.endswith('The script writes this file. Do not edit it. Stop and tell the user this '
                                                  'line.'), line)
            self.assertEqual(self.files(), before)

    def test_a_data_file_or_a_capture_spec_that_is_not_valid_json_stops_scaffold_before_its_first_write(self):
        self.prepare()
        data = self.site / 'src' / 'data'
        data.mkdir()
        (data / 'versions.json').write_text('{"demo": \n')
        # The pages have open slots. Without the stop, `scaffold` writes the state and then ends with a trace.
        fill = base.fill
        fill(self.page('use/commands/build.mdx'), 'example-command', 'python3 scripts/cli.py build --all')
        before = self.files()
        line = one_error_line(self, self.docgen_run('scaffold', '--project', 'demo'), 'src/data/versions.json is not valid JSON: ')
        self.assertTrue(line.endswith('Stop and tell the user this line.'), line)
        self.assertEqual(self.files(), before)
        (data / 'versions.json').write_text('{}\n')
        self.spec('cmd-build').write_text('{"title": \n')
        before = self.files()
        one_error_line(self, self.docgen_run('scaffold', '--project', 'demo'),
                       'the capture spec captures/demo/cmd-build.json is not valid JSON: ')
        self.assertEqual(self.files(), before)

    def test_the_work_files_that_are_not_valid_json_give_one_line(self):
        self.written()
        self.work('plan.json').write_text('{"pages": \n')
        line = one_error_line(self, self.docgen_run('scaffold', '--project', 'demo'), "the plan of 'demo' is not valid JSON: ")
        self.assertTrue(line.endswith('Run first: ' + self.command('plan')), line)
        self.work('facts.json').write_text('{"trees": \n')
        for action in ('plan', 'scaffold', 'next', 'check'):
            with self.subTest(action=action):
                line = one_error_line(self, self.docgen_run(action, '--project', 'demo'),
                                      "the facts of 'demo' (run survey first) is not valid JSON: ")
                self.assertTrue(line.endswith('Run the survey again in the project repository: it is the first command of '
                                              'the skill.'), line)

    def test_an_absent_file_names_the_complete_command_of_the_step_before(self):
        line = one_error_line(self, self.docgen_run('plan', '--project', 'demo'), "the facts of 'demo' (run survey first) is absent: ")
        self.assertTrue(line.endswith('Run the survey again in the project repository: it is the first command of the skill.'))
        self.ok('survey', '--repo', '.')
        line = one_error_line(self, self.docgen_run('scaffold', '--project', 'demo'), "the plan of 'demo' is absent: ")
        self.assertTrue(line.endswith('Run first: ' + self.command('plan')), line)
        for action in ('next', 'check'):
            with self.subTest(action=action):
                line = one_error_line(self, self.docgen_run(action, '--project', 'demo'),
                                      "the state of 'demo' (run scaffold first) is absent: ")
                self.assertTrue(line.endswith('Run first: ' + self.command('scaffold')), line)

    def test_status_with_no_path_of_the_project_repository_gives_one_line(self):
        self.written()
        self.work('repo').unlink()
        line = one_error_line(self, self.status(), "the project repository of 'demo' (run survey first) is not known: ")
        self.assertIn('Run the survey again in the project repository: it is the first command of the skill.', line)
        # With the option, the same checkout gives the list.
        self.assertEqual(self.status('--repo', '.').returncode, 0)
        one_error_line(self, self.status('--repo', str(self.tmp / 'absent')), f"'{self.tmp / 'absent'}' is not a directory.")
        one_error_line(self, self.status('--repo', str(self.tmp)),
                       f'the directory {self.tmp} is not in the working tree of a Git repository.')


# ----- scaffold -----

class ScaffoldTest(Case):
    def test_refresh_stops_for_a_value_that_is_no_page_of_the_doc_set(self):
        self.written()
        before = self.files()
        for value in ('nosuch.mdx', 'install', 'install/index', 'ALL'):
            with self.subTest(value=value):
                line = one_error_line(self, self.docgen_run('scaffold', '--project', 'demo', '--refresh', value),
                                      f"'{value}' is no page of the doc set of 'demo'. Nothing changed. The pages are: ")
                self.assertIn('The pages are: develop/workflow.mdx, index.mdx, install/index.mdx, reference/index.mdx, '
                              'use/commands/build.mdx, use/commands/check.mdx, use/commands/index.mdx. ', line)
                self.assertEqual(self.files(), before)
        # `status`, `next` and `check` print a page in three forms. Each form names the same page.
        for value in ('install/index.mdx', 'src/content/docs/demo/install/index.mdx', str(self.page('install/index.mdx')), 'all'):
            with self.subTest(value=value):
                out = self.ok('scaffold', '--project', 'demo', '--refresh', value)
                self.assertRegex(out, r'(?m)^recorded install/index\.mdx +the sources of the page are current$')

    def test_refresh_stops_for_a_page_of_a_person_and_for_an_empty_value(self):
        # A person wrote the overview page before the first run. The plan has the page, and the state does not.
        self.docs.mkdir(parents=True)
        self.page('index.mdx').write_text('---\ntitle: demo\ndescription: d\n---\n\nA person wrote this.\n')
        self.written()
        self.assertNotIn('index.mdx', self.state()['pages'])
        before = self.files()
        # `--refresh` records the sources of a page of the state. It records nothing for another value, so it stops.
        for value in ('index.mdx', ''):
            with self.subTest(value=value):
                line = one_error_line(self, self.docgen_run('scaffold', '--project', 'demo', '--refresh', value),
                                      f"'{value}' is no page of the doc set of 'demo'. Nothing changed. The pages are: "
                                      'develop/workflow.mdx, install/index.mdx, reference/index.mdx, ')
                self.assertTrue(line.endswith('`status` prints the complete command below each stale page.'), line)
                self.assertEqual(self.files(), before)

    def test_refresh_stops_for_a_page_that_the_plan_does_not_have(self):
        self.written()
        # The project loses each documentation file of the action `build`, and its command line loses the action.
        self.git('switch', '-q', 'portable')
        (self.repo / 'scripts' / 'cli.py').write_text(base.CLI.replace('    actions.add_parser("build")\n', ''))
        self.git('commit', '-q', '-am', 'No action build')
        self.git('switch', '-q', 'main')
        self.ok('survey', '--repo', '.')
        self.ok('plan', '--project', 'demo')
        before = self.files()
        line = one_error_line(self, self.docgen_run('scaffold', '--project', 'demo', '--refresh', 'use/commands/build.mdx'),
                              "the plan of 'demo' does not have the page use/commands/build.mdx")
        self.assertTrue(line.endswith('Nothing changed. Do not delete the page. Stop and tell the user this line.'), line)
        self.assertEqual(self.files(), before)

    def test_refresh_stops_when_the_plan_is_older_than_the_project(self):
        self.written()
        self.change('docs/setup.md', '# Setup\n\n## Steps\n\nRun `python3 scripts/cli.py check`.\n', branches=('portable',))
        refresh = ('scaffold', '--project', 'demo', '--refresh', 'install/index.mdx')
        # No survey after the change: the facts are older than the repository. Without the stop, `scaffold`
        # records the old sources as current, and the page is stale again.
        before = self.files()
        line = one_error_line(self, self.docgen_run(*refresh), "the facts of 'demo' are older than the project repository: the "
                              'file docs/setup.md changed after the survey. Nothing changed. Run first: ')
        self.assertEqual(self.files(), before)
        again = command_after(line, 'Run first: ')
        self.assertEqual(again, f'python3 {self.docgen} survey --repo {self.repo}')
        self.assertEqual(self.shell(again).returncode, 0)
        # The survey ran, and `plan` did not: the plan is older than the facts.
        line = one_error_line(self, self.docgen_run(*refresh), "the plan of 'demo' is older than the facts of the last survey: "
                              'the file docs/setup.md of the project changed after `plan` ran. Nothing changed. Run first: ')
        self.assertEqual(command_after(line, 'Run first: '), self.command('plan'))
        self.ok('plan', '--project', 'demo')
        self.assertRegex(self.ok(*refresh), r'(?m)^recorded install/index\.mdx ')
        done = self.status('--repo', '.')
        self.assertIn('current  install/index.mdx', done.stdout.splitlines())

    def test_a_survey_of_another_branch_stops_before_it_changes_the_state(self):
        self.written()
        state = self.state()
        self.assertEqual(state['pages']['develop/workflow.mdx']['ref'], 'main')
        # The checkout of the project is on another branch, or an option names it.
        self.git('branch', 'topic/i9-next', 'main')
        self.ok('survey', '--repo', '.', '--develop-ref', 'topic/i9-next')
        before = self.files()
        # No person reviewed this doc set. The agent does not choose between the two branches.
        for words in (('plan', '--project', 'demo'), ('scaffold', '--project', 'demo'),
                      ('scaffold', '--project', 'demo', '--refresh', 'develop/workflow.mdx')):
            with self.subTest(words=words):
                line = one_error_line(self, self.docgen_run(*words), "the pages of 'demo' describe the branch main, and the last "
                                      'survey read the branch topic/i9-next for them. Nothing changed. ')
                self.assertTrue(line.endswith('The option `--develop-ref` of `survey` gives the branch. Do not choose a branch. '
                                              'Stop and tell the user this line.'), line)
        self.assertEqual(self.files(), before)
        self.ok('survey', '--repo', '.', '--develop-ref', 'main')
        self.ok('plan', '--project', 'demo')
        self.ok('scaffold', '--project', 'demo')
        self.assertEqual(self.state(), state)

    def test_a_written_page_that_names_the_planned_note_keeps_its_text(self):
        # A page of the site skeleton: the note is one line of the page. Docgen replaces this page.
        stub = self.page('install/index.mdx')
        stub.parent.mkdir(parents=True)
        stub.write_text('---\ntitle: Install\n---\n\nimport Planned from "@/components/Planned.astro";\n\n<Planned issue={7} />\n')
        # A page of a person that names the component in a sentence is no such page.
        person = self.page('use/commands/index.mdx')
        person.parent.mkdir(parents=True)
        person.write_text('---\ntitle: Use\n---\n\nA page with no content yet holds `<Planned issue={7} />`.\n')
        out = self.prepare().stdout
        self.assertRegex(out, r'(?m)^wrote    install/index\.mdx +has open slots$')
        self.assertRegex(out, r'(?m)^kept     use/commands/index\.mdx +the page exists and docgen did not write it$')
        # A page that docgen wrote, with the text of the note in a slot and on a line of its own.
        self.fill_all()
        self.ok('scaffold', '--project', 'demo')
        self.write_slot('index.mdx', 'limits', 'A page with no content holds this line:\n\n<Planned issue={7} />\n\n' + 'word ' * 20)
        text = self.page('index.mdx').read_text()
        out = self.ok('scaffold', '--project', 'demo')
        self.assertRegex(out, r'(?m)^kept     index\.mdx +the page exists$')
        self.assertEqual(self.page('index.mdx').read_text(), text)

    def test_scaffold_prints_kept_for_a_page_of_the_script_with_the_same_text(self):
        out = self.prepare().stdout
        self.assertRegex(out, r'(?m)^wrote    reference/index\.mdx +complete$')
        watched = (self.page('reference/index.mdx'), self.site / 'docgen' / 'state' / 'demo.json')
        times = [path.stat().st_mtime_ns for path in watched]
        out = self.ok('scaffold', '--project', 'demo')
        self.assertRegex(out, r'(?m)^kept     reference/index\.mdx +the page exists$')
        self.assertNotIn('wrote ', out)
        self.assertEqual([path.stat().st_mtime_ns for path in watched], times)
        # A new title of a documentation file changes the text of the page. Then the line says `wrote`.
        self.change('docs/setup.md', '# Set the project up\n\n## Steps\n\nRun `python3 scripts/cli.py build`.\n', branches=('portable',))
        self.ok('survey', '--repo', '.')
        self.ok('plan', '--project', 'demo')
        out = self.ok('scaffold', '--project', 'demo', '--refresh', 'reference/index.mdx')
        self.assertRegex(out, r'(?m)^wrote    reference/index\.mdx +complete$')
        self.assertIn('Set the project up', self.page('reference/index.mdx').read_text())
        # The same command again: the text is the same, and the line says that the sources are recorded.
        out = self.ok('scaffold', '--project', 'demo', '--refresh', 'reference/index.mdx')
        self.assertRegex(out, r'(?m)^recorded reference/index\.mdx +the sources of the page are current$')

    def test_the_page_of_the_script_records_only_the_files_that_it_lists(self):
        # A Markdown file in another directory. The pattern `*.md` of the profile finds it, and the page does not list it.
        self.change('tools/NOTES.md', '# Notes\n')
        self.written()
        listed = ['README.md', 'docs/build.md', 'docs/setup.md']
        self.assertEqual(sorted(self.state()['pages']['reference/index.mdx']['sources']), listed)
        text = self.page('reference/index.mdx').read_text()
        self.assertNotIn('tools/NOTES.md', text)
        for path in listed:
            self.assertIn(f'`{path}`', text)
        # A change of that file does not make the page stale.
        self.change('tools/NOTES.md', '# Notes\n\nMore text.\n')
        done = self.status('--repo', '.')
        self.assertEqual(done.returncode, 0, done.stdout)
        self.assertIn('current  reference/index.mdx', done.stdout.splitlines())


# ----- status -----

class StatusTest(Case):
    def test_status_gives_the_same_result_from_a_sub_directory(self):
        self.written()
        for start in (self.repo, self.repo / 'docs', self.repo / 'scripts'):
            with self.subTest(start=start.name):
                done = base.run('python3', self.docgen, 'status', '--project', 'demo', '--repo', '.', cwd=start)
                self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
                self.assertNotIn('was removed', done.stdout)
                self.assertEqual([line.split()[0] for line in done.stdout.splitlines()[:7]], ['current'] * 7)

    def test_a_page_of_the_script_gets_the_command_that_writes_it_again(self):
        self.written()
        self.change('docs/setup.md', '# Setup\n\n## Steps\n\nRun `python3 scripts/cli.py check`.\n', branches=('portable',))
        done = self.status('--repo', '.')
        self.assertEqual(done.returncode, 1)
        block = done.stdout[done.stdout.index('stale    reference/index.mdx'):].splitlines()
        self.assertEqual(block[:5], [
            'stale    reference/index.mdx',
            f"           The page is the file {self.page('reference/index.mdx')}",
            '           The script writes this page. Do not edit it.',
            '           docs/setup.md changed',
            '           Write the page again: ' + self.command('scaffold', '--refresh', 'reference/index.mdx')])
        # The page that the agent wrote has the command that shows the change, and the other words.
        block = done.stdout[done.stdout.index('stale    install/index.mdx'):].splitlines()
        self.assertEqual(block[2], '           docs/setup.md changed. Read the change:')
        self.assertRegex(block[3], rf'^             git -C {self.repo} diff [0-9a-f]{{40}} [0-9a-f]{{40}}$')
        self.assertEqual(block[4], '           After you correct the page: ' + self.command('scaffold', '--refresh', 'install/index.mdx'))
        self.assertEqual(done.stdout.count('After you correct the page'), 1)
        # The command of the script page runs after a survey and a plan. Then the page is current.
        self.ok('survey', '--repo', '.')
        self.ok('plan', '--project', 'demo')
        done = self.shell(command_after(block[4], 'After you correct the page: ').replace('install/index.mdx', 'reference/index.mdx'))
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(base.next_command(done.stdout), self.command('status'))
        self.assertIn('current  reference/index.mdx', self.status('--repo', '.').stdout.splitlines())

    def test_a_page_with_an_open_slot_is_an_item_with_the_next_command(self):
        self.written()
        self.write_slot('index.mdx', 'status', 'TODO(docgen:status)')
        self.write_slot('index.mdx', 'limits', 'TODO(docgen:limits)')
        done = self.status('--repo', '.')
        self.assertEqual(done.returncode, 1, done.stdout)
        lines = done.stdout.splitlines()
        at = lines.index('open     index.mdx')
        self.assertEqual(lines[at + 1:at + 3], [
            f"           The page is the file {self.page('index.mdx')}",
            '           The page has 2 open slot(s). Write each open slot first: ' + self.command('next')])
        self.assertIn('1 stale item(s)', lines)
        self.assertNotIn('Nothing to do', done.stdout)
        self.assertNotIn('current  index.mdx', lines)
        # A page with a changed source file and an open slot is one item. The open slots come first.
        self.change('README.md', '# demo\n\nStatus: prototype.\n\ndemo builds a small thing.\n\n## Parts\n\nMore text.\n',
                    branches=('portable',))
        lines = self.status('--repo', '.').stdout.splitlines()
        at = lines.index('stale    index.mdx')
        self.assertEqual(lines[at + 2], '           The page has 2 open slot(s). Write each open slot first: ' + self.command('next'))
        self.assertEqual(lines[at + 3], '           README.md changed. Read the change:')
        self.assertEqual(lines[at + 5], '           After you correct the page: ' + self.command('scaffold', '--refresh', 'index.mdx'))
        self.assertNotIn('open     index.mdx', lines)

    def test_a_source_file_with_a_new_name_and_a_source_file_that_is_gone(self):
        self.change('scripts/extra.sh', '#!/bin/sh\n# Print one line.\necho extra\n')
        self.written()
        self.assertIn('scripts/extra.sh', self.state()['pages']['use/commands/index.mdx']['sources'])
        self.git('switch', '-q', 'portable')
        self.git('mv', 'scripts/extra.sh', 'scripts/more.sh')
        self.git('rm', '-q', 'docs/build.md')
        self.git('commit', '-q', '-m', 'A new name, and one file less')
        self.git('switch', '-q', 'main')
        done = self.status('--repo', '.')
        self.assertEqual(done.returncode, 1)
        lines = done.stdout.splitlines()
        self.assertIn('           scripts/extra.sh was renamed to scripts/more.sh. The text of the file is the same.', lines)
        self.assertIn('           docs/build.md was removed', lines)
        self.assertNotIn('           scripts/extra.sh was removed', lines)
        # After the survey and the plan, the command of each item records the files that the page has now.
        self.ok('survey', '--repo', '.')
        self.ok('plan', '--project', 'demo')
        notes = []
        for line in lines:
            if 'After you correct the page: ' in line:
                done = self.shell(command_after(line, 'After you correct the page: '))
                self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
                notes += [text for text in done.stdout.splitlines() if text.startswith('note ')]
        # The record of one page loses a file, and the plan names no file in its place: one line for the report.
        # The file with the new name is in the plan, so its page gets no such line.
        self.assertEqual(notes, ['note     use/commands/build.mdx: the record of the page does not hold docs/build.md now, and the '
                                 'plan gives no file in its place. A later change of that text does not make this page stale. '
                                 'Put this line into your report.'])
        sources = self.state()['pages']
        self.assertIn('scripts/more.sh', sources['use/commands/index.mdx']['sources'])
        self.assertNotIn('scripts/extra.sh', sources['use/commands/index.mdx']['sources'])
        self.assertNotIn('docs/build.md', sources['use/commands/build.mdx']['sources'])
        done = self.status('--repo', '.')
        self.assertEqual(done.returncode, 0, done.stdout)
        self.assertIn('0 stale item(s)', done.stdout.splitlines())

    def test_the_command_that_shows_a_change_prints_no_change_of_the_mode(self):
        self.change('scripts/extra.sh', '#!/bin/sh\n# Print one line.\necho extra\n', mode=0o755)
        self.written()
        self.change('scripts/extra.sh', '#!/bin/sh\n# Print one line.\necho more\n', branches=('portable',), mode=0o755)
        done = self.status('--repo', '.')
        lines = done.stdout.splitlines()
        shown = lines[lines.index('           scripts/extra.sh changed. Read the change:') + 1].strip()
        out = self.shell(shown)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn('-echo extra\n+echo more\n', out.stdout)
        # The file has the same mode at both states. The output names no mode.
        self.assertNotIn('mode', out.stdout)

    def test_a_clone_with_no_old_text_gets_the_command_that_prints_the_file(self):
        self.written()
        # A clone with a part of the history does not hold the blob that the state records.
        state = self.site / 'docgen' / 'state' / 'demo.json'
        other = self.state()
        other['pages']['install/index.mdx']['sources']['docs/setup.md'] = '0123456789abcdef0123456789abcdef01234567'
        state.write_text(json.dumps(other, indent=1, sort_keys=True) + '\n')
        done = self.status('--repo', '.')
        self.assertEqual(done.returncode, 1)
        lines = done.stdout.splitlines()
        at = lines.index('           docs/setup.md changed. The project repository does not hold the old text of this file. '
                         'Read the file as it is now:')
        shown = lines[at + 1].strip()
        self.assertEqual(shown, f'git -C {self.repo} show portable:docs/setup.md')
        out = self.shell(shown)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(out.stdout, (self.repo / 'docs' / 'setup.md').read_text())
        self.assertNotIn(' diff ', done.stdout)

    def test_status_stops_when_the_project_repository_is_older_than_the_pages(self):
        self.written()
        state = self.site / 'docgen' / 'state' / 'demo.json'
        newer = self.state()
        newer['release'] = 'portable-v0.2.0'
        state.write_text(json.dumps(newer, indent=1, sort_keys=True) + '\n')
        line = one_error_line(self, self.status('--repo', '.'), f'the project repository {self.repo} does not have the release tag '
                              "portable-v0.2.0 that the pages of 'demo' describe. Its newest release tag is portable-v0.1.0.")
        self.assertTrue(line.endswith('Do not change the project repository. Stop and tell the user this line.'), line)
        # A clone with no tag of the branch.
        self.git('tag', '-d', 'portable-v0.1.0')
        one_error_line(self, self.status('--repo', '.'), f'the project repository {self.repo} does not have the release tag '
                       "portable-v0.2.0 that the pages of 'demo' describe. It has no release tag of the branch portable.")

    def test_status_stops_when_the_project_repository_does_not_have_the_branch_of_a_page(self):
        self.written()
        state = self.site / 'docgen' / 'state' / 'demo.json'
        other = self.state()
        other['pages']['develop/workflow.mdx']['ref'] = 'topic/i9-gone'
        state.write_text(json.dumps(other, indent=1, sort_keys=True) + '\n')
        line = one_error_line(self, self.status('--repo', '.'), f'the project repository {self.repo} has no branch topic/i9-gone, '
                              "and pages of 'demo' describe that branch.")
        self.assertTrue(line.endswith('Do not make the branch. Stop and tell the user this line.'), line)


# ----- next -----

class ReadTest(Case):
    def test_next_prints_the_size_of_each_file_and_reads_a_large_file_in_parts(self):
        long_readme = '# demo\n\nStatus: prototype.\n\ndemo builds a small thing.\n\n## Parts\n\n' \
            + ''.join(f'Line {number} of the long text of this file, with some words more.\n' for number in range(1, 1201))
        self.change('README.md', long_readme)
        self.prepare()
        base.fill(self.page('index.mdx'))
        out = self.ok('next', '--project', 'demo')
        lines = out.splitlines()
        self.assertIn('slot         goal (line', out)
        # A small file: its size, and one command that reads it.
        setup = (self.repo / 'docs' / 'setup.md').read_bytes()
        at = lines.index(f'             docs/setup.md (5 lines, {len(setup)} bytes):')
        self.assertEqual(lines[at + 1], f'               git -C {self.repo} show portable:docs/setup.md')
        # A large file: one command for each part. No part is larger than one read of the shell tool.
        size, count = len(long_readme.encode()), len(docgen.file_parts(long_readme.encode()))
        self.assertGreater(size, 3 * docgen.READ_BYTES)
        self.assertGreater(count, 3)
        head = next(line for line in lines if line.startswith('             README.md ('))
        self.assertEqual(head, f'             README.md (1208 lines, {-(-size // 1024)} KB). The file is large. Read it in {count} '
                               'parts, with one command for each part:')
        commands = [line.strip() for line in lines[lines.index(head) + 1:lines.index(head) + 1 + count]]
        self.assertFalse(lines[lines.index(head) + 1 + count].startswith('               git '))
        whole = ''
        for command in commands:
            self.assertRegex(command, rf'^git -C {self.repo} show portable:README\.md \| sed -n \d+,\d+p$')
            part = self.shell(command)
            self.assertEqual(part.returncode, 0, part.stderr)
            self.assertLessEqual(len(part.stdout.encode()), docgen.READ_BYTES)
            self.assertLessEqual(len(part.stdout.splitlines()), docgen.READ_LINES)
            whole += part.stdout
        self.assertEqual(whole, long_readme)
        # The first slot of a page names its files with no other sentence.
        same = 'These are the same files as for the slot before of this page. Read a file again only when you do not have its text.'
        self.assertNotIn(same, out)
        # A later slot of the same page names the same files, and says so.
        page = self.page('install/index.mdx')
        base.fill(page, 'goal', base.sample(next(slot for slot in docgen.slots_of(page.read_text()) if slot['id'] == 'goal')))
        out = self.ok('next', '--project', 'demo')
        self.assertIn('slot         requirements (line', out)
        self.assertIn('read first   these files of the project, at the ref that the page describes:\n             ' + same + '\n', out)
        self.assertIn(head, out.splitlines())

    def test_next_prints_the_read_command_when_git_cannot_read_the_file(self):
        self.prepare()
        # A checkout with no path of the project repository: no size, and the command of each survey.
        self.work('repo').unlink()
        out = self.ok('next', '--project', 'demo')
        self.assertIn("             README.md:\n               git -C '<repo>' show portable:README.md\n", out)

    def test_the_parts_of_a_file(self):
        self.assertEqual(docgen.file_parts(b''), [])
        self.assertEqual(docgen.file_parts(b'one line with no end'), [(1, 1)])
        self.assertEqual(docgen.file_parts(b'a\nb\n'), [(1, 2)])
        # A line that is longer than one read is a part of its own.
        long_line = b'x' * (docgen.READ_BYTES + 10)
        self.assertEqual(docgen.file_parts(b'a\n' + long_line + b'\nb\n'), [(1, 1), (2, 2), (3, 3)])
        self.assertEqual(docgen.file_parts(b'a\n' * (docgen.READ_LINES + 1)), [(1, docgen.READ_LINES), (docgen.READ_LINES + 1,) * 2])
        self.assertEqual(docgen.size_text(b'a\nb'), '2 lines, 3 bytes')
        self.assertEqual(docgen.size_text(b'a\n' * 1024), '1024 lines, 2 KB')

    def test_next_names_each_compose_file_with_its_services(self):
        self.change('compose.yaml', 'services:\n  web:\n    image: demo\n  db:\n    image: store\nnetworks:\n  inner:\n')
        self.change('tools/docker-compose.yml', 'services:\n  extra:\n    image: other\n')
        self.prepare()
        base.fill(self.page('index.mdx'))
        out = self.ok('next', '--project', 'demo')
        self.assertIn('slot         goal (line', out)
        lines = out.splitlines()
        at = lines.index('facts        manifest files: compose.yaml, tools/docker-compose.yml')
        # The file `compose.yaml` is a source of the Install page. The second file is not.
        self.assertEqual(lines[at + 1:at + 4], [
            '             services of the Compose file compose.yaml: web, db.',
            '             services of the Compose file tools/docker-compose.yml: extra. This file is not a source file of this page.',
            '             test commands: python3 -m unittest discover -s tests -q'])
        self.assertNotIn('services of the Compose file:', out)


# ----- the flow of an update -----

class UpdateFlowTest(git_base.GitSiteCase):
    def tag(self, name):
        self.git('-c', 'user.name=t', '-c', 'user.email=t@example.com', 'tag', name, 'portable', cwd=self.repo)

    def shell(self, line):
        elsewhere = self.tmp / 'elsewhere'
        elsewhere.mkdir(exist_ok=True)
        done = base.run('sh', '-c', line, cwd=elsewhere)
        return done

    def follow(self, line, until):
        """Run the command of each `next` line in a new shell. Stop after the action `until`, or at a line with no `next`."""
        actions, done = [], None
        while len(actions) < 12:
            done = self.shell(line)
            actions.append(line.split()[2])
            if actions[-1] == until or not any(text.startswith('next ') for text in done.stdout.splitlines()):
                break
            self.assertEqual(done.returncode, 0, f'{line}\n{done.stdout}{done.stderr}')
            line = base.next_command(done.stdout)
        return actions, done

    def test_the_next_lines_of_an_update_go_from_survey_to_status(self):
        self.merged_doc_set()
        actions, done = self.follow(base.next_command(self.ok('survey', '--repo', '.', '--update')), 'status')
        self.assertEqual(actions, ['branch', 'plan', 'status'])
        self.assertEqual(self.branch(), UPDATE)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertEqual(done.stdout.splitlines()[-2:], [
            '0 stale item(s)',
            'The pages of demo are current, and no file of the doc set waits for a commit. Nothing to do.'])
        # For a first doc set, `plan` names `scaffold`.
        self.git('switch', '-q', git_base.FIRST)
        self.assertEqual(base.next_command(self.ok('plan', '--project', 'demo')), self.command('scaffold'))

    def test_the_pages_of_a_doc_set_in_main_keep_their_branch(self):
        self.merged_doc_set()
        # The checkout of the project gives another develop branch, or an option names it.
        out = self.ok('survey', '--repo', '.', '--update', '--develop-ref', 'portable')
        self.ok('branch', '--project', 'demo', '--update')
        tree = self.tree()
        done = self.docgen_run('plan', '--project', 'demo')
        line = one_error_line(self, done, "the pages of 'demo' describe the branch main, and the last survey read the branch "
                                          'portable for them. Nothing changed. Run first: ')
        # The owner reviewed the doc set of `main`. So the line gives the survey that keeps its branch.
        again = command_after(line, 'Run first: ')
        self.assertEqual(again, f'python3 {self.docgen} survey --repo {self.repo} --develop-ref main --update')
        self.assertEqual(self.shell(again).returncode, 0)
        self.assertEqual(base.next_command(self.ok('plan', '--project', 'demo')), self.command('status'))
        self.assertEqual(self.tree(), tree)

    def test_a_new_release_with_no_stale_page_has_a_next_step(self):
        self.merged_doc_set()
        self.tag('portable-v0.2.0')
        actions, done = self.follow(base.next_command(self.ok('survey', '--repo', '.', '--update')), 'status')
        self.assertEqual(actions, ['branch', 'plan', 'status'])
        self.assertEqual(done.returncode, 1, done.stdout + done.stderr)
        lines = done.stdout.splitlines()
        register = f'python3 {self.docgen} register --project demo --release portable-v0.2.0 --branch portable'
        capture = ('the capture script must run for the new release portable-v0.2.0: `scripts/capture.py --project demo` '
                   'records the output of each command again. Put this line into your report.')
        # The release comes first. Its lines give the command, and one line for the user.
        self.assertEqual(lines[:3], ['release  the pages describe portable-v0.1.0, the newest release is portable-v0.2.0',
                                     '           Set the new release: ' + register,
                                     '           For the user: ' + capture])
        self.assertEqual([line.split()[0] for line in lines[3:10]], ['current'] * 7)
        self.assertEqual(lines[10:], ['1 stale item(s)'])

        # The command sets the release in the site data and in the state. Its `next` line names `status`.
        tree = self.tree()
        done = self.shell(register)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertEqual(done.stdout.splitlines(), [
            'release  demo is at portable-v0.2.0 of the branch portable in src/data/versions.json',
            'recorded demo is at portable-v0.2.0 of the branch portable in docgen/state/demo.json',
            'note     ' + capture,
            'next     ' + self.command('status')])
        changed = sorted(path for path, data in self.tree().items() if tree.get(path) != data)
        self.assertEqual(changed, [STATE, 'src/data/versions.json'])
        self.assertEqual(json.loads((self.site / 'src' / 'data' / 'versions.json').read_text()),
                         {'demo': {'branch': 'portable', 'release': 'portable-v0.2.0'}})

        # `status` does not list the release again. The two files wait for a commit, so the flow goes on to the commit.
        actions, done = self.follow(self.command('status'), 'check')
        self.assertEqual(actions, ['status', 'register', 'check'])
        out = self.ok('status', '--project', 'demo')
        self.assertNotIn('release ', out)
        self.assertEqual(out.splitlines()[-2:], ['0 stale item(s)', 'next     ' + self.command('register')])
        out = self.ok('register', '--project', 'demo')
        self.assertEqual(out.splitlines(), ['kept     demo is in the project list and its release is current. No file changed.',
                                            'next     ' + self.command('check')])
        self.ok('commit', '--project', 'demo')
        self.assertEqual(self.git('log', '-1', '--format=%B'), 'Docs of demo: update to portable-v0.2.0')
        self.assertEqual(self.files_of('HEAD'), [STATE, 'src/data/versions.json'])

        # A second start of the update: no stale item, and no file, no branch and no commit changes.
        refs, tree, remote = self.refs(), self.tree(), self.refs(cwd=self.origin)
        actions, done = self.follow(base.next_command(self.ok('survey', '--repo', '.', '--update')), 'status')
        self.assertEqual(actions, ['branch', 'plan', 'status'])
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertEqual(done.stdout.splitlines()[-2:], [
            '0 stale item(s)',
            'The pages of demo are current, and no file of the doc set waits for a commit. Nothing to do.'])
        self.assertEqual((self.refs(), self.tree(), self.refs(cwd=self.origin)), (refs, tree, remote))

    def test_a_new_release_with_a_stale_page(self):
        self.merged_doc_set()
        (self.repo / 'docs' / 'setup.md').write_text('# Setup\n\n## Steps\n\nRun `python3 scripts/cli.py check`.\n')
        for words in (('switch', '-q', 'portable'), ('commit', '-q', '-am', 'Change the setup'), ('switch', '-q', 'main')):
            self.git('-c', 'user.name=t', '-c', 'user.email=t@example.com', *words, cwd=self.repo)
        self.tag('portable-v0.2.0')
        actions, done = self.follow(base.next_command(self.ok('survey', '--repo', '.', '--update')), 'status')
        self.assertEqual(done.returncode, 1)
        lines = done.stdout.splitlines()
        self.assertTrue(lines[0].startswith('release  '), lines[0])
        self.assertEqual([line.split()[1] for line in lines if line.startswith('stale ')], ['install/index.mdx', 'reference/index.mdx'])
        self.assertIn('3 stale item(s)', lines)
        # The first item is the release. Then each page has its command. No other page changes.
        tree = self.tree()
        self.assertEqual(self.shell(command_after(lines[1], 'Set the new release: ')).returncode, 0)
        out = self.docgen_run('status', '--project', 'demo').stdout
        self.assertNotIn('release ', out)
        self.assertIn('2 stale item(s)', out.splitlines())
        page = self.page('install/index.mdx')
        page.write_text(page.read_text().replace('word word word', 'word word text', 1))
        for line in out.splitlines():
            for words in ('After you correct the page: ', 'Write the page again: '):
                if words in line:
                    done = self.shell(command_after(line, words))
                    self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
                    self.assertEqual(base.next_command(done.stdout), self.command('status'))
        out = self.ok('status', '--project', 'demo')
        self.assertEqual(out.splitlines()[-2:], ['0 stale item(s)', 'next     ' + self.command('register')])
        changed = sorted(path for path, data in self.tree().items() if tree.get(path) != data)
        self.assertEqual(changed, [STATE, 'src/content/docs/demo/install/index.mdx', 'src/data/versions.json'])
        # The page of the script has the same text: the title of the file did not change. Only its record changed.
        self.ok('register', '--project', 'demo')
        self.ok('commit', '--project', 'demo')
        self.assertEqual(self.git('log', '-1', '--format=%B'), 'Docs of demo: update to portable-v0.2.0')

    def test_a_new_page_with_open_slots_has_a_next_step(self):
        self.merged_doc_set()
        # The command line of the project gets a new action. The doc set then needs one page more.
        (self.repo / 'scripts' / 'cli.py').write_text(base.CLI.replace('    actions.add_parser("check")\n',
                                                                       '    actions.add_parser("check")\n    actions.add_parser("clean")\n'))
        for words in (('switch', '-q', 'portable'), ('commit', '-q', '-am', 'A new action'), ('switch', '-q', 'main')):
            self.git('-c', 'user.name=t', '-c', 'user.email=t@example.com', *words, cwd=self.repo)
        actions, done = self.follow(base.next_command(self.ok('survey', '--repo', '.', '--update')), 'status')
        self.assertEqual(done.returncode, 1)
        new = self.page('use/commands/clean.mdx')
        self.assertFalse(new.exists())
        stale = [line.split()[1] for line in done.stdout.splitlines() if line.startswith('stale ')]
        self.assertEqual(stale, ['use/commands/build.mdx', 'use/commands/check.mdx', 'use/commands/index.mdx'])
        # The command of the first stale page records its sources, and the script writes the new page.
        first = next(line for line in done.stdout.splitlines() if 'After you correct the page: ' in line)
        done = self.shell(command_after(first, 'After you correct the page: '))
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertRegex(done.stdout, r'(?m)^wrote    use/commands/clean\.mdx +has open slots$')
        self.assertEqual(base.next_command(done.stdout), self.command('next'))
        # `status` lists the new page as an item with open slots. It is not `current`.
        out = self.docgen_run('status', '--project', 'demo').stdout.splitlines()
        at = out.index('open     use/commands/clean.mdx')
        slots = len(base.docgen.slots_of(new.read_text()))
        self.assertEqual(out[at + 2], f'           The page has {slots} open slot(s). Write each open slot first: '
                                      + self.command('next'))
        self.assertNotIn('current  use/commands/clean.mdx', out)
        # The agent writes each slot. Then `scaffold` names `status`, and the other stale pages follow.
        line, steps = self.command('next'), 0
        while steps < 20:
            done = self.shell(line)
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
            found = base.re.search(r'(?m)^page +(.+)\nslot +([\w-]+) ', done.stdout)
            if not found:
                break
            self.assertEqual(Path(found.group(1)), new)
            slot = next(slot for slot in base.docgen.slots_of(new.read_text()) if slot['id'] == found.group(2))
            base.fill(new, slot['id'], base.sample(slot).replace('scripts/cli.py build', 'scripts/cli.py clean'))
            steps += 1
        self.assertEqual(steps, slots)
        self.assertIn('No open slot.', done.stdout)
        done = self.shell(base.next_command(done.stdout))
        self.assertEqual(base.next_command(done.stdout), self.command('status'))
        while True:
            done = self.docgen_run('status', '--project', 'demo')
            again = next((line for line in done.stdout.splitlines() if 'After you correct the page: ' in line), None)
            if again is None:
                break
            self.assertEqual(self.shell(command_after(again, 'After you correct the page: ')).returncode, 0)
        self.assertEqual(done.stdout.splitlines()[-2:], ['0 stale item(s)', 'next     ' + self.command('register')])
        self.assertIn('current  use/commands/clean.mdx', done.stdout.splitlines())

    def test_register_names_the_capture_script_when_scaffold_recorded_the_new_release(self):
        # The agent corrects a page before it sets the release. `scaffold` then records the release of the facts.
        self.merged_doc_set()
        self.tag('portable-v0.2.0')
        self.follow(base.next_command(self.ok('survey', '--repo', '.', '--update')), 'plan')
        self.ok('scaffold', '--project', 'demo', '--refresh', 'install/index.mdx')
        out = self.ok('status', '--project', 'demo')
        self.assertNotIn('release ', out)
        out = self.ok('register', '--project', 'demo')
        self.assertEqual(out.splitlines(), [
            'release  demo is at portable-v0.2.0 of the branch portable in src/data/versions.json',
            'note     the capture script must run for the new release portable-v0.2.0: `scripts/capture.py --project demo` '
            'records the output of each command again. Put this line into your report.',
            'next     ' + self.command('check')])


class RegisterTest(unittest.TestCase):
    """`register` in a site that has a project list and no state of the project."""

    def setUp(self):
        import test_docgen_register as register_base
        self.case = register_base.SiteCase('setUp')
        self.case.setUp()
        self.addCleanup(self.case.doCleanups)

    def test_register_with_no_state_names_scaffold_and_no_release_that_the_site_does_not_have(self):
        case = self.case
        before = case.files()
        done = case.docgen('register', '--project', 'beta')
        self.assertEqual(done.returncode, 0, done.stderr)
        # The project `beta` has an overview and no release. The line does not say that its release is current.
        self.assertEqual(done.stdout.splitlines(), [
            'kept     beta is in the project list. The site has no release of beta. No file changed.',
            "note     this checkout has no state of 'beta' (docgen/state/beta.json is absent), so `check` cannot run for it. "
            'In a run of docgen, `scaffold` comes before `register`: ' + case.command('scaffold', 'beta')])
        self.assertEqual(case.files(), before)
        # A project with a release in the site data keeps the old words.
        done = case.docgen('register', '--project', 'alpha')
        self.assertEqual(done.stdout.splitlines()[0], 'kept     alpha is in the project list and its release is current. No file changed.')


if __name__ == '__main__':
    unittest.main()
