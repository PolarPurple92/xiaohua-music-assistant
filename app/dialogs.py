# -*- coding: utf-8 -*-
"""两个对话框：依赖检查、模型接口设置。

不用 ttkbootstrap 的 Messagebox（它的返回值在不同版本里不一致，
点了「打开下载页」常常什么也没发生），这里自己搭 Toplevel。
"""
import io
import json
import os
import webbrowser

import ttkbootstrap as tb
from ttkbootstrap.constants import (BOTH, END, LEFT, RIGHT, W, X, YES)

HERE = os.path.dirname(os.path.abspath(__file__))


def _apply_icon(window):
    """对话框也用自己的图标，否则任务栏上是一堆 python 图标。"""
    try:
        icon = os.path.join(HERE, 'icon.ico')
        if os.path.isfile(icon):
            window.iconbitmap(icon)
    except Exception:
        pass


# ---------------------------------------------------------------- 依赖检查
def show_deps_dialog(master, rows, title='依赖检查'):
    """rows: [{label, ok, detail, url}]。每个缺失项旁边一个「打开」按钮。"""
    top = tb.Toplevel(master)
    top.title(title)
    _apply_icon(top)
    top.attributes('-topmost', True)
    body = tb.Frame(top, padding=14)
    body.pack(fill=BOTH, expand=YES)

    tb.Label(body, text='本程序不打包 homr 与 MuseScore，请用官方渠道自行安装。',
             font=('Microsoft YaHei UI', 10)).pack(anchor=W, pady=(0, 10))

    grid = tb.Frame(body)
    grid.pack(fill=X)

    missing = []
    for index, row in enumerate(rows):
        mark = '✓' if row.get('ok') else '✗'
        color = 'success' if row.get('ok') else 'danger'
        tb.Label(grid, text=mark, bootstyle=color,
                 font=('Microsoft YaHei UI', 11, 'bold')).grid(
            row=index, column=0, sticky=W, padx=(0, 8), pady=3)
        tb.Label(grid, text=row.get('label', '')).grid(
            row=index, column=1, sticky=W, pady=3)
        detail = row.get('detail') or ''
        if len(detail) > 46:
            detail = '…' + detail[-44:]
        tb.Label(grid, text=detail, bootstyle='secondary',
                 font=('Microsoft YaHei UI', 9)).grid(
            row=index, column=2, sticky=W, padx=(10, 10), pady=3)
        if not row.get('ok') and row.get('url'):
            missing.append(row)
            tb.Button(grid, text='打开', width=6, bootstyle='secondary-outline',
                      command=lambda url=row['url']: webbrowser.open(url)).grid(
                row=index, column=3, sticky=W, pady=3)
        else:
            tb.Label(grid, text='', width=6).grid(row=index, column=3)

    hint = tb.Label(body, text='装完后重启本程序，「依赖」里会变成 ✓。' if missing
                    else '全部就绪。', bootstyle='secondary',
                    font=('Microsoft YaHei UI', 9))
    hint.pack(anchor=W, pady=(12, 0))

    buttons = tb.Frame(body)
    buttons.pack(fill=X, pady=(14, 0))
    if missing:
        tb.Button(buttons, text='全部打开', bootstyle='primary',
                  command=lambda: [webbrowser.open(row['url']) for row in missing]
                  ).pack(side=RIGHT)
    tb.Button(buttons, text='关闭', bootstyle='secondary-outline',
              command=top.destroy).pack(side=RIGHT, padx=(0, 8))
    top.transient(master)
    return top


# ---------------------------------------------------------------- 模型接口
FIELDS = (
    ('base_url', '接口地址', 'https://open.bigmodel.cn/api/paas/v4'),
    ('model', '模型名', 'glm-5.3-flash'),
    ('api_key', 'API Key', ''),
    ('max_tokens', '最大输出 token', '9000'),
    ('reasoning_effort', '推理强度（low/high/max）', 'low'),
)

PRESETS = (
    ('智谱 GLM', 'https://open.bigmodel.cn/api/paas/v4', 'glm-5.3-flash'),
    ('OpenAI', 'https://api.openai.com/v1', 'gpt-4o'),
    ('DeepSeek', 'https://api.deepseek.com/v1', 'deepseek-chat'),
    ('本地 Ollama', 'http://127.0.0.1:11434/v1', 'qwen2.5vl'),
)


def load_config(path):
    data = {}
    if path and os.path.isfile(path):
        for encoding in ('utf-8-sig', 'utf-8'):
            try:
                with io.open(path, encoding=encoding) as handle:
                    data = json.load(handle)
                break
            except Exception:
                data = {}
    return data if isinstance(data, dict) else {}


def save_config(path, data):
    folder = os.path.dirname(path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    with io.open(path, 'w', encoding='utf-8', newline='\n') as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)


def show_llm_dialog(master, config_path, on_saved=None):
    """让用户自己填接口，任何 OpenAI 兼容服务都行。"""
    data = load_config(config_path)
    top = tb.Toplevel(master)
    top.title('分析用的模型接口')
    _apply_icon(top)
    top.attributes('-topmost', True)
    body = tb.Frame(top, padding=14)
    body.pack(fill=BOTH, expand=YES)

    tb.Label(body, text='「分析本页」会把当前页的图片和 OCR 文字发到这个接口。\n'
                        '不填也能用：识别、播放、术语都是本地的。',
             font=('Microsoft YaHei UI', 9), bootstyle='secondary',
             justify=LEFT).pack(anchor=W, pady=(0, 10))

    preset_row = tb.Frame(body)
    preset_row.pack(fill=X, pady=(0, 10))
    tb.Label(preset_row, text='预设：', font=('Microsoft YaHei UI', 9)).pack(side=LEFT)

    entries = {}
    variables = {}
    for key, label, example in FIELDS:
        row = tb.Frame(body)
        row.pack(fill=X, pady=3)
        tb.Label(row, text=label, width=20, anchor=W,
                 font=('Microsoft YaHei UI', 9)).pack(side=LEFT)
        variable = tb.StringVar(value=str(data.get(key, '') or ''))
        variables[key] = variable
        if key == 'api_key':
            entry = tb.Entry(row, textvariable=variable, show='•', width=52)
        else:
            entry = tb.Entry(row, textvariable=variable, width=52)
        entry.pack(side=LEFT)
        entries[key] = entry
        if example and not data.get(key):
            variable.set('')

    def apply_preset(url, model):
        variables['base_url'].set(url)
        variables['model'].set(model)
        if 'reasoning_effort' in variables:
            variables['reasoning_effort'].set('low')

    for name, url, model in PRESETS:
        tb.Button(preset_row, text=name, bootstyle='secondary-outline',
                  command=lambda u=url, m=model: apply_preset(u, m)).pack(
            side=LEFT, padx=(0, 6))

    status = tb.Label(body, text='', font=('Microsoft YaHei UI', 9),
                      bootstyle='secondary')
    status.pack(anchor=W, pady=(10, 0))

    def collect():
        out = dict(data)
        for key, _label, _example in FIELDS:
            value = variables[key].get().strip()
            if key == 'max_tokens':
                try:
                    out[key] = int(value or 9000)
                except ValueError:
                    out[key] = 9000
            elif value:
                out[key] = value
            elif key in out:
                out.pop(key, None)
        return out

    def do_save():
        payload = collect()
        save_config(config_path, payload)
        status.configure(text='已保存到 %s' % config_path, bootstyle='success')
        if on_saved:
            try:
                on_saved(payload)
            except Exception:
                pass

    def do_test():
        payload = collect()
        if not payload.get('base_url') or not payload.get('model'):
            status.configure(text='至少填接口地址和模型名', bootstyle='danger')
            return
        status.configure(text='正在测试…', bootstyle='secondary')
        top.update_idletasks()

        def worker():
            try:
                import explain
                config = explain.LlmConfig(
                    base_url=payload.get('base_url', ''),
                    model=payload.get('model', ''),
                    api_key=payload.get('api_key', ''),
                    max_tokens=64,
                    temperature=0.1,
                    reasoning_effort=payload.get('reasoning_effort', 'low'))
                messages = [{'role': 'user', 'content': '只回复两个字：可用'}]
                text, _usage = explain.call_cloud(messages, config, timeout=60)
                reply = (text or '').strip()[:40] or '（空响应）'
                top.after(0, lambda: status.configure(
                    text='连接成功，模型回复：%s' % reply, bootstyle='success'))
            except Exception as exc:
                message = '%s: %s' % (type(exc).__name__, str(exc)[:120])
                top.after(0, lambda: status.configure(
                    text='连接失败：' + message, bootstyle='danger'))

        import threading
        threading.Thread(target=worker, daemon=True).start()

    buttons = tb.Frame(body)
    buttons.pack(fill=X, pady=(14, 0))
    tb.Button(buttons, text='保存', bootstyle='primary',
              command=do_save).pack(side=RIGHT)
    tb.Button(buttons, text='测试连接', bootstyle='info-outline',
              command=do_test).pack(side=RIGHT, padx=(0, 8))
    tb.Button(buttons, text='关闭', bootstyle='secondary-outline',
              command=top.destroy).pack(side=RIGHT, padx=(0, 8))
    top.transient(master)
    return top
