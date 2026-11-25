"""Build a schema-1 ZIP for the historical field-migration tests."""
from io import BytesIO
import json
from zipfile import ZipFile

import numpy as np

from lele.project_file import FORMAT, SCHEMA
from lele.project_text import read_project_text


def legacy_archive(path):
    with path.open(encoding='utf-8') as stream:
        root, nodes, arrays = read_project_text(stream, path.stat().st_size, FORMAT, SCHEMA)
    data = BytesIO()
    with ZipFile(data, 'w') as archive:
        for index, array in arrays.items():
            name = f'arrays/{index:06d}.npy'
            nodes[index] = dict(kind='array', path=name)
            with archive.open(name, 'w') as member:
                np.save(member, array, allow_pickle=False)
        manifest = dict(format=FORMAT, schema=1, root=root, nodes=nodes)
        archive.writestr('manifest.json', json.dumps(manifest))
    return ZipFile(data)
