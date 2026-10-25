# -*- coding: utf-8 -*-
"""术语表：按书并列的术语查询 + 「原书定义优先」的格式化。

数据来源（都在 data/ 下）：
    glossary_seed.json        术语、scope（consensus/contested）、原书定义、answer_policy
    glossary_book_defs.json   每本书各自的释义（模型只读该书原文生成）

用法：
    g = Glossary('data')
    g.match('经过音和辅助音有什么区别')      -> [条目...]
    g.format(entries)                        -> 给模型看的文本块
    g.terms_on_page(page_text)               -> 本页出现的术语名
"""
import io
import json
import os


def _load(path, default):
    try:
        with io.open(path, encoding='utf-8') as fp:
            return json.load(fp)
    except Exception:
        return default


class Glossary:
    def __init__(self, data_dir):
        self.data_dir = data_dir
        seed = _load(os.path.join(data_dir, 'glossary_seed.json'), {})
        self.terms = seed.get('terms', [])
        self.policy = seed.get('answer_policy', {})
        self.renames = self.policy.get('term_rename', {})
        self.book_defs = _load(os.path.join(data_dir, 'glossary_book_defs.json'), {})
        evidence = _load(os.path.join(data_dir, 'glossary_evidence.json'), [])
        self.evidence = {item['term']: item for item in evidence}

    # ---------------------------------------------------------------- 查询
    def match(self, text, limit=3):
        """按术语名/别名在文本里做包含匹配，返回条目列表。"""
        if not text:
            return []
        found = []
        for item in self.terms:
            names = [item['term']] + list(item.get('aliases') or [])
            if any(name and name in text for name in names):
                found.append(item)
        # 长词优先（避免「和弦外音」和「外音」同时命中时顺序混乱）
        found.sort(key=lambda item: -len(item['term']))
        return found[:limit]

    def terms_on_page(self, page_text, limit=8):
        """本页里出现了哪些术语（用于教材页的「本页涉及」提示）。"""
        names = []
        for item in self.terms:
            alias = [item['term']] + list(item.get('aliases') or [])
            if any(name and name in page_text for name in alias):
                names.append(item['term'])
        return names[:limit]

    # ---------------------------------------------------------------- 格式化
    def format(self, entries, quote_only=False):
        """把条目渲染成给模型看的块：原书定义 > 分书释义 > 书上原句。

        三级兜底，避免「命中了术语却什么都注入不了」：
          1) 有原书定义 → 逐字引用
          2) 有分书释义 → 按书并列
          3) 只有检索到的原句 → 也照实给出（标注「非定义句，仅供引用」）
          4) 什么都没有 → 明确告诉模型「没有来源」，别让它自由发挥
        """
        blocks = []
        for item in entries:
            term = item['term']
            original = item.get('original')
            book_defs = {book: payload for book, payload in
                         (self.book_defs.get(term) or {}).items()
                         if not (original and book == original.get('book'))}
            quotes = (self.evidence.get(term) or {}).get('by_book') or {}

            lines = [f"【术语】{term}"]
            if item.get('scope') == 'contested':
                lines.append("※ 各教材口径不同：以下按书并列，**不要合并成一个定义**。")
                if item.get('dispute'):
                    lines.append(f"  分歧点：{item['dispute']}")

            if original:
                lines.append(f"★ 原书定义《{original['book']}》p{original.get('book_page')}："
                             f"「{original['text']}」")
                if original.get('types'):
                    lines.append(f"  该书列出的类别：{original['types']}")
            for extra in (item.get('original_extra') or []):
                lines.append(f"★ 原书定义《{extra['book']}》p{extra.get('book_page')}："
                             f"「{extra['text']}」")
            if item.get('general_definition'):
                general = item['general_definition']
                lines.append(f"※ 通用说法（{general.get('caveat') or '无引用来源'}）："
                             f"{general.get('text')}")
            if item.get('state') == 'unclear':
                lines.append(f"⚠ 待定：{item.get('note') or '这个词用户也不确定，只许引用原文，不要自行解释。'}")

            for book, payload in book_defs.items():
                pages = '、'.join(f'p{page}' for page in payload.get('pages') or []) or '—'
                lines.append(f"· 《{book}》{pages}：{payload.get('definition', '')}")
                for point in (payload.get('points') or [])[:2]:
                    lines.append(f"    - {point}")

            # 兜底：没有定义/释义时，直接把检索到的原句给出来
            if not original and not book_defs:
                rendered = False
                for book, hits in list(quotes.items())[:2]:
                    if not hits:
                        continue
                    rendered = True
                    lines.append(f"· 《{book}》书上的原句（不是定义句，只能引用，不要当成定义）：")
                    for hit in hits[:2]:
                        lines.append(f"    - p{hit['page']}：{hit['sentence'][:110]}")
                if not rendered:
                    lines.append("⚠ 本地教材里没有检索到这个词的原句。"
                                 "回答时请说明「书中没有找到依据」，不要自行编造定义。")
            blocks.append('\n'.join(lines))
        return '\n\n'.join(blocks)

    def rename_note(self, text):
        """用户要求统一的叫法（如 副属和弦 → 次属和弦）。"""
        hits = [(old, new) for old, new in self.renames.items() if old in (text or '')]
        if not hits:
            return ''
        return '\n'.join(f'【用词】本表统一用「{new}」，「{old}」是它的别名。' for old, new in hits)
