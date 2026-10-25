# -*- coding: utf-8 -*-
"""术语库质量体检：找出可疑释义，生成一份人工复核清单。

检查项：
  1. 没有任何书内释义的术语（只有我写的通用定义）
  2. 释义里出现"没有相关信息"等占位文本
  3. 释义过短（<15 字）
  4. 只有 1 个来源的术语（证据薄弱）
  5. 黑名单条目统计（按书汇总，看哪本书最容易误收）
"""
import io
import json
from collections import Counter

DATA = r'_unpack\data'
OUT = DATA + r'\glossary_audit.md'


def load(name):
    with io.open(f'{DATA}\\{name}', encoding='utf-8') as handle:
        return json.load(handle)


def main():
    seed = load('glossary_seed.json')
    defs = load('glossary_book_defs.json')
    black = load('glossary_blacklist.json')
    entries = black if isinstance(black, list) else black.get('entries', [])

    no_defs = []
    placeholder = []
    too_short = []
    single_source = []

    for item in seed['terms']:
        term = item['term']
        books = defs.get(term) or {}
        if not books:
            no_defs.append(term)
            continue
        if len(books) == 1:
            single_source.append((term, list(books)[0]))
        for book, payload in books.items():
            text = (payload.get('definition') or '').strip()
            if '没有相关信息' in text or not text:
                placeholder.append((term, book))
            elif len(text) < 15:
                too_short.append((term, book, text))

    by_book = Counter(entry.get('book', '') for entry in entries)

    lines = ['# 术语库体检报告', '']
    lines.append(f'- 术语总数：{len(seed["terms"])}')
    lines.append(f'- 书内释义：{sum(len(v) for v in defs.values())} 条')
    lines.append(f'- 黑名单：{len(entries)} 条')
    lines.append('')

    lines.append(f'## 没有书内释义（{len(no_defs)} 个）')
    lines.append('这些词只有通用定义，回答时要说明没有原书依据。')
    lines.append('')
    lines.append('、'.join(no_defs) or '（无）')
    lines.append('')

    lines.append(f'## 占位文本（{len(placeholder)} 条）')
    for term, book in placeholder[:20]:
        lines.append(f'- {term} / {book}')
    lines.append('')

    lines.append(f'## 释义过短（{len(too_short)} 条）')
    for term, book, text in too_short[:20]:
        lines.append(f'- {term} / {book}：{text}')
    lines.append('')

    lines.append(f'## 只有一个来源（{len(single_source)} 个）')
    for term, book in single_source[:40]:
        lines.append(f'- {term}（{book}）')
    lines.append('')

    lines.append('## 黑名单最多的书（说明该书同词异义多）')
    for book, count in by_book.most_common(8):
        lines.append(f'- {book}：{count} 条')

    with io.open(OUT, 'w', encoding='utf-8') as handle:
        handle.write('\n'.join(lines))
    print('报告已写入:', OUT)
    print('  无释义 %d · 占位 %d · 过短 %d · 单来源 %d'
          % (len(no_defs), len(placeholder), len(too_short), len(single_source)))


if __name__ == '__main__':
    main()
