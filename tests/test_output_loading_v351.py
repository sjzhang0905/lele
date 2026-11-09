"""Chunked source decoding and optional-analysis fast paths keep exact records."""
from unittest.mock import patch
import pytest

from lele.output_text import (
    open_output_text, read_output_lines, output_read_session, LoadCancelled,
)


@pytest.mark.parametrize('encoding', ['utf-8', 'utf-8-sig', 'utf-16', 'utf-16-be'])
@pytest.mark.parametrize('ending', ['', '\n', '\n\n'])
def test_chunked_lines_match_stream_reference(tmp_path, encoding, ending):
    # Cross the 1 Mi-character chunk boundary, including non-ASCII and special
    # separators that splitlines() would incorrectly treat as output records.
    text = ('αβ title\v\f\x85\u2028\r\n' + 'x' * 101 + '\r' + '\n') * 9000
    text += 'final record' + ending
    path = tmp_path/'output.log'
    path.write_bytes(text.encode(encoding))
    with open_output_text(path) as stream:
        reference = [line.rstrip('\r\n') for line in stream]
    assert read_output_lines(path) == reference


def test_empty_lines_cache_and_cancel(tmp_path):
    path = tmp_path/'output.log'
    for text in ['', '\n', '\n\n', 'one', 'one\n']:
        path.write_text(text)
        with output_read_session():
            result = read_output_lines(path)
            assert result == text.splitlines()
            assert read_output_lines(path) is result
    path.write_text('record\n' * 400000)
    events=[]
    with pytest.raises(LoadCancelled), output_read_session(
        progress=lambda *args:events.append(args),
        cancelled=lambda:len(events)>1,
    ):
        read_output_lines(path)


@pytest.mark.parametrize('kind,reader', [
    ('gaussian_out','gaussian'), ('orca_out','orca'), ('vasp_out','vasp'),
    ('cp2k_out','cp2k'), ('qe_out','gipaw'), ('nwchem_out','nwchem'),
])
def test_absent_nmr_avoids_property_parser(tmp_path, kind, reader):
    from lele import nmr_input
    path=tmp_path/'long.out'
    path.write_text('numeric MD diagnostics 0.12345\n' * 10000)
    with patch.object(nmr_input,reader,side_effect=AssertionError('unneeded NMR parser')):
        assert nmr_input.read_nmr_results(path,kind)==[]


@pytest.mark.parametrize('kind,fixture', [
    ('gaussian_out','GAUSSIAN'), ('orca_out','ORCA'), ('vasp_out','VASP_LEGACY'),
    ('cp2k_out','CP2K'), ('qe_out','GIPAW'), ('nwchem_out','NWCHEM'),
])
def test_nmr_beyond_chunk_boundary_retains_source_lines(tmp_path, kind, fixture):
    import test_nmr_v350 as samples
    from lele.nmr_input import read_nmr_results
    path=tmp_path/'long.out'
    text=getattr(samples,fixture)
    path.write_text(text)
    expected=read_nmr_results(path,kind)
    path.write_text('MD record\n' * 8191 + text)
    actual=read_nmr_results(path,kind)
    assert len(actual)==len(expected)>0
    for a,b in zip(actual,expected):
        assert a.source_line == b.source_line + 8191
        assert [n.shielding_ppm for n in a.nuclei] == [n.shielding_ppm for n in b.nuclei]
