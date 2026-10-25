# -*- coding: utf-8 -*-
"""调用 MuseScore 命令行把 MusicXML 排成 PNG。

它比 music21 那条路更直接：music21 只是拼命令行参数，出了问题难排查。
注意两个坑：
  · 输出多页 PNG 时文件名会变成 `out-1.png`，要自己找回来
  · 默认按 A4/300dpi 出图，巨大；用 -T 裁白边、-r 降 DPI
"""
import glob
import os
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
DEPTH = os.path.dirname(HERE)          # _unpack 或便携包根目录


def flatten_voices(xml_path, out_path):
    """把每个声部内的多 voice 合并成和弦，去掉 <backup>。

    返回写出的路径；失败或不必要时返回原路径。
    """
    import os
    import re
    if not xml_path or not os.path.isfile(xml_path):
        return xml_path
    try:
        with open(xml_path, encoding='utf-8', errors='ignore') as handle:
            text = handle.read()
    except Exception:
        return xml_path
    voices = set(re.findall(r'<voice>([^<]*)</voice>', text))
    if len(voices) <= 1 and '<backup>' not in text:
        return xml_path                  # 本来就是单声部，不用动
    try:
        from music21 import converter, stream
    except Exception:
        return xml_path
    try:
        score = converter.parse(xml_path)
        merged = stream.Score()
        for part in score.parts:
            merged.insert(0, part.chordify())
        merged.write('musicxml', fp=out_path)
        return out_path if os.path.isfile(out_path) else xml_path
    except Exception:
        return xml_path


def normalize_stems(xml_path, out_path):
    """去掉 <stem> 元素，交给 MuseScore 按标准规则定符干方向。

    homr 输出的符干方向常常不对（所有音都朝上），MuseScore 会照着画，
    看起来就是"符头朝向乱七八糟"。去掉之后它会自动遵从惯例。
    """
    import re
    import shutil
    if not xml_path or not os.path.isfile(xml_path):
        return ''
    try:
        with open(xml_path, encoding='utf-8', errors='ignore') as handle:
            text = handle.read()
    except Exception:
        return ''
    cleaned = re.sub(r'\s*<stem[^>]*>.*?</stem>', '', text, flags=re.S)
    cleaned = re.sub(r'\s*<stem[^>]*/>', '', cleaned)
    if cleaned == text:
        return xml_path
    target = out_path or xml_path
    try:
        with open(target, 'w', encoding='utf-8') as handle:
            handle.write(cleaned)
        return target
    except Exception:
        return xml_path


def candidates():
    """MuseScore4.exe 可能在哪。"""
    out = [
        os.path.join(HERE, '..', 'musescore', 'bin', 'MuseScore4.exe'),
        os.path.join(DEPTH, 'musescore', 'bin', 'MuseScore4.exe'),
        os.path.join(DEPTH, 'vendor', 'musescore', 'bin', 'MuseScore4.exe'),
        r'C:\Program Files\MuseScore 4\bin\MuseScore4.exe',
        r'C:\Program Files\MuseScore 3\bin\MuseScore3.exe',
        os.path.expandvars(r'%LOCALAPPDATA%\Programs\MuseScore 4\bin\MuseScore4.exe'),
        os.path.expandvars(r'%PROGRAMFILES%\MuseScore 4\bin\MuseScore4.exe'),
    ]
    return [os.path.abspath(path) for path in out]


def find_musescore():
    for path in candidates():
        if os.path.isfile(path):
            return path
    return ''


def _stack_pdf_pages(pdf_path, out_png, dpi=110, gap=10):
    """把多页 PDF 竖向拼成一张 PNG。

    选中的谱行一多，MusicXML 就会排到第二页；只取第一页的 PNG 会让
    「下半部分被裁掉」，所以这里把所有页拼起来。
    """
    try:
        import pypdfium2 as pdfium
        from PIL import Image
    except Exception:
        return ''
    try:
        document = pdfium.PdfDocument(pdf_path)
        scale = max(0.5, dpi / 72.0)
        pages = []
        for page in document:
            pages.append(page.render(scale=scale).to_pil().convert('RGB'))
        document.close()
    except Exception:
        return ''
    if not pages:
        return ''
    width = max(page.width for page in pages)
    height = sum(page.height for page in pages) + gap * (len(pages) - 1)
    canvas = Image.new('RGB', (width, height), 'white')
    y = 0
    for page in pages:
        canvas.paste(page, (0, y))
        y += page.height + gap
    folder = os.path.dirname(out_png)
    if folder:
        os.makedirs(folder, exist_ok=True)
    canvas.save(out_png)
    return out_png


def _tighten_vertical(png_path, keep_gap=14, min_blank=40):
    """把图里成片的空白行压掉。

    MuseScore 会把谱行上下撑满整页，选了两行谱时中间会出现一大块空白，
    看起来像「断开」；这里把超过 min_blank 的空白带缩到 keep_gap。
    """
    try:
        from PIL import Image
    except Exception:
        return png_path
    try:
        image = Image.open(png_path).convert('L')
    except Exception:
        return png_path
    width, height = image.size
    try:
        import numpy as np
        pixels = np.array(image)
    except Exception:
        return png_path
    # 一行里 99.5% 以上是白就算空白行
    blank = (pixels > 240).mean(axis=1) > 0.995
    keep_rows = []
    run_start = None
    for index in range(height):
        if blank[index]:
            if run_start is None:
                run_start = index
            continue
        if run_start is not None:
            length = index - run_start
            if length > min_blank:
                # 只保留 keep_gap 行空白
                keep_rows.extend(range(run_start, run_start + keep_gap))
                keep_rows.extend(range(index - keep_gap // 2, index))
            else:
                keep_rows.extend(range(run_start, index))
            run_start = None
        keep_rows.append(index)
    if run_start is not None:
        keep_rows.extend(range(run_start, min(height, run_start + keep_gap)))
    if len(keep_rows) >= height or not keep_rows:
        return png_path
    try:
        cropped = Image.open(png_path).convert('RGB')
        strip = cropped.crop((0, 0, width, height))
        result = Image.new('RGB', (width, len(keep_rows)), 'white')
        y = 0
        for row in keep_rows:
            result.paste(strip.crop((0, row, width, row + 1)), (0, y))
            y += 1
        result.save(png_path)
    except Exception:
        return png_path
    return png_path


def render(xml_path, out_png, musescore='', dpi=110, trim=6, timeout=120,
           stem_mode='voices'):
    """把 MusicXML 排成 PNG。成功返回图片路径，失败返回 ''。"""
    exe = musescore or find_musescore()
    if not exe or not os.path.isfile(xml_path):
        return ''
    folder = os.path.dirname(out_png)
    if folder:
        os.makedirs(folder, exist_ok=True)
    stem = os.path.splitext(out_png)[0]
    for stale in glob.glob(stem + '*.png'):
        try:
            os.remove(stale)
        except OSError:
            pass
    # 先把多声部合并成和弦（符干方向才符合规范）。
    # xml_merge 自带逐音校验：合并结果对不上就放弃，退回原版渲染。
    source = xml_path
    try:
        import xml_merge
        merged_path = os.path.splitext(out_png)[0] + '.merged.musicxml'
        merged = xml_merge.merge_voices(xml_path, merged_path)
        if merged:
            source = merged
    except Exception:
        source = xml_path
    # 去掉原有的 <stem>
    clean_path = os.path.splitext(out_png)[0] + '.stem.musicxml'
    normalized = normalize_stems(source, clean_path)
    source = normalized or source

    if stem_mode == 'voices':
        # 保守做法：只按原有 <backup> 段落归并声部、写符干，不动时间轴
        # （重建时间轴的版本会把同时发声的音错开，已弃用）
        try:
            import voice_split
            merged_path = os.path.splitext(out_png)[0] + '.voices.musicxml'
            merged = voice_split.merge_file(source, merged_path)
            if merged:
                source = merged
        except Exception:
            pass
    else:
        try:
            import stem_rules
            ruled_path = os.path.splitext(out_png)[0] + '.ruled.musicxml'
            ruled = stem_rules.apply_stem_rules(source, ruled_path, mode=stem_mode)
            if ruled:
                source = ruled
        except Exception:
            pass
    command = [exe, '-o', out_png, '-T', str(trim), '-r', str(dpi), '-f']
    # 超长页面样式：选中的谱行多时不要翻到第二页（否则只导出第一页、下半被裁掉）
    style = os.path.join(os.path.dirname(HERE), 'data', 'tall_page.mss')
    if not os.path.isfile(style):
        style = os.path.join(HERE, 'data', 'tall_page.mss')
    if os.path.isfile(style):
        command += ['-S', style]
    command.append(source)
    creation = 0
    if os.name == 'nt':
        creation = 0x08000000            # CREATE_NO_WINDOW
    try:
        subprocess.run(command, timeout=timeout, creationflags=creation,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        return ''
    if os.path.isfile(out_png):
        return _tighten_vertical(out_png)
    produced = sorted(glob.glob(stem + '-*.png'))
    if len(produced) > 1:
        # 多页：只拿第一页会把下面的谱行裁掉，改成拼图
        try:
            from PIL import Image
            pages = [Image.open(path).convert('RGB') for path in produced]
            width = max(page.width for page in pages)
            height = sum(page.height for page in pages) + 10 * (len(pages) - 1)
            canvas = Image.new('RGB', (width, height), 'white')
            y = 0
            for page in pages:
                canvas.paste(page, (0, y))
                y += page.height + 10
            canvas.save(out_png)
            _tighten_vertical(out_png)
            for path in produced:
                try:
                    os.remove(path)
                except OSError:
                    pass
            return out_png
        except Exception:
            pass
    if produced:
        # MuseScore 有时还占着文件，稍等再改名，否则缓存永远是 -1 那个名字
        import time as _time
        for _ in range(12):
            try:
                os.replace(produced[0], out_png)
                return _tighten_vertical(out_png)
            except OSError:
                _time.sleep(0.2)
        return produced[0]
    return ''
