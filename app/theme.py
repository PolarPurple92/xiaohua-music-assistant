# -*- coding: utf-8 -*-
"""主题：字体、配色混合、ttkbootstrap 样式初始化，以及换主题时的死控件清理。"""
import tkinter as tk

import ttkbootstrap as tb

from settings import THEME_BOOTSTYLES

FONT_NAME = 'Microsoft YaHei UI'
FONT_FALLBACK = 'Microsoft YaHei'
FONT_BODY = (FONT_NAME, 10)
FONT_SMALL = (FONT_NAME, 9)
FONT_TITLE = (FONT_NAME, 19, 'bold')
FONT_SECTION = (FONT_NAME, 11, 'bold')
FONT_BIG_BUTTON = (FONT_NAME, 12, 'bold')

PAD = 16
GAP = 10

def _font_family(root):
    """挑一个系统里真实存在的字体，避免方块。"""
    try:
        from tkinter import font as tkfont
        families = set(tkfont.families(root))
    except Exception:
        return FONT_NAME
    for name in (FONT_NAME, FONT_FALLBACK, 'SimHei', 'SimSun'):
        if name in families:
            return name
    return FONT_NAME


def _blend(color_a, color_b, ratio):
    """把两种 #rrggbb 按比例混合，用来做「比背景稍亮一点」的隔行底色。"""
    try:
        a = color_a.lstrip('#')
        b = color_b.lstrip('#')
        pa = tuple(int(a[i:i + 2], 16) for i in (0, 2, 4))
        pb = tuple(int(b[i:i + 2], 16) for i in (0, 2, 4))
        return '#%02x%02x%02x' % tuple(int(x + (y - x) * ratio) for x, y in zip(pa, pb))
    except Exception:
        return color_a


def _rgb(color):
    color = color.lstrip('#')
    return tuple(int(color[i:i + 2], 16) for i in (0, 2, 4))


def _mix(color, other, ratio):
    """按比例把颜色往 other 混，用来做渐变/浅色。"""
    try:
        a = _rgb(color) if isinstance(color, str) else tuple(color)
        b = _rgb(other) if isinstance(other, str) else tuple(other)
        return tuple(int(round(x + (y - x) * ratio)) for x, y in zip(a, b))
    except Exception:
        return (128, 128, 128)


def theme_bg():
    """当前主题的背景色，给少数原生 tk 控件（Canvas 等）用。"""
    try:
        return tb.Style().colors.bg
    except Exception:
        return '#222222'


def theme_fg():
    """和背景对比的前景色（原生 Text 之类不会被主题自动上色）。"""
    try:
        r, g, b = _rgb(theme_bg())
    except Exception:
        return '#e6e6e6'
    luminance = 0.299 * r + 0.587 * g + 0.114 * b
    return '#1f1f1f' if luminance > 140 else '#e6e6e6'


def theme_muted():
    """次要文字色（时间戳、说明这类）。"""
    try:
        r, g, b = _rgb(theme_bg())
    except Exception:
        return '#8a8a8a'
    luminance = 0.299 * r + 0.587 * g + 0.114 * b
    return '#6b6b6b' if luminance > 140 else '#9a9a9a'


def purge_dead_widgets(root):
    """清掉 ttkbootstrap 里已销毁控件的登记。

    ttkbootstrap 的 Publisher 以「窗口路径」为键登记订阅者，窗口销毁后条目仍在。
    再换主题时它逐个回调，碰到已销毁的控件就抛 bad window path name，
    表现就是「换个主题窗口没了」。
    """
    try:
        from ttkbootstrap.publisher import Publisher
    except Exception:
        return 0
    store = Publisher.__dict__.get('_Publisher__subscribers')
    if not store:
        return 0
    removed = 0
    for name in list(store.keys()):
        if not isinstance(name, str) or not name.startswith('.'):
            continue
        try:
            alive = bool(root.tk.call('winfo', 'exists', name))
        except Exception:
            alive = False
        if alive:
            continue
        try:
            Publisher().unsubscribe(name)
        except Exception:
            store.pop(name, None)
        removed += 1
    return removed


def setup_style(root, theme_mode):
    """按亮/暗模式切换 ttkbootstrap 主题，并统一字体与行高。

    ttkbootstrap 的 Style 是单例，重复构造不会换主题，必须显式 theme_use。
    """
    bootstyle = THEME_BOOTSTYLES.get(theme_mode, 'litera')
    style = tb.Style(theme=bootstyle)
    try:
        if getattr(style.theme, 'name', None) != bootstyle:
            style.theme_use(bootstyle)
    except Exception:
        pass
    family = _font_family(root)
    base = (family, 10)
    style.configure('.', font=base)
    style.configure('TButton', font=base, padding=(12, 6))
    # ttk 的 Button/Combobox 没有 -font 选项，主按钮的字号只能通过样式给
    style.configure('primary.TButton', font=(family, 11, 'bold'), padding=(16, 9))
    style.configure('Treeview', rowheight=30, font=base)
    style.configure('Treeview.Heading', font=(family, 10, 'bold'))
    style.configure('TCombobox', padding=(6, 4))
    style.configure('TCheckbutton', font=base)
    style.configure('TLabelframe.Label', font=(family, 10, 'bold'))
    # 播放条的进度条要细一点，才像播放器
    for name in ('Horizontal.TProgressbar', 'primary.Horizontal.TProgressbar'):
        try:
            style.configure(name, thickness=7)
        except Exception:
            pass
    style.map('Treeview', background=[('selected', style.colors.primary)])
    return style
