"""Read back actual GIFs: frame order, timing, native rendering and cancellation."""
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from lele.animation_export import (GifSettings, ExportCancelled, export_animation_gif,
                                    gif_delays, vibration_frames, write_gif)
from lele.core import Document, Frame
from lele.formats import load_document
from lele.render_options import RenderOptions


def decoded(path):
    with Image.open(path) as gif:
        info = dict(gif.info)
        frames, durations = [], []
        for i in range(gif.n_frames):
            gif.seek(i)
            frames.append(np.asarray(gif.convert('RGB')).copy())
            durations.append(gif.info['duration'])
        return info, frames, durations


def test_streamed_gif_preserves_each_palette_frame_and_fractional_fps(tmp_path):
    colors = ['#ff0000', '#008000', '#0000ff', '#0000ff', '#ffff00', '#ff00ff']
    path = tmp_path / 'palette.gif'
    updates = []
    write_gif(path, (Image.new('RGB', (24, 20), color) for color in colors),
              gif_delays(6, 6), progress=lambda i, total: updates.append((i, total)))
    info, frames, durations = decoded(path)
    assert info['loop'] == 0
    assert len(frames) == 6  # Deliberate repeated input frame is kept.
    assert durations[:3] == [170, 160, 170]
    assert sum(durations) == 1000
    assert updates[-1] == (6, 6)
    for frame, color in zip(frames, colors):
        np.testing.assert_array_equal(frame[0, 0], np.asarray(Image.new('RGB', (1, 1), color))[0, 0])


def test_single_play_gif_omits_loop_extension(tmp_path):
    path = tmp_path / 'once.gif'
    write_gif(path, [Image.new('RGB', (10, 10), color) for color in ['red', 'blue']],
              [100, 100], loop=False)
    assert 'loop' not in decoded(path)[0]


def test_cancel_preserves_destination_and_removes_partial_file(tmp_path):
    path = tmp_path / 'existing.gif'
    path.write_bytes(b'original file')
    stop = False
    def progress(value, total):
        nonlocal stop
        stop = value == 1
    with pytest.raises(ExportCancelled):
        write_gif(path, (Image.new('RGB', (20, 20), c) for c in ['red', 'blue']),
                  [100, 100], cancelled=lambda: stop, progress=progress)
    assert path.read_bytes() == b'original file'
    assert list(tmp_path.iterdir()) == [path]


@pytest.mark.parametrize('failure', ['too_few', 'too_many', 'wrong_size', 'generator_error'])
def test_failed_export_cannot_replace_existing_destination(tmp_path, failure):
    path = tmp_path / 'existing.gif'
    path.write_bytes(b'original file')
    def images():
        yield Image.new('RGB', (20, 20), 'red')
        if failure == 'generator_error':
            raise RuntimeError('Interrupted renderer')
        if failure != 'too_few':
            yield Image.new('RGB', (10 if failure == 'wrong_size' else 20, 20), 'blue')
        if failure == 'too_many':
            yield Image.new('RGB', (20, 20), 'green')
    with pytest.raises((ValueError, RuntimeError)):
        write_gif(path, images(), [100, 100])
    assert path.read_bytes() == b'original file'
    assert list(tmp_path.iterdir()) == [path]


def test_frame_range_and_ping_pong_do_not_repeat_endpoints():
    settings = GifSettings(first_frame=2, last_frame=6, stride=2, ping_pong=True)
    assert settings.trajectory_indices(8) == [1, 3, 5, 3]
    with pytest.raises(ValueError, match='at least two'):
        GifSettings(first_frame=2, last_frame=2).trajectory_indices(8)


def test_vibration_sampling_omits_duplicate_final_pose_and_preserves_source():
    doc = load_document(Path(__file__).resolve().parents[1] / 'examples/synthetic_opt_freq.log')
    reference, mode = doc.vibrations[0].reference, doc.vibrations[0].modes[0]
    coordinates, vectors = reference.positions.copy(), mode.displacements.copy()
    frames = list(vibration_frames(reference, mode, 24, .6))
    assert len(frames) == 24
    np.testing.assert_array_equal(frames[0].positions, coordinates)
    assert not np.allclose(frames[-1].positions, coordinates)
    assert np.linalg.norm(frames[6].positions - coordinates, axis=1).max() == pytest.approx(.6)
    np.testing.assert_allclose(frames[6].positions - coordinates,
                               coordinates - frames[18].positions)
    np.testing.assert_array_equal(reference.positions, coordinates)
    np.testing.assert_array_equal(mode.displacements, vectors)
    assert sum(gif_delays(24, 24, cycle_seconds=1.)) == 1000


def test_short_cycle_rounding_keeps_frame_delays_at_least_twenty_ms():
    settings = GifSettings(source='vibration', fps=50, cycle_seconds=.23)
    count = settings.vibration_frame_count()
    delays = gif_delays(count, settings.fps, cycle_seconds=.23)
    assert count == 11
    assert sum(delays) == 230
    assert min(delays) >= 20


def test_native_trajectory_gif_order_image_orientation_size_and_camera(tmp_path):
    from vtkmodules.vtkRenderingCore import vtkCamera
    frames = [Frame(['O'], [[i * .5, i * .15, 0]]) for i in range(5)]
    original = [f.positions.copy() for f in frames]
    doc = Document(Path('moving.xyz'), 'XYZ', frames)
    options = RenderOptions(background='#ffffff', axes_position='Off')
    camera = vtkCamera()
    camera.SetPosition(1, .3, 10)
    camera.SetFocalPoint(1, .3, 0)
    camera.SetParallelProjection(True)
    camera.SetParallelScale(2.)
    camera_state = (camera.GetPosition(), camera.GetFocalPoint(), camera.GetParallelScale(), camera.GetClippingRange())
    settings = GifSettings(width=160, height=120, fps=5, first_frame=2, last_frame=4, ping_pong=True)
    path = tmp_path / '优化轨迹.gif'
    assert export_animation_gif(path, doc, settings, options, camera=camera) == 4
    info, images, durations = decoded(path)
    assert len(images) == 4 and images[0].shape == (120, 160, 3)
    assert sum(durations) == 800
    centers = []
    for image in images:
        mask = (image[:, :, 0] > image[:, :, 1] + 25.) & (image[:, :, 0] > image[:, :, 2] + 25.)
        ys, xs = np.where(mask)
        assert len(xs) > 10
        centers.append((xs.mean(), ys.mean()))
    assert centers[0][0] < centers[1][0] < centers[2][0]
    assert centers[0][1] > centers[1][1] > centers[2][1]  # VTK bottom-up -> image top-down.
    np.testing.assert_allclose(centers[1], centers[3], atol=.2)
    assert (camera.GetPosition(), camera.GetFocalPoint(), camera.GetParallelScale(), camera.GetClippingRange()) == camera_state
    for f, old in zip(doc.frames, original):
        np.testing.assert_array_equal(f.positions, old)


def test_native_vibration_gif_has_full_motion_and_reference_connectivity(tmp_path):
    doc = load_document(Path(__file__).resolve().parents[1] / 'examples/synthetic_opt_freq.log')
    analysis = doc.vibrations[0]
    originals = [f.positions.copy() for f in doc.frames]
    reference = analysis.reference.positions.copy()
    settings = GifSettings(source='vibration', width=180, height=140, fps=8, amplitude=.4)
    path = tmp_path / 'imaginary.gif'
    count = export_animation_gif(path, doc, settings, RenderOptions(background='#ffffff'),
                                 reference=analysis.reference, mode=analysis.modes[0])
    _, images, delays = decoded(path)
    assert count == len(images) == 8
    assert sum(delays) == 1000
    assert np.count_nonzero(images[0] != images[2]) > 100
    assert np.count_nonzero(images[2] != images[6]) > 100
    assert np.count_nonzero(images[0] != images[-1]) > 100
    for f, old in zip(doc.frames, originals):
        np.testing.assert_array_equal(f.positions, old)
    np.testing.assert_array_equal(analysis.reference.positions, reference)
    assert not doc.modified


def test_mode_without_vectors_is_rejected_before_creating_a_file(tmp_path):
    from lele.core import NormalMode
    doc = Document(Path('x.xyz'), 'XYZ', [Frame(['H'], [[0, 0, 0]])])
    path = tmp_path / 'missing.gif'
    with pytest.raises(ValueError, match='complete displacement'):
        export_animation_gif(path, doc, GifSettings(source='vibration'), RenderOptions(),
                              reference=doc.frames[0], mode=NormalMode(1, 100.))
    assert not path.exists()
