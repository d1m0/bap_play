from bap import disasm
from bap.adt import Visitor
from ..util import flatten
from z3 import If, BitVec, eq, Const, And


def boolToBV(boolExp, ctx):
    return If(boolExp, BitVec(1, 1, ctx=ctx), BitVec(0, 1, ctx=ctx), ctx=ctx)


def bitsToBil(bits, target='x86-64'):
    return flatten([x.bil for x in disasm(bits.toBinStr(), arch=target)])


def neverSeen(adt):
    assert False, "Never seen " + adt.constr


class Stack(list):
    def push(self, arg):
        return self.append(arg)


class StmtNode:
    sId = 0

    def __init__(self, parents):
        self.mDef = {}
        self.mSort = {}
        self.mPrefix = ""
        self.mCond = []
        # Assert simpler tree structures - only 2-way branch/join from ifs
        assert (len(parents) <= 2)
        self.mParents = parents
        self.mSplitSrc = None
        self.mId = StmtNode.sId
        StmtNode.sId += 1

    def lookupDef(self, name, cache=False):
        if name in self.mDef:
            return self
        elif len(self.mParents) == 1:
            return self.mParents[0].lookupDef(name)
        elif len(self.mParents) > 1:
            defs = set([x.lookupDef(name) for x in self.mParents])
            if (len(defs) == 1):
                # If all agree it hasn't been modified in some branch
                return list(defs)[0]
            else:
                # name has been defined independently in different branches.
                # Need a phi def here
                # Make sure all definitions have the same sort
                s = list(defs)[0].mSort[name]
                for d in defs:
                    assert eq(s, d.mSort[name])

                self.mDef[name] = defs
                self.mSort[name] = s
                return self
        else:
            return None

    def cond(self, other):
        if (self == other):
            return []
        elif (len(self.mParents) == 1):
            c = self.mParents[0].cond(other)
        elif (len(self.mParents) > 1):
            c = self.mSplitSrc.cond(other)
        else:
            assert False, str(other) + " doesn't dominate " + str(self)

        return c + self.mCond

    def prefix(self):
        if len(self.mParents) == 1:
            return self.mParents[0].prefix() + self.mPrefix
        elif len(self.mParents) > 1:
            return self.mSplitSrc.prefix() + self.mPrefix
        else:
            return self.mPrefix

    def ssa(self, name):
        return name + self.prefix() + "." + str(self.mId)


class StmtDef(StmtNode):
    def __init__(self, parent, **kwArgs):
        StmtNode.__init__(self, [parent])
        self.mDef = kwArgs
        self.mSort = {k: v.sort() for (k, v) in kwArgs.iteritems()}


class StmtBranch(StmtNode):
    def __init__(self, parent, cond, prefix):
        StmtNode.__init__(self, [parent])
        self.mCond = [cond]
        self.mPrefix = prefix


class StmtJoin(StmtNode):
    def __init__(self, parents, splitSrc):
        StmtNode.__init__(self, parents)
        self.mSplitSrc = splitSrc


class Z3Embedder(Visitor):
    """ Z3 BIL Visitor. Entry points correpsond to
        the ADTs defined in the bap.bil module
    """
    def __init__(self, ctx):
        Visitor.__init__(self)
        self.mStack = Stack()
        self.mRoot = StmtNode([])
        self.mScope = self.mRoot
        self.mCtx = ctx

    def pushScope(self, **kwArgs):
        if (len(kwArgs) == 0):
            raise TypeError("Can't push a scope unless we modify some vars")

        self.mScope = StmtDef(self.mScope, **kwArgs)

    def pushBranchScope(self, prefix, cond, fromScope):
        self.mScope = StmtBranch(fromScope, cond, prefix)

    def pushJoinScope(self, left, right, split):
        self.mScope = StmtJoin([left, right], split)

    def popScope(self):
        # Can only pop Def scopes (related to Let exprs)
        assert len(self.mScope.mParents) == 1 and\
            isinstance(self.mScope, StmtDef)
        res = self.mScope
        self.mScope = self.mScope.mParents[0]
        return res

    def lookup(self, name):
        defNode = self.mScope.lookupDef(name)
        if (defNode):
            return (defNode.ssa(name), defNode.mSort[name])
        else:
            return (name, None)

    def scopeMarker(self):
        return self.mScope

    def extract(self, node=None, visited={}):
        if (node is None):
            node = self.mScope

        if (node in visited):
            return []
        else:
            visited[node] = True

        z3Asserts = []
        for n in node.mParents:
            z3Asserts.extend(self.extract(n))

        ctx = self.mCtx

        for name in node.mDef:
            z3Sort = node.mSort[name]
            ssaName = node.ssa(name)
            if (isinstance(node.mDef[name], set)):
                defs = node.mDef[name]
                assert len(defs) > 1

                # There is at least 1 unconditional definition (initial state)
                # This is the base case of the fold
                baseDef = [x for x in defs if len(x.cond(self.mRoot)) == 0]
                assert len(baseDef) == 1
                baseDef = baseDef[0]
                otherDefs = filter(lambda x:    x != baseDef, defs)

                z3Val = reduce(
                    lambda acc, el:  If(And(*(el.cond(self.mRoot) + [ctx])),
                                        Const(el.ssa(name), z3Sort),
                                        acc),
                    otherDefs,
                    baseDef.mDef[name])
            else:
                z3Val = node.mDef[name]

            assertExp = Const(ssaName, z3Sort) == z3Val
            z3Asserts.append(assertExp)

        return z3Asserts
