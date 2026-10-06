"""Tests of src/sidebar.mjs: the sidebar of a project comes from its directory.

Each test makes the pages of one project in a temporary directory and asks Node.js for the sidebar entries.
"""

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Print the sidebar of one project and the label of each named directory, as JSON.
SCRIPT = '''
import { pathToFileURL } from 'node:url';
const [module, docs, slug, ...directories] = process.argv.slice(1);
const { projectSidebar, sectionLabel } = await import(pathToFileURL(module).href);
console.log(JSON.stringify({ sidebar: projectSidebar(docs, slug), labels: directories.map(sectionLabel) }));
'''


def group(label, directory):
    return {'label': label, 'items': [{'autogenerate': {'directory': directory}}]}


@unittest.skipUnless(shutil.which('node'), 'the sidebar module needs Node.js')
class SidebarTest(unittest.TestCase):
    def setUp(self):
        self.docs = Path(tempfile.mkdtemp(prefix='sidebar-test-'))
        self.addCleanup(shutil.rmtree, self.docs, ignore_errors=True)
        self.write('demo/index.mdx')

    def write(self, path, frontmatter=''):
        page = self.docs / path
        page.parent.mkdir(parents=True, exist_ok=True)
        page.write_text(f'---\ntitle: A page\n{frontmatter}---\n\nText.\n')

    def node(self, slug='demo', *directories):
        return subprocess.run(['node', '--input-type=module', '-e', SCRIPT, str(ROOT / 'src' / 'sidebar.mjs'),
                               str(self.docs), slug, *directories], capture_output=True, text=True)

    def sidebar(self, slug='demo'):
        done = self.node(slug)
        self.assertEqual(done.returncode, 0, done.stderr)
        return json.loads(done.stdout)['sidebar']

    def test_a_project_with_one_page_has_the_overview_entry(self):
        self.assertEqual(self.sidebar(), [{'label': 'Overview', 'slug': 'demo'}])

    def test_the_groups_of_a_doc_set_have_the_order_of_the_doc_set(self):
        # The same directories as the tenant-pi doc set.
        for path in ('reference/index.mdx', 'develop/workflow.mdx', 'use/commands/index.mdx', 'use/commands/plan.mdx',
                     'use/candidate-update.mdx', 'install/index.mdx', 'install/stage-1.mdx'):
            self.write(f'demo/{path}')
        self.assertEqual(self.sidebar(), [
            {'label': 'Overview', 'slug': 'demo'},
            group('Install', 'demo/install'),
            group('Use', 'demo/use'),
            group('Develop', 'demo/develop'),
            group('Reference', 'demo/reference'),
        ])

    def test_a_new_page_in_a_group_needs_no_new_entry(self):
        self.write('demo/install/index.mdx')
        before = self.sidebar()
        self.write('demo/install/stage-2.mdx')
        self.write('demo/install/more/deep.mdx')
        # Starlight makes the entries of a group from its directory.
        self.assertEqual(self.sidebar(), before)
        self.assertEqual(before[1], group('Install', 'demo/install'))

    def test_a_new_directory_is_a_group_after_the_groups_of_the_doc_set(self):
        for path in ('reference/index.mdx', 'install/index.mdx', 'how-to/first.md', 'api/index.mdx'):
            self.write(f'demo/{path}')
        # A directory with no page is not a group.
        (self.docs / 'demo' / 'empty').mkdir()
        (self.docs / 'demo' / 'images').mkdir()
        (self.docs / 'demo' / 'images' / 'shot.png').write_text('')
        self.assertEqual(self.sidebar()[1:], [
            group('Install', 'demo/install'),
            group('Reference', 'demo/reference'),
            group('Api', 'demo/api'),
            group('How to', 'demo/how-to'),
        ])

    def test_a_new_page_at_the_top_is_an_entry_after_the_groups(self):
        self.write('demo/install/index.mdx')
        self.write('demo/notes.mdx')
        self.write('demo/faq.md')
        self.write('demo/changes.mdx', 'sidebar:\n  label: Changes\n  order: 2\n')
        self.write('demo/draft.mdx', 'draft: true\n')
        self.write('demo/hidden.mdx', 'sidebar:\n  hidden: true\n')
        self.assertEqual(self.sidebar(), [
            {'label': 'Overview', 'slug': 'demo'},
            group('Install', 'demo/install'),
            'demo/changes',
            'demo/faq',
            'demo/notes',
        ])

    def test_a_project_with_no_overview_page_stops_the_build(self):
        self.write('other/install/index.mdx')
        for slug in ('other', 'absent'):
            done = self.node(slug)
            self.assertNotEqual(done.returncode, 0)
            self.assertIn(f'Write src/content/docs/{slug}/index.mdx', done.stderr)

    def test_the_label_of_a_directory(self):
        directories = ['install', 'use', 'develop', 'reference', 'commands', 'how-to', 'api_v2']
        done = self.node('demo', *directories)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(json.loads(done.stdout)['labels'],
                         ['Install', 'Use', 'Develop', 'Reference', 'Command reference', 'How to', 'Api v2'])


if __name__ == '__main__':
    unittest.main()
