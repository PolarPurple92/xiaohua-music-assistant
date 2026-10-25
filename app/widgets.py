# -*- coding: utf-8 -*-
"""ttk 控件：药丸、分段选择、文件列表、状态栏、封面墙（含缩略图缓存）。"""
import os
import time
import tkinter as tk

import ttkbootstrap as tb
from ttkbootstrap.constants import BOTH, END, LEFT, RIGHT, X, Y, YES

from settings import IMAGE_EXTS
from theme import _blend, theme_bg
from theme import FONT_BODY, FONT_NAME, FONT_SMALL, FONT_TITLE, GAP, PAD
from util import human_size


class Chip(tb.Frame):
    """状态药丸：一个彩色圆点 + 文字，点击可触发动作。

    圆点用 Label + bootstyle 实现而不是 Canvas —— Canvas 是原生控件，
    背景色不会跟着主题变，暗色下会露出一块浅色方块。
    """

    def __init__(self, master, text='', command=None, **kwargs):
        super().__init__(master, **kwargs)
        self.dot = tb.Label(self, text='●', bootstyle='secondary', font=(FONT_NAME, 11))
        self.dot.pack(side=LEFT, padx=(0, 5))
        self.label = tb.Label(self, text=text, font=FONT_SMALL)
        self.label.pack(side=LEFT)
        if command is not None:
            for widget in (self, self.label, self.dot):
                widget.bind('<Button-1>', lambda _e: command())
                widget.configure(cursor='hand2')

    def set_state(self, text, ok=True):
        self.label.configure(text=text)
        self.dot.configure(bootstyle='success' if ok else 'danger')


class Segmented(tb.Frame):
    """一排互斥的胶囊按钮，用来切换列表分类。"""

    def __init__(self, master, options, variable, command=None, **kwargs):
        super().__init__(master, **kwargs)
        self.variable = variable
        for index, (label, value) in enumerate(options):
            btn = tb.Radiobutton(
                self, text=label, value=value, variable=variable,
                bootstyle='outline-toolbutton', command=command,
                width=len(label) + 4, padding=(8, 3),
            )
            btn.pack(side=LEFT, padx=(0 if index == 0 else 6, 0))


class FileList(tb.Frame):
    """树形文件列表：名称 / 大小 / 时间，双击与右键回调交给上层。"""

    def __init__(self, master, on_open=None, on_menu=None, show_index=False, **kwargs):
        super().__init__(master, **kwargs)
        self.on_open = on_open
        self.on_menu = on_menu
        self.show_index = show_index
        self._count = 0
        self.tree = tb.Treeview(
            self,
            columns=('size', 'time'),
            show='tree headings',
            bootstyle='primary',
            selectmode='browse',
        )
        self.tree.heading('#0', text='名称', anchor='w')
        self.tree.heading('size', text='大小', anchor='e')
        self.tree.heading('time', text='修改时间', anchor='e')
        self.tree.column('#0', width=260, minwidth=160, stretch=True)
        self.tree.column('size', width=80, minwidth=60, anchor='e', stretch=False)
        self.tree.column('time', width=130, minwidth=100, anchor='e', stretch=False)
        self.scroll = tb.Scrollbar(self, orient='vertical', command=self.tree.yview, bootstyle='round')
        self.tree.configure(yscrollcommand=self.scroll.set)
        self.tree.pack(side=LEFT, fill=BOTH, expand=YES)
        self.scroll.pack(side=RIGHT, fill=Y)
        self.tree.tag_configure('empty', foreground='#8a8a8a')
        self.tree.bind('<Double-Button-1>', self._on_double)
        self.tree.bind('<Button-3>', self._on_right)
        self.tree.bind('<Return>', self._on_double)

    # 隔行浅色，播放列表那种阅读节奏
    def _stripe(self):
        try:
            colours = tb.Style().colors
            self.tree.tag_configure('odd', background=_blend(colours.bg, colours.fg, 0.06))
        except Exception:
            pass

    def _on_double(self, _event=None):
        if self.selected() and self.on_open:
            self.on_open()

    def _on_right(self, event):
        row = self.tree.identify_row(event.y)
        if row:
            self.tree.selection_set(row)
        if self.on_menu:
            self.on_menu(event)

    def set_items(self, items, empty_hint='暂无文件'):
        self._stripe()
        self.tree.delete(*self.tree.get_children())
        self._count = len(items)
        if not items:
            self.tree.insert('', END, iid='__empty__', text='  ' + empty_hint,
                             values=('', ''), tags=('empty',))
            return
        for index, item in enumerate(items, start=1):
            label = f'{index:>2}   {item["name"]}' if self.show_index else '  ' + item['name']
            tags = ('odd',) if index % 2 == 0 else ()
            self.tree.insert('', END, iid=item['iid'], text=label,
                             values=(item.get('size', ''), item.get('time', '')), tags=tags)

    def selected(self):
        sel = self.tree.selection()
        if not sel or sel[0] == '__empty__':
            return None
        return sel[0]

    def select_iid(self, iid):
        if iid and self.tree.exists(iid):
            self.tree.selection_set(iid)
            self.tree.see(iid)


class StatusBar(tb.Frame):
    """底部状态栏：左侧文字 + 右侧细进度条（空闲时隐藏）。"""

    def __init__(self, master, **kwargs):
        kwargs.setdefault('padding', (PAD, 6, PAD, 10))
        super().__init__(master, **kwargs)
        self.text = tb.Label(self, text='就绪', font=FONT_SMALL, bootstyle='secondary')
        self.text.pack(side=LEFT)
        self.hint = tb.Label(self, text='', font=FONT_SMALL, bootstyle='secondary')
        self.hint.pack(side=LEFT, padx=(12, 0))
        self.progress = tb.Progressbar(self, mode='indeterminate', length=160,
                                       bootstyle='primary-striped', value=0)
        self._busy = False

    def set(self, message, hint=None):
        self.text.configure(text=message)
        if hint is not None:
            self.hint.configure(text=hint)

    def busy(self, message=None):
        if message:
            self.set(message)
        if not self._busy:
            self._busy = True
            self.progress.pack(side=RIGHT)
            self.progress.start(14)

    def idle(self, message=None):
        if message is not None:
            self.set(message)
        if self._busy:
            self._busy = False
            try:
                self.progress.stop()
            except tk.TclError:
                pass
            self.progress.pack_forget()


class ThumbGrid(tb.Frame):
    """可滚动的封面网格 —— 像播放器的专辑墙。"""

    COVER = (232, 164)
    RADIUS = 16

    def __init__(self, master, on_open=None, on_menu=None, **kwargs):
        super().__init__(master, **kwargs)
        self.on_open = on_open
        self.on_menu = on_menu
        self._images = {}
        self._cards = []
        self._empty = False
        self._empty_overlay = None

        self.canvas = tk.Canvas(self, highlightthickness=0, bd=0, bg=theme_bg())
        self.scroll = tb.Scrollbar(self, orient='vertical', command=self.canvas.yview,
                                   bootstyle='round')
        self.canvas.configure(yscrollcommand=self.scroll.set)
        self.canvas.pack(side=LEFT, fill=BOTH, expand=YES)
        self.scroll.pack(side=RIGHT, fill=Y)

        self.inner = tb.Frame(self.canvas)
        self._window = self.canvas.create_window((0, 0), window=self.inner, anchor='nw')
        self.inner.bind('<Configure>', self._on_inner_configure)
        self.canvas.bind('<Configure>', self._on_canvas_configure)
        for widget in (self.canvas, self.inner):
            widget.bind('<Enter>', self._bind_wheel)
            widget.bind('<Leave>', self._unbind_wheel)

    # ---- 主题
    def apply_theme(self):
        """原生 Canvas 的背景色不会自动跟随主题，换肤后手动同步一次。"""
        try:
            self.canvas.configure(bg=theme_bg())
        except tk.TclError:
            pass
        # 圆角封面是按旧底色合成的，换肤后重新生成
        for path, (label, photo) in list(self._images.items()):
            new = rounded_thumbnail(path, self.COVER, self.RADIUS, master=self)
            if new is not None:
                label.configure(image=new)
                self._images[path] = (label, new)

    # ---- 滚动
    def _bind_wheel(self, _event=None):
        self.canvas.bind_all('<MouseWheel>', self._on_wheel)

    def _unbind_wheel(self, _event=None):
        self.canvas.unbind_all('<MouseWheel>')

    def _on_wheel(self, event):
        try:
            self.canvas.yview_scroll(int(-event.delta / 120), 'units')
        except tk.TclError:
            pass

    def _on_inner_configure(self, _event=None):
        self.canvas.configure(scrollregion=self.canvas.bbox('all'))

    def _on_canvas_configure(self, event):
        self.canvas.itemconfigure(self._window, width=event.width)
        self._relayout(event.width)

    # ---- 空状态覆盖层
    def _show_empty(self):
        """空状态用一层覆盖在画布上，位置由 place 精确居中，不依赖画布高度。"""
        self._hide_empty()
        # 覆盖在 canvas 上（不是整个 ThumbGrid），否则会被右侧滚动条挤偏
        holder = tb.Frame(self.canvas)
        holder.place(x=0, y=0, relwidth=1, relheight=1)
        block = tb.Frame(holder)
        block.place(relx=0.5, rely=0.5, anchor='center')
        tb.Label(block, text='♪', font=(FONT_NAME, 46), bootstyle='secondary').pack()
        tb.Label(block, text='还没有曲谱封面', font=(FONT_NAME, 13, 'bold')).pack(pady=(12, 4))
        tb.Label(block, text='点右上角「截取五线谱」，或把图片拖进来',
                 font=FONT_SMALL, bootstyle='secondary').pack()
        self._empty_overlay = holder
        try:
            self.scroll.pack_forget()          # 空的时候滚动条没意义
        except Exception:
            pass

    def _hide_empty(self):
        if self._empty_overlay is not None:
            try:
                self._empty_overlay.destroy()
            except tk.TclError:
                pass
            self._empty_overlay = None
            try:
                self.scroll.pack(side=RIGHT, fill=Y)
            except Exception:
                pass

    # ---- 内容
    def set_files(self, files, loader=None):
        for card in self._cards:
            card.destroy()
        self._cards.clear()
        self._images.clear()
        self._empty = not files

        for col in range(12):
            self.inner.columnconfigure(col, weight=0)
        self.inner.rowconfigure(0, weight=0)

        if self._empty:
            self._show_empty()
            return

        self._hide_empty()
        for index, path in enumerate(files):
            self._cards.append(self._build_card(index, path))
        self._relayout(self.canvas.winfo_width())

    def _build_card(self, index, path):
        card = tb.Frame(self.inner, padding=(6, 6, 6, 4))
        name = os.path.basename(path)
        photo = rounded_thumbnail(path, self.COVER, self.RADIUS, master=self)
        if photo is not None:
            cover = tb.Label(card, image=photo, anchor='center', cursor='hand2')
            self._images[path] = (cover, photo)
        else:
            cover = tb.Label(card, text='♪', bootstyle='secondary', cursor='hand2',
                             width=18, padding=(0, 40), anchor='center',
                             font=(FONT_NAME, 26))
        cover.pack(fill=BOTH, expand=YES)

        title = os.path.splitext(name)[0]
        # 允许折成两行：中文约 26 字、英文约 42 字，再多才省略。
        # wraplength 卡在封面宽度内，别让文字把卡片撑宽（否则整排缩略图会错位）
        limit = 26 if any('一' <= ch <= '鿿' for ch in title) else 42
        if len(title) > limit:
            title = title[:limit - 1] + '…'
        label = tb.Label(card, text=title, anchor='w', justify='left',
                         font=(FONT_NAME, 10, 'bold'), cursor='hand2',
                         wraplength=self.COVER[0] - 6, width=0)
        label.pack(fill=X, pady=(8, 0))

        try:
            stat = os.stat(path)
            meta_text = f'{human_size(stat.st_size)} · {time.strftime("%m-%d %H:%M", time.localtime(stat.st_mtime))}'
        except OSError:
            meta_text = ''
        meta = tb.Label(card, text=meta_text, anchor='w', font=FONT_SMALL,
                        bootstyle='secondary', cursor='hand2')
        meta.pack(fill=X)

        def hover(_event=None, widget=label, on=True):
            try:
                widget.configure(bootstyle='primary' if on else 'default')
            except tk.TclError:
                pass

        for widget in (card, cover, label, meta):
            widget.bind('<Double-Button-1>', lambda _e, p=path: self.on_open and self.on_open(p))
            widget.bind('<Button-3>', lambda e, p=path: self.on_menu and self.on_menu(e, p))
            widget.bind('<Enter>', lambda e, w=label: hover(e, w, True))
            widget.bind('<Leave>', lambda e, w=label: hover(e, w, False))
            widget.configure(cursor='hand2')
        return card

    def _relayout(self, width):
        if not self._cards or self._empty:
            return
        per_row = max(1, (max(width, 1) - 8) // (self.COVER[0] + 34))
        for i, card in enumerate(self._cards):
            card.grid(row=i // per_row, column=i % per_row, padx=4, pady=6, sticky='nsew')
        for col in range(per_row):
            self.inner.columnconfigure(col, weight=1)


# 封面缓存：(路径, mtime, 尺寸, 圆角, 底色) → PhotoImage。
# 每次刷新都重新解码+缩放所有截图太浪费，图多了会明显卡；切主题底色变了会自动重建。
_THUMB_CACHE = {}
_THUMB_ORDER = []
_THUMB_LIMIT = 240
_THUMB_INTERP = None


def _thumb_guard(master):
    """换了 Tk 解释器（比如测试里重建 root）旧 PhotoImage 就失效了，整体清掉。"""
    global _THUMB_INTERP
    try:
        interp = master.tk.interpaddr() if master is not None else None
    except Exception:
        interp = None
    if _THUMB_INTERP is not None and interp != _THUMB_INTERP:
        _THUMB_CACHE.clear()
        _THUMB_ORDER.clear()
    _THUMB_INTERP = interp


def rounded_thumbnail(path, size=(208, 146), radius=14, bg=None, master=None):
    """圆角封面：按主题底色合成，角上不会出现生硬的白边（带 LRU 缓存）。"""
    try:
        from PIL import Image, ImageDraw, ImageTk
    except Exception:
        return None
    if not path or not str(path).lower().endswith(IMAGE_EXTS):
        return None
    bg = bg or theme_bg()
    _thumb_guard(master)

    try:
        stat = os.stat(path)
        stamp = (stat.st_mtime_ns, stat.st_size)
    except OSError:
        stamp = (0, 0)
    key = (os.path.abspath(path), stamp, size, radius, bg)
    cached = _THUMB_CACHE.get(key)
    if cached is not None:
        return cached

    try:
        with Image.open(path) as img:
            img = img.convert('RGB')
            img.thumbnail(size)
            canvas = Image.new('RGB', size, bg)
            canvas.paste(img, ((size[0] - img.width) // 2, (size[1] - img.height) // 2))
    except Exception:
        return None
    mask = Image.new('L', size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, size[0] - 1, size[1] - 1),
                                           radius=radius, fill=255)
    out = Image.new('RGB', size, bg)
    out.paste(canvas, (0, 0), mask)
    photo = ImageTk.PhotoImage(out)

    _THUMB_CACHE[key] = photo
    _THUMB_ORDER.append(key)
    while len(_THUMB_ORDER) > _THUMB_LIMIT:
        old = _THUMB_ORDER.pop(0)
        _THUMB_CACHE.pop(old, None)
    return photo
