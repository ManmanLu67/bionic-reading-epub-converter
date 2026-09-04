"""EPUB to Bionic Reading conversion."""

import io
import os
import re
import sys
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile

from lxml import etree

LETTER = r'[a-zA-ZÀ-ÿĀ-žА-яЁёҐґЄєІіЇїЎўẞß\u0370-\u03FF\u1F00-\u1FFF]'
WORD_PATTERN = re.compile(
    LETTER + r"+(?:['\u2019\u2010\u2011-]" + LETTER + r'+)*',
    re.UNICODE,
)

HYPHENS = frozenset(['-', '\u2010', '\u2011'])

SKIP_TAGS = frozenset([
    'script', 'style', 'code', 'pre', 'kbd', 'samp', 'var',
    'math', 'svg', 'title', 'meta', 'link', 'annotation',
    'nav',
])

CONTENT_EXTENSIONS = frozenset(['.xhtml', '.html', '.htm'])

SKIP_PATHS = frozenset([
    'mimetype',
    'META-INF/container.xml',
    'META-INF/encryption.xml',
    'META-INF/manifest.xml',
    'META-INF/metadata.xml',
    'META-INF/rights.xml',
    'META-INF/signatures.xml',
])

BIONIC_CSS = 'b{font-weight:bold;font-style:inherit;}'


def _tag_for(local, host_element):
    ns = etree.QName(host_element).namespace
    if ns:
        return '{%s}%s' % (ns, local)
    return local


def _bionic_element(host, bold_text, rest_text):
    b_elem = etree.Element(_tag_for('b', host))
    b_elem.text = bold_text
    b_elem.tail = rest_text
    return b_elem


def _inject_bionic_style(tree):
    heads = tree.xpath('//*[local-name()="head"]')
    if not heads:
        return
    head = heads[0]
    style = etree.Element(_tag_for('style', head))
    style.set('type', 'text/css')
    style.text = BIONIC_CSS
    head.append(style)


class BionicConverter:
    """Convert EPUB bytes to Bionic Reading format."""

    def __init__(self, prefs=None):
        prefs = prefs or {}
        self.boldness_ratio = prefs.get('boldness_ratio', 50) / 100.0
        self.min_word_length = prefs.get('min_word_length', 1)
        self.skip_short_words = prefs.get('skip_short_words', False)
        self._inserted = False

    def convert(self, epub_data):
        """Return converted EPUB bytes."""
        input_io = io.BytesIO(epub_data)
        output_io = io.BytesIO()

        with ZipFile(input_io, 'r') as zip_in:
            with ZipFile(output_io, 'w', ZIP_DEFLATED) as zip_out:
                for item in zip_in.infolist():
                    content = zip_in.read(item.filename)

                    if self._should_process(item.filename):
                        try:
                            content = self._process_xhtml(content)
                        except RecursionError:
                            raise
                        except Exception as exc:
                            print(
                                'warning: skipped %s: %s' % (item.filename, exc),
                                file=sys.stderr,
                            )

                    if item.filename == 'mimetype':
                        zip_out.writestr(item, content, compress_type=ZIP_STORED)
                    else:
                        zip_out.writestr(item, content)

        return output_io.getvalue()

    def _should_process(self, filename):
        if filename in SKIP_PATHS:
            return False
        if filename.startswith('META-INF/'):
            return False
        if filename.endswith('.opf'):
            return False
        if filename.endswith('.ncx'):
            return False
        _, ext = os.path.splitext(filename.lower())
        return ext in CONTENT_EXTENSIONS

    def _process_xhtml(self, content):
        parser = etree.XMLParser(recover=False, remove_blank_text=False)
        try:
            tree = etree.parse(io.BytesIO(content), parser)
        except etree.XMLSyntaxError:
            return content

        self._inserted = False
        self._process_element(tree.getroot())
        if not self._inserted:
            return content

        _inject_bionic_style(tree)

        encoding = tree.docinfo.encoding or 'UTF-8'
        doctype = tree.docinfo.doctype or None
        kwargs = {
            'encoding': encoding,
            'xml_declaration': True,
            'pretty_print': False,
        }
        if doctype:
            kwargs['doctype'] = doctype
        return etree.tostring(tree, **kwargs)

    def _process_element(self, element):
        if not isinstance(element.tag, str):
            return

        tag = etree.QName(element.tag).localname
        if tag.lower() in SKIP_TAGS:
            return

        children = list(element)
        if element.text:
            self._process_text_node(element, 'text', element)

        for child in children:
            self._process_element(child)
            if child.tail:
                parent = child.getparent()
                if parent is not None:
                    self._process_text_node(child, 'tail', parent)

    def _nodes_from_parts(self, parts, host):
        new_kids = []
        leading = None
        first_text = True
        for part in parts:
            if part[0] == 'text':
                if first_text:
                    leading = part[1]
                    first_text = False
                elif new_kids:
                    new_kids[-1].tail = (new_kids[-1].tail or '') + part[1]
                else:
                    leading = (leading or '') + part[1]
            else:
                new_kids.append(_bionic_element(host, part[1], part[2]))
                first_text = False
                self._inserted = True
        return leading, new_kids

    def _process_text_node(self, element, attr, host):
        text = getattr(element, attr)
        if not text or not text.strip():
            return

        parts = []
        last_end = 0

        for match in WORD_PATTERN.finditer(text):
            if match.start() > last_end:
                parts.append(('text', text[last_end:match.start()]))

            word = match.group(0)
            bold_part, rest_part = self._split_word(word)
            if bold_part:
                parts.append(('bold', bold_part, rest_part))
            else:
                parts.append(('text', word))

            last_end = match.end()

        if last_end < len(text):
            parts.append(('text', text[last_end:]))

        if not any(p[0] == 'bold' for p in parts):
            return

        leading, new_kids = self._nodes_from_parts(parts, host)

        if attr == 'text':
            element.text = leading
            if new_kids:
                element[:] = new_kids + list(element)
        else:
            parent = element.getparent()
            if parent is None:
                return
            element.tail = leading
            if new_kids:
                kids = list(parent)
                idx = kids.index(element)
                parent[:] = kids[:idx + 1] + new_kids + kids[idx + 1:]

    def _split_word(self, word):
        length = len(word)

        if self.skip_short_words and length <= 2:
            return None, None

        if length < self.min_word_length:
            return None, None

        if length == 1:
            return word, ''
        if length <= 3:
            return word[0], word[1:]

        bold_len = max(1, round(length * self.boldness_ratio))
        bold_len = min(bold_len, length - 1)
        for i, char in enumerate(word):
            if char in HYPHENS and i > 0:
                bold_len = min(bold_len, i)
                break
        return word[:bold_len], word[bold_len:]
