# -*- coding: utf-8 -*-
"""完整模式：播放器版式（左侧导航 + 封面墙 / 播放列表 + 底部播放条）。"""
import datetime
import os
import shutil
import threading
import time
import tkinter as tk
from tkinter import messagebox

import ttkbootstrap as tb
from ttkbootstrap.constants import BOTH, LEFT, RIGHT, X, Y, YES

import base_window
import analysis
import explain
import pipeline
from base_window import BaseWindow, _fmt_time, _list_dir, _render_with_musescore
from glossary_view import GlossaryView
from hotkey import describe
from notes_panel import NotesPanel
from pdf_view import PdfView
from settings import (
    APP_AUTHOR, APP_NAME, APP_SUBTITLE, APP_VERSION, BRIEF_DIR, LLM_FILE,
    ENGINE_LABEL, HOMR_WORK_DIR, IMAGE_EXTS, MIDI_DIR, PREPROCESSED_DIR, SHEET_DIR,
    SCREENSHOT_DIR, SOUNDFONT_DIR, XML_DIR, XML_EXTS,
    engine_available, find_sf2_path, list_soundfonts,
)
from ui_kit import (
    Chip, FileList, Segmented, StatusBar, ThumbGrid, fmt_mmss, human_size,
    rounded_thumbnail, screen_workarea, theme_bg,
    FONT_BODY, FONT_NAME, FONT_SMALL, FONT_TITLE, GAP, PAD,
)

FILTERS = (('MusicXML', 'xml'), ('MIDI', 'midi'), ('乐谱图', 'sheet'))

# 速度术语 → BPM。取的是通行区间里最常用的那个整数值（Allegro 取 120 是因为
# 识别出来的 MIDI 默认就是 120 BPM，这样默认状态能对应上一个术语而不是「自定义」）。
TEMPO_TERMS = (
    ('Largo 广板', 50),
    ('Larghetto 小广板', 60),
    ('Adagio 柔板', 70),
    ('Andante 行板', 90),
    ('Andantino 小行板', 100),
    ('Moderato 中板', 110),
    ('Allegretto 小快板', 116),
    ('Allegro 快板', 120),
    ('Vivace 活板', 160),
    ('Presto 急板', 184),
    ('Prestissimo 最急板', 208),
)
TEMPO_LABEL_TO_BPM = {label: bpm for label, bpm in TEMPO_TERMS}
TEMPO_BPM_TO_LABEL = {bpm: label for label, bpm in TEMPO_TERMS}
TERM_CUSTOM = '自定义'

ABOUT_TEXT = (
    f'{APP_NAME}\n\n'
    f'版本 {APP_VERSION}\n\n'
    f'作者：{APP_AUTHOR}（B站同名）\n\n'
    f'{APP_SUBTITLE}\n\n'
    '截图五线谱 → 自动识别为 MusicXML → 转 MIDI 并播放。\n'
    '内置 homr 深度学习与传统 Audiveris 两套引擎，可随时切换。'
)

UPDATE_NOTES = (
    f'{APP_NAME} v{APP_VERSION} 更新内容：\n\n'
    '1. 定位改为「读谱工具」：PDF 讲解 + 双击谱行试听 + 术语查询\n'
    '2. 内置 homr 识别引擎与音色库，解压即用\n'
    '3. 谱行检测重写：歪页纠偏、分条带检测、假线合并\n'
    '4. 双击播放（防误触），支持拖框与「＋行/－行」扩选多行\n'
    '5. 识别结果与原谱并排对照，多页自动拼接\n'
    '6. 右键可把选中谱行导出为 MIDI（文件名带书名、页码、位置、时间戳）\n'
    '7. 术语页：手动添加、模型自动归类、从自己的书里批量整理\n'
    '8. 追问支持「本地优先、不足再联网」，回答标注依据来源\n'
    '9. 默认亮色主题，可切暗色；界面排版修复\n\n'
    f'作者：{APP_AUTHOR}（B站同名）'
)


def _find_glossary_dir():
    """找出放了 glossary_seed.json 的目录。"""
    here = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.dirname(LLM_FILE),
        os.path.join(here, '..', 'data'),
        os.path.join(here, '..'),
    ]
    for path in candidates:
        if os.path.isfile(os.path.join(path, 'glossary_seed.json')):
            return os.path.abspath(path)
    return os.path.dirname(LLM_FILE)


class FullApp(BaseWindow):
    """完整模式 —— 播放器版式：左侧导航 / 封面墙或播放列表 / 底部播放条。"""

    SIDEBAR_W = 216

    def build(self):
        self._view = 'library'
        self._playing = False
        self._click_busy = False     # 点谱试听是否正在识别
        self._band_cache = {}        # (书, 页) → 该页的谱行区间
        self._preview_window = None  # 识别结果小窗（惰性创建）
        self._play_worker = None     # 当前播放线程
        self._editor_process = None  # MuseScore 编辑窗口进程
        self._editor_hwnd = 0        # MuseScore 窗口句柄
        self._editor_job = None      # 文件监视的 after 任务
        self._editor_xml = ''        # 正在编辑的 MusicXML
        self._editor_mtime = 0.0     # 上次看到的修改时间
        self._progress_job = None
        self._play_started = 0.0
        self._play_duration = 0.0
        self._now_playing = ''
        self._stop_requested = False
        # 术语表：优先用配置同目录，找不到就用程序目录旁边的 data/
        # （开发时是 _unpack/data，便携包是 Xiaohua_MIDI_Modern/data）
        self._glossary_dir = _find_glossary_dir()
        self._glossary = None
        try:
            from glossary import Glossary
            self._glossary = Glossary(self._glossary_dir)
        except Exception as exc:
            print('术语表加载失败:', exc)
        self._brief = None            # 讲解面板用的分析结果
        self._explain_active = False  # 面板当前显示的是「整页讲解」，别被播放盖掉
        self._notes_visible = False

        self.status = StatusBar(self, padding=(PAD, 0, PAD, 6))
        self.status.pack(fill=X, side='bottom')
        self._build_transport()

        body = tb.Frame(self)
        body.pack(fill=BOTH, expand=YES)
        self._build_sidebar(body)
        self._build_main(body)

        self.setup_dnd()
        self.update_engine_ui()
        self.refresh_soundfonts()
        self.on_hotkey_state(self.hotkey.listener is not None)
        self._schedule_prewarm()
        self.show_view('library')
        self._restore_geometry()
        self._bind_shortcuts()

    # ------------------------------------------------------------ 窗口几何
    def _restore_geometry(self):
        raw = (self.app_config.window_geom or '').strip()
        if not raw or 'x' not in raw or '+' not in raw:
            return
        try:
            size_part, pos_part = raw.split('+', 1)
            width, height = (int(value) for value in size_part.split('x'))
            x, y = (int(value) for value in pos_part.split('+'))
        except ValueError:
            return
        if width < 900 or height < 600:
            return
        left, top, right, bottom = screen_workarea(x + width // 2, y + height // 2)
        width = min(width, right - left)
        height = min(height, bottom - top)
        # 至少留 80px 在屏内，避免窗口跑到看不见的地方
        x = max(left, min(x, right - 80))
        y = max(top, min(y, bottom - 80))
        try:
            self.geometry(f'{width}x{height}+{x}+{y}')
        except tk.TclError:
            pass

    def _save_geometry(self):
        try:
            geo = self.winfo_geometry()
        except tk.TclError:
            return
        if 'x' in geo and '+' in geo:
            self.app_config.window_geom = geo
            self.app_config.save()

    # ------------------------------------------------------------ 快捷键
    def _bind_shortcuts(self):
        for sequence, handler in (
            ('<space>', lambda _e: self._shortcut_play()),
            ('<Delete>', lambda _e: self._shortcut_delete()),
            ('<F5>', lambda _e: self.refresh_all()),
            ('<Control-r>', lambda _e: self.refresh_all()),
            ('<Escape>', lambda _e: self._shortcut_stop()),
        ):
            for widget in (self, self.file_list.tree):
                try:
                    widget.bind(sequence, handler)
                except tk.TclError:
                    pass

    def _shortcut_play(self):
        if self._playing:
            self.stop_playback()
        elif self._view == 'outputs' and self.filter_var.get() == 'midi':
            self.play_selected()
        else:
            self.play_current()
        return 'break'

    def _shortcut_stop(self):
        if self._playing:
            self.stop_playback()
        return 'break'

    def _shortcut_delete(self):
        if self._view == 'outputs':
            self.delete_selected()
        return 'break'

    # ------------------------------------------------------------ 左侧导航
    def _build_sidebar(self, parent):
        bar = tb.Frame(parent, padding=(PAD, PAD, 8, PAD))
        bar.pack(side=LEFT, fill=Y)
        bar.configure(width=self.SIDEBAR_W)
        bar.pack_propagate(False)

        mark = tb.Frame(bar)
        mark.pack(fill=X, pady=(0, 20))
        tb.Label(mark, text='♪', font=(FONT_NAME, 26), bootstyle='primary').pack(side=LEFT)
        col = tb.Frame(mark)
        col.pack(side=LEFT, padx=(6, 0))
        tb.Label(col, text='小花音乐助手', font=(FONT_NAME, 12, 'bold')).pack(anchor='w')
        tb.Label(col, text=f'MIDI · v{APP_VERSION}', font=FONT_SMALL,
                 bootstyle='secondary').pack(anchor='w')

        self.nav_buttons = {}
        for key, glyph, label in (('library', '♫', '曲谱库'), ('outputs', '≡', '输出文件'),
                                  ('reader', '▤', 'PDF 讲解'), ('terms', '❖', '术语')):
            btn = tb.Button(bar, text=f'  {glyph}   {label}', bootstyle='secondary-link',
                            command=lambda k=key: self.show_view(k), padding=(10, 10))
            btn.pack(fill=X, pady=2)
            self.nav_buttons[key] = btn

        tb.Separator(bar).pack(fill=X, pady=14)

        tb.Label(bar, text='识别引擎', font=FONT_SMALL, bootstyle='secondary').pack(anchor='w')
        self.engine_chip = Chip(bar, command=self.toggle_engine)
        self.engine_chip.pack(anchor='w', pady=(6, 14))

        tb.Label(bar, text='库概览', font=FONT_SMALL, bootstyle='secondary').pack(anchor='w')
        self.side_stats = tb.Label(bar, text='—', font=(FONT_NAME, 10), justify='left',
                                   wraplength=self.SIDEBAR_W - 30)
        self.side_stats.pack(anchor='w', pady=(4, 0))

        tb.Frame(bar).pack(fill=BOTH, expand=YES)

        # 底部三个入口：用 Label（可控制左对齐），ttk 的按钮会居中 + 窄了会加省略号
        def side_link(text, command):
            widget = tb.Label(bar, text=text, anchor='w', justify='left',
                              font=(FONT_NAME, 10), cursor='hand2',
                              bootstyle='secondary')
            widget.pack(fill=X, pady=1)
            widget.bind('<Button-1>', lambda _e: command())
            widget.bind('<Enter>', lambda _e: widget.configure(bootstyle='primary'))
            widget.bind('<Leave>', lambda _e: widget.configure(bootstyle='secondary'))
            return widget

        self.theme_btn = side_link(self.theme_label(), self.toggle_theme)
        self.mini_btn = side_link('极简模式', self.switch_mode)
        self.menu_btn = side_link('更多设置', self._popup_menu)

    # ------------------------------------------------------------ 主区域
    def _build_main(self, parent):
        main = tb.Frame(parent, padding=(8, PAD, PAD, 0))
        main.pack(side=LEFT, fill=BOTH, expand=YES)

        head = tb.Frame(main)
        head.pack(fill=X)
        titles = tb.Frame(head)
        titles.pack(side=LEFT)
        self.view_title = tb.Label(titles, text='曲谱库', font=FONT_TITLE)
        self.view_title.pack(anchor='w')
        self.view_sub = tb.Label(titles, text='', font=FONT_SMALL, bootstyle='secondary')
        self.view_sub.pack(anchor='w', pady=(2, 0))

        actions = tb.Frame(head)
        actions.pack(side=RIGHT)
        self.capture_btn = tb.Button(actions, text='截取五线谱', bootstyle='primary',
                                     command=self.area_capture, padding=(20, 10))
        self.capture_btn.pack(side=LEFT)
        tb.Button(actions, text='从剪贴板', bootstyle='secondary-outline',
                  command=self.clipboard_add).pack(side=LEFT, padx=8)
        tb.Button(actions, text='刷新', bootstyle='secondary-outline',
                  command=self.refresh_all).pack(side=LEFT)
        tb.Button(actions, text='依赖', bootstyle='secondary-outline',
                  command=self.show_deps).pack(side=LEFT, padx=(8, 0))

        # 讲解面板：pack 在 stack 之前（先占右侧宽度），默认收起
        self.notes_panel = NotesPanel(main, on_close=self.close_notes)

        self.stack = tb.Frame(main)
        self.stack.pack(fill=BOTH, expand=YES, pady=(PAD, GAP))

        # 曲谱库（封面墙）
        self.library_view = tb.Frame(self.stack)
        self.thumbs = ThumbGrid(self.library_view, on_open=self.play_cover,
                                on_menu=self.screenshot_menu)
        self.thumbs.pack(fill=BOTH, expand=YES)

        # 输出文件（播放列表）
        self.outputs_view = tb.Frame(self.stack)
        bar = tb.Frame(self.outputs_view)
        bar.pack(fill=X, pady=(0, GAP))
        self.filter_var = tk.StringVar(value='xml')
        Segmented(bar, FILTERS, self.filter_var, command=self.refresh_files).pack(side=LEFT)
        tb.Button(bar, text='打开文件夹', bootstyle='secondary-link',
                  command=self.open_output_folder).pack(side=RIGHT)

        self.file_list = FileList(self.outputs_view, on_open=self.open_selected,
                                  on_menu=self.file_menu, show_index=True)
        self.file_list.pack(fill=BOTH, expand=YES)
        self.file_list.tree.bind('<<TreeviewSelect>>', lambda _e: self._update_actions())

        # PDF 阅读器
        self.reader_view = tb.Frame(self.stack)
        self.pdf_view = PdfView(self.reader_view, post=self.post,
                                on_analyze=self._analyze_pdf_page,
                                on_page=self._on_pdf_page,
                                on_lookup=self._on_pdf_lookup,
                                on_click=self._on_pdf_click,
                                on_band=self._on_pdf_band,
                                on_bands=self._pdf_bands,
                                on_model=self.show_llm_settings,
                                on_export=self._export_band_midi,
                                on_region=self._on_pdf_region)
        self.pdf_view.pack(fill=BOTH, expand=YES)

        # 「讲解」属于阅读视图：放在这一页自己的工具栏里，切到别的页就不该出现
        self.notes_btn = tb.Button(self.pdf_view.bar, text='讲解',
                                   bootstyle='secondary-outline',
                                   command=self.toggle_notes)
        self.notes_btn.pack(side=RIGHT, padx=(0, 6))

        # 试听音色：homr 常把声部识别成 Voice，默认改用大钢琴
        import midi_timbre
        self._midi_timbre = midi_timbre
        tb.Label(self.pdf_view.bar, text='试听音色', font=FONT_SMALL,
                 bootstyle='secondary').pack(side=LEFT, padx=(12, 4))
        self.timbre_var = tk.StringVar(
            value=midi_timbre.gm_label(getattr(self.app_config, 'preview_program', 0)))
        self.timbre_combo = tb.Combobox(
            self.pdf_view.bar, textvariable=self.timbre_var, width=13, state='readonly',
            values=[midi_timbre.gm_label(index) for index in range(128)])
        self.timbre_combo.pack(side=LEFT)
        self.timbre_combo.bind('<<ComboboxSelected>>', lambda _e: self._on_timbre_change())

        # 高低音谱表是否合并成一行（四部和声默认合并，避免只听到一半声部）
        self.merge_grand_var = tk.BooleanVar(
            value=bool(getattr(self.app_config, 'merge_grand', True)))
        tb.Checkbutton(self.pdf_view.bar, text='高低音一起', variable=self.merge_grand_var,
                       bootstyle='round-toggle',
                       command=self._on_merge_grand_change).pack(side=LEFT, padx=(12, 0))

        self.preview_var = tk.BooleanVar(
            value=bool(getattr(self.app_config, 'show_score_preview', True)))
        tb.Checkbutton(self.pdf_view.bar, text='看识别结果', variable=self.preview_var,
                       bootstyle='round-toggle',
                       command=self._on_preview_toggle).pack(side=LEFT, padx=(10, 0))

        tb.Button(self.pdf_view.bar, text='本曲目录', bootstyle='secondary-outline',
                  command=self._open_book_folder).pack(side=LEFT, padx=(10, 0))

        tb.Label(self.pdf_view.bar, text='符干', bootstyle='secondary').pack(
            side=LEFT, padx=(10, 2))
        self.stem_var = tk.StringVar()
        self.stem_combo = tb.Combobox(
            self.pdf_view.bar, textvariable=self.stem_var, state='readonly', width=8,
            values=['按声部(SATB)', '逐音朝外', '按谱表', '按中线', '一律朝上'])
        self.stem_combo.pack(side=LEFT, padx=2)
        self.stem_combo.bind('<<ComboboxSelected>>', lambda _e: self._on_stem_mode_change())
        self._sync_stem_combo()

        # 术语页：查词 → 分级 → 跳回原书
        self.terms_view = GlossaryView(self.stack, glossary=self._glossary,
                                       data_dir=self._glossary_dir,
                                       on_open_page=self._open_glossary_page,
                                       on_select=self._on_glossary_select)

        # 追问对话挂到右侧面板里
        chat = self.notes_panel.chat_pane
        chat.on_send = self._on_chat_send
        chat.on_clear = self._on_chat_clear

        row = tb.Frame(self.outputs_view)
        row.pack(fill=X, pady=(GAP, 0))
        self.act_open = tb.Button(row, text='打开', bootstyle='secondary-outline',
                                  command=self.open_selected, width=8)
        self.act_open.pack(side=LEFT)
        self.act_play = tb.Button(row, text='播放', bootstyle='primary',
                                  command=self.play_selected, width=8)
        self.act_play.pack(side=LEFT, padx=8)
        self.act_extra = tb.Button(row, text='转为 MIDI', bootstyle='secondary-outline',
                                   command=self.extra_action, width=10)
        self.act_extra.pack(side=LEFT)
        self.act_delete = tb.Button(row, text='删除', bootstyle='danger-outline',
                                    command=self.delete_selected, width=8)
        self.act_delete.pack(side=RIGHT)

    # ------------------------------------------------------------ 播放条
    def _build_transport(self):
        bar = tb.Frame(self, padding=(PAD, 10, PAD, 10))
        bar.pack(fill=X, side='bottom')
        tb.Separator(self).pack(fill=X, side='bottom')

        left = tb.Frame(bar)
        left.pack(side=LEFT)
        # 迷你封面，播放器常见的那种小图
        self.mini_cover = tb.Label(left, text='♪', bootstyle='secondary',
                                   font=(FONT_NAME, 17), width=3, padding=(10, 8),
                                   anchor='center')
        self.mini_cover.pack(side=LEFT, padx=(0, 12))
        self._mini_photo = None

        info = tb.Frame(left)
        info.pack(side=LEFT)
        self.now_label = tb.Label(info, text='未在播放', font=(FONT_NAME, 10, 'bold'),
                                  width=18, anchor='w')
        self.now_label.pack(anchor='w')
        self.now_meta = tb.Label(info, text='双击封面开始', font=FONT_SMALL,
                                 bootstyle='secondary', width=22, anchor='w')
        self.now_meta.pack(anchor='w')

        self.play_btn = tb.Button(left, text='▶', bootstyle='success', width=4,
                                  command=self.play_current, padding=(12, 10))
        self.play_btn.pack(side=LEFT, padx=(14, 0))

        right = tb.Frame(bar)
        right.pack(side=RIGHT)
        tb.Label(right, text='音色', font=FONT_SMALL, bootstyle='secondary').pack(side=LEFT)
        self.sf2_combo = tb.Combobox(right, width=14, state='readonly')
        self.sf2_combo.pack(side=LEFT, padx=(6, 12))
        self.sf2_combo.bind('<<ComboboxSelected>>', self._on_sf2_change)

        tb.Label(right, text='音量', font=FONT_SMALL, bootstyle='secondary').pack(side=LEFT)
        self.volume_label = tb.Label(right, text=f'{int(self.app_config.volume * 100)}%',
                                     font=FONT_SMALL, width=4, bootstyle='secondary')
        self.volume_scale = tb.Scale(right, from_=0, to=2, length=70, bootstyle='primary',
                                     command=self._on_volume)
        self.volume_scale.set(self.app_config.volume)
        self.volume_scale.pack(side=LEFT, padx=(6, 4))
        self.volume_label.pack(side=LEFT, padx=(0, 10))

        tb.Label(right, text='速度', font=FONT_SMALL, bootstyle='secondary').pack(side=LEFT)
        self.bpm_label = tb.Label(right, text=self._bpm_text(), font=FONT_SMALL,
                                  width=7, bootstyle='secondary')
        self.bpm_scale = tb.Scale(right, from_=40, to=240, length=70, bootstyle='primary',
                                  command=self._on_bpm)
        self.bpm_scale.set(self.app_config.bpm or 120)
        self.bpm_scale.pack(side=LEFT, padx=(6, 4))
        self.bpm_label.pack(side=LEFT)

        self.term_combo = tb.Combobox(right, width=15, state='readonly',
                                      values=[label for label, _bpm in TEMPO_TERMS] + [TERM_CUSTOM])
        self.term_combo.pack(side=LEFT, padx=(6, 0))
        self.term_combo.bind('<<ComboboxSelected>>', self._on_term)
        self._sync_term_combo()

        middle = tb.Frame(bar)
        middle.pack(side=LEFT, fill=X, expand=YES, padx=(24, 24))
        self.progress = tb.Progressbar(middle, mode='determinate', maximum=100, value=0,
                                       bootstyle='success')
        self.progress.pack(fill=X, pady=(6, 2))
        times = tb.Frame(middle)
        times.pack(fill=X)
        self.time_now = tb.Label(times, text='0:00', font=FONT_SMALL, bootstyle='secondary')
        self.time_now.pack(side=LEFT)
        self.time_total = tb.Label(times, text='0:00', font=FONT_SMALL, bootstyle='secondary')
        self.time_total.pack(side=RIGHT)

    # ------------------------------------------------------------ 视图切换
    def show_view(self, key):
        self._view = key
        for name, btn in self.nav_buttons.items():
            btn.configure(bootstyle='primary' if name == key else 'secondary-link')
        self.library_view.pack_forget()
        self.outputs_view.pack_forget()
        self.reader_view.pack_forget()
        self.terms_view.pack_forget()
        if key == 'library':
            self.library_view.pack(fill=BOTH, expand=YES)
            self.view_title.configure(text='曲谱库')
            self.refresh_screenshots()
        elif key == 'terms':
            self.terms_view.pack(fill=BOTH, expand=YES)
            self.view_title.configure(text='术语')
            self.view_sub.configure(text='按书并列的术语表：A 原书定义 / B 有定义句 / C 仅用法')
            # 先记下上次位置，再 reload —— reload 会自动选中第一行并覆盖配置
            last = getattr(self.app_config, 'glossary_term', '') or ''
            tier = getattr(self.app_config, 'glossary_tier', '') or ''
            self.terms_view.reload()
            if last:
                self.terms_view.select_term(last, tier or None)
        elif key == 'reader':
            self.reader_view.pack(fill=BOTH, expand=YES)
            self.view_title.configure(text='PDF 讲解')
            self.view_sub.configure(text='双击一行谱试听 · 拖框选一段 · 右键查本页术语 · 「讲解」交给云端')
            self._restore_pdf_session()
        else:
            self.outputs_view.pack(fill=BOTH, expand=YES)
            self.view_title.configure(text='输出文件')
            self.view_sub.configure(text='转换与渲染出来的文件')
            self.refresh_files()

    # ------------------------------------------------------------ PDF 阅读器
    def _restore_pdf_session(self):
        """回到阅读视图时恢复上次的 PDF 和页码。"""
        if self.pdf_view.book is not None:
            return
        path = self.app_config.pdf_path
        if not path or not os.path.isfile(path):
            self.pdf_view.hint.configure(text='打开一本扫描版曲谱 PDF，翻到想读的那一页')
            return
        self.pdf_view.open(path, self.app_config.pdf_page or 1)

    def open_pdf(self):
        self.show_view('reader')
        self.pdf_view.pick_file()

    def _on_pdf_page(self, book, page):
        self.app_config.pdf_path = book.path
        self.app_config.pdf_page = page
        self.schedule_save()
        self.set_status(f'第 {page} / {book.pages} 页 · {os.path.basename(book.path)}')

    def _open_glossary_page(self, path, page):
        """从术语页跳到原书某一页。"""
        self.show_view('reader')
        try:
            self.pdf_view.open(path, page)
            self.set_status(f'已跳到《{os.path.basename(path)[:22]}》第 {page} 页')
        except Exception as exc:
            self.set_status(f'打开失败：{type(exc).__name__}')

    def _terms_on_pdf_page(self, book, page):
        """本页 OCR 文字里出现了哪些术语。"""
        if not self._glossary:
            return []
        try:
            text = book.text(page)
        except Exception:
            return []
        names = []
        for item in self._glossary.terms:
            aliases = [item['term']] + list(item.get('aliases') or [])
            if any(name and name in text for name in aliases):
                names.append(item['term'])
        names.sort(key=len, reverse=True)
        return names

    def _on_pdf_lookup(self, book, page, action, term=None):
        """阅读器右键：查本页术语 / 直接查某个词 / 打开术语页。"""
        if action == 'list':
            return self._terms_on_pdf_page(book, page)
        self.show_view('terms')
        if action == 'lookup' and term:
            self.terms_view.select_term(term)
            self.set_status(f'术语：{term}')
        return []

    def _on_glossary_select(self, term, tier):
        """记住术语页看到哪儿了。"""
        self.app_config.glossary_term = term
        self.app_config.glossary_tier = tier or '全部'
        self.schedule_save()

    STEM_LABELS = {'voices': '按声部(SATB)', 'outward': '逐音朝外',
                   'staff': '按谱表', 'rule': '按中线', 'up': '一律朝上'}

    def _sync_stem_combo(self):
        try:
            label = self.STEM_LABELS.get(
                str(getattr(self.app_config, 'stem_mode', 'voices')), '按声部(SATB)')
            self.stem_var.set(label)
        except Exception:
            pass

    def _on_stem_mode_change(self):
        label = self.stem_var.get() or '按声部(SATB)'
        mode = next((key for key, value in self.STEM_LABELS.items()
                     if value == label), 'voices')
        self.app_config.stem_mode = mode
        self.schedule_save()
        self.set_status(f'符干方向：{label}')
        # 让已缓存的排版图失效，重新生成时才用新模式
        try:
            book = getattr(self.pdf_view, 'book', None)
            if book:
                import glob as _glob
                import score_click
                folder = score_click.book_folder(
                    self._play_cache_dir(), getattr(book, 'title', ''),
                    book.stem, book.path)
                for path in _glob.glob(os.path.join(folder, '*_engraved*.png')):
                    os.remove(path)
        except Exception:
            pass
        # 小窗还开着就立刻用新模式重排一遍
        try:
            ctx = getattr(self, '_preview_ctx', None) or {}
            midi = ctx.get('midi') or ''
            folder = ctx.get('folder') or (os.path.dirname(midi) if midi else '')
            if folder:
                import glob as _glob2
                for path in _glob2.glob(os.path.join(folder, '*_engraved*.png')):
                    try:
                        os.remove(path)
                    except OSError:
                        pass
            if midi and os.path.isfile(midi) and self._preview_window \
                    and self._preview_window.top:
                self._update_score_preview(midi, ctx.get('xml') or '', force=True)
        except Exception:
            pass

    def _open_book_folder(self):
        """打开当前这本书的音频/图片目录。"""
        book = getattr(self.pdf_view, 'book', None)
        if not book:
            self.set_status('先打开一本 PDF')
            return
        try:
            import score_click
            folder = score_click.book_folder(
                self._play_cache_dir(), getattr(book, 'title', ''),
                book.stem, book.path)
            os.startfile(folder)
            self.set_status(f'已打开 {os.path.basename(folder)}')
        except Exception as exc:
            self.set_status(f'打不开目录：{type(exc).__name__}')

    def _on_preview_toggle(self):
        value = bool(self.preview_var.get())
        self.app_config.show_score_preview = value
        self.schedule_save()
        if not value and self._preview_window is not None:
            self._preview_window.hide()
        self.set_status('识别结果小窗：' + ('开' if value else '关'))

    def _update_score_preview(self, midi_path, xml_path=None, force=False):
        """把识别结果画进小窗：有 MuseScore 就排真谱，没有就用内置画法。"""
        if not bool(getattr(self.app_config, 'show_score_preview', True)):
            return
        try:
            import score_preview
            if self._preview_window is None:
                self._preview_window = score_preview.PreviewWindow(
                    self, theme=self.app_config.theme, on_action=self._preview_action)
            self._preview_window.theme = self.app_config.theme
        except Exception as exc:
            self.set_status(f'识别结果预览失败：{type(exc).__name__}')
            return

        if not xml_path:
            guess = os.path.splitext(midi_path)[0] + '.musicxml'
            if os.path.isfile(guess):
                xml_path = guess
        import musescore_cli
        musescore = self.app_config.musescore_path or musescore_cli.find_musescore()
        if musescore and xml_path and os.path.isfile(xml_path):
            target = os.path.splitext(midi_path)[0] + '_engraved.png'
            if force and os.path.isfile(target):
                try:
                    os.remove(target)
                except OSError:
                    pass
            if os.path.isfile(target):
                original = os.path.splitext(midi_path)[0] + '_crop.png'
                if not os.path.isfile(original):
                    original = ''
                label = '上：原谱　下：识别结果'
                try:
                    if self.pdf_view.book:
                        title = getattr(self.pdf_view.book, 'title', '')
                        if title:
                            label = f'{title} · 第 {self.pdf_view.page} 页　' + label
                except Exception:
                    pass
                self._preview_window.show_pair(original, target, label)
                return
            self.set_status('正在用 MuseScore 排版…')
            threading.Thread(target=self._engrave_preview,
                             args=(musescore, xml_path, target, midi_path),
                             daemon=True).start()
            return

        self._preview_window.show(midi_path, theme=self.app_config.theme)

    def _preview_action(self, action):
        """小窗按钮：移调 / 换引擎重试 / 外挂 MuseScore / 重新载入。"""
        ctx = getattr(self, '_preview_ctx', None)
        if action in ('open_musescore', 'reload'):
            if action == 'open_musescore':
                self._open_in_musescore(ctx)
            else:
                self._reload_from_musescore(ctx)
            return
        if not ctx or not ctx.get('midi') or not os.path.isfile(ctx['midi']):
            self.set_status('还没有可修正的识别结果')
            return
        if action == 'retry_engine':
            self._retry_engine(ctx)
            return
        semitones = {'octave_up': 12, 'octave_down': -12,
                     'sharp': 1, 'flat': -1}.get(action)
        if not semitones:
            return
        if getattr(self, '_click_busy', False):
            self.set_status('正在处理，稍等…')
            return
        self._click_busy = True
        self._preview_window.set_status(f'正在移调 {semitones:+d} 半音…')
        threading.Thread(target=self._transpose_worker,
                         args=(ctx, semitones), daemon=True).start()

    def _transpose_files(self, xml_path, midi_path, semitones):
        """把 XML 和 MIDI 一起移调（原地覆盖）。"""
        if xml_path and os.path.isfile(xml_path):
            from music21 import converter, interval
            score = converter.parse(xml_path)
            moved = score.transpose(interval.ChromaticInterval(semitones))
            moved.write('musicxml', fp=xml_path)
            from score_to_midi import musicxml_to_midi
            if not musicxml_to_midi(xml_path, midi_path) or not os.path.isfile(midi_path):
                raise RuntimeError('移调后转 MIDI 失败')
        else:
            self._shift_midi(midi_path, semitones)
        import midi_timbre
        midi_timbre.force_program(midi_path, int(getattr(self.app_config, 'preview_program', 0)))

    def _open_in_musescore(self, ctx):
        """把这一段 MusicXML 交给 MuseScore 编辑，窗口摆到我们旁边。"""
        ctx = ctx or {}
        xml_path = ctx.get('xml') or ''
        if not xml_path or not os.path.isfile(xml_path):
            self._preview_window.set_status('找不到这一段的 MusicXML')
            return
        try:
            import musescore_cli
            import score_editor
            exe = self.app_config.musescore_path or musescore_cli.find_musescore()
            if not exe:
                self._preview_window.set_status('没有 MuseScore')
                return
            rect = {'x': self.winfo_rootx(), 'y': self.winfo_rooty(),
                    'w': self.winfo_width(), 'h': self.winfo_height()}
            process, hwnd = score_editor.open_file(exe, xml_path, rect)
            self._editor_process = process
            self._editor_hwnd = hwnd
            if hwnd:
                self._preview_window.set_status(
                    '已打开 MuseScore，改完点「重新载入」')
            else:
                self._preview_window.set_status('MuseScore 已启动，但没找到窗口')
            self._preview_window.set_notice('')
            self._editor_xml = xml_path
            self._editor_mtime = self._xml_mtime(xml_path)
            self._start_editor_watch()
        except Exception as exc:
            self._preview_window.set_status(f'打开失败：{type(exc).__name__}: {exc}')

    def _xml_mtime(self, path):
        try:
            return os.path.getmtime(path)
        except OSError:
            return 0.0

    def _start_editor_watch(self):
        """每 2 秒看一眼 MusicXML 有没有被 MuseScore 保存过。"""
        self._stop_editor_watch()
        self._editor_job = self.after(2000, self._watch_editor_file)

    def _stop_editor_watch(self):
        job = getattr(self, '_editor_job', None)
        if job:
            try:
                self.after_cancel(job)
            except Exception:
                pass
            self._editor_job = None

    def _watch_editor_file(self):
        self._editor_job = None
        path = getattr(self, '_editor_xml', '')
        window = self._preview_window
        if not path or not window or not window.top:
            return
        try:
            if not window.top.winfo_exists():
                return
        except Exception:
            return
        hwnd = getattr(self, '_editor_hwnd', 0)
        if hwnd:
            try:
                import score_editor
                if not score_editor.is_alive(hwnd):
                    self._editor_hwnd = 0
                    return          # MuseScore 关了就不再轮询
            except Exception:
                pass
        stamp = self._xml_mtime(path)
        if stamp and stamp > getattr(self, '_editor_mtime', 0) + 1e-6:
            self._editor_mtime = stamp
            try:
                window.set_notice('MuseScore 已保存改动 —— 点「重新载入」生效')
            except Exception:
                pass
        self._editor_job = self.after(2000, self._watch_editor_file)

    def _reload_from_musescore(self, ctx):
        """重新读回 MuseScore 保存过的 MusicXML，并刷新音频与排版。"""
        ctx = ctx or {}
        xml_path = ctx.get('xml') or ''
        midi_path = ctx.get('midi') or ''
        if not xml_path or not os.path.isfile(xml_path):
            self._preview_window.set_status('找不到这一段的 MusicXML')
            return
        if getattr(self, '_click_busy', False):
            self._preview_window.set_status('正在处理，稍等…')
            return
        self._click_busy = True
        self._preview_window.set_status('正在重新载入…')
        threading.Thread(target=self._reload_worker,
                         args=(xml_path, midi_path, ctx), daemon=True).start()

    def _reload_worker(self, xml_path, midi_path, ctx):
        error = None
        try:
            # 手工编辑版单独存一份，缓存重识别时用它
            edited = os.path.splitext(midi_path)[0] + '_edited.musicxml'
            try:
                import shutil
                shutil.copyfile(xml_path, edited)
                folder = (ctx or {}).get('folder') or os.path.dirname(midi_path)
                key = (ctx or {}).get('key') or os.path.splitext(
                    os.path.basename(midi_path))[0]
                import corrections
                corrections.remember(folder, key, edited=True)
            except Exception:
                edited = ''
            from score_to_midi import musicxml_to_midi
            if not musicxml_to_midi(xml_path, midi_path) or not os.path.isfile(midi_path):
                raise RuntimeError('MusicXML 转 MIDI 失败')
            import midi_timbre
            midi_timbre.force_program(midi_path, int(getattr(self.app_config, 'preview_program', 0)))
            target = os.path.splitext(midi_path)[0] + '_engraved.png'
            if os.path.isfile(target):
                os.remove(target)
        except Exception as exc:
            error = f'{type(exc).__name__}: {exc}'
        self.post(self._reload_done, error, midi_path, xml_path)

    def _reload_done(self, error, midi_path, xml_path):
        self._click_busy = False
        if error:
            self._preview_window.set_status(f'重新载入失败：{error}')
            return
        self._preview_ctx['xml'] = xml_path
        try:
            self._preview_window.set_notice('')
        except Exception:
            pass
        self._editor_mtime = self._xml_mtime(xml_path)
        self._update_score_preview(midi_path, xml_path)
        try:
            self.play_midi(midi_path)
        except Exception:
            pass
        self.set_status('已从 MuseScore 重新载入')

    def _transpose_worker(self, ctx, semitones):
        midi_path = ctx['midi']
        xml_path = ctx.get('xml') or ''
        error = None
        try:
            self._transpose_files(xml_path, midi_path, semitones)
            total = int(ctx.get('transpose') or 0) + semitones
            ctx['transpose'] = total
            folder = ctx.get('folder') or ''
            key = ctx.get('key') or ''
            if folder and key:
                import corrections
                corrections.remember(folder, key, transpose=total)
        except Exception as exc:
            error = f'{type(exc).__name__}: {exc}'
        self.post(self._preview_action_done, error, f'已移调 {semitones:+d} 半音')

    def _shift_midi(self, midi_path, semitones):
        """没有 MusicXML 时，直接改 MIDI 音高。"""
        import mido
        midi = mido.MidiFile(midi_path)
        for track in midi.tracks:
            for message in track:
                if message.type in ('note_on', 'note_off'):
                    message.note = max(0, min(127, message.note + semitones))
        midi.save(midi_path)

    def _preview_action_done(self, error, message):
        self._click_busy = False
        if error:
            self.set_status(f'修正失败：{error}')
            try:
                self._preview_window.set_status(f'失败：{error}')
            except Exception:
                pass
            return
        ctx = getattr(self, '_preview_ctx', {}) or {}
        midi_path = ctx.get('midi')
        if midi_path and os.path.isfile(midi_path):
            # 排版图要从新的 MusicXML 重新生成
            target = os.path.splitext(midi_path)[0] + '_engraved.png'
            try:
                if os.path.isfile(target):
                    os.remove(target)
            except OSError:
                pass
            try:
                self._update_score_preview(midi_path, ctx.get('xml') or '')
            except Exception:
                pass
            try:
                self.play_midi(midi_path)
            except Exception:
                pass
        self.set_status(message)

    def _retry_engine(self, ctx):
        """用另一个引擎重新识别同一张裁图。"""
        crop = ctx.get('crop')
        if not crop or not os.path.isfile(crop):
            self.set_status('找不到这一段的裁图，重新点一次吧')
            return
        if getattr(self, '_click_busy', False):
            self.set_status('正在识别，稍等…')
            return
        other = 'audiveris' if ctx.get('engine') == 'homr' else 'homr'
        self._click_busy = True
        self._preview_window.set_status(f'正在用 {other} 重新识别…')
        threading.Thread(target=self._retry_worker, args=(ctx, crop, other),
                         daemon=True).start()

    def _retry_worker(self, ctx, crop, engine):
        error = None
        xml_path = None
        try:
            from omr_recognizer import recognize
            xml_path = recognize(crop, engine=engine)
            if not xml_path or not os.path.isfile(xml_path):
                raise RuntimeError(f'{engine} 没有输出')
            midi_path = ctx['midi']
            try:
                import score_preview
                score_preview.save_musicxml(
                    xml_path, os.path.splitext(midi_path)[0] + '.musicxml')
            except Exception:
                pass
            from score_to_midi import musicxml_to_midi
            if not musicxml_to_midi(xml_path, midi_path) or not os.path.isfile(midi_path):
                raise RuntimeError('转 MIDI 失败')
            import midi_timbre
            midi_timbre.force_program(midi_path, int(getattr(self.app_config, 'preview_program', 0)))
        except Exception as exc:
            error = f'{type(exc).__name__}: {exc}'
        self.post(self._retry_done, error, xml_path, engine)

    def _retry_done(self, error, xml_path, engine):
        self._click_busy = False
        if error:
            self.set_status(f'{engine} 重试失败：{error}')
            try:
                self._preview_window.set_status(f'{engine} 重试失败：{error}')
            except Exception:
                pass
            return
        ctx = getattr(self, '_preview_ctx', {}) or {}
        ctx['engine'] = engine
        ctx['xml'] = xml_path
        ctx['transpose'] = 0
        try:
            import corrections
            corrections.remember(ctx.get('folder') or '', ctx.get('key') or '',
                                 engine=engine, transpose=0)
        except Exception:
            pass
        try:
            import score_preview
            score_preview.save_musicxml(
                xml_path, os.path.splitext(ctx['midi'])[0] + '.musicxml')
        except Exception:
            pass
        target = os.path.splitext(ctx['midi'])[0] + '_engraved.png'
        try:
            if os.path.isfile(target):
                os.remove(target)
        except OSError:
            pass
        self._update_score_preview(ctx['midi'], xml_path)
        try:
            self.play_midi(ctx['midi'])
        except Exception:
            pass
        self.set_status(f'已用 {engine} 重新识别')

    def _engrave_preview(self, musescore, xml_path, target, midi_path):
        try:
            import musescore_cli
            produced = musescore_cli.render(
                xml_path, target, musescore=musescore,
                stem_mode=str(getattr(self.app_config, 'stem_mode', 'outward')))
            error = None if produced else 'MuseScore 没有输出图片'
            target = produced or target
        except Exception as exc:
            error = f'{type(exc).__name__}: {exc}'
        self.post(self._engrave_preview_done, error, target, midi_path)

    def _engrave_preview_done(self, error, target, midi_path):
        if error or not os.path.isfile(target):
            # 排版失败就退回内置画法，不要让小窗空着
            try:
                self._preview_window.show(midi_path, theme=self.app_config.theme)
            except Exception:
                pass
            self.set_status(f'MuseScore 排版失败，已改用内置画法（{error or "无输出"}）')
            return
        original = ''
        try:
            candidate = os.path.splitext(midi_path)[0] + '_crop.png'
            if os.path.isfile(candidate):
                original = candidate
        except Exception:
            pass
        label = '上：原谱　下：识别结果'
        try:
            if self.pdf_view.book:
                title = getattr(self.pdf_view.book, 'title', '')
                if title:
                    label = f'{title} · 第 {self.pdf_view.page} 页　' + label
        except Exception:
            pass
        self._preview_window.show_pair(original, target, label)
        self.set_status('识别结果已用 MuseScore 排版')

    def _on_merge_grand_change(self):
        value = bool(self.merge_grand_var.get())
        self.app_config.merge_grand = value
        self._band_cache.clear()          # 分法变了，缓存作废
        self.schedule_save()
        self.set_status('高低音谱表：' + ('合并成一行播放' if value else '各自单独播放'))
        try:
            if self.pdf_view.book:
                self.pdf_view._hover_box = None
                self.pdf_view._draw_box(None)
                self.pdf_view.update_hover()
        except Exception:
            pass

    def _on_timbre_change(self):
        label = self.timbre_var.get() or ''
        try:
            program = int(label.split(' ')[0])
        except (ValueError, IndexError):
            return
        self.app_config.preview_program = program
        self.schedule_save()
        self.set_status(f'试听音色：{label}')

    # ------------------------------------------------------------ 点谱出声
    def _play_cache_dir(self):
        """试听缓存放在数据目录下（data/play_cache）。"""
        return self._glossary_dir or os.path.dirname(LLM_FILE)

    def _pdf_bands(self, book, page):
        """本页所有谱行（按页缓存，悬停/扩展播放范围都用它）。"""
        try:
            import score_click
        except Exception:
            return []
        merge = bool(getattr(self.app_config, 'merge_grand', True))
        version = getattr(score_click, 'DETECT_VERSION', 0)
        key = (book.path, page, merge, version)
        bands = self._band_cache.get(key)
        if bands is None:
            try:
                bands = score_click.systems(book.render(page), merge_grand=merge)
            except Exception:
                bands = []
            self._band_cache[key] = bands
            while len(self._band_cache) > 12:
                self._band_cache.pop(next(iter(self._band_cache)))
        return bands

    def _on_pdf_band(self, book, page, x, y):
        """鼠标在哪一行上（悬停高亮用）。"""
        bands = self._pdf_bands(book, page)
        if not bands:
            return None
        for top, bottom in bands:
            if top <= y <= bottom:
                return (top, bottom)
        return min(bands, key=lambda band: abs((band[0] + band[1]) / 2 - y))

    def _on_pdf_click(self, book, page, x, y):
        """双击谱面：认出点中的那一行，然后播放。"""
        band = self._on_pdf_band(book, page, x, y)
        width = book.render(page).width
        box = (0, band[0], width, band[1]) if band else None
        self._start_preview(book, page, box, whole_row=True)

    def _on_pdf_region(self, book, page, box):
        """拖框选段：横向按用户框的，纵向对齐到整行。

        如果框跨了多行（旋律答案常占两行谱），就把覆盖到的那几行一起保留，
        不要塌回中间那一行。
        """
        x1, y1, x2, y2 = box
        bands = self._pdf_bands(book, page)
        covered = [(top, bottom) for top, bottom in bands
                   if bottom > y1 + 2 and top < y2 - 2]
        if covered:
            box = (x1, min(top for top, _ in covered), x2,
                   max(bottom for _, bottom in covered))
        else:
            band = self._on_pdf_band(book, page, (x1 + x2) / 2, (y1 + y2) / 2)
            if band:
                box = (x1, band[0], x2, band[1])
        self._start_preview(book, page, box, whole_row=False)

    def _segment_record(self, book, page, box):
        """查这一小节的修正记录（引擎、移调）。"""
        try:
            import score_click
            import corrections
            folder = score_click.book_folder(
                self._play_cache_dir(), getattr(book, 'title', ''),
                book.stem, book.path)
            if not box:
                return {}, folder
            key = score_click.cache_name(
                book.stem, page, box[1],
                box[0] if box[0] else None, box[2] if box[2] else None)
            key = os.path.splitext(key)[0]
            return corrections.get(folder, key), folder
        except Exception:
            return {}, ''

    def _engine_missing_hint(self):
        """识别引擎没装时给一句人话，而不是抛一堆异常。"""
        engine = str(getattr(self.app_config, 'engine', 'homr') or 'homr')
        if engine != 'homr':
            return ''
        try:
            import homr  # noqa: F401
            return ''
        except Exception:
            pass
        return ('还没装 homr（谱面识别引擎）。点右上角「依赖」按提示装好再来；'
                '官方地址：https://github.com/liebharc/homr')

    def _export_band_midi(self, book, page, box):
        """右键导出：确认位置 → 起名 → 复制 MIDI + 写位置说明。"""
        from tkinter import filedialog, messagebox
        if not book or not box:
            return
        try:
            import midi_export, score_click
        except Exception as exc:
            self.set_status('导出不可用：%s' % exc)
            return

        cache_root = None
        midi_path = None
        used_box = box
        try:
            image = book.render(page)
            crop, used_box = score_click.crop_region(image, box)
            cache_root = score_click.book_folder(
                self._play_cache_dir(), getattr(book, 'title', ''),
                book.stem, book.path)
            midi_path = score_click.cache_path(cache_root, book.stem, page,
                                               used_box[1], used_box[0], used_box[2])
        except Exception as exc:
            self.set_status('导出准备失败：%s' % exc)
            return

        printed = ''
        try:
            printed = book.book_page(page) or ''
        except Exception:
            printed = ''

        default_name = midi_export.suggest_name(
            getattr(book, 'title', '') or os.path.splitext(os.path.basename(book.path))[0],
            page, used_box, printed)
        target = filedialog.asksaveasfilename(
            parent=self, title='把这一段的 MIDI 存到哪',
            defaultextension='.mid', initialfile=default_name,
            filetypes=[('MIDI', '*.mid'), ('所有文件', '*.*')])
        if not target:
            return

        if not os.path.isfile(midi_path):
            # 还没识别过：先跑一遍识别，再复制
            if getattr(self, '_click_busy', False):
                self.set_status('上一段还在识别，稍等一下…')
                return
            hint = self._engine_missing_hint()
            if hint:
                self.set_status(hint)
                return
            self._click_busy = True
            self.set_status('还没识别过这一段，先识别再导出…')

            def worker():
                error = None
                try:
                    crop2, used2 = score_click.crop_region(book.render(page), box)
                    crop_png = midi_path[:-4] + '_crop.png'
                    try:
                        crop2.save(crop_png)
                    except Exception:
                        crop_png = ''
                    if not os.path.isfile(midi_path):
                        png = midi_path[:-4] + '.png'
                        crop2.save(png)
                        from omr_recognizer import recognize
                        xml = recognize(png, engine=str(getattr(self.app_config, 'engine', 'homr')))
                        if not xml or not os.path.isfile(xml):
                            raise RuntimeError('这一段没认出音符')
                        from score_to_midi import musicxml_to_midi
                        if not musicxml_to_midi(xml, midi_path) or not os.path.isfile(midi_path):
                            raise RuntimeError('转 MIDI 失败')
                except Exception as exc:
                    error = '%s: %s' % (type(exc).__name__, exc)
                self.post(self._export_done, midi_path, target, book, page,
                          printed, used_box, error)

            threading.Thread(target=worker, daemon=True).start()
            return

        self._export_done(midi_path, target, book, page, printed, used_box, None)

    def _export_done(self, midi_path, target, book, page, printed, box, error):
        self._click_busy = False
        if error or not midi_path or not os.path.isfile(midi_path):
            self.set_status('导出失败：%s' % (error or '没有 MIDI'))
            return
        try:
            import midi_export
            crop_png = midi_path[:-4] + '_crop.png'
            note = midi_export.export(
                midi_path, target,
                book_title=getattr(book, 'title', '') or os.path.basename(book.path),
                page=page, printed_page=printed, box=box, crop_png=crop_png,
                extra={'engine': getattr(self.app_config, 'engine', '')})
            self.set_status('已导出：%s' % os.path.basename(target))
            if note and os.path.isfile(note):
                self.pdf_view.hint.configure(text='已导出 %s（同名 .txt 记录位置）'
                                             % os.path.basename(target))
        except Exception as exc:
            self.set_status('导出失败：%s' % exc)

    def _start_preview(self, book, page, box, whole_row=True):
        hint = self._engine_missing_hint()
        if hint:
            self.set_status(hint)
            try:
                self.pdf_view.hint.configure(text=hint)
            except Exception:
                pass
            return
        if getattr(self, '_click_busy', False):
            self.set_status('上一段还在识别，稍等一下…')
            return
        self._click_busy = True
        what = '这一行' if whole_row else '选中的这一段'
        try:
            self.pdf_view.hint.configure(text=f'正在识别第 {page} 页{what}…')
        except Exception:
            pass
        threading.Thread(target=self._preview_worker,
                         args=(book, page, box, whole_row), daemon=True).start()

    def _preview_worker(self, book, page, box, whole_row):
        midi_path = None
        error = None
        used_box = box
        xml_path = None
        try:
            import score_click
            image = book.render(page)
            if box:
                crop, used_box = score_click.crop_region(image, box)
            else:
                crop, used_box = score_click.crop_band(
                    image, image.height // 2,
                    merge_grand=bool(getattr(self.app_config, 'merge_grand', True)))
            cache_root = score_click.book_folder(
                self._play_cache_dir(), getattr(book, 'title', ''),
                book.stem, book.path)
            if whole_row:
                midi_path = score_click.cache_path(cache_root, book.stem, page,
                                                   used_box[1])
            else:
                midi_path = score_click.cache_path(cache_root, book.stem, page,
                                                   used_box[1], used_box[0], used_box[2])
            crop_png = midi_path[:-4] + '_crop.png'
            try:
                crop.save(crop_png)
            except Exception:
                crop_png = ''
            if not os.path.isfile(midi_path):
                record, _folder = self._segment_record(book, page, used_box)
                edited = midi_path[:-4] + '_edited.musicxml'
                if record.get('edited') and os.path.isfile(edited):
                    xml = edited          # 用你手工改过的版本
                else:
                    png = midi_path[:-4] + '.png'
                    crop.save(png)
                    from omr_recognizer import recognize
                    engine = record.get('engine') or self.app_config.engine
                    xml = recognize(png, engine=engine)
                if not xml or not os.path.isfile(xml):
                    raise RuntimeError('这一段没认出音符')
                xml_path = xml
                try:
                    import score_preview
                    score_preview.save_musicxml(
                        xml, os.path.splitext(midi_path)[0] + '.musicxml')
                except Exception:
                    pass
                from score_to_midi import musicxml_to_midi
                if not musicxml_to_midi(xml, midi_path) or not os.path.isfile(midi_path):
                    raise RuntimeError('转 MIDI 失败')
                offset = int(record.get('transpose') or 0)
                if offset:
                    self._transpose_files(xml, midi_path, offset)
        except Exception as exc:
            error = f'{type(exc).__name__}: {exc}'
            midi_path = None
        self.post(self._on_click_done, midi_path, used_box, error, xml_path)

    def _on_click_done(self, midi_path, band, error, xml_path=None):
        self._click_busy = False
        self._band_cache = {}
        try:
            if not self.pdf_view.book:
                return
            self.pdf_view.hint.configure(
                text=f'{os.path.basename(self.pdf_view.book.path)}  ·  '
                     f'第 {self.pdf_view.page} / {self.pdf_view.book.pages} 页')
        except Exception:
            pass
        if error or not midi_path:
            self.set_status(f'没认出来（{error or "未知原因"}）——换个位置再点一下')
            return
        rows = ''
        if band:
            rows = f'（y {band[0]}–{band[1]}）'
        if not self.current_sf2():
            self.set_status(f'这一行识别好了{rows}，但还没有音色库，无法出声——'
                            '去「更多设置」选一个 .sf2/.sf3')
            return
        # 按当前选的试听音色覆盖（homr 常写成 Voice，听起来不是钢琴）
        try:
            self._midi_timbre.force_program(
                midi_path, getattr(self.app_config, 'preview_program', 0))
        except Exception:
            pass
        if not xml_path:
            guess = os.path.splitext(midi_path)[0] + '.musicxml'
            if os.path.isfile(guess):
                xml_path = guess
        stem = os.path.splitext(os.path.basename(midi_path))[0]
        folder = os.path.dirname(midi_path)
        record = {}
        try:
            import corrections
            record = corrections.get(folder, stem)
        except Exception:
            pass
        self._preview_ctx = {'midi': midi_path, 'xml': xml_path or '',
                             'crop': os.path.splitext(midi_path)[0] + '_crop.png',
                             'engine': record.get('engine')
                             or str(getattr(self.app_config, 'engine', 'homr')),
                             'transpose': int(record.get('transpose') or 0),
                             'folder': folder, 'key': stem}
        self._update_score_preview(midi_path, xml_path)
        self.set_status(f'播放点中的这一行{rows}')
        self.play_midi(midi_path)

    def _analyze_pdf_page(self, book, page):
        """在工作线程里跑：OCR → 组包 → 云端模型。结果回到主线程显示。"""
        self.post(self._ensure_notes_visible)
        try:
            kind = book.detect_kind()
            terms = []
            if self._glossary:
                try:
                    terms = self._glossary.terms_on_page(book.text(page))
                except Exception:
                    terms = []
            package = book.context_for_page(page, kind=kind, glossary_terms=terms)
        except Exception as exc:
            self.post(self._show_pdf_text, f'第 {page} 页处理失败', f'{type(exc).__name__}: {exc}')
            return

        config = explain.LlmConfig.load(LLM_FILE)
        if not config.usable():
            created = explain.ensure_config_template(LLM_FILE)
            missing = '、'.join(config.missing()) or '配置'
            self.post(self._show_pdf_text, f'第 {page} 页 · 还没配置云端模型',
                      '## 需要先填配置\n\n'
                      f'文件：`{LLM_FILE}`' + ('（已为你创建模板）' if created else '') + '\n\n'
                      f'缺：**{missing}**\n\n'
                      '```json\n'
                      '{\n'
                      '  "base_url": "https://open.bigmodel.cn/api/paas/v4",\n'
                      '  "model": "glm-4.5v",\n'
                      '  "api_key": "填你的 key"\n'
                      '}\n'
                      '```\n\n'
                      '必须是支持图片输入的视觉模型。填完不用重启，直接再点一次「分析本页」。\n\n'
                      '本页已识别到的题目：'
                      + ('、'.join(item["label"] for item in package['items']) or '（无）'))
            return

        self.post(self._show_pdf_text, f'第 {page} 页 · 正在分析…', '正在调用云端模型，请稍等。')
        try:
            result = explain.explain_page(
                package, os.path.basename(book.path), config,
                cache_dir=os.path.join(book.cache, 'explain'), kind=kind)
        except Exception as exc:
            self.post(self._show_pdf_text, f'第 {page} 页 · 调用失败',
                      f'```\n{type(exc).__name__}: {exc}\n```\n\n'
                      '检查 base_url / model / api_key，以及这个模型是否支持图片输入。')
            return

        mode = {'exercise': '习题', 'textbook': '教材', 'score': '谱例'}.get(package.get('kind', ''), '')
        subtitle = f'第 {page} 页 · {config.llm_model}' + (f' · {mode}模式' if mode else '')
        if result.get('cached'):
            subtitle += ' · 缓存'
        elif result.get('elapsed'):
            subtitle += f' · {result["elapsed"]}s'
        self.post(self._after_analysis, book, page, package, result.get('text') or '',
                  subtitle)

    def _ensure_notes_visible(self):
        if not self._notes_visible:
            self.open_notes()

    def _show_pdf_text(self, subtitle, text):
        self._ensure_notes_visible()
        self.notes_panel.show_text(title=subtitle, text=text, subtitle=subtitle)
        self._explain_active = True

    # ------------------------------------------------------------ 追问对话
    def _chat_path(self, book, page):
        return os.path.join(book.cache, 'chat', f'chat_p{page:03d}.json')

    def _ensure_chat(self, book, page, package=None):
        """拿到这一页的对话会话：内存里有就复用，否则从磁盘读回。"""
        title = os.path.basename(book.path)
        current = getattr(self, '_chat', None)
        if current is not None and current.package['page'] == page \
                and current.book_title == title:
            return current
        package = package or book.context_for_page(page)
        session = explain.ChatSession.load(self._chat_path(book, page), package, title)
        if not session.analysis_text:
            cached = explain.cache_file(os.path.join(book.cache, 'explain'), page)
            if os.path.isfile(cached):
                with open(cached, encoding='utf-8') as fp:
                    session.analysis_text = fp.read()
        self._chat = session
        self._refresh_chat_view(session)
        return session

    def _refresh_chat_view(self, session):
        pane = self.notes_panel.chat_pane
        has_analysis = bool(session.analysis_text)
        prefix = f'第 {session.package["page"]} 页 · '
        prefix += '已读完讲解，可以就这一页提问' if has_analysis else '先点「分析本页」再提问'
        pane.load_history(session.messages, analysis_prefix=prefix)

    def _after_analysis(self, book, page, package, text, subtitle):
        """整页讲解完成：存下分析文本，并把对话队列准备好。"""
        self._ensure_notes_visible()
        self.notes_panel.show_text(title=subtitle, text=text, subtitle=subtitle)
        session = explain.ChatSession.load(self._chat_path(book, page), package,
                                           os.path.basename(book.path),
                                           glossary=self._glossary)
        session.analysis_text = text
        session.save()
        self._chat = session
        self._refresh_chat_view(session)

    def _on_chat_send(self, question, include_images, allow_web=False):
        pane = self.notes_panel.chat_pane
        book = getattr(self.pdf_view, 'book', None)
        if book is None:
            pane.add_system('先打开一本 PDF，并分析某一页')
            pane.set_busy(False)
            return
        page = self.pdf_view.page
        config = explain.LlmConfig.load(LLM_FILE)
        if not config.usable():
            pane.add_system('还没配置云端模型：先填好 ' + LLM_FILE)
            pane.set_busy(False)
            return
        try:
            session = self._ensure_chat(book, page)
        except Exception as exc:
            pane.add_system(f'这一页还没准备好：{exc}')
            pane.set_busy(False)
            return
        if not session.analysis_text:
            pane.add_system('这一页还没分析过，先点「分析本页」')
            pane.set_busy(False)
            return

        def worker():
            try:
                if allow_web:
                    pane.add_system('本地资料不足，正在联网检索…')
                text, usage, elapsed = session.ask(question, config,
                                                   include_images=include_images,
                                                   allow_web=allow_web)
            except Exception as exc:
                self.post(self._on_chat_error, f'{type(exc).__name__}: {exc}')
                return
            self.post(self._on_chat_reply, text, elapsed, include_images, allow_web)

        threading.Thread(target=worker, daemon=True).start()
        self.set_status('正在等模型回答…')

    def _on_chat_reply(self, text, elapsed, include_images, allow_web=False):
        pane = self.notes_panel.chat_pane
        if text:
            pane.add_bot(text)
        else:
            pane.add_system('模型没有返回内容，可以再问一次')
        flags = ('（带图）' if include_images else '') + ('（已联网）' if allow_web else '')
        pane.set_busy(False, message=f'上次回答 {elapsed}s' + flags)
        self.set_status(f'回答完成 · {elapsed}s')

    def _on_chat_error(self, message):
        pane = self.notes_panel.chat_pane
        pane.add_system('出错了：' + message)
        pane.set_busy(False)
        self.set_status('提问失败')

    def _on_chat_clear(self):
        session = getattr(self, '_chat', None)
        if session is not None:
            session.clear()
        self.set_status('已清空这一页的对话')

    # ------------------------------------------------------------ 数据刷新
    def show_deps(self):
        """依赖检查：homr / MuseScore / 音色库不随包分发，引导到官方页面。"""
        try:
            import install_deps
            rows = install_deps.collect()
        except Exception as exc:
            self.set_status('依赖检查失败：%s: %s' % (type(exc).__name__, exc))
            return
        try:
            import dialogs
            dialogs.show_deps_dialog(self, rows)
        except Exception as exc:
            self.set_status('打不开依赖窗口：%s: %s' % (type(exc).__name__, exc))

    def show_llm_settings(self):
        """让用户自己填模型接口（任何 OpenAI 兼容服务都行）。"""
        try:
            import dialogs
            dialogs.show_llm_dialog(self, LLM_FILE, on_saved=self._on_llm_saved)
        except Exception as exc:
            self.set_status('打不开模型设置：%s: %s' % (type(exc).__name__, exc))

    def _on_llm_saved(self, payload):
        model = payload.get('model') or '（未填模型）'
        self.set_status('已保存模型配置：' + model)

    def refresh_screenshots(self):
        items = [os.path.join(SCREENSHOT_DIR, name) for name, _s, _t in
                 _list_dir(SCREENSHOT_DIR, IMAGE_EXTS)]
        self.thumbs.set_files(items)
        if self._view == 'library':
            self.view_sub.configure(
                text=f'{len(items)} 张截图 · 双击封面识别并播放' if items
                else '还没有截图 · 点右上角「截取五线谱」开始')
        self._update_stats()
        if not items:
            self.set_status('就绪 · 曲谱库是空的')

    def _update_stats(self):
        try:
            counts = (len(_list_dir(SCREENSHOT_DIR, IMAGE_EXTS)),
                      len(_list_dir(XML_DIR, XML_EXTS)),
                      len(_list_dir(MIDI_DIR, ('.mid', '.midi'))))
        except Exception:
            return
        if hasattr(self, 'side_stats'):
            self.side_stats.configure(
                text=f'{counts[0]} 张曲谱\n{counts[1]} 个 XML\n{counts[2]} 首 MIDI')

    def refresh_files(self):
        kind = self.filter_var.get()
        directory, exts, hint = {
            'xml': (XML_DIR, XML_EXTS, '还没有 MusicXML'),
            'midi': (MIDI_DIR, ('.mid', '.midi'), '还没有 MIDI'),
            'sheet': (SHEET_DIR, IMAGE_EXTS, '还没有乐谱图'),
        }[kind]
        rows = _list_dir(directory, exts)
        self.file_list.set_items(
            [{'iid': name, 'name': name, 'size': human_size(size), 'time': _fmt_time(t)}
             for name, size, t in rows], hint)
        self._update_actions()

    def _update_actions(self):
        kind = self.filter_var.get()
        has = self.file_list.selected() is not None
        self.act_open.configure(state='normal' if has else 'disabled',
                                text='打开' if kind != 'midi' else '定位')
        self.act_play.configure(state='normal' if (has and kind in ('midi', 'xml')) else 'disabled')
        self.act_extra.configure(state='normal' if (has and kind == 'xml') else 'disabled')

    def selected_path(self):
        name = self.file_list.selected()
        if not name:
            return None
        kind = self.filter_var.get()
        directory = {'xml': XML_DIR, 'midi': MIDI_DIR, 'sheet': SHEET_DIR}[kind]
        path = os.path.join(directory, name)
        return path if os.path.isfile(path) else None

    def open_output_folder(self):
        self.open_folder({'xml': XML_DIR, 'midi': MIDI_DIR, 'sheet': SHEET_DIR}[
            self.filter_var.get()])

    # ------------------------------------------------------------ 播放
    def play_cover(self, path):
        """双击封面 / 右键「识别并播放」：识别完一定要播，不受 auto_play 影响。"""
        if self._busy:
            self.set_status('上一次识别还没结束，请稍候…')
            return
        self._play_after_process = True
        self.set_status(f'正在识别：{os.path.basename(path)}')
        self.process_image(path)

    def play_current(self):
        if self._playing:
            self.stop_playback()
            return
        midi = self._now_playing
        if midi and os.path.isfile(midi):
            self.play_midi(midi)
            return
        if self._view == 'outputs' and self.filter_var.get() == 'midi':
            self.play_selected()
            return
        self.set_status('先从输出文件里选一首，或双击封面让它去识别')

    def play_midi(self, midi_path):
        sf2 = self.current_sf2()
        if not sf2:
            return
        # 先把上一次播放停掉并等它退出，避免两个线程同时驱动合成器
        try:
            self.stop_playback()
        except Exception:
            pass
        worker = getattr(self, '_play_worker', None)
        if worker is not None and worker.is_alive():
            try:
                worker.join(timeout=1.0)
            except Exception:
                pass
        speed = self.playback_speed(midi_path)
        duration = pipeline.midi_duration(midi_path, speed)
        name = os.path.basename(midi_path)
        self._now_playing = midi_path
        self._stop_requested = False
        sf2_name = os.path.basename(sf2) if sf2 else ''
        base_bpm = pipeline.midi_bpm(midi_path)
        meta = f'{fmt_mmss(duration)} · {int(self.app_config.bpm or base_bpm)} BPM · {sf2_name}'
        self.set_now_playing(name, meta, cover=self._cover_for_midi(midi_path))
        self.set_busy(f'正在播放：{name}')
        self._load_notes_for(midi_path)
        self.set_status(f'正在加载音色库…（就绪后开始播放 {fmt_mmss(duration)}）')

        volume = self.app_config.volume
        self._stop_event = threading.Event()

        def done(ok=True):
            self.post(self._on_play_done, ok)

        self._pending_duration = duration

        def ready():
            self.post(self._on_play_ready)

        self._play_worker = pipeline.start_play_thread(
            midi_path, sf2, volume, speed, on_done=done,
            stop_event=self._stop_event, on_ready=ready)

    def stop_playback(self):
        requested = super().stop_playback()
        if requested:
            self._stop_requested = True
        return requested

    def _on_play_done(self, ok=True):
        self._stop_progress()
        if self._stop_requested:
            self._stop_requested = False
            self.set_idle('已停止播放')
            return
        if ok:
            self.set_idle('播放结束')
        else:
            self._on_play_finished(False)

    def _schedule_prewarm(self):
        """启动 1.5 秒后把音色库加载好，避免第一次点谱干等 3 秒多。"""
        try:
            self.after(1500, self._prewarm_synth)
        except Exception:
            pass

    def _prewarm_synth(self):
        sf2 = ''
        try:
            sf2 = self.current_sf2() or ''
        except Exception:
            sf2 = ''
        if not sf2:
            return
        import threading

        def work():
            try:
                import pipeline
                if pipeline.preload_soundfont(sf2):
                    self.post(self._on_prewarm_done, True)
            except Exception:
                pass

        threading.Thread(target=work, daemon=True).start()

    def _on_prewarm_done(self, ok):
        if ok:
            self.set_status('音色库已就绪')

    def _on_play_ready(self):
        """音色库加载完，真正开始出声时才启动进度条。"""
        if getattr(self, '_stop_requested', False):
            return
        duration = getattr(self, '_pending_duration', 0) or 0
        self._start_progress(duration)
        self.set_busy('正在播放')

    def _start_progress(self, duration):
        self._playing = True
        self._play_duration = max(duration, 0.5)
        self._play_started = time.time()
        self.play_btn.configure(text='⏸')
        self.progress.configure(value=0, maximum=100)
        self.time_total.configure(text=fmt_mmss(self._play_duration))
        self._tick_progress()

    def _tick_progress(self):
        if not self._playing:
            return
        elapsed = time.time() - self._play_started
        pct = min(100.0, elapsed / self._play_duration * 100.0)
        try:
            self.progress.configure(value=pct)
            self.time_now.configure(text=fmt_mmss(elapsed))
        except tk.TclError:
            return
        self._sync_notes_position(elapsed)
        if elapsed < self._play_duration + 1.5:
            self._progress_job = self.after(200, self._tick_progress)
        else:
            self._stop_progress()

    def _stop_progress(self):
        self._playing = False
        if self._progress_job is not None:
            try:
                self.after_cancel(self._progress_job)
            except Exception:
                pass
            self._progress_job = None
        try:
            self.play_btn.configure(text='▶')
            self.progress.configure(value=0)
            self.time_now.configure(text='0:00')
        except tk.TclError:
            pass

    # ------------------------------------------------------------ 讲解面板（L1）
    def toggle_notes(self):
        if self._notes_visible:
            self.close_notes()
        else:
            self.open_notes()

    def open_notes(self):
        if not self._notes_visible:
            # 必须 pack 在 stack 之前，否则 stack 的 expand 会先吃掉全部空间
            self.notes_panel.pack(side=RIGHT, fill=Y, padx=(0, PAD), pady=(PAD, GAP),
                                  before=self.stack)
            self._notes_visible = True
        try:
            self.notes_btn.configure(bootstyle='primary-outline')
        except tk.TclError:
            pass
        if not self._brief:
            self._load_notes_for(self._now_playing, force=True)
        if not self._brief:
            self.notes_panel.clear('还没有可分析的曲子：先播放一首')

    def close_notes(self):
        if self._notes_visible:
            self.notes_panel.pack_forget()
            self._notes_visible = False
        try:
            self.notes_btn.configure(bootstyle='secondary-outline')
        except tk.TclError:
            pass

    def _load_notes_for(self, midi_path, force=False):
        """按 MIDI 找到同源 XML，分析（带缓存）后喂给面板。

        如果面板正在显示「整页讲解」，播放时的自动调用会把讲解冲掉，
        所以非强制调用直接返回，等用户主动点「讲解」再切换。
        """
        if self._explain_active and not force:
            return
        if force:
            self._explain_active = False
        self._brief = None
        if not midi_path:
            self.notes_panel.clear()
            return
        xml_path = pipeline.xml_for_midi(midi_path)
        if not xml_path:
            self.notes_panel.clear('这首曲子还没有对应的 MusicXML，无法分析')
            return
        try:
            brief = analysis.load_brief(xml_path, BRIEF_DIR)
        except Exception as exc:
            self.notes_panel.clear(f'分析失败：{exc}')
            return
        self._brief = brief
        self.notes_panel.set_brief(brief)

    def _sync_notes_position(self, elapsed):
        """把播放进度换算到「乐谱时间」再定位小节。

        分析里的小节时间是按谱面自身速度算的，播放可能被 BPM 滑块改过速，
        所以用「播放比例 × 谱面总时长」来对齐，避免两边速度不一致时错位。
        """
        if not self._brief:
            return
        total = self._brief.get('duration') or 0.0
        if total <= 0:
            return
        fraction = elapsed / max(self._play_duration, 0.1)
        score_time = min(total, max(0.0, fraction * total))
        self.notes_panel.set_current(analysis.measure_at(self._brief, score_time))

    def set_now_playing(self, title, meta='', cover=None):
        for widget, text in ((self.now_label, title), (self.now_meta, meta)):
            try:
                widget.configure(text=text)
            except tk.TclError:
                pass
        photo = rounded_thumbnail(cover, (46, 46), 10) if cover else None
        self._mini_photo = photo
        try:
            if photo is not None:
                self.mini_cover.configure(image=photo, text='')
            else:
                self.mini_cover.configure(image='', text='♪', bootstyle='secondary',
                                          font=(FONT_NAME, 18))
        except tk.TclError:
            pass

    def _cover_for_midi(self, midi_path):
        # 输出名带引擎后缀（cap_x_homr.mid），封面还是 cap_x.png，所以要剥掉后缀
        stem = pipeline.base_stem(midi_path)
        for ext in IMAGE_EXTS:
            candidate = os.path.join(SCREENSHOT_DIR, stem + ext)
            if os.path.isfile(candidate):
                return candidate
        return None

    # ------------------------------------------------------------ 设置项回调
    def on_hotkey_state(self, ok):
        if not hasattr(self, 'status'):
            return
        hint = (f'快捷键 {describe(self.app_config.hotkey)}' if ok
                else '全局热键不可用（可在更多设置里改）')
        self.status.set(self.status.text.cget('text'), hint)

    def on_theme_changed(self):
        super().on_theme_changed()
        try:
            self.notes_panel.apply_theme()
        except Exception:
            pass

    def _on_volume(self, _value):
        self.app_config.volume = round(float(self.volume_scale.get()), 2)
        self.volume_label.configure(text=f'{int(self.app_config.volume * 100)}%')
        self.schedule_save()

    def _bpm_text(self):
        return f'{int(self.app_config.bpm or 120)} BPM'

    def _sync_term_combo(self):
        """把下拉框同步成当前 BPM 对应的术语；对不上就显示「自定义」。"""
        combo = getattr(self, 'term_combo', None)   # 构造期 scale.set() 会先触发回调
        if combo is None:
            return
        bpm = int(self.app_config.bpm or 120)
        label = TEMPO_BPM_TO_LABEL.get(bpm, TERM_CUSTOM)
        if combo.get() != label:
            combo.set(label)

    def _on_bpm(self, value=None):
        if value is None:
            value = self.bpm_scale.get()
        self.app_config.bpm = int(round(float(value)))
        self.bpm_label.configure(text=self._bpm_text())
        self._sync_term_combo()
        self.schedule_save()

    def _on_term(self, _event=None):
        label = self.term_combo.get()
        bpm = TEMPO_LABEL_TO_BPM.get(label)
        if not bpm:
            return
        self.app_config.bpm = bpm
        self.bpm_scale.set(bpm)          # 会让刻度也跳过去，并触发 _on_bpm
        self.bpm_label.configure(text=self._bpm_text())
        self.schedule_save()
        self.set_status(f'速度术语：{label} → {bpm} BPM')

    def _on_sf2_change(self, _event=None):
        name = self.sf2_combo.get()
        if name:
            self.app_config.sf2_name = name
            self.schedule_save()
            self.set_status(f'音色库：{name}')

    def refresh_soundfonts(self):
        paths = list_soundfonts(self.app_config)
        names = [os.path.basename(p) for p in paths]
        self.sf2_combo.configure(values=names or ['(没有音色库)'])
        # 用 find_sf2_path 决定「当前是哪个」，保证下拉框显示的和真正加载的一致
        chosen = find_sf2_path(self.app_config) if paths else ''
        current = os.path.basename(chosen) if chosen else ''
        self.sf2_combo.set(current or '(没有音色库)')
        if current:
            self.app_config.sf2_name = current

    def update_engine_ui(self):
        engine = self.app_config.engine
        self.engine_chip.set_state(ENGINE_LABEL.get(engine, engine), engine_available(engine))

    # ------------------------------------------------------------ 菜单
    def _popup_menu(self):
        colors = tb.Style().colors
        menu = tk.Menu(self, tearoff=False, bd=0,
                       bg=colors.bg, fg=colors.fg,
                       activebackground=colors.primary, activeforeground=colors.selectfg)
        auto_play = tk.BooleanVar(value=self.app_config.auto_play)
        auto_render = tk.BooleanVar(value=self.app_config.auto_render)

        def toggle_auto_play():
            self.app_config.auto_play = bool(auto_play.get())
            self.app_config.save()

        def toggle_auto_render():
            self.app_config.auto_render = bool(auto_render.get())
            self.app_config.save()

        menu.add_checkbutton(label='截图后自动识别并播放', variable=auto_play,
                             command=toggle_auto_play)
        menu.add_checkbutton(label='生成后自动渲染乐谱图', variable=auto_render,
                             command=toggle_auto_render)
        menu.add_separator()
        menu.add_command(label='修改截图快捷键', command=self.change_hotkey)
        menu.add_command(label='选择音色库文件夹', command=self.choose_sf2_folder)
        menu.add_command(label='打开音色库文件夹', command=self.open_soundfont_folder)
        menu.add_command(label='重新扫描音色库', command=self.rescan_soundfonts)
        menu.add_command(label='设置 MuseScore 路径', command=self.set_musescore_path)
        menu.add_separator()
        menu.add_command(label='打开预处理图文件夹',
                         command=lambda: self.open_folder(PREPROCESSED_DIR))
        menu.add_command(label='打开识别中间产物文件夹',
                         command=lambda: self.open_folder(HOMR_WORK_DIR))
        menu.add_separator()
        menu.add_command(label='切换亮/暗主题', command=self.toggle_theme)
        menu.add_command(label='切到极简模式', command=self.switch_mode)
        menu.add_separator()
        menu.add_command(label='关于', command=self.show_about)
        menu.add_command(label='更新说明', command=self.show_notes)
        x = self.menu_btn.winfo_rootx()
        y = self.menu_btn.winfo_rooty() + self.menu_btn.winfo_height() + 4
        try:
            menu.tk_popup(x, y)
        finally:
            menu.grab_release()

    # ------------------------------------------------------------ 文件动作
    def open_selected(self):
        path = self.selected_path()
        if not path:
            return
        if self.filter_var.get() == 'midi':
            self.open_output_folder()
        else:
            os.startfile(path)  # noqa: S606

    def play_selected(self):
        path = self.selected_path()
        if not path:
            return
        if self.filter_var.get() == 'midi':
            self.play_midi(path)
            return
        self.set_busy('正在转换 MIDI…')

        def work():
            midi, error = pipeline.convert_xml(path)
            self.post(self._on_convert_done, midi, error)

        threading.Thread(target=work, daemon=True).start()

    def _on_convert_done(self, midi, error):
        if error:
            self.set_idle(error)
            return
        self.set_idle(f'已转换：{os.path.basename(midi)}')
        self.refresh_files()
        self.play_midi(midi)

    def extra_action(self):
        path = self.selected_path()
        if not path:
            return
        self.set_busy('正在转换 MIDI…')

        def work():
            midi, error = pipeline.convert_xml(path)
            self.post(self._on_convert_done, midi, error)

        threading.Thread(target=work, daemon=True).start()

    def delete_selected(self):
        path = self.selected_path()
        if not path:
            return
        if not messagebox.askyesno('确认删除', f'删除 {os.path.basename(path)}？', parent=self):
            return
        try:
            os.remove(path)
        except OSError as exc:
            messagebox.showerror('删除失败', str(exc), parent=self)
            return
        self.set_status(f'已删除 {os.path.basename(path)}')
        self.refresh_files()

    def clipboard_add(self):
        try:
            from PIL import ImageGrab
        except Exception:
            messagebox.showerror('不可用', '缺少 Pillow，无法读取剪贴板。', parent=self)
            return
        img = ImageGrab.grabclipboard()
        if img is None:
            messagebox.showinfo(
                '剪贴板里没有图片',
                '先用系统截图（Win+Shift+S）截到剪贴板，或者直接用「截取五线谱」。', parent=self)
            return
        if isinstance(img, list):
            messagebox.showinfo('剪贴板是文件', '剪贴板里是文件列表，请用拖拽导入。', parent=self)
            return
        stamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        path = os.path.join(SCREENSHOT_DIR, f'clip_{stamp}.png')
        img.save(path)
        self.show_view('library')
        self.refresh_screenshots()
        self.set_status(f'已从剪贴板导入：{os.path.basename(path)}')

    # ------------------------------------------------------------ 右键菜单
    def screenshot_menu(self, event, path):
        menu = tk.Menu(self, tearoff=False)
        menu.add_command(label='识别并播放', command=lambda: self.play_cover(path))
        menu.add_command(label='打开图片', command=lambda: os.startfile(path))  # noqa: S606
        menu.add_separator()
        menu.add_command(label='删除', command=lambda: self._delete_screenshot(path))
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _delete_screenshot(self, path):
        if not messagebox.askyesno('确认删除', f'删除 {os.path.basename(path)}？', parent=self):
            return
        try:
            os.remove(path)
        except OSError as exc:
            messagebox.showerror('删除失败', str(exc), parent=self)
            return
        self.refresh_screenshots()

    def file_menu(self, event):
        path = self.selected_path()
        if not path:
            return
        kind = self.filter_var.get()
        menu = tk.Menu(self, tearoff=False)
        if kind == 'xml':
            menu.add_command(label='打开文件', command=self.open_selected)
            menu.add_command(label='播放（转换后播放）', command=self.play_selected)
            menu.add_command(label='转为 MIDI', command=self.extra_action)
            menu.add_command(label='渲染为乐谱图', command=lambda: self.render_sheet(path))
        elif kind == 'midi':
            menu.add_command(label='播放', command=self.play_selected)
            menu.add_command(label='打开所在文件夹', command=self.open_output_folder)
        else:
            menu.add_command(label='打开图片', command=self.open_selected)
        menu.add_separator()
        menu.add_command(label='删除', command=self.delete_selected)
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def open_folder(self, directory):
        try:
            os.startfile(directory)  # noqa: S606
        except Exception as exc:
            messagebox.showerror('打开失败', str(exc), parent=self)

    # ------------------------------------------------------------ 弹窗
    def show_about(self):
        base_window._text_dialog(self, '关于', ABOUT_TEXT, width=62)

    def show_notes(self):
        base_window._text_dialog(self, '更新说明', UPDATE_NOTES, width=64)


