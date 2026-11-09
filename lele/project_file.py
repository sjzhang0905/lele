"""Portable .lele snapshots: JSON object graph and numeric NPY arrays in ZIP.

Only explicitly registered LELE data classes can be reconstructed. No Python
pickle, executable objects, arbitrary module imports or file extraction is used.
"""
from dataclasses import fields, is_dataclass, MISSING
from importlib import import_module
from pathlib import Path
import json
import math
import os
import tempfile
import zipfile
import numpy as np
from . import __version__
from .output_text import load_progress,check_load_cancelled,progress_items

FORMAT = 'LELE_PROJECT'
SCHEMA = 1
MODULES = ('core', 'render_options', 'atom_appearance', 'calculation_results',
    'vasp_results', 'orca_neb', 'orca_goat', 'orca_soc', 'gaussian_properties',
    'trajectory_analysis', 'selection_geometry', 'periodic_geometry','cp2k_results','qe_results','qe_phonons',
    'siesta_results', 'gaussian_basis', 'binary_wavefunctions','nmr')


def data_types():
    result = {}
    for short in MODULES:
        module = import_module('lele.'+short)
        for name, value in vars(module).items():
            if isinstance(value, type) and is_dataclass(value) and value.__module__ == module.__name__:
                result[module.__name__+':'+name] = value
    return result


def extra_fields(cls):
    return {'vibrations', 'frequency_records'} if cls.__name__ == 'VaspResults' else set()


class Encoder:
    def __init__(self):
        self.nodes = [];self.arrays = {};self.memo = {};self.types = data_types()
        self.progress=load_progress('Project: encoding data')

    def encode(self, value):
        if len(self.nodes)%512==0:self.progress(len(self.nodes));check_load_cancelled()
        if isinstance(value, np.generic):value = value.item()
        if value is None or isinstance(value, (bool, str, int)):return value
        if isinstance(value, float):
            return value if math.isfinite(value) else {'scalar':'float', 'value':repr(value)}
        if isinstance(value, complex):return {'scalar':'complex', 'real':self.encode(value.real), 'imag':self.encode(value.imag)}
        if isinstance(value, Path):return {'scalar':'path', 'value':str(value)}
        identity = id(value)
        if identity in self.memo:return {'ref':self.memo[identity]}
        index = len(self.nodes);self.memo[identity] = index;self.nodes.append({})
        if isinstance(value, np.ndarray):
            if value.dtype.hasobject:raise ValueError('Project arrays must not contain Python objects.')
            name = f'arrays/{len(self.arrays):06d}.npy';self.arrays[name] = value
            node = dict(kind='array', path=name)
        elif isinstance(value, dict):node = dict(kind='dict', items=[[self.encode(k), self.encode(v)] for k, v in value.items()])
        elif isinstance(value, (list, tuple, set, frozenset)):
            node = dict(kind=type(value).__name__, items=[self.encode(v) for v in value])
        elif is_dataclass(value):
            name = type(value).__module__+':'+type(value).__name__
            if self.types.get(name) is not type(value):raise ValueError('Unsupported project data class: '+name)
            allowed = {f.name for f in fields(value)} | extra_fields(type(value))
            attributes = {key:self.encode(v) for key, v in vars(value).items() if key in allowed}
            unknown = set(vars(value))-allowed
            if unknown:raise ValueError(f'Unsupported fields for {name}: '+', '.join(sorted(unknown)))
            node = dict(kind='object', type=name, attributes=attributes)
        else:raise ValueError('Unsupported project value: '+type(value).__name__)
        self.nodes[index] = node
        return {'ref':index}


class Decoder:
    def __init__(self, nodes, archive):
        self.nodes = nodes;self.archive = archive;self.memo = {};self.pending = set();self.objects = []
        self.types = data_types()
        self.progress=load_progress('Project: decoding data',len(nodes))

    def decode(self, value):
        if len(self.memo)%512==0:self.progress(len(self.memo));check_load_cancelled()
        if value is None or isinstance(value, (str, bool, int, float)):return value
        if not isinstance(value, dict):raise ValueError('Invalid project value.')
        if 'scalar' in value:
            kind = value['scalar']
            if kind == 'path':return Path(value['value'])
            if kind == 'complex':return complex(self.decode(value['real']), self.decode(value['imag']))
            if kind == 'float' and value['value'] in ('nan', 'inf', '-inf'):return float(value['value'])
            raise ValueError('Unknown project scalar.')
        index = value['ref']
        if not isinstance(index, int) or not 0 <= index < len(self.nodes):raise ValueError('Invalid project reference.')
        if index in self.memo:return self.memo[index]
        if index in self.pending:raise ValueError('Unsupported immutable reference cycle.')
        self.pending.add(index)
        node = self.nodes[index];kind = node['kind']
        if kind == 'array':
            name = node['path']
            if not name.startswith('arrays/') or not name.endswith('.npy'):raise ValueError('Invalid project array path.')
            with self.archive.open(name) as stream:result = np.load(stream, allow_pickle=False)
            if not isinstance(result, np.ndarray) or result.dtype.hasobject:raise ValueError('Invalid project array.')
        elif kind == 'object':
            cls = self.types.get(node['type'])
            if cls is None:raise ValueError('Unknown project data class: '+str(node['type']))
            result = cls.__new__(cls);self.memo[index] = result
            attributes = node['attributes'];allowed = {f.name for f in fields(cls)} | extra_fields(cls)
            if set(attributes)-allowed:raise ValueError('Unknown project data fields.')
            for f in fields(cls):
                if f.name in attributes:decoded = self.decode(attributes[f.name])
                elif f.default is not MISSING:decoded = f.default
                elif f.default_factory is not MISSING:decoded = f.default_factory()
                else:raise ValueError('Missing project field: '+f.name)
                object.__setattr__(result, f.name, decoded)
            if cls.__name__ == 'RenderOptions' and 'bond_model' not in attributes:
                # Projects saved before 2.9 retain their original connectivity.
                result.bond_model = 'Covalent radii'
            for key in extra_fields(cls):object.__setattr__(result, key, self.decode(attributes[key]) if key in attributes else [])
            self.objects.append(result)
        elif kind == 'dict':
            result = {};self.memo[index] = result
            for key, item in node['items']:result[self.decode(key)] = self.decode(item)
        elif kind in ('list', 'set'):
            result = [] if kind == 'list' else set();self.memo[index] = result
            for item in node['items']:
                if kind == 'list':result.append(self.decode(item))
                else:result.add(self.decode(item))
        elif kind in ('tuple', 'frozenset'):
            decoded = [self.decode(v) for v in node['items']]
            result = tuple(decoded) if kind == 'tuple' else frozenset(decoded)
        else:raise ValueError('Unknown project node kind.')
        self.memo[index] = result;self.pending.remove(index)
        return result

    def validate_objects(self):
        priority = {'AtomAppearance':0, 'Frame':1, 'Volume':1, 'NormalMode':2, 'VibrationalAnalysis':3, 'Document':4}
        for obj in sorted(self.objects, key=lambda o:priority.get(type(o).__name__, 2)):
            post = getattr(type(obj), '__post_init__', None)
            if post is not None:post(obj)


def save_project(path, state):
    path = Path(path);encoder = Encoder();root = encoder.encode(state)
    manifest = dict(format=FORMAT, schema=SCHEMA, application_version=__version__, root=root, nodes=encoder.nodes)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix='.'+path.name+'.', suffix='.tmp')
    os.close(descriptor)
    try:
        with zipfile.ZipFile(temporary, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=6, allowZip64=True) as archive:
            archive.writestr('manifest.json', json.dumps(manifest, ensure_ascii=False, allow_nan=False))
            for name, array in progress_items(encoder.arrays.items(),'Project: writing numeric arrays'):
                with archive.open(name, 'w', force_zip64=True) as stream:np.save(stream, array, allow_pickle=False)
        check_load_cancelled();os.replace(temporary, path)
    finally:Path(temporary).unlink(missing_ok=True)
    return path


def load_project(path):
    try:
        with zipfile.ZipFile(path) as archive:
            manifest = json.loads(archive.read('manifest.json'))
            if manifest.get('format') != FORMAT or manifest.get('schema') != SCHEMA:
                raise ValueError('Unsupported LELE project format/version.')
            decoder = Decoder(manifest['nodes'], archive);state = decoder.decode(manifest['root'])
            decoder.validate_objects()
        from .vasp_results import normalize_document_e0
        for entry in state.get('documents', []):
            normalize_document_e0(entry['document'], entry.get('vibration_references', {}).values())
            document = entry['document']
            frames = list(document.frames) + [a.reference for a in document.vibrations]
            frames += list(entry.get('vibration_references', {}).values())
            for frame in frames:frame.info.setdefault('bond_model', entry['options'].bond_model)
        validate_state(state)
        return state
    except (KeyError, TypeError, IndexError, AttributeError, zipfile.BadZipFile, json.JSONDecodeError) as exc:
        raise ValueError('Invalid or incomplete LELE project: '+str(exc)) from exc


def validate_state(state):
    from .core import Document, Frame
    from .render_options import RenderOptions
    from .style_presets import snapshot, validate_preset
    from .crystal_planes import validate_planes
    from .polyhedra import validate_polyhedra
    from .element_rules import validate_rules
    if not isinstance(state, dict) or not isinstance(state.get('documents'), list) or not state['documents']:
        raise ValueError('A project needs at least one document.')
    for entry in state['documents']:
        document, options = entry['document'], entry['options']
        if not isinstance(document, Document) or any(not isinstance(f, Frame) for f in document.frames):
            raise ValueError('Invalid project structures.')
        for frame in document.frames:
            if not isinstance(frame.info, dict) or len(frame.pbc) != 3 or any(not isinstance(s, str) for s in frame.symbols):
                raise ValueError('Invalid structure metadata in project.')
        if document.source_preview is not None and not isinstance(document.source_preview, str):
            raise ValueError('Invalid project source preview.')
        if not isinstance(options, RenderOptions):raise ValueError('Invalid project display settings.')
        validate_preset(snapshot(options));validate_planes(options.lattice_planes);validate_polyhedra(options)
        validate_rules(options.element_pair_rules)
        if options.bond_model not in ('Chemcraft pair ranges', 'Covalent radii'):
            raise ValueError('Invalid bond search model.')
        if not math.isfinite(options.bond_cutoff) or not .1 <= options.bond_cutoff <= 5.:
            raise ValueError('Invalid bond distance multiplier.')
        if not 0 <= entry.get('frame_index', 0) < max(1, len(document.frames)):raise ValueError('Invalid project frame index.')
        camera = entry.get('camera')
        if camera is not None:
            for key in ('position', 'focal_point', 'view_up'):
                a = np.asarray(camera[key], float)
                if a.shape != (3,) or not np.isfinite(a).all():raise ValueError('Invalid project camera vector.')
            for key in ('parallel_scale', 'view_angle'):
                if not np.isfinite(camera[key]) or camera[key] <= 0:raise ValueError('Invalid project camera scale.')
            clipping = np.asarray(camera['clipping_range'], float)
            if clipping.shape != (2,) or not np.isfinite(clipping).all() or not 0 < clipping[0] < clipping[1]:
                raise ValueError('Invalid project camera clipping range.')
            window = np.asarray(camera.get('window_center', (0., 0.)), float)
            if window.shape != (2,) or not np.isfinite(window).all():raise ValueError('Invalid camera window center.')
    if not 0 <= state.get('current_document', 0) < len(state['documents']):raise ValueError('Invalid active project document.')
    vibration = state.get('active_vibration')
    if vibration is not None:
        di, ai, mi = vibration
        if not 0 <= di < len(state['documents']):raise ValueError('Invalid vibration document.')
        analyses = state['documents'][di]['document'].vibrations
        if not 0 <= ai < len(analyses) or not 0 <= mi < len(analyses[ai].modes):raise ValueError('Invalid vibration reference.')
    energy = state.get('energy_only_context')
    if energy is not None:
        di, si = energy
        if not 0 <= di < len(state['documents']):raise ValueError('Invalid results document.')
        results = state['documents'][di]['document'].calculation_results
        if results is None or not 0 <= si < len(results.steps):raise ValueError('Invalid results step.')
    controls = state.get('vibration_controls', {})
    for key, lo, hi in (('amplitude', .01, 2.), ('speed', .1, 5.), ('arrow_length', .05, 5.)):
        if key in controls and (not np.isfinite(controls[key]) or not lo <= controls[key] <= hi):
            raise ValueError('Invalid vibration display control.')
    sequence = state.get('result_sequence')
    if sequence is not None:
        document, indices, label = sequence
        if not any(document is e['document'] for e in state['documents']) or not isinstance(label, str):
            raise ValueError('Invalid project result sequence.')
        if any(not isinstance(i, int) or not 0 <= i < len(document.frames) for i in indices):
            raise ValueError('Invalid result sequence frame.')
