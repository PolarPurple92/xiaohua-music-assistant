# -*- coding: utf-8 -*-
"""术语编辑器：手动加一个词，也可以让模型先猜分类/别名/定义。

为什么需要：新用户拿到的是空术语库，不会去写 JSON。
"""
import io
import json
import os
import re
import threading

import ttkbootstrap as tb
from ttkbootstrap.constants import BOTH, LEFT, RIGHT, W, X, YES

CATEGORIES = ['曲式', '和声', '复调', '配器', '旋律', '节奏', '织体', '调性',
              '终止', '主题', '发展手法', '陈述类型', '外音', '和弦', '声部',
              '早期理论', '中国音乐', '爵士和声', '20世纪技法', '演奏法']
PERIODS = ['通用', '中世纪', '文艺复兴', '巴洛克', '前古典', '古典',
           '浪漫', '20世纪', '中国传统']

HERE = os.path.dirname(os.path.abspath(__file__))

PROMPT = """你是音乐理论术语库的编辑。给你一个术语名（可能带少量上下文），
请判断它的分类、时期、常见别名，并写一条简短定义。

只输出 JSON，不要任何解释或代码块标记：

{
  "term": "术语规范写法",
  "aliases": ["英文或其他叫法", "最多四个"],
  "category": "从这些里选一个：%(categories)s",
  "period": "从这些里选一个：%(periods)s",
  "definition": "40~90 字的定义，说清它是什么、用在哪",
  "confidence": "high / medium / low"
}

如果这个术语不属于音乐理论（比如是人名、书名、错别字），
把 category 填 "无法判断"，并在 definition 里说明原因。
"""


def load_seed(data_dir):
    path = os.path.join(data_dir, 'glossary_seed.json')
    if not os.path.isfile(path):
        return {}, path
    for encoding in ('utf-8-sig', 'utf-8'):
        try:
            with io.open(path, encoding=encoding) as handle:
                data = json.load(handle)
            if isinstance(data, dict):
                data.setdefault('terms', [])
                return data, path
        except Exception:
            continue
    return {'terms': []}, path


def save_term(data_dir, payload):
    """写入（或更新）一个术语。同名的直接覆盖可编辑字段。"""
    data, path = load_seed(data_dir)
    terms = data.setdefault('terms', [])
    term = (payload.get('term') or '').strip()
    if not term:
        return False, '术语名不能为空'
    for index, item in enumerate(terms):
        if item.get('term') == term:
            merged = dict(item)
            merged.update({key: payload[key] for key in
                           ('aliases', 'category', 'period', 'definition')
                           if key in payload})
            terms[index] = merged
            break
    else:
        terms.append({
            'term': term,
            'aliases': payload.get('aliases') or [],
            'category': payload.get('category') or '通用',
            'period': payload.get('period') or '通用',
            'definition': payload.get('definition') or '',
            'state': 'draft',
            'scope': 'consensus',
            'review': 'user-added',
        })
    os.makedirs(data_dir, exist_ok=True)
    with io.open(path, 'w', encoding='utf-8', newline='\n') as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
    return True, path


def _looks_like_json(text, term):
    """从模型输出里抠出 JSON（有时会裹一层代码块或前后废话）。"""
    cleaned = (text or '').strip()
    cleaned = re.sub(r'^```(?:json)?|```$', '', cleaned, flags=re.M).strip()
    match = re.search(r'\{.*\}', cleaned, re.S)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    if not data.get('definition') and not data.get('aliases'):
        return None
    return data


def suggest(term, config_path):
    """让云端模型猜分类/时期/别名/定义；返回 dict 或 (None, 错误原因)。"""
    import explain
    from settings import LLM_FILE  # noqa: F401  （保持路径来源一致）
    config_file = config_path or os.path.join(os.path.dirname(HERE), 'data', 'llm.json')
    config = explain.LlmConfig.load(config_file)
    if not config.usable():
        return None, '还没配置模型接口：点「模型」按钮填好再来'
    prompt = PROMPT % {'categories': '、'.join(CATEGORIES),
                       'periods': '、'.join(PERIODS)}
    messages = [{'role': 'system', 'content': prompt},
                {'role': 'user', 'content': '术语：%s' % term}]
    text, _usage = explain.call_cloud(messages, config, timeout=90)
    data = _looks_like_json(text, term)
    if not data:
        return None, '模型的回答不是可用的 JSON：%s' % (text or '')[:60]
    return data, ''


def open_editor(master, data_dir, term='', config_path='', on_saved=None):
    """弹出编辑窗口。term 非空时预填（可用来补全已有词）。"""
    top = tb.Toplevel(master)
    top.title('添加术语')
    top.attributes('-topmost', True)
    try:
        icon = os.path.join(HERE, 'icon.ico')
        if os.path.isfile(icon):
            top.iconbitmap(icon)
    except Exception:
        pass
    body = tb.Frame(top, padding=14)
    body.pack(fill=BOTH, expand=YES)

    tb.Label(body, text='填术语名，可以先让模型猜分类和定义，再自己改。',
             font=('Microsoft YaHei UI', 9), bootstyle='secondary').pack(anchor=W, pady=(0, 10))

    variables = {}

    def field(label, key, width=52):
        row = tb.Frame(body)
        row.pack(fill=X, pady=3)
        tb.Label(row, text=label, width=10, anchor=W,
                 font=('Microsoft YaHei UI', 9)).pack(side=LEFT)
        variable = tb.StringVar(value='')
        variables[key] = variable
        tb.Entry(row, textvariable=variable, width=width).pack(side=LEFT)
        return variable

    field('术语', 'term')
    field('别名', 'aliases')
    field('分类', 'category')
    field('时期', 'period')

    definition_row = tb.Frame(body)
    definition_row.pack(fill=X, pady=3)
    tb.Label(definition_row, text='定义', width=10, anchor=W,
             font=('Microsoft YaHei UI', 9)).pack(side=LEFT, anchor='n')
    definition = tb.Text(definition_row, height=5, width=52, wrap='word')
    definition.pack(side=LEFT)

    if term:
        variables['term'].set(term)

    status = tb.Label(body, text='', font=('Microsoft YaHei UI', 9),
                      bootstyle='secondary')
    status.pack(anchor=W, pady=(8, 0))

    def collect():
        aliases = [item.strip() for item in
                   re.split(r'[,，、]', variables['aliases'].get()) if item.strip()]
        return {
            'term': variables['term'].get().strip(),
            'aliases': aliases,
            'category': variables['category'].get().strip(),
            'period': variables['period'].get().strip(),
            'definition': definition.get('1.0', 'end').strip(),
        }

    def apply_suggestion():
        """同步调用模型：对话框很小，等几秒比线程+回调更可靠。"""
        name = variables['term'].get().strip()
        if not name:
            status.configure(text='先填术语名', bootstyle='danger')
            return
        status.configure(text='正在让模型判断…', bootstyle='secondary')
        top.config(cursor='watch')
        top.update_idletasks()
        try:
            data, error = suggest(name, config_path)
        except Exception as exc:
            data, error = None, '%s: %s' % (type(exc).__name__, str(exc)[:90])
        finally:
            top.config(cursor='')
        if not data:
            status.configure(text=error or '没拿到结果', bootstyle='danger')
            return
        variables['aliases'].set('，'.join(data.get('aliases') or []))
        variables['category'].set(data.get('category') or '')
        variables['period'].set(data.get('period') or '')
        definition.delete('1.0', 'end')
        definition.insert('1.0', data.get('definition') or '')
        note = data.get('confidence') or ''
        status.configure(text='已填入建议（可信度 %s），请核对后再保存' % note,
                         bootstyle='success')

    def do_save():
        payload = collect()
        ok, message = save_term(data_dir, payload)
        if not ok:
            status.configure(text=message, bootstyle='danger')
            return
        status.configure(text='已保存到 %s' % message, bootstyle='success')
        if on_saved:
            try:
                on_saved()
            except Exception:
                pass
        top.after(600, top.destroy)

    buttons = tb.Frame(body)
    buttons.pack(fill=X, pady=(12, 0))
    tb.Button(buttons, text='保存', bootstyle='primary',
              command=do_save).pack(side=RIGHT)
    tb.Button(buttons, text='让模型填', bootstyle='info-outline',
              command=apply_suggestion).pack(side=RIGHT, padx=(0, 8))
    tb.Button(buttons, text='关闭', bootstyle='secondary-outline',
              command=top.destroy).pack(side=RIGHT, padx=(0, 8))
    top.transient(master)
    return top
