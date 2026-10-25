# -*- coding: utf-8 -*-
"""不依赖业务的小工具：时间/尺寸格式化、显示器工作区。"""
import os
import tkinter as tk


def call_soon(widget, func, *args):
    """把回调排到主线程——Tk 不允许跨线程操作控件。"""
    try:
        widget.after(0, lambda: func(*args))
    except tk.TclError:
        pass


def fmt_mmss(seconds):
    """秒 → M:SS，播放条用。"""
    try:
        seconds = max(0, int(round(float(seconds))))
    except (TypeError, ValueError):
        return '0:00'
    return f'{seconds // 60}:{seconds % 60:02d}'


def screen_workarea(x=None, y=None):
    """返回包含该点（默认主屏）的显示器工作区 (left, top, right, bottom)。

    多显示器下必须按「窗口所在那块屏」取边界，否则悬浮球会被拽回主屏。
    """
    if os.name != 'nt':
        return (0, 0, 1024, 768)
    try:
        import ctypes
        from ctypes import wintypes

        class MONITORINFO(ctypes.Structure):
            _fields_ = [('cbSize', wintypes.DWORD), ('rcMonitor', wintypes.RECT),
                        ('rcWork', wintypes.RECT), ('dwFlags', wintypes.DWORD)]

        user32 = ctypes.windll.user32
        user32.MonitorFromPoint.argtypes = [wintypes.POINT, wintypes.DWORD]
        user32.MonitorFromPoint.restype = wintypes.HMONITOR
        user32.GetMonitorInfoW.argtypes = [wintypes.HMONITOR, ctypes.POINTER(MONITORINFO)]

        point = wintypes.POINT(int(x or 0), int(y or 0))
        MONITOR_DEFAULTTONEAREST = 2
        monitor = user32.MonitorFromPoint(point, MONITOR_DEFAULTTONEAREST)
        info = MONITORINFO()
        info.cbSize = ctypes.sizeof(MONITORINFO)
        if monitor and user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
            rect = info.rcWork
            if rect.right > rect.left and rect.bottom > rect.top:
                return (rect.left, rect.top, rect.right, rect.bottom)
    except Exception:
        pass
    return (0, 0, 1920, 1080)


def human_size(num):
    try:
        num = float(num)
    except (TypeError, ValueError):
        return ''
    for unit in ('B', 'KB', 'MB', 'GB'):
        if num < 1024 or unit == 'GB':
            return f'{num:.0f} {unit}' if unit == 'B' else f'{num:.1f} {unit}'
        num /= 1024
    return ''
