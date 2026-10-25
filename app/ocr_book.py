# -*- coding: utf-8 -*-
"""把一本 PDF 的每一页 OCR 成 JSON（并行），结果落到 pdf_cache 目录。

每页一个 `<stem>_pNNN.ocr.json`，格式和 pdf_book.Book.blocks() 一致，
所以之后的检索、断题、讲解都能直接复用。

用法:
    python _unpack\\ocr_book.py "<pdf 路径>" [--scale 1.4] [--workers 4] [--from 1] [--to 0]
"""
import argparse
import gc
import json
import os
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))

# 控制 OCR 的计算线程数：不限制的话每个进程都会吃满所有核心，
# 4 个进程一起跑就是 4 倍的线程争抢，机器会明显卡顿。
for _name in ('OMP_NUM_THREADS', 'ORT_NUM_THREADS', 'MKL_NUM_THREADS',
              'OPENBLAS_NUM_THREADS', 'NUMEXPR_NUM_THREADS'):
    os.environ.setdefault(_name, '2')
sys.path.insert(0, os.path.join(HERE, 'runtime'))

from concurrent.futures import ThreadPoolExecutor  # noqa: E402

_thread_local = threading.local()


def engine():
    """每个进程一个 OCR 实例。

    关键：必须显式限制 intra_op_num_threads。实测默认配置下**一页** OCR 会烧掉
    18 个核心（CPU 101 秒 / 实际 5.7 秒），机器必定卡死；限制到 4 线程后
    只要 7.8 秒 CPU，速度还快一点（3.7 秒/页）。
    """
    if getattr(_thread_local, 'engine', None) is None:
        from rapidocr_onnxruntime import RapidOCR
        threads = int(os.environ.get('XIAOHUA_OCR_THREADS', '4'))
        try:
            _thread_local.engine = RapidOCR(intra_op_num_threads=threads)
        except Exception:
            _thread_local.engine = RapidOCR()
    if getattr(_thread_local, 'doc', None) is None:
        import pypdfium2 as pdfium
        _thread_local.doc = pdfium.PdfDocument(_thread_local.path)
    return _thread_local.engine


def ocr_page(path, stem, cache_dir, number, scale, redo_empty=True,
             max_side=2400, target_side=1600):
    import numpy as np
    target = os.path.join(cache_dir, f'{stem}_p{number:03d}.ocr.json')
    if os.path.isfile(target):
        try:
            with open(target, encoding='utf-8') as fp:
                cached = json.load(fp)
            # 0 块的缓存多半是之前并发跑坏留下的，重做
            if cached or not redo_empty:
                return number, len(cached), True
        except Exception:
            pass
    _thread_local.path = path
    ocr = engine()
    page = _thread_local.doc[number - 1]
    width, height = page.get_size()
    side = max(width, height) or 1
    # 长边封顶：大页书（如 1561×2285 pt）按 scale 1.4 会渲染成 20 MB 位图，
    # 4 个进程同时跑就把内存吃满了。按长边压到 max_side 以内，质量实测没损失。
    effective = scale
    # 小页面（如 519x632 pt）按 scale 1.4 只有 885 px，OCR 会掉置信度；
    # 所以低于目标长边时自动放大，高于上限时压回来。
    if target_side and side * effective < target_side:
        effective = target_side / side
    if max_side and side * effective > max_side:
        effective = max_side / side
    effective = min(4.0, max(0.5, effective))
    image = page.render(scale=effective).to_pil().convert('RGB')
    result, _elapse = ocr(np.array(image))
    del image
    blocks = []
    for box, text, score in (result or []):
        xs = [point[0] for point in box]
        ys = [point[1] for point in box]
        blocks.append({
            'text': text,
            'score': round(float(score), 3),
            'x': int(min(xs)),
            'y': int(sum(ys) / 4),
            'x2': int(max(xs)),
            'y2': int(max(ys)),
        })
    blocks.sort(key=lambda block: (block['y'], block['x']))
    with open(target, 'w', encoding='utf-8') as fp:
        json.dump(blocks, fp, ensure_ascii=False)
    gc.collect()
    return number, len(blocks), False


def _lower_priority():
    """把本进程降到「低于正常」优先级，边用电脑边跑时不抢前台。

    注意：必须声明 argtypes，否则 64 位下 HANDLE 会被截断成 32 位，
    SetPriorityClass 会静默失败（返回 0）。
    """
    try:
        import ctypes
        import ctypes.wintypes as wt
        kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel32.GetCurrentProcess.restype = wt.HANDLE
        kernel32.SetPriorityClass.argtypes = [wt.HANDLE, wt.DWORD]
        kernel32.SetPriorityClass.restype = wt.BOOL
        BELOW_NORMAL_PRIORITY_CLASS = 0x00004000
        handle = kernel32.GetCurrentProcess()
        kernel32.SetPriorityClass(handle, BELOW_NORMAL_PRIORITY_CLASS)
    except Exception:
        pass


def _stem_of(path):
    import re
    name = os.path.splitext(os.path.basename(path))[0]
    return re.sub(r'[^\w\u4e00-\u9fff]+', '_', name).strip('_')[:48]


def run_parallel(path, cache, start, end, scale, workers, max_side=2400,
                 target_side=1600):
    """多进程并行：把页码切成连续几段，每段一个子进程（子进程内是主线程跑 OCR）。

    为什么不用线程：实测在同一个进程里开多个线程同时建 onnxruntime 会话，
    会出现「识别返回 0 块」的静默失败；子进程互不干扰，稳定得多。
    """
    import subprocess
    pages = list(range(start, end + 1))
    if not pages:
        return 0
    workers = max(1, min(workers, len(pages)))
    chunk = (len(pages) + workers - 1) // workers
    children = []
    for index in range(workers):
        part = pages[index * chunk:(index + 1) * chunk]
        if not part:
            continue
        command = [sys.executable, os.path.abspath(__file__), path,
                   '--scale', str(scale), '--workers', '1',
                   '--from', str(part[0]), '--to', str(part[-1]),
                   '--cache', cache, '--max-side', str(max_side),
                   '--target-side', str(target_side), '--low-priority']
        print(f'  子进程 {index + 1}: 第 {part[0]}-{part[-1]} 页')
        env = dict(os.environ)
        env['XIAOHUA_OCR_THREADS'] = str(os.environ.get('XIAOHUA_OCR_THREADS', '4'))
        for _name in ('OMP_NUM_THREADS', 'ORT_NUM_THREADS', 'MKL_NUM_THREADS',
                      'OPENBLAS_NUM_THREADS', 'NUMEXPR_NUM_THREADS'):
            env[_name] = str(os.environ.get(_name, '4'))
        children.append(subprocess.Popen(command, stdout=subprocess.DEVNULL,
                                         stderr=subprocess.STDOUT, env=env))
    for child in children:
        child.wait()
    return 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('pdf')
    parser.add_argument('--scale', type=float, default=1.4)
    parser.add_argument('--workers', type=int, default=1)
    parser.add_argument('--low-priority', action='store_true',
                        help='降低进程优先级，边用电脑边跑')
    parser.add_argument('--from', dest='start', type=int, default=1)
    parser.add_argument('--to', dest='end', type=int, default=0)
    parser.add_argument('--cache', default=os.path.join(HERE, 'data', 'pdf_cache'))
    parser.add_argument('--max-side', dest='max_side', type=int, default=2400,
                        help='渲染长边上限（像素），越大越清晰也越吃内存')
    parser.add_argument('--threads', type=int, default=4,
                        help='每个进程的 onnxruntime 线程数（默认 4；不限制会吃满 18 核）')
    parser.add_argument('--target-side', dest='target_side', type=int, default=1600,
                        help='小于这个长边的小页面会自动放大')
    args = parser.parse_args()
    if args.low_priority:
        _lower_priority()
    os.environ['XIAOHUA_OCR_THREADS'] = str(max(1, args.threads))
    for _name in ('OMP_NUM_THREADS', 'ORT_NUM_THREADS', 'MKL_NUM_THREADS',
                  'OPENBLAS_NUM_THREADS', 'NUMEXPR_NUM_THREADS'):
        os.environ[_name] = str(max(1, args.threads))

    import pypdfium2 as pdfium

    path = os.path.abspath(args.pdf)
    stem = _stem_of(path)
    os.makedirs(args.cache, exist_ok=True)

    total = len(pdfium.PdfDocument(path))
    start = max(1, args.start)
    end = total if not args.end else min(total, args.end)

    if args.workers > 1:
        print(f'{os.path.basename(path)[:60]}')
        print(f'共 {total} 页，处理 {start}-{end}（{end - start + 1} 页），'
              f'分 {args.workers} 个进程')
        return run_parallel(path, args.cache, start, end, args.scale,
                            args.workers, args.max_side, args.target_side)

    pages = list(range(start, end + 1))
    done = sum(1 for n in pages
               if os.path.isfile(os.path.join(args.cache, f'{stem}_p{n:03d}.ocr.json')))
    print(f'{os.path.basename(path)[:60]}')
    print(f'共 {total} 页，处理 {start}-{end}（{len(pages)} 页），已缓存 {done} 页')
    print(f'scale={args.scale} 单进程 cache={args.cache}')
    sys.stdout.flush()

    started = time.time()
    finished = 0
    empty = 0
    failed = 0
    for number in pages:
        try:
            number, blocks, cached = ocr_page(path, stem, args.cache, number,
                                              args.scale, max_side=args.max_side,
                                              target_side=args.target_side)
        except Exception as exc:
            failed += 1
            print(f'  第 {number} 页失败: {type(exc).__name__}: {exc}')
            continue
        finished += 1
        if blocks == 0:
            empty += 1
        if finished % 25 == 0 or finished == len(pages):
            elapsed = time.time() - started
            rate = finished / elapsed if elapsed else 0
            left = (len(pages) - finished) / rate if rate else 0
            print(f'  {finished}/{len(pages)}  已用 {elapsed/60:.1f} 分钟  '
                  f'剩余约 {left/60:.1f} 分钟')
            sys.stdout.flush()

    print(f'完成：{finished} 页，空页 {empty}，失败 {failed}，'
          f'用时 {(time.time()-started)/60:.1f} 分钟')
    return 0


if __name__ == '__main__':
    sys.exit(main())
