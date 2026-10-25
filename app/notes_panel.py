# -*- coding: utf-8 -*-
"""讲解面板（L1）：把 analysis 产出的「事实」按小节排成卡片，随播放高亮。

这一层不联网、不调 AI —— 显示的全是算出来的东西：
    调性 / 拍号 / 小结数 / 终止式 + 每小节的和声、音域、声部、特征
以后接 LLM 时，它的输入就是这里的数据（brief），所以先把这块做扎实。
"""
import tkinter as tk

import ttkbootstrap as tb
from ttkbootstrap.constants import BOTH, LEFT, RIGHT, X, Y, YES

import analysis
from theme import (FONT_NAME, FONT_SMALL, FONT_SECTION, PAD,
                   theme_bg, theme_fg, theme_muted)

TEXT_FONT = (FONT_NAME, 10)
TEXT_BODY_FONT = (FONT_NAME, 9)


class NotesPanel(tb.Frame):
    """右侧的讲解栏。默认收起来，由主窗口的开关控制显示。"""

    WIDTH = 330

    def __init__(self, master, on_close=None, **kwargs):
        super().__init__(master, width=self.WIDTH, **kwargs)
        self.pack_propagate(False)
        self.on_close = on_close
        self._cards = {}
        self._current = None
        self._brief = None
        self._mode = 'notes'
        self._notes_body = 'cards'     # 'cards' 或 'text'，切回讲解时据此恢复

        head = tb.Frame(self, padding=(PAD, PAD, PAD, 4))
        head.pack(fill=X)
        self.title_label = tb.Label(head, text='讲解', font=FONT_SECTION)
        self.title_label.pack(side=LEFT)
        if on_close is not None:
            tb.Button(head, text='×', bootstyle='secondary-link', width=2,
                      command=on_close).pack(side=RIGHT)
        self._mode_buttons = {}
        for key, label in (('chat', '对话'), ('notes', '讲解')):
            btn = tb.Button(head, text=label, width=4, bootstyle='secondary-link',
                            command=lambda k=key: self.set_mode(k))
            btn.pack(side=RIGHT, padx=(0, 4))
            self._mode_buttons[key] = btn
        self._mode_buttons['notes'].configure(bootstyle='primary')

        self.summary = tb.Label(self, text='播放一首曲子，这里会显示逐小节分析',
                                font=FONT_SMALL, bootstyle='secondary',
                                padding=(PAD, 0, PAD, 8), justify='left',
                                wraplength=self.WIDTH - PAD * 2)
        self.summary.pack(fill=X)

        tb.Separator(self).pack(fill=X)

        self.canvas = tk.Canvas(self, highlightthickness=0, bd=0, bg=theme_bg())
        self.scroll = tb.Scrollbar(self, orient='vertical', command=self.canvas.yview,
                                   bootstyle='round')
        self.canvas.configure(yscrollcommand=self.scroll.set)
        self.scroll.pack(side=RIGHT, fill=Y)
        self.canvas.pack(side=LEFT, fill=BOTH, expand=YES)

        self.inner = tb.Frame(self.canvas, padding=(PAD, 10, 10, PAD))
        self._window = self.canvas.create_window((0, 0), window=self.inner, anchor='nw')
        self.inner.bind('<Configure>',
                        lambda _e: self.canvas.configure(scrollregion=self.canvas.bbox('all')))
        self.canvas.bind('<Configure>',
                         lambda event: self.canvas.itemconfigure(self._window, width=event.width))
        for widget in (self.canvas, self.inner):
            widget.bind('<Enter>', self._bind_wheel)
            widget.bind('<Leave>', self._unbind_wheel)

        # 纯文字模式（PDF 讲解用）：和卡片模式互斥，谁显示谁 pack
        self.text_holder = tb.Frame(self)
        self.text_widget = tk.Text(self.text_holder, wrap='word', bd=0, height=10,
                                   highlightthickness=0, padx=12, pady=10,
                                   font=TEXT_BODY_FONT, cursor='arrow')
        self.text_scroll = tb.Scrollbar(self.text_holder, orient='vertical',
                                        command=self.text_widget.yview, bootstyle='round')
        self.text_widget.configure(yscrollcommand=self.text_scroll.set)
        self.text_scroll.pack(side=RIGHT, fill=Y)
        self.text_widget.pack(side=LEFT, fill=BOTH, expand=YES)
        self.text_widget.tag_configure('h2', font=(FONT_NAME, 11, 'bold'),
                                       spacing1=10, spacing3=4)
        self.text_widget.tag_configure('h3', font=(FONT_NAME, 10, 'bold'),
                                       spacing1=8, spacing3=2)
        self.text_widget.tag_configure('body', font=TEXT_BODY_FONT, spacing1=2)
        self.text_widget.tag_configure('code', font=(FONT_NAME, 9), spacing1=1,
                                       lmargin1=10, lmargin2=10)
        self.text_widget.configure(state='disabled')
        self._apply_text_colors()

        # 对话区（追问）
        from chat_pane import ChatPane
        self.chat_pane = ChatPane(self)

    # ------------------------------------------------------------ 模式切换
    def set_mode(self, mode):
        """notes = 讲解（卡片或文字），chat = 追问对话。

        注意「讲解」有两种内容形态：曲谱库用卡片、PDF 讲解用纯文字。
        切回讲解时必须恢复**上次用的那一种**，否则 PDF 模式下会显示空的卡片区。
        """
        self._mode = mode
        for key, btn in self._mode_buttons.items():
            try:
                btn.configure(bootstyle='primary' if key == mode else 'secondary-link')
            except tk.TclError:
                pass
        if mode == 'chat':
            self._hide_cards_area()
            if self.text_holder.winfo_manager():
                self.text_holder.pack_forget()
            if not self.chat_pane.winfo_manager():
                self.chat_pane.pack(fill=BOTH, expand=YES)
        else:
            if self.chat_pane.winfo_manager():
                self.chat_pane.pack_forget()
            if self._notes_body == 'text':
                self._hide_cards_area()
                if not self.text_holder.winfo_manager():
                    self.text_holder.pack(fill=BOTH, expand=YES)
            else:
                if self.text_holder.winfo_manager():
                    self.text_holder.pack_forget()
                self._show_cards_area()

    def show_chat(self):
        self.set_mode('chat')

    def _apply_text_colors(self):
        try:
            self.text_widget.configure(bg=theme_bg(), fg=theme_fg(),
                                       insertbackground=theme_fg())
            self.text_widget.tag_configure('h2', foreground=theme_fg())
            self.text_widget.tag_configure('h3', foreground=theme_fg())
            self.text_widget.tag_configure('body', foreground=theme_fg())
        except tk.TclError:
            pass

    # ------------------------------------------------------------ 主题
    def apply_theme(self):
        """原生 Canvas / Text 不跟主题走，换肤后手动同步。"""
        try:
            self.canvas.configure(bg=theme_bg())
        except tk.TclError:
            pass
        self._apply_text_colors()
        try:
            self.chat_pane.apply_theme()
        except Exception:
            pass
        if self._notes_body == 'text':
            # 文字形态只刷新颜色，内容不动（否则会被 _rebuild 换成空卡片）
            if self._mode == 'notes' and not self.text_holder.winfo_manager():
                self._hide_cards_area()
                self.text_holder.pack(fill=BOTH, expand=YES)
            return
        self._rebuild()

    # ------------------------------------------------------------ 纯文字模式
    def show_text(self, title='', text='', subtitle=''):
        """显示一段文字（PDF 讲解结果、提示语等），切到文字模式。"""
        self._brief = None
        for child in self.inner.winfo_children():
            child.destroy()
        self._cards = {}
        self._current = None
        self.summary.configure(text=subtitle or title or '')
        self._notes_body = 'text'
        self.set_mode('notes')
        self._hide_cards_area()
        if self.chat_pane.winfo_manager():
            self.chat_pane.pack_forget()
        self.text_holder.pack(fill=BOTH, expand=YES)
        widget = self.text_widget
        widget.configure(state='normal')
        widget.delete('1.0', 'end')
        in_code = False
        for line in (text or '').splitlines():
            stripped = line.rstrip()
            if stripped.strip().startswith('```'):
                in_code = not in_code
                continue            # 围栏本身不显示
            if in_code:
                widget.insert('end', stripped + '\n', 'code')
                continue
            if stripped.startswith('### '):
                widget.insert('end', stripped[4:] + '\n', 'h3')
            elif stripped.startswith('## '):
                widget.insert('end', stripped[3:] + '\n', 'h2')
            elif stripped.startswith('# '):
                widget.insert('end', stripped[2:] + '\n', 'h2')
            else:
                # 简单清掉行内标记，免得界面上显示 ** 和 `
                clean = stripped.replace('**', '').replace('`', '')
                widget.insert('end', clean + '\n', 'body')
        widget.configure(state='disabled')
        widget.yview_moveto(0)

    def _hide_cards_area(self):
        if self.canvas.winfo_manager():
            self.canvas.pack_forget()
        if self.scroll.winfo_manager():
            self.scroll.pack_forget()

    def _show_cards_area(self):
        if self.text_holder.winfo_manager():
            self.text_holder.pack_forget()
        if self.chat_pane.winfo_manager():
            self.chat_pane.pack_forget()
        if not self.scroll.winfo_manager():
            self.scroll.pack(side=RIGHT, fill=Y)
        if not self.canvas.winfo_manager():
            self.canvas.pack(side=LEFT, fill=BOTH, expand=YES)

    # ------------------------------------------------------------ 滚动
    def _bind_wheel(self, _event=None):
        self.canvas.bind_all('<MouseWheel>', self._on_wheel)

    def _unbind_wheel(self, _event=None):
        self.canvas.unbind_all('<MouseWheel>')

    def _on_wheel(self, event):
        try:
            self.canvas.yview_scroll(int(-event.delta / 120), 'units')
        except tk.TclError:
            pass

    # ------------------------------------------------------------ 内容
    def set_brief(self, brief, subtitle=''):
        self._brief = brief
        self._rebuild(subtitle)

    def clear(self, message='播放一首曲子，这里会显示逐小节分析'):
        self._brief = None
        self._rebuild(message=message)

    def _rebuild(self, subtitle='', message=None):
        self._notes_body = 'cards'
        self._show_cards_area()
        for child in self.inner.winfo_children():
            child.destroy()
        self._cards = {}
        self._current = None
        if message:
            self.summary.configure(text=message)
            return
        brief = self._brief
        if not brief:
            self.summary.configure(text=subtitle or '播放一首曲子，这里会显示逐小节分析')
            return
        summary = analysis.summarize(brief)
        self.summary.configure(text=summary or subtitle)
        for entry in brief.get('measure_list', []):
            self._add_card(entry)
        if not brief.get('measure_list'):
            tb.Label(self.inner, text='没有解析出小节', font=FONT_SMALL,
                     bootstyle='secondary').pack(anchor='w')

    def _add_card(self, entry):
        card = tb.Frame(self.inner, padding=(10, 8))
        card.pack(fill=X, pady=(0, 6))

        top = tb.Frame(card)
        top.pack(fill=X)
        marker = tb.Label(top, text='  ', font=FONT_SMALL, width=2, bootstyle='secondary')
        marker.pack(side=LEFT)
        number = tb.Label(top, text=f'第 {entry["number"]} 小节',
                          font=(FONT_NAME, 10, 'bold'))
        number.pack(side=LEFT)
        timing = tb.Label(top, text=f'{entry["start"]:.1f}–{entry["end"]:.1f}s',
                          font=FONT_SMALL, bootstyle='secondary')
        timing.pack(side=RIGHT)

        romans = [chord['roman'] or '?' for chord in entry.get('chords', [])]
        symbols = [chord['symbol'] for chord in entry.get('chords', []) if chord['symbol']]
        first_line = ' → '.join(romans) if romans else '（未识别出和声）'
        roman_label = tb.Label(card, text=first_line, font=(FONT_NAME, 10),
                               bootstyle=None if romans else 'secondary')
        roman_label.pack(anchor='w', padx=(22, 0))

        symbol_label = None
        if symbols:
            symbol_label = tb.Label(card, text=' · '.join(symbols), font=FONT_SMALL,
                                    bootstyle='secondary')
            symbol_label.pack(anchor='w', padx=(22, 0))

        # 特征和数字分成两行：中文没有空格，Tk 的 wraplength 不会断行，只能自己分行
        features = [item for item in entry.get('features', []) if item][:3]
        if features:
            tb.Label(card, text=' · '.join(features), font=FONT_SMALL,
                     bootstyle='secondary').pack(anchor='w', padx=(22, 0), pady=(2, 0))

        bits = [f'{entry.get("notes", 0)} 音符']
        if entry.get('voices'):
            bits.append(f'{entry["voices"]} 声部')
        if entry.get('range') and entry['range'][0]:
            bits.append(f'{entry["range"][0]}–{entry["range"][1]}')
        tb.Label(card, text=' · '.join(bits), font=FONT_SMALL,
                 bootstyle='secondary').pack(anchor='w', padx=(22, 0))

        self._cards[entry['number']] = {
            'card': card, 'marker': marker, 'number': number,
            'roman': roman_label, 'symbol': symbol_label,
        }

    # ------------------------------------------------------------ 播放同步
    def set_current(self, number):
        """高亮当前小节；切换时把卡片滚到可见区域。

        只改文字颜色，不动卡片底色 —— 换底色会让子标签的背景和主题对不上，
        反而看不清（ttk 的标签各自带背景色）。
        """
        if number == self._current:
            return
        self._current = number
        for key, widgets in self._cards.items():
            active = key == number
            try:
                widgets['marker'].configure(text='▍' if active else '  ',
                                            bootstyle='success' if active else 'secondary')
                widgets['number'].configure(bootstyle='success' if active else None)
                widgets['roman'].configure(bootstyle='success' if active else None)
            except tk.TclError:
                pass
        if number is not None and number in self._cards:
            self._scroll_into_view(self._cards[number]['card'])

    def _scroll_into_view(self, widget):
        try:
            self.canvas.update_idletasks()
            total = max(1, self.inner.winfo_height())
            view = self.canvas.winfo_height()
            top = widget.winfo_y()
            bottom = top + widget.winfo_height()
            first, last = self.canvas.yview()
            visible_top = first * total
            visible_bottom = last * total
            if top < visible_top:
                self.canvas.yview_moveto(max(0.0, (top - 10) / total))
            elif bottom > visible_bottom:
                self.canvas.yview_moveto(min(1.0, (bottom - view + 10) / total))
        except tk.TclError:
            pass

    def current(self):
        return self._current
