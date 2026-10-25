# -*- coding: utf-8 -*-
"""追问对话面板：和「讲解」并列，同一个右侧栏里切换。

默认提问不带图（快、便宜）；想核对细节时按「带上图」再问。
"""
import time

import tkinter as tk

import ttkbootstrap as tb
from ttkbootstrap.constants import BOTH, LEFT, RIGHT, X, Y, END, YES

from theme import FONT_NAME, FONT_SMALL, PAD, theme_bg, theme_fg, theme_muted


class ChatPane(tb.Frame):
    """对话区：历史记录 + 输入框 + 发送/带图/清空。"""

    def __init__(self, master, on_send=None, on_clear=None, **kwargs):
        super().__init__(master, **kwargs)
        self.on_send = on_send
        self.on_clear = on_clear
        self.include_images = False
        self.allow_web = False              # 本地资料不足时先联网检索
        self._busy = False

        # 先占住底部输入区，再让日志区吃掉剩余高度
        # （反过来 pack 的话，expand 的日志区会把输入区挤扁）
        box = tb.Frame(self, padding=(PAD, 4, PAD, PAD))
        box.pack(side='bottom', fill=X)
        self.entry = tk.Text(box, height=2, wrap='word', bd=0, highlightthickness=1,
                             padx=8, pady=6, font=(FONT_NAME, 9))
        self.entry.pack(fill=X)
        self.entry.bind('<Return>', self._on_return)
        self.entry.bind('<Shift-Return>', lambda _e: None)
        self._apply_entry_colors()

        row = tb.Frame(box)
        row.pack(fill=X, pady=(6, 0))
        self.image_btn = tb.Button(row, text='带上图', bootstyle='secondary-outline',
                                   width=7, command=self.toggle_images)
        self.image_btn.pack(side=LEFT)
        self.web_btn = tb.Button(row, text='联网', bootstyle='secondary-outline',
                                 width=6, command=self.toggle_web)
        self.web_btn.pack(side=LEFT, padx=(6, 0))
        self.clear_btn = tb.Button(row, text='清空', bootstyle='secondary-link',
                                   width=5, command=self._clear)
        self.clear_btn.pack(side=LEFT, padx=(6, 0))
        self.send_btn = tb.Button(row, text='发送', bootstyle='success', width=6,
                                  command=self.submit)
        self.send_btn.pack(side=RIGHT)

        # 日志区最后建：pack 顺序在输入区之后，才会占满剩下的高度
        self.hint = tb.Label(self, text='问这一页的问题，例如「第 3 小节为什么用 IV」',
                             font=FONT_SMALL, bootstyle='secondary', anchor='w',
                             wraplength=300, justify='left')
        self.hint.pack(side='bottom', fill=X, padx=PAD, pady=(4, 0))

        body = tb.Frame(self)
        body.pack(fill=BOTH, expand=YES)
        self.log = tk.Text(body, wrap='word', bd=0, height=3, highlightthickness=0,
                           padx=10, pady=8, font=(FONT_NAME, 9), cursor='arrow',
                           spacing1=2, spacing3=6)
        self.log_scroll = tb.Scrollbar(body, orient='vertical', command=self.log.yview,
                                       bootstyle='round')
        self.log.configure(yscrollcommand=self.log_scroll.set)
        self.log_scroll.pack(side=RIGHT, fill=Y)
        self.log.pack(side=LEFT, fill=BOTH, expand=YES)
        for tag, font, colour in (('me', (FONT_NAME, 9, 'bold'), theme_muted()),
                                  ('bot', (FONT_NAME, 9), theme_fg()),
                                  ('sys', (FONT_NAME, 9), theme_muted())):
            self.log.tag_configure(tag, font=font, foreground=colour,
                                   lmargin1=0, lmargin2=0)
        self.log.tag_configure('me', justify='right', spacing1=8)
        self.log.tag_configure('sys', justify='center', spacing1=10, spacing3=6)
        self.log.configure(state='disabled')
        self._apply_entry_colors()

    # ---------------------------------------------------------------- 主题
    def _apply_entry_colors(self):
        try:
            bg = theme_bg()
            log = getattr(self, 'log', None)     # 构造期可能还没建日志区
            if log is not None:
                log.configure(bg=bg, fg=theme_fg(), insertbackground=theme_fg())
            self.entry.configure(bg=bg, fg=theme_fg(), insertbackground=theme_fg(),
                                 highlightbackground=theme_muted(),
                                 highlightcolor=theme_fg())
        except tk.TclError:
            pass
    def apply_theme(self):
        self._apply_entry_colors()
        for tag, colour in (('me', theme_muted()), ('bot', theme_fg()), ('sys', theme_muted())):
            try:
                self.log.tag_configure(tag, foreground=colour)
            except tk.TclError:
                pass

    # ---------------------------------------------------------------- 记录
    def _write(self, text, tag):
        self.log.configure(state='normal')
        if self.log.index('end-1c') != '1.0':
            self.log.insert(END, '\n')
        self.log.insert(END, text, tag)
        self.log.configure(state='disabled')
        self.log.see(END)

    def add_user(self, text):
        self._write(text, 'me')

    def add_bot(self, text):
        self._write(text, 'bot')

    def add_system(self, text):
        self._write(text, 'sys')

    def clear_log(self):
        self.log.configure(state='normal')
        self.log.delete('1.0', END)
        self.log.configure(state='disabled')

    def load_history(self, messages, analysis_prefix=''):
        self.clear_log()
        if analysis_prefix:
            self.add_system(analysis_prefix)
        for item in messages:
            tag = 'me' if item.get('role') == 'user' else 'bot'
            self._write(item.get('content', ''), tag)

    # ---------------------------------------------------------------- 交互
    def toggle_web(self):
        self.allow_web = not self.allow_web
        try:
            self.web_btn.configure(
                text='联网 ✓' if self.allow_web else '联网',
                bootstyle='primary-outline' if self.allow_web else 'secondary-outline')
        except tk.TclError:
            pass

    def toggle_images(self):
        self.include_images = not self.include_images
        try:
            self.image_btn.configure(
                text='带图 ✓' if self.include_images else '带上图',
                bootstyle='primary-outline' if self.include_images else 'secondary-outline')
        except tk.TclError:
            pass

    def _on_return(self, event):
        if event.state & 0x0001:      # Shift 按下 -> 换行
            return None
        self.submit()
        return 'break'

    def submit(self):
        if self._busy:
            return
        question = self.entry.get('1.0', END).strip()
        if not question:
            return
        self.entry.delete('1.0', END)
        self.add_user(question)
        self.set_busy(True)
        if self.on_send:
            try:
                self.on_send(question, self.include_images, self.allow_web)
            except TypeError:
                self.on_send(question, self.include_images)

    def _clear(self):
        self.clear_log()
        if self.on_clear:
            self.on_clear()

    def set_busy(self, busy, message='思考中…'):
        self._busy = busy
        try:
            self.send_btn.configure(state='disabled' if busy else 'normal',
                                    text='…' if busy else '发送')
            self.hint.configure(text=message if busy else '继续追问，或点「带上图」核对细节')
        except tk.TclError:
            pass

    def focus_entry(self):
        try:
            self.entry.focus_set()
        except tk.TclError:
            pass
