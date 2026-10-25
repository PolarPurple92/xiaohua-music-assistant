# -*- coding: utf-8 -*-
"""兼容壳：实现在 theme / widgets / ball_render / util 里。

保留这个名字是为了不打断既有的 `from ui_kit import X` 写法。
"""
from ball_render import (  # noqa: F401
    apply_layered_bitmap, ball_image, ball_sprite, make_layered,
)
from theme import (  # noqa: F401
    FONT_BIG_BUTTON, FONT_BODY, FONT_FALLBACK, FONT_NAME, FONT_SECTION, FONT_SMALL,
    FONT_TITLE, GAP, PAD, _blend, _font_family, _mix, _rgb, purge_dead_widgets,
    setup_style, theme_bg,
)
from util import call_soon, fmt_mmss, human_size, screen_workarea  # noqa: F401
from widgets import (  # noqa: F401
    Chip, FileList, Segmented, StatusBar, ThumbGrid, _thumb_guard, rounded_thumbnail,
)

__all__ = [
    'Chip', 'FileList', 'Segmented', 'StatusBar', 'ThumbGrid',
    'rounded_thumbnail', 'ball_image', 'ball_sprite', 'apply_layered_bitmap',
    'make_layered', 'setup_style', 'theme_bg', 'purge_dead_widgets',
    'fmt_mmss', 'human_size', 'screen_workarea', 'call_soon',
    'FONT_NAME', 'FONT_FALLBACK', 'FONT_BODY', 'FONT_SMALL', 'FONT_TITLE',
    'FONT_SECTION', 'FONT_BIG_BUTTON', 'PAD', 'GAP',
]
