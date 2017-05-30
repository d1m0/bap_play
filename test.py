from lib.util import Bits, toLLVMAsm
from lib.z3_embed import bitsToBil, embed
from traceback import print_exc

pat1 = Bits("ff 25 02 37 cb 03")
pat2 = Bits("0f 84 c1 00 00 00")
pat3 = Bits("49 89 f5")

t = bitsToBil(pat1)
print t
print toLLVMAsm(pat1)
t1 = map(embed, t)
print t1[0].defs

readC = 0
startSkipC = 6702
skipC = startSkipC

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
            print_exc()
            print "Failed parsing ", l
            continue
        try:
            z3Vis = embed(bil)
        except:
            print l.strip()
            print bil
            print "New skipC: ", startSkipC + readC - 1
            raise
