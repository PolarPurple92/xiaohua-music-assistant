# 第三方组件与许可证

本项目（小花音乐助手 Xiaohua Music Assistant）以 **AGPL-3.0** 发布。原因是它调用并在发布包中附带 **homr**，
而 homr 采用 AGPL-3.0。

发布包**附带 homr**（含模型权重，位于 `lib\homr`），**不附带** MuseScore、Audiveris，由用户自行从官方渠道获取。

| 组件 | 用途 | 许可证 | 是否随包 | 官方来源 |
|---|---|---|---|---|
| **homr** | 谱面识别（OMR）：图片 → MusicXML | **AGPL-3.0** | ✅ 附带（含权重） | https://github.com/liebharc/homr |
| MuseScore | MusicXML 排版 / 导出 PNG、MIDI | **GPL-3.0** | ❌ 可选安装 | https://musescore.org/download |
| Audiveris | 另一个识别引擎（可选） | **AGPL-3.0** | ❌ 可选安装 | https://github.com/Audiveris/audiveris/releases |
| FluidSynth | MIDI 合成播放 | **LGPL-2.1-or-later** | ✅ 附带（DLL） | https://www.fluidsynth.org/ |
| Python | 运行时 | PSF-2.0 | ✅ 附带 | https://www.python.org/ |
| pypdfium2 / PDFium | PDF 渲染 | Apache-2.0 / BSD-3-Clause | ✅ | https://pypi.org/project/pypdfium2/ |
| ttkbootstrap | 界面主题 | MIT | ✅ | https://pypi.org/project/ttkbootstrap/ |
| Pillow | 图像处理 | MIT-CMU | ✅ | https://pypi.org/project/Pillow/ |
| numpy | 数值计算 | BSD-3-Clause | ✅ | https://numpy.org/ |

## homr 与它的模型权重（重要）

homr 代码与权重均以 AGPL-3.0 发布，本包一并分发；对应源码可从上面的 GitHub 仓库获取。

**但权重还受训练数据许可的约束。** homr 自己的 `LICENSE_FAQ.md` 写明：

> The weights are published under the AGPL as well. However, the AGPL can't grant more rights
> than the training data allows.

其权重用到的数据里包含 **Camera-PrIMuS（CC BY-NC 4.0，禁止商业使用）**，且官方说明
「目前发布的所有 transformer 权重都包含 PrIMuS」。

因此：

- **本发布包按非商业用途提供**（个人学习、教学、开源分发）
- 如需**商业使用**（收费产品、商业项目集成、商业定制），请自行评估权重许可风险，
  或改用仅用宽松许可数据训练的模型，或购买/替换为其它引擎
- 本项目不对权重的许可合规性作任何担保

## Audiveris（可选）

Audiveris 同样是 AGPL-3.0，本包**不附带**（含 Java 运行时约 200 MB，且对扫描件识别效果不如 homr）。

需要时自行安装，程序会自动发现（放在 `vendor\Audiveris\Audiveris.exe`、
或设置环境变量 `XIAOHUA_AUDIVERIS`、或加进 PATH），然后在识别结果窗口点「换引擎重试」。
| requests | HTTP | Apache-2.0 | https://pypi.org/project/requests/ |

## 音色库（SoundFont）

发布包内附带 **MuseScore_General.sf3**（`vendor/soundfonts/`，38 MB），用于免安装即可试听。

- 许可证：**MIT**（部分采样为 Public Domain / CC0）
- 来源：MuseScore 官方音色库 <https://musescore.org/en/handbook/soundfonts>
- 改编与整合：Copyright © 2018–2021 S. Christian Collins
- 基于 FluidR3 Mono GM（MIT）：Copyright © 2014–2017 Michael Cowgill；
  FluidR3 GM（MIT）：Copyright © 2000–2002, 2008 Frank Wen
- MuseScore Drumline 采样（CC0）：S. Christian Collins & Amir Oosman
- Splendid Grand 钢琴采样：Public Domain

MIT 许可要求：在副本中保留上述版权声明与本许可声明。

```
Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.
```

你也可以换成自己的音色库：把 `.sf2` / `.sf3` 放进 `data/soundfonts/`，或在设置里指路径。

## 云端模型（可选）

「分析本页」需要你自己填一个兼容 OpenAI 的接口（默认指向智谱开放平台）。
发送的是**该页图片与 OCR 文本**，走你自己申请的 API key，服务条款以服务商为准。
不填也能用：谱面识别、播放、术语查询都是本地的。

## 书籍与术语数据

仓库**不包含**任何从受版权保护的教材中提取的术语释义、引文与书页 OCR 文本。

`tools/` 下有整理流程的脚本（`ocr_queue.py` → `ocr_book.py` → `lookup_terms.py` → `book_definitions.py`），
供你处理**自己合法持有**的书籍。数据放在本机，是否分享由你决定，并自行承担相应责任。

## 名称与图标

项目名称「小花音乐助手」（Xiaohua Music Assistant）、图标（`app/icon.ico`、`app/icon.png`）
及界面视觉为项目作者所有，**不随 AGPL-3.0 授权**。

AGPL 只覆盖源代码。你可以自由 fork、修改、再分发代码，但请：

- 更换程序名称与图标，避免与你分发的版本被误认为本项目
- 不要在宣传中暗示本项目为你背书

如果你希望保留「小花音乐助手」名称做二次分发，请先联系作者。

## 商标

「MuseScore」「Audiveris」「智谱」等名称归各自权利人所有。
本项目与上述项目**没有官方关联**，也不代表其认可。
