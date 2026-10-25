# -*- coding: utf-8 -*-
"""兼容壳：真正的实现在 base_window / full_app / ball_app。

保留这个名字是为了不打断既有的 `from apps import FullApp, BallApp` 写法。
"""
import pipeline  # noqa: F401  （测试里有 apps.pipeline.xxx = ... 的写法）

import base_window
from base_window import (  # noqa: F401
    BaseWindow, _fmt_time, _list_dir, _render_with_musescore, _text_dialog,
)
from ball_app import BallApp  # noqa: F401
from full_app import ABOUT_TEXT, FILTERS, UPDATE_NOTES, FullApp  # noqa: F401

__all__ = ['BaseWindow', 'FullApp', 'BallApp', 'FILTERS', 'ABOUT_TEXT', 'UPDATE_NOTES',
           'base_window', 'pipeline']
