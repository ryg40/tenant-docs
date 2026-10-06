#!/usr/bin/env python3
"""Check the internal links and anchors of the built site.

Usage: scripts/check_links.py [--site <origin>] [<directory>]

<directory> is the built site (default: dist/ of this checkout). The check
reads each HTML file in it. An internal link must go to a file of the built
site. A link with a fragment must go to a page that has an element with that id.

The check resolves a path like the web server of the site (deploy/nginx.conf):
the file, then <path>/index.html, then <path>.html.

A link to another origin is not checked. --site gives the public origin of
the site. A link that starts with this origin is internal. The default is
the environment variable SITE_URL.

Exit: 0 no broken link, 1 broken link, 2 usage error or no built site.
Needs: Python 3.8 or later.
"""

import argparse
import os
import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urljoin, urlsplit

ROOT = Path(__file__).resolve().parent.parent
# The attributes that hold a URL, for each tag.
URL_ATTRIBUTES = {
    'a': ('href',), 'area': ('href',), 'link': ('href',), 'img': ('src', 'srcset'),
    'script': ('src',), 'iframe': ('src',), 'source': ('src', 'srcset'), 'video': ('src', 'poster'),
    'audio': ('src',), 'track': ('src',), 'embed': ('src',), 'object': ('data',),
}
SCHEME_RE = re.compile(r'^[A-Za-z][A-Za-z0-9+.-]*:')
# The directory of the page sources, for the hint in the report.
PAGES_REL = 'src/content/docs'


class Page(HTMLParser):
    """The ids and the links of one HTML file."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.ids = set()
        self.links = []

    def handle_starttag(self, tag, attributes):
        values = {name: value for name, value in attributes if value is not None}
        if 'id' in values:
            self.ids.add(values['id'])
        if tag == 'a' and 'name' in values:
            self.ids.add(values['name'])
        line, column = self.getpos()
        for name in URL_ATTRIBUTES.get(tag, ()):
            if name not in values:
                continue
            if name == 'srcset':
                urls = [part.split()[0] for part in values[name].split(',') if part.split()]
            else:
                urls = [values[name].strip()]
            for url in urls:
                self.links.append((url, line, column + 1))

    handle_startendtag = handle_starttag


def resolve(site, path):
    """The file of the built site that answers a URL path, or None."""
    relative = unquote(path).lstrip('/')
    target = (site / relative).resolve()
    if site != target and site not in target.parents:
        return None
    if target.is_file():
        return target
    candidates = [target / 'index.html']
    if not path.endswith('/') and target != site:
        candidates.append(target.with_name(target.name + '.html'))
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def source_hint(relative):
    """The page source of a built page, when it exists."""
    route = relative[:-len('index.html')].strip('/') if relative.endswith('index.html') else relative[:-len('.html')]
    for candidate in (f'{route}.mdx', f'{route}.md', f'{route}/index.mdx', f'{route}/index.md'):
        candidate = f'{PAGES_REL}/{candidate.lstrip("/")}'
        if (ROOT / candidate).is_file():
            return candidate
    return None


def check(site, origin=''):
    """Return (broken, pages, links): broken is {(target, reason): [(file, line, column)]}."""
    site = site.resolve()
    pages = {}
    for folder, dirs, files in os.walk(site):
        dirs.sort()
        for name in sorted(files):
            if name.endswith(('.html', '.htm')):
                path = Path(folder) / name
                page = Page()
                page.feed(path.read_text(encoding='utf-8', errors='replace'))
                page.close()
                pages[path] = page
    origin = origin.rstrip('/')
    broken, count = {}, 0
    for path, page in pages.items():
        relative = path.relative_to(site).as_posix()
        for url, line, column in page.links:
            if origin and (url == origin or url.startswith(origin + '/')):
                url = url[len(origin):] or '/'
            if not url or SCHEME_RE.match(url) or url.startswith('//'):
                continue
            count += 1
            parts = urlsplit(urljoin('/' + relative, url))
            target = path if url.startswith(('#', '?')) else resolve(site, parts.path)
            reason = None
            if target is None:
                reason = 'no such page or file'
            elif parts.fragment and target in pages:
                fragment = unquote(parts.fragment)
                # "#top" is the top of the page. A text fragment selects text, not an element.
                if fragment not in pages[target].ids and fragment.lower() != 'top' and not fragment.startswith(':~:'):
                    reason = f'the page has no anchor #{fragment}'
            if reason:
                shown = '/' + parts.path.lstrip('/') + ('#' + parts.fragment if parts.fragment else '')
                broken.setdefault((shown, reason), []).append((relative, line, column))
    return broken, len(pages), count


def main(argv=None):
    parser = argparse.ArgumentParser(description='Check the internal links and anchors of the built site.',
                                     epilog='Exit: 0 no broken link, 1 broken link, 2 usage error or no built site.')
    parser.add_argument('--site', metavar='ORIGIN', default=os.environ.get('SITE_URL', ''),
                        help='the public origin of the site (default: the variable SITE_URL)')
    parser.add_argument('directory', nargs='?', default=str(ROOT / 'dist'), help='the built site (default: dist/)')
    options = parser.parse_args(argv)

    site = Path(options.directory)
    if not site.is_dir():
        print(f'links: error: {site} does not exist. Run "npm run build" first.', file=sys.stderr)
        return 2
    broken, pages, links = check(site, options.site)
    if pages == 0:
        print(f'links: error: {site} has no HTML file. Run "npm run build" first.', file=sys.stderr)
        return 2
    shown_site = os.path.relpath(site)
    if shown_site.startswith('..'):
        shown_site = str(site)
    for (target, reason), places in sorted(broken.items()):
        print(f'FAIL  link  {target}  {reason}  in {len(places)} page(s):')
        for relative, line, column in places[:5]:
            hint = source_hint(relative)
            print(f'      {shown_site}/{relative}:{line}:{column}' + (f'  (source: {hint})' if hint else ''))
        if len(places) > 5:
            print(f'      and {len(places) - 5} more')
    print(f'links: {len(broken)} broken link(s). {pages} page(s), {links} internal link(s).')
    return 1 if broken else 0


if __name__ == '__main__':
    sys.exit(main())
