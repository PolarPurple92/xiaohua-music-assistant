# -*- coding: utf-8 -*-
"""书库路径对话框：列出已添加的文件夹，可以添加、删除、直接开始整理。"""
import os

import tkinter as tk

import ttkbootstrap as tb
from ttkbootstrap.constants import BOTH, LEFT, RIGHT, W, X, YES

import book_paths


def open_manager(master, on_run=None):
    """on_run(folders) 在用户点「开始整理」时回调（folders 为存在的目录列表）。"""
    top = tb.Toplevel(master)
    top.title('书库路径')
    top.attributes('-topmost', True)
    try:
        icon = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'icon.ico')
        if os.path.isfile(icon):
            top.iconbitmap(icon)
    except Exception:
        pass

    body = tb.Frame(top, padding=14)
    body.pack(fill=BOTH, expand=YES)

    tb.Label(body, text='「从书里整理」会扫描下面这些文件夹里的 PDF。\n'
                        '默认是发布包里的 books\\，可以再加别的地方，不用的可以删。',
             font=('Microsoft YaHei UI', 9), bootstyle='secondary',
             justify=LEFT).pack(anchor=W, pady=(0, 10))

    frame = tb.Frame(body)
    frame.pack(fill=BOTH, expand=YES)
    listing = tk.Listbox(frame, height=8, width=64, activestyle='none',
                         exportselection=False)
    listing.pack(side=LEFT, fill=BOTH, expand=YES)
    scroll = tb.Scrollbar(frame, orient='vertical', command=listing.yview,
                          bootstyle='round')
    scroll.pack(side=RIGHT, fill='y')
    listing.configure(yscrollcommand=scroll.set)

    status = tb.Label(body, text='', font=('Microsoft YaHei UI', 9),
                      bootstyle='secondary')
    status.pack(anchor=W, pady=(8, 0))

    def refresh():
        listing.delete(0, 'end')
        folders = book_paths.load()
        for path in folders:
            mark = '' if os.path.isdir(path) else '  （不存在）'
            listing.insert('end', path + mark)
        status.configure(text='共 %d 个路径，其中 %d 个可用' % (
            len(folders), len(book_paths.existing(folders))))

    def add_folder():
        from tkinter import filedialog
        kwargs = {'parent': top, 'title': '选一个装着 PDF 的文件夹'}
        default = book_paths.default_folder()
        if os.path.isdir(default):
            kwargs['initialdir'] = default
        path = filedialog.askdirectory(**kwargs)
        if not path:
            return
        book_paths.add(os.path.abspath(path))
        refresh()

    def remove_selected():
        selection = listing.curselection()
        if not selection:
            status.configure(text='先选中一行再删')
            return
        text = listing.get(selection[0]).replace('  （不存在）', '').strip()
        if text == book_paths.default_folder():
            status.configure(text='books 是默认目录，不能删；可以删掉里面别的路径')
            return
        book_paths.remove(text)
        refresh()

    def run_now():
        folders = book_paths.existing()
        if not folders:
            status.configure(text='没有可用目录，先添加一个')
            return
        if on_run:
            top.destroy()
            on_run(folders)
        else:
            status.configure(text='这个窗口没有接上整理动作')

    buttons = tb.Frame(body)
    buttons.pack(fill=X, pady=(12, 0))
    tb.Button(buttons, text='开始整理', bootstyle='primary',
              command=run_now).pack(side=RIGHT)
    tb.Button(buttons, text='添加文件夹…', bootstyle='info-outline',
              command=add_folder).pack(side=RIGHT, padx=(0, 8))
    tb.Button(buttons, text='删除选中', bootstyle='danger-outline',
              command=remove_selected).pack(side=RIGHT, padx=(0, 8))
    tb.Button(buttons, text='关闭', bootstyle='secondary-outline',
              command=top.destroy).pack(side=RIGHT, padx=(0, 8))

    refresh()
    top.transient(master)
    return top
