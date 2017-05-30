from subprocess import Popen, PIPE
from itertools import chain


class Bits:
    def __init__(self, arg):
        if type(arg) == str:
            hexL = [x.strip() for x in arg.split(' ')]
            self.mHexL = \
                map(lambda x: '0x' + x if not x.startswith('0x') else x,
                    hexL)
        elif type(arg) == list:
            hexL = [x.strip() for x in arg]
            self.mHexL = \
                map(lambda x: '0x' + x if not x.startswith('0x') else x,
                    hexL)
        else:
            raise Exception('Unkown bits type ' + str(arg))

    def toHexList(self):
        return self.mHexL

    def toHexStr(self):
        return ' '.join(self.mHexL)

    def toBinStr(self):
        return ''.join([chr(int(x, 16)) for x in self.mHexL])


def toLLVMAsm(bits):
    p = Popen(['llvm-mc', '--disassemble'], stdin=PIPE, stdout=PIPE,
              stderr=PIPE)
    (stdout, stderr) = p.communicate(bits.toHexStr())
    if (stderr != '' or p.returncode != 0):
        raise Exception("llvm-mc failed disassembling string " +
                        bits.toHexStr())
    return stdout


def flatten(listOfLists):
        return list(chain.from_iterable(listOfLists))
