"""Decode printed output, including Windows PowerShell UTF-16 redirection."""
from pathlib import Path


def output_encoding(data):
    if data.startswith(b'\xff\xfe'):
        return 'utf-16-le'
    if data.startswith(b'\xfe\xff'):
        return 'utf-16-be'
    sample = data[:4096]
    if sample.count(b'\0') > len(sample) // 5:
        return 'utf-16-le' if sample[1::2].count(0) >= sample[::2].count(0) else 'utf-16-be'
    return 'utf-8-sig'


def decode_output(data):
    return data.decode(output_encoding(data), errors='replace').lstrip('\ufeff')


def read_output_lines(path):
    return decode_output(Path(path).read_bytes()).splitlines()
