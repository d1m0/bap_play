from subprocess import Popen, PIPE
from itertools import chain, izip_longest


def drain(iterable):
    res = []
    try:
        while True:
            res.append(iterable.next())
    except StopIteration:
        return res


def grouper(iterable, n, fillvalue=None):
    "Collect data into fixed-length chunks or blocks"
    # grouper('ABCDEFG', 3, 'x') --> ABC DEF Gxx
    args = [iter(iterable)] * n
    return izip_longest(fillvalue=fillvalue, *args)


class Bits:
    def __init__(self, arg):
        if type(arg) == str:
            hexL = [x.strip() for x in arg.split(' ')]
            hexL = [x for x in hexL if len(x) > 0]
            newHexL = []
            for x in hexL:
                if (len(x) == 1):
                    newHexL.append('0' + x)
                if (len(x) == 2):
                    newHexL.append(x)
                else:
                    splitL = map(lambda x:  x[0] + x[1], drain(grouper(x, 2, '')))
                    if len(splitL[-1]) == 1:
                        splitL[-1] = '0' + splitL[-1]
                    newHexL.extend(splitL)

            self.mHexL = \
                map(lambda x: '0x' + x if not x.startswith('0x') else x,
                    newHexL)
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


def toAsm(bits):
    p = Popen(['llvm-mc', '--disassemble'], stdin=PIPE, stdout=PIPE,
              stderr=PIPE)
    (stdout, stderr) = p.communicate(bits.toHexStr())
    if (stderr != '' or p.returncode != 0):
        raise Exception("llvm-mc failed disassembling string " +
                        bits.toHexStr())
    return stdout


def flatten(listOfLists):
        return list(chain.from_iterable(listOfLists))
