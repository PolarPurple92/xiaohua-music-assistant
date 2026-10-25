# -*- coding: utf-8 -*-
"""PDF 阅读视图：翻页、缩放、看当前页，并把「分析本页」交给上层。

只负责显示与导航；翻页后要不要 OCR、要不要调云端，都由 FullApp 决定。
"""
import os
import re
import threading

import tkinter as tk

import ttkbootstrap as tb
from ttkbootstrap.constants import BOTH, LEFT, RIGHT, X, Y, YES

from theme import FONT_NAME, FONT_SMALL, PAD, theme_bg

try:                                    # 拖放依赖 tkdnd；缺了就不支持拖入，不影响其它功能
    from tkinterdnd2 import DND_FILES, TkinterDnD
    _DND_OK = True
except Exception:                       # noqa: BLE001
    DND_FILES = None
    TkinterDnD = None
    _DND_OK = False


def _hex_rgb(color):
    color = (color or '').strip().lstrip('#')
    if len(color) == 3:
        color = ''.join(ch * 2 for ch in color)
    if len(color) < 6:
        return (255, 255, 255)
    return (int(color[0:2], 16), int(color[2:4], 16), int(color[4:6], 16))


class PdfView(tb.Frame):
    """一个极简 PDF 阅读器：整页显示 + 翻页 + 适合窗口。"""

    def __init__(self, master, post=None, on_analyze=None, on_page=None,
                 on_lookup=None, on_click=None, on_band=None, on_region=None,
                 on_bands=None, on_model=None, on_export=None, **kwargs):
        super().__init__(master, **kwargs)
        self.post = post or (lambda func, *a, **k: func(*a, **k))
        self.on_analyze = on_analyze
        self.on_page = on_page
        self.on_lookup = on_lookup
        self.on_click = on_click
        self.on_band = on_band
        self.on_region = on_region
        self.on_bands = on_bands
        self.on_model = on_model
        self.on_export = on_export
        self._hover_box = None      # 当前高亮的 (x1,y1,x2,y2)（图片坐标）
        self._selected_box = None   # 最近一次选中的框，供「＋行 / －行」扩展
        self._last_pointer = None   # 最后一次鼠标画布坐标（翻页后据此重算高亮）
        self._rect_id = None
        self._drag_start = None
        self.book = None
        self.page = 1
        self._photo = None
        self._image_id = None
        self._fit = True
        self._busy = False

        bar = tb.Frame(self)
        bar.pack(fill=X, pady=(0, 8))
        self.bar = bar
        tb.Button(bar, text='打开 PDF', bootstyle='primary',
                  command=self.pick_file).pack(side=LEFT)
        self.prev_btn = tb.Button(bar, text='‹', width=3, bootstyle='secondary-outline',
                                  command=self.prev_page)
        self.prev_btn.pack(side=LEFT, padx=(10, 0))
        self.page_var = tk.StringVar(value='—')
        entry = tb.Entry(bar, textvariable=self.page_var, width=6, justify='center',
                         style='PageNum.TEntry')
        entry.pack(side=LEFT, padx=4)
        entry.bind('<Return>', lambda _e: self.goto_text(self.page_var.get()))
        self.page_entry = entry
        self.total_label = tb.Label(bar, text='/ 0', font=FONT_SMALL, bootstyle='secondary')
        self.total_label.pack(side=LEFT)
        self.next_btn = tb.Button(bar, text='›', width=3, bootstyle='secondary-outline',
                                  command=self.next_page)
        self.next_btn.pack(side=LEFT, padx=(4, 12))
        self.fit_btn = tb.Button(bar, text='适合窗口', bootstyle='secondary-outline',
                                 command=self.toggle_fit)
        self.fit_btn.pack(side=LEFT)
        # 播放范围：一行谱常常不够（旋律题会跨两行），可上下扩/缩
        self.more_btn = tb.Button(bar, text='＋行', width=4, bootstyle='secondary-outline',
                                  command=lambda: self.expand_selection(1))
        self.more_btn.pack(side=LEFT, padx=(10, 0))
        self.less_btn = tb.Button(bar, text='－行', width=4, bootstyle='secondary-outline',
                                  command=lambda: self.expand_selection(-1))
        self.less_btn.pack(side=LEFT, padx=(2, 0))
        self.analyze_btn = tb.Button(bar, text='分析本页', bootstyle='success',
                                     command=self.analyze, state='disabled')
        self.analyze_btn.pack(side=RIGHT)
        self.model_btn = tb.Button(bar, text='模型', bootstyle='secondary-outline',
                                   command=self.configure_model)
        self.model_btn.pack(side=RIGHT, padx=(0, 6))

        self.hint = tb.Label(self, text='把 PDF 拖进来或点「打开 PDF」；手头没有就先试 samples\\sample-score.pdf',
                             font=FONT_SMALL, bootstyle='secondary', anchor='w')
        self.hint.pack(fill=X, pady=(0, 6))

        wrap = tb.Frame(self)
        wrap.pack(fill=BOTH, expand=YES)
        self.canvas = tk.Canvas(wrap, highlightthickness=0, bd=0, bg=theme_bg())
        self.scroll = tb.Scrollbar(wrap, orient='vertical', command=self.canvas.yview,
                                   bootstyle='round')
        self.canvas.configure(yscrollcommand=self.scroll.set)
        self.scroll.pack(side=RIGHT, fill=Y)
        self.canvas.pack(side=LEFT, fill=BOTH, expand=YES)
        self.canvas.bind('<Configure>', lambda _e: self._redraw())
        for sequence in ('<Left>', '<Right>', '<Prior>', '<Next>', '<Home>', '<End>'):
            self.canvas.bind(sequence, self._on_key)
        self.canvas.bind('<MouseWheel>', self._on_wheel)
        # 右键：查本页出现的术语；左键：点哪行谱就听哪行
        self.canvas.bind('<Button-3>', self._on_context)
        self.canvas.bind('<Button-1>', self._on_press)
        self.canvas.bind('<B1-Motion>', self._on_drag)
        self.canvas.bind('<ButtonRelease-1>', self._on_release)
        self.canvas.bind('<Double-Button-1>', self._on_double)
        self.canvas.bind('<Motion>', self._on_motion)
        self.canvas.bind('<Leave>', self._on_leave)
        self._enable_drop()
        self._style_page_entry()
        self.canvas.configure(takefocus=True)

    # ---------------------------------------------------------------- 打开
    # ---------------------------------------------------------------- 拖放
    def _enable_drop(self):
        """把 PDF 直接拖到这一栏就切换当前文件。"""
        if not _DND_OK:
            return
        try:
            TkinterDnD._require(self)
        except Exception:
            pass
        for widget in (self, self.canvas, getattr(self, 'hint', None)):
            if widget is None:
                continue
            try:
                widget.drop_target_register(DND_FILES)
                widget.dnd_bind('<<Drop>>', self._on_drop)
            except Exception:
                continue

    @staticmethod
    def _parse_drop(data):
        """tkdnd 的 data 可能是「{带 空格 的路径} 另一个路径」，要拆开。"""
        if not data:
            return []
        found = re.findall(r'\{([^}]*)\}|(\S+)', str(data))
        paths = []
        for braced, plain in found:
            value = braced or plain
            if value:
                paths.append(value)
        return paths

    def _on_drop(self, event):
        paths = self._parse_drop(getattr(event, 'data', ''))
        pdfs = [path for path in paths if path.lower().endswith('.pdf')]
        if not pdfs:
            try:
                self.hint.configure(text='只支持拖入 PDF 文件')
            except Exception:
                pass
            return None
        self.open(pdfs[0])
        return None

    def pick_file(self):
        from tkinter import filedialog
        path = filedialog.askopenfilename(
            parent=self, title='选择 PDF',
            filetypes=[('PDF', '*.pdf'), ('所有文件', '*.*')])
        if path:
            self.open(path)

    def open(self, path, page=1):
        from pdf_book import Book
        from settings import BRIEF_DIR
        try:
            self.book = Book(path, os.path.dirname(BRIEF_DIR.rstrip('\\/')))
        except Exception as exc:
            self.hint.configure(text=f'打不开这个 PDF：{exc}')
            return False
        self.book.title = os.path.splitext(os.path.basename(path))[0]
        self.page = max(1, min(int(page or 1), self.book.pages))
        self.total_label.configure(text=f'/ {self.book.pages}')
        self.analyze_btn.configure(state='normal')
        name = os.path.basename(path)
        self.hint.configure(text=f'{name}')
        self._show()
        if self.on_page:
            self.on_page(self.book, self.page)
        return True

    # ---------------------------------------------------------------- 翻页
    def goto_text(self, text):
        try:
            number = int(str(text).strip())
        except ValueError:
            self._sync_page_entry()
            return
        self.goto(number)

    def goto(self, number):
        if not self.book:
            return
        number = max(1, min(int(number), self.book.pages))
        if number == self.page:
            self._sync_page_entry()
            return
        self.page = number
        self._show()
        if self.on_page:
            self.on_page(self.book, self.page)

    def next_page(self):
        self.goto(self.page + 1)

    def prev_page(self):
        self.goto(self.page - 1)

    def _on_key(self, event):
        mapping = {'Left': self.prev_page, 'Right': self.next_page,
                   'Prior': self.prev_page, 'Next': self.next_page,
                   'Home': lambda: self.goto(1),
                   'End': lambda: self.goto(self.book.pages if self.book else 1)}
        action = mapping.get(event.keysym)
        if action:
            action()
            return 'break'
        return None

    def _on_wheel(self, event):
        if self._fit:
            if event.delta > 0:
                self.prev_page()
            else:
                self.next_page()
            return 'break'
        self.canvas.yview_scroll(int(-event.delta / 120), 'units')
        return 'break'

    def _context_menu(self):
        """构造右键菜单（不弹出，便于测试与截图）。没有可用内容时返回 None。"""
        if not self.book or not self.on_lookup:
            return None
        try:
            names = self.on_lookup(self.book, self.page, 'list')
        except Exception:
            names = []
        menu = tk.Menu(self, tearoff=0)
        box = self._selected_box
        if self.on_export:
            if box:
                menu.add_command(
                    label='导出这一段的 MIDI…',
                    command=lambda b=box: self.on_export(self.book, self.page, b))
            else:
                menu.add_command(label='先双击或拖框选中一行，才能导出 MIDI',
                                 state='disabled')
            menu.add_separator()
        if names:
            menu.add_command(label=f'本页出现的术语（{len(names)} 个）',
                             state='disabled')
            for name in names[:12]:
                menu.add_command(
                    label=f'  查「{name}」',
                    command=lambda n=name: self.on_lookup(self.book, self.page, 'lookup', n))
        else:
            menu.add_command(label='本页没有出现的术语', state='disabled')
        menu.add_separator()
        menu.add_command(label='打开术语页',
                         command=lambda: self.on_lookup(self.book, self.page, 'open'))
        return menu

    def _on_context(self, event):
        """右键菜单：查本页出现的术语，或者看这页有哪些术语。"""
        menu = self._context_menu()
        if menu is None:
            return
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    # ---------------------------------------------------------------- 点/框选
    def _image_coords(self, event):
        """画布坐标 → 原图坐标。"""
        scale = getattr(self, '_scale', 1.0) or 1.0
        x = (event.x - getattr(self, '_offset_x', 0)) / scale
        y = event.y / scale
        if self.book is None:
            return None
        if getattr(self, '_rendered_page', None) != self.page:
            return None
        if x < 0 or y < 0:
            return None
        return x, y

    def _band_for(self, x, y):
        if not self.book or not self.on_band:
            return None
        try:
            return self.on_band(self.book, self.page, x, y)
        except Exception:
            return None

    def _draw_box(self, box):
        """把图片坐标的框画到画布上（半透明 + 描边）。"""
        if not box:
            if self._rect_id is not None:
                self.canvas.delete(self._rect_id)
                self._rect_id = None
            return
        scale = getattr(self, '_scale', 1.0) or 1.0
        offset = getattr(self, '_offset_x', 0)
        x1, y1, x2, y2 = box
        coords = (offset + x1 * scale, y1 * scale, offset + x2 * scale, y2 * scale)
        if self._rect_id is None:
            self._rect_id = self.canvas.create_rectangle(
                *coords, outline='#1a5fb4', width=2, fill='#1a5fb4',
                stipple='gray12', tags='hoverbox')
        else:
            self.canvas.coords(self._rect_id, *coords)
            self.canvas.tag_raise(self._rect_id)

    def _on_motion(self, event):
        self._last_pointer = (event.x, event.y)
        if self._drag_start is not None:
            return
        self.update_hover()

    def update_hover(self):
        """按最后的鼠标位置重算高亮框（翻页/缩放后调用）。"""
        if not self._last_pointer or self._drag_start is not None:
            return
        px, py = self._last_pointer
        scale = getattr(self, '_scale', 1.0) or 1.0
        x = (px - getattr(self, '_offset_x', 0)) / scale
        y = py / scale
        if x < 0 or y < 0:
            return
        band = self._band_for(x, y)
        if not band:
            return
        image_width = self.book.render(self.page).width
        box = (0, band[0], image_width, band[1])
        if box != self._hover_box:
            self._hover_box = box
            self._draw_box(box)

    def _on_leave(self, _event=None):
        if self._drag_start is None:
            self._hover_box = None
            self._last_pointer = None
            self._draw_box(None)

    def _on_press(self, event):
        self.canvas.focus_set()
        point = self._image_coords(event)
        if not point:
            return None
        band = self._band_for(point[0], point[1])
        if not band:
            return None
        self._drag_start = (point[0], point[1], band)
        self._draw_box((0, band[0], self.book.render(self.page).width, band[1]))
        return None

    def _on_double(self, event):
        """双击谱行 → 识别并播放整行。"""
        self._drag_start = None
        point = self._image_coords(event)
        if not point:
            return None
        x, y = point
        band = self._band_for(x, y)
        if not band:
            return None
        box = (0, band[0], self.book.render(self.page).width, band[1])
        self._selected_box = box
        self._draw_box(box)
        if self.on_click:
            self.on_click(self.book, self.page, x, y)
        return None

    # ------------------------------------------------------------ 播放范围
    def _page_bands(self):
        """本页所有谱行（由外部回调提供，失败就当没有）。"""
        if not self.book or not self.on_bands:
            return []
        try:
            return list(self.on_bands(self.book, self.page) or [])
        except Exception:
            return []

    def _band_containing(self, y, fallback=None):
        for top, bottom in self._page_bands():
            if top - 2 <= y <= bottom + 2:
                return (top, bottom)
        return fallback

    def expand_selection(self, delta):
        """把当前选区往上/下扩一行或缩一行，并立即按新范围播放。

        delta > 0：向下扩一行（旋律题常跨两行，一行谱不够听）
        delta < 0：从底部缩一行
        """
        if not self.book:
            return None
        image_width = self.book.render(self.page).width
        box = self._selected_box
        if not box:
            # 还没选过：就取鼠标当前所在行（没有就第一行）
            pointer = self._last_pointer
            point = self._image_coords(pointer) if pointer else None
            band = self._band_for(*point) if point else None
            bands = self._page_bands()
            if not band and bands:
                band = bands[0]
            if not band:
                return None
            box = (0, band[0], image_width, band[1])

        bands = self._page_bands()
        if not bands:
            return None
        x1, top, x2, bottom = box
        inside = [index for index, (band_top, band_bottom) in enumerate(bands)
                  if band_bottom > top + 2 and band_top < bottom - 2]
        if not inside:
            return None
        first, last = inside[0], inside[-1]
        if delta > 0:
            last = min(len(bands) - 1, last + 1)
        elif delta < 0 and last > first:
            last -= 1
        new_top = min(bands[first][0], bands[last][0])
        new_bottom = max(bands[first][1], bands[last][1])
        new_box = (x1, new_top, x2, new_bottom)
        self._selected_box = new_box
        self._draw_box(new_box)
        if self.on_region:
            self.on_region(self.book, self.page, new_box)
        return None

    def _on_drag(self, event):
        if not self._drag_start:
            return None
        point = self._image_coords(event)
        if not point:
            return None
        start_x, _start_y, band = self._drag_start
        x1, x2 = sorted((start_x, point[0]))
        # 纵向跨到别的谱行时，把中间那几行一起圈进来
        other = self._band_containing(point[1], fallback=band)
        top = min(band[0], other[0])
        bottom = max(band[1], other[1])
        self._hover_box = (x1, top, x2, bottom)
        self._draw_box(self._hover_box)
        return None

    def _on_release(self, event):
        if not self._drag_start:
            return None
        start_x, start_y, band = self._drag_start
        self._drag_start = None
        point = self._image_coords(event)
        if not point:
            return None
        x, y = point
        image_width = self.book.render(self.page).width
        other = self._band_containing(y, fallback=band)
        top = min(band[0], other[0])
        bottom = max(band[1], other[1])
        multi_system = bottom - top > (band[1] - band[0]) + 4
        if abs(x - start_x) < 8 and not multi_system:
            # 没怎么拖 = 单击：只保留高亮，不播放（改为双击才播放，避免误触）
            box = (0, band[0], image_width, band[1])
            self._selected_box = box
            self._draw_box(box)
            return None
        x1, x2 = sorted((start_x, x))
        box = (x1, top, x2, bottom)
        self._selected_box = box
        self._draw_box(box)
        if self.on_region:
            self.on_region(self.book, self.page, box)
        return None

    # ---------------------------------------------------------------- 显示
    def configure_model(self):
        """打开模型接口设置（任何 OpenAI 兼容服务）。"""
        if self.on_model:
            try:
                self.on_model()
            except Exception as exc:
                self.hint.configure(text='打不开模型设置：%s' % exc)

    def toggle_fit(self):
        self._fit = not self._fit
        self.fit_btn.configure(text='适合窗口' if self._fit else '原始大小')
        self._redraw()

    def _sync_page_entry(self):
        try:
            self.page_var.set(str(self.page))
        except tk.TclError:
            pass

    def _show(self):
        self._sync_page_entry()
        self._redraw()
        if self.book:
            self.hint.configure(
                text=f'{os.path.basename(self.book.path)}  ·  第 {self.page} / {self.book.pages} 页')

    def _redraw(self):
        if not self.book:
            return
        from PIL import ImageTk
        try:
            image = self.book.render(self.page)
        except Exception as exc:
            self.hint.configure(text=f'这一页渲染失败：{exc}')
            return
        area_w = max(200, self.canvas.winfo_width())
        area_h = max(200, self.canvas.winfo_height())
        if self._fit:
            ratio = min(area_w / image.width, area_h / image.height)
        else:
            ratio = 1.0
        ratio = max(0.2, min(ratio, 4.0))
        target = (max(1, int(image.width * ratio)), max(1, int(image.height * ratio)))
        if target != image.size:
            from PIL import Image
            image = image.resize(target, Image.LANCZOS)
        self._photo = ImageTk.PhotoImage(image)
        if self._image_id is None:
            self._image_id = self.canvas.create_image(0, 0, anchor='nw', image=self._photo)
        else:
            self.canvas.itemconfigure(self._image_id, image=self._photo)
        self.canvas.configure(scrollregion=(0, 0, max(target[0], area_w), max(target[1], area_h)))
        # 水平居中（竖直方向「适合窗口」时本来就填满，原始大小时从顶部看）
        offset_x = max(0, int((area_w - target[0]) / 2))
        self.canvas.coords(self._image_id, offset_x, 0)
        # 记下显示比例与偏移，左键点击时用来换算成原图坐标
        self._scale = ratio
        self._offset_x = offset_x
        self._rendered_page = self.page
        # 旧矩形必须从画布上真正删掉，否则翻页后还停在旧位置（之前的 bug）
        if self._rect_id is not None:
            try:
                self.canvas.delete(self._rect_id)
            except tk.TclError:
                pass
        self._rect_id = None
        self._hover_box = None
        self._drag_start = None
        if self._last_pointer:
            self.after_idle(self.update_hover)
        if self._fit:
            self.canvas.yview_moveto(0)

    def apply_theme(self):
        try:
            self.canvas.configure(bg=theme_bg())
        except tk.TclError:
            pass
        self._style_page_entry()

    def _style_page_entry(self):
        """页码框在亮色下要有一点底色，否则白底白框看不出来。"""
        entry = getattr(self, 'page_entry', None)
        if entry is None:
            return
        try:
            bg = theme_bg()
            red, green, blue = _hex_rgb(bg)
        except Exception:
            red, green, blue = (255, 255, 255)
        light = 0.299 * red + 0.587 * green + 0.114 * blue > 140
        field = '#e8f1fb' if light else '#1d2a38'
        foreground = '#1f2937' if light else '#e6e6e6'
        border = '#b9d4f2' if light else '#2f4256'
        try:
            style = tb.Style()
            style.configure('PageNum.TEntry', fieldbackground=field,
                            foreground=foreground, bordercolor=border,
                            lightcolor=field, darkcolor=field, insertcolor=foreground)
            entry.configure(style='PageNum.TEntry')
        except Exception:
            pass

    # ---------------------------------------------------------------- 分析
    def analyze(self):
        if not self.book or self._busy:
            return
        if not self.on_analyze:
            return
        self._busy = True
        self.analyze_btn.configure(state='disabled', text='分析中…')
        page = self.page

        def worker():
            try:
                self.on_analyze(self.book, page)
            finally:
                self.post(self._done)

        threading.Thread(target=worker, daemon=True).start()

    def _done(self):
        self._busy = False
        try:
            self.analyze_btn.configure(state='normal', text='分析本页')
        except tk.TclError:
            pass
