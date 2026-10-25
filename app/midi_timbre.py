# -*- coding: utf-8 -*-
"""MIDI 音色工具：改掉生成结果里的 GM 音色号。

由来：homr 把声部识别成 "Voice"，music21 据此写入 program 53（Voice Oohs），
听起来是"人声啊"，不是钢琴。试听时按用户选的音色覆盖一下即可。
"""
import mido

# GM 128 音色的中文名（0 基）
GM_NAMES = [
    '大钢琴', '明亮钢琴', '电钢琴', '酒吧电钢', '电钢琴2', '电钢琴3', '羽管键琴', '拨弦古钢',
    '钢片琴', '钟琴', '音乐盒', '颤音琴', '马林巴', '木琴', '管钟', '洋琴',
    '簧风琴', '打击风琴', '摇滚风琴', '教堂管风琴', '簧管风琴', '手风琴', '口琴', '探戈手风琴',
    '尼龙弦吉他', '钢丝弦吉他', '电吉他(爵士)', '电吉他(清音)', '闷音吉他', '过载吉他', '失真吉他', '吉他泛音',
    '原声贝斯', '电贝斯(指弹)', '电贝斯(拨片)', '无品贝斯', '击弦贝斯1', '击弦贝斯2', '合成贝斯1', '合成贝斯2',
    '小提琴', '中提琴', '大提琴', '低音提琴', '弦乐震音', '弦乐拨奏', '竖琴', '定音鼓',
    '弦乐合奏1', '弦乐合奏2', '合成弦乐1', '合成弦乐2', '人声合唱', '人声“啊”', '合成人声', '管弦乐齐奏',
    '小号', '长号', '大号', '弱音小号', '圆号', '铜管合奏', '合成铜管1', '合成铜管2',
    '高音萨克斯', '中音萨克斯', '次中音萨克斯', '上低音萨克斯', '双簧管', '英国管', '巴松管', '单簧管',
    '短笛', '长笛', '竖笛', '排箫', '吹瓶声', '尺八', '口哨', '陶笛',
    '方波主音', '锯齿波主音', '风琴主音', '簧管主音', '特色主音', '人声主音', '五度主音', '贝斯加主音',
    '方波铺底', '锯齿波铺底', '风琴铺底', '弦乐铺底', '人声铺底', '金属铺底', '合成铺底', '合成效果',
    '雨声', '音轨', '水晶', '大气', '明亮', '地精', '回声', '科幻',
    '西塔琴', '班卓琴', '三味线', '日本筝', '卡林巴', '风笛', '二胡', '笛子',
    '拨弦音色', '拨弦音色2', '竖琴音色', '定音鼓2', '弦乐合奏', '人声', '金属敲击', '木鱼',
    '吉他泛音2', '贝斯泛音', '弓弦音', '弓弦音2', '合成效果2', '合成效果3', '合成效果4', '枪声',
]

# 试听常用的一组（下拉框里先给这些，后面再给全部）
COMMON = [0, 1, 4, 6, 11, 16, 19, 21, 24, 25, 32, 40, 41, 42, 43, 48, 52, 56, 57, 60,
          64, 68, 71, 73, 75, 80, 81, 88]


def gm_label(program):
    """给下拉框用的「0 大钢琴」这种标签。"""
    program = max(0, min(127, int(program)))
    return f'{program} {GM_NAMES[program]}'


def force_program(midi_path, program=0):
    """把 MIDI 里所有通道的音色改成 program（0 = 大钢琴）。"""
    program = max(0, min(127, int(program)))
    try:
        midi = mido.MidiFile(midi_path)
    except Exception:
        return False
    changed = False
    for track in midi.tracks:
        channels = sorted({msg.channel for msg in track
                           if hasattr(msg, 'channel')})
        if not channels:
            continue
        # 去掉已有的 program_change，在开头插入新的
        keep = [msg for msg in track if msg.type != 'program_change']
        head = [mido.Message('program_change', channel=ch, program=program, time=0)
                for ch in channels]
        track.clear()
        for msg in head + keep:
            track.append(msg)
        changed = True
    if not changed:
        # 没有通道信息：至少给通道 0 设一个
        track = mido.MidiTrack()
        track.append(mido.Message('program_change', channel=0, program=program, time=0))
        midi.tracks.insert(1, track)
    try:
        midi.save(midi_path)
        return True
    except Exception:
        return False


def programs_in(midi_path):
    """看看这个 MIDI 实际用了哪些音色（调试用）。"""
    out = []
    try:
        midi = mido.MidiFile(midi_path)
    except Exception:
        return out
    for track in midi.tracks:
        for msg in track:
            if msg.type == 'program_change':
                out.append((msg.channel, msg.program))
    return out
