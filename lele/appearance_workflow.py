"""Document-wide display edits with compact, coordinate-independent undo."""
from dataclasses import replace
from .atom_appearance import DEFAULT_APPEARANCE, appearance


def _targets(window):
    doc = window.doc
    result = [('frame', i, frame) for i, frame in enumerate(doc.frames)]
    result += [('reference', i, analysis.reference) for i, analysis in enumerate(doc.vibrations)
               ]
    result += [('preview', key, frame) for key, frame in window._vibration_references.items()
               if key[0] == window.current_doc]
    return result


def apply_appearance(window, indices, values, reset=False):
    targets = _targets(window)
    changes = []
    for kind, key, frame in targets:
        from .atom_indices import atom_mapping
        mapping=atom_mapping(window.frame,frame,allow_partial=True)
        if mapping is None:continue
        updated = frame.atom_appearance.copy()
        for i in dict.fromkeys(indices):
            if 0 <= i < len(mapping) and mapping[i] is not None:
                i=mapping[i]
                style = DEFAULT_APPEARANCE if reset else replace(appearance(frame, i), **values)
                if style == DEFAULT_APPEARANCE:
                    updated.pop(i, None)
                else:
                    updated[i] = style
        if updated != frame.atom_appearance:
            changes.append((kind, key, frame, updated))
    if not changes:
        return False
    snapshot = [(kind, key, frame.atom_appearance.copy()) for kind, key, frame, _ in changes]
    window.undo_stack.append(('appearance', window.current_doc, window.frame_index,
                              list(window.selection), window._active_vibration, snapshot))
    window.undo_stack = window.undo_stack[-50:]
    for _, _, frame, updated in changes:
        frame.atom_appearance = updated
    return True


def restore_appearance(window, document_index, snapshots):
    doc = window.documents[document_index]
    for kind, key, styles in snapshots:
        if kind == 'frame':
            frame = doc.frames[key]
        elif kind == 'reference':
            frame = doc.vibrations[key].reference
        else:
            frame = window._vibration_references.get(key)
        if frame is not None:
            frame.atom_appearance = styles.copy()
