# -*- coding: utf-8 -*-
"""把三本种子书排队 OCR（多进程并行，一本跑完再跑下一本）。

用法: python _unpack\\ocr_seed.py [--workers 4] [--scale 1.4]
"""
import argparse
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))

BOOKS = [
    ('和声学教程（桑桐）', r'J:\pdf收集处\第三次英文\和声学教程 (桑桐) (z-library.sk, 1lib.sk, z-lib.sk).pdf'),
    ('和声分析 351 例', r'J:\pdf收集处\第三次英文\和声分析351例 (吴式锴编著) (z-library.sk, 1lib.sk, z-lib.sk).pdf'),
    ('250 首和声习题解答', r'J:\pdf收集处\第三次英文\250首和声习题解答 (桑桐) (z-library.sk, 1lib.sk, z-lib.sk).pdf'),
]


def main():
    parser = argparse.ArgumentParser()
    # 实测每个 OCR 进程常驻约 500 MB（模型占大头），
    # 所以默认只开 1 个进程；机器空闲时可以 --workers 2 提速。
    parser.add_argument('--workers', type=int, default=1)
    parser.add_argument('--scale', type=float, default=1.4)
    parser.add_argument('--threads', type=int, default=2,
                        help='每个进程的 OCR 线程数')
    parser.add_argument('--max-side', dest='max_side', type=int, default=2400,
                        help='渲染长边上限（像素）')
    args = parser.parse_args()

    started = time.time()
    for index, (label, path) in enumerate(BOOKS, start=1):
        if not os.path.isfile(path):
            print(f'[{index}/{len(BOOKS)}] 跳过（找不到）：{label}')
            continue
        print(f'\n[{index}/{len(BOOKS)}] {label}')
        print(f'  {path}')
        sys.stdout.flush()
        book_started = time.time()
        result = subprocess.run(
            [sys.executable, os.path.join(HERE, 'ocr_book.py'), path,
             '--scale', str(args.scale), '--workers', str(args.workers),
             '--threads', str(args.threads), '--max-side', str(args.max_side),
             '--low-priority'],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8',
            errors='ignore')
        tail = [line for line in (result.stdout or '').splitlines() if line.strip()][-6:]
        for line in tail:
            print('  ' + line)
        print(f'  该书用时 {(time.time() - book_started) / 60:.1f} 分钟')
        sys.stdout.flush()

    print(f'\n全部完成，总用时 {(time.time() - started) / 60:.1f} 分钟')
    return 0


if __name__ == '__main__':
    sys.exit(main())
