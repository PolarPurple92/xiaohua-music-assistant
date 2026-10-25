# -*- coding: utf-8 -*-
"""把「一页 PDF 的图 + OCR 文字」交给云端视觉模型，换回中文讲解。

设计要点：
- 走 OpenAI 兼容协议（/chat/completions + image_url），换服务商只改 base_url/model；
- 图以 base64 data URL 内联，不依赖外链；
- 结果按「书 + 页」缓存成 md，同一页不重复花钱；
- `dry_run=True` 时不发请求，只回报将要发送的内容（图片数、字节数、提示词），
  方便先看清楚再决定。
"""
import base64
import io
import json
import os
import time


TEMPLATE = {
    'base_url': 'https://open.bigmodel.cn/api/paas/v4',
    'model': 'glm-4.6v',
    'api_key': '',
    'max_tokens': 9000,
    'temperature': 0.2,
}


def ensure_config_template(path):
    """配置文件不存在时写一份模板，用户只要填 key 就能用。"""
    if os.path.isfile(path):
        return False
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w', encoding='utf-8') as fp:
            json.dump(TEMPLATE, fp, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False


def web_search(query, config, limit=4, timeout=25):
    """调用智谱的 Web Search API。返回 [{'title','link','content'}]，失败返回 []。

    其它厂商的兼容接口不一定有 /web_search，失败就当没有联网能力。
    """
    import requests
    base = (getattr(config, 'llm_base_url', '') or '').rstrip('/')
    key = getattr(config, 'llm_api_key', '') or ''
    if not base or not key:
        return []
    try:
        response = requests.post(
            base + '/web_search',
            json={'search_engine': 'search_std', 'search_query': str(query)[:100]},
            headers={'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json'},
            timeout=timeout)
        if response.status_code >= 400:
            return []
        data = response.json()
    except Exception:
        return []
    results = []
    for item in (data.get('search_result') or [])[:limit]:
        results.append({
            'title': (item.get('title') or '').strip(),
            'link': (item.get('link') or '').strip(),
            'content': (item.get('content') or '').strip()[:300],
        })
    return [item for item in results if item['content']]


class LlmConfig:
    """云端模型配置：环境变量优先，其次 data/llm.json（把 key 放那儿，别贴聊天里）。"""

    def __init__(self, base_url='', model='', api_key='',
                 max_tokens=4000, temperature=0.2, reasoning_effort='low'):
        self.llm_base_url = base_url
        self.llm_model = model
        self.llm_api_key = api_key
        self.max_tokens = int(max_tokens or 4000)
        self.temperature = float(temperature if temperature is not None else 0.2)
        self.reasoning_effort = str(reasoning_effort or 'low')

    @classmethod
    def load(cls, config_file=''):
        data = {}
        if config_file and os.path.isfile(config_file):
            # utf-8-sig：PowerShell 的 Set-Content -Encoding UTF8 会带 BOM，直接 json.load 会崩
            for encoding in ('utf-8-sig', 'utf-8'):
                try:
                    with open(config_file, encoding=encoding) as fp:
                        data = json.load(fp)
                    break
                except Exception:
                    data = {}
        return cls(
            base_url=os.environ.get('XIAOHUA_LLM_BASE_URL') or data.get('base_url', ''),
            model=os.environ.get('XIAOHUA_LLM_MODEL') or data.get('model', ''),
            api_key=os.environ.get('XIAOHUA_LLM_API_KEY') or data.get('api_key', ''),
            max_tokens=data.get('max_tokens', 4000),
            temperature=data.get('temperature', 0.2),
            reasoning_effort=os.environ.get('XIAOHUA_LLM_REASONING') or data.get('reasoning_effort', 'low'),
        )

    def ready(self):
        return bool(self.llm_base_url and self.llm_model)

    def usable(self):
        """能不能真的发请求：本地接口可以没 key，云端接口必须有。"""
        if not self.ready():
            return False
        if self.llm_api_key:
            return True
        lowered = self.llm_base_url.lower()
        return 'localhost' in lowered or '127.0.0.1' in lowered or '0.0.0.0' in lowered

    def missing(self):
        parts = []
        if not self.llm_base_url:
            parts.append('base_url')
        if not self.llm_model:
            parts.append('model')
        if not self.llm_api_key and 'localhost' not in self.llm_base_url.lower() \
                and '127.0.0.1' not in self.llm_base_url:
            parts.append('api_key')
        return parts

    def describe(self):
        if not self.llm_base_url:
            return '未配置（在 data/llm.json 里填 base_url / model / api_key）'
        return f'{self.llm_model} @ {self.llm_base_url}' + (
            '' if self.llm_api_key else '（没有 key）')

SYSTEM_PROMPT = """你是一位给「读谱吃力的人」讲谱的音乐理论老师。

你会看到一页扫描版乐谱书：整页图、上一页底部接缝条、下一页顶部接缝条，以及这一页的 OCR 文字。
图里的谱例是四声部和声写作，谱表下方通常标有调性和罗马数字级数（如 G: I IV V）。

请遵守：
1. 先判断本页内容是否完整。接缝条只用于判断「开头是否接着上一页」「结尾是否延续到下一页」，
   不要把它当成另一个题。如果内容跨页，就说明跨页的部分是什么，不要硬凑一句结论。
2. 逐题讲解。每题的顺序是：题目（数字低音）→ [解答]（可能有多版 (a)(b)(c)）→ [简释]。
   **重要**：文字里出现的「本页第 1 处」这类编号，是我们按 [解答] 出现顺序自动编的，
   **不是书上印的题号**。请以谱面上印刷的题号（如「4.」）为准，并在每节开头注明
   「谱面题号：4」，如果看不清就写「谱面题号看不清」。
3. 讲什么：
   - 调性与调性布局（是否离调、转调）
   - 和弦进行：尽量给罗马数字，并说清功能（主、属、下属、副属…）
   - 低音走向、声部排列（密集/开放）、声部进行是否平稳
   - 外音（经过音、辅助音、留音、先现音、换音）
   - 终止式类型与位置（小节号如果用不了就用「第几个小节」）
   - 这一题想训练什么（比如「练习属七的准备」「练习外音的处理」）
4. 只讲谱面上能看到的。看不清、OCR 有矛盾、或你不确定的地方，直接说「这里看不清/不确定」。
   绝对不要编造题号、调性或者小节数。
5. 术语用中文，必要时保留意大利语/英文原名（如 appoggiatura 倚音）。
6. 输出 Markdown，结构固定：
   ## 本页概览
   （2-3 句：这页在讲什么，有几题，是否跨页）
   ## 逐题讲解
   ### 本页第 1 题
   （分小节讲，不要一次一大段）
   ## 需要注意的坑
   （这本书体系里容易搞错的点、或 OCR 可能出错的地方）
"""

TEXTBOOK_PROMPT = """你是一位给「读谱吃力的人」讲教材的音乐理论老师。

你会看到：一页扫描版和声教材（整页图）、上一页底部接缝条、下一页顶部接缝条，以及这一页的 OCR 文字。
这一页可能是大段讲解，也可能夹着谱例（例号形如「例6～78」）——**它没有 1、2、3 这样的题号**，
也不要去找「[解答]」「[简释]」这类标记。

请按这个结构输出：

## 本页在讲什么
（2-3 句：这一页的主题、它在整章里的位置；若开头是承接上一页，点明）

## 概念与规则
（逐条列出本页的规则/定义/分类；每条尽量先引原文，再用自己的话解释一遍；
  括号里标出依据的位置，如「（p69）」或「（例62）」）

## 谱例说明
（本页的谱例各自在演示哪条规则；看不清就说看不清）

## 需要注意
（这本书体系里的易错点，或 OCR 可能出错的地方）

硬性要求：
1. 只讲本页内容。看不清就说看不清，**不要编造章节号、谱例号、音高**。
2. 引用原文优先：重要定义先用书上的原话（加引号），再解释。
3. 术语用中文，必要时保留意大利语/英文原名（如 appoggiatura 倚音）。
"""

USER_TEMPLATE = """这是《{book}》第 {page} 页（全书 {total} 页）。

{notes}

{text}

请按系统提示的格式分析这一页。
"""


def _image_to_data_url(image, max_side=1600, quality=88):
    """PIL 图 → data URL。长边超过 max_side 就等比缩小，省 token。"""
    from PIL import Image
    if image.mode not in ('RGB', 'L'):
        image = image.convert('RGB')
    width, height = image.size
    longest = max(width, height)
    if longest > max_side:
        ratio = max_side / float(longest)
        image = image.resize((max(1, int(width * ratio)), max(1, int(height * ratio))),
                             Image.LANCZOS)
    buffer = io.BytesIO()
    image.save(buffer, format='JPEG', quality=quality, optimize=True)
    raw = buffer.getvalue()
    return 'data:image/jpeg;base64,' + base64.b64encode(raw).decode('ascii'), len(raw)


def build_messages(package, book_title, kind='exercise'):
    """把 context_for_page 的产出变成 chat/completions 的 messages。

    kind 决定用哪套提示词：习题册（题目→解答→简释）还是教材（讲解+谱例）。
    """
    system_prompt = TEXTBOOK_PROMPT if kind != 'exercise' else SYSTEM_PROMPT
    content = [{'type': 'text', 'text': USER_TEMPLATE.format(
        book=book_title,
        page=package['page'],
        total=package['total_pages'],
        notes='\n'.join(f'- {note}' for note in package['notes']) or '- （无相邻页）',
        text=package['text'],
    )}]
    stats = []
    for label, image in package['images']:
        url, size = _image_to_data_url(image)
        stats.append({'label': label, 'bytes': size,
                      'size': (image.size[0], image.size[1])})
        content.append({'type': 'text', 'text': f'\n【图：{label}】'})
        content.append({'type': 'image_url', 'image_url': {'url': url}})
    return ([{'role': 'system', 'content': system_prompt},
             {'role': 'user', 'content': content}], stats)


def call_cloud(messages, config, timeout=300):
    """调用 OpenAI 兼容的 /chat/completions。返回 (文本, 用量信息)。

    不同视觉模型对 max_tokens 的上限差别很大（glm-4v-plus 只允许 2048，
    glm-4.6v 能到好几千）。所以撞到「max_tokens 非法」就自动降档重试，
    而不是让用户去改配置。
    """
    import re

    import requests
    base = (getattr(config, 'llm_base_url', '') or '').rstrip('/')
    if not base:
        raise ValueError('没有配置 llm_base_url')
    url = base + '/chat/completions'
    headers = {'Content-Type': 'application/json'}
    key = getattr(config, 'llm_api_key', '') or ''
    if key:
        headers['Authorization'] = f'Bearer {key}'

    requested = int(getattr(config, 'max_tokens', 4000) or 4000)
    attempts = [requested]
    for fallback in (2048, 1024):
        if fallback < requested and fallback not in attempts:
            attempts.append(fallback)

    last_error = ''
    for budget in attempts:
        payload = {
            'model': getattr(config, 'llm_model', '') or 'gpt-4o-mini',
            'messages': messages,
            'temperature': getattr(config, 'temperature', 0.2),
            # 思考型模型（glm-4.6v）的思考 token 也算进这个上限，给少了会被截断
            'max_tokens': budget,
        }
        # GLM-5.3 系列强制思考：thinking.type 只能 enabled，
        # 想快只能把顶层 reasoning_effort 降到 low（文档：low/high/max）
        effort = str(getattr(config, 'reasoning_effort', '') or '')
        if effort:
            payload['thinking'] = {'type': 'enabled'}
            payload['reasoning_effort'] = effort
        response = requests.post(url, json=payload, headers=headers, timeout=timeout)
        if response.status_code < 400:
            data = response.json()
            text = (data.get('choices') or [{}])[0].get('message', {}).get('content', '')
            usage = data.get('usage') or {}
            return text, {'model': data.get('model'), 'usage': usage, 'max_tokens': budget}

        last_error = f'HTTP {response.status_code}: {response.text[:500]}'
        # 只有「参数非法」这类才值得降档重试，鉴权/模型不存在直接抛
        if 'max_tokens' not in response.text and 'max token' not in response.text.lower():
            raise RuntimeError(last_error)
        match = re.search(r'\[1,\s*(\d+)\]', response.text)
        if match:
            limit = int(match.group(1))
            if limit not in attempts and limit < budget:
                attempts.insert(attempts.index(budget) + 1, limit)
    raise RuntimeError(last_error)
    text = (data.get('choices') or [{}])[0].get('message', {}).get('content', '')
    usage = data.get('usage') or {}
    return text, {'model': data.get('model'), 'usage': usage}


def cache_file(book_cache_dir, page):
    return os.path.join(book_cache_dir, f'explain_p{page:03d}.md')


def explain_page(package, book_title, config, cache_dir, dry_run=False, force=False, kind='exercise'):
    """分析一页；有缓存直接返回。dry_run 时不发请求，只返回准备情况。"""
    path = cache_file(cache_dir, package['page'])
    if not force and os.path.isfile(path):
        with open(path, encoding='utf-8') as fp:
            cached = fp.read()
        return {'text': cached, 'cached': True, 'stats': [], 'payload_bytes': 0}

    messages, stats = build_messages(package, book_title, kind=kind)
    payload_bytes = sum(item['bytes'] for item in stats)
    info = {
        'messages': messages,
        'stats': stats,
        'payload_bytes': payload_bytes,
        'image_count': len(stats),
        'prompt_chars': len(messages[1]['content'][0]['text']),
        'url': (getattr(config, 'llm_base_url', '') or '').rstrip('/') + '/chat/completions',
        'model': getattr(config, 'llm_model', ''),
        'has_key': bool(getattr(config, 'llm_api_key', '')),
    }
    if dry_run:
        return {'text': '', 'cached': False, 'dry_run': True, 'info': info}

    started = time.time()
    text, usage = call_cloud(messages, config)
    elapsed = time.time() - started
    if text:
        os.makedirs(cache_dir, exist_ok=True)
        with open(path, 'w', encoding='utf-8') as fp:
            fp.write(text)
    return {'text': text, 'cached': False, 'info': info, 'usage': usage,
            'elapsed': round(elapsed, 2), 'saved': path}


# ---------------------------------------------------------------- 追问对话
CHAT_SYSTEM = """你是一位和声老师，正在就「某一页乐谱」回答学生的问题。

硬性要求：
1. 只就这一页的内容回答。这一页看不出来的，直接说「这一页上看不出」，不要猜别的页。
2. 事实以【事实卡】为准——那是机器从谱面和书上文字里提取的（题号位置、[解答]/[简释] 标记、
   跨页判断、OCR 文字）。如果你之前的回答和事实卡冲突，**以事实卡为准，并主动纠正自己**。
3. 如果消息里有【术语参考】，说明用户问的是术语：
   a. **优先逐字引用书上的原文**，并标出书名和页码（例：「《和声学教程》p76：'…'」）；
   b. 书上没有原文时才用自己的话解释，并写明「（归纳，非原书原话）」；
   c. 参考里标注了「各教材口径不同」的词，**必须分书并列，不要合并成一个定义**；
   d. 参考里标了「⚠ 待定」的词，只引用原文，不要加自己的解释。
4. 回答要短：先一句话给结论，再 1-3 句理由；需要时引用「第 N 小节」「谱面题号 N」。
5. 不要复述整页讲解，只回答被问到的那个点。
6. 看不清就说不清，不要编造音高、调性、小节数。
7. **依据分三层，按优先级使用**：
   a. 【事实卡】与【术语参考】——最高优先级，引用时要写书名和页码；
   b. 【网络检索】——本地没有时使用，引用时说「网上资料」并给链接；
   c. 你自己的乐理常识——前两者都没有时才能用，并写明「（通用知识，非本地原文）」。
8. **本地没有就明说**：如果【术语参考】写了「本地没有来源」，不要假装有，
   先写一句「本地资料没有这一条」，再按 7b/7c 补充。
9. 回答末尾单独一行给出依据，格式：依据：本地《书名》p12 / 依据：网络检索 + 通用知识 / 依据：通用知识。
"""

FACT_TEMPLATE = """【事实卡】《{book}》第 {page} 页（全书 {total} 页）

{facts}

【这一页已有的讲解（你可以引用，但如果与事实卡冲突，以事实卡为准）】
{analysis}
"""


class ChatSession:
    """某一页的追问对话。默认不带图，按需可以把整页图再发一次。"""

    MAX_TURNS = 8

    def __init__(self, cache_path, package, analysis_text, book_title, glossary=None):
        self.cache_path = cache_path
        self.package = package
        self.analysis_text = analysis_text or ''
        self.book_title = book_title
        self.glossary = glossary
        self.messages = []          # [{'role': 'user'/'assistant', 'content': str}]

    # ---------------------------------------------------------------- 存取
    @staticmethod
    def _payload(package, analysis_text, book_title, messages):
        return {
            'page': package['page'],
            'book': book_title,
            'total': package['total_pages'],
            'facts': package['text'],
            'analysis': analysis_text or '',
            'messages': messages,
        }

    def save(self):
        try:
            os.makedirs(os.path.dirname(self.cache_path), exist_ok=True)
            with open(self.cache_path, 'w', encoding='utf-8') as fp:
                json.dump(self._payload(self.package, self.analysis_text,
                                        self.book_title, self.messages),
                          fp, ensure_ascii=False, indent=2)
        except Exception:
            pass

    @classmethod
    def load(cls, cache_path, package, book_title, glossary=None):
        """有存档就把历史读回来；没有就新建（分析文本随之读回）。"""
        data = {}
        try:
            with open(cache_path, encoding='utf-8') as fp:
                data = json.load(fp)
        except Exception:
            data = {}
        session = cls(cache_path, package, data.get('analysis', ''), book_title, glossary=glossary)
        session.messages = [item for item in (data.get('messages') or [])
                            if item.get('role') in ('user', 'assistant')]
        return session

    # ---------------------------------------------------------------- 提问
    def _fact_message(self):
        return {'role': 'user', 'content': FACT_TEMPLATE.format(
            book=self.book_title,
            page=self.package['page'],
            total=self.package['total_pages'],
            facts=self.package['text'],
            analysis=self.analysis_text[:4000] or '（还没有整页讲解）',
        )}

    def glossary_message(self, question):
        """问题里命中术语表时，把「按书并列」的释义作为一条独立消息注入。"""
        if not self.glossary:
            return None
        entries = self.glossary.match(question)
        if not entries:
            return None
        block = self.glossary.format(entries)
        rename = self.glossary.rename_note(question)
        text = '【术语参考（来自本地教材，按书并列，不要合并）】\n' + block
        if rename:
            text += '\n\n' + rename
        return {'role': 'user', 'content': text}

    def _local_is_thin(self, question):
        """本地（术语库）对这个问题的覆盖够不够：没命中术语，或命中但没原书定义。"""
        if not self.glossary:
            return True
        entries = self.glossary.match(question) or []
        if not entries:
            return True
        for item in entries:
            term = item.get('term')
            if item.get('original'):
                return False
            if (self.glossary.book_defs.get(term) or {}):
                return False
            if ((self.glossary.evidence.get(term) or {}).get('by_book') or {}):
                return False
        return True

    def build_messages(self, question, include_images=False, web_results=None):
        """组装这一轮的 messages：事实卡 +（术语参考）+ 最近几轮 + 新问题。

        事实卡每轮都重发（几百字，很便宜），这是防止模型顺着自己上一轮的错误往下编的关键。
        """
        history = self.messages[-(self.MAX_TURNS * 2):]
        content = []
        if include_images:
            content.append({'type': 'text', 'text': '【本页图片，供核对细节】'})
            for _label, image in self.package.get('images', []):
                url, _size = _image_to_data_url(image)
                content.append({'type': 'image_url', 'image_url': {'url': url}})
        content.append({'type': 'text', 'text': question})
        messages = [{'role': 'system', 'content': CHAT_SYSTEM}, self._fact_message()]
        if web_results:
            lines = ['【网络检索结果（本地资料不足时才用；引用要给链接）】']
            for index, item in enumerate(web_results, start=1):
                lines.append('%d. %s\n   %s\n   %s' % (
                    index, item.get('title') or '', item.get('content') or '',
                    item.get('link') or ''))
            messages.append({'role': 'user', 'content': '\n'.join(lines)})
        glossary = self.glossary_message(question)
        if glossary is not None:
            messages.append(glossary)
        messages += history
        messages.append({'role': 'user', 'content': content})
        return messages

    def ask(self, question, config, include_images=False, allow_web=False):
        """问一句，返回 (回答, 用量)。allow_web 且本地资料不足时会先联网检索。"""
        web_results = []
        if allow_web:
            try:
                thin = self._local_is_thin(question)
            except Exception:
                thin = True
            if thin:
                web_results = web_search(question, config)
        messages = self.build_messages(question, include_images=include_images,
                                       web_results=web_results)
        started = time.time()
        text, usage = call_cloud(messages, config)
        elapsed = time.time() - started
        if text:
            self.messages.append({'role': 'user', 'content': question})
            self.messages.append({'role': 'assistant', 'content': text})
            self.save()
        return text, usage, round(elapsed, 2)

    def clear(self):
        self.messages = []
        self.save()
