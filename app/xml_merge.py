# -*- coding: utf-8 -*-
"""把 MusicXML 里的多声部合并成单声部（和弦）。

为什么要做：homr 会把同时发声的音拆进 voice 1/2/3/5/6，MuseScore 按声部
决定符干方向（1 声部朝上、2 声部朝下），画出来符干乱七八糟。
合并成"一张谱表一个声部、同时发声的和弦"之后，MuseScore 会自动按标准
规则定符干（符头在中线以下朝上，以上朝下）。

做法（在 XML 层，保住谱表归属）：
  · 逐小节读出每个 <note> 的时刻（<note> 推进、<chord/> 不推进、
    <backup>/<forward> 加减）
  · 按 (谱表, 时刻) 分组：第一个音保留，其余加 <chord/>
  · 每个谱表按时间顺序重排，空隙补 <forward>
  · 谱表之间用一个 <backup> 回到小节开头
  · 所有音统一标成 voice 1

只用标准库，不引入 lxml 之类的依赖。
"""
import copy
import os
import xml.etree.ElementTree as ET

NOTE = 'note'
CHORD = 'chord'
REST = 'rest'
GRACE = 'grace'
DURATION = 'duration'
BACKUP = 'backup'
FORWARD = 'forward'
VOICE = 'voice'
STAFF = 'staff'
ATTRIBUTES = 'attributes'
TYPE = 'type'
PITCH = 'pitch'

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


def _duration(element, default=0):
    try:
        return int(float(_text(element, DURATION, '0') or 0))
    except (TypeError, ValueError):
        return default


def _staff_of(note):
    try:
        return int(_text(note, STAFF, '1') or 1)
    except (TypeError, ValueError):
        return 1


def _pitch_key(note):
    pitch = _child(note, PITCH)
    if pitch is None:
        return 0
    step = _text(pitch, 'step', 'C')
    try:
        octave = int(_text(pitch, 'octave', '4'))
    except (TypeError, ValueError):
        octave = 4
    try:
        alter = int(float(_text(pitch, 'alter', '0') or 0))
    except (TypeError, ValueError):
        alter = 0
    return octave * 12 + NOTE_NAMES.get(step, 0) + alter


def _collect(measure):
    """读出这一小节里所有音/休止符及其时刻。"""
    items = []
    cursor = 0
    previous_start = 0     # 上一个「非和弦」音的起点，供 <chord/> 复用
    for child in measure:
        tag = _tag(child)
        if tag == NOTE:
            grace = _child(child, GRACE) is not None
            chord = _child(child, CHORD) is not None
            length = _duration(child)
            if chord:
                start = previous_start
            else:
                start = cursor
                previous_start = cursor
                if not grace:
                    cursor += length
            items.append({
                'element': child,
                'staff': _staff_of(child),
                'onset': start,
                'duration': 0 if grace else length,
                'grace': grace,
                'rest': _child(child, REST) is not None,
            })
        elif tag == BACKUP:
            cursor = max(0, cursor - _duration(child))
        elif tag == FORWARD:
            cursor += _duration(child)
    return items, cursor


def _force_voice_one(note):
    for node in list(note):
        if _tag(node) == VOICE:
            note.remove(node)
    voice = ET.Element(VOICE)
    voice.text = '1'
    index = len(note)
    for position, node in enumerate(note):
        if _tag(node) == TYPE:
            index = position
            break
    note.insert(index, voice)


def merge_measure(measure):
    """把一个小节合并成单声部；返回是否有改动。"""
    # 有连音符（三连音等）的小节不合并：时值换算复杂，容易把节奏改坏
    if any(_tag(node) == 'time-modification' for node in measure.iter()):
        return False
    items, total = _collect(measure)
    if not items:
        return False
    staves = sorted({item['staff'] for item in items})
    voices = {(_text(item['element'], VOICE, '1') or '1') for item in items}
    has_backup = any(_tag(child) in (BACKUP, FORWARD) for child in measure)
    has_chord = any(_tag(child) == NOTE and _child(child, CHORD) is not None
                    for child in measure)
    if len(staves) <= 1 and len(voices) <= 1 and not has_backup and not has_chord:
        return False

    per_staff = {staff: {} for staff in staves}
    for item in items:
        slot = per_staff[item['staff']].setdefault(
            item['onset'], {'notes': [], 'rests': []})
        (slot['rests'] if item['rest'] else slot['notes']).append(item)

    others = [copy.deepcopy(child) for child in measure
              if _tag(child) not in (NOTE, BACKUP, FORWARD)]

    for child in list(measure):
        measure.remove(child)

    head = [node for node in others
            if _tag(node) in (ATTRIBUTES, 'print', 'direction', 'sound')]
    tail = [node for node in others if node not in head]
    for node in head:
        measure.append(node)

    for index, staff in enumerate(staves):
        cursor = 0
        slots = per_staff[staff]
        for onset in sorted(slots):
            slot = slots[onset]
            notes = slot['notes']
            rests = slot['rests']
            if not notes and not rests:
                continue
            if onset > cursor:
                forward = ET.SubElement(measure, FORWARD)
                ET.SubElement(forward, DURATION).text = str(onset - cursor)
                cursor = onset
            if notes:
                notes.sort(key=lambda item: _pitch_key(item['element']))
                # 和弦各音的时值必须一致：MusicXML 只按第一个音推进时间，
                # 若各成员时值不同，后续小节会整体漂移
                span = max(item['duration'] for item in notes)
                first = True
                for item in notes:
                    note = copy.deepcopy(item['element'])
                    for node in list(note):
                        if _tag(node) in (CHORD, VOICE):
                            note.remove(node)
                    duration_node = _child(note, DURATION)
                    if duration_node is not None:
                        duration_node.text = str(span)
                    if not first:
                        note.insert(0, ET.Element(CHORD))
                    _force_voice_one(note)
                    measure.append(note)
                    first = False
            else:
                rest = rests[0]
                note = copy.deepcopy(rest['element'])
                for node in list(note):
                    if _tag(node) == CHORD:
                        note.remove(node)
                _force_voice_one(note)
                measure.append(note)
                span = rest['duration']
            cursor = max(cursor, onset + span)
        if index != len(staves) - 1 and cursor > 0:
            back = ET.SubElement(measure, BACKUP)
            ET.SubElement(back, DURATION).text = str(cursor)

    for node in tail:
        measure.append(node)
    return True


def _events(xml_path):
    """整份谱的 (小节号, 时刻, 音高, 时值) 清单，用来核对合并有没有改坏。"""
    try:
        tree = ET.parse(xml_path)
    except Exception:
        return None
    events = []
    try:
        for index, measure in enumerate(tree.getroot().iter('measure')):
            items, _total = _collect(measure)
            for item in items:
                if item['rest']:
                    continue
                events.append((index, item['onset'],
                               _pitch_key(item['element']), item['duration']))
    except Exception:
        return None
    return sorted(events)


def verify_merge(original_path, merged_path):
    """合并前后逐音比对：完全一致才算成功。"""
    before = _events(original_path)
    after = _events(merged_path)
    if before is None or after is None:
        return False
    if len(before) != len(after):
        return False
    for left, right in zip(before, after):
        if left[0] != right[0] or left[2] != right[2]:
            return False
        if abs(left[1] - right[1]) > 0:
            return False
    return True


def _measure_events(measure):
    """某一小节的 (时刻, 音高) 清单，用于逐节校验。"""
    items, _total = _collect(measure)
    events = []
    for item in items:
        if item['rest']:
            continue
        # 只比时刻和音高：和弦合并会统一成员时值，时值不参与校验
        events.append((item['onset'], _pitch_key(item['element'])))
    return sorted(events)


def _restore_measure(measure, backup):
    """把备份内容写回原 measure 元素（保持同一对象引用）。"""
    for child in list(measure):
        measure.remove(child)
    for child in list(backup):
        measure.append(copy.deepcopy(child))


def merge_voices(xml_path, out_path):
    """把整份 MusicXML 的多声部合并。成功返回输出路径，失败返回 ''。"""
    if not xml_path or not os.path.isfile(xml_path):
        return ''
    try:
        tree = ET.parse(xml_path)
    except Exception:
        return ''
    root = tree.getroot()
    changed = False
    for measure in root.iter('measure'):
        try:
            before = copy.deepcopy(measure)
            before_events = _measure_events(before)
            if not merge_measure(measure):
                continue
            after_events = _measure_events(measure)
            if before_events != after_events:
                # 这一小节合坏了：还原
                _restore_measure(measure, before)
                continue
            changed = True
        except Exception:
            continue
    if not changed:
        return ''
    try:
        body = ET.tostring(root, encoding='unicode')
    except Exception:
        return ''
    header = ('<?xml version="1.0" encoding="UTF-8"?>\n'
              '<!DOCTYPE score-partwise PUBLIC "-//Recordare//DTD MusicXML 4.0 Partwise//EN" '
              '"http://www.musicxml.org/dtds/partwise.dtd">\n')
    try:
        with open(out_path, 'w', encoding='utf-8') as handle:
            handle.write(header)
            handle.write(body)
    except Exception:
        return ''
    # 自检：合并前后每个音的音高、时刻都要对得上，否则说明改坏了
    if not verify_merge(xml_path, out_path):
        try:
            os.remove(out_path)
        except OSError:
            pass
        return ''
    return out_path


if __name__ == '__main__':
    import sys
    if len(sys.argv) < 3:
        print('用法: python xml_merge.py <in.musicxml> <out.musicxml>')
        raise SystemExit(2)
    print('输出:', merge_voices(sys.argv[1], sys.argv[2]) or '没有改动/失败')
