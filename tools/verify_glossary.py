# -*- coding: utf-8 -*-
"""术语表自检：书内核对 + 英文库交叉核对。

书内核对：逐条检查「原书定义」的原文是否真的出现在所标的 PDF 页上（防页码漂移/抄错）。
英文交叉：用本地英文库（Open Music Theory、爵士站）找对应定义，看是否与我们的说法一致。

产出 data/verification.md 与控制台摘要。
用法: python _unpack\\verify_glossary.py
"""
import io
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, 'runtime'))
sys.path.insert(0, os.path.join(HERE, 'recovered'))
sys.path.insert(0, HERE)

SEED = os.path.join(HERE, 'data', 'glossary_seed.json')
BOOKS = os.path.join(HERE, 'data', 'books.json')
DEFS = os.path.join(HERE, 'data', 'glossary_book_defs.json')
BLACK = os.path.join(HERE, 'data', 'glossary_blacklist.json')
OUT = os.path.join(HERE, 'data', 'verification.md')
LIB_ROOT = os.path.join(HERE, 'data', 'web_library')


def norm(text):
    """只留汉字、字母、数字：半角/全角标点差异不该影响比对。"""
    return re.sub(r'[^\u4e00-\u9fffa-zA-Z0-9]', '', text or '')


def load_json(path, default):
    try:
        with io.open(path, encoding='utf-8') as fp:
            return json.load(fp)
    except Exception:
        return default


def book_path(name, books):
    for book in books:
        if book.get('name') == name:
            return book.get('path') or ''
    # 名字可能被截断，做包含匹配
    for book in books:
        if name[:6] in (book.get('name') or ''):
            return book.get('path') or ''
    return ''


def verify_original(term, original, books, cache):
    """检查原书原文是否真的在那一页上。"""
    path = book_path(original.get('book', ''), books)
    if not path or not os.path.isfile(path):
        return 'missing-book', ''
    pdf_page = original.get('pdf_page')
    if not pdf_page:
        return 'no-page', ''
    if path not in cache:
        import pdf_book
        cache[path] = pdf_book.Book(path, os.path.join(HERE, 'data'))
    book = cache[path]
    try:
        text = book.text(pdf_page)
    except Exception as exc:
        return f'page-error({type(exc).__name__})', ''
    needle = norm(original.get('text', ''))[:24]
    if needle and needle in norm(text):
        return 'ok', ''
    # 允许跨页：检查前后一页
    for neighbour in (pdf_page - 1, pdf_page + 1):
        if 1 <= neighbour <= book.pages:
            try:
                if needle in norm(book.text(neighbour)):
                    return f'neighbour(p{neighbour})', ''
            except Exception:
                pass
    return 'not-found', (text[:80] if text else '')


def english_hits(term, en_map, libraries, limit=1):
    patterns = en_map.get(term) or []
    hits = []
    for name, text in libraries:
        flat = re.sub(r'\s+', ' ', text)
        for pattern in patterns:
            match = re.search(re.escape(pattern), flat, re.I)
            if not match:
                continue
            window = flat[max(0, match.start() - 120):match.start() + 300]
            hits.append((name, window))
            break
        if len(hits) >= limit:
            break
    return hits


def main():
    seed = load_json(SEED, {'terms': []})
    books = load_json(BOOKS, {'books': []}).get('books', [])
    defs = load_json(DEFS, {})
    black = load_json(BLACK, {'entries': []}).get('entries', [])

    from verify_terms import EN_MAP

    libraries = []
    if os.path.isdir(LIB_ROOT):
        for site in sorted(os.listdir(LIB_ROOT)):
            site_dir = os.path.join(LIB_ROOT, site)
            if not os.path.isdir(site_dir):
                continue
            for name in sorted(os.listdir(site_dir)):
                if name.endswith('.txt'):
                    with io.open(os.path.join(site_dir, name), encoding='utf-8') as fp:
                        libraries.append((f'{site}/{name}', fp.read()))

    cache = {}
    rows = []
    ok = failed = 0
    for item in seed['terms']:
        term = item['term']
        status, detail = '', ''
        if item.get('original'):
            status, detail = verify_original(term, item['original'], books, cache)
            if status == 'ok':
                ok += 1
                item['original']['verified'] = True
            else:
                failed += 1
        extra_status = ''
        for extra in (item.get('original_extra') or []):
            extra_status, _ = verify_original(term, extra, books, cache)
        web = english_hits(term, EN_MAP, libraries)
        rows.append({
            'term': term,
            'original': item.get('original'),
            'status': status,
            'extra_status': extra_status,
            'detail': detail,
            'web': web,
            'books': len(defs.get(term) or {}),
        })

    blocked = {(entry['term'], entry['book']) for entry in black}
    leaks = [(term, book) for term, bucket in defs.items() for book in bucket
             if (term, book) in blocked and not bucket[book].get('blacklisted')]

    lines = ['# 术语表验证报告\n',
             f'- 术语 {len(seed["terms"])} 条',
             f'- 原书定义核对：通过 {ok}，待查 {failed}',
             f'- 黑名单拦截泄漏：{len(leaks)} 条',
             f'- 本地英文库交叉：{len(libraries)} 个文件\n']
    lines.append('| 术语 | 原书定义核对 | 英文参考命中 | 分书释义 |')
    lines.append('|---|---|---|---|')
    for row in rows:
        original = row['original']
        label = f"《{original['book'][:12]}》p{original.get('book_page')}" if original else '—'
        status = row['status'] or '—'
        if status != 'ok' and row['extra_status']:
            status += f" / 补充:{row['extra_status']}"
        web = row['web'][0][0] if row['web'] else '—'
        lines.append(f"| {row['term']} | {label} {status} | {web[:26]} | {row['books']} |")

    if leaks:
        lines.append('\n## 黑名单泄漏\n')
        for term, book in leaks:
            lines.append(f'- {term} / {book}')

    with io.open(OUT, 'w', encoding='utf-8') as fp:
        fp.write('\n'.join(lines))
    # 把核对通过的 verified 标记写回术语表
    with io.open(SEED, 'w', encoding='utf-8', newline='\n') as fp:
        json.dump(seed, fp, ensure_ascii=False, indent=2)

    print(f'原书定义核对：通过 {ok}，待查 {failed}')
    for row in rows:
        if row['status'] and row['status'] != 'ok':
            print(f"  ⚠ {row['term']}: {row['status']}")
    print(f'黑名单泄漏: {len(leaks)} 条')
    print(f'英文库交叉命中: {sum(1 for r in rows if r["web"])} 条')
    print(f'报告: {OUT}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
