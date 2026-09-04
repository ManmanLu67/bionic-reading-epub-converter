import io
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
