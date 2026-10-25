# -*- coding: utf-8 -*-
"""按「从高到低交替」规则重建双声部。

规则（用户定义）：
  同一时刻、整个系统里所有在响的音，从高到低排序
    第 1 高 → 朝上
    第 2 高 → 朝下
    第 3 高 → 朝上
    第 4 高 → 朝下 ……
  只有一个音时：高音谱默认朝上、低音谱默认朝下。

实现：把每个音按排序奇偶分到 voice 1（朝上）/ voice 2（朝下），
再按小节时间轴分别输出两个声部（中间用 <backup> 回到小节开头）。
"""
import copy
import os
import xml.etree.ElementTree as ET

NOTE = 'note'
REST = 'rest'
GRACE = 'grace'
CHORD = 'chord'
DURATION = 'duration'
BACKUP = 'backup'
FORWARD = 'forward'
VOICE = 'voice'
STAFF = 'staff'
PITCH = 'pitch'
STEM = 'stem'
BEAM = 'beam'
ATTRIBUTES = 'attributes'

NOTE_NAMES = {'C': 0, 'D': 2, 'E': 4, 'F': 5, 'G': 7, 'A': 9, 'B': 11}

ORDER = [
    'grace', 'cue', 'chord', 'pitch', 'unpitched', 'rest', 'duration', 'tie',
    'instrument', 'footnote', 'level', 'voice', 'type', 'dot', 'accidental',
    'time-modification', 'stem', 'notehead', 'notehead-text', 'staff', 'beam',
    'notations', 'lyric', 'play', 'listen',
]
_ORDER_INDEX = {name: index for index, name in enumerate(ORDER)}


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


def _int_duration(element, default=0):
    try:
        return int(float(_text(element, DURATION, '0') or 0))
    except (TypeError, ValueError):
        return default


def _pitch_of(note):
    pitch = _child(note, PITCH)
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
    return octave * 12 + NOTE_NAMES.get(step, 0) + alter


def _set(element, name, text):
    node = _child(element, name)
    if node is None:
        node = ET.Element(name)
        element.append(node)
    node.text = text


def _reorder(note):
    children = list(note)
    decorated = [(_ORDER_INDEX.get(_tag(child), len(ORDER)), position, child)
                 for position, child in enumerate(children)]
    decorated.sort(key=lambda item: (item[0], item[1]))
    ordered = [item[2] for item in decorated]
    if ordered == children:
        return
    for child in children:
        note.remove(child)
    for child in ordered:
        note.append(child)


def _collect(measure):
    items = []
    cursor = 0
    previous_start = 0
    for child in measure:
        tag = _tag(child)
        if tag == NOTE:
            grace = _child(child, GRACE) is not None
            chord = _child(child, CHORD) is not None
            length = _int_duration(child)
            if chord:
                start = previous_start
            else:
                start = cursor
                previous_start = cursor
                if not grace:
                    cursor += length
            items.append({
                'element': child,
                'staff': int(_text(child, STAFF, '1') or 1),
                'onset': start,
                'duration': 0 if grace else max(1, length),
                'pitch': _pitch_of(child),
                'rest': _child(child, REST) is not None,
            })
        elif tag == BACKUP:
            cursor = max(0, cursor - _int_duration(child))
        elif tag == FORWARD:
            cursor += _int_duration(child)
    return items


def _assign(items):
    """按「从高到低交替」分配声部：1 高 → voice1，2 高 → voice2 …"""
    pitched = [item for item in items if item['pitch'] is not None and not item['rest']]
    for item in items:
        item['voice'] = None
    for item in pitched:
        start = item['onset']
        end = start + item['duration']
        sounding = [other for other in pitched
                    if other['onset'] < end and start < other['onset'] + other['duration']]
        sounding.sort(key=lambda entry: (-entry['pitch'], entry['onset'], entry['staff']))
        if len(sounding) == 1:
            item['voice'] = 1 if item['staff'] == 1 else 2
            continue
        index = sounding.index(item)
        item['voice'] = 1 if index % 2 == 0 else 2


def rebuild_measure(measure):
    items = _collect(measure)
    pitched = [item for item in items if item['pitch'] is not None and not item['rest']]
    if not pitched:
        return False
    _assign(items)
    staves = sorted({item['staff'] for item in items if item['voice'] is not None})

    others = [copy.deepcopy(child) for child in measure
              if _tag(child) not in (NOTE, BACKUP, FORWARD)]
    for child in list(measure):
        measure.remove(child)
    head = [node for node in others
            if _tag(node) in (ATTRIBUTES, 'print', 'direction', 'sound')]
    tail = [node for node in others if node not in head]
    for node in head:
        measure.append(node)

    length = max((item['onset'] + item['duration'] for item in items), default=1)

    groups = []
    for staff in staves:
        for voice in (1, 2):
            group = [item for item in pitched
                     if item['staff'] == staff and item['voice'] == voice]
            if group:
                groups.append(sorted(group, key=lambda entry: entry['onset']))

    for index, group in enumerate(groups):
        cursor = 0
        for item in group:
            if item['onset'] > cursor:
                forward = ET.SubElement(measure, FORWARD)
                ET.SubElement(forward, DURATION).text = str(item['onset'] - cursor)
                cursor = item['onset']
            note = copy.deepcopy(item['element'])
            for node in list(note):
                if _tag(node) in (CHORD, VOICE, STEM, BEAM):
                    note.remove(node)
            voice = item['voice']
            _set(note, VOICE, str(voice))
            _set(note, STEM, 'up' if voice == 1 else 'down')
            _reorder(note)
            measure.append(note)
            cursor = item['onset'] + item['duration']
        if index != len(groups) - 1 and cursor > 0:
            back = ET.SubElement(measure, BACKUP)
            ET.SubElement(back, DURATION).text = str(cursor)

    for node in tail:
        measure.append(node)
    return True


def rebuild_file(xml_path, out_path):
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
            if rebuild_measure(measure):
                changed = True
        except Exception:
            continue
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
