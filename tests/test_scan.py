"""Tests of scripts/scan.py, the host-value scanner.

Each sample value is built at run time from parts. So this file holds no
value that the scanner finds.
"""

import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCAN = ROOT / 'scripts' / 'scan.py'
RULE_FILES = ('host-values.regex', 'host-values.allow', 'host-values.local.deny.example', '.gitignore')

spec = importlib.util.spec_from_file_location('scan', SCAN)
scan = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scan)


def j(*parts):
    return ''.join(parts)


LETTERS = 'Zx9QwEr7TyUi3OpAs5DfGh1JkLz2XcVbNm4Q'  # 36 characters

# One sample for each generic rule. The scanner must find each one.
SAMPLES = {
    'private-ip-10': j('host = 10', '.20.30.40'),
    'private-ip-172': j('host = 172', '.20.1.2'),
    'private-ip-192': j('http', '://192', '.168.1.2:8080/'),
    'private-ip-100': j('peer 100', '.100.1.2'),
    'private-ip-169': j('addr 169', '.254.1.2'),
    'private-ip-after-tag': j('<code dir="auto">192', '.168.7.20</code>'),
    'private-ip-after-tag-end': j('<code\n   dir="auto">192', '.168.7.20</code>'),
    'private-ip-after-comment': j('<!-- the address -->192', '.168.7.20'),
    'private-ip-ula': j('addr fd12', ':3456::1'),
    'private-ip-fe80': j('addr fe80', '::1'),
    'home-path-unix': j('cd /ho', 'me/alice/project'),
    'home-path-root': j('cd /ro', 'ot/.config'),
    'home-path-windows': j('cd C:', '\\Users', '\\alice\\project'),
    'opt-path': j('cd /op', 't/stacks/project'),
    'internal-url-tld': j('see http', '://wiki.corp', '.internal/page'),
    'internal-url-host': j('see http', '://nas:5000/share'),
    'credential-private-key': j('-----BEGIN OPENSSH ', 'PRIVATE KEY-----'),
    'credential-github-token': j('ghp', '_', LETTERS),
    'credential-gitlab-token': j('glpat', '-', LETTERS[:24]),
    'credential-aws-key-id': j('AKIA', 'ABCDEFGHIJKLMNOP'),
    'credential-slack-token': j('xoxb', '-1234567890-abcdefghij'),
    'credential-google-api-key': j('AIza', LETTERS[:35]),
    'credential-npm-token': j('npm', '_', LETTERS),
    'credential-hf-token': j('hf', '_', LETTERS),
    'credential-sk-key': j('sk', '-', LETTERS[:30]),
    'credential-jwt': j('eyJ', 'hbGciOiJIUzI1NiJ9', '.eyJ', 'zdWIiOiIxMjM0NTY3ODkwIn0', '.', LETTERS[:20]),
    'credential-url-password': j('https', '://deploy', ':hunter22', '@git.example.com/repo.git'),
    'credential-auth-header': j('Authorization', ': Bearer ', LETTERS[:30]),
    'credential-assignment': j('API_TOKEN', '=', LETTERS[:30]),
}

# Text that looks like a host value and is not one. The scanner must find nothing.
CLEAN = '\n'.join([
    j('pin = "pkg==10', '.2.3.4" "pkg>=10', '.2.3.4" pkg-10', '.2.3.4 v10', '.2.3.4 10', '.2.3.4.dev0'),
    j('loopback = 127', '.0.0.1 ::1 and docs = 192', '.0.2.10 198', '.51.100.7 203', '.0.113.9'),
    j('placeholders: /ho', 'me/<user> /ho', 'me/$USER ~/tenant-pi ~/.pi-candidate'),
    j('relative: src/ho', 'me/page.astro docs/op', 't/readme.md'),
    j('public: https://docs.example/ho', 'me/alice https://example.com/op', 't/tool/'),
    j('local: http', '://localhost:4321/ and http', '://<host>:8080/'),
    j('names: GITEA_TOKEN', '=$GITEA_TOKEN and token', ': ${{ secrets.TOKEN }} and password', '=<your password>'),
    j('url: https://<user>', ':<token>', '@git.example.com/repo.git'),
    j('header: Authorization', ': token $GITEA_TOKEN'),
    'a commit: 5092ad7f3c1e4b6a9d8e7f6a5b4c3d2e1f0a9b8c',
    # A ">" with no tag before it is a version pin. A tag with a public address after it is clean.
    j('pins: pkg>10', '.2.3.4 and "<2.0,>10', '.2.3.4" and <b>pkg</b>>=10', '.2.3.4'),
    j('tags: <code>127', '.0.0.1</code> <td>192', '.0.2.10</td> <code>10', '.2.3.4.dev0</code>'),
    # A tag that ends on a second line, and a comment, with a public address after them. A pin with a quote before it.
    j('<code\n   dir="auto">192', '.0.2.10</code> <!-- c -->127', '.0.0.1 and \'pkg>10', '.2.3.4\' and "pkg" >10', '.2.3.4'),
    '',
])


def clean_env():
    """The environment without the variables of a Git hook and without a local deny list."""
    return {key: value for key, value in os.environ.items()
            if not key.startswith('GIT_') and key != 'SCAN_LOCAL_DENY'}


def run(arguments, script=SCAN, cwd=None, text=None):
    result = subprocess.run([sys.executable, str(script)] + arguments, cwd=cwd, env=clean_env(),
                            input=text, capture_output=True, universal_newlines=True)
    return result.returncode, result.stdout, result.stderr


class ScanFileTest(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix='scan-test-'))
        self.addCleanup(shutil.rmtree, self.dir)
        # An empty local deny list: the tests do not depend on the list of this host.
        self.deny = self.dir / 'deny'
        self.deny.write_text('')

    def scan(self, text, name='test.txt'):
        path = self.dir / name
        path.write_text(text)
        code, out, _ = run(['--local-deny', str(self.deny), str(path)])
        findings = [line for line in out.splitlines() if line.startswith('FAIL')]
        return code, findings, out

    def test_address_path_and_url_give_one_finding_each(self):
        text = '\n'.join([SAMPLES['private-ip-10'], SAMPLES['home-path-unix'], SAMPLES['internal-url-tld'], ''])
        code, findings, out = self.scan(text)
        self.assertEqual(code, 1, out)
        self.assertEqual(len(findings), 3, out)
        for number, rule in enumerate(('private-ip-10', 'home-path-unix', 'internal-url-tld'), 1):
            self.assertIn(f'test.txt:{number}:', findings[number - 1])
            self.assertIn(f'rule {rule}', findings[number - 1])

    def test_each_generic_rule_finds_its_sample(self):
        rules = [rule.name for rule in scan.load_rules(ROOT / scan.REGEX_REL)]
        self.assertEqual(sorted(rules), sorted(SAMPLES), 'each rule of the regex file needs one sample in this test')
        for name in rules:
            with self.subTest(rule=name):
                code, findings, out = self.scan(SAMPLES[name] + '\n')
                self.assertEqual(code, 1, out)
                self.assertTrue(any(f'rule {name}' in line for line in findings), out)

    def test_an_address_directly_after_a_tag_gives_one_finding(self):
        # The built site writes inline code as a tag, then the address. The character before the address is ">".
        addresses = (j('10', '.20.30.40'), j('172', '.20.1.2'), j('192', '.168.7.20'), j('100', '.80.1.2'),
                     j('169', '.254.10.20'))
        for address in addresses:
            with self.subTest(address=address):
                code, findings, out = self.scan(f'<p>x <code dir="auto">{address}</code> y</p>\n<td>{address}</td>\n')
                self.assertEqual(code, 1, out)
                self.assertEqual(len(findings), 2, out)
                for number, column in ((1, 23), (2, 5)):
                    self.assertIn(f'test.txt:{number}:{column}  rule private-ip-after-tag  {address}', findings[number - 1])
        # An address after a blank has one finding of its own rule, and no second finding.
        code, findings, out = self.scan(f'<p>the address {addresses[2]} is private</p>\n')
        self.assertEqual((code, len(findings)), (1, 1), out)
        self.assertIn('rule private-ip-192', findings[0])

    def test_an_address_after_a_tag_of_two_lines_and_after_a_comment_gives_one_finding(self):
        # The tag starts on the line before, so the line of the address has no start of a tag.
        addresses = (j('10', '.20.30.40'), j('172', '.20.1.2'), j('192', '.168.7.20'), j('100', '.80.1.2'),
                     j('169', '.254.10.20'))
        for address in addresses:
            with self.subTest(address=address):
                code, findings, out = self.scan(f'<span\n   class="x">{address}</span>\n<a\n  href=\'/y\' >{address}</a>\n'
                                                f'<!-- c -->{address}\n')
                self.assertEqual(code, 1, out)
                self.assertEqual(len(findings), 3, out)
                self.assertIn(f'test.txt:2:14  rule private-ip-after-tag-end  {address}', findings[0])
                self.assertIn(f'test.txt:4:14  rule private-ip-after-tag-end  {address}', findings[1])
                self.assertIn(f'test.txt:5:11  rule private-ip-after-comment  {address}', findings[2])
        # A tag on one line has the finding of its own rule only.
        code, findings, out = self.scan(f'<span class="x">{addresses[0]}</span>\n')
        self.assertEqual((code, len(findings)), (1, 1), out)
        self.assertIn('rule private-ip-after-tag  ', findings[0])

    def test_a_home_path_directly_after_the_scheme_of_a_url_gives_one_finding(self):
        # A `file` URL has no host name: its path starts directly after `://`.
        root, home = j('/ro', 'ot'), j('/ho', 'me/dana')
        code, findings, out = self.scan(f'Open file://{root}/site/index.html in a browser.\n'
                                        f'Open `file://{home}/site/index.html` in a browser.\n')
        self.assertEqual(code, 1, out)
        self.assertEqual(len(findings), 2, out)
        self.assertIn(f'test.txt:1:13  rule home-path-root  {root}', findings[0])
        self.assertIn(f'test.txt:2:14  rule home-path-unix  {home}', findings[1])
        # A second `/` inside a path starts no path, and a longer name is another name.
        code, findings, out = self.scan(f'see https://example.com/{root}/x and a/{root}/x and file://{root}fs\n')
        self.assertEqual((code, findings), (0, []), out)
        # The user name of a URL is no path: it has one `/` of the `://` before it, and not three characters.
        rule = next(rule for rule in scan.load_rules(ROOT / scan.REGEX_REL) if rule.name == 'home-path-root')
        self.assertIsNone(rule.regex.search(j('ssh:/', root, '@git.example.com/repo.git')))

    def test_text_that_is_no_host_value_gives_no_finding(self):
        code, findings, out = self.scan(CLEAN)
        self.assertEqual((code, findings), (0, []), out)

    def test_report_does_not_show_a_credential(self):
        token = SAMPLES['credential-github-token']
        code, findings, out = self.scan(f'token = "{token}"\n')
        self.assertEqual(code, 1, out)
        self.assertNotIn(token, out)
        self.assertIn('(value not shown)', out)

    def test_local_deny_list_ignores_case_and_hides_the_value(self):
        self.deny.write_text('# comment\n\nMy-Machine\n')
        code, findings, out = self.scan('ssh admin@my-machine\nssh admin@MY-MACHINE-2\nssh admin@other\n')
        self.assertEqual(code, 1, out)
        self.assertEqual(len(findings), 2, out)
        self.assertTrue(all('rule local-1' in line for line in findings), out)
        self.assertNotIn('machine', ' '.join(line.split('rule', 1)[1] for line in findings).lower())

    def test_local_deny_list_that_is_named_must_exist(self):
        code, _, err = run(['--local-deny', str(self.dir / 'absent'), str(self.deny)])
        self.assertEqual(code, 2)
        self.assertIn('does not exist', err)

    def test_allow_list_drops_the_exact_value_only(self):
        allowed = j('http', '://host.docker', '.internal')
        code, findings, out = self.scan(f'url = {allowed}:8080/\n')
        self.assertEqual((code, findings), (0, []), out)
        code, findings, out = self.scan(f'url = {allowed.replace("host", "other")}:8080/\n')
        self.assertEqual(code, 1, out)

    def test_standard_input(self):
        code, out, _ = run(['--local-deny', str(self.deny), '-'], text=SAMPLES['opt-path'] + '\n')
        self.assertEqual(code, 1, out)
        self.assertIn('(standard input):1:', out)

    def test_binary_file(self):
        path = self.dir / 'image.bin'
        path.write_bytes(b'\x89PNG\0\0' + SAMPLES['home-path-unix'].encode() + b'\0\xff')
        code, out, _ = run(['--local-deny', str(self.deny), str(path)])
        self.assertEqual(code, 1, out)
        self.assertIn('(binary file)', out)

    def test_rule_files_and_tests_hold_no_finding(self):
        files = [ROOT / 'scripts' / name for name in RULE_FILES + ('scan.py', 'check_links.py', 'lint_ste.py')]
        files += sorted((ROOT / 'tests').glob('test_*.py'))
        code, out, _ = run(['--local-deny', str(self.deny)] + [str(path) for path in files])
        self.assertEqual(code, 0, out)


class RuleFileTest(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix='scan-test-'))
        self.addCleanup(shutil.rmtree, self.dir)

    def write(self, name, text):
        path = self.dir / name
        path.write_text(text)
        return path

    def test_macro(self):
        rules = scan.load_rules(self.write('r', 'define DIGIT [0-9]\nnumber-pair x{DIGIT}{2}y\n'))
        self.assertTrue(rules[0].regex.search('x12y'))
        self.assertEqual(rules[0].kind, 'host value')

    def test_bad_rule_files(self):
        for text in ('', 'only-a-name\n', 'Bad_Name x\n', 'local-1 x\n', 'a x\na y\n', 'a (\n', 'a x*\n', 'a {NONE}\n'):
            with self.subTest(text=text):
                with self.assertRaises(scan.ConfigError):
                    scan.load_rules(self.write('r', text))

    def test_allow_list_does_not_apply_to_a_credential_rule(self):
        rules = scan.load_rules(self.write('r', 'credential-x secret[0-9]+\nhost-x host[0-9]+\n'))
        self.assertEqual(scan.load_allow(self.write('a', 'host-x host1\n'), rules), {('host-x', 'host1')})
        for text in ('credential-x secret1\n', 'no-rule value\n', 'host-x\n'):
            with self.subTest(text=text):
                with self.assertRaises(scan.ConfigError):
                    scan.load_allow(self.write('a', text), rules)


@unittest.skipUnless(shutil.which('git'), 'needs git')
class ScanRepositoryTest(unittest.TestCase):
    """The scan of a repository: a copy of the scanner in a new Git repository."""

    def setUp(self):
        self.repo = Path(tempfile.mkdtemp(prefix='scan-test-'))
        self.addCleanup(shutil.rmtree, self.repo)
        (self.repo / 'scripts').mkdir()
        shutil.copy(SCAN, self.repo / 'scripts')
        for name in RULE_FILES:
            shutil.copy(ROOT / 'scripts' / name, self.repo / 'scripts')
        self.git('init', '-q')
        self.write('README.md', 'A clean file.\n')
        self.git('add', '-A')

    def git(self, *arguments):
        subprocess.run(('git',) + arguments, cwd=self.repo, env=clean_env(), check=True, capture_output=True)

    def write(self, name, text):
        path = self.repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)

    def scan(self, *arguments):
        code, out, err = run(list(arguments), script=self.repo / 'scripts' / 'scan.py', cwd=self.repo)
        return code, [line for line in out.splitlines() if line.startswith('FAIL')], out + err

    def test_clean_repository(self):
        code, findings, out = self.scan()
        self.assertEqual((code, findings), (0, []), out)
        self.assertIn('no local deny list', out)

    def test_tracked_file(self):
        self.write('docs/page.md', 'line one\n' + SAMPLES['private-ip-192'] + '\n')
        self.git('add', '-A')
        code, findings, out = self.scan()
        self.assertEqual(code, 1, out)
        self.assertEqual(len(findings), 1, out)
        self.assertIn('docs/page.md:2:', findings[0])

    def test_staged_content_counts_when_the_working_tree_is_clean(self):
        self.write('page.md', SAMPLES['home-path-unix'] + '\n')
        self.git('add', '-A')
        self.write('page.md', 'clean again\n')
        code, findings, out = self.scan()
        self.assertEqual((code, len(findings)), (1, 1), out)

    def test_working_tree_content_counts_when_the_staged_content_is_clean(self):
        self.write('README.md', SAMPLES['opt-path'] + '\n')
        code, findings, out = self.scan()
        self.assertEqual((code, len(findings)), (1, 1), out)

    def test_untracked_file_outside_captures_is_not_scanned(self):
        self.write('notes.txt', SAMPLES['private-ip-10'] + '\n')
        code, findings, out = self.scan()
        self.assertEqual((code, findings), (0, []), out)

    def test_file_name(self):
        self.write(j('10', '.20.30.40', '/notes.md'), 'clean\n')
        self.git('add', '-A')
        code, findings, out = self.scan()
        self.assertEqual(code, 1, out)
        self.assertIn('(file name)', findings[0])

    def test_capture_that_is_not_tracked(self):
        self.write('captures/tenant-pi/validate.txt', '$ run\n' + SAMPLES['home-path-root'] + '\n')
        code, findings, out = self.scan()
        self.assertEqual(code, 1, out)
        self.assertIn('captures/tenant-pi/validate.txt:2:', findings[0])

    def test_built_site(self):
        self.write('dist/page/index.html', '<p>' + SAMPLES['internal-url-tld'] + '</p>\n')
        code, findings, out = self.scan()
        self.assertEqual(code, 1, out)
        self.assertIn('dist/page/index.html:1:', findings[0])
        code, findings, out = self.scan('--no-dist')
        self.assertEqual((code, findings), (0, []), out)

    def test_work_files_of_a_build_that_failed_are_not_scanned(self):
        # A build that fails leaves dist/.prerender. No person wrote its files, and no person can correct them.
        self.write('dist/.prerender/chunks/path.mjs', 'const u = "' + SAMPLES['internal-url-host'] + '";\n')
        self.write('dist/page/index.html', '<p>A clean page.</p>\n')
        code, findings, out = self.scan()
        self.assertEqual((code, findings), (0, []), out)
        self.assertIn('dist/.prerender holds the work files of a build that failed', out)
        # Only that one directory of dist/. A directory with the same name at another place is scanned.
        self.write('dist/page/.prerender/x.html', '<p>' + SAMPLES['internal-url-tld'] + '</p>\n')
        self.write('docs/.prerender/page.md', SAMPLES['opt-path'] + '\n')
        self.git('add', 'docs')
        code, findings, out = self.scan()
        self.assertEqual(code, 1, out)
        self.assertEqual(sorted(line.split()[3].split(':')[0] for line in findings),
                         ['dist/page/.prerender/x.html', 'docs/.prerender/page.md'], out)

    def test_local_deny_list_of_the_checkout(self):
        self.write('scripts/host-values.local.deny', 'my-machine\n')
        self.write('README.md', 'The server is My-Machine.\n')
        code, findings, out = self.scan()
        self.assertEqual(code, 1, out)
        self.assertIn('rule local-1', findings[0])
        self.assertNotIn('no local deny list', out)
        # Git ignores the list, so "git add -A" does not track it.
        self.git('add', '-A')
        code, findings, out = self.scan()
        self.assertFalse(any('policy' in line for line in findings), out)

    def test_policy_findings(self):
        self.write('scripts/host-values.local.deny', 'my-machine\n')
        self.write('.env', 'SITE_URL=https://docs.example\n')
        self.write('.env.example', 'SITE_URL=https://docs.example\n')
        self.git('add', '-A', '-f')
        code, findings, out = self.scan()
        self.assertEqual(code, 1, out)
        self.assertEqual(sorted(line.split()[2] for line in findings if ' policy ' in line),
                         ['.env', 'scripts/host-values.local.deny'], out)

    def test_directory_that_is_no_repository(self):
        shutil.rmtree(self.repo / '.git')
        self.write('page.md', SAMPLES['private-ip-172'] + '\n')
        code, findings, out = self.scan()
        self.assertEqual((code, len(findings)), (1, 1), out)
        self.assertIn('no Git working tree', out)


if __name__ == '__main__':
    unittest.main()
