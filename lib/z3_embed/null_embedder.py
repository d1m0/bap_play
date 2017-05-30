from .embedder import Z3Embedder, neverSeen


class NullZ3Embedder(Z3Embedder):
    def __init__(self, ctx):
        Z3Embedder.__init__(self, ctx)

    def leave_Imm(self, typ):
        neverSeen(typ)

    def leave_Mem(self, typ):
        neverSeen(typ)

    def leave_Int(self, ival):
        neverSeen(ival)

    def leave_Var(self, var):
        neverSeen(var)

    # Expressions
    #   Ternary Ops
    def visit_Let(self, expr):
        neverSeen(expr)

    def leave_Ite(self, expr):
        neverSeen(expr)

    def leave_Extract(self, expr):
        neverSeen(expr)

    #   Binary Ops
    def leave_Concat(self, expr):
        neverSeen(expr)

    def leave_PLUS(self, expr):
        neverSeen(expr)

    def leave_MINUS(self, expr):
        neverSeen(expr)

    def leave_TIMES(self, expr):
        neverSeen(expr)

    def leave_DIVIDE(self, expr):
        neverSeen(expr)

    def leave_SDIVIDE(self, expr):
        neverSeen(expr)

    def leave_MOD(self, expr):
        neverSeen(expr)

    def leave_SMOD(self, expr):
        neverSeen(expr)

    def leave_LSHIFT(self, expr):
        neverSeen(expr)

    def leave_RSHIFT(self, expr):
        neverSeen(expr)

    def leave_ARSHIFT(self, expr):
        neverSeen(expr)

    def leave_AND(self, expr):
        neverSeen(expr)

    def leave_OR(self, expr):
        neverSeen(expr)

    def leave_XOR(self, expr):
        neverSeen(expr)

    def leave_EQ(self, expr):
        neverSeen(expr)

    def leave_NEQ(self, expr):
        neverSeen(expr)

    def leave_LT(self, expr):
        neverSeen(expr)

    def leave_LE(self, expr):
        neverSeen(expr)

    def leave_SLT(self, expr):
        neverSeen(expr)

    def leave_SLE(self, expr):
        neverSeen(expr)

    #   Unary Ops
    def leave_NEG(self, expr):
        neverSeen(expr)

    def leave_NOT(self, expr):
        neverSeen(expr)

    def leave_Unknown(self, expr):
        neverSeen(expr)

    #   Casts Ops
    def leave_UNSIGNED(expr):
        neverSeen(expr)

    def leave_signed(expr):
        neverSeen(expr)

    def leave_HIGH(expr):
        neverSeen(expr)

    def leave_LOW(expr):
        neverSeen(expr)

    #   Mem Ops
    def leave_Load(self, expr):
        neverSeen(expr)

    def leave_Store(self, expr):
        neverSeen(expr)

    # Statements
    def leave_Move(self, stmt):
        neverSeen(stmt)

    def leave_Jmp(self, stmt):
        neverSeen(stmt)

    def leave_Special(self, stmt):
        neverSeen(stmt)

    def leave_While(self, stmt):
        neverSeen(stmt)

    def leave_If(self, stmt):
        neverSeen(stmt)

    def leave_CpuExn(self, stmt):
        neverSeen(stmt)
