# -*- coding: utf-8 -*-
"""让模型按「每一本书单独」写释义 —— 绝不合并不同教材的说法。

输入：data/glossary_evidence.json（每个术语在各本书里的原文片段）
输出：data/glossary_book_defs.json
      {术语: {书名: {definition, points[], pages[], ocr_issues}}}，带缓存

用法:
    python _unpack\\book_definitions.py --only 变和弦,经过音
    python _unpack\\book_definitions.py            # 全部有分歧的词
"""
import argparse
import json
import time
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, 'runtime'))
sys.path.insert(0, os.path.join(HERE, 'recovered'))

import explain  # noqa: E402

EVIDENCE = os.path.join(HERE, 'data', 'glossary_evidence.json')
BLACKLIST = os.path.join(HERE, 'data', 'glossary_blacklist.json')
SLEEP_SECONDS = 0.0
OUT = os.path.join(HERE, 'data', 'glossary_book_defs.json')
LLM_FILE = os.path.join(HERE, 'data', 'llm.json')

PROMPT = """你在读一本中文和声教材《{book}》。下面是从这本书 OCR 出来的、包含「{term}」的原文片段
（片段前的数字是书页码，OCR 可能有错字）。

原文片段：
{quotes}

任务：**只根据这些片段**，概括《{book}》这本书对「{term}」的理解。

硬性要求：
1. 不许引入其他教材、也不许写「通行定义」；这本书没说的就不要补。
2. definition 一句话：如果片段里有定义句，直接用它的意思；**如果没有定义句，就从这些片段归纳出
   「这本书怎么用它、把它归到哪一类」**，并在句末注明「（归纳自原文，非原书原话）」。
   只有片段完全没有信息时，才写「本书该段没有相关信息」。
3. points 写 2-4 条，每条一句短句，尽量带页码，例如「p270：把Ⅱ级音的属变和弦作为独立例题」。
4. pages 填你实际依据的页码。
5. 注意到 OCR 明显错字就写进 ocr_issues，没有就留空字符串。

只输出 JSON：
{{"definition": "...", "points": ["..."], "pages": [12, 47], "ocr_issues": ""}}
"""


def _same_book(a, b, width=14):
    """两个书名是否指同一本（登记时可能被截断）。"""
    a = (a or '').strip()
    b = (b or '').strip()
    if a == b:
        return True
    return a[:width] == b[:width] or a.startswith(b[:width]) or b.startswith(a[:width])

def load_json(path, default):
    try:
        with open(path, encoding='utf-8') as fp:
            return json.load(fp)
    except Exception:
        return default


def save_json(path, data):
    with open(path, 'w', encoding='utf-8') as fp:
        json.dump(data, fp, ensure_ascii=False, indent=1)


def call(config, book, term, quotes):
    text = PROMPT.format(book=book, term=term, quotes=quotes)
    messages = [{'role': 'user', 'content': text}]
    if SLEEP_SECONDS:
        time.sleep(SLEEP_SECONDS)
    reply, usage = explain.call_cloud(messages, config)
    reply = (reply or '').strip()
    # 去掉可能的 ```json 围栏
    if reply.startswith('```'):
        reply = reply.split('```')[1] if '```' in reply[3:] else reply
        reply = reply.replace('json', '', 1).strip() if reply.lower().startswith('json') else reply
    start = reply.find('{')
    end = reply.rfind('}')
    if start >= 0 and end > start:
        reply = reply[start:end + 1]
    try:
        return json.loads(reply), usage
    except Exception:
        return {'definition': reply[:400], 'points': [], 'pages': [],
                'ocr_issues': '解析失败'}, {}
    

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--only', default='')
    parser.add_argument('--include-consensus', action='store_true')
    parser.add_argument('--sleep', type=float, default=0.0,
                    help='每次调用之间等待秒数（免费模型限速时用）')
    parser.add_argument('--workers', type=int, default=3,
                        help='并发请求数（网络等待可以并行）')
    parser.add_argument('--books', default='',
                        help='只处理书名包含这些关键词的书（逗号分隔）')
    args = parser.parse_args()
    global SLEEP_SECONDS
    SLEEP_SECONDS = args.sleep
    only = [item.strip() for item in args.only.split(',') if item.strip()]

    config = explain.LlmConfig.load(LLM_FILE)
    if not config.usable():
        print('没有可用的模型配置:', LLM_FILE)
        return 2

    evidence = load_json(EVIDENCE, [])
    store = load_json(OUT, {})
    targets = []
    for item in evidence:
        if only and item['term'] not in only:
            continue
        if not only and item['scope'] != 'contested' and not args.include_consensus:
            continue
        targets.append(item)

    # 黑名单里的「术语 × 书」直接跳过（删过的错误不会再生成）
    blocked = set()
    try:
        from apply_blacklist import as_keys
        blocked = as_keys()
    except Exception:
        pass
    if blocked:
        print(f'黑名单：跳过 {len(blocked)} 个「术语 × 书」组合')

    # 先把所有「术语 × 书」的待办摊平
    book_filter = [item.strip() for item in (args.books or '').split(',') if item.strip()]
    tasks = []
    for item in targets:
        term = item['term']
        bucket = store.get(term) or {}
        for book, hits in item.get('by_book', {}).items():
            if book in bucket:
                continue
            if book_filter and not any(word in book for word in book_filter):
                continue
            if any(t == term and _same_book(b, book) for t, b in blocked):
                continue
            quotes = '\n'.join(f'[p{hit["page"]}] {hit["sentence"]}' for hit in hits[:3])
            if quotes.strip():
                tasks.append((term, book, quotes, hits))
    print(f'待处理 {len(tasks)} 条（{len(targets)} 个术语），模型 {config.llm_model}，'
          f'并发 {args.workers}')
    if not tasks:
        print('没有待办，已是最新。')
        return 0

    lock = threading.Lock()
    done = [0]
    failed = [0]

    def work(task):
        term, book, quotes, hits = task
        started = time.time()
        try:
            parsed, _usage = call(config, book, term, quotes)
        except Exception as exc:
            with lock:
                failed[0] += 1
                done[0] += 1
                print(f'  [{done[0]}/{len(tasks)}] {term} / {book} 失败: '
                      f'{type(exc).__name__}: {exc}')
            return
        with lock:
            store.setdefault(term, {})[book] = {
                'definition': parsed.get('definition', ''),
                'points': parsed.get('points', []),
                'pages': parsed.get('pages', []),
                'ocr_issues': parsed.get('ocr_issues', ''),
                'quotes': [hit['sentence'][:200] for hit in hits[:3]],
                'elapsed': round(time.time() - started, 1),
            }
            done[0] += 1
            print(f'  [{done[0]}/{len(tasks)}] {term} / {book}：'
                  f'{parsed.get("definition", "")[:52]}')
            save_json(OUT, store)

    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        list(pool.map(work, tasks))

    print(f'\n完成 {done[0] - failed[0]} 条，失败 {failed[0]} 条，写入 {OUT}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
