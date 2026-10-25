# -*- coding: utf-8 -*-
"""路径、常量与配置。

配置项的键名与旧版 config.json 完全一致，老用户升级后设置不会丢。
所有目录都支持用环境变量覆盖，便于拿样例数据试跑而不污染真实目录。
"""
import json
import os
import sys
from dataclasses import asdict, dataclass

APP_NAME = '小花音乐助手'
APP_SUBTITLE = '截图即听，让乐谱活起来'
APP_VERSION = '2.0.0'
APP_AUTHOR = '饭吃完了我吃什么'

ENGINE_HOMR = 'homr'
ENGINE_AUDIVERIS = 'audiveris'
ENGINES = (ENGINE_HOMR, ENGINE_AUDIVERIS)
ENGINE_LABEL = {ENGINE_HOMR: 'homr 深度学习', ENGINE_AUDIVERIS: 'Audiveris 传统'}
DEFAULT_ENGINE = ENGINE_HOMR

DEFAULT_HOTKEY = 'ctrl+shift+z'
HOTKEY_HELP = 'ctrl+shift+z'

# 亮/暗两套肤色，映射到 ttkbootstrap 主题
THEME_MODES = ('light', 'dark')
THEME_BOOTSTYLES = {'light': 'litera', 'dark': 'darkly'}
DEFAULT_THEME = 'light'

AUDIO_EXTS = ('.mid', '.midi')
XML_EXTS = ('.xml', '.mxl', '.musicxml')
IMAGE_EXTS = ('.png', '.jpg', '.jpeg', '.bmp', '.tiff', '.gif')


def _base_dir():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


BASE_DIR = _base_dir()


def resource_path(*parts):
    root = getattr(sys, '_MEIPASS', BASE_DIR)
    return os.path.join(root, *parts)


def _dir_env(name, default):
    return os.path.abspath(os.environ.get(name) or os.path.join(BASE_DIR, default))


SCREENSHOT_DIR = _dir_env('XIAOHUA_SCREENSHOTS', 'screenshots')
XML_DIR = _dir_env('XIAOHUA_XML', 'xml_outputs')
MIDI_DIR = _dir_env('XIAOHUA_MIDI', 'midi_outputs')
SHEET_DIR = _dir_env('XIAOHUA_SHEETS', 'sheet_images')
SOUNDFONT_DIR = _dir_env('XIAOHUA_SOUNDFONTS', 'soundfonts')
SOUNDFONT_EXTS = ('.sf2', '.sf3')     # .sf3 是 Ogg 压缩版，体积小很多
# 没有指定音色库时优先用这个（比原来 5.7MB 的 TimGM6mb 好听得多，体积 38MB）
DEFAULT_SOUNDFONT = 'MuseScore_General.sf3'
# 额外只读扫描目录（便携包把自带音色库放这里，用';'分隔多个）——
# 这样 vendor 里的库不用复制进 data，省掉一份重复体积
def _bundle_soundfont_dirs():
    """便携包自带的音色库位置：不靠 run.bat 设环境变量也能找到。"""
    root = os.path.dirname(BASE_DIR)          # app 的上一级就是发布包根目录
    candidates = [
        os.path.join(root, 'vendor', 'soundfonts'),
        os.path.join(root, 'data', 'soundfonts'),
        os.path.join(root, 'preview_data', 'soundfonts'),
        os.path.join(BASE_DIR, 'soundfonts'),
    ]
    return [path for path in candidates if os.path.isdir(path)]


SOUNDFONT_DIRS_EXTRA = tuple(
    [path for path in (os.environ.get('XIAOHUA_SOUNDFONTS_EXTRA') or '').split(';') if path]
    + _bundle_soundfont_dirs()
)

# 识别过程产生的中间产物，和「原始截图」严格分开，避免混在缩略图网格里
PREPROCESSED_DIR = _dir_env('XIAOHUA_PREPROCESSED', 'preprocessed')   # 二值化/加线后的图
HOMR_WORK_DIR = _dir_env('XIAOHUA_HOMR_WORK', 'homr_work')            # homr 的工作目录与调试图
AUDIVERIS_TEMP_DIR = _dir_env('XIAOHUA_AUDIVERIS_TEMP', 'temp_audiveris')
# 识别引擎产出的 XML 先落到这里，再由 pipeline 归入 xml_outputs（带重名去重）
STAGING_DIR = _dir_env('XIAOHUA_STAGING', 'staging')

CONFIG_FILE = os.environ.get('XIAOHUA_CONFIG') or os.path.join(BASE_DIR, 'config.json')
# 讲解面板的分析缓存（每首曲子一份 brief.json，XML 没变就直接读）
BRIEF_DIR = _dir_env('XIAOHUA_BRIEF', 'briefs')
# 云端模型配置（base_url / model / api_key）：放在 config.json 旁边，用户自己填
LLM_FILE = os.environ.get('XIAOHUA_LLM_FILE') or os.path.join(
    os.path.dirname(CONFIG_FILE), 'llm.json')

MANAGED_DIRS = (SCREENSHOT_DIR, XML_DIR, MIDI_DIR, SHEET_DIR, SOUNDFONT_DIR,
                PREPROCESSED_DIR, HOMR_WORK_DIR, STAGING_DIR, BRIEF_DIR)


def ensure_dirs():
    for path in MANAGED_DIRS:
        try:
            os.makedirs(path, exist_ok=True)
        except OSError:
            pass


def audiveris_exe():
    """Audiveris 位置：优先环境变量，便于从源码运行时指向打包目录里的 exe。"""
    override = os.environ.get('XIAOHUA_AUDIVERIS')
    if override:
        return override
    return resource_path('Audiveris', 'Audiveris.exe')


def engine_available(engine_name):
    """真实检测引擎可用性：Audiveris 看 exe 是否存在，homr 看包能否导入。"""
    if engine_name == ENGINE_AUDIVERIS:
        return os.path.isfile(audiveris_exe())
    if engine_name == ENGINE_HOMR:
        try:
            import homr  # noqa: F401
            return True
        except Exception:
            return False
    return False


@dataclass
class Config:
    """运行设置。键名沿用旧版 config.json，保证向后兼容。"""

    hotkey: str = DEFAULT_HOTKEY
    auto_play: bool = False
    auto_render: bool = False
    engine: str = DEFAULT_ENGINE
    sf2_folder: str = ''
    sf2_name: str = ''
    volume: float = 1.0
    # 播放速度用 BPM 表示：0 表示跟随曲子原本的速度
    bpm: int = 120
    musescore_path: str = ''
    theme: str = DEFAULT_THEME
    first_run_done: bool = False
    # 悬浮球的屏幕位置，形如 "1520,640"；空字符串表示用默认位置
    ball_pos: str = ''
    # 完整模式的窗口几何，形如 "1180x760+300+180"
    window_geom: str = ''
    # 上次打开的 PDF 和页码（阅读器恢复现场用）
    pdf_path: str = ''
    pdf_page: int = 1
    # 术语页上次看的词与分级（下次进来直接回到这里）
    glossary_term: str = ''
    glossary_tier: str = '全部'
    # 点谱试听用的 GM 音色号（0 = 大钢琴）
    preview_program: int = 0
    # 点谱试听时，高低音谱表是否合成一行一起播
    merge_grand: bool = True
    # 符干方向：voices=按声部(SATB)、outward=逐音朝外、staff=按谱表、rule=按中线、up=一律朝上
    stem_mode: str = 'voices'
    # 生成试听音频后，是否弹出小窗显示识别出来的五线谱
    show_score_preview: bool = True

    @classmethod
    def load(cls, path=None):
        path = path or CONFIG_FILE
        cfg = cls()
        try:
            with open(path, 'r', encoding='utf-8') as fp:
                raw = json.load(fp)
        except Exception:
            return cfg
        if not isinstance(raw, dict):
            return cfg
        for key, value in raw.items():
            if not hasattr(cfg, key):
                continue
            default = getattr(cfg, key)
            try:
                if isinstance(default, bool):
                    value = bool(value)
                elif isinstance(default, float):
                    value = float(value)
                elif isinstance(default, str):
                    value = str(value)
            except (TypeError, ValueError):
                continue
            setattr(cfg, key, value)
        if cfg.theme not in THEME_MODES:
            cfg.theme = DEFAULT_THEME
        if cfg.engine not in ENGINES:
            cfg.engine = DEFAULT_ENGINE
        return cfg

    def save(self, path=None):
        path = path or CONFIG_FILE
        try:
            with open(path, 'w', encoding='utf-8') as fp:
                json.dump(asdict(self), fp, indent=2, ensure_ascii=False)
            return True
        except OSError:
            return False

    def toggle_engine(self):
        idx = ENGINES.index(self.engine) if self.engine in ENGINES else 0
        self.engine = ENGINES[(idx + 1) % len(ENGINES)]
        return self.engine

    @property
    def theme_bootstyle(self):
        return THEME_BOOTSTYLES.get(self.theme, THEME_BOOTSTYLES[DEFAULT_THEME])


def list_soundfonts(config):
    """按 用户指定目录 → soundfonts 目录 → 程序目录 的顺序找音色库。

    支持 .sf2 和 .sf3：后者是 Ogg 压缩的同源音色库，体积只有 1/3 左右，
    fluidsynth 3 直接能读（FluidR3_GM 141MB → .sf3 约 40MB）。
    """
    found, seen = [], set()

    def add(path):
        real = os.path.abspath(path)
        if real in seen:
            return
        if os.path.isfile(real) and real.lower().endswith(SOUNDFONT_EXTS):
            seen.add(real)
            found.append(real)

    folder = config.sf2_folder
    if folder and os.path.isdir(folder):
        for name in sorted(os.listdir(folder)):
            add(os.path.join(folder, name))

    for directory in (SOUNDFONT_DIR, BASE_DIR) + SOUNDFONT_DIRS_EXTRA:
        if not os.path.isdir(directory):
            continue
        for name in sorted(os.listdir(directory)):
            add(os.path.join(directory, name))

    return found


def find_sf2_path(config):
    """返回当前选中音色库的绝对路径。

    优先级：配置里指定的 → DEFAULT_SOUNDFONT → 扫到的第一个。
    """
    candidates = list_soundfonts(config)
    if not candidates:
        return ''
    if config.sf2_name:
        for path in candidates:
            if os.path.basename(path) == config.sf2_name:
                return path
    if DEFAULT_SOUNDFONT:
        for path in candidates:
            if os.path.basename(path) == DEFAULT_SOUNDFONT:
                return path
    return candidates[0]
