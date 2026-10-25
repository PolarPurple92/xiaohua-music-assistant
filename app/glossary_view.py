# -*- coding: utf-8 -*-
"""术语页：应用内查词，按可信度分级，可跳回原书那一页。

分级：
  A 原书定义 —— 逐字引用过、核对过页面
  B 有定义句 —— 书里能找到「X 是 / 指 / 称为…」这类句子
  C 仅用法   —— 书里只提到过，没有定义，只能当线索
"""
import io
import json
import os
import re
import threading
import tkinter as tk

import ttkbootstrap as tb

try:
    from ui_kit import FONT_NAME, FONT_SMALL, PAD, GAP
except Exception:                                   # 测试环境兜底
    FONT_NAME, FONT_SMALL, PAD, GAP = 'Microsoft YaHei UI', 'Microsoft YaHei UI', 12, 8

DEF_PAT = re.compile(r'(是|指|称为|所谓|叫做|即)')
TIERS = [('全部', None), ('A 原书定义', 'A'), ('B 有定义句', 'B'), ('C 仅用法', 'C')]
TIER_LABEL = {'A': 'A', 'B': 'B', 'C': 'C'}


def _load_books(data_dir):
    try:
        with io.open(os.path.join(data_dir, 'books.json'), encoding='utf-8') as fp:
            items = json.load(fp).get('books', [])
    except Exception:
        return {}
    out = {}
    for book in items:
        path = book.get('path') or ''
        if path:
            out[book.get('name') or ''] = path
    return out


def term_tier(item, book_defs, evidence):
    """判断一个术语的可信等级。"""
    if item.get('original') or item.get('original_extra'):
        return 'A'
    names = [item['term']] + list(item.get('aliases') or [])
    for book, payload in (book_defs.get(item['term']) or {}).items():
        if payload.get('blacklisted'):
            continue
        for quote in payload.get('quotes') or []:
            if DEF_PAT.search(quote) and any(name[:2] in quote for name in names):
                return 'B'
    return 'C'


class GlossaryView(tb.Frame):
    def __init__(self, parent, glossary=None, data_dir='', on_open_page=None,
                 on_select=None):
        super().__init__(parent)
        self.glossary = glossary
        self.data_dir = data_dir
        self.on_open_page = on_open_page
        self.on_select = on_select
        self.books = _load_books(data_dir) if data_dir else {}
        self._rows = []          # [(term, tier, item)]
        self._current = None     # 当前显示的 term
        self._target = None      # (book_path, pdf_page)
        self._build()
        self.reload()

    # ------------------------------------------------------------ 构建
    def _build(self):
        bar = tb.Frame(self)
        bar.pack(fill=tk.X, pady=(0, GAP))

        tb.Label(bar, text='查找', font=FONT_SMALL, bootstyle='secondary').pack(side=tk.LEFT)
        self.search_var = tk.StringVar()
        entry = tb.Entry(bar, textvariable=self.search_var, width=22)
        entry.pack(side=tk.LEFT, padx=(6, 12))
        entry.bind('<KeyRelease>', lambda _e: self.refresh_list())
        entry.bind('<Return>', lambda _e: self.refresh_list())
        self.search_entry = entry

        self.tier_var = tk.StringVar(value=TIERS[0][0])
        combo = tb.Combobox(bar, textvariable=self.tier_var, width=12, state='readonly',
                            values=[name for name, _ in TIERS])
        combo.pack(side=tk.LEFT)
        combo.bind('<<ComboboxSelected>>', lambda _e: self.refresh_list())
        self.tier_combo = combo

        self.period_var = tk.StringVar(value='全部时期')
        self.period_combo = tb.Combobox(
            bar, textvariable=self.period_var, width=10, state='readonly',
            values=['全部时期', '中世纪', '文艺复兴', '巴洛克', '前古典', '古典',
                    '浪漫', '20世纪', '中国传统', '通用'])
        self.period_combo.pack(side=tk.LEFT, padx=(6, 0))
        self.period_combo.bind('<<ComboboxSelected>>', lambda _e: self.refresh_list())

        self.domain_var = tk.StringVar(value='全部语境')
        self.domain_combo = tb.Combobox(
            bar, textvariable=self.domain_var, width=10, state='readonly',
            values=['全部语境', '曲式', '和声', '复调', '配器', '爵士', '中国音乐',
                    '综合', '其他'])
        self.domain_combo.pack(side=tk.LEFT, padx=(6, 0))
        self.domain_combo.bind('<<ComboboxSelected>>', lambda _e: self.refresh_list())

        self.add_btn = tb.Button(bar, text='＋ 添加术语', bootstyle='primary',
                                 command=self.add_term)
        self.add_btn.pack(side=tk.RIGHT, padx=(8, 0))
        self.pick_btn = tb.Button(bar, text='书库路径…', bootstyle='secondary-outline',
                                  command=self.manage_book_paths)
        self.pick_btn.pack(side=tk.RIGHT, padx=(8, 0))
        self.auto_btn = tb.Button(bar, text='整理 books', bootstyle='secondary-outline',
                                  command=self.auto_organize_default)
        self.auto_btn.pack(side=tk.RIGHT, padx=(8, 0))
        self.count_label = tb.Label(bar, text='', font=FONT_SMALL, bootstyle='secondary')
        self.count_label.pack(side=tk.RIGHT)

        body = tb.Frame(self)
        body.pack(fill=tk.BOTH, expand=True)

        left = tb.Frame(body)
        left.pack(side=tk.LEFT, fill=tk.Y)
        self.listbox = tk.Listbox(left, width=24, activestyle='none', exportselection=False,
                                  relief='flat', borderwidth=0, highlightthickness=0,
                                  font=(FONT_NAME, 10))
        scroll = tb.Scrollbar(left, command=self.listbox.yview)
        self.listbox.configure(yscrollcommand=scroll.set)
        self.listbox.pack(side=tk.LEFT, fill=tk.Y)
        scroll.pack(side=tk.LEFT, fill=tk.Y)
        self.listbox.bind('<<ListboxSelect>>', lambda _e: self.show_selected())

        right = tb.Frame(body)
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(12, 0))
        self.text = tk.Text(right, wrap='word', relief='flat', borderwidth=0,
                            padx=14, pady=10, font=(FONT_NAME, 10))
        vscroll = tb.Scrollbar(right, command=self.text.yview)
        self.text.configure(yscrollcommand=vscroll.set)
        vscroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.text.tag_configure('title', font=(FONT_NAME, 15, 'bold'), spacing3=4)
        self.text.tag_configure('badge_a', foreground='#1e7d32', font=(FONT_NAME, 9, 'bold'))
        self.text.tag_configure('badge_b', foreground='#1a5fb4', font=(FONT_NAME, 9, 'bold'))
        self.text.tag_configure('badge_c', foreground='#b8860b', font=(FONT_NAME, 9, 'bold'))
        self.text.tag_configure('book', font=(FONT_NAME, 10, 'bold'), foreground='#1a5fb4',
                                spacing1=10)
        self.text.tag_configure('orig', foreground='#1e7d32')
        self.text.tag_configure('quote', foreground='#666666', font=(FONT_NAME, 9))
        self.text.tag_configure('meta', foreground='#888888', font=(FONT_NAME, 9))
        self.text.tag_configure('body', spacing1=2)
        self.text.tag_configure('weak', foreground='#b8860b', font=(FONT_NAME, 9))
        self.text.tag_configure('domain', foreground='#7a4f9a', font=(FONT_NAME, 10, 'bold'),
                                spacing1=8, spacing3=2)
        self.text.tag_configure('related', foreground='#1a5fb4', underline=True,
                                font=(FONT_NAME, 9))
        self.text.configure(state='disabled')

        bottom = tb.Frame(self)
        bottom.pack(fill=tk.X, pady=(GAP, 0))
        self.open_btn = tb.Button(bottom, text='跳到原书这一页', bootstyle='primary-outline',
                                  command=self._open_page, state='disabled')
        self.open_btn.pack(side=tk.RIGHT)
        self.hint_label = tb.Label(bottom, text='', font=FONT_SMALL, bootstyle='secondary')
        self.hint_label.pack(side=tk.LEFT)

    # ------------------------------------------------------------ 数据
    def _books_dir(self):
        """发布包里的默认收书目录。"""
        return os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), 'books')

    def _pick_books_folder(self):
        from tkinter import filedialog
        kwargs = {'parent': self, 'title': '选一个装着 PDF 的文件夹'}
        default = self._books_dir()
        if os.path.isdir(default):
            kwargs['initialdir'] = default
        return filedialog.askdirectory(**kwargs)

    def manage_book_paths(self):
        """打开书库路径管理：可以添加/删除文件夹，再开始整理。"""
        try:
            import book_paths_dialog
        except Exception as exc:
            self.count_label.configure(text='打不开路径管理：%s' % exc)
            return
        book_paths_dialog.open_manager(self, on_run=self._run_organize_folders)

    def auto_organize_default(self):
        """整理已经配置的所有书库路径；一个 PDF 都没有就提示去管理路径。"""
        from tkinter import messagebox
        try:
            import auto_terms, book_paths
        except Exception as exc:
            self.count_label.configure(text='打不开自动整理：%s' % exc)
            return
        folders = [path for path in book_paths.existing()
                   if auto_terms.find_pdfs(path)]
        if not folders:
            if messagebox.askyesno(
                    '没有找到 PDF',
                    '默认目录 books 里没有 PDF。\n要打开「书库路径」添加别的文件夹吗？',
                    parent=self):
                self.manage_book_paths()
            return
        self._run_organize_folders(folders)

    def _run_organize_folders(self, folders):
        from tkinter import messagebox
        try:
            import auto_terms
            from settings import LLM_FILE
        except Exception as exc:
            self.count_label.configure(text='打不开自动整理：%s' % exc)
            return
        pdfs = []
        for folder in folders:
            pdfs.extend(auto_terms.find_pdfs(folder))
        if not pdfs:
            messagebox.showinfo('没有 PDF', '这些目录里没有找到 PDF。', parent=self)
            return
        started = messagebox.askokcancel(
            '从书里整理术语',
            '%d 个目录，共 %d 个 PDF。\n\n'
            '流程：逐页本地 OCR（不联网）→ 把文字交给模型提炼术语。\n'
            '书多时会比较久，可以关掉窗口中断。\n\n继续吗？' % (len(folders), len(pdfs)),
            parent=self)
        if not started:
            return

        def progress(message):
            self.after(0, lambda: self.count_label.configure(text=str(message)[:46]))

        def worker():
            try:
                total_added = total_skipped = 0
                for folder in folders:
                    result = auto_terms.run(folder, max_pages=80,
                                             config_path=LLM_FILE, progress=progress)
                    total_added += result.get('added', 0)
                    total_skipped += result.get('skipped', 0)
                message = '整理完成：新增 %d 个术语（跳过 %d 个已有的）' % (
                    total_added, total_skipped)
            except Exception as exc:
                message = '整理失败：%s' % str(exc)[:70]

            def finish():
                self.count_label.configure(text=message)
                self._reload_glossary()
            self.after(0, finish)

        threading.Thread(target=worker, daemon=True).start()

    def add_term(self):
        """打开术语编辑器；保存后重新读一遍术语表。"""
        try:
            import term_editor
            from settings import LLM_FILE
        except Exception as exc:
            self.count_label.configure(text='打不开编辑器：%s' % exc)
            return
        term_editor.open_editor(self, self.data_dir, config_path=LLM_FILE,
                                on_saved=self._reload_glossary)

    def _reload_glossary(self):
        try:
            import glossary as glossary_module
            self.glossary = glossary_module.Glossary(self.data_dir)
        except Exception:
            pass
        self.reload()

    def reload(self):
        if not self.glossary:
            self._rows = []
        else:
            rows = []
            for item in self.glossary.terms:
                tier = term_tier(item, self.glossary.book_defs, self.glossary.evidence)
                rows.append((item['term'], tier, item))
            order = {'A': 0, 'B': 1, 'C': 2}
            rows.sort(key=lambda row: (order[row[1]], row[0]))
            self._rows = rows
        self.refresh_list()

    def refresh_list(self):
        keyword = (self.search_var.get() or '').strip()
        wanted = dict(TIERS).get(self.tier_var.get())
        period = (self.period_var.get() or '全部时期').strip()
        domain = (self.domain_var.get() or '全部语境').strip()
        shown = []
        for term, tier, item in self._rows:
            if wanted and tier != wanted:
                continue
            if period != '全部时期' and (item.get('period') or '通用') != period:
                continue
            if domain != '全部语境':
                books = self.glossary.book_defs.get(term) or {} if self.glossary else {}
                domains = {self._domain_of(book) for book in books}
                if domain not in domains:
                    continue
            if keyword:
                names = [term] + list(item.get('aliases') or [])
                if not any(keyword.lower() in name.lower() for name in names):
                    continue
            shown.append((term, tier, item))

        self.listbox.delete(0, tk.END)
        for term, tier, _item in shown:
            self.listbox.insert(tk.END, f'{TIER_LABEL[tier]}  {term}')
        self.count_label.configure(text=f'{len(shown)} / {len(self._rows)} 个术语')

        if shown:
            self.listbox.selection_set(0)
            self.show_selected()
        else:
            self._render_empty(keyword)

    # ------------------------------------------------------------ 渲染
    def _render_empty(self, keyword=''):
        self.text.configure(state='normal')
        self.text.delete('1.0', tk.END)
        if not self._rows:
            msg = '术语表没有加载。检查 data/glossary_seed.json 是否存在。'
        elif keyword:
            msg = f'没有匹配「{keyword}」的术语。'
        else:
            msg = '这个分级下没有术语。'
        self.text.insert(tk.END, msg, 'meta')
        self.text.configure(state='disabled')
        self._current = None
        self._target = None
        self.open_btn.configure(state='disabled')
        self.hint_label.configure(text='')

    def show_selected(self):
        selection = self.listbox.curselection()
        if not selection:
            return
        label = self.listbox.get(selection[0])
        term = label.split('  ', 1)[-1]
        item = next((row[2] for row in self._rows if row[2]['term'] == term), None)
        if not item:
            return
        self._current = term
        self._render(term, item)
        if self.on_select:
            try:
                self.on_select(term, self.tier_var.get())
            except Exception:
                pass

    def _render(self, term, item):
        tier = term_tier(item, self.glossary.book_defs, self.glossary.evidence)
        text = self.text
        text.configure(state='normal')
        text.delete('1.0', tk.END)

        badge = {'A': 'A 原书定义', 'B': 'B 有定义句', 'C': 'C 仅用法'}[tier]
        text.insert(tk.END, term, 'title')
        text.insert(tk.END, f'    {badge}\n', f'badge_{tier.lower()}')

        category = item.get('category') or ''
        period = item.get('period') or ''
        if period == '通用':
            period = ''
        aliases = '、'.join(item.get('aliases') or [])
        meta = ' · '.join(part for part in (
            category,
            f'时期：{period}' if period else '',
            f'别名：{aliases}' if aliases else '') if part)
        if meta:
            text.insert(tk.END, meta + '\n', 'meta')

        related = [name for name in (item.get('related') or []) if name]
        if related:
            text.insert(tk.END, '相关：', 'meta')
            for index, name in enumerate(related):
                tag = f'rel_{index}'
                text.insert(tk.END, name, ('related', tag))
                text.tag_bind(tag, '<Button-1>',
                              lambda _event, term_name=name: self.select_term(term_name))
                if index != len(related) - 1:
                    text.insert(tk.END, '、', 'meta')
            text.insert(tk.END, '\n', 'meta')

        if item.get('dispute'):
            text.insert(tk.END, '\n⚠ 各教材口径不同：' + item['dispute'] + '\n', 'weak')

        self._target = None
        original = item.get('original')
        if original:
            text.insert(tk.END, f"\n★ 原书定义《{original['book']}》p{original.get('book_page')}\n", 'book')
            text.insert(tk.END, f"「{original['text']}」\n", 'orig')
            if original.get('types'):
                text.insert(tk.END, f"分类：{original['types']}\n", 'quote')
            path = self._book_path(original['book'])
            if path and original.get('pdf_page'):
                self._target = (path, int(original['pdf_page']))

        for extra in (item.get('original_extra') or []):
            text.insert(tk.END, f"\n★ 原书定义《{extra['book']}》p{extra.get('book_page')}\n", 'book')
            text.insert(tk.END, f"「{extra['text']}」\n", 'orig')

        general = item.get('general_definition')
        if general:
            text.insert(tk.END, '\n※ 通用说法（书上没有定义句）\n', 'book')
            text.insert(tk.END, general.get('text', '') + '\n', 'body')
            if general.get('caveat'):
                text.insert(tk.END, general['caveat'] + '\n', 'quote')

        web = item.get('web_reference')
        if web:
            text.insert(tk.END, '\n※ 网络参考（不是书上的原文）\n', 'book')
            text.insert(tk.END, web.get('text', '') + '\n', 'body')
            if web.get('source'):
                text.insert(tk.END, web['source'] + '\n', 'quote')

        books = self.glossary.book_defs.get(term) or {}
        skip_book = (original or {}).get('book')
        rows = []
        for book, payload in books.items():
            definition = payload.get('definition') or ''
            if not definition.strip():
                continue
            # 已经引用过原书定义的那本书不再重复显示（内容一样）
            if skip_book and book == skip_book:
                continue
            rows.append((book, payload))

        # 按语境分组：同一术语在不同体系里可能不是一回事
        groups = {}
        for book, payload in rows:
            groups.setdefault(self._domain_of(book), []).append((book, payload))
        order = ['曲式', '和声', '复调', '爵士', '配器', '综合', '其他']
        ordered = [name for name in order if name in groups]
        ordered += [name for name in groups if name not in ordered]
        multi = len(ordered) > 1

        for domain in ordered:
            if multi:
                text.insert(tk.END, f'\n── {domain}语境 ──\n', 'domain')
            for book, payload in groups[domain]:
                definition = payload.get('definition') or ''
                pages = '、'.join(f"p{page}" for page in (payload.get('pages') or []))
                text.insert(tk.END, f'\n· 《{book}》{pages}\n', 'book')
                if payload.get('blacklisted') or payload.get('note_only'):
                    text.insert(tk.END, definition + '\n', 'weak')
                    continue
                text.insert(tk.END, definition + '\n', 'body')
                for point in (payload.get('points') or [])[:2]:
                    text.insert(tk.END, f'   - {point}\n', 'quote')

        text.configure(state='disabled')
        if self._target:
            name, page = self._target
            self.open_btn.configure(state='normal')
            self.hint_label.configure(text=f'可跳转到《{os.path.basename(name)[:24]}》第 {page} 页')
        else:
            self.open_btn.configure(state='disabled')
            self.hint_label.configure(text='这个术语没有可直接跳转的原书页码')

    def _domain_of(self, book_name):
        """这本书属于哪个体系（曲式/和声/复调/爵士…），用于分组显示。"""
        domains = getattr(self, '_domains', None)
        if domains is None:
            domains = {}
            path = os.path.join(self.data_dir, 'book_domains.json')
            try:
                with open(path, encoding='utf-8') as handle:
                    domains = json.load(handle)
            except Exception:
                domains = {}
            self._domains = domains
        if book_name in domains:
            return domains[book_name]
        for name, domain in domains.items():
            key = name[:8]
            if key and (key in book_name or book_name[:8] in name):
                return domain
        return '其他'

    def _book_path(self, book_name):
        if book_name in self.books:
            return self.books[book_name]
        for name, path in self.books.items():
            if name[:6] and (name[:6] in book_name or book_name[:6] in name):
                return path
        return ''

    # ------------------------------------------------------------ 动作
    def _open_page(self):
        if not self._target or not self.on_open_page:
            return
        path, page = self._target
        self.on_open_page(path, page)

    def focus_search(self):
        self.search_entry.focus_set()

    # ------------------------------------------------------------ 定位
    def select_term(self, term, tier=None):
        """跳到某个术语（阅读器右键查词、或恢复上次位置时用）。"""
        if tier:
            valid = [name for name, _ in TIERS]
            if tier in valid:
                self.tier_var.set(tier)
        self.search_var.set('')
        self.refresh_list()
        # 若当前分级下没有它，切回「全部」再找
        target = next(((i, row) for i, row in enumerate(self._shown_rows())
                       if row[0] == term), None)
        if target is None and self.tier_var.get() != TIERS[0][0]:
            self.tier_var.set(TIERS[0][0])
            self.refresh_list()
            target = next(((i, row) for i, row in enumerate(self._shown_rows())
                           if row[0] == term), None)
        if target is None:
            return False
        index, _row = target
        self.listbox.selection_clear(0, tk.END)
        self.listbox.selection_set(index)
        self.listbox.see(index)
        self.show_selected()
        return True

    def _shown_rows(self):
        """当前列表里实际显示的行（和 listbox 顺序一致）。"""
        keyword = (self.search_var.get() or '').strip()
        wanted = dict(TIERS).get(self.tier_var.get())
        rows = []
        for term, tier, item in self._rows:
            if wanted and tier != wanted:
                continue
            if keyword:
                names = [term] + list(item.get('aliases') or [])
                if not any(keyword.lower() in name.lower() for name in names):
                    continue
            rows.append((term, tier, item))
        return rows
