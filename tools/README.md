# tools —— 用你自己的书建术语库

仓库不附带任何书籍数据。这几个脚本是把**你自己合法持有**的书变成术语库的完整流程。

数据只写在本机 `data/` 下，是否分享由你决定。

## 流程

```
1. ingest_book.py     把 PDF 登记进 data/books.json（书名、路径、页数、前缀）
2. ocr_queue.py       列出还没 OCR 的页
3. ocr_book.py        逐页 OCR → data/pdf_cache/<前缀>_pNNN.ocr.json（本地模型，不上传）
4. lookup_terms.py    在书里找每个术语出现的句子 → data/glossary_evidence.json
5. book_definitions.py 让模型把句子归纳成「某书对某词的定义」→ data/glossary_book_defs.json
6. verify_glossary.py 核对：定义有没有编造、黑名单有没有漏
7. audit_glossary.py  体检：无释义、过短、单来源
```

## 术语表从哪来

`data/glossary_seed.json` 是术语清单，结构：

```json
{
  "terms": [
    {
      "term": "乐句",
      "aliases": ["phrase", "period"],
      "category": "曲式",
      "period": "通用",
      "definition": "你自己写的一句话",
      "state": "draft"
    }
  ]
}
```

`aliases` 很重要：英文书里只用 `phrase`，没有别名就检索不到。

没有这个文件也能用软件（术语库显示为空）。

## 常用命令

```bash
# OCR 一本书（本地，慢但免费）
python tools/ocr_queue.py --book "配器法"
python tools/ocr_book.py --workers 2 --threads 4

# 检索 + 抽定义（需要配好 data/llm.json）
python tools/lookup_terms.py --only 乐句,乐段
python tools/book_definitions.py --include-consensus --workers 2 --sleep 1 --only 乐句,乐段

# 只跑某几本书（书名包含关键词）
python tools/book_definitions.py --books "配器法,Reviser" --only 连弓,跳弓

# 体检
python tools/verify_glossary.py
python tools/audit_glossary.py
```

## 注意

- `book_definitions.py` 会消耗云端额度，先小批量试（`--only` 两三个词）
- 跑之前确认 `data/llm.json` 里 `reasoning_effort` 是 `low`，否则 GLM-5.3 会把 token 花在思考上
- 书页 OCR 只有本地模型，不上传；只有第 5 步会把**检索到的句子**发给模型
- 如果书是扫描件且歪得厉害，谱行检测可能漏，先在软件里翻一遍看效果
