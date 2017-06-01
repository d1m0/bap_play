from bap.bil import Exp, LittleEndian, Stmt
from bap.adt import visit
from z3 import BitVecVal, BitVecSort, Context, ArraySort, eq, \
    Select, Concat, Const, Extract, ULE, ULT, LShR, Update, \
    ZeroExt, If, SignExt, UDiv, URem, Not
from .null_embedder import NullZ3Embedder
from .embedder import boolToBV, bvToBool


class X86_64Z3Embedder(NullZ3Embedder):
    """ X86_64 + AVX Embedder
    """
    def __init__(self, ctx):
        NullZ3Embedder.__init__(self, ctx)

    def arch_state(self):
        ctx = self.mCtx
        return [("mem64", ArraySort(BitVecSort(64, ctx=ctx),
                                    BitVecSort(8, ctx=ctx))),
                ("CF", BitVecSort(1, ctx=ctx)),
                ("AF", BitVecSort(1, ctx=ctx)),
                ("ZF", BitVecSort(1, ctx=ctx)),
                ("SF", BitVecSort(1, ctx=ctx)),
                ("OF", BitVecSort(1, ctx=ctx)),
                ("PF", BitVecSort(1, ctx=ctx)),
                ("DF", BitVecSort(1, ctx=ctx)),
                ("RAX", BitVecSort(64, ctx=ctx)),
                ("RBX", BitVecSort(64, ctx=ctx)),
                ("RCX", BitVecSort(64, ctx=ctx)),
                ("RDX", BitVecSort(64, ctx=ctx)),
                ("RSP", BitVecSort(64, ctx=ctx)),
                ("RBP", BitVecSort(64, ctx=ctx)),
                ("RSI", BitVecSort(64, ctx=ctx)),
                ("RDI", BitVecSort(64, ctx=ctx)),
                ("RIP", BitVecSort(64, ctx=ctx)),
                ("R8", BitVecSort(64, ctx=ctx)),
                ("R9", BitVecSort(64, ctx=ctx)),
                ("R10", BitVecSort(64, ctx=ctx)),
                ("R11", BitVecSort(64, ctx=ctx)),
                ("R12", BitVecSort(64, ctx=ctx)),
                ("R13", BitVecSort(64, ctx=ctx)),
                ("R14", BitVecSort(64, ctx=ctx)),
                ("R15", BitVecSort(64, ctx=ctx)),
                ("FS_BASE", BitVecSort(64, ctx=ctx)),
                ("GS_BASE", BitVecSort(64, ctx=ctx)),
                ("SS_BASE", BitVecSort(64, ctx=ctx)),
                ("DS_BASE", BitVecSort(64, ctx=ctx)),
                ("YMM0", BitVecSort(256, ctx=ctx)),
                ("YMM1", BitVecSort(256, ctx=ctx)),
                ("YMM2", BitVecSort(256, ctx=ctx)),
                ("YMM3", BitVecSort(256, ctx=ctx)),
                ("YMM4", BitVecSort(256, ctx=ctx)),
                ("YMM5", BitVecSort(256, ctx=ctx)),
                ("YMM6", BitVecSort(256, ctx=ctx)),
                ("YMM7", BitVecSort(256, ctx=ctx)),
                ("YMM8", BitVecSort(256, ctx=ctx)),
                ("YMM9", BitVecSort(256, ctx=ctx)),
                ("YMM10", BitVecSort(256, ctx=ctx)),
                ("YMM11", BitVecSort(256, ctx=ctx)),
                ("YMM12", BitVecSort(256, ctx=ctx)),
                ("YMM13", BitVecSort(256, ctx=ctx)),
                ("YMM14", BitVecSort(256, ctx=ctx)),
                ("YMM15", BitVecSort(256, ctx=ctx)),
                ("CPUEXN", BitVecSort(1, ctx=ctx))]

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
        z3Name, z3DefSort = self.lookup(name)
        z3ExpectedSort = self.mStack.pop()
        assert z3DefSort is not None, \
            "Lookup of undefined variable " + name
        assert z3DefSort == z3ExpectedSort
        self.mStack.push(Const(z3Name, z3DefSort))

    # Expressions
    #   Ternary Ops
    def visit_Let(self, expr):
        var, val, expr = expr.arg

        # Evaluate val in the current scope
        self.run(val)
        z3Val = self.mStack.pop()
        # Push the new scope and define var=z3val
        self.pushScope(**{var.name: z3Val})
        # Evaluate expr in the new scope
        self.run(expr)
        z3Expr = self.mStack.pop()
        # Pop the let scope
        self.popScope()
        self.mStack.push(z3Expr)

    def leave_Ite(self, expr):
        falseE = self.mStack.pop()
        trueE = self.mStack.pop()
        cond = self.mStack.pop()
        boolCond = bvToBool(cond, self.mCtx)
        self.mStack.push(If(boolCond, trueE, falseE, ctx=self.mCtx))

    #   Binary Ops
    def leave_PLUS(self, expr):
        rhs = self.mStack.pop()
        lhs = self.mStack.pop()
        self.mStack.push(lhs + rhs)

    def leave_MINUS(self, expr):
        rhs = self.mStack.pop()
        lhs = self.mStack.pop()
        self.mStack.push(lhs - rhs)

    def leave_TIMES(self, stmt):
        rhs = self.mStack.pop()
        lhs = self.mStack.pop()
        self.mStack.push(lhs * rhs)

    def leave_DIVIDE(self, stmt):
        rhs = self.mStack.pop()
        lhs = self.mStack.pop()
        self.mStack.push(UDiv(lhs, rhs))

    def leave_SDIVIDE(self, stmt):
        rhs = self.mStack.pop()
        lhs = self.mStack.pop()
        self.mStack.push(lhs / rhs)

    def leave_MOD(self, stmt):
        rhs = self.mStack.pop()
        lhs = self.mStack.pop()
        self.mStack.push(URem(lhs, rhs))

    def leave_SMOD(self, stmt):
        rhs = self.mStack.pop()
        lhs = self.mStack.pop()
        self.mStack.push(lhs % rhs)

    def leave_XOR(self, expr):
        rhs = self.mStack.pop()
        lhs = self.mStack.pop()
        self.mStack.push(lhs ^ rhs)

    def leave_AND(self, expr):
        rhs = self.mStack.pop()
        lhs = self.mStack.pop()
        self.mStack.push(lhs & rhs)

    def leave_OR(self, expr):
        rhs = self.mStack.pop()
        lhs = self.mStack.pop()
        self.mStack.push(lhs | rhs)

    # Z3 requires that lhs and rhs of
    # a shift be of the same size.
    @staticmethod
    def equalize(lhs, rhs):
        lhsSize = lhs.sort().size()
        rhsSize = rhs.sort().size()

        if (lhsSize < rhsSize):
            assert False, "NYI"
        elif (lhsSize > rhsSize):
            return (lhs, ZeroExt(lhsSize-rhsSize, rhs))
        else:
            return (lhs, rhs)

    def leave_RSHIFT(self, expr):
        rhs = self.mStack.pop()
        lhs = self.mStack.pop()
        lhs, rhs = X86_64Z3Embedder.equalize(lhs, rhs)
        self.mStack.push(LShR(lhs, rhs))

    def leave_LSHIFT(self, expr):
        rhs = self.mStack.pop()
        lhs = self.mStack.pop()
        lhs, rhs = X86_64Z3Embedder.equalize(lhs, rhs)
        self.mStack.push(lhs << rhs)

    def leave_ARSHIFT(self, expr):
        rhs = self.mStack.pop()
        lhs = self.mStack.pop()
        lhs, rhs = X86_64Z3Embedder.equalize(lhs, rhs)
        self.mStack.push(lhs >> rhs)

    #  Comparisons
    def leave_EQ(self, expr):
        rhs = self.mStack.pop()
        lhs = self.mStack.pop()
        boolCmp = lhs == rhs
        self.mStack.push(boolToBV(boolCmp, self.mCtx))

    def leave_NEQ(self, expr):
        rhs = self.mStack.pop()
        lhs = self.mStack.pop()
        boolCmp = lhs != rhs
        self.mStack.push(boolToBV(boolCmp, self.mCtx))

    def leave_LT(self, expr):
        rhs = self.mStack.pop()
        lhs = self.mStack.pop()
        boolCmp = ULT(lhs, rhs)
        self.mStack.push(boolToBV(boolCmp, self.mCtx))

    def leave_LE(self, expr):
        rhs = self.mStack.pop()
        lhs = self.mStack.pop()
        boolCmp = ULE(lhs, rhs)
        self.mStack.push(boolToBV(boolCmp, self.mCtx))

    def leave_SLT(self, expr):
        rhs = self.mStack.pop()
        lhs = self.mStack.pop()
        boolCmp = lhs < rhs  # < is signed in pyz3 by default
        self.mStack.push(boolToBV(boolCmp, self.mCtx))

    def leave_SLE(self, expr):
        rhs = self.mStack.pop()
        lhs = self.mStack.pop()
        boolCmp = lhs <= rhs  # <= is signed in pyz3 by default
        self.mStack.push(boolToBV(boolCmp, self.mCtx))

    def leave_Concat(self, expr):
        rhs = self.mStack.pop()
        lhs = self.mStack.pop()
        self.mStack.push(Concat(lhs, rhs))

    #   Unary Ops
    def leave_NEG(self, expr):
        assert isinstance(expr.arg, Exp)
        expr = self.mStack.pop()
        self.mStack.push(-expr)

    def leave_NOT(self, expr):
        assert isinstance(expr.arg, Exp)
        expr = self.mStack.pop()
        self.mStack.push(~expr)

    #   Casts Ops
    def leave_HIGH(self, expr):
        assert len(expr.arg) == 2 and\
            type(expr.arg[0]) == int and\
            isinstance(expr.arg[1], Exp)
        numBits = expr.arg[0]
        expr = self.mStack.pop()
        width = expr.sort().size()
        self.mStack.push(Extract(width-1, width-numBits, expr))

    def leave_LOW(self, expr):
        assert len(expr.arg) == 2 and\
            type(expr.arg[0]) == int and\
            isinstance(expr.arg[1], Exp)
        numBits = expr.arg[0]
        expr = self.mStack.pop()
        self.mStack.push(Extract(numBits-1, 0, expr))

    def leave_Extract(self, expr):
        hb, lb, _ = expr.arg
        expr = self.mStack.pop()
        self.mStack.push(Extract(hb, lb, expr))

    def leave_Unknown(self, expr):
        assert len(expr.arg) == 2
        typ = self.mStack.pop()
        self.mStack.push(self.getFreshUnknown(typ))

    def leave_UNSIGNED(self, expr):
        size, _ = expr.arg
        exp = self.mStack.pop()
        # TODO: Is this the correct z3 primitive?
        self.mStack.push(ZeroExt(size - exp.sort().size(), exp))

    def leave_SIGNED(self, expr):
        size, _ = expr.arg
        exp = self.mStack.pop()
        # TODO: Is this the correct z3 primitive?
        self.mStack.push(SignExt(size - exp.sort().size(), exp))

    #   Mem Ops
    def leave_Load(self, expr):
        memVar, off, endianness, size = expr.arg
        # We didn't push anything for endianness. Assume little endian
        off = self.mStack.pop()
        memV = self.mStack.pop()

        assert isinstance(endianness, LittleEndian)
        assert size % 8 == 0 and \
            memV.sort().range().size() % 8 == 0 and \
            size >= memV.sort().range().size() and \
            eq(off.sort(), memV.sort().domain())

        # Least signifficant first
        byts = [Select(memV, off + idx) for idx in range(0, size/8)]
        if (len(byts) == 1):
            self.mStack.push(byts[0])  # Select expects lsb last
        else:
            # Select expects lsb last
            self.mStack.push(Concat(*reversed(byts)))

    def leave_Store(self, expr):
        _, _, _, endianness, size = expr.arg
        # We didn't push anything for endianness. Assume little endian
        value = self.mStack.pop()
        off = self.mStack.pop()
        memV = self.mStack.pop()

        assert isinstance(endianness, LittleEndian)
        assert size % 8 == 0 and \
            memV.sort().domain().size() % 8 == 0 and \
            size >= memV.sort().range().size() and \
            size == value.sort().size() and \
            eq(off.sort(), memV.sort().domain())

        byts = [Extract((idx+1)*8-1, idx*8, value) for idx in range(0, size/8)]
        for (i, b) in enumerate(byts):
            memV = Update(memV, off + i, b)
        self.mStack.push(memV)

    # Stmts
    def visit_Move(self, stmt):
        # Need to visit move to avoid calling leave_Var on the (potentially yet
        # undefined) lhs
        assert len(stmt.arg) == 2
        newBindingName = stmt.var.name

        self.run(stmt.expr)
        expr = self.mStack.pop()

        oldSSAName, oldSort = self.lookup(newBindingName)
        if oldSort is not None:
            # If defined, cannot redefine type
            assert eq(expr.sort(), oldSort), \
                "Redefining " + newBindingName + " from " +\
                str(oldSort) + " to " +\
                str(expr.sort())

        self.pushScope(**{newBindingName: expr})
        print self.mScope.ssa(newBindingName), ":=", expr
        return True

    def visit_If(self, stmt):
        cond, if_stmt, else_stmt = stmt.arg
        assert isinstance(cond, Exp) and\
            isinstance(if_stmt, Stmt) or isinstance(if_stmt, tuple) and\
            isinstance(else_stmt, Stmt) or isinstance(else_stmt, tuple)

        # Get the condition
        self.run(cond)
        z3Cond = self.mStack.pop()

        # Mark current position on stack
        beforeIf = self.scopeMarker()

        # run on if branch
        trueCond = bvToBool(z3Cond)
        self.pushBranchScope('.if_true', trueCond, beforeIf)
        self.run(if_stmt)

        endIfStmt = self.scopeMarker()

        # run on else branch (reading from current position on stack)
        falseCond = Not(trueCond, ctx=self.mCtx)
        self.pushBranchScope('.if_false', falseCond, beforeIf)
        self.run(else_stmt)

        endElseStmt = self.scopeMarker()

        self.pushJoinScope(endIfStmt, endElseStmt, beforeIf)

    def leave_Jmp(self, stmt):
        assert isinstance(stmt.arg, Exp)
        dest = self.mStack.pop()
        self.pushScope(RIP=dest)
        # Doesn't return a value

    def leave_CpuExn(self, stmt):
        self.pushScope(CPUEXN=BitVecVal(1, 1, ctx=self.mCtx))


def embed(bil):
    visitor = X86_64Z3Embedder(Context())
    visit(visitor, bil)
    assert len(visitor.mStack) == 0
    return visitor
