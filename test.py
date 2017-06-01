from lib.util import Bits, toLLVMAsm
from lib.z3_embed import bitsToBil, embed
from traceback import print_exc

unused = [print_exc]

from lib.z3_embed.embedder import StmtNode

pat1 = Bits("ff 25 02 37 cb 03")
pat2 = Bits("0f 84 c1 00 00 00")
pat3 = Bits("49 89 f5")

readC = 0
startSkipC = 8121
skipC = startSkipC
failedParsing = []
failedEmbedding = []

with open('../libxul.hex') as f:
    for l in f:
        if skipC > 0:
            skipC -= 1
            continue

        readC += 1

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
            print bil
            print z3Vis.extract()
            break
        except AssertionError, e:
            print e.message
            print l.strip()
            print toLLVMAsm(b)
            # print "\n".join(map(str, bil))
            print "New skipC: ", startSkipC + readC - 1
            failedParsing.append((l, bil, e))
            if (e.message != "Never seen Special"):
                raise e
