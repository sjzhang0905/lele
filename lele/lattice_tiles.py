"""Integer replica ranges shared by boundary display and real supercells."""
from itertools import product


def axis_tiles(count, growth='alternating'):
    if growth not in ('alternating', 'forward'):
        raise ValueError('Unknown cell growth mode.')
    if growth == 'forward':
        return tuple(range(count))
    return tuple(0 if i == 0 else ((i+1)//2 if i % 2 else -i//2)
                 for i in range(count))


def repeat_tiles(repeats, growth='alternating'):
    return tuple(product(*(axis_tiles(n, growth) for n in repeats)))


def repeat_bounds(repeats, growth='alternating'):
    return tuple((min(values), max(values)+1)
                 for values in (axis_tiles(n, growth) for n in repeats))


def ordered_range(low, high):
    """Zero first, then positive/negative pairs, restricted to the given range."""
    return tuple(sorted(range(low, high), key=lambda value: (abs(value), value < 0)))
