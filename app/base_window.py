# -*- coding: utf-8 -*-
"""两个模式共用的窗口外壳。

窗口、图标、全局热键、截图流程、跨线程队列、状态栏、渲染入口只在这里写一次，
FullApp / BallApp 只管各自的布局。
"""
import datetime
import os
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog

import ttkbootstrap as tb
from ttkbootstrap.constants import BOTH, LEFT, RIGHT, X, Y, YES

import pipeline
from capture import ScreenCapture
from hotkey import GlobalHotkey, describe
from settings import (
    APP_AUTHOR, APP_NAME, APP_SUBTITLE, APP_VERSION,
    ENGINE_LABEL, IMAGE_EXTS, MIDI_DIR, SHEET_DIR, SCREENSHOT_DIR, XML_DIR, XML_EXTS,
    engine_available, find_sf2_path, list_soundfonts, resource_path,
)
from ui_kit import FONT_BODY, FONT_SMALL, GAP, PAD, theme_bg

try:
    from tkinterdnd2 import DND_FILES
    from tkinterdnd2.TkinterDnD import Toplevel as DnDToplevel
except Exception:  # pragma: no cover - 没有 tkinterdnd2 时退化为普通窗口
    DND_FILES = None
    DnDToplevel = tk.Toplevel


def _fmt_time(timestamp):
    try:
        return datetime.datetime.fromtimestamp(timestamp).strftime('%m-%d %H:%M')
    except (OSError, ValueError):
        return ''


def _list_dir(directory, exts):
    """返回按修改时间倒序的 (name, size, mtime)。"""
    items = []
    if not os.path.isdir(directory):
        return items
    for name in os.listdir(directory):
        if not name.lower().endswith(exts):
            continue
        path = os.path.join(directory, name)
        try:
            stat = os.stat(path)
        except OSError:
            continue
        items.append((name, stat.st_size, stat.st_mtime))
    items.sort(key=lambda item: item[2], reverse=True)
    return items


class BaseWindow(DnDToplevel):
    """两个模式共用的外壳。"""

    window_title = APP_NAME
    geometry_size = '1180x760'
    min_size = (980, 620)

    def __init__(self, master, config, controller):
        super().__init__(master)
        self.app_config = config
        self.controller = controller
        self.capturing = False
        self._busy = False
        self._play_after_process = False
        self._stop_event = None
        self._save_job = None
        self._queue = queue.Queue()

        self.title((f'{self.window_title}  v{APP_VERSION}'))
        self.geometry(self.geometry_size)
        self.minsize(*self.min_size)
        try:
            self.configure(bg=theme_bg())
        except tk.TclError:
            pass
        self._apply_icon()
        self.protocol('WM_DELETE_WINDOW', self.on_close)

        self.hotkey = GlobalHotkey(lambda: self.post(self.area_capture))
        self.register_hotkey()

        self.build()
        self.after(60, self._drain_queue)
        self.refresh_all()

    # ------------------------------------------------------------ 基础
    def _apply_icon(self):
        try:
            ico = resource_path('icon.ico')
            if os.path.isfile(ico):
                self.iconbitmap(ico)
        except Exception:
            pass

    def post(self, func, *args):
        """从任意线程把回调排进主线程。"""
        self._queue.put((func, args))

    def _drain_queue(self):
        try:
            while True:
                func, args = self._queue.get_nowait()
                try:
                    func(*args)
                except Exception as exc:  # 单个回调失败不能拖垮整个循环
                    print(f'[ui] 回调异常: {exc}')
        except queue.Empty:
            pass
        try:
            if self.winfo_exists():
                self.after(60, self._drain_queue)
        except tk.TclError:
            pass

    def schedule_save(self):
        """配置改动做 300ms 防抖，避免拖动滑块时疯狂写盘。"""
        if self._save_job is not None:
            try:
                self.after_cancel(self._save_job)
            except Exception:
                pass
        self._save_job = self.after(300, self._save_now)

    def _save_now(self):
        self._save_job = None
        self.app_config.save()

    # ------------------------------------------------------------ 热键
    def register_hotkey(self):
        ok = self.hotkey.start(self.app_config.hotkey)
        self.on_hotkey_state(ok)
        return ok

    def on_hotkey_state(self, ok):
        """子类可以在这里更新热键提示。"""

    # ------------------------------------------------------------ 截图
    def area_capture(self):
        if self.capturing:
            return
        self.capturing = True
        try:
            self.iconify()
        except tk.TclError:
            pass
        self.after(180, self._open_capture)

    def _open_capture(self):
        try:
            ScreenCapture(self, self.on_capture_done)
        except Exception as exc:
            self.capturing = False
            self.deiconify()
            messagebox.showerror('截图失败', f'无法打开截图窗口：{exc}', parent=self)

    def on_capture_done(self, path):
        self.capturing = False
        try:
            self.deiconify()
            self.lift()
        except tk.TclError:
            pass
        if not path:
            self.set_status('已取消截图')
            return
        self.set_status(f'已保存截图：{os.path.basename(path)}')
        self.refresh_screenshots()
        if self.app_config.auto_play:
            self.handle_new_image(path)

    def handle_new_image(self, path):
        self.process_image(path)

    # ------------------------------------------------------------ 状态
    def set_status(self, text, hint=None):
        self.status.set(text, hint)

    def set_busy(self, text=None):
        self._busy = True
        self.status.busy(text)

    def set_idle(self, text=None):
        self._busy = False
        self.status.idle(text)

    # ------------------------------------------------------------ 主题
    def toggle_theme(self):
        self.controller.toggle_theme()

    def on_theme_changed(self):
        """主题就地切换后同步那些不跟随 ttk 样式的部分。"""
        try:
            self.configure(bg=theme_bg())
        except tk.TclError:
            pass
        thumbs = getattr(self, 'thumbs', None)
        if thumbs is not None:
            thumbs.apply_theme()
        button = getattr(self, 'theme_btn', None)
        if button is not None:
            button.configure(text=self.theme_label())
        nav_theme = getattr(self, 'nav_buttons', {}).get('__theme__')
        for widget in self.winfo_children():
            if isinstance(widget, (tb.Frame,)) and hasattr(widget, 'winfo_children'):
                pass

    def theme_label(self):
        """按钮上写"将要切到"的主题，比写"主题"更明确。"""
        return '亮色' if self.app_config.theme == 'dark' else '暗色'

    def switch_mode(self):
        self.controller.switch_mode()

    def on_close(self):
        try:
            self.hotkey.stop()
        except Exception:
            pass
        self._save_geometry()
        self.app_config.save()
        try:
            pipeline.release_playback()      # 放掉缓存的合成器，别占着音频设备
        except Exception:
            pass
        try:
            self.master.destroy()
        except tk.TclError:
            pass

    def _save_geometry(self):
        """子类覆写：退出/切模式时把窗口几何记进配置。"""

    def _restore_geometry(self):
        """子类覆写：启动时恢复上次的窗口几何。"""

    # ------------------------------------------------------------ 子类实现
    def build(self):
        raise NotImplementedError

    def refresh_all(self):
        self.refresh_screenshots()
        self.refresh_files()

    def refresh_screenshots(self):
        raise NotImplementedError

    def refresh_files(self):
        raise NotImplementedError

    # ------------------------------------------------------------ 业务
    def process_image(self, image_path):
        if self._busy:
            self.set_status('上一次识别还没结束，请稍候…')
            return
        self.set_busy(f'正在处理：{os.path.basename(image_path)}')
        config = self.app_config

        def work():
            result = pipeline.process_image(
                image_path, config, report=lambda msg: self.post(self.set_status, msg))
            self.post(self._on_process_done, result)

        threading.Thread(target=work, daemon=True).start()

    def _on_process_done(self, result):
        error = result.get('error')
        midi = result.get('midi')
        # 「识别并播放」是显式点的，必须播；auto_play 只管「截完自动识别」这条流程
        wants_play = self._play_after_process or self.app_config.auto_play
        self._play_after_process = False
        if error:
            self.set_idle(error)
            messagebox.showwarning('处理未完成', error, parent=self)
            self.refresh_files()
            return
        self.set_idle(f'完成：{os.path.basename(midi)}' if midi else '完成')
        if self.app_config.auto_render and result.get('xml'):
            self.post(self.render_sheet, result['xml'])
        if midi and wants_play:
            self.play_midi(midi)
        self.refresh_files()

    def current_sf2(self):
        path = find_sf2_path(self.app_config)
        if not path:
            messagebox.showwarning(
                '缺少音色库',
                '没有找到 .sf2 音色库。\n请把音色库放进 soundfonts 目录，或在设置里选择音色库文件夹。',
                parent=self)
            return None
        return path

    def playback_speed(self, midi_path):
        """配置里的目标 BPM → 播放倍率（以曲子自身速度为基准）。"""
        return pipeline.speed_for_bpm(midi_path, getattr(self.app_config, 'bpm', 0))

    def play_midi(self, midi_path):
        sf2 = self.current_sf2()
        if not sf2:
            return
        self.set_busy(f'正在播放：{os.path.basename(midi_path)}')
        volume = self.app_config.volume
        speed = self.playback_speed(midi_path)
        self._stop_event = threading.Event()

        def done(ok=True):
            self.post(self._on_play_finished, ok)

        pipeline.start_play_thread(midi_path, sf2, volume, speed, on_done=done,
                                   stop_event=self._stop_event)

    def stop_playback(self):
        """随时掐掉当前播放。"""
        event = getattr(self, '_stop_event', None)
        if event is not None and not event.is_set():
            event.set()
            self.set_status('正在停止播放…')
            return True
        return False

    def _on_play_finished(self, ok=True):
        if ok:
            self.set_idle('播放结束')
            return
        self.set_idle('播放失败：没有声音输出')
        messagebox.showwarning(
            '播放失败',
            '没有声音输出。常见原因：\n'
            '· 系统没有可用的音频输出设备，或被别的程序独占\n'
            '· 音色库 .sf2 加载失败\n'
            '详情见应用日志（搜「播放」或「音频驱动」）', parent=self)

    def render_sheet(self, xml_path):
        """用 MuseScore 把 MusicXML 渲染成乐谱图片。"""
        musescore = self.app_config.musescore_path
        if not musescore or not os.path.isfile(musescore):
            musescore = self.find_musescore()
        if not musescore:
            messagebox.showwarning(
                'MuseScore 未找到',
                '渲染乐谱图需要 MuseScore。请在「设置 → 设置 MuseScore 路径」中指定。',
                parent=self)
            return
        base_name = os.path.splitext(os.path.basename(xml_path))[0]
        target = os.path.join(SHEET_DIR, base_name + '.png')
        self.set_busy('正在渲染乐谱图…')

        def work():
            error = _render_with_musescore(musescore, xml_path, target)
            self.post(self._on_render_done, error, target)

        threading.Thread(target=work, daemon=True).start()

    def _on_render_done(self, error, target):
        if error:
            self.set_idle('渲染失败')
            messagebox.showerror('渲染失败', error, parent=self)
        else:
            self.set_idle(f'乐谱图已生成：{os.path.basename(target)}')
            self.refresh_files()

    def find_musescore(self):
        try:
            import musescore_cli
            found = musescore_cli.find_musescore()
            if found:
                return found
        except Exception:
            pass
        candidates = [
            r'C:\Program Files\MuseScore 4\bin\MuseScore4.exe',
            r'C:\Program Files\MuseScore 3\bin\MuseScore3.exe',
            os.path.expandvars(r'%LOCALAPPDATA%\Programs\MuseScore 4\bin\MuseScore4.exe'),
            os.path.expandvars(r'%PROGRAMFILES%\MuseScore 4\bin\MuseScore4.exe'),
        ]
        for path in candidates:
            if os.path.isfile(path):
                self.app_config.musescore_path = path
                self.schedule_save()
                return path
        return ''

    # ------------------------------------------------------------ 设置项
    def toggle_engine(self):
        engine = self.app_config.toggle_engine()
        self.app_config.save()
        self.update_engine_ui()
        self.set_status(f'识别引擎已切换为 {ENGINE_LABEL.get(engine, engine)}')

    def change_hotkey(self):
        current = self.app_config.hotkey
        value = simpledialog.askstring(
            '修改截图快捷键', '组合键写法示例：ctrl+shift+z', initialvalue=current, parent=self)
        if value is None:
            return
        value = value.strip()
        if not value:
            messagebox.showwarning('未修改', '快捷键不能为空。', parent=self)
            return
        self.app_config.hotkey = value
        self.app_config.save()
        if self.register_hotkey():
            self.set_status(f'截图快捷键已设为 {describe(value)}')
        else:
            messagebox.showwarning('注册失败',
                                   f'快捷键 {value} 注册失败：{self.hotkey.error}', parent=self)

    def choose_sf2_folder(self):
        folder = filedialog.askdirectory(title='选择包含 .sf2 / .sf3 的文件夹', parent=self)
        if not folder:
            return
        names = [n for n in sorted(os.listdir(folder)) if n.lower().endswith(SOUNDFONT_EXTS)]
        if not names:
            messagebox.showinfo('没有音色库',
                                '这个文件夹里没有 .sf2 / .sf3 文件。', parent=self)
            return
        self.app_config.sf2_folder = folder
        self.app_config.sf2_name = names[0]
        self.app_config.save()
        self.refresh_soundfonts()
        self.set_status(f'已加载 {len(names)} 个音色库')

    def open_soundfont_folder(self):
        """直接打开音色库目录，方便用户往里丢文件。"""
        folder = self.app_config.sf2_folder or SOUNDFONT_DIR
        try:
            os.makedirs(folder, exist_ok=True)
        except Exception as exc:
            messagebox.showwarning('打不开', f'创建目录失败：{exc}', parent=self)
            return
        try:
            os.startfile(folder)      # noqa: S606 - Windows 专用
            self.set_status(f'已打开：{folder}')
        except Exception as exc:
            messagebox.showinfo('音色库目录', f'{folder}\n\n（自动打开失败：{exc}）', parent=self)

    def rescan_soundfonts(self):
        self.refresh_soundfonts()
        self.set_status(f'音色库：{self.app_config.sf2_name or "（没有找到）"}')

    def set_musescore_path(self):
        path = filedialog.askopenfilename(
            title='选择 MuseScore 可执行文件', parent=self,
            filetypes=[('MuseScore', 'MuseScore*.exe'), ('所有文件', '*.*')])
        if not path:
            return
        self.app_config.musescore_path = path
        self.app_config.save()
        self.set_status(f'MuseScore 路径已设置：{os.path.basename(path)}')

    def refresh_soundfonts(self):
        raise NotImplementedError

    def update_engine_ui(self):
        raise NotImplementedError

    # ------------------------------------------------------------ 拖拽
    def setup_dnd(self):
        if DND_FILES is None:
            return
        try:
            self.drop_target_register(DND_FILES)
            self.dnd_bind('<<Drop>>', self.on_drop)
        except Exception:
            pass

    def on_drop(self, event):
        try:
            paths = self.tk.splitlist(event.data)
        except Exception:
            paths = [event.data]
        accepted = 0
        for path in paths:
            path = str(path).strip('{}')
            if not os.path.isfile(path) or not path.lower().endswith(IMAGE_EXTS):
                continue
            dest = pipeline.unique_dest(SCREENSHOT_DIR, os.path.basename(path))
            try:
                with open(path, 'rb') as src, open(dest, 'wb') as dst:
                    dst.write(src.read())
            except OSError as exc:
                messagebox.showerror('导入失败', str(exc), parent=self)
                continue
            accepted += 1
        if accepted:
            self.refresh_screenshots()
            self.set_status(f'已导入 {accepted} 张截图')



# ---------------------------------------------------------------- 辅助

def _render_with_musescore(musescore, xml_path, target_png):
    """用 music21 驱动 MuseScore 输出 PNG，失败返回错误文案。"""
    try:
        from music21 import converter, environment
    except Exception as exc:
        return f'music21 不可用：{exc}'

    out_dir = os.path.dirname(target_png)
    before = set(os.listdir(out_dir)) if os.path.isdir(out_dir) else set()
    try:
        us = environment.UserSettings()
        us['musescoreDirectPNGPath'] = musescore
        score = converter.parse(xml_path)
        score.write('musicxml.png', target_png)
    except Exception as exc:
        return str(exc)

    after = set(os.listdir(out_dir))
    new_files = after - before
    if os.path.basename(target_png) not in new_files:
        pngs = [name for name in new_files if name.lower().endswith('.png')]
        if not pngs:
            return 'MuseScore 没有生成图片。'
        source = os.path.join(out_dir, pngs[0])
        try:
            if os.path.exists(target_png):
                os.remove(target_png)
            os.rename(source, target_png)
            new_files.discard(pngs[0])
        except OSError as exc:
            return str(exc)
    for name in new_files:
        if name == os.path.basename(target_png):
            continue
        try:
            os.remove(os.path.join(out_dir, name))
        except OSError:
            pass
    return None


def _text_dialog(parent, title, body, width=60):
    win = tk.Toplevel(parent)
    win.title(title)
    win.transient(parent)
    win.resizable(False, False)
    frame = tb.Frame(win, padding=24)
    frame.pack(fill=BOTH, expand=YES)
    tb.Label(frame, text=body, justify='left', font=FONT_BODY,
             wraplength=width * 8).pack(anchor='w')
    tb.Button(frame, text='知道了', bootstyle='primary',
              command=win.destroy, width=10).pack(anchor='e', pady=(18, 0))
    win.grab_set()
    win.focus_force()
