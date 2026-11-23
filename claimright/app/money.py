"""Indian rupee formatting: 101500 -> '₹1,01,500'."""


def inr(x: float, symbol: bool = True) -> str:
    neg = x < 0
    x = abs(round(float(x)))
    s = str(int(x))
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        s = ",".join(groups + [tail])
    return ("-" if neg else "") + ("₹" if symbol else "") + s
