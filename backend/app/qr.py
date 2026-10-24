"""极简二维码生成器（字节模式，纠错等级 M，版本 1-10），输出 SVG。
算法参照 Project Nayuki 的 QR Code generator（MIT 许可）。用于谷歌验证器绑定，避免额外依赖。
"""
from __future__ import annotations

_ECC_PER_BLOCK_M = [-1, 10, 16, 26, 18, 24, 16, 18, 22, 22, 26]
_NUM_BLOCKS_M = [-1, 1, 1, 1, 2, 2, 4, 4, 4, 5, 5]
_ECL_M_FORMAT = 0


def _gf_mul(x: int, y: int) -> int:
    z = 0
    for i in reversed(range(8)):
        z = (z << 1) ^ ((z >> 7) * 0x11D)
        z ^= ((y >> i) & 1) * x
    return z


def _rs_divisor(degree: int) -> list[int]:
    result = [0] * (degree - 1) + [1]
    root = 1
    for _ in range(degree):
        for j in range(degree):
            result[j] = _gf_mul(result[j], root)
            if j + 1 < degree:
                result[j] ^= result[j + 1]
        root = _gf_mul(root, 0x02)
    return result


def _rs_remainder(data: list[int], divisor: list[int]) -> list[int]:
    result = [0] * len(divisor)
    for b in data:
        factor = b ^ result.pop(0)
        result.append(0)
        for i, coef in enumerate(divisor):
            result[i] ^= _gf_mul(coef, factor)
    return result


def _raw_modules(ver: int) -> int:
    result = (16 * ver + 128) * ver + 64
    if ver >= 2:
        n = ver // 7 + 2
        result -= (25 * n - 10) * n - 55
        if ver >= 7:
            result -= 36
    return result


def _data_codewords(ver: int) -> int:
    return _raw_modules(ver) // 8 - _ECC_PER_BLOCK_M[ver] * _NUM_BLOCKS_M[ver]


def _align_positions(ver: int, size: int) -> list[int]:
    if ver == 1:
        return []
    n = ver // 7 + 2
    step = (ver * 4 + n * 2 + 1) // (n * 2 - 2) * 2
    result = [size - 7 - i * step for i in range(n - 1)] + [6]
    return list(reversed(result))


class QrCode:
    def __init__(self, text: str) -> None:
        data = text.encode("utf-8")
        for ver in range(1, 11):
            count_bits = 8 if ver <= 9 else 16
            needed = 4 + count_bits + len(data) * 8
            cap = _data_codewords(ver) * 8
            if needed <= cap:
                break
        else:
            raise ValueError("内容太长")
        self.ver = ver
        self.size = ver * 4 + 17
        bits: list[int] = []

        def put(val: int, n: int) -> None:
            bits.extend((val >> i) & 1 for i in reversed(range(n)))

        put(0b0100, 4)
        put(len(data), count_bits)
        for b in data:
            put(b, 8)
        put(0, min(4, cap - len(bits)))
        put(0, (-len(bits)) % 8)
        pad = 0xEC
        while len(bits) < cap:
            put(pad, 8)
            pad ^= 0xEC ^ 0x11
        codewords = [int("".join(map(str, bits[i:i + 8])), 2) for i in range(0, len(bits), 8)]

        n = self.size
        self.mod = [[False] * n for _ in range(n)]
        self.fn = [[False] * n for _ in range(n)]
        self._draw_function_patterns()
        self._draw_codewords(self._add_ecc(codewords))
        best, best_pen = 0, None
        for m in range(8):
            self._apply_mask(m)
            self._draw_format(m)
            pen = self._penalty()
            if best_pen is None or pen < best_pen:
                best, best_pen = m, pen
            self._apply_mask(m)  # 撤销
        self._apply_mask(best)
        self._draw_format(best)

    # ---------- 功能图形 ----------
    def _set_fn(self, x: int, y: int, dark: bool) -> None:
        self.mod[y][x] = dark
        self.fn[y][x] = True

    def _draw_function_patterns(self) -> None:
        n = self.size
        for i in range(n):
            self._set_fn(6, i, i % 2 == 0)
            self._set_fn(i, 6, i % 2 == 0)
        for cx, cy in ((3, 3), (n - 4, 3), (3, n - 4)):
            for dy in range(-4, 5):
                for dx in range(-4, 5):
                    x, y = cx + dx, cy + dy
                    if 0 <= x < n and 0 <= y < n:
                        self._set_fn(x, y, max(abs(dx), abs(dy)) not in (2, 4))
        pos = _align_positions(self.ver, n)
        last = len(pos) - 1
        for i, a in enumerate(pos):
            for j, b in enumerate(pos):
                if (i == 0 and j == 0) or (i == 0 and j == last) or (i == last and j == 0):
                    continue
                for dy in range(-2, 3):
                    for dx in range(-2, 3):
                        self._set_fn(a + dx, b + dy, max(abs(dx), abs(dy)) != 1)
        self._draw_format(0)
        if self.ver >= 7:
            rem = self.ver
            for _ in range(12):
                rem = (rem << 1) ^ ((rem >> 11) * 0x1F25)
            bits = self.ver << 12 | rem
            for i in range(18):
                bit = (bits >> i) & 1 == 1
                a, b = n - 11 + i % 3, i // 3
                self._set_fn(a, b, bit)
                self._set_fn(b, a, bit)

    def _draw_format(self, mask: int) -> None:
        data = _ECL_M_FORMAT << 3 | mask
        rem = data
        for _ in range(10):
            rem = (rem << 1) ^ ((rem >> 9) * 0x537)
        bits = (data << 10 | rem) ^ 0x5412
        g = lambda i: (bits >> i) & 1 == 1  # noqa: E731
        n = self.size
        for i in range(6):
            self._set_fn(8, i, g(i))
        self._set_fn(8, 7, g(6))
        self._set_fn(8, 8, g(7))
        self._set_fn(7, 8, g(8))
        for i in range(9, 15):
            self._set_fn(14 - i, 8, g(i))
        for i in range(8):
            self._set_fn(n - 1 - i, 8, g(i))
        for i in range(8, 15):
            self._set_fn(8, n - 15 + i, g(i))
        self._set_fn(8, n - 8, True)

    # ---------- 数据 ----------
    def _add_ecc(self, data: list[int]) -> list[int]:
        nblocks = _NUM_BLOCKS_M[self.ver]
        ecclen = _ECC_PER_BLOCK_M[self.ver]
        raw = _raw_modules(self.ver) // 8
        nshort = nblocks - raw % nblocks
        shortlen = raw // nblocks
        div = _rs_divisor(ecclen)
        blocks, k = [], 0
        for i in range(nblocks):
            dat = data[k: k + shortlen - ecclen + (0 if i < nshort else 1)]
            k += len(dat)
            ecc = _rs_remainder(dat, div)
            if i < nshort:
                dat = dat + [0]
            blocks.append(dat + ecc)
        out = []
        for i in range(len(blocks[0])):
            for j, blk in enumerate(blocks):
                if i != shortlen - ecclen or j >= nshort:
                    out.append(blk[i])
        return out

    def _draw_codewords(self, data: list[int]) -> None:
        n = self.size
        i = 0
        for right in range(n - 1, 0, -2):
            if right <= 6:
                right -= 1
            for vert in range(n):
                for j in range(2):
                    x = right - j
                    upward = ((right + 1) & 2) == 0
                    y = (n - 1 - vert) if upward else vert
                    if not self.fn[y][x] and i < len(data) * 8:
                        self.mod[y][x] = (data[i >> 3] >> (7 - (i & 7))) & 1 == 1
                        i += 1

    def _apply_mask(self, m: int) -> None:
        f = [
            lambda x, y: (x + y) % 2 == 0,
            lambda x, y: y % 2 == 0,
            lambda x, y: x % 3 == 0,
            lambda x, y: (x + y) % 3 == 0,
            lambda x, y: (x // 3 + y // 2) % 2 == 0,
            lambda x, y: x * y % 2 + x * y % 3 == 0,
            lambda x, y: (x * y % 2 + x * y % 3) % 2 == 0,
            lambda x, y: ((x + y) % 2 + x * y % 3) % 2 == 0,
        ][m]
        for y in range(self.size):
            for x in range(self.size):
                if not self.fn[y][x] and f(x, y):
                    self.mod[y][x] = not self.mod[y][x]

    def _penalty(self) -> int:
        n, m = self.size, self.mod
        pen = 0
        for line in [[m[y][x] for x in range(n)] for y in range(n)] + [[m[y][x] for y in range(n)] for x in range(n)]:
            run = 1
            for a, b in zip(line, line[1:]):
                if a == b:
                    run += 1
                else:
                    if run >= 5:
                        pen += run - 2
                    run = 1
            if run >= 5:
                pen += run - 2
        for y in range(n - 1):
            for x in range(n - 1):
                if m[y][x] == m[y][x + 1] == m[y + 1][x] == m[y + 1][x + 1]:
                    pen += 3
        dark = sum(sum(r) for r in m)
        total = n * n
        k = (abs(dark * 20 - total * 10) + total - 1) // total - 1
        return pen + max(k, 0) * 10

    def svg(self, scale: int = 6, border: int = 4) -> str:
        n = self.size + border * 2
        path = "".join(f"M{x + border},{y + border}h1v1h-1z" for y in range(self.size) for x in range(self.size) if self.mod[y][x])
        return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {n} {n}" width="{n * scale}" height="{n * scale}" '
                f'shape-rendering="crispEdges"><rect width="100%" height="100%" fill="#fff"/><path d="{path}" fill="#000"/></svg>')
