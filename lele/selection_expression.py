"""A safe, explicitly documented subset of VMD-style atom selection syntax.

All atom identities are current source rows. No Python evaluation is used.
Distance predicates use the nearest atom in one immutable selection snapshot.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
import re


MAX_EXPRESSION_CHARS = 8192
MAX_TOKENS = 512
MAX_NESTING = 32
DISTANCE_PAIR_BLOCK = 8192  # Maximum periodic pair vectors passed to ASE at once.

SELECTION_EXPRESSION_HELP = """Atom selection expressions

Enter an expression in Atoms selection and press Enter or Apply expression.
This is a supported subset of VMD-style syntax, not the complete VMD language.
Expression selection replaces the current selection. The index-entry rows below
remain an independent selection method and are not combined with the expression.

Examples
  element O
  element C H
  element O and within 3.5 of selected
  element H and distance > 2 and distance < 5
  not selected and within 3 of selected
  (element O or element N) and not index 1-4
  index 1, 3-8
  index >= 5 and index < 11
  all
  none

Syntax
  all / none / selected
  element O              element O H       element O, H
  index 1, 3-8           index 3 to 8       index >= 5
  within 3.5 of selected
  distance < 3.5         distance >= 2      distance != 0
  and / or / not, with parentheses

Keywords and element symbols are case-insensitive. Precedence is not, then and,
then or. Comparisons support <, <=, >, >=, =, == and !=. Indices must be integers.
index starts at 1. These are global source-atom numbers, not
per-element ordinals. Ranges are inclusive and must ascend.

Distances are in Å and refer to the nearest atom selected when Apply is pressed,
not the selection produced during evaluation. A distance predicate requires at
least one reference atom. Reference atoms have distance zero. 'within R' means
distance <= R, so it includes selected atoms unless 'not selected' is added.
Periodic structures use the nearest periodic image along their enabled axes,
including skew cells. Nonperiodic structures use Cartesian Euclidean distance.
Element filters include any positive-occupancy component of a mixed atomic site;
the shared site is selected only once.

Empty expressions, invalid syntax, out-of-range indices and cancelled operations
leave the current selection unchanged. Enter 'none' to clear it. Ctrl+Z undoes a
successful selection change. Scripts, functions, wildcards and arbitrary VMD
commands are not executed.
"""

_TOKEN = re.compile(r'\s*(?:(<=|>=|==|!=|[<>=(),-])|([0-9]+(?:\.[0-9]*)?(?:[eE][+-]?[0-9]+)?|\.[0-9]+(?:[eE][+-]?[0-9]+)?)|([A-Za-z_]+))')
_COMPARISONS = frozenset(('<', '<=', '>', '>=', '=', '==', '!='))
_STOPS = frozenset(('and', 'or', ')'))


@dataclass(frozen=True)
class Token:
    value: str
    position: int


def _tokens(text):
    if len(text) > MAX_EXPRESSION_CHARS:
        raise ValueError(f'Expression is too long (maximum {MAX_EXPRESSION_CHARS} characters).')
    result = []
    offset = 0
    while offset < len(text):
        if not text[offset:].strip():
            break
        match = _TOKEN.match(text, offset)
        if match is None:
            raise ValueError(f'Unexpected character at position {offset + 1}.')
        value = next(group for group in match.groups() if group is not None)
        result.append(Token(value, match.end() - len(value)))
        if len(result) > MAX_TOKENS:
            raise ValueError(f'Expression has too many terms (maximum {MAX_TOKENS} tokens).')
        offset = match.end()
    return result


class _Parser:
    def __init__(self, text, count):
        self.tokens = _tokens(str(text))
        self.cursor = 0
        self.count = count
        self.needs_reference = False

    def peek(self):
        return self.tokens[self.cursor].value.lower() if self.cursor < len(self.tokens) else ''

    def error(self, message):
        position = self.tokens[self.cursor].position + 1 if self.cursor < len(self.tokens) else None
        raise ValueError(message + (f' (position {position})' if position is not None else ''))

    def pop(self):
        if self.cursor >= len(self.tokens):
            self.error('Unexpected end of expression.')
        token = self.tokens[self.cursor].value
        self.cursor += 1
        return token

    def expect(self, value):
        if self.peek() != value:
            self.error(f"Expected '{value}'.")
        self.cursor += 1

    def parse(self):
        if not self.tokens:
            self.error("Enter an expression; use 'none' to clear the selection.")
        result = self.expression(0)
        if self.peek():
            self.error(f"Unexpected token '{self.peek()}'; use and/or between predicates.")
        return result

    def expression(self, depth):
        left = self.conjunction(depth)
        while self.peek() == 'or':
            self.pop();left = ('or', left, self.conjunction(depth))
        return left

    def conjunction(self, depth):
        left = self.unary(depth)
        while self.peek() == 'and':
            self.pop();left = ('and', left, self.unary(depth))
        return left

    def unary(self, depth):
        if depth > MAX_NESTING:
            self.error(f'Expression is nested too deeply (maximum {MAX_NESTING}).')
        if self.peek() == 'not':
            self.pop();return ('not', self.unary(depth + 1))
        if self.peek() == '(':
            self.pop();node = self.expression(depth + 1);self.expect(')');return node
        return self.predicate()

    def number(self, *, integer=False):
        token = self.pop()
        try:
            if integer and (not token.isascii() or not token.isdigit()):
                raise ValueError()
            value = int(token) if integer else float(token)
            if not math.isfinite(value) or value < 0:
                raise ValueError()
        except (ValueError, OverflowError):
            self.error('Expected a nonnegative integer.' if integer else 'Expected a finite, nonnegative distance in Å.')
        return value

    def predicate(self):
        word = self.pop().lower()
        if word in ('all', 'none', 'selected'):
            return (word,)
        if word == 'element':
            from .chemical_analysis import ATOMIC_NUMBERS
            allowed = set(ATOMIC_NUMBERS) | {'D', 'T'}
            symbols = []
            while self.peek() and self.peek() not in _STOPS:
                if self.peek() == ',':
                    if not symbols:
                        self.error('An element symbol must precede a comma.')
                    self.pop()
                    if not self.peek() or self.peek() in _STOPS or self.peek() == ',':
                        self.error('An element symbol must follow a comma.')
                symbol = self.pop().capitalize()
                if symbol not in allowed:
                    self.error(f"Unknown element '{symbol}'. Use symbols such as C, O or Fe.")
                symbols.append(symbol)
            if not symbols:
                self.error('Specify at least one element, for example element O.')
            return ('element', frozenset(symbols))
        if word == 'index':
            base = 1
            if self.peek() in _COMPARISONS:
                operator = self.pop();value = self.number(integer=True)
                return ('index_compare', base, operator, value)
            ranges = []
            while self.peek() and self.peek() not in _STOPS:
                if self.peek() == ',':
                    if not ranges:
                        self.error('An index must precede a comma.')
                    self.pop()
                    if not self.peek() or self.peek() in _STOPS or self.peek() == ',':
                        self.error('An index must follow a comma.')
                first = self.number(integer=True)
                last = first
                if self.peek() in ('-', 'to'):
                    self.pop();last = self.number(integer=True)
                if not base <= first <= last < self.count + base:
                    self.error(f'{word} ranges must ascend and stay between {base} and {self.count + base - 1}.')
                ranges.append((first - base, last - base + 1))
            if not ranges:
                self.error(f'Specify {word} numbers or a comparison.')
            return ('index_ranges', tuple(ranges))
        if word == 'within':
            value = self.number();self.expect('of');self.expect('selected')
            self.needs_reference = True
            return ('distance', '<=', value)
        if word == 'distance':
            if self.peek() not in _COMPARISONS:
                self.error('Use a distance comparison, for example distance < 3.5.')
            operator = self.pop();value = self.number()
            self.needs_reference = True
            return ('distance', operator, value)
        self.error(f"Unknown selection keyword '{word}'. See Selection expression syntax in Help.")


def _compare(values, operator, limit):
    if operator == '<':return values < limit
    if operator == '<=':return values <= limit
    if operator == '>':return values > limit
    if operator == '>=':return values >= limit
    if operator in ('=', '=='):return values == limit
    return values != limit


class _Evaluator:
    def __init__(self, frame, selected, checkpoint, progress):
        import numpy as np
        self.frame = frame
        self.count = len(frame.symbols)
        self.selected = np.asarray(selected, dtype=int)
        self.reference_mask = np.zeros(self.count, dtype=bool)
        self.reference_mask[self.selected] = True
        self.distances = np.full(self.count, np.nan)
        self.distances[self.selected] = 0.
        self.checkpoint = checkpoint
        self.progress = progress
        self.tree = None
        self._periodic = None

    def nearest_distances(self, indices):
        import numpy as np
        pending = indices[np.isnan(self.distances[indices])]
        if not len(pending):
            return self.distances[indices]
        frame = self.frame
        if not any(frame.pbc):
            from scipy.spatial import cKDTree
            if self.tree is None:
                self.tree = cKDTree(frame.positions[self.selected])
            for start in range(0, len(pending), 8192):
                self.checkpoint()
                chunk = pending[start:start + 8192]
                self.distances[chunk] = self.tree.query(frame.positions[chunk], k=1)[0]
                self.progress('Selecting atoms by distance', min(start + len(chunk), len(pending)), len(pending))
            return self.distances[indices]
        from .periodic_geometry import periodic_basis, _reduced_cell
        from ase.geometry import find_mic
        if self._periodic is None:
            cell = periodic_basis(frame)
            if cell is None:
                raise ValueError('Periodic distance selection requires a nondegenerate cell.')
            reduced, _ = _reduced_cell(tuple(cell.ravel()), tuple(frame.pbc))
            periodic = reduced[np.asarray(frame.pbc, dtype=bool)]
            projector = None if all(frame.pbc) else np.linalg.pinv(periodic) @ periodic
            self._periodic = reduced, projector
        reduced, projector = self._periodic
        references = frame.positions[self.selected]
        target_block = min(128, DISTANCE_PAIR_BLOCK)
        reference_block = max(1, DISTANCE_PAIR_BLOCK // target_block)
        for start in range(0, len(pending), target_block):
            chunk = pending[start:start + target_block]
            positions = frame.positions[chunk]
            nearest = np.full(len(chunk), np.inf)
            for offset in range(0, len(references), reference_block):
                self.checkpoint()
                other = references[offset:offset + reference_block]
                vectors = (positions[:, None, :] - other[None, :, :]).reshape(-1, 3)
                search = vectors if projector is None else vectors @ projector
                image, length = find_mic(search, reduced, pbc=frame.pbc)
                if projector is not None:
                    length = np.linalg.norm(vectors - search + image, axis=1)
                nearest = np.minimum(nearest, np.asarray(length).reshape(len(chunk), len(other)).min(axis=1))
            self.distances[chunk] = nearest
            self.progress('Selecting atoms by periodic distance', min(start + len(chunk), len(pending)), len(pending))
        return self.distances[indices]

    def evaluate(self, node, candidates):
        import numpy as np
        self.checkpoint()
        kind = node[0]
        if kind == 'and':
            return self.evaluate(node[2], self.evaluate(node[1], candidates))
        if kind == 'or':
            left = self.evaluate(node[1], candidates)
            return left | self.evaluate(node[2], candidates & ~left)
        if kind == 'not':
            return candidates & ~self.evaluate(node[1], candidates)
        if kind == 'all':return candidates.copy()
        if kind == 'none':return np.zeros(self.count, dtype=bool)
        if kind == 'selected':return candidates & self.reference_mask
        indices = np.flatnonzero(candidates)
        result = np.zeros(self.count, dtype=bool)
        if kind == 'element':
            sites = self.frame.info.get('site_occupancies')
            if sites is None:
                for position, index in enumerate(indices):
                    if position % 4096 == 0:self.checkpoint()
                    result[index] = self.frame.symbols[index] in node[1]
            else:
                for position, index in enumerate(indices):
                    if position % 4096 == 0:self.checkpoint()
                    result[index] = any(symbol in node[1] and occupancy > 0 for symbol, occupancy in sites[index].items())
        elif kind == 'index_ranges':
            for first, end in node[1]:result[first:end] = True
            result &= candidates
        elif kind == 'index_compare':
            result[indices] = _compare(indices + node[1], node[2], node[3])
        elif kind == 'distance':
            result[indices] = _compare(self.nearest_distances(indices), node[1], node[2])
        return result


def evaluate_selection_expression(frame, text, selected=(), *, cancelled=None, progress=None):
    """Return source indices; validate all syntax before evaluating any predicate.

    No frame or selection is modified. Nonperiodic nearest-distance queries use
    a KD tree; periodic pair processing is capped at DISTANCE_PAIR_BLOCK vectors.
    """
    import numpy as np
    from operator import index as integer_index
    from .output_text import LoadCancelled, check_load_cancelled, load_progress
    if frame is None:
        raise ValueError('Open a structure before selecting atoms.')
    count = len(frame.symbols)
    parser = _Parser(text, count)
    syntax = parser.parse()
    try:
        references = tuple(sorted({integer_index(i) for i in selected}))
    except TypeError:
        raise ValueError('The reference selection contains invalid atom indices.') from None
    if any(i < 0 or i >= count for i in references):
        raise ValueError('The reference selection contains an atom outside the current structure.')
    if parser.needs_reference and not references:
        raise ValueError('Select at least one reference atom before using distance or within.')
    if np.asarray(frame.positions).shape != (count, 3) or not np.isfinite(frame.positions).all():
        raise ValueError('The structure has invalid Cartesian coordinates.')
    def checkpoint():
        check_load_cancelled()
        if cancelled is not None and cancelled():
            raise LoadCancelled()
    reporters = {}
    def report(label, value, total):
        checkpoint()
        if progress is not None:
            progress(label, value, total)
        else:
            key = label, total
            if key not in reporters:reporters[key] = load_progress(label, total)
            reporters[key](value)
    evaluator = _Evaluator(frame, references, checkpoint, report)
    result = evaluator.evaluate(syntax, np.ones(count, dtype=bool))
    checkpoint()
    return np.flatnonzero(result).tolist()
