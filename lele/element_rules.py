"""Element-pair search rules. Importing defaults does not load the backend.

Ordinary bonds match in both directions; polyhedron rules are center->ligand.
The most specific matching row wins, with the last row breaking ties.
"""
from copy import deepcopy
from math import isfinite


def default_rule():
    return dict(enabled=True, a1='Ti', a2='O', minimum=0., maximum=2.5,
                bonds=True, polyhedra=True)


def validate_rules(values):
    from ase.data import atomic_numbers
    result = []
    for value in values:
        rule = {**default_rule(), **value}
        for key in ('a1', 'a2'):
            rule[key] = str(rule[key]).strip()
            if rule[key] != '*' and rule[key] not in atomic_numbers:
                raise ValueError('Each element must be a chemical symbol or *.')
        for key in ('minimum', 'maximum'):
            rule[key] = float(rule[key])
        if not all(isfinite(rule[k]) for k in ('minimum', 'maximum')) or not 0 <= rule['minimum'] < rule['maximum'] <= 20:
            raise ValueError('Use 0 ≤ minimum < maximum ≤ 20 Å for each rule.')
        for key in ('enabled', 'bonds', 'polyhedra'):rule[key] = bool(rule[key])
        result.append({key:rule[key] for key in default_rule()})
    return result


def matching_rule(rules, first, second, *, polyhedra=False):
    best = None;score = -1
    for row in rules:
        if not row['enabled']:continue
        a, b = row['a1'], row['a2']
        forward = a in ('*', first) and b in ('*', second)
        reverse = not polyhedra and a in ('*', second) and b in ('*', first)
        rank = int(a != '*')+int(b != '*')
        if (forward or reverse) and rank >= score:best, score = row, rank
    return best


def pair_decision(rules, first, second, distance, default, *, only=False, polyhedra=False):
    row = matching_rule(rules, first, second, polyhedra=polyhedra)
    if row is None:return bool(default and not only), False
    enabled = row['polyhedra' if polyhedra else 'bonds']
    return bool(enabled and distance > 1.e-7 and row['minimum']-1.e-8 <= distance <= row['maximum']+1.e-8), True


def search_radius(rules, default, *, only=False, polyhedra=False):
    key = 'polyhedra' if polyhedra else 'bonds'
    values = [row['maximum'] for row in rules if row['enabled'] and row[key]]
    return max(([0.] if only else [default])+values)


def rule_signature(rules, only=False):
    return bool(only), tuple(tuple(row[key] for key in default_rule()) for row in rules)


def frame_rules(frame):
    return frame.info.get('element_pair_rules', []), bool(frame.info.get('pair_rules_only', False))


def install_rules(frame, rules, only=False):
    frame.info['element_pair_rules'] = deepcopy(rules)
    frame.info['pair_rules_only'] = bool(only)
