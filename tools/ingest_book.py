# -*- coding: utf-8 -*-
"""把一本新书纳入语料：登记 → OCR → 提示下一步。

用法:
    python _unpack\\ingest_book.py "<pdf 路径>" [--name 书名] [--workers 4] [--scale 1.4]
    python _unpack\\ingest_book.py --list          # 看当前书目和进度
    python _unpack\\ingest_book.py --no-ocr "<pdf>" # 只登记（OCR 已完成时用）

跑完之后执行（脚本会打印出来）：
    python _unpack\\lookup_terms.py          # 重新检索：新书会进入证据
    python _unpack\\book_definitions.py      # 只为「新书里缺的那部分」生成释义（有缓存）
    python _unpack\\make_glossary_review.py   # 重新出校对稿
"""
import argparse
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, 'runtime'))
sys.path.insert(0, HERE)

import books as registry  # noqa: E402


def list_books():
    items = registry.load_books()
    print(f'{"书名":<24}{"页数":>6}{"类型":>10}  OCR')
    print('-' * 62)
    for book in items:
        prefix = book.get('prefix') or ''
        done = registry._count_pages(prefix)
        total = book.get('pages') or 0
        mark = '完成' if total and done >= total else (f'{done}/{total}' if total else f'{done} 页')
        print(f'{book.get("name", "")[:22]:<24}{total:>6}{book.get("kind") or "-":>10}  {mark}')
    return 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('pdf', nargs='?', default='')
    parser.add_argument('--name', default='')
    parser.add_argument('--workers', type=int, default=4)
    parser.add_argument('--scale', type=float, default=1.4)
    parser.add_argument('--no-ocr', action='store_true')
    parser.add_argument('--list', action='store_true')
    args = parser.parse_args()

    if args.list:
        return list_books()
    if not args.pdf:
        parser.print_help()
        return 2

    path = os.path.abspath(args.pdf)
    if not os.path.isfile(path):
        print('找不到文件:', path)
        return 2

    name = args.name or os.path.splitext(os.path.basename(path))[0][:40]
    print(f'书名: {name}')

    # 1) 页数与类型
    pages = 0
    kind = ''
    try:
        import pypdfium2 as pdfium
        pages = len(pdfium.PdfDocument(path))
        print(f'页数: {pages}')
    except Exception as exc:
        print('读页数失败:', exc)

    # 2) OCR（已有缓存会自动跳过）
    if not args.no_ocr and pages:
        print(f'开始 OCR（{args.workers} 进程，scale={args.scale}）…')
        started = time.time()
        command = [sys.executable, os.path.join(HERE, 'ocr_book.py'), path,
                   '--scale', str(args.scale), '--workers', str(args.workers)]
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, encoding='utf-8', errors='ignore')
        tail = [line for line in (result.stdout or '').splitlines() if line.strip()][-4:]
        for line in tail:
            print('  ' + line)
        print(f'OCR 用时 {(time.time() - started) / 60:.1f} 分钟')
        if result.returncode != 0:
            print('OCR 返回码非 0，可能有个别页失败（不影响后续）')

    # 3) 判类型（需要缓存）
    try:
        import pdf_book
        kind = pdf_book.Book(path, os.path.join(HERE, 'data')).detect_kind()
        print('类型判定:', kind)
    except Exception as exc:
        print('类型判定失败（可忽略）:', exc)

    book = registry.register(name, path, pages=pages, kind=kind, scale=args.scale)
    print(f'已登记: {book["name"]}  prefix={book["prefix"]}')
    print()
    print('下一步（按顺序）：')
    print('  python _unpack\\lookup_terms.py')
    print('  python _unpack\\book_definitions.py')
    print('  python _unpack\\make_glossary_review.py')
    return 0


if __name__ == '__main__':
    sys.exit(main())
