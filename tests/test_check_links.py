"""Tests of scripts/check_links.py, the link check of the built site."""

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHECK = ROOT / 'scripts' / 'check_links.py'

PAGE = '<!doctype html><html><head><link rel="stylesheet" href="/_astro/site.css"></head><body>{}</body></html>'


def run(arguments):
    env = {key: value for key, value in os.environ.items() if key != 'SITE_URL'}
    result = subprocess.run([sys.executable, str(CHECK)] + arguments, env=env,
                            capture_output=True, universal_newlines=True)
    return result.returncode, result.stdout + result.stderr


class CheckLinksTest(unittest.TestCase):
    def setUp(self):
        self.site = Path(tempfile.mkdtemp(prefix='links-test-'))
        self.addCleanup(shutil.rmtree, self.site)
        self.write('_astro/site.css', 'body {}')
        self.write('guide/index.html', PAGE.format('<h2 id="install">Install</h2><a name="old"></a>'))
        self.write('about.html', PAGE.format('<h2 id="team">Team</h2>'))

    def write(self, name, text):
        path = self.site / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)

    def page(self, *links):
        self.write('index.html', PAGE.format('<h1 id="_top">Home</h1>' +
                                             ''.join(f'<a href="{link}">link</a>' for link in links)))

    def test_good_links(self):
        self.page('/guide/', '/guide', '/guide/index.html', 'guide/', './guide/#install', '/guide/#old',
                  '/about', '/about.html#team', '#_top', '#top', '#', '/guide/?tab=1#install',
                  'https://example.com/missing', '//example.com/x', 'mailto:someone@example.com',
                  '/guide/#:~:text=Install')
        code, out = run([str(self.site)])
        self.assertEqual(code, 0, out)
        self.assertIn('0 broken link(s). 3 page(s)', out)

    def test_link_to_a_page_that_does_not_exist(self):
        self.page('/guide/', '/missing/')
        code, out = run([str(self.site)])
        self.assertEqual(code, 1, out)
        self.assertIn('FAIL  link  /missing/  no such page or file  in 1 page(s)', out)
        self.assertIn('index.html:1:', out)
        self.assertIn('1 broken link(s)', out)

    def test_anchor_that_does_not_exist(self):
        self.page('/guide/#uninstall', '#nowhere')
        code, out = run([str(self.site)])
        self.assertEqual(code, 1, out)
        self.assertIn('/guide/#uninstall  the page has no anchor #uninstall', out)
        self.assertIn('/index.html#nowhere  the page has no anchor #nowhere', out)

    def test_relative_link_and_asset(self):
        self.write('guide/more/index.html', PAGE.format('<a href="../">up</a><a href="../../about">about</a>'
                                                        '<a href="../../../outside">out</a>'
                                                        '<img src="/_astro/none.png" srcset="/_astro/a.png 1x">'))
        self.page('/guide/more/')
        code, out = run([str(self.site)])
        self.assertEqual(code, 1, out)
        self.assertIn('/outside  no such page or file', out)
        self.assertIn('/_astro/none.png  no such page or file', out)
        self.assertIn('/_astro/a.png  no such page or file', out)
        self.assertIn('3 broken link(s)', out)

    def test_one_line_for_a_link_that_is_broken_on_many_pages(self):
        for number in range(7):
            self.write(f'p{number}/index.html', PAGE.format('<a href="/missing/">x</a>'))
        self.page()
        code, out = run([str(self.site)])
        self.assertEqual(code, 1, out)
        self.assertIn('in 7 page(s)', out)
        self.assertIn('and 2 more', out)
        self.assertIn('1 broken link(s)', out)

    def test_link_to_the_public_origin_is_internal(self):
        self.page('https://docs.example/missing/', 'https://docs.example/guide/')
        code, out = run([str(self.site)])
        self.assertEqual(code, 0, out)
        code, out = run(['--site', 'https://docs.example', str(self.site)])
        self.assertEqual(code, 1, out)
        self.assertIn('/missing/  no such page or file', out)
        self.assertIn('1 broken link(s)', out)

    def test_no_built_site(self):
        code, out = run([str(self.site / 'absent')])
        self.assertEqual(code, 2, out)
        self.assertIn('npm run build', out)
        shutil.rmtree(self.site / 'guide')
        os.remove(self.site / 'about.html')
        code, out = run([str(self.site)])
        self.assertEqual(code, 2, out)


if __name__ == '__main__':
    unittest.main()
