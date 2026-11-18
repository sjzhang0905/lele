"""Consistent filename suffixes and POSCAR prefixes for structure exports."""
from pathlib import Path


def structure_export_path(path, target):
    path = Path(path)
    if target in ('poscar-direct', 'poscar-cartesian'):
        name = path.name
        return path.with_name('POSCAR' + (name[6:] if name.upper().startswith('POSCAR') else name))
    suffix = {'gjf': '.gjf', 'xyz': '.xyz', 'cif': '.cif'}.get(target)
    if suffix is not None and path.suffix.lower() != suffix:
        return Path(str(path) + suffix)
    return path
