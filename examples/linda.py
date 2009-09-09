"""
a simplistic linda implementation
"""

import greenhouse


__all__ = ["ANY", "in_", "out", "rd", "eval"]

# indexes, length groups, counts
tuplespace = ({}, {}, {})

ANY = object()

def _findall(tup):
    tuples = tuplespace[1].get(len(tup), set()).copy()
    if not tuples:
        return set()
    ind = tuplespace[0].get(len(tup), {})
    for i, arg in enumerate(tup):
        if arg is ANY:
            continue
        tuples.intersection_update(ind.get(i, {}).get(arg, ()))
        if not tuples:
            return set()
    return tuples

def rd(tup):
    tuples = _findall(tup)
    if tuples:
        return iter(tuples).next()
    return None

def _rem(tup):
    tuplespace[2][tup] -= 1
    if not tuplespace[2][tup]:
        tuplespace[1][len(tup)].remove(tup)
        ind = tuplespace[0][len(tup)]
        for i, item in enumerate(tup):
            ind[i][item].remove(tup)
        del tuplespace[2][tup]

def in_(tup):
    tuples = _findall(tup)
    if not tuples:
        return None
    tup = iter(tuples).next()
    _rem(tup)
    return tup

def out(tup):
    tuplespace[2].setdefault(tup, 0)
    if not tuplespace[2][tup]:
        tuplespace[1].setdefault(len(tup), set()).add(tup)
        ind = tuplespace[0].setdefault(len(tup), {})
        for i, item in enumerate(tup):
            ind.setdefault(i, {}).setdefault(item, set()).add(tup)
    tuplespace[2][tup] += 1

def eval(tup, func):
    tuples = tuplespace[1].get(len(tup), set()).copy()
    if not tuples:
        return
    ind = tuplespace[0].get(len(tup), {})
    for i, arg in enumerate(tup):
        if arg is ANY:
            continue
        tuples.intersection_update(ind.get(i, {}).get(arg, ()))
        if not tuples:
            return
    for tup in tuples:
        greenhouse.schedule(func, (tup,))
