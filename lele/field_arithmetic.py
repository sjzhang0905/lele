"""Transactional arithmetic of physically compatible scalar grids.

Grid values are combined without interpolation, atom fitting, registration,
or source mutation. Atomic structures may differ (fragment densities), but
the sampled physical coordinates and periodic cells must agree.
"""
from dataclasses import dataclass
from pathlib import Path
import numpy as np
from .core import Volume
from .field_mapping import field_transform
from .output_text import check_load_cancelled, load_progress

from .grid_memory import AUTO, scalar_limit
MAX_FIELD_VALUES = AUTO
GRID_ATOL = 1e-6  # Å, allows text round-trip precision, not real alignment.
GRID_RTOL = 1e-8
DECLARED_UNITS = ('e/Å³', 'e/Bohr³', 'eV', 'Hartree', 'dimensionless',
                  'Å⁻³ᐟ²', 'Bohr⁻³ᐟ²')


@dataclass(frozen=True)
class FieldTerm:
    document: object
    index: int
    sign: int = 1
    declared_unit: str | None = None


def unit_spec(unit):
    """Return physical family, factor to Å/eV units and normalized spelling.

    Unknown CUBE units are rejected rather than assuming that two unknown
    strings describe the same physical quantity. A caller may explicitly
    declare them through FieldTerm.declared_unit.
    """
    from ase.units import Bohr, Hartree
    text = str(unit or '').strip()
    units = {
        'e/Å³': ('density', 1., 'e/Å³'),
        'e/Bohr³': ('density', 1/Bohr**3, 'e/Bohr³'),
        'Å⁻³': ('density', 1., 'e/Å³'),
        'Bohr⁻³': ('density', 1/Bohr**3, 'e/Bohr³'),
        'e/Angstrom^3': ('density', 1., 'e/Å³'),
        'e/A^3': ('density', 1., 'e/Å³'),
        'e/Bohr^3': ('density', 1/Bohr**3, 'e/Bohr³'),
        'eV': ('potential', 1., 'eV'),
        'Hartree': ('potential', Hartree, 'Hartree'),
        'Ha': ('potential', Hartree, 'Hartree'),
        'dimensionless': ('dimensionless', 1., 'dimensionless'),
        'Å⁻³ᐟ²': ('amplitude', 1., 'Å⁻³ᐟ²'),
        'Bohr⁻³ᐟ²': ('amplitude', 1/Bohr**1.5, 'Bohr⁻³ᐟ²'),
    }
    if text in units:
        return units[text]
    # These labels are produced by LELE's WAVECAR reader. Retain their
    # qualifier in provenance; units still have an unambiguous dimension.
    for prefix in ('Å⁻³', 'Bohr⁻³', 'Å⁻³ᐟ²', 'Bohr⁻³ᐟ²'):
        if text.startswith(prefix + ' (') and text.endswith(')'):
            return units[prefix]
    raise ValueError(f'Unknown scalar units: {text or "not specified"}. Explicitly declare the physical unit before combining this field.')


def _term_volume(term):
    if term.sign not in (-1, 1):
        raise ValueError('Each field operation must be + or −.')
    if term.document is None or term.document.volume is None:
        raise ValueError('A source field was detached from its structure. Undo the edit or reopen that source.')
    if isinstance(term.index, bool) or not isinstance(term.index, (int, np.integer)) or not 0 <= term.index < len(term.document.volumes):
        raise ValueError('The selected source dataset is unavailable.')
    return term.document.volumes[term.index]


def _effective_grid(document, volume):
    transform, shift = field_transform(document.volume)
    basis = np.asarray(volume.reference_voxel_vectors) @ transform
    origin = np.asarray(volume.reference_origin) @ transform + shift
    if (not np.isfinite(basis).all() or not np.isfinite(origin).all()
            or abs(np.linalg.det(basis)) < 1e-15):
        raise ValueError('A field has a nonfinite or singular grid basis.')
    return origin, basis


def _symbol(index):
    text = ''
    while True:
        text = chr(ord('A') + index % 26) + text
        index = index // 26 - 1
        if index < 0:
            return text


def expression_formula(terms):
    return ' '.join(('− ' if t.sign < 0 else '+ ' if i else '') + _symbol(i)
                    for i, t in enumerate(terms))


def _effective_unit(term, volume):
    if term.declared_unit is None:
        return unit_spec(volume.unit)
    declared = unit_spec(term.declared_unit)
    try:
        known = unit_spec(volume.unit)
    except ValueError:
        return declared
    if known != declared:
        raise ValueError('A known source unit cannot be relabeled. Compatible unit conversion is applied automatically without changing its meaning.')
    return known


def combine_fields(terms, *, target_document=None, target_frame=None,
                   label='', chunk_size=262144):
    """Prepare a new Volume; neither source nor target is modified on failure.

    Compatible scalar units are explicitly converted to the first operand's
    unit. The new Volume retains a self-contained formula and source records;
    its bytes, not a recipe that reloads sources, are saved in project files.
    """
    terms = tuple(terms)
    if not 2 <= len(terms) <= 64:
        raise ValueError('Choose between 2 and 64 fields to add or subtract.')
    if chunk_size < 1:
        raise ValueError('Chunk size must be positive.')
    target = terms[0].document if target_document is None else target_document
    if target is None or target.volume is None:
        raise ValueError('The current document needs an attached reference field.')
    if target_frame is None:
        target_frame = target.frames[0] if target.frames else None
    if target_frame is None:
        raise ValueError('The result needs the current document structure.')
    reference = target.volume
    shape = reference.data.shape
    if len(shape) != 3 or min(shape) < 2:
        raise ValueError('A field must be a three-dimensional grid with at least two nodes per direction.')
    if sum(v.data.size for v in target.volumes) + reference.data.size > scalar_limit(MAX_FIELD_VALUES):
        raise ValueError('Adding this result would exceed the available scalar-field memory budget for the document.')
    origin, basis = _effective_grid(target, reference)
    if reference.periodic and not np.allclose(basis*np.asarray(shape)[:, None],
            target_frame.cell, atol=GRID_ATOL, rtol=GRID_RTOL):
        raise ValueError('The periodic field cell does not match the current structure cell.')
    volumes, factors, records = [], [], []
    family = output_factor = output_unit = None
    for i, term in enumerate(terms):
        check_load_cancelled()
        volume = _term_volume(term)
        if volume.data.shape != shape:
            raise ValueError(f'Field {_symbol(i)} has a different grid shape. No interpolation is performed.')
        if bool(volume.periodic) != bool(reference.periodic):
            raise ValueError(f'Field {_symbol(i)} has different periodicity. Convert both sources to the same physical grid first.')
        candidate_origin, candidate_basis = _effective_grid(term.document, volume)
        if not np.allclose(candidate_origin, origin, atol=GRID_ATOL, rtol=0):
            raise ValueError(f'Field {_symbol(i)} has a different grid origin. No translation or registration is performed.')
        if not np.allclose(candidate_basis, basis, atol=GRID_ATOL, rtol=GRID_RTOL):
            raise ValueError(f'Field {_symbol(i)} has different voxel vectors / cell. No rotation, rescaling or interpolation is performed.')
        source_frame = target_frame if term.document is target else (
            term.document.frames[0] if term.document.frames else None)
        if volume.periodic and (source_frame is None or not np.allclose(
                candidate_basis*np.asarray(shape)[:, None], source_frame.cell,
                atol=GRID_ATOL, rtol=GRID_RTOL)):
            raise ValueError(f'Field {_symbol(i)} has an inconsistent periodic structure cell.')
        current_family, factor, unit = _effective_unit(term, volume)
        if i == 0:
            family, output_factor, output_unit = current_family, factor, unit
        elif family != current_family:
            raise ValueError(f'Field {_symbol(i)} has incompatible physical units ({volume.unit}). Density, potential and orbital amplitude cannot be added to one another.')
        conversion = factor/output_factor
        volumes.append(volume)
        factors.append(term.sign*conversion)
        records.append(dict(symbol=_symbol(i), sign=term.sign,
            source_path=str(Path(term.document.path)), dataset_index=int(term.index),
            dataset_label=volume.label, source_unit=volume.unit,
            declared_unit=term.declared_unit, conversion_factor=conversion,
            source_operation=volume.provenance.get('operation',''),
            source_formula=volume.provenance.get('formula','')))
    check_load_cancelled()
    output = np.empty(shape, dtype=np.float32)
    flat = output.ravel()
    report = load_progress('Combining scalar fields', len(flat))
    max_float = np.finfo(np.float32).max
    for start in range(0, len(flat), chunk_size):
        check_load_cancelled()
        stop = min(start+chunk_size, len(flat))
        combined = np.zeros(stop-start, dtype=np.float64)
        for volume, factor in zip(volumes, factors):
            check_load_cancelled()
            values = np.asarray(volume.data.flat[start:stop], dtype=np.float64)
            if not np.isfinite(values).all():
                raise ValueError('A source grid contains nonfinite values.')
            combined += values*factor
        if not np.isfinite(combined).all() or np.any(np.abs(combined) > max_float):
            raise ValueError('Field arithmetic exceeds the finite float32 scalar range.')
        flat[start:stop] = combined
        report(stop)
    check_load_cancelled()
    formula = expression_formula(terms)
    provenance = dict(operation='field_arithmetic', formula=formula,
        output_unit=output_unit, terms=records, grid_shape=list(shape),
        interpolation='none', grid_tolerance_A=GRID_ATOL)
    if 'grid_extent' in reference.provenance:
        provenance['grid_extent'] = reference.provenance['grid_extent']
    quantity = dict(density='Density', potential='Potential', amplitude='Amplitude', dimensionless='Scalar')[family]
    return Volume(output, origin.copy(), basis.copy(),
        label.strip() or quantity + ' arithmetic: ' + formula, output_unit, reference.periodic,
        reference.reference_origin.copy(), reference.reference_voxel_vectors.copy(), provenance)


def append_field_result(document, result, *, expected_active):
    """Commit only after successful calculation and a final state check."""
    if document.volume is not expected_active or expected_active is None:
        raise ValueError('The active reference field changed. Reopen field arithmetic and calculate again.')
    if result.provenance.get('operation') != 'field_arithmetic':
        raise ValueError('This is not a completed field-arithmetic result.')
    if sum(v.data.size for v in document.volumes)+result.data.size > scalar_limit(MAX_FIELD_VALUES):
        raise ValueError('The resulting document exceeds the scalar-value memory limit.')
    check_load_cancelled()
    document.volumes.append(result)
    document.volume = result
    return len(document.volumes)-1
