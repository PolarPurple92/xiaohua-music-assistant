# -*- coding: utf-8 -*-
"""环境自检：换机器后先跑这个，能立刻看出缺什么。

用法（便携包里直接双击 doctor.bat，或）：
    python doctor.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

# 便携包：环境变量由 run.bat/doctor.bat 设好；开发目录：用 _unpack 下的路径兜底
IS_BUNDLE = os.path.isdir(os.path.join(HERE, 'python')) and os.path.isdir(os.path.join(HERE, 'lib'))
LIB_DIR = os.path.join(HERE, 'lib') if IS_BUNDLE else os.path.join(HERE, 'runtime')
if IS_BUNDLE:
    sys.path.insert(0, os.path.join(HERE, 'lib'))
    sys.path.insert(0, os.path.join(HERE, 'app'))
else:
    sys.path.insert(0, os.path.join(HERE, 'runtime'))
    sys.path.insert(0, os.path.join(HERE, 'recovered'))
    for env, sub in (('XIAOHUA_SCREENSHOTS', 'screenshots'), ('XIAOHUA_XML', 'xml_outputs'),
                     ('XIAOHUA_MIDI', 'midi_outputs'), ('XIAOHUA_SHEETS', 'sheet_images'),
                     ('XIAOHUA_SOUNDFONTS', 'soundfonts'), ('XIAOHUA_PREPROCESSED', 'preprocessed'),
                     ('XIAOHUA_HOMR_WORK', 'homr_work'), ('XIAOHUA_STAGING', 'staging')):
        base = os.path.join(HERE, 'preview_data')
        os.environ.setdefault(env, os.path.join(base, sub))
    os.environ.setdefault('XIAOHUA_CONFIG', os.path.join(HERE, 'preview_data', 'config.json'))

# libfluidsynth-3.dll 之类靠 PATH 才能被 ctypes 找到，先把自己这边挂上去
if os.path.isdir(LIB_DIR):
    os.environ['PATH'] = LIB_DIR + os.pathsep + os.environ.get('PATH', '')
    try:
        os.add_dll_directory(LIB_DIR)
    except Exception:
        pass

results = []


def check(name, func, hint='', optional=False):
    """optional=True 的项缺失只报 SKIP，不算失败（例如精简版没带 Audiveris）。"""
    try:
        detail = func()
        results.append((name, 'OK', detail or ''))
    except Exception as exc:
        message = f'{type(exc).__name__}: {exc}'
        if hint:
            message = f'{message}  ({hint})'
        results.append((name, 'SKIP' if optional else 'FAIL', message))


def py_info():
    bits = 64 if sys.maxsize > 2 ** 32 else 32
    return f'{sys.version.split()[0]}  {bits}-bit   {sys.executable}'


def tcl_info():
    import tkinter
    root = tkinter.Tk()
    version = root.tk.call('info', 'patchlevel')
    root.destroy()
    return f'Tcl/Tk {version}'


def ui_boot():
    """真正把主题样式和字体跑一遍——只 import 是发现不了缺 DLL 的。"""
    import tkinter
    import ttkbootstrap as tb
    from ttkbootstrap.constants import LEFT

    root = tkinter.Tk()
    root.withdraw()
    try:
        style = tb.Style(theme='darkly')
        style.configure('Probe.TButton', font=('Microsoft YaHei UI', 11, 'bold'))
        frame = tb.Frame(root, padding=6,
                         style='')
        frame.pack()
        tb.Label(frame, text='自检', font=('Microsoft YaHei UI', 10)).pack(side=LEFT)
        tb.Button(frame, text='按钮', bootstyle='primary').pack(side=LEFT)
        root.update_idletasks()
        root.update()
        return f'theme={style.theme.name}'
    finally:
        root.destroy()


def module(name):
    def load():
        mod = __import__(name)
        version = getattr(mod, '__version__', '')
        return version
    return load


def audiveris():
    path = os.environ.get('XIAOHUA_AUDIVERIS')
    if not path:
        import settings
        path = settings.audiveris_exe()
    if not os.path.isfile(path):
        raise FileNotFoundError(f'找不到 {path}')
    size = os.path.getsize(path) / 1024
    return f'{path}  ({size:.0f} KB)'


def soundfont():
    import settings
    cfg = settings.Config.load()
    path = settings.find_sf2_path(cfg)
    if not path:
        raise FileNotFoundError('没有可用的 .sf2，请放到 data\\soundfonts\\')
    return path


def data_writable():
    import settings
    settings.ensure_dirs()
    probe = os.path.join(settings.SCREENSHOT_DIR, '.write_test')
    with open(probe, 'w', encoding='utf-8') as fp:
        fp.write('ok')
    os.remove(probe)
    return settings.SCREENSHOT_DIR


def engine_state():
    import settings
    parts = []
    for name in settings.ENGINES:
        parts.append(f'{name}={"可用" if settings.engine_available(name) else "不可用"}')
    return ',  '.join(parts)


def bat_line_endings():
    """启动脚本必须是 CRLF —— cmd.exe 读 LF-only 的批处理会解析错乱（实测窗口起不来）。"""
    bad = []
    for name in sorted(os.listdir(HERE)):
        if not name.lower().endswith('.bat'):
            continue
        path = os.path.join(HERE, name)
        if not os.path.isfile(path):
            continue
        with open(path, 'rb') as fp:
            data = fp.read()
        lone_lf = data.replace(b'\r\n', b'').count(b'\n')
        if lone_lf:
            bad.append(f'{name}({lone_lf} 行是 LF)')
    if bad:
        raise ValueError('行尾不是 CRLF：' + '、'.join(bad))
    return '全部 CRLF'


def musescore_available():
    """找得到 MuseScore 可执行文件吗。"""
    import musescore_cli
    found = musescore_cli.find_musescore()
    if not found:
        raise FileNotFoundError('没找到 MuseScore4.exe')
    if not os.path.isfile(found):
        raise FileNotFoundError(found)
    return os.path.basename(os.path.dirname(os.path.dirname(found))) + '/' + os.path.basename(found)


MINI_MUSICXML = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE score-partwise PUBLIC "-//Recordare//DTD MusicXML 4.0 Partwise//EN"
 "http://www.musicxml.org/dtds/partwise.dtd">
<score-partwise version="4.0">
 <part-list><score-part id="P1"><part-name>Piano</part-name></score-part></part-list>
 <part id="P1"><measure number="1">
  <attributes><divisions>1</divisions><key><fifths>0</fifths></key>
   <time><beats>4</beats><beat-type>4</beat-type></time>
   <clef><sign>G</sign><line>2</line></clef></attributes>
  <note><pitch><step>C</step><octave>4</octave></pitch>
   <duration>4</duration><type>whole</type></note>
 </measure></part>
</score-partwise>
"""


def musescore_renders():
    """就地造一个最小 MusicXML 排版一次，确认命令行可用。"""
    import glob
    import musescore_cli
    import tempfile
    folder = tempfile.mkdtemp(prefix='ms_check_')
    sample = os.path.join(folder, 'mini.musicxml')
    with open(sample, 'w', encoding='utf-8') as fp:
        fp.write(MINI_MUSICXML)
    target = os.path.join(folder, 'out.png')
    produced = musescore_cli.render(sample, target)
    if not produced or not os.path.isfile(produced):
        raise RuntimeError('MuseScore 没有输出图片')
    size = os.path.getsize(produced)
    os.remove(produced)
    return f'{size // 1024} KB'


def main():
    print('小花截图 MIDI · 环境自检')
    print('-' * 68)
    check('Python 解释器', py_info)
    check('tkinter / Tcl', tcl_info)
    check('界面启动（主题+字体）', ui_boot, '这一步能发现缺 PIL/_imagingft 之类的 DLL 问题')
    for name in ('ttkbootstrap', 'PIL.ImageTk', 'tkinterdnd2', 'cv2', 'numpy',
                 'music21', 'mido', 'fluidsynth', 'musicxml',
                 'rapidocr_onnxruntime', 'homr'):
        check(f'import {name}', module(name))
    check('Audiveris', audiveris, '可选引擎；精简版不含它，只影响 audiveris 引擎', optional=True)
    check('音色库 .sf2', soundfont, '播放需要')
    check('MuseScore', musescore_available, '识别结果排版需要；缺失会退回内置画法', optional=True)
    check('MuseScore 排版', musescore_renders, '真跑一次转换', optional=True)
    check('数据目录可写', data_writable)
    check('引擎状态', engine_state)
    check('启动脚本行尾', bat_line_endings, 'cmd 只认 CRLF；用文本编辑器改过 bat 就可能坏')

    failed = [r for r in results if r[1] == 'FAIL']
    for name, state, detail in results:
        print(f'[{state:<4}] {name:<26} {detail}')
    print('-' * 68)
    skipped = [r for r in results if r[1] == 'SKIP']
    print(f'通过 {len(results) - len(failed) - len(skipped)} / {len(results) - len(skipped)}'
          + (f'   跳过 {len(skipped)} 项（可选）' if skipped else ''))
    if failed:
        print()
        print('有项目未通过。上面标 FAIL 的就是缺的东西：')
        print('  · import 失败 -> 拷漏了 lib 目录，或位数/版本不对（必须是 CPython 3.11 64 位）')
        print('  · 音色库      -> data\\soundfonts\\ 下放一个 .sf2')
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
