# -*- coding: utf-8 -*-
"""在 MuseScore 里编辑这一段谱，并把它的窗口摆到我们旁边方便对照。

注意：MuseScore 的编辑界面是独立窗口，没法嵌进 Tk，
所以做法是「外挂」——启动它、把窗口挪到我们右边，改完点「重新载入」。
"""
import ctypes
import os
import subprocess
import time
from ctypes import wintypes

SW_RESTORE = 9
WM_CLOSE = 0x0010


def _user32():
    return ctypes.windll.user32


def _windows_of(pid):
    user32 = _user32()
    found = []
    proc_type = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)

    def callback(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length == 0:
            return True
        buffer = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buffer, length + 1)
        owner = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        if owner.value != pid:
            return True
        rect = wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
        found.append({'hwnd': hwnd, 'title': buffer.value,
                      'w': rect.right - rect.left, 'h': rect.bottom - rect.top})
        return True

    user32.EnumWindows(proc_type(callback), 0)
    return found


def _main_window(pid, timeout=45):
    """等 MuseScore 的主窗口出现（跳过加载中的小窗）。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        big = [item for item in _windows_of(pid) if item['w'] > 400 and item['h'] > 300]
        if big:
            return big[0]
        time.sleep(0.4)
    return None


def place_beside(hwnd, app_rect, screen=None):
    """把窗口还原并摆到主程序右边（放不下就放下边）。"""
    user32 = _user32()
    user32.ShowWindow(hwnd, SW_RESTORE)
    time.sleep(0.3)
    if screen is None:
        screen_w = user32.GetSystemMetrics(0)
        screen_h = user32.GetSystemMetrics(1)
    else:
        screen_w, screen_h = screen
    margin = 12
    left_room = screen_w - (app_rect['x'] + app_rect['w']) - margin * 2
    if left_room >= 640:
        x = app_rect['x'] + app_rect['w'] + margin
        y = max(0, app_rect['y'])
        w = min(left_room, 1400)
        h = min(app_rect['h'], screen_h - y - margin)
    else:
        x = max(0, app_rect['x'])
        y = app_rect['y'] + app_rect['h'] - 200
        w = min(app_rect['w'], screen_w - margin * 2)
        h = max(320, screen_h - y - margin)
    user32.MoveWindow(hwnd, int(x), int(y), int(w), int(h), True)
    return (int(x), int(y), int(w), int(h))


def open_file(exe, file_path, app_rect=None):
    """启动 MuseScore 打开某个 MusicXML，并摆好窗口。返回 (process, hwnd)。"""
    if not exe or not os.path.isfile(exe) or not os.path.isfile(file_path):
        return None, 0
    process = subprocess.Popen([exe, file_path])
    window = _main_window(process.pid)
    if window and app_rect:
        place_beside(window['hwnd'], app_rect)
    return process, (window['hwnd'] if window else 0)


def close_window(hwnd):
    if not hwnd:
        return False
    try:
        _user32().PostMessageW(hwnd, WM_CLOSE, 0, 0)
        return True
    except Exception:
        return False


def is_alive(hwnd):
    if not hwnd:
        return False
    try:
        return bool(_user32().IsWindow(wintypes.HWND(hwnd)))
    except Exception:
        return False
