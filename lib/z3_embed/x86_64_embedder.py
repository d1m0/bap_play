from bap.bil import Exp
from z3 import BitVecSort, ArraySort
from .base_embedder import BaseEmbedder
from .embedder import embed


class X86_64Z3Embedder(BaseEmbedder):
    """ X86_64 + AVX Embedder
    """
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

    def leave_Jmp(self, stmt):
        assert isinstance(stmt.arg, Exp)
        dest = self.mStack.pop()
        self.pushScope(RIP=dest)
        # Doesn't return a value


def embed_x86(bil):
    return embed(bil, X86_64Z3Embedder)
