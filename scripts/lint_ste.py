#!/usr/bin/env python3
"""Simplified English lint for the pages.

Usage: scripts/lint_ste.py [--gate] [<path>...]

<path> is a Markdown or MDX file, or a directory with such files
(default: src/content/docs of this checkout).

Rules:
  sentence-length  A sentence has 20 words at most in a step and 25 words at
                   most in other text.
  warning-form     A warning is its own line and starts with "Warning:".
  step-actions     A step has one action.
  example-form     A block of typed output has the title "Example", and the
                   line before it says "It is not a capture."

A step is an item of a numbered list. Other text is a paragraph, a bullet, a
table cell, a heading, the title and the description of the page, and the
text of a component attribute such as title="...".
The lint does not read code blocks, inline code counts as one word, and a
link counts as its text. A block of typed output is a code block with the
language "text".

The lint is a report: it prints each finding and exits with 0.
With --gate, a finding gives the exit code 1.

Exit: 0 no finding or report mode, 1 finding in gate mode, 2 usage error.
Needs: Python 3.8 or later.
"""

import argparse
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PAGES_REL = 'src/content/docs'
STEP_WORDS = 20
TEXT_WORDS = 25

# One inline code span is CODE_OPEN, its number, CODE_CLOSE. It counts as one word.
CODE_OPEN, CODE_CLOSE = '', ''

# Verbs that start an instruction.
VERBS = (
    'add apply approve attach build call change check choose click clone close commit compare configure '
    'confirm copy create delete deploy disable download edit enable enter export fetch fill find fix follow '
    'generate give go import install launch list load log make merge mount move name open paste pick press '
    'print pull push put read rebase record reload remove rename repeat replace restart restore run save '
    'scroll select send set show sign start stop switch tag tell test type uninstall unpack update upload '
    'use validate verify wait write'
).split()
# A sentence that starts with one of these tells the reader which result to check. It is not a second action.
RESULT_STARTS = ('check that', 'check if', 'check whether', 'make sure', 'verify that', 'confirm that', 'wait')
# Words that follow a verb. They show that the word before them is a verb and not a noun.
FOLLOW = (r'(?=(?:the|a|an|each|every|all|any|your|its|it|them|this|that|these|those|one|both|to|into|in|on|off|'
          r'out|up|down|again|with|for|from|if|whether|sure)\b|[' + CODE_OPEN + r'<\[("\'$~/.0-9A-Z])')
VERB_GROUP = '(' + '|'.join(VERBS) + ')'
THEN_RE = re.compile(r'(?:[,;]|\band)\s+then\b', re.IGNORECASE)
AND_VERB_RE = re.compile(r'(?:\band|;)\s+' + VERB_GROUP + r'\s+' + FOLLOW)
COMMA_VERB_RE = re.compile(r',\s+' + VERB_GROUP + r'\s+' + FOLLOW)
FIRST_WORD_RE = re.compile(r'^[^A-Za-z' + CODE_OPEN + r']*([A-Za-z]+)')

FENCE_RE = re.compile(r'^\s*(?:>\s?)*(`{3,}|~{3,})')
CODE_SPAN_RE = re.compile(r'(`+)(.+?)\1(?!`)')
# A block of typed output has this title, and the line before it holds this sentence.
EXAMPLE_TITLE_RE = re.compile(r'\btitle=(["\'])Example\1')
EXAMPLE_SENTENCE = 'It is not a capture.'
COMMENT_RE = re.compile(r'<!--.*?-->|\{/\*.*?\*/\}', re.DOTALL)
QUOTE_RE = re.compile(r'^\s*>\s?')
ASIDE_OPEN_RE = re.compile(r'^\s*:::\s*(\w+)\s*(?:\[(.*)\])?\s*$')
ASIDE_CLOSE_RE = re.compile(r'^\s*:::\s*$')
HEADING_RE = re.compile(r'^\s{0,3}#{1,6}\s+(.*?)\s*#*\s*$')
RULE_RE = re.compile(r'^\s*([-*_])(?:\s*\1){2,}\s*$')
TABLE_RULE_RE = re.compile(r'^\s*\|?[\s:|-]*-[\s:|-]*\|?\s*$')
ITEM_RE = re.compile(r'^(\s*)(\d+[.)]|[-*+])\s+(?:\[[ xX]\]\s+)?(.*)$')
ATTRIBUTE_RE = re.compile(r'(?<![\w-])(?:title|description|alt|caption|text|label|summary|tagline)\s*[=:]\s*'
                          r'(?:"([^"]*)"|\'([^\']*)\')')
ASIDE_TAG_RE = re.compile(r'^Aside\b.*\btype\s*=\s*["\'](?:caution|danger)["\']', re.DOTALL)
FRONTMATTER_RE = re.compile(r'^(\s*)(?:-\s+)?(?:title|description|tagline)\s*:\s*(.*)$')

# A warning label at the start of a line, in each form.
LABEL_RE = re.compile(r'^[*_]{0,3}(warning|caution|danger)[*_]{0,3}\s*(?:[:!]|[-–—]\s)', re.IGNORECASE)
GOOD_LABEL_RE = re.compile(r'^Warning:(?:\s|$)')
LATER_LABEL_RE = re.compile(r'\b(?:Warning|WARNING|Caution|CAUTION):')

BOUNDARY_RE = re.compile(r'[.!?]+[")\]\'”’]*\s+(?=["(\[\'“‘]*[A-Z0-9' + CODE_OPEN + '])')
ABBREVIATIONS = ('e.g.', 'i.e.', 'etc.', 'vs.', 'cf.', 'approx.', 'fig.')
WORD_RE = re.compile(r'[\w' + CODE_OPEN + ']')


class Block:
    """One unit of text: a paragraph, a list item, a table cell, a heading or an attribute."""

    def __init__(self, kind, item=0):
        self.kind = kind          # 'step' or 'text'
        self.item = item          # the number of the list item, for a step
        self.parts = []           # (line number, text)
        self.warning = False

    def add(self, line, text):
        self.parts.append((line, text))


class Parser:
    def __init__(self):
        self.blocks = []
        self.findings = []
        self.codes = []
        self.current = None
        self.items = []           # the open list items: (kind, indent of the marker, number)
        self.item_count = 0
        self.aside = None         # the line of a caution aside that waits for its first text line
        self.tag = None           # the state inside a tag that continues on the next line: [quote, depth]

    def close(self):
        self.current = None

    def mask_code(self, line):
        def keep(match):
            self.codes.append(match.group(2).strip())
            return f'{CODE_OPEN}{len(self.codes) - 1}{CODE_CLOSE}'
        return CODE_SPAN_RE.sub(keep, line)

    def split_tags(self, line):
        """Split a line into the text outside tags and the text inside tags."""
        outside, inside = [], []
        quote, depth = self.tag if self.tag else ('', 0)
        in_tag = self.tag is not None
        index = 0
        while index < len(line):
            char = line[index]
            if not in_tag:
                following = line[index + 1:index + 2]
                escaped = index > 0 and line[index - 1] == '\\'
                if char == '<' and not escaped and (following.isalpha() or following in ('/', '>')):
                    in_tag, quote, depth = True, '', 0
                    inside.append(' ')
                else:
                    outside.append(char)
            elif quote:
                inside.append(char)
                if char == quote:
                    quote = ''
            elif char in '"\'':
                quote = char
                inside.append(char)
            elif char == '{':
                depth += 1
                inside.append(char)
            elif char == '}':
                depth = max(0, depth - 1)
                inside.append(char)
            elif char == '>' and depth == 0:
                in_tag = False
                outside.append(' ')
            else:
                inside.append(char)
            index += 1
        self.tag = (quote, depth) if in_tag else None
        return ''.join(outside), ''.join(inside)

    def start(self, kind, indent):
        """Start a block. Its kind comes from the list item that holds it."""
        while self.items and self.items[-1][1] >= indent:
            self.items.pop()
        item = 0
        if kind is None:
            kind = self.items[-1][0] if self.items else 'text'
            item = self.items[-1][2] if self.items else 0
        self.current = Block(kind, item)
        self.blocks.append(self.current)
        return self.current

    def text_line(self, number, text, indent, new_block=False):
        """Add one line of text to the open block, or start a block."""
        text = text.strip()
        if not text:
            return
        label = LABEL_RE.match(text)
        if label or new_block or self.current is None:
            self.start(None, indent)
        if label:
            self.current.kind, self.current.warning = 'text', True
        self.current.add(number, text)

    def single(self, number, text):
        """A block of one line that is not part of a list item: a heading, a cell, an attribute."""
        block = Block('text')
        block.add(number, text.strip())
        self.blocks.append(block)

    def frontmatter(self, lines, first):
        index = 0
        while index < len(lines):
            match = FRONTMATTER_RE.match(lines[index])
            index += 1
            if not match:
                continue
            indent, value = len(match.group(1)), match.group(2).strip()
            block = Block('text')
            if value in ('>', '>-', '>+', '|', '|-', '|+'):
                while index < len(lines) and (not lines[index].strip() or
                                              len(lines[index]) - len(lines[index].lstrip()) > indent):
                    if lines[index].strip():
                        block.add(first + index, self.mask_code(lines[index].strip()))
                    index += 1
            elif value:
                if len(value) > 1 and value[0] == value[-1] and value[0] in '"\'':
                    value = value[1:-1]
                block.add(first + index - 1, self.mask_code(value))
            if block.parts:
                self.blocks.append(block)

    def parse(self, text):
        text = COMMENT_RE.sub(lambda match: re.sub(r'[^\n]', ' ', match.group(0)), text)
        lines = text.split('\n')
        index = 0
        if lines and lines[0].strip() == '---':
            for end in range(1, len(lines)):
                if lines[end].strip() == '---':
                    self.frontmatter(lines[1:end], 2)
                    index = end + 1
                    break
        fence = None
        module = False
        for number, raw in enumerate(lines[index:], index + 1):
            match = FENCE_RE.match(raw)
            if fence:
                if match and match.group(1).startswith(fence) and not raw.strip().lstrip('> ').strip(fence[0]):
                    fence = None
                continue
            if match and self.tag is None:
                fence = match.group(1)
                self.close()
                continue
            if not raw.strip():
                self.close()
                self.tag = None
                module = False
                continue
            # An import or an export of MDX, to the next empty line.
            if module or (self.current is None and self.tag is None and re.match(r'(?:import|export)\s', raw)):
                module = True
                continue
            line = raw
            while QUOTE_RE.match(line):
                line = QUOTE_RE.sub('', line, count=1)
            indent = len(line) - len(line.lstrip())
            if ASIDE_CLOSE_RE.match(line):
                self.close()
                self.aside = None
                continue
            match = ASIDE_OPEN_RE.match(line)
            if match:
                self.close()
                if match.group(2):
                    self.single(number, self.mask_code(match.group(2)))
                self.aside = number if match.group(1) in ('caution', 'danger') else None
                continue
            if RULE_RE.match(line):
                self.close()
                continue
            line = self.mask_code(line)
            was_in_tag = self.tag is not None
            outside, inside = self.split_tags(line)
            for match in ATTRIBUTE_RE.finditer(inside):
                value = match.group(1) if match.group(1) is not None else match.group(2)
                if value.strip():
                    self.single(number, value)
            if ASIDE_TAG_RE.match(inside.strip()):
                self.aside = number
            outside = re.sub(r'\{[^{}]*\}', ' ', outside)
            if not outside.strip():
                # A line with tags only ends the block.
                if inside.strip() and not was_in_tag:
                    self.close()
                    while self.items and self.items[-1][1] >= indent:
                        self.items.pop()
                continue
            if self.aside is not None:
                # The first text line of a caution aside.
                item = ITEM_RE.match(outside)
                if not GOOD_LABEL_RE.match((item.group(3) if item else outside).strip()):
                    self.findings.append((self.aside, 'warning-form',
                                          'the text of a caution aside starts with "Warning:"'))
                self.aside = None
            match = HEADING_RE.match(outside)
            if match:
                self.close()
                self.items = []
                self.single(number, match.group(1))
                continue
            if outside.lstrip().startswith('|'):
                self.close()
                if not TABLE_RULE_RE.match(outside):
                    for cell in re.split(r'(?<!\\)\|', outside.strip().strip('|')):
                        if cell.strip():
                            self.single(number, cell)
                continue
            match = ITEM_RE.match(outside)
            if match:
                marker_indent = len(match.group(1))
                kind = 'step' if match.group(2)[0].isdigit() else 'text'
                self.start(kind, marker_indent)
                self.item_count += 1
                self.current.item = self.item_count
                self.items.append((kind, marker_indent, self.item_count))
                if LABEL_RE.match(match.group(3).strip()):
                    self.current.warning = True
                if match.group(3).strip():
                    self.current.add(number, match.group(3).strip())
                continue
            self.text_line(number, outside, indent)


def clean(text):
    """Remove the inline markup of one line."""
    text = re.sub(r'!\[([^\]]*)\]\([^)]*\)', r'\1', text)
    text = re.sub(r'\[([^\]]*)\]\([^)]*\)', r'\1', text)
    text = re.sub(r'\[([^\]]*)\]\[[^\]]*\]', r'\1', text)
    text = re.sub(r'\[\^[^\]]+\]', '', text)
    text = re.sub(r'&#?[A-Za-z0-9]+;', ' ', text)
    text = re.sub(r'\*\*|__|~~', '', text)
    text = re.sub(r'(?<![\w\\])[*_]+|[*_]+(?!\w)', '', text)
    text = re.sub(r'\\([\\`*_{}\[\]()#+.!<>|-])', r'\1', text)
    return text


def sentences(block):
    """The sentences of a block: (line number, text)."""
    text, starts = '', []
    for line, part in block.parts:
        part = clean(part)
        if text:
            text += ' '
        starts.append((len(text), line))
        text += part

    def line_of(offset):
        found = starts[0][1]
        for start, line in starts:
            if start <= offset:
                found = line
        return found

    begin = 0
    for match in BOUNDARY_RE.finditer(text):
        if text[begin:match.end()].rstrip().lower().endswith(ABBREVIATIONS):
            continue
        yield line_of(begin), text[begin:match.end()].strip()
        begin = match.end()
    if text[begin:].strip():
        yield line_of(begin), text[begin:].strip()


def word_count(sentence):
    return sum(1 for token in sentence.split() if WORD_RE.search(token))


def example_findings(text):
    """The findings of the blocks of typed output: (line number, rule, message)."""
    findings = []
    fence = None
    before = ''
    for number, raw in enumerate(text.split('\n'), 1):
        match = FENCE_RE.match(raw)
        if fence:
            if match and match.group(1).startswith(fence) and not raw.strip().lstrip('> ').strip(fence[0]):
                fence = None
            continue
        if match:
            fence = match.group(1)
            info = raw[match.end():].strip()
            example = bool(EXAMPLE_TITLE_RE.search(info))
            if info.split(None, 1)[:1] == ['text'] and not example:
                findings.append((number, 'example-form',
                                 'a "text" block is typed output: give it title="Example", or use a capture'))
            elif example and EXAMPLE_SENTENCE not in before:
                findings.append((number, 'example-form',
                                 f'the line before an Example block says "{EXAMPLE_SENTENCE}"'))
            continue
        if raw.strip():
            before = raw
    return findings


def lint_text(text):
    """Return the findings of one page: (line number, rule, message)."""
    parser = Parser()
    parser.parse(text)
    findings = list(parser.findings) + example_findings(text)

    def shown(sentence, words=8):
        """The start of a sentence, with the inline code in it."""
        tokens = sentence.split()
        short = ' '.join(tokens[:words]) + (' ...' if len(tokens) > words else '')
        return re.sub(CODE_OPEN + r'(\d+)' + CODE_CLOSE, lambda match: '`' + parser.codes[int(match.group(1))] + '`', short)

    steps = {}
    for block in parser.blocks:
        for line, part in block.parts:
            label = LABEL_RE.match(part)
            if label and not GOOD_LABEL_RE.match(part):
                findings.append((line, 'warning-form',
                                 f'a warning starts with "Warning:", not with "{label.group(0).strip()}"'))
            later = LATER_LABEL_RE.search(part, 1)
            if later and not (label and later.start() < label.end()):
                findings.append((line, 'warning-form', 'a warning is its own line: put "Warning:" at the start of a line'))
        limit, place = (STEP_WORDS, 'a step') if block.kind == 'step' else (TEXT_WORDS, 'a description')
        for line, sentence in sentences(block):
            count = word_count(sentence)
            if count > limit:
                findings.append((line, 'sentence-length',
                                 f'{count} words in {place} ({limit} at most): "{shown(sentence)}"'))
            if block.kind == 'step' and not block.warning:
                steps.setdefault(block.item, []).append((line, sentence))

    for item in steps.values():
        instructions = 0
        for line, sentence in item:
            first = FIRST_WORD_RE.match(sentence)
            verb_first = bool(first) and first.group(1).lower() in VERBS
            is_result = sentence.lower().startswith(RESULT_STARTS)
            if verb_first and not is_result:
                instructions += 1
            reason = None
            if THEN_RE.search(sentence) and not sentence.lower().startswith(('if ', 'when ')):
                reason = 'two actions in one sentence ("then")'
            else:
                match = AND_VERB_RE.search(sentence) or (verb_first and COMMA_VERB_RE.search(sentence))
                if match:
                    reason = f'two actions in one sentence ("{match.group(0).strip(" ,;")}")'
                elif verb_first and not is_result and instructions > 1:
                    reason = f'instruction {instructions} in one step'
            if reason:
                findings.append((line, 'step-actions', f'{reason}: "{shown(sentence)}"'))
    return sorted(set(findings))


def page_files(paths):
    for given in paths:
        if os.path.isdir(given):
            for folder, dirs, files in os.walk(given):
                dirs.sort()
                for name in sorted(files):
                    if name.endswith(('.md', '.mdx')):
                        yield os.path.join(folder, name)
        elif os.path.isfile(given):
            yield given
        else:
            raise FileNotFoundError(given)


def main(argv=None):
    parser = argparse.ArgumentParser(description='Simplified English lint for the pages.',
                                     epilog='Exit: 0 no finding or report mode, 1 finding in gate mode, 2 usage error.')
    parser.add_argument('--gate', action='store_true', help='a finding gives the exit code 1')
    parser.add_argument('paths', nargs='*', metavar='path', help=f'a page or a directory (default: {PAGES_REL})')
    options = parser.parse_args(argv)

    paths = options.paths or [os.path.relpath(ROOT / PAGES_REL)]
    totals = {'sentence-length': 0, 'warning-form': 0, 'step-actions': 0, 'example-form': 0}
    pages = with_findings = 0
    try:
        for path in page_files(paths):
            pages += 1
            findings = lint_text(Path(path).read_text(encoding='utf-8'))
            with_findings += 1 if findings else 0
            for line, rule, message in findings:
                totals[rule] += 1
                print(f'{path}:{line}: {rule}: {message}')
    except FileNotFoundError as error:
        print(f'lint: error: {error} does not exist', file=sys.stderr)
        return 2
    total = sum(totals.values())
    detail = ', '.join(f'{count} {rule}' for rule, count in totals.items())
    print(f'lint: {total} finding(s) in {with_findings} of {pages} page(s): {detail}. '
          f'Mode: {"gate" if options.gate else "report"}.')
    return 1 if options.gate and total else 0


if __name__ == '__main__':
    sys.exit(main())
