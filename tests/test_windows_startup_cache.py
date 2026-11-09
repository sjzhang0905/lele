"""The Windows dependency cache must invalidate whenever an installation changes."""
import importlib.util
from pathlib import Path
import sys

import pytest


@pytest.fixture
def bootstrap(tmp_path, monkeypatch):
    path = Path(__file__).resolve().parents[1] / 'windows_bootstrap.py'
    spec = importlib.util.spec_from_file_location('windows_bootstrap_under_test', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    root = tmp_path / 'LELE'
    venv = root / '.venv'
    site = venv / 'Lib' / 'site-packages'
    site.mkdir(parents=True)
    python = venv / 'Scripts' / 'python.exe'
    python.parent.mkdir()
    python.write_bytes(b'python')
    (venv / 'pyvenv.cfg').write_text('version = 3.12')
    (root / 'requirements.txt').write_text('numpy>=1.26,<3\n')
    for name in module.REQUIRED_PACKAGES:
        package = site / name
        package.mkdir()
        (package / '__init__.py').write_text('# test package')
        metadata = site / (name + '-1.0.dist-info')
        metadata.mkdir()
        (metadata / 'METADATA').write_text('Version: 1.0')
        (metadata / 'RECORD').write_text(name + '/__init__.py')
    for key, value in dict(ROOT=root, VENV=venv, WIN_PY=python,
                           VERIFICATION_CACHE=venv / '.lele_dependencies_verified.json').items():
        monkeypatch.setattr(module, key, value)
    monkeypatch.delenv('LELE_VERIFY_DEPENDENCIES', raising=False)
    return module


def test_verification_cache_and_requirement_changes(bootstrap):
    assert not bootstrap.dependencies_verified()
    bootstrap.save_dependency_verification()
    assert bootstrap.dependencies_verified()
    (bootstrap.ROOT / 'requirements.txt').write_text('numpy>=2,<3\n')
    assert not bootstrap.dependencies_verified()


@pytest.mark.parametrize('relative', [
    'numpy/__init__.py', 'numpy-1.0.dist-info/METADATA',
    'numpy-1.0.dist-info/RECORD', 'PIL/_imaging.pyd',
])
def test_changed_package_or_metadata_invalidates_cache(bootstrap, relative):
    target = bootstrap.VENV / 'Lib' / 'site-packages' / relative
    if not target.exists():target.write_bytes(b'old native module')
    bootstrap.save_dependency_verification()
    assert bootstrap.dependencies_verified()
    target.write_bytes(b'changed installation')
    assert not bootstrap.dependencies_verified()


def test_missing_module_and_force_verify(bootstrap, monkeypatch):
    bootstrap.save_dependency_verification()
    monkeypatch.setenv('LELE_VERIFY_DEPENDENCIES', '1')
    assert not bootstrap.dependencies_verified()
    monkeypatch.delenv('LELE_VERIFY_DEPENDENCIES')
    assert bootstrap.dependencies_verified()
    (bootstrap.VENV / 'Lib' / 'site-packages' / 'numpy' / '__init__.py').unlink()
    assert not bootstrap.dependencies_verified()


def test_cached_launcher_skips_import_probe_and_rechecks_after_failure(bootstrap, monkeypatch):
    bootstrap.save_dependency_verification()
    monkeypatch.setattr(bootstrap, 'describe_python', lambda _: (sys.version_info.major, sys.version_info.minor, 64))
    monkeypatch.setattr(bootstrap.subprocess, 'run', lambda *a, **kw: pytest.fail('cached launch imported dependencies again'))
    launches = []
    monkeypatch.setattr(bootstrap, 'run', lambda args: launches.append(args) or 8)
    assert bootstrap.main() == 8
    assert len(launches) == 1 and launches[0][1:3] == ['-m', 'lele']
    assert not bootstrap.VERIFICATION_CACHE.exists()


def test_corrupt_cache_is_reverified(bootstrap):
    bootstrap.VERIFICATION_CACHE.write_text('{bad cache')
    assert not bootstrap.dependencies_verified()


@pytest.mark.parametrize('remove', [False, True])
def test_nested_native_runtime_is_checked(bootstrap, remove):
    site = bootstrap.VENV / 'Lib' / 'site-packages'
    native = site / 'numpy' / '_core' / '_multiarray_umath.pyd'
    native.parent.mkdir()
    native.write_bytes(b'original native file')
    (site / 'numpy-1.0.dist-info' / 'RECORD').write_text('numpy/_core/_multiarray_umath.pyd,,\n')
    bootstrap.save_dependency_verification()
    assert bootstrap.dependencies_verified()
    if remove:native.unlink()
    else:native.write_bytes(b'changed native file contents')
    assert not bootstrap.dependencies_verified()
