# -*- coding: utf-8 -*-
"""MIDI 播放：用 fluidsynth 出声，事件调度自己做。

旧实现直接调 `fs.play_midi_file()` 再 `sleep(时长)`：中途没法停、
改速度要重写一份临时 MIDI、时长也估不准。现在改成先把 MIDI 解析成
(绝对秒, 消息) 时间线，再按墙钟逐条派发 —— 可以随时停止，速度直接算在时间轴上。
"""
import os
import threading
import time

import mido

_STEP = 0.008          # 调度粒度，8ms 足够跟手
_PANIC_CHANNEL_ALL = range(16)
DEFAULT_BPM = 120.0
SOUNDFONT_EXTS = ('.sf2', '.sf3')

# 音色库只加载一次，播放之间复用：FluidR3_GM 这种 141MB 的库每次 sfload 要 1~3 秒
_SYNTH_CACHE = {'path': None, 'synth': None, 'sfid': -1, 'driver': None}

# 同一时刻只允许一个线程驱动合成器（否则多个线程会互相叠音）
_PLAY_LOCK = threading.Lock()


def release_synth():
    """放掉缓存的合成器（换音色库、关窗口时调用）。"""
    synth = _SYNTH_CACHE.get('synth')
    if synth is not None:
        try:
            _all_notes_off(synth)
        except Exception:
            pass
        try:
            synth.delete()
        except Exception:
            pass
    _SYNTH_CACHE.update({'path': None, 'synth': None, 'sfid': -1, 'driver': None})


def _acquire_synth(sf2_file, audio_driver=None):
    """返回 (synth, sfid)，同一条路径直接复用已加载的实例。"""
    cached = _SYNTH_CACHE
    if cached['synth'] is not None and cached['path'] == sf2_file:
        return cached['synth'], cached['sfid']

    release_synth()
    import fluidsynth

    synth = fluidsynth.Synth()
    drivers = ['dsound', 'coreaudio', 'pulseaudio', 'alsa']
    if audio_driver:
        drivers = [audio_driver] + drivers
    started = False
    for driver in drivers:
        try:
            synth.start(driver=driver)
            print(f'成功使用音频驱动: {driver}')
            started = True
            break
        except Exception:
            continue
    if not started:
        print('错误：无法启动任何音频驱动')
        try:
            synth.delete()
        except Exception:
            pass
        return None, -1

    sfid = synth.sfload(sf2_file)
    if sfid < 0:
        print(f'错误：无法加载音色库 {sf2_file}')
        try:
            synth.delete()
        except Exception:
            pass
        return None, -1

    _SYNTH_CACHE.update({'path': sf2_file, 'synth': synth, 'sfid': sfid, 'driver': audio_driver})
    return synth, sfid


def get_midi_bpm(midi_file, default=DEFAULT_BPM):
    """取 MIDI 的基准速度（第一处 set_tempo；没有就按 120 BPM）。

    界面上的「速度」用的是 BPM，播放时需要把目标 BPM 换算成倍率，
    换算的基准就是这个函数返回的「曲子本身多快」。
    """
    try:
        mid = mido.MidiFile(midi_file)
        for track in mid.tracks:
            for msg in track:
                if msg.type == 'set_tempo' and msg.tempo > 0:
                    return 60000000.0 / float(msg.tempo)
    except Exception:
        pass
    return float(default)


def _timeline(midi_file):
    """解析成 (绝对秒, 消息) 并按时间排序；同时返回总时长。"""
    mid = mido.MidiFile(midi_file)
    ticks_per_beat = mid.ticks_per_beat or 480
    events = []
    for track in mid.tracks:
        tempo = 500000
        seconds = 0.0
        for msg in track:
            seconds += mido.tick2second(msg.time, ticks_per_beat, tempo)
            if msg.type == 'set_tempo':
                tempo = msg.tempo
                continue
            if msg.is_meta:
                continue
            events.append((seconds, msg))
    events.sort(key=lambda item: item[0])
    total = events[-1][0] if events else 0.0
    return events, total


def get_midi_duration(midi_file, speed=1.0):
    try:
        _events, total = _timeline(midi_file)
        return total / speed if speed else total
    except Exception:
        return 0.0


def _dispatch(synth, msg):
    try:
        if msg.type == 'note_on' and msg.velocity > 0:
            synth.noteon(msg.channel, msg.note, msg.velocity)
        elif msg.type in ('note_on', 'note_off'):
            synth.noteoff(msg.channel, msg.note)
        elif msg.type == 'program_change':
            synth.program_change(msg.channel, msg.program)
        elif msg.type == 'control_change':
            synth.cc(msg.channel, msg.control, msg.value)
        elif msg.type == 'pitchwheel':
            synth.pitch_bend(msg.channel, msg.pitch)
    except Exception as exc:
        print(f'[play] 事件派发失败 {msg}: {exc}')


def _all_notes_off(synth):
    for channel in _PANIC_CHANNEL_ALL:
        try:
            synth.cc(channel, 123, 0)       # All Notes Off
            synth.cc(channel, 120, 0)       # All Sound Off
        except Exception:
            pass


def play_midi(midi_file, sf2_file='soundfont.sf2', volume=1.0, audio_driver=None,
              speed=1.0, stop_event=None, on_progress=None, on_ready=None):
    """阻塞播放，返回是否成功开始并走完（被 stop_event 打断也算走完）。"""
    if not os.path.exists(midi_file):
        print(f'错误：找不到 MIDI 文件 {midi_file}')
        return False

    if not os.path.exists(sf2_file):
        base = os.path.dirname(os.path.abspath(__file__)) if '__file__' in dir() else os.getcwd()
        sf_dir = os.path.join(base, 'soundfonts')
        if os.path.isdir(sf_dir):
            sf2_files = [f for f in os.listdir(sf_dir) if f.lower().endswith(SOUNDFONT_EXTS)]
            if sf2_files:
                sf2_file = os.path.join(sf_dir, sf2_files[0])
                print(f'自动选择音色库: {sf2_file}')

    if not os.path.exists(sf2_file):
        print(f'错误：找不到 SoundFont 文件 {sf2_file}')
        return False

    try:
        events, total = _timeline(midi_file)
    except Exception as exc:
        print(f'错误：解析 MIDI 失败 {exc}')
        return False
    if not events:
        print('错误：MIDI 里没有可播放的事件')
        return False

    speed = max(0.1, float(speed or 1.0))
    duration = total / speed

    synth, sfid = _acquire_synth(sf2_file, audio_driver)
    if synth is None:
        return False

    # 等上一个播放线程退出；它可能还在往同一个合成器里塞事件
    acquired = _PLAY_LOCK.acquire(timeout=5.0)
    if not acquired:
        print('播放被跳过：上一个播放还没结束')
        return False

    try:
        try:
            _all_notes_off(synth)
        except Exception:
            pass
        synth.program_select(0, sfid, 0, 0)
        try:
            synth.setting('synth.gain', min(2.0, max(0.0, float(volume))))
        except Exception:
            print('警告：设置音量失败')

        # 音色库加载完了，这才算真正能出声
        if on_ready is not None:
            try:
                on_ready()
            except Exception:
                pass

        print(f'正在播放 {midi_file} (预计 {duration:.1f} 秒)...')
        started_at = time.perf_counter()
        index = 0
        total_events = len(events)
        while index < total_events:
            if stop_event is not None and stop_event.is_set():
                print('播放被停止')
                break
            elapsed = (time.perf_counter() - started_at) * speed
            while index < total_events and events[index][0] <= elapsed:
                _dispatch(synth, events[index][1])
                index += 1
            if on_progress is not None:
                try:
                    on_progress(min(1.0, index / total_events))
                except Exception:
                    pass
            if index >= total_events:
                break
            time.sleep(_STEP)

        # 尾巴：让最后一个音符自然响完（除非是被停掉的）
        if stop_event is None or not stop_event.is_set():
            time.sleep(0.25)
        print('播放结束')
        return True
    except Exception as exc:
        print(f'播放出错：{exc}')
        return False
    finally:
        try:
            _all_notes_off(synth)
        except Exception:
            pass
        try:
            _PLAY_LOCK.release()
        except Exception:
            pass
        # 合成器留着复用，下一次播放就不用再 sfload（大音色库能省 1~3 秒）
