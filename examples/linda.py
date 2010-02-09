"""
a simplistic linda implementation

supports the four basic linda operations, changing the name of "in" to "in_"
to avoid the python reserved word. none of these operations block (they
shouldn't to be a faithful linda implementation), so one more function is
provided, "yield_". that will block the current linda process and allow other
scheduled processes to run.

in_ takes a tuple which may have values of ANY and finds a matching tuple from
the tuplespace, removes it, and returns it. if no match is found it returns
None.

rd takes a tuple which may have values of ANY and finds a matching tuple and
returns it, or None if no match was found. (it is in_ without the removal)

out takes a tuple (with no ANYs) and stores it in the tuple space

eval takes a tuple which may have ANYs, and a function, and for every tuple
matching the argument that is found schedules the function, passing that tuple
as the only argument
"""

import greenhouse


__all__ = ["ANY", "in_", "out", "rd", "eval", "yield_"]

# the main data structure for holding all the tuples has 3 dictionaries
# tuplespace[0] (indexes):
#   {length: {index: {value: [tuples]}}}
# tuplespace[1] (length groups):
#   {length: set(tuples)}
# tuplespace[2] (counts):
#   {tuple: counter}
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

def _findone(tup):
    # we find matching tuples by process of elimination via set intersection,
    # so to identify even one match we have to find them all anyway
    tuples = _findall(tup)
    return (tuples and (iter(tuples).next(),) or (None,))[0]

def rd(tup):
    tuple = _findone(tup)
    if tuple is None:
        return None
    return tuple

def _rem(tup):
    tuplespace[2][tup] -= 1
    if not tuplespace[2][tup]:
        tuplespace[1][len(tup)].remove(tup)
        ind = tuplespace[0][len(tup)]
        for i, item in enumerate(tup):
            ind[i][item].remove(tup)
        del tuplespace[2][tup]

def in_(tup):
    tuple = _findone(tup)
    if tuple is None:
        return None
    _rem(tuple)
    return tuple

def out(tup):
    tuplespace[2].setdefault(tup, 0)
    if not tuplespace[2][tup]:
        tuplespace[1].setdefault(len(tup), set()).add(tup)
        ind = tuplespace[0].setdefault(len(tup), {})
        for i, item in enumerate(tup):
            ind.setdefault(i, {}).setdefault(item, set()).add(tup)
    tuplespace[2][tup] += 1

def eval(tup, func):
    for tup in _findall(tup):
        greenhouse.schedule(func, args=(tup,))

yield_ = greenhouse.pause
