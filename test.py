from lib.util import Bits, toLLVMAsm
from lib.z3_embed import bitsToBil, embed
from traceback import print_exc
from sys import exit
from lib.z3_embed.embedder import StmtNode

unused = [print_exc]

def filterUnchanged(asserts):
    def filterF(x):
        if x.decl().name().strip() != '=':
            return True

        rhs = x.children()[1]
        if (len(rhs.children()) != 0):
            return True
        if (not rhs.decl().name().endswith(".initial")):
            return True

        return False
    return filter(filterF, asserts)


pat1 = Bits("ff 25 02 37 cb 03")
pat2 = Bits("0f 84 c1 00 00 00")
pat3 = Bits("49 89 f5")

divq = Bits("48 f7 f1")
add = Bits("48 83 c4 08")

bil = bitsToBil(add)
print "==============ASM : ", toLLVMAsm(add)
print "==============BIT Pattern: ", add.toHexStr()
print "===============BIL:\n", "\n".join(map(str, bil))

print "==============Z3 Formulas: \n"
z3Vis = embed(bil)
print "\n".join(map(str, filterUnchanged(z3Vis.extract())))

exit()

"""
readC = 0
startSkipC = 8931
skipC = startSkipC
failedParsing = []
failedEmbedding = []

with open('../libxul.hex') as f:
    for l in f:
        if skipC > 0:
            skipC -= 1
            continue

        readC += 1
        z3Vis = None

        b = Bits(l.strip())
        try:
            bil = bitsToBil(b)
        except Exception:
            print "Failed parsing ", l
            print_exc()
            failedParsing.append(l)
            continue
        try:
            StmtNode.sId = 0  # 0-out ctr for easy reading
            z3Vis = embed(bil)
        except AssertionError, e:
            print e.message
            print l.strip()
            print toLLVMAsm(b)
            # print "\n".join(map(str, bil))
            print "New skipC: ", startSkipC + readC - 1
            failedParsing.append((l, bil, e))

        if (z3Vis):
            print l
            print bil
            print z3Vis.extract()
"""
