# -*- coding: utf-8 -*-

import sys
import os
from music21 import converter


def musicxml_to_midi(xml_file, midi_file='output.mid'):
    if not os.path.exists(xml_file):
        print(f'错误：找不到文件 {xml_file}')
        return False
    try:
        score = converter.parse(xml_file)
        score.write('midi', midi_file)
        print(f'转换成功：{xml_file} → {midi_file}')
        return True
    except Exception as e:
        print(f'转换失败：{e}')
        # music21 出错时会留下 0 字节的 .mid 文件，留着会让 MIDI 列表里出现打不开的条目
        try:
            if os.path.exists(midi_file) and os.path.getsize(midi_file) == 0:
                os.remove(midi_file)
        except OSError:
            pass
        return False


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('用法: python score_to_midi.py <MusicXML或MXL文件> [输出MIDI文件]')
    else:
        xml_in = sys.argv[1]
        midi_out = sys.argv[2] if len(sys.argv) > 2 else 'output.mid'
        musicxml_to_midi(xml_in, midi_out)
