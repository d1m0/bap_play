from bap import disasm
from bap.adt import Visitor
from ..util import flatten
from copy import copy


def bitsToBil(bits, target='x86-64'):
    return flatten([x.bil for x in disasm(bits.toBinStr(), arch=target)])


def neverSeen(adt):
    print "Never seen: ", adt.constr, adt.arg
    assert False, "Never seen it"


class Stack(list):
    def push(self, arg):
        return self.append(arg)


class Env(dict):
    def __getitem__(self, name):
        try:
            return dict.__getitem__(self, name)
        except KeyError:
            return 0


class Z3Embedder(Visitor):
    """ Z3 BIL Visitor. Entry points correpsond to
        the ADTs defined in the bap.bil module
    """
    def __init__(self, ctx):
        Visitor.__init__(self)
        self.mStack = Stack()
        self.mScopeStack = [Env()]
        self.mCtx = ctx
        self.defs = {}

    def pushScope(self, **kwArgs):
        if (len(kwArgs) == 0):
            raise TypeError("Can't push a scope unless we modify some vars")

        newEnv = copy(self.mScopeStack[-1])
        self.mScopeStack.append(newEnv)

        for (var, val) in kwArgs.iteritems():
            if type(var) != str:
                raise TypeError("Var names should be string")
            newEnv[var] = newEnv[var] + 1
            self.defs[self.lookup(var)] = val

    def popScope(self):
        return self.mScopeStack.pop()

    def lookup(self, name):
        return name + "." + str(self.mScopeStack[-1][name])
