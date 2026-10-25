# -*- coding: utf-8 -*-
"""从书里自动整理术语：扫描文件夹 → 本地 OCR → 模型读文字 → 写进术语库。

用法（命令行）：
    python auto_terms.py <文件夹或 PDF> [--max-pages 80] [--dry-run]

也可以在术语页点「从书里整理」触发同一套逻辑。
"""
import argparse
import glob
import io
import json
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE) if os.path.basename(HERE) == 'app' else HERE
DATA = os.path.join(ROOT, 'data')
CACHE = os.path.join(DATA, 'pdf_cache')

CATEGORIES = ['曲式', '和声', '复调', '配器', '旋律', '节奏', '织体', '调性',
              '终止', '主题', '发展手法', '陈述类型', '外音', '和弦', '声部',
              '早期理论', '中国音乐', '爵士和声', '20世纪技法', '演奏法']
PERIODS = ['通用', '中世纪', '文艺复兴', '巴洛克', '前古典', '古典',
           '浪漫', '20世纪', '中国传统']

PROMPT = """你是音乐理论术语库的编辑。下面是一本教材某几页的 OCR 文字。

请从中找出**作者在定义或系统解释的术语**，输出 JSON 数组，不要任何解释：

[
  {
    "term": "中文规范名",
    "aliases": ["英文或别称", "最多三个"],
    "category": "从这些里选：%(categories)s",
    "period": "从这些里选：%(periods)s",
    "definition": "用这本书的意思概括，40~90 字",
    "page": 12
  }
]

规则：
1. 只收「书里真的在讲的概念」。人名、曲名、书名、谱例编号、习题编号一律不要。
2. 一段文字最多给 5 个术语，宁少勿滥。
3. 定义必须忠于这段文字，不要补充书里没有的内容。
4. 没有合适术语就输出 []。
"""


def _log(message):
    try:
        os.makedirs(DATA, exist_ok=True)
        with io.open(os.path.join(DATA, 'auto_terms.log'), 'a', encoding='utf-8') as handle:
            handle.write('[%s] %s\n' % (time.strftime('%H:%M:%S'), message))
    except Exception:
        pass


def find_pdfs(target):
    target = os.path.abspath(target)
    if os.path.isfile(target):
        return [target] if target.lower().endswith('.pdf') else []
    if not os.path.isdir(target):
        return []
    found = sorted(glob.glob(os.path.join(target, '*.pdf')))
    return [path for path in found if os.path.getsize(path) > 20000]


def _stem(name):
    return re.sub(r'[^\w\u4e00-\u9fff]+', '_', name)[:48]


def page_texts(pdf_path, max_pages=80, progress=None):
    """返回 {页码: 文字}。缺 OCR 的页现跑（本地，不联网）。"""
    try:
        from pdf_book import Book
    except Exception:
        return {}
    stem = _stem(os.path.splitext(os.path.basename(pdf_path))[0])
    try:
        book = Book(pdf_path, CACHE)
    except Exception as exc:
        _log('打不开 %s：%s' % (os.path.basename(pdf_path), exc))
        return {}

    total = min(book.pages, max_pages)
    try:
        import ocr_book
    except Exception:
        ocr_book = None

    texts = {}
    for page in range(1, total + 1):
        cache_file = os.path.join(CACHE, '%s_p%03d.ocr.json' % (stem, page))
        text = ''
        if os.path.isfile(cache_file):
            try:
                blocks = json.load(io.open(cache_file, encoding='utf-8'))
                text = ' '.join(block.get('text', '') for block in blocks)
            except Exception:
                text = ''
        if len(text) < 80 and ocr_book is not None:
            try:
                ocr_book.ocr_page(pdf_path, stem, CACHE, page, 1.4)
                blocks = json.load(io.open(cache_file, encoding='utf-8'))
                text = ' '.join(block.get('text', '') for block in blocks)
            except Exception as exc:
                _log('OCR 第 %d 页失败：%s' % (page, exc))
        if text.strip():
            texts[page] = text
        if progress and page % 10 == 0:
            progress('OCR %d/%d 页' % (page, total))
    return texts


def _chunks(texts, size=3):
    pages = sorted(texts)
    for index in range(0, len(pages), size):
        group = pages[index:index + size]
        yield group, '\n'.join('【第 %d 页】%s' % (page, texts[page]) for page in group)


def _parse(text):
    cleaned = (text or '').strip()
    cleaned = re.sub(r'^```(?:json)?|```$', '', cleaned, flags=re.M).strip()
    match = re.search(r'\[.*\]', cleaned, re.S)
    if not match:
        return []
    try:
        data = json.loads(match.group(0))
    except Exception:
        return []
    return [item for item in data if isinstance(item, dict) and item.get('term')]


def extract_from_book(pdf_path, config_path='', max_pages=80, progress=None, stop=None):
    """返回本书记录到的术语（未去重、未写盘）。"""
    import explain
    config = explain.LlmConfig.load(config_path or os.path.join(DATA, 'llm.json'))
    if not config.usable():
        raise RuntimeError('还没配置模型接口：先在「模型」里填好')

    texts = page_texts(pdf_path, max_pages=max_pages, progress=progress)
    if not texts:
        _log('%s 没有可读文字' % os.path.basename(pdf_path))
        return []

    system = PROMPT % {'categories': '、'.join(CATEGORIES),
                       'periods': '、'.join(PERIODS)}
    collected = []
    groups = list(_chunks(texts))
    for index, (pages, chunk) in enumerate(groups, start=1):
        if stop and stop():
            break
        if progress:
            progress('模型整理 %d/%d 段（第 %d 页起）' % (index, len(groups), pages[0]))
        messages = [{'role': 'system', 'content': system},
                    {'role': 'user', 'content': chunk[:4000]}]
        try:
            answer, _usage = explain.call_cloud(messages, config, timeout=120)
        except Exception as exc:
            _log('第 %s 页调用失败：%s' % (pages, exc))
            continue
        for item in _parse(answer):
            item['book'] = os.path.basename(pdf_path)
            item.setdefault('page', pages[0])
            collected.append(item)
    return collected


def merge_terms(terms, data_dir=None, dry_run=False):
    """把结果并进 glossary_seed.json，返回 (新增数, 跳过数)。"""
    data_dir = data_dir or DATA
    path = os.path.join(data_dir, 'glossary_seed.json')
    seed = {'terms': []}
    if os.path.isfile(path):
        try:
            seed = json.load(io.open(path, encoding='utf-8-sig'))
        except Exception:
            seed = {'terms': []}
    existing = {item.get('term') for item in seed.get('terms', [])}
    added = skipped = 0
    for item in terms:
        term = (item.get('term') or '').strip()
        if not term or term in existing:
            skipped += 1
            continue
        if item.get('category') not in CATEGORIES:
            item['category'] = '通用'
        if item.get('period') not in PERIODS:
            item['period'] = '通用'
        seed.setdefault('terms', []).append({
            'term': term,
            'aliases': item.get('aliases') or [],
            'category': item.get('category'),
            'period': item.get('period'),
            'definition': item.get('definition') or '',
            'state': 'draft',
            'scope': 'consensus',
            'review': 'auto-extract',
            'source': '%s p%s' % (item.get('book') or '', item.get('page') or ''),
        })
        existing.add(term)
        added += 1
    if not dry_run and added:
        os.makedirs(data_dir, exist_ok=True)
        with io.open(path, 'w', encoding='utf-8', newline='\n') as handle:
            json.dump(seed, handle, ensure_ascii=False, indent=2)
    return added, skipped


def run(target, max_pages=80, config_path='', progress=None, stop=None, dry_run=False):
    pdfs = find_pdfs(target)
    if not pdfs:
        return {'added': 0, 'skipped': 0, 'books': 0, 'message': '这个文件夹里没有 PDF'}
    added = skipped = 0
    for index, pdf in enumerate(pdfs, start=1):
        if stop and stop():
            break
        name = os.path.basename(pdf)
        if progress:
            progress('第 %d/%d 本：%s' % (index, len(pdfs), name))
        try:
            terms = extract_from_book(pdf, config_path, max_pages=max_pages,
                                      progress=progress, stop=stop)
        except Exception as exc:
            _log('%s 失败：%s' % (name, exc))
            continue
        a, s = merge_terms(terms, dry_run=dry_run)
        added += a
        skipped += s
        _log('%s：新增 %d，跳过 %d' % (name, a, s))
    return {'added': added, 'skipped': skipped, 'books': len(pdfs), 'pdfs': pdfs}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('target', help='PDF 文件或文件夹')
    parser.add_argument('--max-pages', type=int, default=80)
    parser.add_argument('--config', default='')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    result = run(args.target, args.max_pages, args.config,
                 progress=lambda message: print('  ' + message, flush=True),
                 dry_run=args.dry_run)
    print('结果：%s' % {k: v for k, v in result.items() if k != 'pdfs'})
    return 0


if __name__ == '__main__':
    sys.exit(main())
