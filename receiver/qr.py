def _append_bits(value, count, bits):
    for shift in range(count - 1, -1, -1):
        bits.append((value >> shift) & 1)


def _gf_multiply(x, y):
    result = 0
    while y:
        if y & 1:
            result ^= x
        y >>= 1
        x <<= 1
        if x & 0x100:
            x ^= 0x11D
    return result


def _rs_remainder(data, degree):
    generator = [1]
    root = 1
    for _ in range(degree):
        next_poly = [0] * (len(generator) + 1)
        for index, coefficient in enumerate(generator):
            next_poly[index] ^= coefficient
            next_poly[index + 1] ^= _gf_multiply(coefficient, root)
        generator = next_poly
        root = _gf_multiply(root, 2)
    remainder = data + [0] * degree
    for index in range(len(data)):
        factor = remainder[index]
        if factor:
            for offset, coefficient in enumerate(generator):
                remainder[index + offset] ^= _gf_multiply(coefficient, factor)
    return remainder[-degree:]


def matrix(text):
    payload = text.encode("utf-8")
    if len(payload) > 62:
        raise ValueError("二维码地址过长。")
    bits = []
    _append_bits(0b0100, 4, bits)
    _append_bits(len(payload), 8, bits)
    for byte in payload:
        _append_bits(byte, 8, bits)
    capacity = 64 * 8
    bits.extend([0] * min(4, capacity - len(bits)))
    while len(bits) % 8:
        bits.append(0)
    words = [
        sum(bits[start + bit] << (7 - bit) for bit in range(8))
        for start in range(0, len(bits), 8)
    ]
    initial_count = len(words)
    pad = [0xEC, 0x11]
    while len(words) < 64:
        words.append(pad[(len(words) - initial_count) % 2])
    blocks = [words[:32], words[32:]]
    checks = [_rs_remainder(block, 18) for block in blocks]
    codewords = []
    for index in range(32):
        codewords.extend(block[index] for block in blocks)
    for index in range(18):
        codewords.extend(block[index] for block in checks)
    stream = [((word >> shift) & 1) for word in codewords for shift in range(7, -1, -1)]

    size = 33
    grid = [[None] * size for _ in range(size)]
    function = [[False] * size for _ in range(size)]

    def mark(x, y, dark):
        if 0 <= x < size and 0 <= y < size:
            grid[y][x] = dark
            function[y][x] = True

    def finder(cx, cy):
        for dy in range(-4, 5):
            for dx in range(-4, 5):
                distance = max(abs(dx), abs(dy))
                mark(cx + dx, cy + dy, distance != 2 and distance != 4)

    def alignment(cx, cy):
        for dy in range(-2, 3):
            for dx in range(-2, 3):
                mark(cx + dx, cy + dy, max(abs(dx), abs(dy)) != 1)

    finder(3, 3)
    finder(size - 4, 3)
    finder(3, size - 4)
    for cy in (6, 26):
        for cx in (6, 26):
            if grid[cy][cx] is None:
                alignment(cx, cy)
    for position in range(8, size - 8):
        if grid[6][position] is None:
            mark(position, 6, position % 2 == 0)
        if grid[position][6] is None:
            mark(6, position, position % 2 == 0)
    for index in range(15):
        if index < 6:
            mark(8, index, False)
        elif index < 8:
            mark(8, index + 1, False)
        else:
            mark(14 - index, 8, False)
        if index < 8:
            mark(size - 1 - index, 8, False)
        else:
            mark(8, size - 15 + index, False)
    mark(8, size - 8, True)

    bit_index = 0
    right = size - 1
    upward = True
    while right >= 1:
        if right == 6:
            right = 5
        for vertical in range(size):
            y = size - 1 - vertical if upward else vertical
            for offset in (0, 1):
                x = right - offset
                if not function[y][x]:
                    dark = bit_index < len(stream) and stream[bit_index] == 1
                    bit_index += 1
                    if (x + y) % 2 == 0:
                        dark = not dark
                    grid[y][x] = dark
        upward = not upward
        right -= 2

    format_value = 0
    remainder = format_value
    for _ in range(10):
        remainder = (remainder << 1) ^ (0x537 if remainder & (1 << 9) else 0)
    format_bits = ((format_value << 10) | remainder) ^ 0x5412
    for index in range(15):
        bit = ((format_bits >> index) & 1) != 0
        if index < 6:
            mark(8, index, bit)
        elif index < 8:
            mark(8, index + 1, bit)
        else:
            mark(14 - index, 8, bit)
        if index < 8:
            mark(size - 1 - index, 8, bit)
        else:
            mark(8, size - 15 + index, bit)
    mark(8, size - 8, True)
    return [[bool(cell) for cell in row] for row in grid]


def svg(text):
    cells = matrix(text)
    quiet = 4
    size = len(cells) + quiet * 2
    path = "".join(
        "M{} {}h1v1h-1z".format(x + quiet, y + quiet)
        for y, row in enumerate(cells)
        for x, dark in enumerate(row)
        if dark
    )
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {0} {0}" '
        'shape-rendering="crispEdges" role="img" aria-label="上传页面二维码">'
        '<rect width="{0}" height="{0}" fill="#fff"/>'
        '<path d="{1}" fill="#183d32"/></svg>'
    ).format(size, path).encode("utf-8")
