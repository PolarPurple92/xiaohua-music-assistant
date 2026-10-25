# -*- coding: utf-8 -*-
"""记住对某一小节的修正（引擎 / 移调），下次点同一行自动套用。

存到书目录下的 corrections.json：
    {
      "p016_b0320_96a7b98f": {"engine": "audiveris", "transpose": 12,
                              "updated": "2026-10-20 18:40:12"}
    }
键是缓存名（含页码、谱行位置），所以同一本书里不同小节互不干扰。
"""
import json
import os
import time


def _path(folder):
    return os.path.join(folder, 'corrections.json')


def load(folder):
    path = _path(folder)
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, encoding='utf-8') as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save(folder, data):
    try:
        os.makedirs(folder, exist_ok=True)
        with open(_path(folder), 'w', encoding='utf-8') as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False


def get(folder, key):
    return load(folder).get(key) or {}


def remember(folder, key, engine=None, transpose=None, edited=None):
    """记一条修正；只更新传入的字段。"""
    data = load(folder)
    record = data.get(key) or {}
    if engine:
        record['engine'] = engine
    if transpose is not None:
        record['transpose'] = int(transpose)
    if edited is not None:
        record['edited'] = bool(edited)
    record['updated'] = time.strftime('%Y-%m-%d %H:%M:%S')
    data[key] = record
    return _save(folder, data)


def forget(folder, key):
    data = load(folder)
    if key in data:
        data.pop(key, None)
        return _save(folder, data)
    return True
