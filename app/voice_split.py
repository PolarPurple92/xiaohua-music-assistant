# -*- coding: utf-8 -*-
"""声部归并（保守版）：不改时间轴，只重新标声部号 + 写符干。

原理：原文件里用 <backup> 把不同声部分开，每个 backup 后的那段音属于同一个声部。
我们按「段」为单位判断：同一时刻重叠的几段，平均音高高的那段 → voice 1（朝上），
低的 → voice 2（朝下）。时间轴、backup 数量、音符顺序全部保持原样，
所以不会像上一版那样把版面搞乱。
"""
import os
import xml.etree.ElementTree as ET

NOTE = 'note'
REST = 'rest'
GRACE = 'grace'
DURATION = 'duration'
BACKUP = 'backup'
FORWARD = 'forward'
VOICE = 'voice'
STEM = 'stem'
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


def segments(measure):
    """把小节按 <backup> 切成若干段，返回 [{notes, span}]。"""
    result = []
    current = []
    cursor = 0
    start = 0
    for child in measure:
        tag = _tag(child)
        if tag == BACKUP:
            if current:
                result.append({'notes': current, 'start': start, 'end': cursor})
            current = []
            cursor = max(0, cursor - _duration(child))
            start = cursor
        elif tag == FORWARD:
            cursor += _duration(child)
        elif tag == NOTE:
            current.append(child)
            if _child(child, GRACE) is None and _child(child, 'chord') is None:
                cursor += _duration(child)
    if current:
        result.append({'notes': current, 'start': start, 'end': cursor})
    return result


def merge_to_two(measure):
    parts = segments(measure)
    if len(parts) < 2:
        return False
    for part in parts:
        pitches = []
        for note in part['notes']:
            if _child(note, REST) is not None:
                continue
            pitch = _pitch_of(note)
            if pitch is not None:
                pitches.append(pitch)
        part['mean'] = sum(pitches) / len(pitches) if pitches else None

    ranked = sorted([part for part in parts if part['mean'] is not None],
                    key=lambda entry: -entry['mean'])
    if len(ranked) < 2:
        return False
    half = max(1, len(ranked) // 2)
    upper = set(id(part) for part in ranked[:half])
    lower = set(id(part) for part in ranked[half:])
    if not lower:                       # 只有一段高的，剩下的都算低声部
        lower = set(id(ranked[-1]))
        upper.discard(id(ranked[-1]))

    changed = False
    for part in parts:
        if part['mean'] is None:
            continue
        number = 1 if id(part) in upper else 2
        for note in part['notes']:
            if _child(note, REST) is not None:
                continue
            _set(note, VOICE, str(number))
            _set(note, STEM, 'up' if number == 1 else 'down')
            changed = True
    return changed


def merge_file(xml_path, out_path):
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
            if merge_to_two(measure):
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
