"""Natural filename ordering and responsive recursive folder imports."""
import os
import threading
from pathlib import Path
from time import sleep
from unittest.mock import patch

import pytest
from PySide6.QtWidgets import QApplication

from lele.import_paths import ImportBatch, natural_filename_key, prepare_import_batch, sort_import_paths
from lele.output_text import LoadCancelled
from test_drop_loading_v357 import window, wait_for, xyz, drop


def test_natural_sort_is_numeric_case_insensitive_and_deterministic():
    names = ['frame10.xyz', 'frame02.xyz', 'frame2.xyz', 'Frame1.xyz', 'frame1.xyz', 'frame11.xyz']
    expected = ['Frame1.xyz', 'frame1.xyz', 'frame2.xyz', 'frame02.xyz', 'frame10.xyz', 'frame11.xyz']
    assert sorted(names, key=natural_filename_key) == expected
    assert sorted(reversed(names), key=natural_filename_key) == expected
    assert sorted([Path('run10/a2.xyz'), Path('run2/a2.xyz')], key=natural_filename_key) == [
        Path('run2/a2.xyz'), Path('run10/a2.xyz')]


def test_import_request_itself_never_touches_the_filesystem(tmp_path):
    with patch.object(Path, 'stat', side_effect=AssertionError('Filesystem access in request')):
        batch = ImportBatch([tmp_path / 'future.xyz', tmp_path])
    assert isinstance(batch.paths, tuple)


def test_expansion_recurses_deduplicates_and_globally_sorts_supported_files(tmp_path):
    folder = tmp_path / 'run10';folder.mkdir()
    sub = folder / 'nested';sub.mkdir()
    one = xyz(folder, 'frame1.xyz');ten = xyz(folder, 'frame10.xyz');two = xyz(sub, 'frame2.xyz')
    (folder / 'notes.log').write_text('ordinary application log, not quantum chemistry\n')
    (sub / 'notes.txt').write_text('not a structure\n')
    (folder / 'program.com').write_bytes(b'MZ\0\0executable')
    (folder / 'session.lele').write_bytes(b'project is explicitly opened only')
    (sub / 'photo.png').write_bytes(b'not scientific data')
    orca = sub / 'scan3.log';orca.write_text('ORCA VERSION 6.0\nORCA TERMINATED NORMALLY\n')
    cp2k = folder / 'calc.restart.bak-1';cp2k.write_text('&GLOBAL\n PROJECT test\n&END GLOBAL\n')
    (folder / 'unknown.dat').write_text('ORCA VERSION 6.0\n')
    result = prepare_import_batch([ten, folder, sub, one, one])
    assert [p.name for p in result.paths] == ['calc.restart.bak-1', 'frame1.xyz', 'frame2.xyz', 'frame10.xyz', 'scan3.log']
    assert len(result.paths) == len(set(result.paths))
    assert two.resolve() in result.paths and not result.issues
    assert result.skipped == 6
    # Explicitly chosen files keep normal loader errors/project behavior.
    project = folder / 'session.lele'
    explicit = prepare_import_batch([project, folder / 'unknown.dat'])
    assert explicit.paths == tuple(sorted((project.resolve(), (folder / 'unknown.dat').resolve()), key=natural_filename_key))


def test_directory_symlink_loops_are_not_followed_and_file_aliases_dedupe(tmp_path):
    folder = tmp_path / 'tree';folder.mkdir()
    real = xyz(folder, 'frame2.xyz')
    try:
        (folder / 'loop').symlink_to(folder, target_is_directory=True)
        (folder / 'alias.xyz').symlink_to(real)
    except (OSError, NotImplementedError):
        pytest.skip('Symbolic links are unavailable on this filesystem')
    result = prepare_import_batch([folder, folder / 'loop', real])
    assert result.paths == (real.resolve(),)
    assert not result.issues


def test_unrelated_large_log_has_only_bounded_detection_reads(tmp_path):
    path = tmp_path / 'application.log'
    with path.open('wb') as handle:
        handle.write(b'not a scientific calculation\n')
        handle.truncate(128 * 1024 * 1024)
    reads = []
    original = Path.open
    class Tracked:
        def __init__(self, stream):self.stream = stream
        def __enter__(self):self.stream.__enter__();return self
        def __exit__(self, *args):return self.stream.__exit__(*args)
        def read(self, size=-1):
            reads.append(size)
            assert 0 <= size <= 768000, 'Folder discovery must not read a whole generic log'
            return self.stream.read(size)
        def __getattr__(self, name):return getattr(self.stream, name)
    def opening(target, *args, **kwargs):
        stream = original(target, *args, **kwargs)
        return Tracked(stream) if target == path else stream
    with patch.object(Path, 'open', opening):
        result = prepare_import_batch([tmp_path])
    assert not result.paths and result.skipped == 1
    assert reads and sum(reads) < 2 * 1024 * 1024


def test_cancellation_never_returns_a_partial_batch(tmp_path):
    for i in range(20):xyz(tmp_path, f'frame{i}.xyz')
    calls = []
    def cancelled():
        calls.append(True)
        return len(calls) > 8
    with pytest.raises(LoadCancelled):
        prepare_import_batch([tmp_path], cancelled=cancelled)


def test_background_batch_and_later_file_keep_queue_and_attachment_order(window, tmp_path):
    ten = xyz(tmp_path, 'frame10.xyz');two = xyz(tmp_path, 'frame2.xyz');one = xyz(tmp_path, 'frame1.xyz')
    later = xyz(tmp_path, 'later.xyz')
    entered = threading.Event();release = threading.Event();threads = [];attached = []
    original = prepare_import_batch
    def gated(paths, **kwargs):
        threads.append(threading.get_ident());entered.set()
        while not release.is_set():
            if kwargs['cancelled']():raise LoadCancelled()
            sleep(.001)
        return original(paths, **kwargs)
    with patch('lele.import_paths.prepare_import_batch', side_effect=gated), \
         patch.object(window, '_attach_loaded_document', side_effect=lambda doc: attached.append(doc.path)):
        window.open_path(ImportBatch((ten, two, one, two)))
        wait_for(entered.is_set)
        window.open_path(later)
        assert not attached
        release.set()
        wait_for(lambda: len(attached) == 4)
        wait_for(lambda: not QApplication.instance()._lele_file_loaders)
    assert threads == [threads[0]] and threads[0] != threading.get_ident()
    assert attached == [one.resolve(), two.resolve(), ten.resolve(), later.resolve()]


def test_folder_drop_returns_before_discovery_and_loads_each_file_once(window, tmp_path):
    one = xyz(tmp_path, 'file1.xyz');ten = xyz(tmp_path, 'file10.xyz');two = xyz(tmp_path, 'file2.xyz')
    attached = []
    mime, event = drop([tmp_path, ten])
    with patch.object(window, '_attach_loaded_document', side_effect=lambda doc: attached.append(doc.path)):
        with patch.object(Path, 'stat', side_effect=AssertionError('Native drop accessed filesystem')):
            window.dropEvent(event)
        assert event.isAccepted() and not attached
        mime.clear()
        wait_for(lambda: len(attached) == 3)
    assert attached == [one.resolve(), two.resolve(), ten.resolve()]


def test_close_during_discovery_cancels_without_loading(window, tmp_path):
    path = xyz(tmp_path)
    entered = threading.Event();attached = []
    def gated(paths, *, cancelled, progress):
        entered.set()
        while not cancelled():sleep(.001)
        raise LoadCancelled()
    with patch('lele.import_paths.prepare_import_batch', side_effect=gated), \
         patch.object(window, '_attach_loaded_document', side_effect=attached.append):
        window.open_path(ImportBatch((path,)))
        wait_for(entered.is_set)
        window._closing = True;window._cancel_file_imports()
        wait_for(lambda: window._file_batch_active is None)
        wait_for(lambda: not QApplication.instance()._lele_file_loaders)
    assert not attached and not window._file_load_queue


def test_native_filename_comparator_is_used_and_equal_names_get_path_ties(monkeypatch):
    import lele.import_paths as module
    compared = []
    # Simulate the platform comparator making two distinct names logically
    # equal, as happens with case or numeric-padding variants in Explorer.
    def native(left, right):
        compared.append((left, right))
        rank = {'A2.xyz': 0, 'a02.xyz': 0, 'a10.xyz': 1}
        return (rank[left] > rank[right]) - (rank[left] < rank[right])
    monkeypatch.setattr(module, '_windows_logical_compare', lambda: native)
    paths = [Path('run10/A2.xyz'), Path('run2/a02.xyz'), Path('run1/a10.xyz')]
    assert sort_import_paths(paths) == (paths[1], paths[0], paths[2])
    assert compared


@pytest.mark.parametrize('name', ['water.molden.input', 'WATER.MOLDEN.INPUT', 'water.input'])
def test_folder_import_detects_molden_input_compound_suffix_from_real_contents(tmp_path, name):
    from lele.formats import load_document
    path = tmp_path / name
    path.write_text('[Molden Format]\n[Atoms] Angs\nO 1 8 0 0 0\nH 2 1 .96 0 0\nH 3 1 -.24 .93 0\n')
    (tmp_path / 'unrelated.input').write_text('keyboard input settings\n')
    result = prepare_import_batch([tmp_path])
    assert result.paths == (path.resolve(),)
    assert result.skipped == 1
    document = load_document(result.paths[0])
    assert document.frames[0].symbols == ['O', 'H', 'H']
    assert document.format_name == 'Molden'


@pytest.mark.parametrize('name', ['job.finalensemble.xyz', 'job_MEP_trj.xyz', 'job_MEP_ALL_trj.xyz',
                                  'job.NEB.log', 'job.interp', 'job.interp.final', 'cp2k.restart.bak-2'])
def test_known_supported_compound_names_reach_folder_import(tmp_path, name):
    from lele.import_paths import is_folder_import_candidate
    path = tmp_path / name
    path.write_text('&GLOBAL\n PROJECT test\n&END GLOBAL\n' if '.restart.' in name else '')
    assert is_folder_import_candidate(path)
