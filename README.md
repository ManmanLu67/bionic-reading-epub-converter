# Bionic EPUB Converter

CLI that converts an EPUB to [Bionic Reading](https://bionic-reading.com/) format: the start of each word is wrapped in `<b>` so the eye can pick up word shapes faster.

Fork of [dobrosketchkun/bionic-reading-epub-converter](https://github.com/dobrosketchkun/bionic-reading-epub-converter). Original authors are credited; this tree is a standalone command-line tool.

## Install

Python 3.9+ and `lxml`:

```
pip install -e .
```

For tests:

```
pip install -e ".[dev]"
```

## Usage

```
bionic-epub INPUT.epub [OUTPUT.epub]
```

If `OUTPUT` is omitted, the file is written next to the input as `bionic_<filename>.epub`.

```
bionic-epub book.epub
bionic-epub book.epub book-bionic.epub --ratio 40
bionic-epub book.epub --force
```

| Option | Default | Meaning |
|--------|---------|---------|
| `--ratio` | 50 | Percent of each word to bold (25–75). Shorter words still bold only the first letter. The last letter is never bolded. |
| `--min-word-length` | 1 | Ignore words shorter than this. |
| `--skip-short-words` | off | Leave 1–2 letter words unchanged. |
| `--force` | off | Overwrite an existing output file. |

Without `--force`, an existing output path is an error.

## Limits

- EPUB only (not MOBI, AZW3, or PDF).
- Latin, Cyrillic, and Greek alphabets. Logographic scripts (Chinese, Japanese kanji, Korean hanja) are not supported.
- Chapter XHTML/HTML/XML inside the EPUB is rewritten; images, CSS, fonts, and package metadata are copied as-is.

## Develop

```
pytest
```
