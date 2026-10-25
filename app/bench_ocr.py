# -*- coding: utf-8 -*-
"""量一页 OCR 的峰值内存（Windows PSAPI）。

用法: python _unpack\\bench_ocr.py --max-side 2400 --page 52
"""
import argparse
import ctypes
import ctypes.wintypes as wt
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, 'runtime'))

SANG = (r'J:\pdf收集处\第一次上传\和声学教程 （上下册） （增订重译版） 俄罗斯 '
        r'([苏]伊·杜波夫斯基，斯·叶甫谢耶夫，伊·斯波索宾，符·索科洛夫合著) '
        r'(z-library.sk, 1lib.sk, z-lib.sk).pdf')


class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
    _fields_ = [
        ('cb', wt.DWORD), ('PageFaultCount', wt.DWORD),
        ('PeakWorkingSetSize', ctypes.c_size_t), ('WorkingSetSize', ctypes.c_size_t),
        ('QuotaPeakPagedPoolUsage', ctypes.c_size_t), ('QuotaPagedPoolUsage', ctypes.c_size_t),
        ('QuotaPeakNonPagedPoolUsage', ctypes.c_size_t), ('QuotaNonPagedPoolUsage', ctypes.c_size_t),
        ('PagefileUsage', ctypes.c_size_t), ('PeakPagefileUsage', ctypes.c_size_t),
    ]


def peak_mb():
    counters = PROCESS_MEMORY_COUNTERS()
    counters.cb = ctypes.sizeof(counters)
    psapi = ctypes.WinDLL('psapi', use_last_error=True)
    psapi.GetProcessMemoryInfo.argtypes = [wt.HANDLE,
                                           ctypes.POINTER(PROCESS_MEMORY_COUNTERS),
                                           wt.DWORD]
    psapi.GetProcessMemoryInfo.restype = wt.BOOL
    handle = ctypes.windll.kernel32.GetCurrentProcess()
    ok = psapi.GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb)
    if not ok:
        return -1
    return counters.PeakWorkingSetSize / 1024 / 1024


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--max-side', dest='max_side', type=int, default=2400)
    parser.add_argument('--page', type=int, default=52)
    parser.add_argument('--threads', type=int, default=2)
    parser.add_argument('--book', default=SANG)
    args = parser.parse_args()

    for name in ('OMP_NUM_THREADS', 'ORT_NUM_THREADS', 'MKL_NUM_THREADS'):
        os.environ[name] = str(args.threads)

    import numpy as np
    import pypdfium2 as pdfium
    from rapidocr_onnxruntime import RapidOCR

    doc = pdfium.PdfDocument(args.book)
    page = doc[args.page - 1]
    width, height = page.get_size()
    side = max(width, height)
    scale = 1.4
    if args.max_side and side * scale > args.max_side:
        scale = args.max_side / side
    started = time.time()
    image = page.render(scale=scale).to_pil().convert('RGB')
    engine = RapidOCR()
    result, _ = engine(np.array(image))
    elapsed = time.time() - started
    blocks = len(result or [])
    print(f'max_side={args.max_side}  渲染 {image.size[0]}x{image.size[1]}  '
          f'{blocks} 块  {elapsed:.1f}s  峰值 {peak_mb():.0f} MB')
    return 0


if __name__ == '__main__':
    sys.exit(main())
