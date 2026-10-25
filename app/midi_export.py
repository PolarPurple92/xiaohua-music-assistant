# -*- coding: utf-8 -*-
"""导出选中谱行/片段的 MIDI：连位置信息一起存下来。

文件名形如：`和声学教程_p076_行2_20261025-1712.mid`
同名 `.txt` 里记录书名、页、谱行位置、时间戳、原始框坐标。
"""
import io
import json
import os
import shutil
import time


def meta_path(midi_path):
    return os.path.splitext(midi_path)[0] + '.txt'


def suggest_name(book_title, page, box, printed_page=''):
    """给「另存为」对话框用的默认文件名。"""
    title = (book_title or 'book').replace(os.sep, '_').strip()[:40]
    stamp = time.strftime('%Y%m%d-%H%M')
    where = ''
    if printed_page and str(printed_page) != str(page):
        where = 'p%s_PDF%s' % (printed_page, page)
    else:
        where = 'p%s' % page
    band = ''
    if box:
        band = '_y%d-%d' % (int(box[1]), int(box[3]))
    return '%s_%s%s_%s.mid' % (title, where, band, stamp)


def export(midi_path, target, book_title='', page=0, printed_page='',
           box=None, crop_png='', extra=None):
    """把识别好的 MIDI 复制到 target，并写一个同名 .txt 说明。返回说明文件路径。"""
    if not midi_path or not os.path.isfile(midi_path):
        return ''
    os.makedirs(os.path.dirname(os.path.abspath(target)) or '.', exist_ok=True)
    shutil.copy2(midi_path, target)
    info = {
        'book': book_title,
        'pdf_page': page,
        'printed_page': printed_page,
        'box': [int(value) for value in box] if box else None,
        'saved_at': time.strftime('%Y-%m-%d %H:%M:%S'),
        'midi': os.path.basename(target),
        'source_midi': os.path.basename(midi_path),
    }
    if extra:
        info.update(extra)
    note = meta_path(target)
    with io.open(note, 'w', encoding='utf-8', newline='\n') as handle:
        handle.write('谱行摘录\n')
        handle.write('========\n\n')
        if book_title:
            handle.write('书名：%s\n' % book_title)
        handle.write('PDF 页：第 %s 页\n' % page)
        if printed_page and str(printed_page) != str(page):
            handle.write('书上页码：%s\n' % printed_page)
        if box:
            handle.write('位置（图片坐标）：x %d-%d，y %d-%d\n'
                         % (int(box[0]), int(box[2]), int(box[1]), int(box[3])))
        handle.write('导出时间：%s\n' % info['saved_at'])
        if extra:
            for key, value in extra.items():
                handle.write('%s：%s\n' % (key, value))
        handle.write('\n--- 机器可读 ---\n')
        handle.write(json.dumps(info, ensure_ascii=False, indent=2) + '\n')
    if crop_png and os.path.isfile(crop_png):
        try:
            shutil.copy2(crop_png, os.path.splitext(target)[0] + '_原图.png')
        except Exception:
            pass
    return note
