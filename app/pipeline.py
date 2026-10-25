# -*- coding: utf-8 -*-
"""统一的识别流水线：图片 → MusicXML → MIDI。

旧版把这段逻辑在完整模式和极简模式里各写了一份，命名去重、自动渲染、音量速度
传递都不一致。这里只留一份，两个界面都调它。

本模块不依赖 tkinter，回调 `report` 只收字符串，由调用方决定怎么显示。
"""
import os
import shutil

from settings import MIDI_DIR, XML_DIR

# 重活(导入 cv2/music21)全部延迟到真正调用时，避免拖慢启动
_recognizer = None
_converter = None


def _recognize():
    global _recognizer
    if _recognizer is None:
        from omr_recognizer import recognize
        _recognizer = recognize
    return _recognizer


def _musicxml_to_midi():
    global _converter
    if _converter is None:
        from score_to_midi import musicxml_to_midi
        _converter = musicxml_to_midi
    return _converter


def unique_dest(directory, filename):
    """同名文件自动加 _1、_2 序号，绝不覆盖已有结果。"""
    base, ext = os.path.splitext(filename)
    candidate = os.path.join(directory, filename)
    index = 1
    while os.path.exists(candidate):
        candidate = os.path.join(directory, f'{base}_{index}{ext}')
        index += 1
    return candidate


ENGINE_TAGS = ('homr', 'audiveris')
# 预处理图叫 <stem>_pre.png，Audiveris 按输入名导出，于是会带出 _pre，去掉它
NOISE_TAGS = ('pre',) + ENGINE_TAGS


def engine_tag(engine):
    return (engine or 'audiveris').strip().lower()


def _strip_engine_tag(stem):
    """把名字末尾的 _homr / _audiveris / _pre 去掉，避免重复叠加。"""
    lowered = stem.lower()
    for tag in NOISE_TAGS:
        if lowered.endswith('_' + tag):
            return stem[:-(len(tag) + 1)]
    return stem


def base_stem(name):
    """从文件名/路径里取出「源图名」：去掉扩展名和各种后缀。

    输出文件叫 cap_x_homr.mid，但它对应的封面是 cap_x.png —— 播放条找封面靠这个。
    """
    return _strip_engine_tag(os.path.splitext(os.path.basename(name))[0])


XML_SUFFIXES = ('.musicxml', '.mxl', '.xml')


def output_paths(base_stem_name, engine, ext='.musicxml'):
    """同源图 + 同引擎 → 固定的输出路径（重复识别覆盖，不再堆 _1.._6）。

    不同引擎带不同后缀，方便区分：cap_x_homr.musicxml / cap_x_audiveris.mxl。
    扩展名沿用识别器产出的格式：Audiveris 导出的是压缩的 .mxl，改成 .musicxml 会让解析失败。
    """
    ext = (ext or '.musicxml').lower()
    if ext not in XML_SUFFIXES:
        ext = '.musicxml'
    stem = f'{_strip_engine_tag(base_stem_name)}_{engine_tag(engine)}'
    return (os.path.join(XML_DIR, stem + ext),
            os.path.join(MIDI_DIR, stem + '.mid'))


def xml_for_midi(midi_path):
    """从 MIDI 反查同源的 MusicXML（讲解面板要用它做分析）。"""
    stem = base_stem(midi_path)
    for suffix in XML_SUFFIXES:
        candidate = os.path.join(XML_DIR, stem + suffix)
        if os.path.isfile(candidate):
            return candidate
    # 引擎后缀可能不一致（_homr / _audiveris / _pre），退一步模糊匹配
    lowered = stem.lower()
    try:
        for name in os.listdir(XML_DIR):
            if not name.lower().endswith(XML_SUFFIXES):
                continue
            if _strip_engine_tag(os.path.splitext(name)[0]).lower() == lowered:
                return os.path.join(XML_DIR, name)
    except OSError:
        pass
    return ''


def _replace_move(src, dest):
    """覆盖式移动：目标是派生文件，重跑就该更新，而不是无限加序号。"""
    folder = os.path.dirname(dest)
    if folder and not os.path.isdir(folder):
        os.makedirs(folder, exist_ok=True)
    if os.path.abspath(src) == os.path.abspath(dest):
        return
    if os.path.exists(dest):
        os.remove(dest)
    shutil.move(src, dest)


def process_image(image_path, config, report=None):
    """识别一张截图并转成 MIDI。

    返回 dict: {'xml': 路径或None, 'midi': 路径或None, 'error': 文案或None}
    """
    def say(message):
        if report is not None:
            report(message)

    result = {'xml': None, 'midi': None, 'error': None}
    if not os.path.isfile(image_path):
        result['error'] = f'找不到图片：{image_path}'
        return result

    say('正在识别乐谱…')
    try:
        generated = _recognize()(image_path, engine=config.engine)
    except Exception as exc:
        result['error'] = f'识别失败：{exc}'
        return result

    if not generated or not os.path.isfile(generated):
        result['error'] = '没有识别出 MusicXML，检查图片是否包含清晰完整的五线谱。'
        return result

    base_stem = os.path.splitext(os.path.basename(generated))[0]
    ext = os.path.splitext(generated)[1].lower()
    dest, midi_path = output_paths(base_stem, config.engine, ext)
    try:
        _replace_move(generated, dest)
    except OSError as exc:
        result['error'] = f'保存 MusicXML 失败：{exc}'
        return result
    result['xml'] = dest
    say(f'识别完成：{os.path.basename(dest)}')

    if os.path.getsize(dest) < 100:
        result['error'] = '生成的 MusicXML 过小，多半识别失败了。'
        return result

    say('正在转换 MIDI…')
    try:
        ok = _musicxml_to_midi()(dest, midi_path)
    except Exception as exc:
        result['error'] = f'转换 MIDI 失败：{exc}'
        return result

    if not ok or not os.path.isfile(midi_path):
        result['error'] = 'MusicXML 转 MIDI 失败。'
        return result

    result['midi'] = midi_path
    say(f'已生成：{os.path.basename(midi_path)}')
    return result


def midi_duration(midi_path, speed=1.0):
    """给播放条用：拿不到就返回 0，不抛异常。"""
    try:
        from midi_player import get_midi_duration
        return float(get_midi_duration(midi_path, speed=speed))
    except Exception:
        return 0.0


def midi_bpm(midi_path, default=120.0):
    """曲子本身的速度（BPM）。"""
    try:
        from midi_player import get_midi_bpm
        return float(get_midi_bpm(midi_path, default=default))
    except Exception:
        return float(default)


def speed_for_bpm(midi_path, bpm):
    """界面上的目标 BPM → 播放倍率。bpm<=0 表示跟随曲子原速。"""
    base = midi_bpm(midi_path)
    try:
        target = float(bpm)
    except (TypeError, ValueError):
        target = base
    if target <= 0 or base <= 0:
        return 1.0
    return max(0.25, min(4.0, target / base))


def convert_xml(xml_path):
    """把一个已有的 MusicXML 转成 MIDI，返回 (midi 路径, 错误文案)。

    MIDI 沿用 XML 的名字（已经带引擎后缀），重转就覆盖，不再堆 _1.._6。
    """
    if not xml_path or not os.path.isfile(xml_path):
        return None, '找不到 XML 文件。'
    midi_path = os.path.join(MIDI_DIR,
                             os.path.splitext(os.path.basename(xml_path))[0] + '.mid')
    try:
        ok = _musicxml_to_midi()(xml_path, midi_path)
    except Exception as exc:
        return None, f'转换失败：{exc}'
    if not ok or not os.path.isfile(midi_path):
        return None, '转换失败。'
    return midi_path, None


def play_midi_file(midi_path, sf2_path, volume=1.0, speed=1.0, stop_event=None,
                   on_progress=None, on_ready=None):
    """阻塞播放，调用方负责放到后台线程。返回是否真的播成功。"""
    from midi_player import play_midi
    return bool(play_midi(midi_path, sf2_path, volume=volume, speed=speed,
                          stop_event=stop_event, on_progress=on_progress,
                          on_ready=on_ready))


def release_playback():
    """放掉缓存的 fluidsynth 合成器（换音色库、关窗口时用）。"""
    try:
        from midi_player import release_synth
        release_synth()
    except Exception:
        pass


def preload_soundfont(sf2_path, audio_driver=None):
    """把音色库加载进缓存的合成器（第一次播放前预热用）。"""
    if not sf2_path or not os.path.isfile(sf2_path):
        return False
    try:
        from midi_player import _acquire_synth
        synth, _sfid = _acquire_synth(sf2_path, audio_driver)
        return synth is not None
    except Exception:
        return False


def start_play_thread(midi_path, sf2_path, volume, speed, on_done=None,
                      stop_event=None, on_progress=None, on_ready=None):
    import threading

    def run():
        ok = False
        try:
            ok = play_midi_file(midi_path, sf2_path, volume, speed,
                                stop_event=stop_event, on_progress=on_progress,
                                on_ready=on_ready)
        except Exception as exc:
            print(f'[play] 播放线程异常：{exc}')
        finally:
            if on_done is not None:
                on_done(ok)

    worker = threading.Thread(target=run, daemon=True)
    worker.start()
    return worker
