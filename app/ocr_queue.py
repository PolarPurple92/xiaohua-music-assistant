# -*- coding: utf-8 -*-
"""排队 OCR 多本书：一本跑完再跑下一本，全程低优先级、单进程、省内存。

用法:
    python _unpack\\ocr_queue.py "<pdf1>" "<pdf2>" ...
    python _unpack\\ocr_queue.py --workers 2 "<pdf1>" "<pdf2>"
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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('pdfs', nargs='+')
    parser.add_argument('--workers', type=int, default=1)
    parser.add_argument('--threads', type=int, default=2)
    parser.add_argument('--max-side', dest='max_side', type=int, default=2400)
    parser.add_argument('--scale', type=float, default=1.4)
    parser.add_argument('--name', action='append', default=[],
                        help='可选：与 pdf 顺序对应的书名')
    args = parser.parse_args()

    total_started = time.time()
    for index, path in enumerate(args.pdfs, start=1):
        path = os.path.abspath(path)
        name = (args.name[index - 1] if index - 1 < len(args.name)
                else os.path.splitext(os.path.basename(path))[0][:40])
        print(f'\n[{index}/{len(args.pdfs)}] {name}')
        print(f'  {path}')
        sys.stdout.flush()
        if not os.path.isfile(path):
            print('  跳过：文件不存在')
            continue

        started = time.time()
        command = [sys.executable, os.path.join(HERE, 'ocr_book.py'), path,
                   '--scale', str(args.scale), '--workers', str(args.workers),
                   '--threads', str(args.threads), '--max-side', str(args.max_side),
                   '--low-priority']
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, encoding='utf-8', errors='ignore')
        tail = [line for line in (result.stdout or '').splitlines() if line.strip()][-5:]
        for line in tail:
            print('  ' + line)
        print(f'  用时 {(time.time() - started) / 60:.1f} 分钟')
        sys.stdout.flush()

        # 登记 + 判类型
        pages = 0
        kind = ''
        try:
            import pypdfium2 as pdfium
            pages = len(pdfium.PdfDocument(path))
        except Exception:
            pass
        try:
            import pdf_book
            kind = pdf_book.Book(path, os.path.join(HERE, 'data')).detect_kind()
        except Exception:
            pass
        registry.register(name, path, pages=pages, kind=kind, scale=args.scale)
        print(f'  已登记：{pages} 页 / {kind or "未知类型"}')

    print(f'\n全部完成，总用时 {(time.time() - total_started) / 60:.1f} 分钟')
    print('下一步：python _unpack\\lookup_terms.py')
    return 0


if __name__ == '__main__':
    sys.exit(main())
