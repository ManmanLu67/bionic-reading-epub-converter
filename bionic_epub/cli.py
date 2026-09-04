"""Command-line entry for EPUB Bionic conversion."""

import argparse
import sys
from pathlib import Path
from zipfile import BadZipFile

from bionic_epub.converter import BionicConverter


def default_output_path(input_path):
    return input_path.with_name('bionic_' + input_path.name)


def build_parser():
    parser = argparse.ArgumentParser(
        description='Convert an EPUB file to Bionic Reading format.',
    )
    parser.add_argument('input', help='Input EPUB file path')
    parser.add_argument(
        'output',
        nargs='?',
        help='Output EPUB path (default: bionic_<input> next to the source)',
    )
    parser.add_argument(
        '--ratio',
        type=int,
        default=50,
        help='Percent of each word to bold (25-75, default 50)',
    )
    parser.add_argument(
        '--min-word-length',
        type=int,
        default=1,
        help='Do not process words shorter than this (default 1)',
    )
    parser.add_argument(
        '--skip-short-words',
        action='store_true',
        help='Skip 1-2 letter words entirely',
    )
    parser.add_argument(
        '--force',
        action='store_true',
        help='Overwrite the output file if it already exists',
    )
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)

    if not 25 <= args.ratio <= 75:
        parser.error('--ratio must be between 25 and 75')

    if args.min_word_length < 1:
        parser.error('--min-word-length must be at least 1')

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Error: Input file '{input_path}' does not exist.", file=sys.stderr)
        return 1

    output_path = Path(args.output) if args.output else default_output_path(input_path)
    if output_path.exists() and not args.force:
        print(
            f"Error: Output file '{output_path}' already exists. Use --force to overwrite.",
            file=sys.stderr,
        )
        return 1

    try:
        epub_data = input_path.read_bytes()
    except OSError as exc:
        print(f'Error: Could not read input: {exc}', file=sys.stderr)
        return 1

    converter = BionicConverter({
        'boldness_ratio': args.ratio,
        'min_word_length': args.min_word_length,
        'skip_short_words': args.skip_short_words,
    })

    try:
        converted = converter.convert(epub_data)
    except BadZipFile:
        print(f"Error: '{input_path}' is not a valid EPUB/ZIP file.", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f'Error occurred during processing: {exc}', file=sys.stderr)
        return 1

    try:
        output_path.write_bytes(converted)
    except OSError as exc:
        print(f'Error: Could not write output: {exc}', file=sys.stderr)
        return 1

    print(f"Conversion complete. Output saved to '{output_path}'")
    return 0


if __name__ == '__main__':
    sys.exit(main())
