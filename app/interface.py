# -*- coding: utf-8 -*-
"""小花音乐助手 · 程序入口。

默认启动极简模式（和旧版一致），`--full` 直接进完整模式，`--theme light|dark` 覆盖主题。
"""
import os
import sys
import tkinter as tk

# --demo：用 _unpack/preview_data 里的样例数据启动，方便先看界面。
# 必须在导入 settings 之前设置，因为目录在 settings 导入时就算好了。
if '--demo' in sys.argv:
    _DEMO = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'preview_data')
    if os.path.isdir(_DEMO):
        os.environ.setdefault('XIAOHUA_SCREENSHOTS', os.path.join(_DEMO, 'screenshots'))
        os.environ.setdefault('XIAOHUA_XML', os.path.join(_DEMO, 'xml_outputs'))
        os.environ.setdefault('XIAOHUA_MIDI', os.path.join(_DEMO, 'midi_outputs'))
        os.environ.setdefault('XIAOHUA_SHEETS', os.path.join(_DEMO, 'sheet_images'))
        os.environ.setdefault('XIAOHUA_SOUNDFONTS', os.path.join(_DEMO, 'soundfonts'))
        os.environ.setdefault('XIAOHUA_CONFIG', os.path.join(_DEMO, 'config.json'))

import ui_kit
from apps import BallApp, FullApp
from settings import APP_NAME, THEME_MODES, Config, ensure_dirs

_STYLE = None


class _NullStream:
    """pythonw 下 sys.stdout/stderr 是 None，兜一个空写入器，避免 print 崩掉。"""

    def write(self, *_args):
        return 0

    def flush(self):
        pass

    def isatty(self):
        return False


def _setup_logging():
    """无控制台启动时把日志写进文件，出问题可以翻这个文件。"""
    if sys.stdout is None:
        sys.stdout = _NullStream()
    if sys.stderr is None:
        sys.stderr = _NullStream()

    path = os.environ.get('XIAOHUA_LOG')
    if not path:
        return None
    try:
        folder = os.path.dirname(path)
        if folder:
            os.makedirs(folder, exist_ok=True)
        stream = open(path, 'a', encoding='utf-8', buffering=1)
    except OSError:
        return None

    sys.stdout = stream
    sys.stderr = stream

    import datetime
    import traceback

    def hook(exc_type, exc, tb):
        traceback.print_exception(exc_type, exc, tb, file=stream)
        stream.flush()

    sys.excepthook = hook
    print(f'\n===== {datetime.datetime.now():%Y-%m-%d %H:%M:%S} 启动 =====')
    return stream


def _ensure_dll_path():
    """把三方库目录挂到 PATH / DLL 搜索路径，别处直接 python interface.py 也能找到 DLL。"""
    here = os.path.dirname(os.path.abspath(__file__))
    for name in ('lib', 'runtime'):
        candidate = os.path.abspath(os.path.join(here, '..', name))
        if not os.path.isdir(candidate):
            continue
        os.environ['PATH'] = candidate + os.pathsep + os.environ.get('PATH', '')
        try:
            os.add_dll_directory(candidate)
        except Exception:
            pass
        return candidate
    return None


def _set_app_id():
    """让 Windows 任务栏把窗口归到本程序名下（图标才会用我们自己的）。

    不设的话任务栏会显示 python/pyw 的图标，而且多个窗口会被拆成不同分组。
    """
    if os.name != 'nt':
        return
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('Xiaohua.Music.Assistant')
    except Exception:
        pass


def _make_root():
    """优先用 tkinterdnd2 的 Tk，这样窗口才能接受拖拽文件。"""
    _set_app_id()
    try:
        from tkinterdnd2 import Tk as DnDTk
        root = DnDTk()
    except Exception:
        root = tk.Tk()
    try:
        icon = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'icon.ico')
        if os.path.isfile(icon):
            root.iconbitmap(default=icon)
    except Exception:
        pass
    return root


def apply_theme(root, mode):
    global _STYLE
    _STYLE = ui_kit.setup_style(root, mode)
    return _STYLE


class Controller:
    """负责在两种模式之间切换，以及切换主题。

    主题切换是**就地换肤**：不重建窗口，所以窗口位置、滚动位置、焦点都保留。
    （早期版本的做法是销毁再重建，既丢位置，又会踩到 ttkbootstrap 里已销毁
    控件的登记项，第二次切换直接抛异常、窗口消失。）
    """

    def __init__(self, root, config):
        self.root = root
        self.config = config
        self.mode = 'full' if '--full' in sys.argv else 'compact'
        self.app = None
        self._full_pos = None

    def start(self):
        self._build()

    def _build(self):
        app_class = FullApp if self.mode == 'full' else BallApp
        self.app = app_class(self.root, self.config, self)

    def _position(self):
        """记住当前窗口的屏幕位置，重建时原样恢复。"""
        if self.app is None:
            return None
        try:
            geo = self.app.winfo_geometry()
        except tk.TclError:
            return None
        tail = geo.split('+', 1)
        if len(tail) != 2:
            return None
        try:
            x, y = tail[1].split('+')
            return int(x), int(y)
        except ValueError:
            return None

    def switch_mode(self):
        # 悬浮球自己恢复上次的位置；完整模式沿用离开时的位置
        if self.mode == 'full':
            self._full_pos = self._position()
            position = None
        else:
            position = self._full_pos
        self.mode = 'compact' if self.mode == 'full' else 'full'
        self._teardown()
        self._build()
        if position:
            self.app.geometry(f'+{position[0]}+{position[1]}')

    def toggle_theme(self):
        self.config.theme = 'light' if self.config.theme == 'dark' else 'dark'
        self.config.save()
        ui_kit.purge_dead_widgets(self.root)
        try:
            apply_theme(self.root, self.config.theme)
        except Exception as exc:  # 极端情况：还有死引用，退回重建
            print(f'[ui] 就地换肤失败，改为重建窗口：{exc}')
            position = self._position()
            self._teardown()
            self._build()
            if position:
                self.app.geometry(f'+{position[0]}+{position[1]}')
            return
        if self.app is not None:
            self.app.on_theme_changed()

    def _teardown(self):
        if self.app is None:
            return
        try:
            self.app.hotkey.stop()
        except Exception:
            pass
        try:
            self.app._save_geometry()
        except Exception:
            pass
        try:
            self.app.destroy()
        except tk.TclError:
            pass
        self.app = None


_SINGLE_HANDLE = None
ERROR_ALREADY_EXISTS = 183


def _single_instance_name():
    """互斥量名字带上安装目录的哈希。

    用固定的名字会踩坑：一旦残留进程把那个对象占着、且它的 DACL 不允许我们
    Create（实测返回 ACCESS_DENIED），检测就会永远失效。按目录区分还顺带允许
    两份不同安装各自运行。
    """
    import hashlib
    here = os.path.dirname(os.path.abspath(__file__))
    digest = hashlib.md5(here.encode('utf-8', 'ignore')).hexdigest()[:10]
    return f'Local\\XiaohuaScreenshotMIDI_{digest}'


def _acquire_single_instance(name=None, silent=False):
    """命名互斥量：第二个实例提示后退出，免得两个球、两个全局热键互相抢。

    用 use_last_error=True：普通 windll 调用的 GetLastError 会被 ctypes
    内部调用冲掉。任何异常都「放行」——这个保护坏了也不该让人打不开程序。

    name/silent 是给自检用的：测试要能换一个干净名字、且不弹模态框。
    """
    global _SINGLE_HANDLE
    if os.name != 'nt':
        return True
    name = name or _single_instance_name()
    try:
        import ctypes
        kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel32.CreateMutexW.restype = ctypes.c_void_p
        kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_wchar_p]
        handle = kernel32.CreateMutexW(None, False, name)
        last_error = ctypes.get_last_error()
    except Exception:
        return True
    if not handle:
        print(f'[单实例] 创建互斥量失败（错误码 {last_error}），跳过检测直接启动')
        return True
    if last_error == ERROR_ALREADY_EXISTS:
        if not silent:
            try:
                ctypes.windll.user32.MessageBoxW(
                    None,
                    '小花音乐助手 已经在运行了。\n\n'
                    '· 完整模式：看任务栏窗口（可能被别的窗口挡住了）\n'
                    '· 悬浮球模式：桌面上那个小球\n\n'
                    '关掉它再启动，或者直接用 Alt+Tab 找它。',
                    '已经在运行', 0x40)
            except Exception:
                pass
        kernel32.CloseHandle(ctypes.c_void_p(handle))
        return False
    _SINGLE_HANDLE = handle
    return True


def main():
    log_stream = _setup_logging()
    if not _acquire_single_instance():
        if log_stream is not None:
            try:
                log_stream.close()
            except Exception:
                pass
        return 1
    _ensure_dll_path()
    ensure_dirs()
    config = Config.load()

    theme_override = None
    for index, arg in enumerate(sys.argv):
        if arg == '--theme' and index + 1 < len(sys.argv):
            theme_override = sys.argv[index + 1]
    if theme_override in THEME_MODES:
        config.theme = theme_override

    root = _make_root()
    root.withdraw()
    apply_theme(root, config.theme)

    controller = Controller(root, config)
    controller.start()
    try:
        root.mainloop()
    finally:
        config.save()
        if log_stream is not None:
            try:
                log_stream.close()
            except Exception:
                pass


if __name__ == '__main__':
    main()
