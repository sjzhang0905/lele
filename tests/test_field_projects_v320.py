"""Portable multichannel field snapshots, including pre-field project defaults."""
from pathlib import Path
import json
import zipfile
import numpy as np
from lele.core import Document, Frame, Volume
from lele.project_file import save_project, load_project
from lele.render_options import RenderOptions


def state_for(document):
    return dict(documents=[dict(document=document, options=RenderOptions(), frame_index=0)],
                current_document=0, selection=[])


def field_document():
    frame = Frame(['H'], [[0., 0., 0.]])
    basis = np.array([[.3, 0, 0], [.1, .4, 0], [0, .1, .5]])
    total = Volume(np.arange(24).reshape(2, 3, 4), [.1, .2, .3], basis,
                   label='Total charge density', unit='e/Å³', periodic=True)
    spin = Volume(-np.arange(24).reshape(2, 3, 4), [.1, .2, .3], basis,
                  label='Magnetization', unit='e/Å³', periodic=True)
    return Document(Path('missing.CHGCAR'), 'VASP CHGCAR', [frame],
                    volume=spin, volumes=[total, spin])


def test_field_project_retains_active_channel_identity_and_metadata(tmp_path):
    doc = field_document()
    path = tmp_path/'fields.lele'
    save_project(path, state_for(doc))
    restored = load_project(path)['documents'][0]['document']
    assert restored.volume is restored.volumes[1]
    assert len(restored.volumes) == 2
    for a, b in zip(doc.volumes, restored.volumes):
        assert (a.label, a.unit, a.periodic) == (b.label, b.unit, b.periodic)
        np.testing.assert_array_equal(a.data, b.data)
        np.testing.assert_array_equal(a.origin, b.origin)
        np.testing.assert_array_equal(a.voxel_vectors, b.voxel_vectors)
    save_project(tmp_path/'resaved.lele', state_for(restored))


def test_pre_v320_project_gets_compatible_field_defaults(tmp_path):
    """Remove new fields from a real project to simulate a v3.1 archive."""
    doc = field_document()
    path = tmp_path/'new.lele'
    save_project(path, state_for(doc))
    with zipfile.ZipFile(path) as source:
        payload = {name: source.read(name) for name in source.namelist()}
    manifest = json.loads(payload['manifest.json'])
    for node in manifest['nodes']:
        if node.get('type') == 'lele.core:Document':
            for name in ('volumes', 'wavefunction'):
                node['attributes'].pop(name, None)
        if node.get('type') == 'lele.core:Volume':
            for name in ('label', 'unit', 'periodic', 'reference_origin', 'reference_voxel_vectors'):
                node['attributes'].pop(name, None)
    payload['manifest.json'] = json.dumps(manifest).encode()
    old = tmp_path/'v310.lele'
    with zipfile.ZipFile(old, 'w') as archive:
        for name, data in payload.items():archive.writestr(name, data)
    restored = load_project(old)['documents'][0]['document']
    assert restored.volumes == [restored.volume]
    assert restored.wavefunction is None
    assert restored.volume.label == '' and restored.volume.unit == ''
    assert restored.volume.periodic is False
    np.testing.assert_array_equal(restored.volume.data, doc.volume.data)
    save_project(tmp_path/'upgraded.lele', state_for(restored))


def test_gaussian_wavefunction_snapshot_retains_evaluation_without_source(tmp_path):
    from lele.gaussian_basis import GaussianShell, GaussianWavefunction
    shell = GaussianShell(np.zeros(3), 0, np.array([.5, 1.]), np.array([.3, .7]))
    wf = GaussianWavefunction(np.zeros((1, 3)), [shell],
        {'Alpha':np.array([[1.]]), 'Beta':np.array([[-.8]])},
        [('Alpha', 1, 1., -10.), ('Beta', 1, 1., -9.)], 'FCHK',
        metadata={'basis':'synthetic S contraction'})
    points = np.array([[0., 0., 0.], [1., 2., 3.]])
    expected = wf.evaluate_points('Alpha', 1, points)
    doc = Document(tmp_path/'not-present.fchk', 'Gaussian FCHK',
                   [Frame(['H'], [[0., 0., 0.]])], wavefunction=wf)
    path = tmp_path/'orbitals.lele'
    save_project(path, state_for(doc))
    restored = load_project(path)['documents'][0]['document']
    assert restored.wavefunction is not wf
    assert restored.wavefunction.source_format == 'FCHK'
    assert restored.wavefunction.metadata == wf.metadata
    assert restored.wavefunction.orbitals == wf.orbitals
    np.testing.assert_array_equal(restored.wavefunction.coefficients['Beta'], wf.coefficients['Beta'])
    np.testing.assert_allclose(restored.wavefunction.evaluate_points('Alpha', 1, points), expected)
    generated = restored.wavefunction.evaluate_orbital('Beta', 1, spacing=.5, padding=1.)
    assert generated.data.shape == (5, 5, 5)
    assert generated.data.max() < 0
    save_project(tmp_path/'resaved-orbitals.lele', state_for(restored))


def test_detached_fields_stay_detached_on_project_load(tmp_path):
    doc = field_document()
    doc.volume = None
    path = tmp_path/'detached.lele'
    save_project(path, state_for(doc))
    restored = load_project(path)['documents'][0]['document']
    assert restored.volume is None
    assert len(restored.volumes) == 2


def test_field_transform_references_survive_snapshot_and_channel_switch(tmp_path):
    from lele.field_actions import select_field
    doc = field_document()
    other = doc.volumes[0]
    # A second dataset may have a different voxel grid (for example a sampled MO).
    other.voxel_vectors = other.voxel_vectors * 2
    other.reference_voxel_vectors = other.voxel_vectors.copy()
    basis_before = other.voxel_vectors.copy()
    origin_before = other.origin.copy()
    rotation = np.array([[0., -1., 0.], [1., 0., 0.], [0., 0., 1.]])
    translation = np.array([2., -1., .5])
    doc.volume.origin = doc.volume.origin @ rotation + translation
    doc.volume.voxel_vectors = doc.volume.voxel_vectors @ rotation
    path = tmp_path/'transformed.lele'
    save_project(path, state_for(doc))
    restored = load_project(path)['documents'][0]['document']
    select_field(restored, 0)
    np.testing.assert_allclose(restored.volume.origin, origin_before @ rotation + translation)
    np.testing.assert_allclose(restored.volume.voxel_vectors, basis_before @ rotation)
    select_field(restored, 1)
    np.testing.assert_allclose(restored.volume.origin, doc.volume.origin)
    np.testing.assert_allclose(restored.volume.voxel_vectors, doc.volume.voxel_vectors)


def test_wavecar_project_retains_metadata_and_explains_missing_source(tmp_path):
    import pytest
    from test_binary_wavefunctions_v320 import write_wavecar
    from lele.binary_wavefunctions import read_wavecar
    source=write_wavecar(tmp_path/'WAVECAR')
    doc=read_wavecar(source)
    path=tmp_path/'wavecar.lele';save_project(path,state_for(doc))
    restored=load_project(path)['documents'][0]['document']
    np.testing.assert_array_equal(restored.wavecar.energies,doc.wavecar.energies)
    np.testing.assert_array_equal(restored.wavecar.coefficients(),doc.wavecar.coefficients())
    source.unlink()
    restored=load_project(path)['documents'][0]['document']
    assert restored.wavecar.nbands==2
    with pytest.raises(ValueError,match='original WAVECAR is unavailable'):
        restored.wavecar.coefficients()


def test_converted_gbw_project_has_no_temporary_file_dependency(tmp_path, monkeypatch):
    from lele.binary_wavefunctions import read_gbw
    from test_wavefunction_inputs import molden_text
    converted_paths=[]
    def converter(source, destination):
        converted_paths.append(destination)
        destination.write_text(molden_text())
        return destination
    monkeypatch.setattr('lele.binary_wavefunctions.convert_gbw_to_molden', converter)
    source=tmp_path/'source.gbw';source.write_bytes(b'synthetic GBW placeholder')
    doc=read_gbw(source)
    assert doc.path==source
    assert not converted_paths[0].exists()
    expected=doc.wavefunction.evaluate_points('alpha',1,np.zeros((1,3)))
    path=tmp_path/'converted.lele';save_project(path,state_for(doc));source.unlink()
    restored=load_project(path)['documents'][0]['document']
    np.testing.assert_array_equal(restored.wavefunction.evaluate_points('alpha',1,np.zeros((1,3))),expected)
