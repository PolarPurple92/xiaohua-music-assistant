# -*- coding: utf-8 -*-
"""用书里的原文给种子术语表做「证据校验」。

做法：拿术语表里的每个词（含别名），在三本书的 OCR 结果里找包含它的句子，
按「像不像定义句」打分，取每条书的前几条，附上书名和书页码。

产出 data/glossary_evidence.json。这一步不调模型、不联网，纯检索。
用法: python _unpack\\lookup_terms.py [--only 圣咏式,留音]
"""
import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, 'runtime'))

CACHE = os.path.join(HERE, 'data', 'pdf_cache')
SEED = os.path.join(HERE, 'data', 'glossary_seed.json')
OUT = os.path.join(HERE, 'data', 'glossary_evidence.json')

def _book_pairs():
    """书目来自 data/books.json（可由 ingest_book.py 追加新书）。"""
    try:
        from books import book_pairs
        pairs = book_pairs()
        if pairs:
            return pairs
    except Exception as exc:
        print('读取书目失败，退回内置三本:', exc)
    return [
        ('和声学教程（桑桐）', '和声学教程_桑桐_z_library_sk_1lib_sk_z_lib_sk'),
        ('和声分析351例', '和声分析351例_吴式锴编著_z_library_sk_1lib_sk_z_lib_sk'),
        ('250首和声习题解答', '250首和声习题解答_桑桐_z_library_sk_1lib_sk_z_lib_sk'),
    ]


BOOKS = _book_pairs()

DEF_VERBS = ('是', '指', '称为', '叫做', '所谓', '又称', '亦称', '即')
SENTENCE_END = '。！？；\n'


PURE_NUM_RE = re.compile(r'^[\s\-—.、()（）\[\]]*(\d{1,4})[\s\-—.、()（）\[\]]*$')
HEAD_NUM_RE = re.compile(r'^(\d{1,4})\s*[\u4e00-\u9fff]')
TAIL_NUM_RE = re.compile(r'[\u4e00-\u9fff）)\]]\s*(\d{1,4})\s*$')


def _printed_page(blocks, pdf_page):
    """从页面边缘认印刷页码；认不出就退回 PDF 页码。

    书本页码可能出现在：页脚孤立数字（最常见）、页眉开头、页眉末尾。
    """
    if not blocks:
        return pdf_page
    height = max(block.get('y2', 0) for block in blocks) or 1
    edge = [block for block in blocks
            if block.get('y', 0) < height * 0.08 or block.get('y', 0) > height * 0.90]

    def plausible(value):
        return 1 <= value <= 9999 and value <= pdf_page and pdf_page - value <= 40

    for block in edge:
        text = block['text'].strip()
        if len(text) > 8:
            continue
        match = PURE_NUM_RE.match(text)
        if match and plausible(int(match.group(1))):
            return int(match.group(1))
    for block in edge:
        text = block['text'].strip()
        match = HEAD_NUM_RE.match(text) or TAIL_NUM_RE.search(text)
        if match and plausible(int(match.group(1))):
            return int(match.group(1))
    return pdf_page


def load_book(prefix):
    """返回 [(pdf_page, 书页, 句子)]。"""
    pages = {}
    for name in os.listdir(CACHE):
        if not name.startswith(prefix) or not name.endswith('.ocr.json'):
            continue
        match = re.search(r'_p(\d{3})\.ocr\.json$', name)
        if match:
            number = int(match.group(1))
            with open(os.path.join(CACHE, name), encoding='utf-8') as fp:
                pages[number] = json.load(fp)

    out = []
    for pdf_page in sorted(pages):
        blocks = sorted(pages[pdf_page], key=lambda b: (round(b['y'] / 12), b['x']))
        lines, current, current_y = [], [], None
        for block in blocks:
            if current_y is None or abs(block['y'] - current_y) <= 14:
                current.append(block['text'])
                current_y = block['y'] if current_y is None else current_y
            else:
                lines.append(''.join(current))
                current, current_y = [block['text']], block['y']
        if current:
            lines.append(''.join(current))

        book_page = _printed_page(blocks, pdf_page)

        text = ''.join(line if line.endswith(tuple(SENTENCE_END)) else line + '。'
                       for line in lines)
        buffer = ''
        for char in text:
            buffer += char
            if char in SENTENCE_END:
                if len(buffer.strip()) >= 8:
                    out.append((pdf_page, book_page, buffer.strip()))
                buffer = ''
        if buffer.strip():
            out.append((pdf_page, book_page, buffer.strip()))
    return out


def is_toc_like(sentence):
    """目录行/页眉：「三、经过音76。」「属七和弦（例42～53）...（14）」。"""
    if sentence.count('…') >= 3 or sentence.count('·') >= 3:
        return True
    if re.search(r'\.{2,}', sentence):          # 任意两个以上英文点 = 点线
        return True
    if re.search(r'[（(]\s*例\s*\d+', sentence):  # 例题索引
        return True
    if len(sentence) <= 14 and re.search(r'\d+\s*。$', sentence):
        return True
    if re.search(r'[.…]{4,}', sentence):
        return True
    return False


def score_sentence(sentence, term):
    score = 0
    if any(verb in sentence for verb in DEF_VERBS):
        score += 3
    # 术语附近就跟着「是/指/称为」——最像定义
    if re.search(re.escape(term) + r'[^。；]{0,10}(是|指|称为|叫做|即)', sentence):
        score += 4
    if 12 <= len(sentence) <= 120:
        score += 2
    elif len(sentence) > 200:
        score -= 2
    if sentence.find(term) <= 20:
        score += 1          # 术语出现在句首附近，多半是主语
    if any(word in sentence for word in ('音', '和弦', '声部', '调', '节奏')):
        score += 1
    if is_toc_like(sentence):
        score -= 5          # 目录行不是定义
    return score


def build_presentation(item, by_book):
    """按 scope 生成给用户/模型看的文本块。

    consensus：统一定义 + 各书原句作佐证
    contested：不合并，逐书列出各自的原文与页码
    """
    lines = []
    if item.get('scope') == 'contested':
        lines.append(f"【{item['term']}｜各教材口径不同，不要合并】")
        if item.get('dispute'):
            lines.append(f"分歧点：{item['dispute']}")
        for book, hits in by_book.items():
            best = hits[0]
            lines.append(f"· 《{book}》第 {best['page']} 页：{best['sentence'][:120]}")
        if not by_book:
            lines.append(f"（书上暂未检索到原句；通行说法：{item.get('definition', '')[:80]}）")
    else:
        lines.append(f"【{item['term']}】{item.get('definition', '')}")
        for book, hits in list(by_book.items())[:2]:
            best = hits[0]
            lines.append(f"· 《{book}》第 {best['page']} 页：{best['sentence'][:100]}")
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--only', default='')
    args = parser.parse_args()
    only = [item.strip() for item in args.only.split(',') if item.strip()]

    with open(SEED, encoding='utf-8') as fp:
        seed = json.load(fp)
    terms = seed['terms']
    if only:
        terms = [item for item in terms if item['term'] in only or
                 any(alias in only for alias in item.get('aliases', []))]

    corpus = {}
    for title, prefix in BOOKS:
        sentences = load_book(prefix)
        corpus[title] = sentences
        print(f'{title}: {len(sentences)} 句')

    result = []
    for item in terms:
        names = [item['term']] + item.get('aliases', [])
        by_book = {}
        for title, sentences in corpus.items():
            hits = []
            for index, (pdf_page, book_page, sentence) in enumerate(sentences):
                if not any(name and name in sentence for name in names):
                    continue
                if is_toc_like(sentence):
                    continue
                context = sentence
                # 带上下一句，避免「采用同节奏圣咏式处理法。」这种太短的句子没头没尾
                if len(sentence) < 40 and index + 1 < len(sentences):
                    context = sentence + ' ' + sentences[index + 1][2][:120]
                hits.append({
                    'sentence': context[:300],
                    'page': book_page,
                    'pdf_page': pdf_page,
                    'score': score_sentence(sentence, item['term']),
                })
            if hits:
                hits.sort(key=lambda entry: -entry['score'])
                by_book[title] = hits[:6]

        result.append({
            'term': item['term'],
            'aliases': item.get('aliases', []),
            'category': item.get('category', ''),
            'scope': item.get('scope', 'consensus'),
            'definition': item.get('definition', ''),
            'dispute': item.get('dispute', ''),
            'pitfall': item.get('pitfall', ''),
            'by_book': by_book,
            'evidence': [entry for hits in by_book.values() for entry in hits],
            'presentation': build_presentation(item, by_book),
        })

    # 合并：只更新本次检索到的术语，其余保留（避免 --only 把别的术语证据冲掉）
    merged = []
    seen = set()
    for entry in result:
        merged.append(entry)
        seen.add(entry['term'])
    if only:
        try:
            with open(OUT, encoding='utf-8') as fp:
                previous = json.load(fp)
        except Exception:
            previous = []
        for entry in previous:
            if entry.get('term') not in seen:
                merged.append(entry)
                seen.add(entry.get('term'))

    with open(OUT, 'w', encoding='utf-8') as fp:
        json.dump(merged, fp, ensure_ascii=False, indent=1)
    print(f'\n写入 {OUT}')
    result = merged

    covered = sum(1 for item in result if item['evidence'])
    print(f'术语 {len(result)} 个，其中 {covered} 个在书里找到了原文')

    print('\n--- 证据示例 ---')
    showcase = ('圣咏式处理法', '留音', '经过音', '同和弦变位', '模进',
                '二五进行', '引导音')
    for item in result:
        if not item.get('by_book'):
            continue
        if item['term'] not in showcase:
            continue
        print('\n【%s】' % item['term'])
        print('  我的定义: %s…' % item['definition'][:70])
        for book, hits in list(item['by_book'].items())[:2]:
            best = hits[0]
            print('  ·《%s》书页 %s（PDF %s）' % (book, best['page'], best['pdf_page']))
            print('    %s' % best['sentence'][:100])
    return 0


if __name__ == '__main__':
    sys.exit(main())
