# 小花音乐助手（Xiaohua Music Assistant）

把扫描版乐谱 PDF 变成「点一下就能听」的交互读物，并给出和声/曲式讲解。

面向的场景：读谱吃力、做和声题看不明白、想听一段四声部写作是什么效果。

## 它做什么

- **PDF 逐页阅读**：鼠标悬停高亮谱行，双击识别并播放，拖框可选多行（旋律题常跨两行）
- **曲谱识别**：谱行 → MusicXML → MuseScore 排版 → MIDI 播放，识别结果与原谱并排对照
- **术语查询**：右键查本页出现的术语，按时期与语境筛选，给出各教材的原书定义与页码
- **整页讲解**：把这一页交给云端大模型讲一遍（需自备 API key）

## 依赖

解压就能用：识别引擎（homr）、音色库、Python 运行时都已随包附带。

| 组件 | 用途 | 许可证 | 是否随包 |
|---|---|---|---|
| homr | 谱面识别（双击播放靠它） | AGPL-3.0 | ✅ **已内置** |
| 音色库 | 播放音色 | MIT | ✅ `vendor/soundfonts/MuseScore_General.sf3` |
| Python 运行时 | 免安装 | PSF-2.0 | ✅ |
| MuseScore | 让识别结果排版更漂亮 | GPL-3.0 | ❌ 可选，[下载](https://musescore.org/download) |
| Audiveris | 另一个识别引擎 | AGPL-3.0 | ❌ 可选，[下载](https://github.com/Audiveris/audiveris/releases) |

点右上角「依赖」可以看每一项的实时状态和官方下载地址。

**注意**：homr 的模型权重含非商业训练数据（CC BY-NC 4.0），**本包按非商业用途提供**。
商业使用请自行评估，详见 `THIRD_PARTY_NOTICES.md`。

## 快速开始

1. 解压，双击 `run.bat`（或在命令行 `python app\main.py`）
2. 点 **「打开 PDF」**，选一本你自己持有的乐谱扫描件
   - 手头没有的话，先用随包的 `samples\sample-score.pdf`（巴赫《马太受难曲》众赞歌，公版扫描页）
3. 把鼠标移到某一行谱上，**双击**试听；想听整段就往上/下拖出多行，或用 `＋行 / －行` 调整
4. 右键某个术语查它的原书定义

## 书放哪里

发布包里有个 `books` 文件夹，专门放你要整理的书：

    XiaohuaMusicAssistant\
      books\             <- 把 PDF 放这里
      app\  data\  tools\  samples\ ...

放进去之后：术语页 -> 从书里整理 -> 选这个文件夹。

程序逐页做本地 OCR（不联网，做过一次就缓存），再把文字交给模型提炼术语。
第一次建议只放一本小的试试，一本 300 页的书大约要 20~30 分钟。

放别处也行，整理时会让你选文件夹，books 只是默认位置。

## 术语库

仓库**不含**任何书籍数据。首次运行是空库，需要自己建：

```
app/../tools/            整理流程脚本
  ocr_queue.py           排队要 OCR 的页
  ocr_book.py            页面 → 文字（本地 OCR）
  lookup_terms.py        在书里找术语出现的句子
  book_definitions.py    让模型把这些句子归纳成「某书对某词的定义」
```

处理对象应当是**你自己合法持有**的书。数据只存在本机。

## 云端功能（可选）

「分析本页」需要填 `data/llm.json`：

```json
{
  "base_url": "https://open.bigmodel.cn/api/paas/v4",
  "model": "glm-5.3-flash",
  "api_key": "你自己申请的 key",
  "max_tokens": 9000,
  "reasoning_effort": "low"
}
```

`reasoning_effort` 对 GLM-5.3 系列重要：该系列强制思考，填 `low` 才快（十几秒），
填 `max` 会把 token 全花在思考上、导致超时。

不填也能用：识别、播放、术语查询都是本地的。

## 目录

```
app/        程序源码（界面、识别流水线、术语库、MuseScore 调用）
data/       运行数据与配置（书籍索引、术语库、llm.json）
python/     内置 Python 运行时
lib/        内置依赖
run.bat     启动脚本
```

## 许可证

AGPL-3.0，见 `LICENSE`。
第三方组件见 `THIRD_PARTY_NOTICES.md`。

名称「小花音乐助手」与图标不随 AGPL 授权：fork 后请更换名称与图标，详见 `THIRD_PARTY_NOTICES.md`。

## 免责

见 `DISCLAIMER.md`：只处理你合法持有的乐谱；不提供任何书籍下载。
