# -*- coding: utf-8 -*-
"""扫描版曲谱 PDF 的预处理：渲染 → OCR → 按 [解答] 标记定题号 → 裁接缝条。

为什么这样做（针对桑桐《250 首和声习题解答》这类书）：
- 纯扫描件、没有文字层，只能 OCR；
- 题号（1. 2. 3.）字号很小、紧贴谱表，OCR 基本认不出；
- 但 [解答] / [简释] 这两个标记 OCR 几乎 100% 认得出，而且每题恰好一个 [解答]；
- 书里题目编号是连续的，所以「数 [解答] 的个数」就能把题号定死；
- 跨页有三种：谱例跨页、简释文字跨页、题在上一页解答在下一页。
  与其硬判，不如把相邻页的「接缝条」裁出来一起给模型，让它自己判断。

这一层完全不联网，产出就是给云端模型看的「图 + 文字」。
"""
import json
import os
import re

import numpy as np

SECTION_RE = re.compile(r'\[\s*(解答|简释|提示|说明|分析)\s*\]')
PAGE_NO_RE = re.compile(r'^\s*[-—\s]*\d{1,3}\s*[-—\s]*$')
# 教材的层级标题：第四章 / 第二节 / 一、 / （二）
HEADING_RE = re.compile(r'^\s*(第[一二三四五六七八九十百]+[章节讲]|[一二三四五六七八九十]{1,3}、|（[一二三四五六七八九十]{1,3}）)')
EXAMPLE_RE = re.compile(r'例\s*(\d{1,3})(?:\s*[～~\-—]\s*(\d{1,3}))?')


def _safe_stem(path, limit=48):
    base = os.path.splitext(os.path.basename(path))[0]
    base = re.sub(r'[^\w\u4e00-\u9fff]+', '_', base).strip('_')
    return base[:limit] or 'book'


class Book:
    """一本扫描版曲谱。渲染、OCR、结果都按页缓存到磁盘。"""

    def __init__(self, path, cache_root, scale=2.0, max_side=2200):
        import pypdfium2 as pdfium
        self.path = os.path.abspath(path)
        self.scale = float(scale)
        # 长边上限：大页书（1561×2285 pt）按 scale 2.0 会渲染出 40 MB 位图，翻页会卡。
        self.max_side = max_side
        self.doc = pdfium.PdfDocument(self.path)
        self.pages = len(self.doc)
        self.stem = _safe_stem(self.path)
        self.cache = os.path.join(cache_root, 'pdf_cache')
        os.makedirs(self.cache, exist_ok=True)
        self._ocr = None
        self._images = {}
        self._blocks = {}

    # ---------------------------------------------------------------- 渲染
    def _png(self, number):
        return os.path.join(self.cache, f'{self.stem}_p{number:03d}.png')

    def _scale_for(self, number):
        """按长边封顶换算这一页该用的渲染倍率。"""
        try:
            width, height = self.doc[number - 1].get_size()
        except Exception:
            return self.scale
        side = max(width, height) or 1
        scale = self.scale
        if self.max_side and side * scale > self.max_side:
            scale = self.max_side / side
        return scale

    def render(self, number):
        if number in self._images:
            return self._images[number]
        if number < 1 or number > self.pages:
            raise IndexError(f'页码越界：{number}（共 {self.pages} 页）')
        path = self._png(number)
        from PIL import Image
        if os.path.isfile(path):
            image = Image.open(path).convert('RGB')
        else:
            image = self.doc[number - 1].render(scale=self._scale_for(number)).to_pil().convert('RGB')
            image.save(path)
        self._images[number] = image
        return image

    # ---------------------------------------------------------------- OCR
    def _engine(self):
        if self._ocr is None:
            from rapidocr_onnxruntime import RapidOCR
            self._ocr = RapidOCR()
        return self._ocr

    def blocks(self, number):
        """OCR 块：text / score / x / y / x2 / y2，按 (y, x) 排序，带缓存。"""
        if number in self._blocks:
            return self._blocks[number]
        path = os.path.join(self.cache, f'{self.stem}_p{number:03d}.ocr.json')
        if os.path.isfile(path):
            try:
                with open(path, encoding='utf-8') as fp:
                    data = json.load(fp)
                self._blocks[number] = data
                return data
            except Exception:
                pass
        image = self.render(number)
        result, _elapse = self._engine()(np.array(image))
        out = []
        for box, text, score in (result or []):
            xs = [point[0] for point in box]
            ys = [point[1] for point in box]
            out.append({
                'text': text,
                'score': round(float(score), 3),
                'x': int(min(xs)),
                'y': int(sum(ys) / 4),
                'x2': int(max(xs)),
                'y2': int(max(ys)),
            })
        out.sort(key=lambda block: (block['y'], block['x']))
        with open(path, 'w', encoding='utf-8') as fp:
            json.dump(out, fp, ensure_ascii=False)
        self._blocks[number] = out
        return out

    def text(self, number, drop_page_numbers=True):
        """整页文字（按行拼接），默认去掉页脚/页眉的纯数字页码。"""
        image = self.render(number)
        height = image.size[1]
        width = image.size[0]
        lines = []
        for block in self.blocks(number):
            if drop_page_numbers and PAGE_NO_RE.match(block['text']):
                continue
            if drop_page_numbers and block['y'] > height * 0.94 and block['x'] > width * 0.75:
                continue
            lines.append(block['text'])
        return '\n'.join(lines)

    def markers(self, number):
        """本页出现的 [解答] / [简释] 标记及其位置。"""
        out = []
        for block in self.blocks(number):
            match = SECTION_RE.search(block['text'])
            if match:
                out.append({'kind': match.group(1), 'y': block['y'], 'x': block['x'],
                            'text': block['text']})
        return out

    # ---------------------------------------------------------------- 定题号
    def local_items(self, number):
        """只按本页的 [解答] 标记编号（快，只 OCR 这一页）。

        题号（1. 2. 3.）字号太小、贴着谱表，OCR 认不准（会把「2.」和谱号粘成「2.3」）。
        而 [解答] 每题恰好一个、OCR 几乎必中，所以用它的个数和位置来定位题目。
        编号是「本页第几个题」，不是书里的编号 —— 书里编号要全书扫描才准（见 scan_items）。
        """
        out = []
        for index, marker in enumerate(self.markers(number), start=1):
            if marker['kind'] != '解答':
                continue
            out.append({'local_index': len(out) + 1, 'page': number, 'y': marker['y']})
        return out

    def scan_items(self, start_page=1, max_pages=None, workers=4):
        """从 start_page 开始数 [解答]，给每题书里的连续编号（慢，结果缓存）。

        整本 200 多页单进程要十几分钟，这里用线程池并行 OCR。
        """
        cache_path = os.path.join(self.cache, f'{self.stem}_items.json')
        if os.path.isfile(cache_path):
            try:
                with open(cache_path, encoding='utf-8') as fp:
                    data = json.load(fp)
                if data.get('pages') == self.pages:
                    return data
            except Exception:
                pass

        last = self.pages if max_pages is None else min(self.pages, start_page + max_pages - 1)
        numbers = list(range(start_page, last + 1))

        def markers_of(page):
            try:
                return page, self.markers(page)
            except Exception:
                return page, []

        results = {}
        if workers > 1:
            from concurrent.futures import ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=workers) as pool:
                for page, found in pool.map(markers_of, numbers):
                    results[page] = found
        else:
            for page in numbers:
                page, found = markers_of(page)
                results[page] = found

        items = []
        counter = 0
        for page in numbers:
            for marker in results.get(page, []):
                if marker['kind'] != '解答':
                    continue
                counter += 1
                items.append({'number': counter, 'page': page, 'y': marker['y']})
        data = {'start_page': start_page, 'pages': self.pages, 'items': items}
        try:
            with open(cache_path, 'w', encoding='utf-8') as fp:
                json.dump(data, fp, ensure_ascii=False)
        except Exception:
            pass
        return data

    def items_on_page(self, number, scan=None):
        """本页的题：有全书扫描结果就用书里编号，否则按页内顺序。

        统一返回 {'label', 'number', 'y'}，number 可能是 None（没扫描时）。
        """
        if scan:
            mine = [item for item in scan['items'] if item['page'] == number]
            if mine:
                return [{'label': f'第 {item["number"]} 题', 'number': item['number'],
                         'y': item['y']} for item in mine]
        return [{'label': f'本页第 {item["local_index"]} 处解答', 'number': None,
                 'y': item['y']} for item in self.local_items(number)]

    # ---------------------------------------------------------------- 裁接缝
    def strip_top(self, number, ratio=0.30):
        """某页顶部的一条（用于判断「本页是否承接上一页」）。"""
        image = self.render(number)
        height = image.size[1]
        return image.crop((0, 0, image.size[0], int(height * ratio)))

    def strip_bottom(self, number, ratio=0.30):
        image = self.render(number)
        height = image.size[1]
        return image.crop((0, int(height * (1 - ratio)), image.size[0], height))

    def ink_rows(self, number):
        """每行黑像素数，用来判断某段是不是「有谱有字」。"""
        image = self.render(number)
        gray = np.array(image.convert('L'))
        return (gray < 128).sum(axis=1)

    def ink_ratio(self, number, y0, y1):
        image = self.render(number)
        gray = np.array(image.convert('L'))
        height = gray.shape[0]
        y0 = max(0, min(height - 1, int(y0)))
        y1 = max(y0 + 1, min(height, int(y1)))
        band = gray[y0:y1] < 128
        return float(band.mean()) if band.size else 0.0

    # ---------------------------------------------------------------- 书籍类型
    def detect_kind(self):
        """判断这是哪种书，决定用哪套提示词。

        exercise = 习题册（每题 [解答]/[简释]，如《250 首》）
        textbook = 教材（大段讲解，有章节标题，混着谱例，如《和声学教程》）
        score    = 谱例集（正文几乎只有谱子，如《和声分析 351 例》）
        """
        if getattr(self, '_kind', None):
            return self._kind
        total = self.pages
        sample = [n for n in range(max(1, total // 10), min(total, total - 3),
                                   max(1, total // 12))][:12]
        answers = 0
        chars = 0
        for number in sample:
            try:
                blocks = self.blocks(number)
            except Exception:
                continue
            answers += sum(1 for block in blocks if SECTION_RE.search(block['text'])
                           and '解答' in block['text'])
            chars += sum(len(block['text']) for block in blocks)
        per_page_answers = answers / max(1, len(sample))
        per_page_chars = chars / max(1, len(sample))
        if per_page_answers >= 0.5:
            kind = 'exercise'
        elif per_page_chars >= 150:
            # 教材页常夹着大块谱例，文字量不像纯文字书那么多，阈值要低一些
            kind = 'textbook'
        else:
            kind = 'score'
        self._kind = kind
        self._kind_stats = {'answers/page': round(per_page_answers, 2),
                            'chars/page': int(per_page_chars), 'sampled': len(sample)}
        return kind

    def book_page(self, number):
        """书上印的页码。

        只在**页面边缘**找（页眉 6% / 页脚 6%），并且要求候选块基本只含数字，
        否则很容易把正文里的「1」「4」当成页码（实测《250 首》就踩过）。
        取不到就返回 None，宁可不给也不要给错。
        """
        cached = getattr(self, '_book_pages', None)
        if cached is None:
            cached = self._book_pages = {}
        if number in cached:
            return cached[number]

        height = self.render(number).size[1]
        blocks = sorted(self.blocks(number), key=lambda block: block['y'])
        edges = [b for b in blocks if b['y'] < height * 0.06 or b['y'] > height * 0.94]

        pure = re.compile(r'^[\s\-—.、()（）\[\]]*(\d{1,4})[\s\-—.、()（）\[\]]*$')
        header = re.compile(r'^(\d{1,4})\s*[\u4e00-\u9fff]')
        # 有的书页码在页眉末尾：「第七章副属和弦与副下属和弦（二）133」
        header_tail = re.compile(r'[\u4e00-\u9fff）)\]]\s*(\d{1,4})\s*$')

        def plausible(value):
            if not (1 <= value <= 9999):
                return False
            if value > number:
                return False
            return number - value <= 40

        value = None
        # 先找「只有数字」的块（最常见的页脚页码）
        for block in edges:
            text = block['text'].strip()
            if len(text) > 8:
                continue
            match = pure.match(text)
            if match and plausible(int(match.group(1))):
                value = int(match.group(1))
                break
        # 再找页眉里「76中国艺术教育大系…」这种
        if value is None:
            for block in edges:
                match = header.match(block['text'].strip())
                if match and plausible(int(match.group(1))):
                    value = int(match.group(1))
                    break
        if value is None:
            for block in edges:
                match = header_tail.search(block['text'].strip())
                if match and plausible(int(match.group(1))):
                    value = int(match.group(1))
                    break
        cached[number] = value
        return value

    # ---------------------------------------------------------------- 教材结构
    def headings(self, number):
        """章节标题行：第四章 / 一、 / （二）。"""
        out = []
        for block in self.blocks(number):
            text = block['text'].strip()
            if HEADING_RE.match(text) and 2 <= len(text) <= 40:
                out.append(text)
        return out

    def examples(self, number):
        """本页提到的谱例编号。"""
        numbers = []
        for block in self.blocks(number):
            for match in EXAMPLE_RE.finditer(block['text']):
                numbers.append(int(match.group(1)))
                if match.group(2):
                    numbers.append(int(match.group(2)))
        return sorted(set(numbers))[:8]

    # ---------------------------------------------------------------- 组包
    def _continuation_hints(self, number):
        """用 [解答]/[简释] 的先后顺序，直接判断跨页 —— 不靠模型猜。

        这本书的结构很固定：题 → [解答] → [简释]。所以：
          · 页首就是 [简释] → 这一题是上一页开始的；
          · 本页最后一个 [解答] 后面没有 [简释] → 这题还没讲完，延续到下一页。
        """
        markers = self.markers(number)
        answers = [item for item in markers if item['kind'] == '解答']
        notes = [item for item in markers if item['kind'] == '简释']
        hints = []
        if markers and markers[0]['kind'] == '简释':
            hints.append('【自动判断】本页最上方就是 [简释]：它的 [解答] 在上一页，'
                         '本页开头承接上一页。')
        if answers and not any(note['y'] > answers[-1]['y'] for note in notes):
            hints.append('【自动判断】本页最后一处 [解答] 之后没有 [简释]：'
                         '这一题的讲解尚未完成，内容延续到下一页。')
        elif answers:
            hints.append('【自动判断】本页最后一处 [解答] 之后有 [简释]：'
                         '这一题在本页内有讲解。')

        # 光看标记不够：有时 [简释] 的文字本身写到页脚，剩下的在下一页。
        # 判据是「下一页最上方是不是一段正文」——正文顶格出现，说明是接着说的。
        # 注意把「低音题」「第一单元」这种小标题排除掉：它们短、且常出现在页首。
        def is_body_text(block):
            text = (block.get('text') or '').strip()
            return len(text) >= 12 and not SECTION_RE.search(text)

        if number < self.pages:
            next_blocks = self.blocks(number + 1)
            next_height = self.render(number + 1).size[1]
            if next_blocks:
                first = sorted(next_blocks, key=lambda block: block['y'])[0]
                if first['y'] < next_height * 0.10 and is_body_text(first):
                    hints.append('【自动判断】下一页最上方是一段正文（不是题号或标记）：'
                                 '它接着说本页末尾的话，本页文字延续到下一页。')

        if number > 1:
            own = sorted(self.blocks(number), key=lambda block: block['y'])
            if own:
                first = own[0]
                own_height = self.render(number).size[1]
                if first['y'] < own_height * 0.10 and is_body_text(first):
                    hints.append('【自动判断】本页最上方是一段正文（不是题号或标记）：'
                                 '它是从上一页接着说下来的。')
        return hints

    def context_for_page(self, number, scan=None, kind=None, glossary_terms=None):
        """给云端模型准备的东西：本页整图 + 上下接缝条 + OCR 文字 + 结构提示。

        不硬判跨页，而是把接缝条一并交出：模型看得到相邻页的边缘，
        自然能判断「本页内容是否完整」。这样不会因为启发式误判而漏掉半个题。

        kind: exercise（习题册）/ textbook（教材）/ score（谱例集）
        """
        kind = kind or self.detect_kind()
        items = self.items_on_page(number, scan) if kind == 'exercise' else []
        image = self.render(number)
        width, height = image.size

        images = [(f'第 {number} 页（整页，本次分析的主体）', image)]
        notes = []
        if number > 1:
            images.append((f'第 {number - 1} 页底部接缝（只用于判断本页开头是否接着上一页）',
                           self.strip_bottom(number - 1)))
            notes.append('第二张是上一页底部接缝条；若本页开头内容不完整，用它补全。')
        if number < self.pages:
            images.append((f'第 {number + 1} 页顶部接缝（只用于判断本页结尾是否延续到下一页）',
                           self.strip_top(number + 1)))
            notes.append('最后一张是下一页顶部接缝条；若本页结尾内容不完整，用它补全。')

        printed = self.book_page(number)
        where = (f'【页码】本书第 {printed} 页（PDF 第 {number} 页）'
                 if printed else f'【页码】PDF 第 {number} 页')
        lines = [f'【第 {number} 页 OCR 文字】', where]
        if kind == 'exercise':
            if items:
                labels = '、'.join(item['label'] for item in items)
                lines.append(f'本页含：{labels}（按 [解答] 标记定位，位置见下）')
                for item in items:
                    lines.append(f'  · {item["label"]}：[解答] 出现在 y≈{item["y"]}')
            else:
                lines.append('本页没有 [解答] 标记（可能是目录、前言或纯文字页）')
        else:
            # 教材/谱例集：没有题号，用章节标题和谱例编号定位
            headings = self.headings(number)
            examples = self.examples(number)
            lines.append(f'【书籍类型】{"教材（大段讲解 + 谱例）" if kind == "textbook" else "谱例集"}')
            if headings:
                lines.append('【本页标题行】' + ' / '.join(headings[:4]))
            if examples:
                lines.append('【本页提到的谱例】例' + '、例'.join(str(n) for n in examples)
                             + '（OCR 识别，可能有个别错字）')
            if glossary_terms:
                lines.append('【本页出现的术语】' + '、'.join(glossary_terms))

        for hint in self._continuation_hints(number):
            lines.append(hint)
        lines.append('')
        lines.append(self.text(number))
        return {
            'page': number,
            'total_pages': self.pages,
            'kind': kind,
            'images': images,
            'notes': notes,
            'items': items,
            'size': (width, height),
            'text': '\n'.join(lines),
        }
