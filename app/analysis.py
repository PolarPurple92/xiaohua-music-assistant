# -*- coding: utf-8 -*-
"""把 MusicXML 拆成结构化的「事實」——纯计算，不联网、不调 AI、不依赖界面。

为什么不直接分析 MIDI：MIDI 丢了调号拼写、声部归属、连音线、保留音，
而这些恰恰是讲解时要说的东西。MusicXML 才有。

产出（brief）大致长这样：
    {
      'title': 'cap_20261019_182934',
      'measures': 5,
      'key': {'label': 'C 大调', ...},
      'time_signature': '4/4',
      'tempo': 120.0,
      'duration': 6.0,
      'measure_list': [
          {'number': 1, 'start': 0.0, 'end': 2.0,
           'chords': [{'symbol': 'C', 'roman': 'I', 'beat': 1.0}, ...],
           'notes': 4, 'range': ['G3', 'G5'], 'voices': 2,
           'features': ['七和弦', '转位']},
          ...
      ],
      'cadences': [{'measure': 4, 'type': 'authentic', 'label': '正格终止（V→I）'}],
      'warnings': ['分析基于自动识别，可能有个别错音'],
    }

约定：能算的就算准，算不准的宁可标「疑似」也不编。
"""
import logging
import os
import re
import warnings

# music21 导入时会抱怨没装 matplotlib（它只用于绘图，我们用不到），压掉免得日志脏
warnings.filterwarnings('ignore', message=r'.*(matplotlib|optional package).*')
logging.getLogger('music21').setLevel(logging.ERROR)

CADENCE_LABELS = {
    'authentic': '正格终止（V→I）',
    'half': '半终止（停在属和弦）',
    'plagal': '变格终止（IV→I）',
    'deceptive': '阻碍终止（V→vi）',
    'none': '',
}

ROMAN_QUALITY_HINTS = (
    ('dim', '减三和弦'),
    ('aug', '增三和弦'),
    ('M7', '大七和弦'),
    ('m7', '小七和弦'),
    ('7', '七和弦'),
)


def _safe(callable_, default=None):
    try:
        return callable_()
    except Exception:
        return default


def _key_label(key_obj):
    if key_obj is None:
        return ''
    tonic = _safe(lambda: key_obj.tonic.name, '') or ''
    mode = _safe(lambda: key_obj.mode, '') or ''
    mode_cn = {'major': '大调', 'minor': '小调'}.get(mode, mode)
    return f'{tonic} {mode_cn}'.strip()


def _parse(path):
    from music21 import converter
    return converter.parse(path)


def _first_key(score):
    """优先取谱面写明的调号，没有才用算法猜。"""
    from music21 import key as m21key
    for part in score.parts:
        for sig in part.recurse().getElementsByClass(m21key.KeySignature):
            return sig.asKey()
    guess = _safe(lambda: score.analyze('key'))
    return guess


def _first_time_signature(score):
    from music21 import meter
    for part in score.parts:
        for sig in part.recurse().getElementsByClass(meter.TimeSignature):
            return sig
    return None


def _tempo_bpm(score):
    from music21 import tempo
    for mark in score.recurse().getElementsByClass(tempo.MetronomeMark):
        bpm = _safe(lambda: float(mark.number))
        if bpm:
            return bpm, 'score'
    return 120.0, 'default'


def _part_measures(score, part_index=0):
    """取第一个声部的小节列表（保持顺序，不按编号索引）。

    OMR 出来的 MusicXML 常有重复编号（弱起小节也编成 1），所以后面一律
    用「第几个」定位，编号只用于显示。
    """
    try:
        part = score.parts[part_index]
    except Exception:
        return []
    return list(part.getElementsByClass('Measure'))


def _measure_span(measure, index):
    length = _safe(lambda: float(measure.duration.quarterLength), 0.0)
    start = _safe(lambda: float(measure.offset), 0.0)
    source_number = _safe(lambda: int(measure.number), index + 1)
    return {
        'index': index,
        'number': index + 1,             # 统一编号，界面上不会出现两个「第1小节」
        'source_number': source_number,  # 文件里原本的编号，排查问题时用
        'start_ql': start,
        'length_ql': length,
    }


def _chord_symbol(chord_object):
    """和弦符号：C / Cm / G7 / G/B。

    music21 的 chordSymbolFigureFromChord 遇到「带八度重复的三和弦」会直接
    拒绝识别（返回 'Chord Symbol Cannot Be Identified'），所以这里用
    root + quality 自己拼，顺带把转位写成 C/E 这种形式。
    """
    root = _safe(lambda: chord_object.root())
    if root is None:
        return ''
    quality = _safe(lambda: chord_object.quality, '') or ''
    suffix = {
        'major': '', 'minor': 'm', 'diminished': 'dim', 'augmented': 'aug',
        'dominant-seventh': '7', 'major-seventh': 'maj7', 'minor-seventh': 'm7',
        'half-diminished': 'm7b5', 'diminished-seventh': 'dim7',
        'minor-major-seventh': 'mMaj7', 'augmented-seventh': 'aug7',
    }.get(quality, '')
    symbol = f'{root.name}{suffix}'
    bass = _safe(lambda: chord_object.bass())
    if bass is not None and bass.name != root.name:
        symbol += f'/{bass.name}'
    return symbol


def _roman_figure(chord_object, key_obj):
    from music21 import roman
    if key_obj is None:
        return ''
    # 注意：RomanNumeral(pitches, key) 在 music21 9 里不接受音高列表，
    # 要用 romanNumeralFromChord(chord, key)
    figure = _safe(lambda: roman.romanNumeralFromChord(chord_object, key_obj).figure)
    return figure or ''


def _pitch_class_count(chord_object):
    return len({pitch.name for pitch in chord_object.pitches})


def _analyse_measure_chords(chordified_measures, index, key_obj):
    """小节内的和声：按出现顺序，给出符号、级数、所在拍。"""
    from music21 import chord as m21chord
    result = []
    if index >= len(chordified_measures):
        return result
    target = chordified_measures[index]
    base = _safe(lambda: float(target.offset), 0.0)
    for chord in target.getElementsByClass(m21chord.Chord):
        if not chord.pitches:
            continue
        beat = round(float(_safe(lambda: chord.offset, base) or base) - base + 1, 2)
        result.append({
            'beat': max(1.0, beat),
            'symbol': _chord_symbol(chord),
            'roman': _roman_figure(chord, key_obj),
            'pitches': _pitch_class_count(chord),
        })
    return result


def _measure_texture(score, index):
    """音域 / 声部数 / 音符数——直接从原始声部统计，比 chordify 更贴近谱面。"""
    from music21 import chord as m21chord
    from music21 import note as m21note
    from music21 import stream as m21stream
    pitches, voices, count = [], set(), 0
    for part in score.parts:
        measures = list(part.getElementsByClass('Measure'))
        if index >= len(measures):
            continue
        measure = measures[index]
        for voice in measure.getElementsByClass(m21stream.Voice):
            voices.add(_safe(lambda: int(voice.id), 0) or len(voices) + 1)
        for element in measure.recurse():
            if isinstance(element, m21note.Note) and element.pitch is not None:
                pitches.append(element.pitch)
                count += 1
            elif isinstance(element, m21chord.Chord):
                pitches.extend(element.pitches)
                count += 1
    low = min(pitches).nameWithOctave if pitches else ''
    high = max(pitches).nameWithOctave if pitches else ''
    return {
        'notes': count,
        'range': [low, high],
        'voices': len(voices) or 1,
    }


ROMAN_DEGREES = ('VII', 'VI', 'V', 'IV', 'III', 'II', 'I')


def _degree(figure):
    """从罗马数字里取出「级数」（去掉升降号和后缀）。

    注意不能直接取首字母：'IV'[0] 是 'I'，会把下属和弦当成主和弦。
    """
    text = (figure or '').lstrip('#b').upper()
    for degree in ROMAN_DEGREES:
        if text.startswith(degree):
            return degree
    return ''


def _detect_cadences(measure_list):
    """按小节边界判断终止式。只认「强特征」，其余一律不写。"""
    out = []
    if not measure_list:
        return out
    for index in range(len(measure_list) - 1):
        if index == 0:
            continue          # 弱起小节后面那一下不算终止式
        current = measure_list[index]
        following = measure_list[index + 1]
        if not current['chords'] or not following['chords']:
            continue
        last = current['chords'][-1]['roman']
        first = following['chords'][0]['roman']
        last_degree = _degree(last)
        first_degree = _degree(first)
        if not last_degree or not first_degree:
            continue
        cadence = None
        if last_degree == 'V' and first_degree == 'I':
            cadence = 'authentic'
        elif last_degree == 'V' and first_degree == 'VI':
            cadence = 'deceptive'
        elif last_degree == 'V':
            cadence = 'half'
        elif last_degree == 'IV' and first_degree == 'I':
            cadence = 'plagal'
        if cadence:
            out.append({'measure': current['number'], 'type': cadence,
                        'label': CADENCE_LABELS.get(cadence, ''),
                        'from': last, 'to': first})
    return out


def _measure_features(chords):
    features = []
    if not chords:
        return features
    if any(entry['pitches'] >= 4 for entry in chords):
        features.append('七和弦')
    romans = [entry['roman'] for entry in chords if entry['roman']]
    if any(figure.endswith('7') for figure in romans) and '七和弦' not in features:
        features.append('七和弦')
    if any(entry['symbol'] and '/' in entry['symbol'] for entry in chords):
        features.append('转位')
    if any(figure.startswith(('vii', 'ii')) and figure.endswith(('o', '°', 'ø', '7'))
           for figure in romans):
        features.append('减和弦')
    if len(set(romans)) == 1 and len(romans) >= 2 and romans[0]:
        features.append('同和弦持续')
    if any(figure.startswith('V') for figure in romans) and \
            any(figure.startswith('I') for figure in romans):
        features.append('属到主')
    return features


def analyze(xml_path, title=None):
    """把 MusicXML 变成 brief。失败抛异常，由调用方决定怎么提示。"""
    score = _parse(xml_path)
    key_obj = _first_key(score)
    time_sig = _first_time_signature(score)
    time_sig_text = _safe(lambda: time_sig.ratioString, '') or ''
    bpm, tempo_source = _tempo_bpm(score)
    seconds_per_quarter = 60.0 / bpm if bpm else 0.5

    spans = [_measure_span(measure, index)
             for index, measure in enumerate(_part_measures(score))]
    spans = [span for span in spans if span['length_ql'] > 0]
    chordified = _safe(lambda: score.chordify())
    chord_measures = list(chordified.getElementsByClass('Measure')) if chordified else []

    measure_list = []
    for span in spans:
        number = span['number']
        index = span['index']
        chords = _analyse_measure_chords(chord_measures, index, key_obj) if chord_measures else []
        texture = _measure_texture(score, index)
        entry = {
            'number': number,
            'source_number': span['source_number'],
            'start': round(span['start_ql'] * seconds_per_quarter, 3),
            'end': round((span['start_ql'] + span['length_ql']) * seconds_per_quarter, 3),
            'beats': round(span['length_ql'], 2),
            'chords': chords,
            'notes': texture['notes'],
            'range': texture['range'],
            'voices': texture['voices'],
        }
        entry['features'] = _measure_features(chords)
        measure_list.append(entry)

    cadences = _detect_cadences(measure_list)
    for cadence in cadences:
        for entry in measure_list:
            if entry['number'] == cadence['measure']:
                entry['features'] = entry['features'] + [cadence['label']]
                break

    duration = measure_list[-1]['end'] if measure_list else 0.0
    warnings = []
    if measure_list and not any(entry['chords'] for entry in measure_list):
        warnings.append('没能从谱面提取出和声（可能是单旋律或识别质量不足）')
    if key_obj is None:
        warnings.append('没能确定调性')
    warnings.append('分析基于自动识别结果，可能有错音')

    return {
        'source': os.path.abspath(xml_path),
        'title': title or os.path.splitext(os.path.basename(xml_path))[0],
        'measures': len(measure_list),
        'key': {
            'label': _key_label(key_obj),
            'tonic': _safe(lambda: key_obj.tonic.name, '') if key_obj else '',
            'mode': _safe(lambda: key_obj.mode, '') if key_obj else '',
        },
        'time_signature': time_sig_text,
        'tempo': round(bpm, 1),
        'tempo_source': tempo_source,
        'duration': round(duration, 3),
        'parts': len(score.parts),
        'measure_list': measure_list,
        'cadences': cadences,
        'warnings': warnings,
    }


def summarize(brief):
    """一句话总览，给面板头部用。"""
    if not brief:
        return ''
    bits = []
    if brief.get('key', {}).get('label'):
        bits.append(brief['key']['label'])
    if brief.get('time_signature'):
        bits.append(brief['time_signature'])
    if brief.get('measures'):
        bits.append(f'{brief["measures"]} 小节')
    if brief.get('duration'):
        bits.append(f'{brief["duration"]:.1f}s')
    summary = ' · '.join(bits)
    cadences = brief.get('cadences') or []
    if cadences:
        names = '、'.join(sorted({entry['label'] for entry in cadences}))
        summary += f'｜{names}'
    return summary


def measure_at(brief, seconds):
    """当前时刻落在第几小节（播放同步用）。落在空隙里就归前一小节。"""
    if not brief:
        return None
    measures = brief.get('measure_list') or []
    if not measures:
        return None
    for entry in measures:
        if entry['start'] <= seconds < entry['end']:
            return entry['number']
    previous = measures[0]['number']
    for entry in measures:
        if seconds >= entry['end']:
            previous = entry['number']
        else:
            break
    return previous


def phrase_groups(brief):
    """按终止式把小节分成乐句（没有终止式就整首一句）。"""
    measures = (brief or {}).get('measure_list') or []
    if not measures:
        return []
    boundaries = {entry['measure'] for entry in (brief.get('cadences') or [])}
    groups, current = [], []
    for entry in measures:
        current.append(entry['number'])
        if entry['number'] in boundaries:
            groups.append(current)
            current = []
    if current:
        groups.append(current)
    return groups


_SAFE_NAME = re.compile(r'[\\/:*?"<>|]')


def cache_path(xml_path, cache_dir):
    stem = os.path.splitext(os.path.basename(xml_path))[0]
    return os.path.join(cache_dir, _SAFE_NAME.sub('_', stem) + '.brief.json')


def load_brief(xml_path, cache_dir=None):
    """带磁盘缓存的分析：XML 没变就直接读 JSON。"""
    import json
    if not cache_dir:
        return analyze(xml_path)
    path = cache_path(xml_path, cache_dir)
    try:
        if os.path.isfile(path) and os.path.getmtime(path) >= os.path.getmtime(xml_path):
            with open(path, encoding='utf-8') as fp:
                return json.load(fp)
    except Exception:
        pass
    brief = analyze(xml_path)
    try:
        os.makedirs(cache_dir, exist_ok=True)
        with open(path, 'w', encoding='utf-8') as fp:
            json.dump(brief, fp, ensure_ascii=False, indent=2)
    except Exception:
        pass
    return brief
