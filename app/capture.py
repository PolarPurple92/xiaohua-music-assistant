# -*- coding: utf-8 -*-
"""全屏遮罩框选截图。

相比旧版：加了操作提示、拖拽时实时显示尺寸、Esc/右键取消、松手后先隐藏遮罩再抓屏
（避免把半透明遮罩拍进去）。
"""
import datetime
import os
import tkinter as tk

from PIL import ImageGrab

from settings import SCREENSHOT_DIR


class ScreenCapture:
    def __init__(self, master, callback):
        self.master = master
        self.callback = callback
        self.start = (0, 0)
        self.rect = None

        self.top = tk.Toplevel(master)
        self.top.attributes('-fullscreen', True, '-alpha', 0.30, '-topmost', True)
        self.top.configure(cursor='crosshair')
        self.top.attributes('-alpha', 0.30)

        self.canvas = tk.Canvas(self.top, bg='#101418', highlightthickness=0, bd=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)
        sw = self.top.winfo_screenwidth()
        self.hint = self.canvas.create_text(
            sw // 2, 60,
            text='拖动框选五线谱区域    ·    Esc / 右键 取消',
            fill='#f2f5f8', font=('Microsoft YaHei UI', 15, 'bold'),
        )
        self.size_tag = self.canvas.create_text(
            0, 0, text='', fill='#f2f5f8', font=('Microsoft YaHei UI', 11), anchor='nw',
        )

        self.canvas.bind('<ButtonPress-1>', self.on_press)
        self.canvas.bind('<B1-Motion>', self.on_drag)
        self.canvas.bind('<ButtonRelease-1>', self.on_release)
        self.top.bind('<Escape>', self.cancel)
        self.canvas.bind('<Button-3>', self.cancel)
        self.top.focus_force()

    # ---- 交互
    def on_press(self, event):
        self.start = (self.top.winfo_pointerx(), self.top.winfo_pointery())
        self.rect = self.canvas.create_rectangle(
            event.x, event.y, event.x, event.y,
            outline='#2ecc71', width=2, fill='#2ecc71', stipple='gray50',
        )

    def on_drag(self, event):
        if self.rect is None:
            return
        x0, y0 = self.start[0] - self.top.winfo_rootx(), self.start[1] - self.top.winfo_rooty()
        self.canvas.coords(self.rect, x0, y0, event.x, event.y)
        self.canvas.coords(self.size_tag, min(x0, event.x) + 6, min(y0, event.y) + 6)
        self.canvas.itemconfigure(
            self.size_tag, text=f'{abs(event.x - x0)} × {abs(event.y - y0)}')

    def on_release(self, event):
        end = (self.top.winfo_pointerx(), self.top.winfo_pointery())
        x1, x2 = sorted((self.start[0], end[0]))
        y1, y2 = sorted((self.start[1], end[1]))
        self.top.destroy()

        if x2 - x1 < 10 or y2 - y1 < 10:
            self.callback(None)
            return

        self.master.after(120, lambda: self._grab(x1, y1, x2, y2))

    def _grab(self, x1, y1, x2, y2):
        try:
            img = ImageGrab.grab(bbox=(x1, y1, x2, y2))
            stamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
            save_path = os.path.join(SCREENSHOT_DIR, f'cap_{stamp}.png')
            img.save(save_path)
            self.callback(save_path)
        except Exception:
            self.callback(None)

    def cancel(self, _event=None):
        try:
            self.top.destroy()
        except tk.TclError:
            pass
        self.callback(None)
