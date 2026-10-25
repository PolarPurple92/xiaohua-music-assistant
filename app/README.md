# 小花截图 MIDI · 重构版源码

在原版基础上做了**结构化重构 + 界面现代化**。功能集合与旧版一致（截图、双引擎识别、
MusicXML/MIDI 管理、音量/速度、全局热键、亮暗主题、拖拽导入），代码组织与外观重做。

## 怎么跑起来

```bat
:: 悬浮球（默认）—— 无控制台窗口，日志写入 _unpack\logs\app.log
_unpack\run.bat

:: 完整模式
_unpack\run.bat --full

:: 先用样例数据看看新界面长什么样
_unpack\run.bat --full --demo

:: 指定主题
_unpack\run.bat --full --theme light

:: 排查问题时用这个：保留控制台，日志直接看
_unpack\debug.bat --full
```

`run.bat` 会：
1. 把 `_unpack\runtime`（`build_runtime.py` 合并出的运行库）挂到 `PYTHONPATH`
2. 把 `_internal` 里的 `soundfonts`、`Audiveris.exe` 通过环境变量指好
3. 用 `pythonw.exe` 启动（**不弹控制台**），stdout/stderr 重定向到 `_unpack\logs\app.log`

窗口起不来、识别没反应时，先翻 `_unpack\logs\app.log`，里面有完整的
`[识别]`/`[recognize]`/`[homr]`/`[清理]` 日志和任何未捕获异常的 traceback。

## 运行期目录

全部落在 `_unpack\data\`（源码目录只放代码）：

```
_unpack\data\
├── screenshots\      原始截图——只有这里的图会进左侧缩略图
├── preprocessed\     预处理图（灰度→放大→二值化→锐化后的「带线」版本）
├── homr_work\        homr 工作目录：谱表切片图、调试图都在这里
├── staging\          引擎产出的 XML 中转站，随后归入 xml_outputs
├── temp_audiveris\   Audiveris 临时目录，识别结束即删
├── xml_outputs\      MusicXML 结果
├── midi_outputs\     MIDI 结果
├── sheet_images\     MuseScore 渲染出的乐谱图
├── soundfonts\       音色库（.sf2 / .sf3，默认 MuseScore_General.sf3）
├── briefs\           讲解用的分析缓存（每首一份 brief.json，XML 没变就直读）
└── config.json       设置
```

**三类图严格分开**：原始截图只留在 `screenshots\`；预处理图进 `preprocessed\`；
引擎自己吐出来的中间图（homr 的 `*_staff-N_input.jpg`、`_teaser.png` 之类，也就是
你说的「带扫描线」的那些）全部收进 `homr_work\`。识别结束后还会做一次兜底搬运：
即使某个引擎硬往截图目录里写图，也会被移走，不会再混进缩略图网格。

## 文件结构

```
recovered/
├── interface.py     入口：单实例锁、--full/--demo/--theme、建 root、挂主题、mainloop
├── settings.py      路径常量 + Config(dataclass) + 引擎/音色库探测（配置键与旧版兼容）
├── theme.py         字体/配色混合/ttkbootstrap 样式初始化 + 换肤时清理死控件
├── widgets.py       ttk 控件：Chip / Segmented / FileList / StatusBar / ThumbGrid
│                    + 圆角封面（LRU 缓存）
├── ball_render.py   悬浮球图形：渐变球体（PIL）+ 逐像素 alpha 分层窗口（Win32 API）
├── util.py          小工具：fmt_mmss / screen_workarea（多屏工作区）/ human_size / call_soon
├── ui_kit.py        兼容壳：把上面四个模块重新导出，老写法 `from ui_kit import X` 仍可用
├── base_window.py   BaseWindow：窗口/图标/热键/截图/队列/状态栏/渲染入口（两种模式共用）
├── full_app.py      完整模式：播放器版式（导航 + 封面墙 + 播放列表 + 播放条 + 快捷键）
├── ball_app.py      悬浮球模式：圆形分层窗口、拖动吸边、右键菜单
├── apps.py          兼容壳：把上面三个模块重新导出，老写法 `from apps import FullApp` 仍可用
├── capture.py       全屏遮罩框选截图（带尺寸提示与引导）
├── hotkey.py        全局热键封装（pynput 缺失也不影响主功能）
├── pipeline.py      统一识别流水线：图片 → MusicXML → MIDI（引擎后缀、覆盖式命名）
├── analysis.py       MusicXML → 结构化「事实」：调性/拍号/逐小节和弦与级数/终止式/音域（纯计算，不联网）
├── notes_panel.py    讲解面板：把上面的事实排成逐小节卡片，随播放高亮
├── omr_recognizer.py 识别引擎（homr / Audiveris）——沿用还原版，仅修了 oemer 分支与死代码
├── score_to_midi.py MusicXML → MIDI（music21）
└── midi_player.py   自己调度 mido 事件 + fluidsynth 出声（可停止、精确时长、原生变速）
```

对比旧版：

| 旧版 | 现在 |
|---|---|
| `interface.py` 1083 行单文件，`ScoreBrowserApp` 52 个方法 | 拆成 16 个模块，最大 749 行（`full_app.py`） |
| 两个窗口类复制粘贴（9 个同名方法、6 个逐行相同） | 共用 `BaseWindow`，差异只剩布局 |
| 两条 OMR 流水线各自演化（一边有序号去重、一边没有） | 统一走 `pipeline.process_image` |
| 三套 Listbox+Scrollbar+右键菜单 | 一个 `FileList`（Treeview）+ 分段筛选器 |
| 配置键散落 23 处 `.get('key', 默认值)` | `Config` dataclass，键与默认值唯一来源 |
| `HAS_KEYBOARD/GLOBAL_STYLE/APP_MODE` 模块级可变全局 | 收敛进 `Config` / `BaseWindow` |
| 16 处 `root.after(0, ...)` + 7 个裸 `except:` | 主线程队列 `post()` + `Exception` 收敛 |

## 界面：播放器版式

整体按「音乐播放器」的三段式来做，而不是平铺的控件堆叠：

```
┌────────────┬──────────────────────────────────────────┐
│ ♪ 小花截图  │  曲谱库                    [截取五线谱]  │
│            │  6 张截图 · 双击封面识别并播放            │
│ ▸ 曲谱库    │  ┌───────┐ ┌───────┐ ┌───────┐          │
│ ▸ 输出文件  │  │ 封面   │ │ 封面   │ │ 封面   │         │
│            │  └───────┘ └───────┘ └───────┘          │
│ 识别引擎    │   标题        标题        标题           │
│ ● homr     │   2.5 KB · 10-19 17:20  …               │
│            │                                          │
│ 库概览      │                                          │
├────────────┴──────────────────────────────────────────┤
│ ♪ │ 曲名            │ ▶ │ ────进度──── 0:12/1:48 │ 音色/音量/BPM │
└───────────────────────────────────────────────────────┘
```

- **左侧导航**：曲谱库 / 输出文件两个视图切换，底部是主题、极简模式、更多设置
- **封面墙**：圆角封面（PIL 圆角遮罩按主题底色合成）、悬停标题变色、双击识别播放、右键菜单
- **播放列表**：编号 + 隔行浅底，MusicXML / MIDI / 乐谱图 分段切换，底部操作按钮随选中状态启用
- **底部播放条**：迷你封面 + 曲名 + 绿色播放键 + 细进度条 + 左右时间 + 音色/音量/**BPM**
  播放时进度条会跟着走（`after(200)` 轮询），结束后自动归零
- **暗/亮双主题**：选择会记住；换肤是就地改样式，不重建窗口（窗口位置不丢）
- **PDF 讲解（阅读器）**：侧栏第三项。打开扫描版曲谱 PDF，`‹` `›` 或方向键翻页，
  页码可直接输入跳转，`适合窗口 / 原始大小` 切换缩放；右上「分析本页」把
  「整页图 + 上下接缝条 + OCR 文字」交给云端视觉模型，结果显示在右侧讲解栏并缓存。

  跨页问题不硬判：每次分析都会附带**上一页底部 30%** 和**下一页顶部 30%** 的接缝条，
  提示词里说明「接缝条只用于判断本页内容是否完整」，模型自己看断点在哪。
  （实测这本书 p15 文字跨页、p16 谱例跨页、p17 顶上是上一页的 (c) 版本，接缝条都能覆盖到。）

  模型配置在 `data/llm.json`（首次点「分析本页」会自动生成模板）：

  ```json
  {
    "base_url": "https://open.bigmodel.cn/api/paas/v4",
    "model": "glm-4.5v",
    "api_key": "你的 key"
  }
  ```

  **追问对话**：面板右上角「讲解 / 对话」切换。默认**不带图**（快、便宜），
  想核对细节点「带上图」。每页一条独立对话线，存在 `data/pdf_cache/chat/chat_pNNN.json`，
  翻页回来还能接着聊。每轮都会重发一张「事实卡」（OCR 文字 + 跨页判断 + 谱面题号提示），
  这是防止模型顺着自己上一轮的错误往下编的关键；实测第二带图提问有 1700 token 命中缓存。

  实测成本：纯文字追问约 15s / 1700 prompt token；带图约 6s / 4800 token。

  **必须是支持图片输入的视觉模型**。实测（智谱，2026-10）：

  | 模型 | 耗时/页 | 效果 |
  |---|---|---|
  | `glm-4.6v` | 33–105s | **推荐**。读谱准确，会自己判断跨页；思考 token 算进 `max_tokens`，给 9000 才不会被截断 |
  | `glm-4v-plus` | 39s | 不行。把 p17 说成「第 4 题 (a)(b)」，调号和低音走向是编的 |
  | `glm-4v` / `glm-4v-flash` | 快 | 未细测，只验证过能接收图片 |

  `max_tokens` 上限各模型不同（glm-4v-plus 只允许 2048），代码里撞到会**自动降档重试**，
  不用你改配置。

  跨页判断不交给模型猜：`pdf_book._continuation_hints()` 用 `[解答]`/`[简释]` 的先后顺序
  直接推出结论塞进提示词，例如「本页最后一处 [解答] 之后没有 [简释] → 这题延续到下一页」。
  实测 p15/p16/p17 三页判断全部正确。

  **必须是支持图片输入的视觉模型**（glm-4.5v / qwen-vl-max / gpt-4o 之类）。
  走 OpenAI 兼容协议，所以换服务商只改这三行。结果是纯文本 Markdown，
  按「书 + 页」缓存在 `data/pdf_cache/explain/`，同一页不重复花钱。

- **悬浮球（原来的极简模式）**：72px 球体、四周留白放投影，走 **逐像素 alpha 的分层窗口**
  （`WS_EX_LAYERED` + `UpdateLayeredWindow`），所以边缘是**抗锯齿的平滑圆**、没有方块底也没有锯齿；
  球面是 PIL 4× 超采样渲染的**渐变 + 左上柔光 + 底部内阴影 + 柔和投影**，图标也画进位图里。
  单击截图、拖动挪位置并吸边、右键菜单、双击回完整界面

![悬浮球状态](../shots/ball_states.png)

截图都在 `_unpack/shots/`：`ui_full_dark.png` / `ui_outputs_dark.png` / `ui_empty_dark.png` /
`ui_full_light.png` / `ball_states.png` / `ball_tip.png`

![完整模式](../shots/ui_full_dark.png)

![输出文件](../shots/ui_outputs_dark.png)

![空状态](../shots/ui_empty_dark.png)

![讲解面板](../shots/ui_notes_dark.png)

### 讲解面板（L1：纯计算，不联网）

右上角「讲解」按钮打开右侧面板。播放时面板会自动加载同源 MusicXML 并**逐小节高亮**：

```
讲解
C 大调 · 3/4 · 5 小节 · 6.0s｜变格终止（IV→I）
──────────────────────────────
▍第 3 小节            2.0–3.5s     ← 播放到这里时绿色高亮
  V → V → I
  G · G · C
  属到主
  8 音符 · 2 声部 · C3–D5
```

数据全部来自 `analysis.py` 的确定性计算，**不调用任何 AI、不联网**：

| 字段 | 怎么来的 |
|---|---|
| 调性 | 优先读谱面调号，没有才用 Krumhansl 算法猜 |
| 拍号 / 速度 | 读 XML 的时间签名 / 速度标记，缺省 120 BPM |
| 每小节和弦 | `chordify()` 后逐小节取和弦，转成 `I / IV / V7 / iv` 这类级数 |
| 和弦符号 | 根音 + 性质自己拼（`C` / `G/B` / `G7`）——music21 自带的对带八度重复的三和弦会拒绝识别 |
| 终止式 | 相邻小节边界上认 IV→I / V→I / V→vi / 停在 V，其余一律不写 |
| 音域 / 声部 / 音符数 | 直接数原始声部，比 chordify 更贴近谱面 |
| 时间轴 | quarterLength × 60/BPM，播放时按「进度比例 × 谱面总时长」对齐 |

**已知局限**（诚实说明）：分析基于 OMR 结果，识别错音会带着分析一起错；homr 目前仍会丢弃连音符，
那几小节的节奏与和声判断会偏；无调性/爵士和声这类，级数标注不可靠。



![悬浮球](../shots/ball_tip.png)


## 点击自测清单

建议按顺序点一遍，每步都能在界面上看到反馈。**完整模式**：

1. **启动** — 窗口出现，标题「小花截图 MIDI v1.2.0」，默认暗色；左侧是导航栏，
   右侧「曲谱库」+ 封面墙，底部一条播放条；最下面一行「就绪 / 快捷键 Ctrl + Shift + Z」。
2. **换主题** — 点左下「亮色」→ 整个窗口就地变亮，按钮文字变成「暗色」，**窗口位置和大小不变**；
   再点一次回到暗色。可以来回点多次，窗口不会消失。
3. **换模式** — 点左下「极简模式」→ 变成一个悬浮球（74×74，无边框、四角透明）；
4. **切视图** — 左侧「曲谱库 / 输出文件」来回点：标题、副标题、内容区一起切换，当前项高亮。
5. **筛选列表** — 输出文件里依次点 `MusicXML` / `MIDI` / `乐谱图`，列表随之切换；
   空目录时显示一行灰色「还没有 …」。
6. **选中联动** — 点任意一行 → 底部「打开 / 播放」由灰变亮；切到 MIDI 时「转为 MIDI」变灰，
   「播放」仍可用。
7. **音量 / BPM / 速度术语** — 拖播放条右侧滑块：音量 `100%`、速度 `120 BPM` 实时跟着变；
    BPM 范围 40–240，换算基准是**曲子自身的速度**（识别出来的 MIDI 通常是 120，
    所以 120 BPM 就是原速）。右边那个下拉框是**速度术语**，选 `Andantino 小行板` 就跳到
    100 BPM，拖滑块到非术语值时它会显示 `自定义`。关掉程序重开，数值保留。
8. **音色库** — 播放条下拉里应出现 `MuseScore_General.sf3`（默认，38MB，来自 `vendor/soundfonts`）
   和 `soundfont.sf2`（5.7MB 的 TimGM6mb 兜底）；切换后状态栏提示「音色库：…」，重开程序后仍是它。
   自己加音色：⋯ → 打开音色库文件夹，把 `.sf2`/`.sf3` 丢进 `data/soundfonts/`，
   再点「重新扫描音色库」就能在下拉里看到。
8.5 **讲解面板** — 点右上「讲解」→ 右侧出现面板；播放一首 → 卡片随进度依次高亮（1→2→3…），
   面板头部显示调性/拍号/小节数/终止式；再点「讲解」收起。没有 XML 的曲子会提示「还没有对应的 MusicXML」。
9. **切换引擎** — 点侧栏绿色药丸「homr 深度学习」→ 变成「Audiveris 传统」并更新圆点颜色
   （Audiveris 的 exe 不存在时是红点，属于正确表现）。
10. **区域截图** — 点右上「截取五线谱」→ 主窗口最小化，出现半透明遮罩和顶部提示；
    按住拖动会实时显示 `宽 × 高`；松手后封面墙出现新截图；按 Esc 或右键则取消。
11. **拖拽导入** — 从资源管理器拖一张 png 进窗口 → 出现在封面墙；
    再拖一张同名文件 → 生成 `xxx_1.png`，不会覆盖。
12. **识别** — 双击封面（或右键 →「识别并播放」）：状态栏进入进度条；成功后输出文件列表各多一条，
    **识别完一定会播放**（这条路径不受「截完自动识别」开关影响），播放条会显示曲名 + 迷你封面，
    进度条跟着走；如果播不出声，会弹窗说明原因而不是静默。
    若要「截完图就自动识别并播放」，去「⋯ → 截图后自动识别并播放」勾上。
    **命名规则**：输出带引擎后缀 `cap_x_homr.musicxml` / `cap_x_audiveris.mxl`；
    同一张图再识别一次会**覆盖**同名文件，不会再多出 `_1`、`_2`。
    **顺便看一下目录**：`_unpack\data\screenshots\` 里应该仍然只有原始截图，多出来的是
    `_unpack\data\preprocessed\<名字>_pre.png`（预处理图）和 `_unpack\data\homr_work\`
    （引擎中间图），封面墙**不应该**多出「带五线谱切片」的怪图。
    「⋯ → 打开预处理图文件夹 / 打开识别中间产物文件夹」可以直接核对。
13. **播放** — 输出文件里选中 MIDI →「播放」，或直接点播放条的绿色 ▶（重播上一首）；
    进度条走完自动归零，状态栏回到「播放结束」。
14. **停止** — 播放过程中按 **空格**（或再点一次播放键、或按 Esc）→ 立刻静音，
    状态栏显示「已停止播放」。
15. **快捷键** — `F5`/`Ctrl+R` 刷新、输出文件里 `Del` 删除选中、空格播放/停止。
16. **窗口记忆** — 把窗口拖到某个位置、改个大小 → 关掉程序 → 重开，应该回到原处原尺寸。
17. **单实例** — 程序开着时再从 `run.bat` 启动一次 → 弹「已经在运行」，不会冒出第二个程序。
18. **转换** — 选中 MusicXML 行 →「转为 MIDI」，成功后 MIDI 列表出现同名 `.mid`（同样覆盖）。
19. **右键菜单** — 在文件行上右键，不同分类菜单项不同（XML 有「渲染为乐谱图」）。
20. **删除** — 选中一行 →「删除」→ 确认框 → 列表刷新，文件确实消失。
21. **⋯ 菜单** — 点侧栏「更多设置 ⋯」弹出：自动识别/自动渲染开关、修改快捷键、音色库文件夹、
    MuseScore 路径、打开中间目录、切换主题、切到极简模式、关于、更新说明。
22. **弹窗** — 「关于」「更新说明」内容完整，点「知道了」关闭，不会卡住主窗口。
23. **退出** — 关闭窗口后任务管理器里不应残留 python 进程（热键线程会一起停）。

**悬浮球**（不带 `--full` 启动就是它）：

1. 桌面上出现一个 74×74 的蓝色圆球，四角透明（能看到背后的桌面/窗口），始终置顶。
2. **单击** → 球变黄、窗口隐藏，出现遮罩；框选完成后球变绿、旁边冒出气泡
   「已保存 cap_xxx.png」；点右键或 Esc 取消则球变回蓝。
3. **拖动** → 球跟着鼠标走，松手自动吸到最近的屏幕边缘，位置写进配置，重开还在原处。
4. **右键** → 菜单：截取五线谱 / 从剪贴板导入 / 截完自动识别（勾选）/ 引擎切换 /
   切换亮暗 / 打开完整界面 / 打开截图文件夹 / 退出程序。
5. **双击** → 切回完整模式（不会顺带截图）；完整模式里点「极简模式」再变回球。
6. 颜色含义：蓝=空闲、黄=处理中、绿勾=完成、红感叹号=失败、绿 ♪=正在播放。
7. 鼠标悬停会显示一行操作提示，2 秒左右自动消失。

## 本轮优化

| 优化 | 说明 |
|---|---|
| **输出按引擎加后缀** | `cap_x_homr.musicxml` / `cap_x_audiveris.mxl`，两个引擎的结果一眼能分清；扩展名沿用引擎产出的格式（Audiveris 导出的是压缩 `.mxl`，硬改成 `.musicxml` 会让解析失败） |
| **重复识别不再堆序号** | 同源图 + 同引擎 → 固定路径，重跑直接覆盖。以前同一张图跑 6 次会留下 `_1.._6` 六份 |
| **窗口几何记忆** | 完整模式的大小和位置存进 `config.window_geom`，重启回到原处；越界会被拉回屏内 |
| **封面缩略图缓存** | `(路径, mtime, 尺寸, 圆角, 底色)` 做 LRU（上限 240）。以前每次刷新都重新解码所有截图，主题切换更是全量重算 |
| **多显示器** | 悬浮球的位置/吸边/气泡都按「它所在那块屏」的工作区计算，副屏也能放，不会被拽回主屏 |
| **播放可停止** | 播放改成自己调度 mido 事件（8ms 粒度），空格或播放键随时停；时长算法也准了（同一首旧版报 6.5s，实际 6.0s）；变速直接在时间轴上算，不再写临时 MIDI |
| **速度改成 BPM** | 播放条右侧从「0.3–2.0 倍率」换成「40–240 BPM」，换算基准取曲子自身的速度；配置键 `speed` → `bpm`（旧的 `speed` 会被忽略，默认 120 即原速） |
| **速度术语下拉框** | BPM 滑块右边加了一个术语选择框（Largo 50 / Larghetto 60 / Adagio 70 / Andante 90 / Andantino 100 / Moderato 110 / Allegretto 116 / Allegro 120 / Vivace 160 / Presto 184 / Prestissimo 208）；选中即跳到对应 BPM，反过来拖滑块也会自动显示匹配的术语，对不上显示 `自定义` |
| **音色库可换、支持 .sf3** | 扫描 `data/soundfonts/`、自选文件夹和 `vendor/soundfonts`（只读，不复制，省一份体积），`.sf2` 和 Ogg 压缩的 `.sf3` 都认；更多设置里加了「打开音色库文件夹」「重新扫描音色库」；合成器改成**跨播放复用**（38MB 的 sf3 首次加载要 3.6 秒，复用后每次只需 1 秒） |
| **讲解面板（L1）** | 新 `analysis.py` + `notes_panel.py`：MusicXML → 调性/拍号/逐小节级数与和弦符号/终止式/音域声部，排成卡片随播放高亮。纯本地计算，不联网；结果缓存在 `data/briefs/` |
| **追问对话** | `chat_pane.py` + `explain.ChatSession`：面板内「讲解/对话」切换，默认不带图，每轮重发事实卡防跑偏；对话按页持久化，`带上图` 可重新发整页核对细节 |
| **PDF 讲解阅读器（L2）** | 新 `pdf_book.py`（渲染/OCR/按 `[解答]` 定位题目/裁接缝条） + `pdf_view.py`（翻页缩放） + `explain.py`（OpenAI 兼容视觉调用、dry-run、按页缓存）；侧栏新增「PDF 讲解」，扫码版曲谱一键交给云端模型逐题讲 |
| **默认音色换成 MuseScore_General.sf3** | 原来是 5.7MB 的 TimGM6mb，128 种乐器挤在 6MB 里，听着又薄又硬。换成 38MB 的 MuseScore_General（Ogg 压缩的 sf3），音质跨档；TimGM6mb 保留作兜底 |
| **单实例** | 命名互斥量 `Local\XiaohuaScreenshotMIDI`，第二个实例提示后退出，不会两个球、两个热键互相抢 |
| **快捷键** | 空格 播放/停止、`Del` 删除、`F5`/`Ctrl+R` 刷新、`Esc` 停止 |
| **结构拆分 + 死代码** | `apps.py` 1609 行 → `base_window.py` + `full_app.py` + `ball_app.py`；`ui_kit.py` 857 行 → `theme.py` + `widgets.py` + `ball_render.py` + `util.py`（两个都留兼容壳）；删掉零引用的 `Card`、`load_thumbnail` 和多余的 import |

## 修复记录

- **启动脚本被改坏行尾**（已修，并加了守卫）
  用脚本批量改 `run.bat` 时把 CRLF 全写成了 LF。`python.exe app\interface.py` 照样能跑，
  但双击 `run.bat` **什么都不发生**——cmd.exe 读 LF-only 的批处理会解析错乱，而且不报错。
  现在 `doctor.py` 有一项「启动脚本行尾」，任何 .bat 出现单独的 LF 就 FAIL。

- **方法名撞车导致「讲解」打开的是「更新说明」**（已修）
  新写的面板方法叫 `show_notes`，和原来弹「更新说明」对话框的方法同名；Python 里后定义的
  覆盖前面的，于是点「讲解」弹出了更新说明。已改名 `open_notes` / `close_notes`。

- **单实例保护其实是失效的**（已修）
  原来用固定名字 `Local\XiaohuaScreenshotMIDI`。实测这台机器上那个名字被某个残留进程占着，
  且它的 DACL 不允许再 Create —— `CreateMutexW` 直接返回 `ACCESS_DENIED`（错误码 5），
  代码走「拿不到句柄就放行」的分支，于是检测形同虚设；另外普通 `windll` 调用后的
  `GetLastError()` 会被 ctypes 内部调用冲掉，导致「已在运行」时灵时不灵。
  改法：`ctypes.WinDLL('kernel32', use_last_error=True)` 取错误码、互斥量名字带上
  **安装目录哈希**（顺带允许两份不同安装共存）、任何异常都放行（保护坏了不能让人打不开程序）。

- **「识别并播放」只识别、不出声**（已修）
  `_on_process_done` 里播放的条件写成了 `if midi and self.app_config.auto_play`，
  而 `auto_play` 控制的是「截完自动识别」那条流程，默认 `false`。
  于是菜单写「识别并播放」，实际只识别、不播放 —— 用户听到的就是一片安静。
  改成显式标记：`play_cover()` 先置 `_play_after_process = True`，识别结束按它播放，
  `auto_play` 只管截图自动流程；识别失败或忙碌时标记会清掉，不会漏到下一次。
  顺带补上播放失败的反馈：`midi_player.play_midi` 现在返回成功/失败，
  失败时弹窗说明（音频设备被独占 / 音色库加载失败），不再静默。
  端到端验证：`auto_play=false` 下用真实截图走一遍，识别 6s + 播放 6.5s，
  播放条显示曲名、结束回落「播放结束」。

- **曲谱库空状态没在正中间**（已修）
  空状态原来是 `grid(row=0, column=0)` 塞进画布内容框，但那个框的列没有权重、高度也只有内容高度，
  于是「还没有曲谱封面」贴在左上角。改成**覆盖在 canvas 上的独立一层**，用
  `place(relx=0.5, rely=0.5, anchor='center')` 精确居中；覆盖层挂在 canvas 上而不是整个 ThumbGrid 上，
  否则会被右侧滚动条挤偏约 7px。空的时候顺便把滚动条收起来。
  自检里加了逐像素断言：块中心与画布中心水平差 ≤4px、垂直差 ≤6px，并且切回有封面时必须清掉覆盖层。

- **悬浮球是个「方块底」+ 纯色死板 + 边缘锯齿**（已修，两轮）
  第一轮：原来用 `wm_attributes('-transparentcolor')` 抠键控色，这招依赖颜色键在当前 DPI / 显卡 /
  GDI 缩放下精确命中，不少环境会失效，四角就露出一块方形底色（亮色主题下是白方块）。
  换成 `SetWindowRgn(CreateEllipticRgn(...))` 后没方块了，但**区域裁剪是系统级的，不做抗锯齿**，
  看着还是一格一格的像素毛边。
  第二轮：改成 **逐像素 alpha 的分层窗口** —— `WS_EX_LAYERED` + `UpdateLayeredWindow`，
  自己把 PIL 渲染的 RGBA 位图（预乘 alpha）推给系统，边缘就是真正的抗锯齿过渡，
  还能带柔和投影。两个坑：
  · `UpdateLayeredWindow` 的位图位置和 Tk 的 `geometry()` 是两套坐标，必须用 `GetWindowRect`
    取真实位置，否则球会画到别处（表现为「球不见了」）；
  · 窗口 map 之前 HWND 不稳定，分层样式会设到旧窗口上，所以要在 30/200/700ms 各重试一次。
  兜底：分层窗口建不起来时退回 `SetWindowRgn`（有锯齿但不是方块）。
  球面同时从「纯色圆片」换成 4× 超采样渲染的渐变球，配色独立于主题（更亮的蓝/橙/绿/红）。
  顺带修掉一个被吞掉的异常：`canvas.configure(bg=<RGB 元组>)` 会抛 `unknown color`，
  导致每次换状态只换了颜色、没换图标（一直显示 ♪）。自检里现在会逐个状态核对图标，
  并且断言分层窗口确实建立。

- **悬浮球拖动后位置回弹**（已修）
  `geometry()` 之后立刻读 `winfo_x()` 可能还是旧值，导致松手吸边时把球拽回原位、
  `ball_pos` 也存成旧坐标。改成自己记录「请求的位置」（`_pos`），拖拽/吸边/保存都以它为准。
  自检里加了「拖动挪位置并记忆」这条断言（`uiselftest.py`）。

- **识别产物和原始截图混在一起**（已修）
  homr 会把识别过程中的谱表切片图（`*_staff-N_input.jpg`、`_teaser.png`、`*_output.jpg` 这类
  带五线谱的图）按输入图片路径写到**截图目录**；旧实现把 homr 的工作目录直接设在截图目录，
  于是这些图和原始截图混在一起，甚至被缩略图网格当成截图显示。
  现在拆成三个位置：原始截图 `screenshots/`、预处理图 `preprocessed/`、引擎中间图 `homr_work/`；
  homr 的 cwd 改到 `homr_work`，识别结束后再对截图目录做一次「新增图片兜底搬运」。
  回归脚本：`python _unpack\test_separation.py`（11 项断言）。

- **启动时的控制台窗口**（已去掉）
  `run.bat` 改用 `pythonw.exe` 启动，不再弹控制台；日志改为写入 `_unpack\logs\app.log`，
  并装了 `sys.excepthook`，即使启动阶段就崩了也能在日志里看到 traceback。
  需要看实时日志时用 `debug.bat`。

- **换主题两次后窗口消失 / 窗口位置被重置**（已修）
  ttkbootstrap 的 `Publisher` 以窗口路径为键登记订阅者，被销毁窗口的条目不会自动清掉；
  旧实现每次换主题都「销毁窗口 → 换皮肤 → 重建」，第二次重建时 `theme_use` 回调到已销毁的
  Combobox 上抛 `bad window path name`，异常导致重建根本没执行。同时重建用的是固定
  `geometry()`，所以位置被重置。
  现在改为**就地换肤**（`theme_use` + 同步 Canvas/药丸等非 ttk 部件），并在换肤前调用
  `ui_kit.purge_dead_widgets()` 清理死订阅；只有切模式这种必须重建的场景才重建，且保留原位置。

## 换机器部署

```powershell
# 在这台机器上打包（自带 Python，无需目标机装环境）
python _unpack\build_portable.py                    # 精简版 419 MB（homr 引擎）
python _unpack\build_portable.py --with-audiveris   # 约 546 MB（多带传统引擎）
```

产物 `Xiaohua_MIDI_Modern\` 整个文件夹拷走即可：里面自带 CPython 3.11.9，
`run.bat` 用相对路径，不依赖注册表/环境变量。到新机器上：

1. 先双击 `doctor.bat`，逐项检查解释器、依赖、引擎、音色库（`[SKIP]` 是可选缺失，不影响）
2. 再双击 `run.bat`（无控制台，日志在 `logs\app.log`）

数据都在 `data\`，想整个重置就删掉这个目录。

## 已知限制

- **识别/播放依赖打包目录**：`run.bat` 已经把 `_internal` 的 soundfonts 与
  `Audiveris.exe` 通过环境变量指好；如果你换机器、只拷了 `recovered/`，
  这两个功能会因为找不到资源而显示红点/提示。
- **MuseScore 渲染**需要本机安装 MuseScore，并在「⋯ → 设置 MuseScore 路径」指定。
- **重名截图**自动加 `_1` 序号；但 MIDI 文件名仍按截图 basename 生成，
  两张同名截图会共用同一个 `.mid`（这一点和旧版一致，尚未改动）。
- 界面是 tkinter，做不到圆角/阴影这类效果；主题色由 ttkbootstrap 提供。
- 日志里可能出现一次 `music21: ... might need the optional package matplotlib` ——
  这是我们主动裁掉 matplotlib 后的提示，只影响 music21 的绘图相关功能，可以忽略。

## 复核与回归

```powershell
$py='C:\Users\Windows\AppData\Local\Programs\Python\Python311\python.exe'
$rt='_unpack\runtime'; $env:PYTHONPATH=$rt; $env:PATH="$rt;$env:PATH"

# 交互自检（41 项：窗口构建、筛选、选中联动、主题重建、模式切换、回调健壮性…）
& $py '_unpack\uiselftest.py'

# 重新出图（改完界面后看效果）
& $py '_unpack\uipreview.py' full dark
& $py '_unpack\uipreview.py' compact light
```

`_unpack/recovered_original/` 是**改造前、字节码与原 exe 完全一致**的还原版本，
想确认「某个行为是不是被改坏了」可以直接 diff 对照。
