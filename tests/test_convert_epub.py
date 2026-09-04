import io
import re
from zipfile import ZIP_STORED, ZipFile, ZipInfo

from lxml import etree

from bionic_epub.converter import BionicConverter


XHTML = b'''<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml">
<body><p>Hello world</p></body>
</html>
'''

CSS = b'p { color: red; }\n'

CONVERTER = BionicConverter({
    'boldness_ratio': 50,
    'min_word_length': 1,
    'skip_short_words': False,
})


def make_epub(chapter=None, extra_files=None):
    buf = io.BytesIO()
    with ZipFile(buf, 'w') as zf:
        info = ZipInfo('mimetype')
        zf.writestr(info, b'application/epub+zip', compress_type=ZIP_STORED)
        zf.writestr('OEBPS/chapter.xhtml', chapter if chapter is not None else XHTML)
        zf.writestr('OEBPS/style.css', CSS)
        if extra_files:
            for name, data in extra_files.items():
                zf.writestr(name, data)
    return buf.getvalue()


def read_entry(epub_bytes, name):
    with ZipFile(io.BytesIO(epub_bytes), 'r') as zf:
        return zf.read(name)


def visible_text(xml_bytes):
    tree = etree.parse(io.BytesIO(xml_bytes))
    return ''.join(tree.xpath('//text()'))


def test_convert_inserts_b_tags_in_xhtml():
    out = CONVERTER.convert(make_epub())
    xhtml = read_entry(out, 'OEBPS/chapter.xhtml').decode('utf-8')
    assert '<b>' in xhtml or '<b ' in xhtml or ':b>' in xhtml
    assert 'He' in xhtml and 'llo' in xhtml
    assert 'wo' in xhtml and 'rld' in xhtml


def test_mimetype_stays_uncompressed():
    out = CONVERTER.convert(make_epub())
    with ZipFile(io.BytesIO(out), 'r') as zf:
        info = zf.getinfo('mimetype')
        assert info.compress_type == ZIP_STORED
        assert zf.read('mimetype') == b'application/epub+zip'


def test_css_bytes_unchanged():
    out = CONVERTER.convert(make_epub())
    assert read_entry(out, 'OEBPS/style.css') == CSS


def test_visible_text_unchanged_with_unicode():
    chapter = (
        b'<?xml version="1.0" encoding="utf-8"?>'
        b'<html xmlns="http://www.w3.org/1999/xhtml">'
        b'<body><p>Hello \xe2\x80\x94 caf\xc3\xa9</p></body></html>'
    )
    out = CONVERTER.convert(make_epub(chapter=chapter))
    converted = read_entry(out, 'OEBPS/chapter.xhtml')
    assert visible_text(converted) == visible_text(chapter)


def test_doctype_preserved():
    chapter = (
        b'<?xml version="1.0" encoding="utf-8"?>\n'
        b'<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.1//EN" '
        b'"http://www.w3.org/TR/xhtml11/DTD/xhtml11.dtd">\n'
        b'<html xmlns="http://www.w3.org/1999/xhtml">'
        b'<body><p>Hello</p></body></html>'
    )
    out = CONVERTER.convert(make_epub(chapter=chapter))
    converted = read_entry(out, 'OEBPS/chapter.xhtml')
    assert b'-//W3C//DTD XHTML 1.1//EN' in converted
    assert b'xhtml11.dtd' in converted


def test_malformed_xml_kept_as_bytes():
    chapter = b'<<<<'
    out = CONVERTER.convert(make_epub(chapter=chapter))
    assert read_entry(out, 'OEBPS/chapter.xhtml') == chapter


def test_prefixed_namespace_b_tags_do_not_reset_xmlns():
    chapter = (
        b'<?xml version="1.0" encoding="utf-8"?>'
        b'<x:html xmlns:x="http://www.w3.org/1999/xhtml">'
        b'<x:body><x:p>Hello</x:p></x:body></x:html>'
    )
    out = CONVERTER.convert(make_epub(chapter=chapter))
    converted = read_entry(out, 'OEBPS/chapter.xhtml')
    assert b'xmlns=""' not in converted
    tree = etree.parse(io.BytesIO(converted))
    b_elems = tree.xpath('//*[local-name()="b"]')
    assert b_elems
    xhtml_ns = 'http://www.w3.org/1999/xhtml'
    for elem in b_elems:
        assert etree.QName(elem).namespace == xhtml_ns


def test_unchanged_when_no_words_to_bold():
    chapter = (
        b'<?xml version="1.0" encoding="utf-8"?>'
        b'<html xmlns="http://www.w3.org/1999/xhtml">'
        b'<body><p>123 456</p></body></html>'
    )
    out = CONVERTER.convert(make_epub(chapter=chapter))
    assert read_entry(out, 'OEBPS/chapter.xhtml') == chapter


def test_xml_sidecar_not_processed():
    xml_payload = b'<?xml version="1.0"?><root><p>Hello world</p></root>'
    out = CONVERTER.convert(make_epub(extra_files={'OEBPS/foo.xml': xml_payload}))
    assert read_entry(out, 'OEBPS/foo.xml') == xml_payload


def _chapter_tree(chapter):
    out = CONVERTER.convert(make_epub(chapter=chapter))
    return etree.parse(io.BytesIO(read_entry(out, 'OEBPS/chapter.xhtml')))


def test_plain_words_use_b_without_style():
    tree = _chapter_tree(
        b'<?xml version="1.0" encoding="utf-8"?>'
        b'<html xmlns="http://www.w3.org/1999/xhtml">'
        b'<body><p>Hello</p></body></html>'
    )
    b_elems = tree.xpath('//*[local-name()="b"]')
    assert b_elems
    assert b_elems[0].text == 'He'
    assert b_elems[0].tail == 'llo'
    assert b_elems[0].xpath('./*') == []
    assert not b_elems[0].get('style')


def test_formatted_wrappers_keep_plain_b_inside():
    tree = _chapter_tree(
        b'<?xml version="1.0" encoding="utf-8"?>'
        b'<html xmlns="http://www.w3.org/1999/xhtml">'
        b'<body><p>'
        b'<i>Italic</i> '
        b'<em>Emphasis</em> '
        b'<span style="font-style:italic">Styled</span> '
        b'<u>Under</u> '
        b'<sub>two</sub>'
        b'</p></body></html>'
    )
    ns = {'h': 'http://www.w3.org/1999/xhtml'}
    cases = [
        (tree.xpath('//h:i', namespaces=ns)[0], 'Italic'),
        (tree.xpath('//h:em', namespaces=ns)[0], 'Emphasis'),
        (tree.xpath('//h:span[@style="font-style:italic"]', namespaces=ns)[0], 'Styled'),
        (tree.xpath('//h:u', namespaces=ns)[0], 'Under'),
        (tree.xpath('//h:sub', namespaces=ns)[0], 'two'),
    ]
    for wrapper, text in cases:
        assert ''.join(wrapper.itertext()) == text
        b_elems = wrapper.xpath('./*[local-name()="b"]')
        assert b_elems
        assert b_elems[0].text
        assert not b_elems[0].get('style')


def test_spaces_between_words_preserved():
    chapter = (
        b'<?xml version="1.0" encoding="utf-8"?>'
        b'<html xmlns="http://www.w3.org/1999/xhtml">'
        b'<body><p>Hello world</p>'
        b'<p><i>hello world</i></p></body></html>'
    )
    out = CONVERTER.convert(make_epub(chapter=chapter))
    converted = read_entry(out, 'OEBPS/chapter.xhtml')
    assert visible_text(converted) == visible_text(chapter)
    assert 'Hello world' in visible_text(converted)
    assert 'hello world' in visible_text(converted)


def test_many_words_prepend_keeps_existing_sibling():
    words = ' '.join(['word'] * 200)
    chapter = (
        b'<?xml version="1.0" encoding="utf-8"?>'
        b'<html xmlns="http://www.w3.org/1999/xhtml">'
        b'<body><p>' + words.encode('utf-8') + b' <span>x</span> tail</p></body></html>'
    )
    out = CONVERTER.convert(make_epub(chapter=chapter))
    converted = read_entry(out, 'OEBPS/chapter.xhtml')
    assert visible_text(converted) == visible_text(chapter)
    tree = etree.parse(io.BytesIO(converted))
    ns = {'h': 'http://www.w3.org/1999/xhtml'}
    spans = tree.xpath('//h:span', namespaces=ns)
    assert len(spans) == 1
    assert ''.join(spans[0].itertext()) == 'x'


def test_prefixed_namespace_italic_keeps_plain_b():
    chapter = (
        b'<?xml version="1.0" encoding="utf-8"?>'
        b'<x:html xmlns:x="http://www.w3.org/1999/xhtml">'
        b'<x:body><x:p><x:i>Hello</x:i></x:p></x:body></x:html>'
    )
    out = CONVERTER.convert(make_epub(chapter=chapter))
    converted = read_entry(out, 'OEBPS/chapter.xhtml')
    assert b'xmlns=""' not in converted
    tree = etree.parse(io.BytesIO(converted))
    xhtml_ns = 'http://www.w3.org/1999/xhtml'
    b_elems = tree.xpath('//*[local-name()="b"]')
    assert b_elems
    assert b_elems[0].text == 'He'
    assert b_elems[0].xpath('./*[local-name()="i"]') == []
    assert not b_elems[0].get('style')
    for elem in b_elems:
        assert etree.QName(elem).namespace == xhtml_ns


def test_apostrophe_words_get_one_b():
    chapter = (
        b'<?xml version="1.0" encoding="utf-8"?>'
        b'<html xmlns="http://www.w3.org/1999/xhtml">'
        b"<body><p>America\xe2\x80\x99s don't</p></body></html>"
    )
    out = CONVERTER.convert(make_epub(chapter=chapter))
    converted = read_entry(out, 'OEBPS/chapter.xhtml')
    assert visible_text(converted) == visible_text(chapter)
    tree = etree.parse(io.BytesIO(converted))
    b_elems = tree.xpath('//*[local-name()="b"]')
    assert len(b_elems) == 2
    xhtml = converted.decode('utf-8')
    assert not re.search(r"['\u2019]<b", xhtml)


def test_hyphenated_word_gets_one_b_before_hyphen():
    chapter = (
        b'<?xml version="1.0" encoding="utf-8"?>'
        b'<html xmlns="http://www.w3.org/1999/xhtml">'
        b'<body><p>still-astonished</p></body></html>'
    )
    tree = _chapter_tree(chapter)
    b_elems = tree.xpath('//*[local-name()="b"]')
    assert len(b_elems) == 1
    assert b_elems[0].text == 'still'
    assert (b_elems[0].tail or '').startswith('-')


def test_injects_inherit_css_once_when_head_present():
    chapter = (
        b'<?xml version="1.0" encoding="utf-8"?>'
        b'<html xmlns="http://www.w3.org/1999/xhtml">'
        b'<head><title>t</title></head>'
        b'<body><p>Hello</p></body></html>'
    )
    xhtml = read_entry(
        CONVERTER.convert(make_epub(chapter=chapter)),
        'OEBPS/chapter.xhtml',
    ).decode('utf-8')
    assert xhtml.count('font-style:inherit') == 1
    assert 'b{font-weight:bold;font-style:inherit;}' in xhtml.replace(' ', '')


def test_converts_without_head():
    tree = _chapter_tree(
        b'<?xml version="1.0" encoding="utf-8"?>'
        b'<html xmlns="http://www.w3.org/1999/xhtml">'
        b'<body><p>Hello</p></body></html>'
    )
    b_elems = tree.xpath('//*[local-name()="b"]')
    assert b_elems
    assert b_elems[0].text == 'He'
