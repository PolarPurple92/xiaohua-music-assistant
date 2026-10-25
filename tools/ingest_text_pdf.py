# -*- coding: utf-8 -*-
"""带文字层 PDF 的快速入库：跳过 OCR，直接抽取文本写进同一套缓存格式。

用法：
    python _unpack\\ingest_text_pdf.py "<pdf>" [--name 书名] [...]
生成 `data/pdf_cache/<stem>_pNNN.ocr.json`，格式与 ocr_book 一致：
    [{"text": ..., "score": 1.0, "x": 0, "y": 0, "x2": 0, "y2": 0}, ...]
"""
import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, 'runtime'))
sys.path.insert(0, HERE)

CACHE = os.path.join(HERE, 'data', 'pdf_cache')


def stem_of(path):
    name = os.path.splitext(os.path.basename(path))[0]
    return re.sub(r'[^\w\u4e00-\u9fff]+', '_', name).strip('_')[:48]


def page_text(page):
    try:
        return page.get_textpage().get_text_range() or ''
    except Exception:
        return ''


def ingest(path, name=''):
    import pypdfium2 as pdfium
    os.makedirs(CACHE, exist_ok=True)
    doc = pdfium.PdfDocument(path)
    total = len(doc)
    stem = stem_of(path)
    written = skipped = empty = 0
    for index in range(total):
        target = os.path.join(CACHE, '%s_p%03d.ocr.json' % (stem, index + 1))
        if os.path.isfile(target) and os.path.getsize(target) > 40:
            skipped += 1
            continue
        text = page_text(doc[index]).strip()
        if len(text) < 20:
            empty += 1
            continue
        blocks = [{'text': text, 'score': 1.0, 'x': 0, 'y': 0, 'x2': 0, 'y2': 0}]
        with open(target, 'w', encoding='utf-8') as handle:
            json.dump(blocks, handle, ensure_ascii=False)
        written += 1
        if written % 50 == 0:
            print('   已写 %d 页' % written, flush=True)
    doc.close()

    # 登记
    try:
        import books as registry
        import pdf_book
        kind = ''
        try:
            kind = pdf_book.Book(path, os.path.join(HERE, 'data')).detect_kind()
        except Exception:
            pass
        registry.register(name or stem, path, pages=total, kind=kind, scale=1.0)
    except Exception as exc:
        print('   登记失败（不影响缓存）:', str(exc)[:60])

    print('%s：共 %d 页，写入 %d，跳过 %d，空白 %d'
          % (name or stem, total, written, skipped, empty))
    return written


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('pdfs', nargs='+')
    parser.add_argument('--name', action='append', default=[])
    args = parser.parse_args()
    for index, path in enumerate(args.pdfs):
        path = os.path.abspath(path)
        name = args.name[index] if index < len(args.name) else ''
        print('[%d/%d] %s' % (index + 1, len(args.pdfs), name or os.path.basename(path)))
        if not os.path.isfile(path):
            print('   文件不存在')
            continue
        ingest(path, name)
    return 0


if __name__ == '__main__':
    sys.exit(main())
