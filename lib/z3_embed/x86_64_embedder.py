from bap.bil import Exp, LittleEndian
from bap.adt import visit
from z3 import BitVecVal, BitVecSort, Context, ArraySort, eq, Array,\
    Select, Concat
from .null_embedder import NullZ3Embedder
from .embedder import neverSeen


class X86_64Z3Embedder(NullZ3Embedder):
    """ Z3 BIL Visitor. Entry points correpsond to
        the ADTs defined in the bap.bil module
    """
    def __init__(self, ctx):
        NullZ3Embedder.__init__(self, ctx)
        addr_size = 64
        val_size = 8
        self.defs["mem64.0"] = Array("mem64",
                                     BitVecSort(addr_size, ctx=ctx),
                                     BitVecSort(val_size, ctx=ctx))

    # Types
    def leave_Imm(self, typ):
        assert isinstance(typ.arg, int)
        ctx = self.mCtx
        self.mStack.push(BitVecSort(typ.arg, ctx=ctx))

    def leave_Mem(self, typ):
        addr_size, value_size = typ.arg
        ctx = self.mCtx
        self.mStack.push(ArraySort(BitVecSort(addr_size, ctx=ctx),
                                   BitVecSort(value_size, ctx=ctx)))

    def leave_Int(self, expr):
        val, size = expr.arg
        self.mStack.push(BitVecVal(val, size, self.mCtx))

    def leave_Var(self, expr):
        name, typ = expr.arg
        z3Name = self.lookup(name)
        z3Sort = self.mStack.pop()
        assert z3Name in self.defs
        assert eq(self.defs[z3Name].sort(), z3Sort)
        self.mStack.push(self.defs[z3Name])

    # Expressions
    #   Ternary Ops
    def visit_Let(self, expr):
        var, val, expr = expr.arg

        # Evaluate val in the current scope
        self.run(val)
        z3Val = self.mStack.pop()
        # Push the new scope and define var=z3val
        self.pushScope(var, z3Val)
        # Evaluate expr in the new scope
        self.run(expr)
        z3Expr = self.mStack.pop()
        # Pop the let scope
        self.popScope()

        self.mStack.push(z3Expr)

    #   Binary Ops
    def leave_PLUS(self, expr):
        rhs = self.mStack.pop()
        lhs = self.mStack.pop()
        self.mStack.push(lhs + rhs)

    #   Unary Ops
    def leave_NEG(self, expr):
        assert isinstance(expr.arg, Exp)
        expr = self.mStack.pop()
        self.mStack.push(-expr)

    #   Casts Ops

    #   Mem Ops
    def leave_Load(self, expr):
        memVar, off, endianness, size = expr.arg
        # We didn't push anything for endianness. Assume little endian
        off = self.mStack.pop()
        memV = self.mStack.pop()

        assert isinstance(endianness, LittleEndian)
        assert size % 8 == 0 and \
            memV.sort().domain().size() % 8 == 0 and \
            size >= memV.sort().domain().size()

        # Least signifficant first
        byts = [Select(memV, off + idx) for idx in range(0, size/8)]
        self.mStack.push(Concat(*reversed(byts)))  # Select expects lsb last

    def leave_Store(self, expr):
        memVar, off, value, endianness, size = expr.arg
        # We didn't push anything for endianness. Assume little endian
        value = self.mStack.pop()
        memV = self.mStack.pop()
        print memV, off, value, size
        # TODO: Store individual bytes into the right places
        neverSeen(expr)

    def leave_Jmp(self, stmt):
        assert isinstance(stmt.arg, Exp)
        dest = self.mStack.pop()
        self.pushScope(RIP=dest)
        # Doesn't return a value


def embed(bil):
    visitor = X86_64Z3Embedder(Context())
    visit(visitor, bil)
    assert len(visitor.mStack) == 0
    return visitor
