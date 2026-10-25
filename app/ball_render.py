# -*- coding: utf-8 -*-
"""悬浮球的图形：渐变球体（PIL）与逐像素 alpha 的分层窗口（Win32 API）。

和 ttk 控件完全无关，独立成一模块，免得改按钮样式时要翻几百行 GDI 代码。
"""
import os

from theme import _mix, _rgb


def ball_image(color, size=72, gloss=1.0):
    """生成一个有渐变的「圆球」位图：上亮下深 + 柔和高光 + 底部内阴影。

    纯色圆片看着很硬，加上渐变和高光才像一颗能浮起来的球。
    """
    try:
        from PIL import Image, ImageDraw, ImageFilter, ImageTk
    except Exception:
        return None

    scale = 4
    width = size * scale
    top = _mix(color, '#ffffff', 0.34)
    bottom = _mix(color, '#000000', 0.18)

    try:
        import numpy as np
        ramp = np.linspace(0.0, 1.0, width, dtype=np.float32)[:, None]
        pixels = np.empty((width, width, 3), dtype=np.float32)
        for index in range(3):
            pixels[:, :, index] = top[index] + (bottom[index] - top[index]) * ramp
        base = Image.fromarray(pixels.astype('uint8'), 'RGB')
    except Exception:
        base = Image.new('RGB', (width, width), tuple(int(v) for v in top))

    disc = base.convert('RGBA')
    mask = Image.new('L', (width, width), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, width - 1, width - 1), fill=255)
    disc.putalpha(mask)
    empty = Image.new('RGBA', (width, width), (0, 0, 0, 0))

    # 左上柔光
    gloss_layer = Image.new('RGBA', (width, width), (0, 0, 0, 0))
    ImageDraw.Draw(gloss_layer).ellipse(
        (width * 0.15, width * 0.07, width * 0.62, width * 0.44),
        fill=(255, 255, 255, int(78 * gloss)))
    gloss_layer = gloss_layer.filter(ImageFilter.GaussianBlur(width * 0.07))
    disc = Image.alpha_composite(disc, Image.composite(gloss_layer, empty, mask))

    # 底部内阴影，撑出体积
    shade = Image.new('RGBA', (width, width), (0, 0, 0, 0))
    ImageDraw.Draw(shade).ellipse(
        (width * 0.10, width * 0.60, width * 0.90, width * 1.02),
        fill=(0, 0, 0, 62))
    shade = shade.filter(ImageFilter.GaussianBlur(width * 0.07))
    disc = Image.alpha_composite(disc, Image.composite(shade, empty, mask))

    return ImageTk.PhotoImage(disc.resize((size, size), Image.LANCZOS))


def ball_sprite(color, size=68, shadow=True, glyph='♪', glyph_font_paths=None):
    """画一颗有渐变、高光和投影的球，返回 RGBA 图（逐像素 alpha，边缘抗锯齿）。

    返回的图比 size 大一整圈，四周是透明留白，用来放柔和投影。
    """
    try:
        from PIL import Image, ImageDraw, ImageFilter, ImageFont
    except Exception:
        return None

    margin = 10 if shadow else 1
    canvas_size = size + margin * 2
    scale = 4
    big = canvas_size * scale
    circle = size * scale

    # 渐变球体
    top = _mix(color, '#ffffff', 0.34)
    bottom = _mix(color, '#000000', 0.18)
    try:
        import numpy as np
        ramp = np.linspace(0.0, 1.0, circle, dtype=np.float32)[:, None]
        pixels = np.empty((circle, circle, 3), dtype=np.float32)
        for index in range(3):
            pixels[:, :, index] = top[index] + (bottom[index] - top[index]) * ramp
        disc_rgb = Image.fromarray(pixels.astype('uint8'), 'RGB')
    except Exception:
        disc_rgb = Image.new('RGB', (circle, circle), tuple(int(v) for v in top))

    disc = disc_rgb.convert('RGBA')
    mask = Image.new('L', (circle, circle), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, circle - 1, circle - 1), fill=255)
    disc.putalpha(mask)
    empty = Image.new('RGBA', (circle, circle), (0, 0, 0, 0))

    # 左上柔光
    gloss_layer = Image.new('RGBA', (circle, circle), (0, 0, 0, 0))
    ImageDraw.Draw(gloss_layer).ellipse(
        (circle * 0.16, circle * 0.07, circle * 0.62, circle * 0.44),
        fill=(255, 255, 255, 74))
    gloss_layer = gloss_layer.filter(ImageFilter.GaussianBlur(circle * 0.07))
    disc = Image.alpha_composite(disc, Image.composite(gloss_layer, empty, mask))

    # 底部内阴影
    shade = Image.new('RGBA', (circle, circle), (0, 0, 0, 0))
    ImageDraw.Draw(shade).ellipse(
        (circle * 0.10, circle * 0.60, circle * 0.90, circle * 1.02),
        fill=(0, 0, 0, 58))
    shade = shade.filter(ImageFilter.GaussianBlur(circle * 0.07))
    disc = Image.alpha_composite(disc, Image.composite(shade, empty, mask))

    # 图标
    if glyph:
        font = None
        candidates = glyph_font_paths or [
            r'C:\Windows\Fonts\seguisym.ttf',
            r'C:\Windows\Fonts\segoeui.ttf',
            r'C:\Windows\Fonts\msyh.ttc',
            r'C:\Windows\Fonts\arial.ttf',
        ]
        for path in candidates:
            if not os.path.isfile(path):
                continue
            try:
                font = ImageFont.truetype(path, int(circle * 0.40))
                break
            except Exception:
                continue
        if font is not None:
            layer = Image.new('RGBA', (circle, circle), (0, 0, 0, 0))
            draw = ImageDraw.Draw(layer)
            try:
                box = draw.textbbox((0, 0), glyph, font=font)
                x = (circle - (box[2] - box[0])) / 2 - box[0]
                y = (circle - (box[3] - box[1])) / 2 - box[1]
            except Exception:
                x, y = circle * 0.30, circle * 0.22
            draw.text((x, y), glyph, font=font, fill=(255, 255, 255, 245))
            disc = Image.alpha_composite(disc, Image.composite(layer, empty, mask))

    sprite = Image.new('RGBA', (big, big), (0, 0, 0, 0))
    offset = margin * scale
    sprite.paste(disc, (offset, offset), disc)
    sprite = sprite.resize((canvas_size, canvas_size), Image.LANCZOS)

    if shadow:
        shadow_layer = Image.new('RGBA', (canvas_size, canvas_size), (0, 0, 0, 0))
        ImageDraw.Draw(shadow_layer).ellipse(
            (margin + size * 0.06, margin + size * 0.16,
             margin + size * 0.94, margin + size * 0.96),
            fill=(0, 0, 0, 90))
        shadow_layer = shadow_layer.filter(ImageFilter.GaussianBlur(size * 0.07))
        sprite = Image.alpha_composite(shadow_layer, sprite)

    return sprite


def apply_layered_bitmap(hwnd, image, pos=None):
    """把 RGBA 图按逐像素 alpha 贴到分层窗口上 —— 这才是真正平滑的圆形窗口。

    pos 给定时同时把窗口内容挪到该屏幕坐标（拖动时要跟着推）。
    """
    try:
        import ctypes
        from ctypes import wintypes
        import numpy as np
    except Exception:
        return False
    if image is None:
        return False

    user32 = ctypes.windll.user32
    gdi32 = ctypes.windll.gdi32

    # 64 位下句柄是 8 字节，不声明 argtypes 会被截断成 int 而报 OverflowError
    user32.GetDC.argtypes = [wintypes.HWND]
    user32.GetDC.restype = wintypes.HDC
    user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
    gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
    gdi32.CreateCompatibleDC.restype = wintypes.HDC
    gdi32.DeleteDC.argtypes = [wintypes.HDC]
    gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
    gdi32.SelectObject.restype = wintypes.HGDIOBJ
    gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]

    width, height = image.size
    rgba = np.asarray(image.convert('RGBA'), dtype=np.float32)
    alpha = rgba[:, :, 3] / 255.0                      # (h, w)
    bgra = np.empty((height, width, 4), dtype=np.uint8)
    bgra[:, :, 0] = (rgba[:, :, 2] * alpha).astype(np.uint8)   # 预乘
    bgra[:, :, 1] = (rgba[:, :, 1] * alpha).astype(np.uint8)
    bgra[:, :, 2] = (rgba[:, :, 0] * alpha).astype(np.uint8)
    bgra[:, :, 3] = rgba[:, :, 3].astype(np.uint8)

    class BITMAPINFOHEADER(ctypes.Structure):
        _fields_ = [('biSize', wintypes.DWORD), ('biWidth', wintypes.LONG),
                    ('biHeight', wintypes.LONG), ('biPlanes', wintypes.WORD),
                    ('biBitCount', wintypes.WORD), ('biCompression', wintypes.DWORD),
                    ('biSizeImage', wintypes.DWORD), ('biXPelsPerMeter', wintypes.LONG),
                    ('biYPelsPerMeter', wintypes.LONG), ('biClrUsed', wintypes.DWORD),
                    ('biClrImportant', wintypes.DWORD)]

    class BITMAPINFO(ctypes.Structure):
        _fields_ = [('bmiHeader', BITMAPINFOHEADER), ('bmiColors', wintypes.DWORD * 3)]

    class BLENDFUNCTION(ctypes.Structure):
        _fields_ = [('BlendOp', ctypes.c_ubyte), ('BlendFlags', ctypes.c_ubyte),
                    ('SourceConstantAlpha', ctypes.c_ubyte), ('AlphaFormat', ctypes.c_ubyte)]

    gdi32.CreateDIBSection.argtypes = [
        wintypes.HDC, ctypes.POINTER(BITMAPINFO), wintypes.UINT,
        ctypes.POINTER(ctypes.c_void_p), wintypes.HANDLE, wintypes.DWORD]
    gdi32.CreateDIBSection.restype = wintypes.HBITMAP

    info = BITMAPINFO()
    info.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    info.bmiHeader.biWidth = width
    info.bmiHeader.biHeight = -height
    info.bmiHeader.biPlanes = 1
    info.bmiHeader.biBitCount = 32
    info.bmiHeader.biCompression = 0

    screen_dc = user32.GetDC(0)
    if not screen_dc:
        return False
    mem_dc = gdi32.CreateCompatibleDC(screen_dc)
    bits = ctypes.c_void_p()
    gdi32.CreateDIBSection.restype = wintypes.HBITMAP
    bitmap = gdi32.CreateDIBSection(mem_dc, ctypes.byref(info), 0, ctypes.byref(bits), None, 0)
    if not bitmap:
        gdi32.DeleteDC(mem_dc)
        user32.ReleaseDC(0, screen_dc)
        return False

    payload = bgra.tobytes()
    ctypes.memmove(bits, payload, len(payload))
    old = gdi32.SelectObject(mem_dc, bitmap)

    blend = BLENDFUNCTION(0, 0, 255, 1)      # AC_SRC_OVER / AC_SRC_ALPHA
    size = wintypes.SIZE(width, height)
    source = wintypes.POINT(0, 0)
    dest = None
    if pos is not None:
        dest = wintypes.POINT(int(pos[0]), int(pos[1]))
    user32.UpdateLayeredWindow.argtypes = [
        wintypes.HWND, wintypes.HDC, ctypes.POINTER(wintypes.POINT),
        ctypes.POINTER(wintypes.SIZE), wintypes.HDC, ctypes.POINTER(wintypes.POINT),
        wintypes.DWORD, ctypes.POINTER(BLENDFUNCTION), wintypes.DWORD]
    user32.UpdateLayeredWindow.restype = wintypes.BOOL
    ok = user32.UpdateLayeredWindow(
        wintypes.HWND(hwnd), screen_dc,
        ctypes.byref(dest) if dest is not None else None, ctypes.byref(size),
        mem_dc, ctypes.byref(source), 0, ctypes.byref(blend), 2)   # ULW_ALPHA

    gdi32.SelectObject(mem_dc, old)
    gdi32.DeleteObject(bitmap)
    gdi32.DeleteDC(mem_dc)
    user32.ReleaseDC(0, screen_dc)
    return bool(ok)


def make_layered(hwnd):
    """给窗口加上 WS_EX_LAYERED，否则 UpdateLayeredWindow 不生效。"""
    try:
        import ctypes
        user32 = ctypes.windll.user32
        GWL_EXSTYLE = -20
        WS_EX_LAYERED = 0x00080000
        if hasattr(user32, 'GetWindowLongPtrW'):
            current = user32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE)
            user32.SetWindowLongPtrW(hwnd, GWL_EXSTYLE, current | WS_EX_LAYERED)
        else:
            current = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            user32.SetWindowLongW(hwnd, GWL_EXSTYLE, current | WS_EX_LAYERED)
        return True
    except Exception:
        return False
