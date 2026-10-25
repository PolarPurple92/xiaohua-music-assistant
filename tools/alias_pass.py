# -*- coding: utf-8 -*-
"""别名补全：书里查不到的术语，换几种叫法再试一次。

中文乐理同一概念常有 2-3 种写法（导七和弦 / 导音七和弦、固定音型 / 顽固音型）。
命中后把新叫法写进 aliases，并把找到的原句补进证据，这样之后提问就能命中了。

用法: python _unpack\\alias_pass.py [--dry]
"""
import argparse
import io
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, 'runtime'))
sys.path.insert(0, HERE)

import books as registry  # noqa: E402
import lookup_terms as lt  # noqa: E402

SEED = os.path.join(HERE, 'data', 'glossary_seed.json')
EVIDENCE = os.path.join(HERE, 'data', 'glossary_evidence.json')

# 人工整理的常见异名（只写「书里可能出现的写法」）
VARIANTS = {
    '导七和弦': ['导音七和弦', '导七', '导音上的七和弦'],
    '卡农': ['卡农曲', '卡农式', '轮唱'],
    '固定音型': ['固定低音音型', '固定低音', '顽固音型'],
    '回音': ['回转音', '回音音型'],
    '声部交叉': ['声部交错', '声部间交叉', '与低音交叉'],
    '声部超越': ['声部越过', '超越进行'],
    '跳进辅助音': ['跳进助音'],
    '倚音': ['倚音式', '强位外音'],
    '阻碍终止': ['意外终止', '规避终止', '阻碍进行'],
    '持续音': ['持续低音', '顽固低音'],
    '模进': ['模进式'],
    '调式交替': ['交替和弦', '同主音交替'],
    '变和弦': ['变音和弦', '变化和弦'],
    '副属和弦': ['次属和弦', '副属'],
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry', action='store_true')
    args = parser.parse_args()

    with io.open(SEED, encoding='utf-8') as fp:
        seed = json.load(fp)
    with io.open(EVIDENCE, encoding='utf-8') as fp:
        evidence = json.load(fp)
    by_term = {item['term']: item for item in evidence}

    corpus = []
    for name, prefix in registry.book_pairs():
        sentences = lt.load_book(prefix)
        print(f'  {name}: {len(sentences)} 句')
        corpus.append((name, sentences))

    rescued = 0
    for item in seed['terms']:
        term = item['term']
        current = by_term.get(term) or {}
        if current.get('by_book'):
            continue                      # 已经有证据，不折腾
        variants = [v for v in VARIANTS.get(term, []) if v != term]
        if not variants:
            continue
        found = {}
        for name, sentences in corpus:
            hits = []
            for pdf_page, book_page, sentence in sentences:
                if not any(variant in sentence for variant in variants):
                    continue
                if lt.is_toc_like(sentence):
                    continue
                score = max(lt.score_sentence(sentence, variant) for variant in variants
                            if variant in sentence)
                hits.append({'sentence': sentence[:280], 'page': book_page,
                             'pdf_page': pdf_page, 'score': score})
            if hits:
                hits.sort(key=lambda entry: -entry['score'])
                found[name] = hits[:3]

        if not found:
            print(f'  {term}: 变体也没找到（{"、".join(variants)}）')
            continue

        used = sorted({variant for name, sentences in corpus for variant in variants
                       if any(variant in sentence for _p, _b, sentence in sentences)})
        print(f'  {term}: 用「{"、".join(used)}」在 '
              f'{len(found)} 本书里找到 {sum(len(v) for v in found.values())} 条')
        for name, hits in found.items():
            print(f'      {name} p{hits[0]["page"]}：{hits[0]["sentence"][:70]}')

        if args.dry:
            continue
        # 把新叫法写进别名
        aliases = item.get('aliases') or []
        for variant in used:
            if variant not in aliases:
                aliases.append(variant)
        item['aliases'] = aliases
        # 补证据
        entry = by_term.get(term)
        if entry is None:
            entry = {'term': term, 'aliases': aliases, 'category': item.get('category', ''),
                     'scope': item.get('scope', 'consensus'),
                     'definition': item.get('definition', ''),
                     'dispute': item.get('dispute', ''), 'pitfall': item.get('pitfall', ''),
                     'by_book': {}, 'evidence': [], 'presentation': ''}
            evidence.append(entry)
            by_term[term] = entry
        entry['aliases'] = aliases
        for name, hits in found.items():
            entry.setdefault('by_book', {})[name] = hits
            entry.setdefault('evidence', []).extend(hits)
        rescued += 1

    if args.dry:
        print(f'\n（dry-run）可救回 {rescued} 个术语')
        return 0

    with io.open(SEED, 'w', encoding='utf-8', newline='\n') as fp:
        json.dump(seed, fp, ensure_ascii=False, indent=2)
    with io.open(EVIDENCE, 'w', encoding='utf-8', newline='\n') as fp:
        json.dump(evidence, fp, ensure_ascii=False, indent=1)
    print(f'\n救回 {rescued} 个术语，已写入 seed 与 evidence')
    return 0


if __name__ == '__main__':
    sys.exit(main())
