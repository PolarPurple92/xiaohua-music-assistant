# -*- coding: utf-8 -*-
"""全局截图热键封装。

pynput 缺失或注册失败都不应该影响主功能，所以这里只暴露 available 标志，
由界面自己决定要不要把热键提示显示出来。
"""
try:
    from pynput.keyboard import GlobalHotKeys
    PYNPUT_OK = True
except Exception:  # pragma: no cover - 环境相关
    GlobalHotKeys = None
    PYNPUT_OK = False

MODIFIERS = {'ctrl': '<ctrl>', 'control': '<ctrl>', 'alt': '<alt>', 'shift': '<shift>',
             'cmd': '<cmd>', 'win': '<cmd>', 'super': '<cmd>'}


def to_pynput_syntax(hotkey):
    """'Ctrl+Shift+Z' -> '<ctrl>+<shift>+z'。"""
    parts = [p.strip().lower() for p in (hotkey or '').split('+') if p.strip()]
    converted = [MODIFIERS.get(p, p) for p in parts]
    return '+'.join(converted)


def describe(hotkey):
    """给界面看的可读写法。"""
    return (hotkey or '').replace('+', ' + ').title().replace('Ctrl', 'Ctrl')


class GlobalHotkey:
    def __init__(self, callback):
        self.callback = callback
        self.listener = None
        self.error = None

    @property
    def available(self):
        return PYNPUT_OK

    def start(self, hotkey):
        """返回是否注册成功。"""
        self.stop()
        if not PYNPUT_OK:
            self.error = '未安装 pynput'
            return False
        try:
            combo = to_pynput_syntax(hotkey)
            self.listener = GlobalHotKeys({combo: self.callback})
            self.listener.start()
            self.error = None
            return True
        except Exception as exc:
            self.error = str(exc)
            self.listener = None
            return False

    def stop(self):
        if self.listener is not None:
            try:
                self.listener.stop()
            except Exception:
                pass
            self.listener = None
