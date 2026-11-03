"""Write minimal acceptance inputs and record actual v2.13.1 failures.

Usage: PYTHONPATH=/path/to/LELE python reproduce_findings.py /path/to/evidence
Returns 1 while any confirmed finding remains reproducible.
"""
import json
from pathlib import Path
import sys
from lele.formats import load_document

destination=Path(sys.argv[1]);destination.mkdir(parents=True,exist_ok=True)
rows={
    'A1_pqr_single_space.pqr':'ATOM 1 O ASN 1 1.000 2.000 3.000 -0.8 1.5\n',
    'A1_pqr_double_space.pqr':'ATOM  1 O ASN 1 1.000 2.000 3.000 -0.8 1.5\n',
    'A1_pqr_hetatm.pqr':'HETATM 1 O ASN 1 1.000 2.000 3.000 -0.8 1.5\n',
    'control_pqr_fixed_width.pqr':'ATOM      1  O   WAT A   1       1.000   2.000   3.000 -0.8000 1.5000\n',
    'A2_cube_negative.cube':'Synthetic Angstrom grid\nLELE negative-count branch\n1 1 2 3\n-2 .5 0 0\n-2 0 .5 0\n-2 0 0 .5\n8 0 1.25 2.25 3.25\n0 1 2 3 4 5 6 7\n',
    'control_cube_positive.cube':'Synthetic Bohr grid\nLELE positive-count branch\n1 1 2 3\n2 .5 0 0\n2 0 .5 0\n2 0 0 .5\n8 0 1.25 2.25 3.25\n0 1 2 3 4 5 6 7\n'}
result={}
for name,text in rows.items():
    path=destination/name;path.write_text(text)
    expected=['O']
    try:
        document=load_document(path);frame=document.frames[0]
        row={'expected_symbols':expected,'actual_symbols':frame.symbols,'positions':frame.positions.tolist(),
            'volume_shape':None if document.volume is None else list(document.volume.data.shape),
            'correct':frame.symbols==expected and (not name.endswith('cube') or document.volume is not None)}
    except Exception as exc:
        row={'expected_symbols':expected,'correct':False,'error_type':type(exc).__name__,'error':str(exc)}
    result[name]=row
(destination/'findings.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
sys.exit(0 if all(row['correct'] for row in result.values()) else 1)
