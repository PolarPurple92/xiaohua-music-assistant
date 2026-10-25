# -*- coding: utf-8 -*-
"""书库路径管理：默认 books/，用户可以再加别的文件夹，也可以删。

路径存 data/book_folders.json，形如：
    {"folders": ["D:\\\\我的书", "J:\\\\小花音乐助手\\\\books"]}
"""
import io
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = (os.path.dirname(HERE)
        if os.path.basename(HERE) in ('app', 'recovered') else HERE)
STORE = os.path.join(ROOT, 'data', 'book_folders.json')


def default_folder():
    return os.path.join(ROOT, 'books')


def load():
    """返回文件夹列表；至少包含默认的 books/。"""
    folders = []
    if os.path.isfile(STORE):
        for encoding in ('utf-8-sig', 'utf-8'):
            try:
                data = json.load(io.open(STORE, encoding=encoding))
                folders = [str(item) for item in (data.get('folders') or [])]
                break
            except Exception:
                continue
    default = default_folder()
    if default not in folders:
        folders.insert(0, default)
    seen = []
    for path in folders:
        if path and path not in seen:
            seen.append(path)
    return seen


def save(folders):
    os.makedirs(os.path.dirname(STORE), exist_ok=True)
    cleaned = []
    for path in folders:
        path = (path or '').strip()
        if path and path not in cleaned:
            cleaned.append(path)
    with io.open(STORE, 'w', encoding='utf-8', newline='\n') as handle:
        json.dump({'folders': cleaned}, handle, ensure_ascii=False, indent=2)
    return cleaned


def add(path):
    folders = load()
    if path and path not in folders:
        folders.append(path)
    return save(folders)


def remove(path):
    return save([item for item in load() if item != path])


def existing(folders=None):
    """只保留真实存在的目录。"""
    return [path for path in (folders if folders is not None else load())
            if os.path.isdir(path)]
