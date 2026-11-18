"""Saved fragment reorder follows atom identities and preserves source results."""
from pathlib import Path
from copy import deepcopy

import numpy as np
import pytest

from lele.atom_appearance import AtomAppearance
from lele.atom_indices import atom_mapping, fragment_order, reorder_atoms, source_order
from lele.core import Document, Frame
from lele.selection_geometry import delete_selected_atoms


def structure():
    return Frame(['C','C','O','H','N','H'],np.arange(18,dtype=float).reshape(6,3),
        np.diag([20.,20.,20.]),(True,True,True),-12.,
        info={'site_occupancies':[{'C':.4,'N':.6},{'C':1.},{'O':1.},{'H':1.},{'N':1.},{'H':.5}],
              'cif_row_order':[(0,'C'),(0,'N'),(1,'C'),(2,'O'),(3,'H'),(4,'N'),(5,'H')],
              'fixed_axes':[[True,False,False],[False]*3,[True]*3,[None]*3,[False,True,False],[False]*3],
              'fixed_axes_basis':'cartesian','fixed_axes_source':'synthetic constraints',
              'vasp_fixed_axes':[[i==0,i==2,i==4] for i in range(6)],
              'qe_forces_ev_ang':np.arange(18,dtype=float).reshape(6,3),
              'qe_masses_amu':[13.,12.,16.,1.,15.,2.],
              'atom_source_order':['source:'+str(i) for i in range(6)],
              'saved_fragments':[{'name':'fragment1','indices':[1,3,5]},
                                 {'name':'fragment2','indices':[0,3]},
                                 {'name':'fragment3','indices':[2]}],
              'fragment_next_id':4},
        bond_added={(0,5)},bond_removed={(1,4)},
        atom_appearance={0:AtomAppearance(color='#112233'),3:AtomAppearance(representation='Sticks')},
        bond_snapshot=frozenset({(0,1),(1,2),(3,5)}),
        periodic_bond_snapshot=((0,1,(1,-1,0)),(3,5,(0,0,1))),
        hbond_added={(0,5):(1,0,0)},hbond_removed={(1,4)})


@pytest.mark.parametrize('destination,expected',[
    ('front',[1,3,5,0,2,4]),('back',[0,2,4,1,3,5])])
def test_fragment_is_stable_block_not_click_order(destination,expected):
    assert fragment_order(6,[5,1,3,1],destination)==expected
    assert fragment_order(6,[],destination)==list(range(6))
    assert fragment_order(6,[5,3,4,0,2,1],destination)==list(range(6))


@pytest.mark.parametrize('count,indices,destination',[
    (4,[4],'front'),(4,[-1],'back'),(4,[1.5],'front'),(4,[0],'middle'),(-1,[],'front')])
def test_invalid_fragment_order_is_rejected(count,indices,destination):
    with pytest.raises(ValueError):fragment_order(count,indices,destination)


def test_reorder_moves_all_frame_properties_and_retains_identity():
    frame=structure();original=frame.clone();original_info=deepcopy(original.info)
    order=fragment_order(6,[5,1,3],'front');mapping=reorder_atoms(frame,order)
    assert mapping=={old:new for new,old in enumerate(order)}
    assert frame.symbols==[original.symbols[i] for i in order]
    np.testing.assert_array_equal(frame.positions,original.positions[order])
    assert source_order(frame)==tuple(source_order(original)[i] for i in order)
    assert atom_mapping(original,frame)==tuple(mapping[i] for i in range(6))
    for key in ('site_occupancies','fixed_axes','vasp_fixed_axes','qe_masses_amu'):
        assert frame.info[key]==[original_info[key][i] for i in order]
    np.testing.assert_array_equal(frame.info['qe_forces_ev_ang'],original_info['qe_forces_ev_ang'][order])
    assert frame.info['saved_fragments']==[
        {'name':'fragment1','indices':[0,1,2]},
        {'name':'fragment2','indices':[1,3]},
        {'name':'fragment3','indices':[4]}]
    assert frame.info['fragment_next_id']==4
    assert frame.atom_appearance[mapping[0]]==original.atom_appearance[0]
    assert frame.atom_appearance[mapping[3]]==original.atom_appearance[3]
    assert frame.bond_added=={(2,3)} and frame.bond_removed=={(0,5)}
    assert frame.bond_snapshot==frozenset({(0,3),(0,4),(1,2)})
    assert frame.periodic_bond_snapshot==((0,3,(-1,1,0)),(1,2,(0,0,1)))
    assert frame.hbond_added=={(2,3):(-1,0,0)} and frame.hbond_removed=={(0,5)}
    assert frame.energy_ev==original.energy_ev
    # An undo snapshot must not share mutable component/constraint rows with
    # later updates to the newly ordered frame.
    frame.info['fixed_axes'][0][0]=True
    frame.info['site_occupancies'][0]['C']=.2
    frame.info['saved_fragments'][0]['indices'].append(4)
    assert original.info['fixed_axes']==original_info['fixed_axes']
    assert original.info['site_occupancies']==original_info['site_occupancies']
    assert original.info['saved_fragments']==original_info['saved_fragments']


def test_delete_drops_empty_fragments_and_remaps_survivors_without_stale_results():
    frame=structure();old=frame.clone();old_fragments=deepcopy(frame.info['saved_fragments'])
    frame.info.update(qe_total_energy_ry=-1.,cartesian_max_force_ev_ang=1.,
                      cartesian_rms_force_ev_ang=.5,coordinate_reorientation={'selection':[0,1,2]})
    assert delete_selected_atoms(frame,[2,3])==2
    assert frame.info['saved_fragments']==[
        {'name':'fragment1','indices':[1,3]},
        {'name':'fragment2','indices':[0]}]
    assert frame.info['fixed_axes']==[old.info['fixed_axes'][i] for i in (0,1,4,5)]
    assert frame.info['fragment_next_id']==4
    assert old.info['saved_fragments']==old_fragments
    assert frame.energy_ev is None
    assert not any(key in frame.info for key in ('qe_total_energy_ry','qe_forces_ev_ang',
        'cartesian_max_force_ev_ang','cartesian_rms_force_ev_ang','coordinate_reorientation'))


def test_fragment_and_constraints_survive_project_roundtrip(tmp_path):
    from lele.project_file import save_project,load_project
    from lele.render_options import RenderOptions
    frame=structure();reorder_atoms(frame,fragment_order(6,[1,3,5],'back'))
    state={'documents':[{'document':Document(Path('input.xyz'),'XYZ',[frame]),
                         'options':RenderOptions(),'frame_index':0}],
           'current_document':0,'selection':[3,4,5]}
    path=tmp_path/'fragment.lele';save_project(path,state)
    restored=load_project(path)
    other=restored['documents'][0]['document'].frames[0]
    assert other.info['saved_fragments']==frame.info['saved_fragments']
    assert other.info['fixed_axes']==frame.info['fixed_axes']
    assert other.info['fragment_next_id']==4
    assert source_order(other)==source_order(frame)
    assert restored['selection']==[3,4,5]


def test_supercell_repeats_fragment_members_and_fixed_axes():
    from lele.supercell import make_supercell
    frame=structure();original=deepcopy(frame.info)
    expanded=make_supercell(frame,(2,1,1),wrap=False)
    assert expanded.info['saved_fragments']==[
        {'name':'fragment1','indices':[1,3,5,7,9,11]},
        {'name':'fragment2','indices':[0,3,6,9]},
        {'name':'fragment3','indices':[2,8]}]
    assert expanded.info['fixed_axes']==original['fixed_axes']*2
    expanded.info['fixed_axes'][6][0]=False
    assert expanded.info['fixed_axes'][0][0] is True
    assert frame.info['fixed_axes']==original['fixed_axes']
    assert frame.info['saved_fragments']==original['saved_fragments']


def test_pasted_atoms_have_unknown_constraint_status_and_keep_existing_fragments():
    from lele.atom_clipboard import paste_atoms
    frame=structure();old=deepcopy(frame.info)
    fragment=Frame(['H'],[[0.,0.,0.]])
    assert paste_atoms(frame,fragment,[4.,0.,0.])==[6]
    assert frame.info['fixed_axes']==old['fixed_axes']+[[None,None,None]]
    assert frame.info['saved_fragments']==old['saved_fragments']
    assert frame.info['fragment_next_id']==4
    assert 'qe_forces_ev_ang' not in frame.info
    reorder_atoms(frame,fragment_order(7,[6],'front'))
    assert frame.info['fixed_axes'][0]==[None,None,None]
