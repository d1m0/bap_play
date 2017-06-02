from bap import disasm
from bap.adt import Visitor, visit
from ..util import flatten
from z3 import If, eq, Const, And, BitVecRef, ArrayRef, BitVecNumRef, \
        BitVecVal, BitVecSort, Context
from re import compile


def boolToBV(boolExp, ctx):
    return If(boolExp, BitVecVal(1, 1, ctx=ctx), BitVecVal(0, 1, ctx=ctx),
              ctx=ctx)


def bvToBool(bvExp, ctx):
    assert eq(bvExp.sort(), BitVecSort(1, ctx=ctx))
    return bvExp == BitVecVal(1, 1, ctx)


def bitsToBil(bits, target='x86-64'):
    return flatten([x.bil for x in disasm(bits.toBinStr(), arch=target)])


class Stack(list):
    def push(self, arg):
        return self.append(arg)


def z3Ids(z3Term):
    if len(z3Term.children()) == 0:
            if (isinstance(z3Term, BitVecRef) or
               isinstance(z3Term, ArrayRef)) and \
               not isinstance(z3Term, BitVecNumRef):
                return set([(z3Term.decl().name(), z3Term.sort())])
            else:
                return set()
    else:
        return reduce(lambda acc, el:    acc.union(z3Ids(el)),
                      z3Term.children(),
                      set())


ssaRE = compile("(.*)\.([0-9]*)")
initialRE = compile("(.*)\.initial*")
unknownRE = compile("unknown_[0-9]*")


def unssa(name):
    m = ssaRE.match(name)
    assert m
    return (m.groups()[0], int(m.groups()[1]))


def isInitial(name):
    return initialRE.match(name) is not None


def isUnknown(name):
    return unknownRE.match(name) is not None


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
    def __init__(self, parents, **kwArgs):
        StmtNode.__init__(self, parents)
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
        self.mNodeMap = {}
        self.mCtx = ctx

        initialState = {name: Const(name + ".initial", sort)
                        for name, sort in self.arch_state()}
        self.mRoot = StmtDef([], **initialState)
        self.mScope = self.mRoot
        self.mNodeMap = {self.mScope.mId: self.mScope}
        self.mNumUnknowns = 0

    def getFreshUnknown(self, typ):
        newUnknown = "unknown_" + str(self.mNumUnknowns)
        z3Unknown = Const(newUnknown, typ)
        self.mScope.mDef[newUnknown] = z3Unknown
        self.mScope.mSort[newUnknown] = typ

        self.mNumUnknowns += 1
        return z3Unknown

    def pushScope(self, **kwArgs):
        if (len(kwArgs) == 0):
            raise TypeError("Can't push a scope unless we modify some vars")

        self.mScope = StmtDef([self.mScope], **kwArgs)
        self.mNodeMap[self.mScope.mId] = self.mScope

    def pushBranchScope(self, prefix, cond, fromScope):
        self.mScope = StmtBranch(fromScope, cond, prefix)
        self.mNodeMap[self.mScope.mId] = self.mScope

    def pushJoinScope(self, left, right, split):
        self.mScope = StmtJoin([left, right], split)
        self.mNodeMap[self.mScope.mId] = self.mScope

    def popScope(self):
        # Can only pop Def scopes (related to Let exprs)
        assert len(self.mScope.mParents) == 1 and\
            isinstance(self.mScope, StmtDef)
        res = self.mScope

        self.mScope = self.mScope.mParents[0]
        return res

    def lookupNode(self, id):
        try:
            return self.mNodeMap[id]
        except KeyError, e:
            print self.mNodeMap
            raise e

    def lookup(self, name):
        defNode = self.mScope.lookupDef(name)
        if (defNode):
            return (defNode.ssa(name), defNode.mSort[name])
        else:
            return (name, None)

    def scopeMarker(self):
        return self.mScope

    def extract_one(self, node, name, sort, emitted):
        if (node, name) in emitted:
            return []

        ssaName = node.ssa(name)
        defn = node.mDef[name]
        ctx = self.mCtx
        asserts = []
        if (isinstance(defn, set)):
            asserts.extend(reduce(
                    lambda acc, nd:  acc + self.extract_one(nd, name, sort,
                                                            emitted),
                    defn, []))

            baseDef = [x for x in defn if len(x.cond(self.mRoot)) == 0]
            assert len(baseDef) == 1
            baseDef = baseDef[0]
            otherDefs = filter(lambda x:    x != baseDef, defn)
            z3Val = reduce(
                    lambda exp, d: If(And(*(d.cond(self.mRoot) + [ctx])),
                                      Const(d.ssa(name), sort),
                                      exp),
                    otherDefs,
                    Const(baseDef.ssa(name), sort))
        else:
            for (id, idSort) in z3Ids(defn):
                if isInitial(id) or isUnknown(id):
                    # Initial values and unknowns are not defined in
                    # any scope
                    continue

                unssaName, ssaId = unssa(id)
                defnNode = self.lookupNode(ssaId)
                asserts.extend(self.extract_one(defnNode,
                                                unssaName, idSort, emitted))
            z3Val = defn

        asserts.append(Const(ssaName, sort) == z3Val)
        emitted.add((node, name))
        return asserts

    def extract(self):
        asserts = []
        emitted = set()
        for (name, sort) in self.arch_state():
            asserts.extend(self.extract_one(self.mScope.lookupDef(name),
                                            name, sort, emitted))

        return asserts

    def arch_state(self):
        raise Exception("Abstract")


def embed(bil, visitor_class):
    visitor = visitor_class(Context())
    visit(visitor, bil)
    assert len(visitor.mStack) == 0
    return visitor.extract()
