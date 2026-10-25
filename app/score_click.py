# -*- coding: utf-8 -*-
"""点击谱面 → 猜出点中的是哪一行五线谱（谱表系统），裁出来交给 OMR。

判据（在真实扫描页上验证过）：
  谱线 = 一行里有一条**几乎不断的长横线**（≥22% 页宽），且**上下都是白**
  文字行 = 也横跨页面，但字形是断续的、上下都有墨，所以被排除

拿到谱线行之后再按间距聚类成「系统」：单谱表 5 条线，大谱表 10 条。
"""
import os
import re

# 谱行检测算法版本：算法改动后 +1，让界面里的按页缓存失效
DETECT_VERSION = 7

MIN_RUN_RATIO = 0.22      # 谱线至少占页宽的 22%（很多谱例是缩进的，不能要求更长）
NEIGHBOUR_WHITE = 0.18    # 上下 2 像素内暗像素比例低于这个值，才算「细线」
MAX_GAP_FACTOR = 2.6      # 谱线间距超过中位数的这个倍数，就认为是另一行谱


def _binarize(gray, boost=12):
    """自适应二值化：浅色扫描件用固定阈值会漏掉谱线。"""
    import numpy as np
    threshold = 160.0
    try:
        import cv2
        value, _ = cv2.threshold(gray, 0, 255,
                                 cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        threshold = float(value) + boost
    except Exception:
        low = float(np.percentile(gray, 2))
        middle = float(np.percentile(gray, 55))
        threshold = (low + middle) / 2
    threshold = min(215.0, max(110.0, threshold))
    return (gray < threshold).astype(np.int8)


def row_stats(image):
    """每一行的 (最长连续暗段占页宽比例, 暗像素比例)。"""
    import numpy as np
    gray = np.array(image.convert('L'))
    dark = _binarize(gray)
    # 横向补 1 像素缝：抗锯齿/压缩常把谱线打断成一小段一小段
    if dark.shape[1] > 2:
        left = dark[:, :-2]
        middle = dark[:, 1:-1]
        right = dark[:, 2:]
        dark[:, 1:-1] = np.where((left | right) & ~middle, 1, middle)
    width = max(1, gray.shape[1])
    pad = np.zeros((dark.shape[0], 1), dtype=np.int8)
    edges = np.diff(np.hstack([pad, dark, pad]), axis=1)
    longest = np.zeros(dark.shape[0], dtype=np.float32)
    for row in range(dark.shape[0]):
        starts = np.flatnonzero(edges[row] == 1)
        ends = np.flatnonzero(edges[row] == -1)
        if starts.size and ends.size:
            longest[row] = (ends[:starts.size] - starts).max() / width
    return longest, dark.mean(axis=1)


def staff_rows(image, min_ratio=MIN_RUN_RATIO, neighbour=NEIGHBOUR_WHITE):
    """返回谱线所在的 y 坐标列表。

    判据：这一行有几乎不断的长横线，且**线外侧（上方或下方 3-5 像素）是白的**。
    注意不能用 ±2 像素判断：扫描件里谱线常有 3 像素粗，±2 还落在线内，
    会把 250 首那种清晰页面全部误杀。
    """
    longest, fractions = row_stats(image)
    rows = []
    total = len(longest)
    for index in range(total):
        if longest[index] < min_ratio:
            continue
        above = fractions[max(0, index - 5):max(0, index - 2)]
        below = fractions[index + 3:index + 6]
        outer = [value for block in (above, below) for value in block]
        white = bool(outer) and min(outer) < neighbour
        # 密集乐段里线间也有墨，靠「明显高于邻行」判断更可靠
        left = longest[index - 2] if index >= 2 else 0.0
        right = longest[index + 2] if index + 2 < total else 0.0
        spike = longest[index] - max(left, right) >= 0.15
        if white or spike:
            rows.append(index)
    return rows


def collapse_lines(rows, thickness=2):
    """把同一根谱线占的连续几行合成一条（扫描件里一根线常占 3-4 行）。"""
    if not rows:
        return []
    out = []
    start = prev = rows[0]
    for y in rows[1:]:
        if y - prev <= thickness:
            prev = y
            continue
        out.append((start + prev) // 2)
        start = prev = y
    out.append((start + prev) // 2)
    return out


def estimate_skew(image, limit=3.0, step=0.5):
    """估计页面倾斜角（度）。返回 0 表示不用转。"""
    import numpy as np
    try:
        import cv2
    except Exception:
        return 0.0
    gray = np.array(image.convert('L'))
    height, width = gray.shape
    if width > 700:
        ratio = 700 / width
        gray = cv2.resize(gray, (700, max(1, int(height * ratio))))
    binary = (gray < 160).astype(np.uint8) * 255
    best_angle, best_score = 0.0, 0.0
    angle = -limit
    while angle <= limit + 1e-6:
        center = (binary.shape[1] / 2, binary.shape[0] / 2)
        matrix = cv2.getRotationMatrix2D(center, angle, 1.0)
        rotated = cv2.warpAffine(binary, matrix, (binary.shape[1], binary.shape[0]),
                                 flags=cv2.INTER_NEAREST, borderValue=0)
        row_sum = (rotated > 0).sum(axis=1)
        # 一行如果几乎全黑，说明谱线被转平了
        score = float(row_sum.max()) / max(1, rotated.shape[1])
        if score > best_score + 0.02:
            best_score, best_angle = score, angle
        angle += step
    return best_angle if best_score > 0.35 else 0.0


def _rotate(image, angle):
    import cv2
    import numpy as np
    from PIL import Image
    array = np.array(image.convert('RGB'))
    height, width = array.shape[:2]
    matrix = cv2.getRotationMatrix2D((width / 2, height / 2), -angle, 1.0)
    rotated = cv2.warpAffine(array, matrix, (width, height),
                             flags=cv2.INTER_LINEAR, borderValue=(255, 255, 255))
    return Image.fromarray(rotated)


def _map_bands_back(bands, angle, width):
    """把小角度旋转后的谱行映射回原图坐标（够用即可）。"""
    import math
    if not angle:
        return bands
    shift = math.tan(math.radians(angle)) * (width / 2)
    return [(max(0, int(top - shift)), max(0, int(bottom - shift)))
            for top, bottom in bands]


_LAST_DETECT = {'angle': 0.0, 'size': (0, 0)}


def last_angle(size=None):
    """最近一次检测用的倾斜角；size 对不上就当 0。"""
    if size and _LAST_DETECT['size'] != tuple(size):
        return 0.0
    return _LAST_DETECT['angle']


def _remember_angle(angle, image):
    _LAST_DETECT['angle'] = float(angle or 0.0)
    _LAST_DETECT['size'] = (image.width, image.height)


def candidate_angles(image, min_length=150, limit=6.0):
    """横线段的候选角度（去重、按覆盖程度排序）。"""
    import numpy as np
    try:
        import cv2
    except Exception:
        return []
    gray = np.array(image.convert('L'))
    binary = _binarize(gray).astype(np.uint8) * 255
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (25, 1))
    opened = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel)
    segments = cv2.HoughLinesP(opened, 1, np.pi / 180, threshold=60,
                               minLineLength=min_length, maxLineGap=10)
    if segments is None:
        return []
    weights = {}
    for item in segments[:500]:
        x1, y1, x2, y2 = item[0]
        if x2 == x1:
            continue
        length = ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5
        angle = float(np.degrees(np.arctan2(y2 - y1, x2 - x1)))
        if abs(angle) >= limit:
            continue
        key = round(angle, 1)
        weights[key] = weights.get(key, 0) + length
    ordered = sorted(weights.items(), key=lambda pair: -pair[1])
    return [angle for angle, _weight in ordered[:6]]


def skew_from_lines(image, min_length=300):
    """用长横线段的中位角度估倾斜（只看够长的线，避开正文）。"""
    import numpy as np
    try:
        import cv2
    except Exception:
        return 0.0
    gray = np.array(image.convert('L'))
    binary = _binarize(gray).astype(np.uint8) * 255
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (25, 1))
    opened = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel)
    segments = cv2.HoughLinesP(opened, 1, np.pi / 180, threshold=60,
                               minLineLength=min_length, maxLineGap=10)
    if segments is None:
        return 0.0
    angles = []
    for item in segments[:500]:
        x1, y1, x2, y2 = item[0]
        if x2 == x1:
            continue
        length = ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5
        if length < min_length:
            continue
        angle = float(np.degrees(np.arctan2(y2 - y1, x2 - x1)))
        if abs(angle) < 6.0:
            angles.append(angle)
    if len(angles) < 3:
        return 0.0
    return float(np.median(angles))


def _merge_false_lines(rows, ratio=0.5, floor=3):
    """合并「同一条谱线被识别成两行」的情况。

    扫描件里粗线/重影会在一根线附近多检出一行（相差 2~4 像素），
    会让后面的间距均匀性检查判失败，整条谱表被丢掉。
    判据：间距小于典型间距的一半，就认为是同一根线，取中点。
    """
    if len(rows) < 3:
        return list(rows)
    import statistics
    wide = [b - a for a, b in zip(rows, rows[1:]) if b - a > floor]
    typical = statistics.median(wide) if wide else 10.0
    limit = max(floor, typical * ratio)
    out = [rows[0]]
    for y in rows[1:]:
        if y - out[-1] <= limit:
            out[-1] = (out[-1] + y) // 2
        else:
            out.append(y)
    return out


def staff_groups(image, max_gap_factor=2.2):
    """把谱线聚成一个个「单谱表」，返回 [{'top','bottom','spacing','lines'}]。"""
    rows = collapse_lines(staff_rows(image))
    rows = _merge_false_lines(rows)
    if not rows:
        return []
    import statistics
    gaps = [b - a for a, b in zip(rows, rows[1:]) if b - a > 1]
    typical = statistics.median(gaps) if gaps else 10
    limit = max(10, typical * max_gap_factor)

    groups = []
    start = prev = rows[0]
    for y in rows[1:]:
        if y - prev <= limit:
            prev = y
            continue
        groups.append((start, prev))
        start = prev = y
    groups.append((start, prev))

    out = []
    for top, bottom in groups:
        if bottom - top < 10:            # 单根线，不像谱表
            continue
        inside = [y for y in rows if top <= y <= bottom]
        spacing = statistics.median([b - a for a, b in zip(inside, inside[1:])]) \
            if len(inside) > 1 else typical
        # 真正的谱表有 5 条线；允许漏检 1 条，但线距要像谱线（4~40 像素）
        if len(inside) < 4:
            continue
        if not (4.0 <= spacing <= 40.0):
            continue
        gaps = [b - a for a, b in zip(inside, inside[1:])]
        if gaps and spacing > 0:
            # 间隙要均匀：最小不能太小、最大不能太大
            if min(gaps) < spacing * 0.45:
                continue
            if max(gaps) > spacing * 2.4:
                continue
            # 最多允许一个「2 倍间隙」——那代表中间漏了一根线
            doubles = [gap for gap in gaps if gap > spacing * 1.5]
            if len(doubles) > 1:
                continue
        out.append({'top': top, 'bottom': bottom,
                    'spacing': spacing, 'lines': len(inside)})
    return out


def _uncovered_ink_height(image, bands, min_run=40):
    """有没有「明显有墨、却没被任何谱行覆盖」的横向区块（歪页常这样）。"""
    import numpy as np
    try:
        gray = np.array(image.convert('L'))
    except Exception:
        return 0
    binary = np.array(_binarize(gray), dtype=np.uint8)
    width = binary.shape[1]
    rows = binary.sum(axis=1) > max(8, int(width * 0.02))
    covered = np.zeros(binary.shape[0], dtype=bool)
    for top, bottom in bands:
        covered[max(0, int(top) - 4):min(binary.shape[0], int(bottom) + 4)] = True
    longest = run = 0
    for index, has_ink in enumerate(rows):
        if has_ink and not covered[index]:
            run += 1
            longest = max(longest, run)
        else:
            run = 0
    return longest if longest >= min_run else 0


def _skew_attempt(image, merge_grand, inner_gap_factor, pad_ratio):
    """按候选角度转正后再检测，**取检出谱行最多的那个角度**。

    以前碰到第一个能出结果的角就返回，歪得厉害、曲率不均的页会只找到一半。
    """
    tried = []
    expanded = []
    for angle in candidate_angles(image):
        for delta in (0.0, 0.4, -0.4, 0.8, -0.8, 1.2, -1.2):
            expanded.append(round(angle + delta, 1))

    best = None
    best_score = (-1, -1)
    for angle in expanded:
        for signed in (angle, -angle):
            if abs(signed) < 0.15 or signed in tried or len(tried) >= 48:
                continue
            tried.append(signed)
            rotated = _rotate(image, signed)
            groups = staff_groups(rotated)
            if not groups:
                continue
            bands = _systems_from_groups(rotated, groups, merge_grand,
                                         inner_gap_factor, pad_ratio)
            # 行数优先；行数相同时，用到的谱表分组更多者更好（说明检出更完整）
            score = (len(bands), len(groups))
            if score > best_score:
                best_score = score
                best = (signed, bands)
            if best_score[0] >= 8:        # 已经够多，不必再试
                break
        if best_score[0] >= 8:
            break

    if best is not None:
        signed, bands = best
        _remember_angle(signed, image)
        return _map_bands_back(bands, signed, image.width)

    angle = estimate_skew(image)
    if angle:
        rotated = _rotate(image, angle)
        groups = staff_groups(rotated)
        if groups:
            bands = _systems_from_groups(rotated, groups, merge_grand,
                                         inner_gap_factor, pad_ratio)
            _remember_angle(angle, image)
            return _map_bands_back(bands, angle, image.width)
    return []


def _detect_core(image, merge_grand, inner_gap_factor, pad_ratio):
    """单张图的检测：先直接找，找不到/明显漏行再纠偏。"""
    groups = staff_groups(image)
    if groups:
        bands = _systems_from_groups(image, groups, merge_grand,
                                     inner_gap_factor, pad_ratio)
        if not _uncovered_ink_height(image, bands):
            return bands
    alternative = _skew_attempt(image, merge_grand, inner_gap_factor, pad_ratio)
    if alternative:
        return alternative
    return bands if groups else []


def _strip_detect(image, merge_grand, inner_gap_factor, pad_ratio):
    """把页面横切成三条（带重叠）分别检测，各自纠偏。

    歪得厉害或扫描弯曲的页面，上下部分的倾斜角不一样，
    整页用一个角度只能救回一半，分条带就能各管各的。
    """
    height = image.height
    width = image.width
    strips = ((0.00, 0.44), (0.28, 0.72), (0.56, 1.00))
    collected = []
    for top_ratio, bottom_ratio in strips:
        top = int(height * top_ratio)
        bottom = int(height * bottom_ratio)
        if bottom - top < 60:
            continue
        crop = image.crop((0, top, width, bottom))
        for band_top, band_bottom in _detect_core(crop, merge_grand,
                                                  inner_gap_factor, pad_ratio):
            collected.append((band_top + top, band_bottom + top))
    collected.sort()
    merged = []
    for band_top, band_bottom in collected:
        if merged and band_top <= merged[-1][1] - 8:
            merged[-1] = (merged[-1][0], max(merged[-1][1], band_bottom))
        else:
            merged.append((band_top, band_bottom))
    return merged


def systems(image, merge_grand=True, inner_gap_factor=14.0, pad_ratio=0.35):
    """谱表系统。

    merge_grand=True（默认）时，把相距很近（≤9.5 个谱线间距）的上下两个谱表
    合并成一个大谱表——四部和声的高音谱表 + 低音谱表就属于这种，
    否则会被当成两行、只听得到一半声部。

    检测顺序：
      1. 整页直接找
      2. 找不到或明显漏行 → 整页纠偏后再找
      3. 还漏 → 把页面横切三条各自纠偏，取检出更多的结果
    """
    _remember_angle(0.0, image)
    bands = _detect_core(image, merge_grand, inner_gap_factor, pad_ratio)
    if _uncovered_ink_height(image, bands) or len(bands) <= 2:
        strip_bands = _strip_detect(image, merge_grand, inner_gap_factor, pad_ratio)
        # 只有「多检出至少两条」才采用：条带切分偶尔会把一整个大谱表切成两半，
        # 只多一条时很可能就是这种误切，不能拿来覆盖整页结果。
        if len(strip_bands) >= len(bands) + 2:
            return strip_bands
    return bands


def _brace_between(binary, upper_bottom, lower_top, pad=18):
    """两张谱表之间左侧有没有连着的竖线（花括号/连谱号）。"""
    import numpy as np
    if binary is None or lower_top <= upper_bottom:
        return 0.0
    try:
        starts = []
        for y in (upper_bottom, lower_top):
            row = binary[min(y, binary.shape[0] - 1)]
            index = np.flatnonzero(row)
            starts.append(int(index[0]) if index.size else 0)
        left = max(0, min(starts) - pad)
        right = max(0, min(starts) + 6)
        if right <= left:
            return 0.0
        band = binary[max(0, upper_bottom):min(binary.shape[0], lower_top), left:right]
        if band.size == 0:
            return 0.0
        return float(band.max(axis=1).mean())
    except Exception:
        return 0.0


def _stem_between(binary, upper_bottom, lower_top, pad=70):
    """两张谱表之间左侧有没有一条**贯穿的竖线**（连谱号的竖干）。

    比「弯钩墨迹比例」可靠：扫描件里花括号的弯钩常被压平/断掉，
    但那条从上谱表连到下谱表的竖干几乎总在。
    返回最佳一列的覆盖率（0~1）。
    """
    import numpy as np
    if binary is None or lower_top <= upper_bottom:
        return 0.0
    height, width = binary.shape
    try:
        starts = []
        for y in (upper_bottom, lower_top):
            row = binary[min(max(y, 0), height - 1)]
            index = np.flatnonzero(row)
            if index.size:
                starts.append(int(index[0]))
        anchor = min(starts) if starts else 0
        left = max(0, anchor - pad)
        right = min(width, anchor + 25)
        if right <= left:
            return 0.0
        band = binary[max(0, upper_bottom):min(height, lower_top), left:right]
        if band.size == 0:
            return 0.0
        # 每一列的最长连续暗段占区域高度的比例
        best = 0.0
        for column in band.T:
            run = longest = 0
            for value in column:
                if value:
                    run += 1
                    longest = max(longest, run)
                else:
                    run = 0
            best = max(best, longest / float(band.shape[0]))
        return best
    except Exception:
        return 0.0


def _systems_from_groups(image, groups, merge_grand, inner_gap_factor, pad_ratio):
    if not groups:
        return []

    binary = None
    if merge_grand:
        try:
            import numpy as np
            binary = _binarize(np.array(image.convert('L')))
        except Exception:
            binary = None

    merged = []
    for group in groups:
        if not merged:
            merged.append(dict(group))
            continue
        last = merged[-1]
        gap = group['top'] - last['bottom']
        spacing = max(4.0, (last['spacing'] + group['spacing']) / 2)
        if not merge_grand:
            merged.append(dict(group))
            continue
        # 同一行的判据（优先级从高到低）：
        #   1) 左侧有一条贯穿两谱表的竖干（连谱号竖干，最可靠）
        #   2) 左边有连谱号的弯钩墨迹
        #   3) 两张谱表贴得特别近（≤7 个谱间距）
        brace = _brace_between(binary, last['bottom'], group['top'])
        stem = _stem_between(binary, last['bottom'], group['top'])
        tight = gap <= 7.0 * spacing
        wide_ok = gap <= inner_gap_factor * spacing
        if (stem >= 0.7 and wide_ok) or (brace >= 0.6 and wide_ok) or (brace < 0.6 and tight):
            last['bottom'] = group['bottom']
            last['lines'] += group['lines']
            last['spacing'] = (last['spacing'] + group['spacing']) / 2
        else:
            merged.append(dict(group))

    out = []
    for group in merged:
        height = group['bottom'] - group['top']
        pad = int(max(10, height * pad_ratio))
        out.append((max(0, group['top'] - pad), min(image.height, group['bottom'] + pad)))
    # 留白会让相邻两行重叠，重叠区分不清该点哪一行，从中间切开
    for index in range(len(out) - 1):
        top, bottom = out[index]
        next_top, next_bottom = out[index + 1]
        if bottom > next_top:
            middle = (bottom + next_top) // 2
            out[index] = (top, max(top + 8, middle))
            out[index + 1] = (min(next_bottom - 8, middle), next_bottom)
    return out


def staff_at(image, y):
    """只要点中那一张谱表（不合并高低音时的行为）。"""
    groups = staff_groups(image)
    if not groups:
        return None
    for group in groups:
        if group['top'] <= y <= group['bottom']:
            return (group['top'], group['bottom'])
    nearest = min(groups, key=lambda g: abs((g['top'] + g['bottom']) / 2 - y))
    return (nearest['top'], nearest['bottom'])


def band_at(image, y, merge_grand=True):
    """点中 y 时该用哪一段。点空处就取最近的一段。"""
    bands = systems(image, merge_grand=merge_grand)
    if not bands:
        single = staff_at(image, y) if merge_grand else None
        if single:
            return single
        half = max(60, int(image.height * 0.08))
        return (max(0, int(y) - half), min(image.height, int(y) + half))
    for top, bottom in bands:
        if top <= y <= bottom:
            return (top, bottom)
    return min(bands, key=lambda band: abs((band[0] + band[1]) / 2 - y))


def _longest_run_extent(binary_row, min_length=40):
    """一行里最长暗段的起止 x（没有就当整行）。"""
    import numpy as np
    if binary_row.size == 0:
        return None
    padded = np.concatenate(([0], binary_row.astype(np.int8), [0]))
    edges = np.diff(padded)
    starts = np.flatnonzero(edges == 1)
    ends = np.flatnonzero(edges == -1)
    if not starts.size or not ends.size:
        return None
    lengths = ends[:starts.size] - starts
    index = int(lengths.argmax())
    if lengths[index] < min_length:
        return None
    return int(starts[index]), int(ends[index])


def missing_lines(image):
    """找出谱表里缺失的线（2 倍间隙的中点），返回 [(y, x1, x2)]。"""
    import numpy as np
    try:
        groups = staff_groups(image)
    except Exception:
        return []
    if not groups:
        return []
    rows = collapse_lines(staff_rows(image))
    gray = np.array(image.convert('L'))
    binary = _binarize(gray)
    found = []
    for group in groups:
        inside = [y for y in rows if group['top'] <= y <= group['bottom']]
        if len(inside) < 2:
            continue
        spacing = group['spacing'] or 1
        for upper, lower in zip(inside, inside[1:]):
            if lower - upper <= spacing * 1.5:
                continue
            middle = (upper + lower) // 2
            extent = _longest_run_extent(binary[min(upper, gray.shape[0] - 1)])
            if not extent:
                continue
            found.append((middle, extent[0], extent[1]))
    return found


def _synthesize_missing_lines(crop, image, top):
    """在裁图上补出缺掉的谱线。倾斜页坐标对不上，不补。"""
    from PIL import ImageDraw
    if last_angle((image.width, image.height)):
        return crop
    try:
        lines = missing_lines(image)
    except Exception:
        return crop
    if not lines:
        return crop
    draw = ImageDraw.Draw(crop)
    for y_page, x1, x2 in lines:
        y = int(y_page) - int(top)
        if 0 <= y < crop.height:
            # 真谱线是 2~4 像素粗，合成线太细 OMR 也不认
            draw.line([(max(0, x1), y), (min(crop.width - 1, x2), y)],
                      fill=(28, 28, 28), width=2)
    return crop


def _straighten(crop, image):
    """按检测时的倾斜角把裁图转正。"""
    angle = last_angle((image.width, image.height))
    if not angle:
        return crop
    try:
        return _rotate(crop, angle)
    except Exception:
        return crop


def crop_band(image, y, merge_grand=True):
    """裁出点中的那一行（整幅宽度，保留完整小节）。返回 (crop, (top, bottom))。"""
    top, bottom = band_at(image, y, merge_grand=merge_grand)
    crop = _straighten(image.crop((0, top, image.width, bottom)), image)
    crop = _synthesize_missing_lines(crop, image, top)
    return crop, (top, bottom)


def crop_region(image, box):
    """按给定矩形裁剪（用于拖框选段）。box = (x1, y1, x2, y2)，自动理正。"""
    x1, y1, x2, y2 = box
    left, right = sorted((int(x1), int(x2)))
    top, bottom = sorted((int(y1), int(y2)))
    left = max(0, min(left, image.width - 8))
    right = max(left + 8, min(right, image.width))
    top = max(0, min(top, image.height - 8))
    bottom = max(top + 8, min(bottom, image.height))
    crop = _straighten(image.crop((left, top, right, bottom)), image)
    crop = _synthesize_missing_lines(crop, image, top)
    return crop, (left, top, right, bottom)


def cache_name(book_stem, page, band_top, x1=None, x2=None):
    """缓存文件名必须全 ASCII —— homr 遇到中文文件名会直接失败（实测 0.0 秒返回）。"""
    import hashlib
    digest = hashlib.md5((book_stem or '').encode('utf-8')).hexdigest()[:8]
    if x1 is None or x2 is None:
        return f'p{page:03d}_b{band_top:04d}_{digest}.mid'
    return f'p{page:03d}_b{band_top:04d}_x{int(x1):04d}_{int(x2):04d}_{digest}.mid'


def book_slug(book_stem):
    """每本书一个 ASCII 目录名（homr 不接受中文路径）。"""
    import hashlib
    digest = hashlib.md5((book_stem or 'book').encode('utf-8')).hexdigest()[:8]
    return f'book_{digest}'


def book_folder(cache_root, book_title='', book_stem='', book_path=''):
    """返回这本书的专属目录，并写好 book.json（存真实书名）。"""
    import json
    folder = os.path.join(cache_root, 'books', book_slug(book_stem))
    os.makedirs(folder, exist_ok=True)
    info_path = os.path.join(folder, 'book.json')
    payload = {'title': book_title, 'stem': book_stem, 'pdf': book_path}
    try:
        keep = {}
        if os.path.isfile(info_path):
            with open(info_path, encoding='utf-8') as handle:
                keep = json.load(handle)
        keep.update({k: v for k, v in payload.items() if v})
        with open(info_path, 'w', encoding='utf-8') as handle:
            json.dump(keep, handle, ensure_ascii=False, indent=2)
    except Exception:
        pass
    return folder


def cache_path(cache_root, book_stem, page, band_top, x1=None, x2=None):
    """缓存直接放在本书目录下（cache_root 就是书目录）。"""
    os.makedirs(cache_root, exist_ok=True)
    return os.path.join(cache_root, cache_name(book_stem, page, band_top, x1, x2))
