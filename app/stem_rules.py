# -*- coding: utf-8 -*-
"""按固定规则给 MusicXML 写上显式符干方向。

规则（和传统制谱惯例一致）：
  · 每个「同一时刻 + 同一谱表」的音归为一组（和弦）
  · 以该谱表的中线为界：整组落在中线以上 → 符干朝下；以下 → 朝上
  · 跨中线时看「离中线更远的那一端」在哪边
      —— 和弦里最高的音离中线更远就朝下，反之朝上
  · 中线按谱号定：高音谱表 B4、低音谱表 D3、中音谱表 C4、次中音谱表 A3

这样不管 homr 把音分到几个声部，画出来都是统一的朝向。
"""
import os
import xml.etree.ElementTree as ET

MIDDLE_BY_CLEF = {
    ('G', '2'): 71,   # 高音谱表：中线 B4
    ('F', '4'): 50,   # 低音谱表：中线 D3
    ('C', '3'): 60,   # 中音谱表：中线 C4
    ('C', '4'): 57,   # 次中音谱表：中线 A3
    ('G', '1'): 76,   # 法式高音谱表（少见）
}
DEFAULT_MIDDLE = 71

NOTE_NAMES = {'C': 0, 'D': 2, 'E': 4, 'F': 5, 'G': 7, 'A': 9, 'B': 11}


def _tag(element):
    tag = element.tag
    return tag.rsplit('}', 1)[-1] if '}' in tag else tag


def _child(element, name):
    for node in element:
        if _tag(node) == name:
            return node
    return None


def _text(element, name, default=None):
    node = _child(element, name)
    if node is None or node.text is None:
        return default
    return node.text.strip()


def _pitch_midi(note):
    pitch = _child(note, 'pitch')
    if pitch is None:
        return None
    step = _text(pitch, 'step', 'C')
    try:
        octave = int(_text(pitch, 'octave', '4'))
    except (TypeError, ValueError):
        octave = 4
    try:
        alter = int(float(_text(pitch, 'alter', '0') or 0))
    except (TypeError, ValueError):
        alter = 0
    return (octave + 1) * 12 + NOTE_NAMES.get(step, 0) + alter


def _staff_middles(root):
    """每个 part 的每张谱表，中线音高是多少。"""
    middles = {}
    for part in root.iter('part'):
        part_id = part.get('id') or ''
        table = {}
        for attributes in part.iter('attributes'):
            number = attributes.get('number') or '1'
            clefs = attributes.findall('clef')
            for clef in clefs:
                sign = _text(clef, 'sign', 'G')
                line = _text(clef, 'line', '2')
                table[clef.get('number') or number] = MIDDLE_BY_CLEF.get(
                    (sign, line), DEFAULT_MIDDLE)
        middles[part_id] = table
    return middles


def _direction_for(pitches, middle, outward=False):
    """outward=False：朝中线（通用规则）；True：朝外（上朝上、下朝下）。"""
    if not pitches:
        return 'up'
    low, high = min(pitches), max(pitches)
    above = high - middle
    below = middle - low
    higher = above > below
    if outward:
        # 离中线更远的那端在上 -> 朝上；在下 -> 朝下
        return 'up' if higher else 'down'
    return 'down' if higher else 'up'


def _insert_stem(note, direction):
    for node in list(note):
        if _tag(node) == 'stem':
            note.remove(node)
    stem = ET.Element('stem')
    stem.text = direction
    # 按 MusicXML 的元素顺序，<stem> 排在 <time-modification> 之后、
    # <notehead>/<staff>/<beam>/<notations> 之前
    later = {'notehead', 'staff', 'beam', 'notations', 'lyric', 'play', 'listen'}
    index = len(note)
    for position, node in enumerate(note):
        if _tag(node) in later:
            index = position
            break
    note.insert(index, stem)


def _voice_directions(notes, middle):
    """按 SATB 习惯分配符干（按时长重叠分组）。

    组内最高音朝上、最低音朝下，中间的跟随较近的邻居；
    只有一个音且没有别的音同时响时，才退回按音区判断。
    """
    items = []
    for note in notes:
        if _child(note, 'rest') is not None:
            continue
        pitch = _pitch_midi(note)
        if pitch is None:
            continue
        items.append({'pitch': pitch, 'note': note})
    if not items:
        return []
    # 每个音的开始时刻/时长（在同一小节内按出现顺序累加）
    cursor = 0
    for item in items:
        note = item['note']
        item['onset'] = cursor
        try:
            length = int(float(_text(note, 'duration', '0') or 0))
        except (TypeError, ValueError):
            length = 0
        item['duration'] = max(1, length)
        if _child(note, 'chord') is None:
            cursor += item['duration']
        else:
            item['onset'] = max(0, cursor - item['duration'])

    result = []
    for item in items:
        start, end = item['onset'], item['onset'] + item['duration']
        # 与本音在时间上重叠的所有音（包括持续中的全音符）
        group = [other for other in items
                 if other['onset'] < end and start < other['onset'] + other['duration']]
        group.sort(key=lambda entry: entry['pitch'])
        total = len(group)
        index = group.index(item)
        if total == 1:
            direction = 'up' if item['pitch'] >= middle - 2 else 'down'
        elif index == total - 1:
            direction = 'up'
        elif index == 0:
            direction = 'down'
        else:
            lower_gap = item['pitch'] - group[index - 1]['pitch']
            upper_gap = group[index + 1]['pitch'] - item['pitch']
            direction = 'up' if upper_gap <= lower_gap else 'down'
        result.append((item['note'], direction))
    return result


NOTE_ORDER = [
    'grace', 'cue', 'chord', 'pitch', 'unpitched', 'rest', 'duration', 'tie',
    'instrument', 'footnote', 'level', 'voice', 'type', 'dot', 'accidental',
    'time-modification', 'stem', 'notehead', 'notehead-text', 'staff', 'beam',
    'notations', 'lyric', 'play', 'listen',
]
_ORDER_INDEX = {name: index for index, name in enumerate(NOTE_ORDER)}


def normalize_note_order(root):
    """把每个 <note> 的子元素按规范顺序排好（稳定排序）。"""
    changed = False
    for note in root.iter('note'):
        children = list(note)
        if not children:
            continue
        decorated = []
        for position, child in enumerate(children):
            name = _tag(child)
            rank = _ORDER_INDEX.get(name, len(NOTE_ORDER))
            decorated.append((rank, position, child))
        decorated.sort(key=lambda item: (item[0], item[1]))
        ordered = [item[2] for item in decorated]
        if ordered != children:
            for child in children:
                note.remove(child)
            for child in ordered:
                note.append(child)
            changed = True
    return changed


def apply_stem_rules(xml_path, out_path, mode='outward'):
    """给整份谱写上显式符干。成功返回输出路径。

    mode:
      'voices'  —— 按声部（SATB）：上半朝上、下半朝下，中间音跟最近邻居
      'outward' —— 朝外（逐音）：每个音按自己在中线以上/以下，分别朝上/朝下
      'staff'   —— 按声部：上面的谱表符干朝上、下面的朝下
      'rule'    —— 按中线：音在中线以上朝下、以下朝上（通用制谱规则）
      'up'      —— 一律朝上
    """
    if not xml_path or not os.path.isfile(xml_path):
        return ''
    try:
        tree = ET.parse(xml_path)
    except Exception:
        return ''
    root = tree.getroot()
    middles = _staff_middles(root)
    staff_set = set()
    for part in root.iter('part'):
        for note in part.iter('note'):
            staff_set.add(int(_text(note, 'staff', '1') or 1))
    changed = False
    for part in root.iter('part'):
        part_id = part.get('id') or ''
        table = middles.get(part_id) or {}
        for measure in part.findall('measure'):
            groups = {}
            order = []
            current_onset = 0
            for child in measure:
                tag = _tag(child)
                if tag != 'note':
                    if tag == 'backup':
                        try:
                            current_onset = max(
                                0, current_onset - int(float(
                                    _text(child, 'duration', '0') or 0)))
                        except (TypeError, ValueError):
                            pass
                    elif tag == 'forward':
                        try:
                            current_onset += int(float(
                                _text(child, 'duration', '0') or 0))
                        except (TypeError, ValueError):
                            pass
                    continue
                staff = _text(child, 'staff', '1') or '1'
                chord = _child(child, 'chord') is not None
                if not chord:
                    group = [child]
                    key = (staff, current_onset)
                    groups[key] = group
                    order.append(key)
                    try:
                        current_onset += int(float(
                            _text(child, 'duration', '0') or 0))
                    except (TypeError, ValueError):
                        pass
                else:
                    key = (staff, current_onset - int(float(
                        _text(child, 'duration', '0') or 0)))
                    group = groups.get(key)
                    if group is None:
                        group = [child]
                        groups[key] = group
                        order.append(key)
                    else:
                        group.append(child)
            for key in order:
                group = groups[key]
                staff = key[0]
                middle = table.get(staff) or table.get('1') or DEFAULT_MIDDLE
                pitches = [p for p in (_pitch_midi(n) for n in group)
                           if p is not None]
                if mode == 'voices':
                    for note, direction in _voice_directions(group, middle):
                        _insert_stem(note, direction)
                        changed = True
                    continue
                if mode == 'outward':
                    # 逐音判断：每个音看自己在中线以上还是以下
                    for note in group:
                        if _child(note, 'rest') is not None:
                            continue
                        own = _pitch_midi(note)
                        if own is None:
                            continue
                        _insert_stem(note, 'up' if own >= middle else 'down')
                        changed = True
                    continue
                if mode == 'up':
                    direction = 'up'
                elif mode == 'staff' and len(staff_set) >= 2:
                    # 上面的谱表朝上、下面的朝下
                    direction = 'up' if int(staff) <= min(staff_set) else 'down'
                else:
                    direction = _direction_for(pitches, middle)
                for note in group:
                    if _child(note, 'rest') is not None:
                        continue
                    _insert_stem(note, direction)
                    changed = True
    if mode == 'outward':
        # 逐音兜底：按每个音自己的音高重写一遍，确保一个都不漏。
        # 中线附近 2 个半音内算"靠上"，这样紧贴中线的音不会被判成朝下。
        for part in root.iter('part'):
            table = middles.get(part.get('id') or '') or {}
            for note in part.iter('note'):
                if _child(note, 'rest') is not None:
                    continue
                pitch = _pitch_midi(note)
                if pitch is None:
                    continue
                staff = _text(note, 'staff', '1') or '1'
                middle = table.get(staff) or table.get('1') or DEFAULT_MIDDLE
                _insert_stem(note, 'up' if pitch >= middle - 2 else 'down')
                changed = True
    if mode in ('voices', 'outward'):
        # 兜底：任何还没拿到符干的音，按音区补一个（分组时可能被覆盖）
        for part in root.iter('part'):
            table = middles.get(part.get('id') or '') or {}
            for note in part.iter('note'):
                if _child(note, 'rest') is not None:
                    continue
                if _child(note, 'stem') is not None:
                    continue
                pitch = _pitch_midi(note)
                if pitch is None:
                    continue
                staff = _text(note, 'staff', '1') or '1'
                middle = table.get(staff) or table.get('1') or DEFAULT_MIDDLE
                _insert_stem(note, 'up' if pitch >= middle - 2 else 'down')
                changed = True
    # 写盘前按规范重排元素顺序（voice 必须在 type 之前）
    normalize_note_order(root)
    if not changed:
        return ''
    try:
        body = ET.tostring(root, encoding='unicode')
        header = ('<?xml version="1.0" encoding="UTF-8"?>\n'
                  '<!DOCTYPE score-partwise PUBLIC "-//Recordare//DTD MusicXML 4.0 Partwise//EN" '
                  '"http://www.musicxml.org/dtds/partwise.dtd">\n')
        with open(out_path, 'w', encoding='utf-8') as handle:
            handle.write(header)
            handle.write(body)
        return out_path
    except Exception:
        return ''


if __name__ == '__main__':
    import sys
    if len(sys.argv) < 3:
        print('用法: python stem_rules.py <in.musicxml> <out.musicxml>')
        raise SystemExit(2)
    print('输出:', apply_stem_rules(sys.argv[1], sys.argv[2]) or '失败')
