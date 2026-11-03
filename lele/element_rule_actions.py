"""Explicit, undoable application of per-document pair rules."""
from copy import deepcopy
from PySide6.QtWidgets import QMessageBox


class ElementRuleActions:
    def _initialize_document_pair_rules(self, document, options):
        from .element_rules import install_rules
        frames = list(document.frames)+[a.reference for a in document.vibrations]
        for frame in frames:
            frame.info.setdefault('bond_model', options.bond_model)
            if 'element_pair_rules' not in frame.info:install_rules(frame, options.element_pair_rules, options.pair_rules_only)

    def _rule_targets(self, document, index):
        result = [(('frame', i), frame) for i, frame in enumerate(document.frames)]
        result += [(('vibration', i), a.reference) for i, a in enumerate(document.vibrations)]
        result += [(('cached', key[1]), frame) for key, frame in self._vibration_references.items() if key[0] == index]
        return result

    def _apply_element_pair_rules(self, values, only=False):
        if self.doc is None or self.frame is None:return False
        from .element_rules import validate_rules, install_rules
        try:rules = validate_rules(values)
        except (ValueError, TypeError) as exc:
            QMessageBox.warning(self, 'Invalid element-pair rules', str(exc));return False
        snapshots = [(locator, deepcopy(frame.info.get('element_pair_rules')), frame.info.get('pair_rules_only'),
                      frame.bond_snapshot, frame.periodic_bond_snapshot)
                     for locator, frame in self._rule_targets(self.doc, self.current_doc)]
        self.undo_stack.append(('pair_rules', self.current_doc, deepcopy(self.render_options.element_pair_rules),
                                self.render_options.pair_rules_only, snapshots, self.doc.modified,
                                self.frame_index, self._active_vibration, list(self.selection)))
        self.render_options.element_pair_rules = rules;self.render_options.pair_rules_only = bool(only)
        for _, frame in self._rule_targets(self.doc, self.current_doc):
            install_rules(frame, rules, only);frame.bond_snapshot = frame.periodic_bond_snapshot = None
        self.doc.modified = True
        self.crystal_panel.rules.set_values(rules, only);self.refresh_scene()
        self.statusBar().showMessage(f'Applied {len(rules)} rules and rebuilt ordinary bonds in {len(self.doc.frames)} frame(s); manual overrides retained. Ctrl+Z to restore.', 7000)
        return True

    def _undo_element_pair_rules(self, item):
        _, index, rules, only, snapshots, modified, frame_index, vibration, selected = item
        document = self.documents[index]
        state = self._document_views.get(id(document))
        options = self.render_options if self.doc is document else state.options
        options.element_pair_rules = rules;options.pair_rules_only = only
        for (kind, number), old_rules, old_only, bonds, periodic in snapshots:
            if kind == 'frame':frame = document.frames[number]
            elif kind == 'vibration':frame = document.vibrations[number].reference
            else:frame = self._vibration_references.get((index, number))
            if frame is None:continue
            for key, value in (('element_pair_rules', old_rules), ('pair_rules_only', old_only)):
                if value is None:frame.info.pop(key, None)
                else:frame.info[key] = deepcopy(value)
            frame.bond_snapshot = bonds;frame.periodic_bond_snapshot = periodic
        document.modified = modified
        if vibration is not None:self.select_vibration(*vibration, autoplay=False)
        else:self.change_frame(frame_index, switch_doc=index)
        self.selection = selected;self._sync_selection_to_table()
        self.crystal_panel.rules.set_values(rules, only);self.refresh_scene()
