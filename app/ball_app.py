# -*- coding: utf-8 -*-
"""悬浮球模式：常驻置顶的小圆球，单击截图、拖动挪位置、右键菜单、双击回完整界面。"""
import datetime
import os
import tkinter as tk

import ttkbootstrap as tb
from ttkbootstrap.constants import BOTH, YES

import pipeline
from base_window import BaseWindow
from settings import (
    APP_NAME, APP_VERSION, ENGINE_LABEL, IMAGE_EXTS, SCREENSHOT_DIR,
)
from ui_kit import (
    _mix, apply_layered_bitmap, ball_sprite, fmt_mmss, make_layered, screen_workarea,
    theme_bg, FONT_NAME, FONT_SMALL, PAD,
)


class BallApp(BaseWindow):
    """悬浮球：常驻置顶的小圆球。

    单击 = 截取五线谱，拖动 = 挪位置（松手吸边），右键 = 菜单，双击 = 回完整界面。
    球面是 PIL 渲染的 RGBA 图，通过 UpdateLayeredWindow 贴到分层窗口上，
    所以边缘是逐像素抗锯齿的，不是被系统硬裁出来的锯齿圆。
    """

    window_title = APP_NAME + ' · 悬浮球'
    BALL = 72                       # 可见球体直径
    MARGIN = 10                     # 四周留白，放柔和投影
    SIZE = BALL + MARGIN * 2        # 窗口尺寸
    geometry_size = f'{SIZE}x{SIZE}'
    min_size = (SIZE, SIZE)

    # 球体自己一套亮一点的颜色，不受主题的暗色调影响（它浮在桌面上，不跟窗口走）
    STATES = {
        'idle': ('#4a90e2', '♪'),
        'busy': ('#f5a623', '…'),
        'done': ('#2fbf8f', '✓'),
        'error': ('#e5534b', '!'),
        'playing': ('#2fbf8f', '♪'),
    }
    TIP = '单击截图 · 拖动挪位置 · 右键菜单 · 双击完整界面'

    def build(self):
        self._state = 'idle'
        self._drag = None
        self._moved = False
        self._click_job = None
        self._tip = None
        self._tip_job = None
        self._pos = None
        self._sprite = None
        self._sprite_glyph = None
        self._ball_photo = None
        self._layered = False
        self._solid = bool(os.environ.get('XIAOHUA_BALL_SOLID'))
        self._auto_var = tk.BooleanVar(value=self.app_config.auto_play)

        self.overrideredirect(True)
        self.attributes('-topmost', True)
        bg = theme_bg() if self._solid else '#000000'
        self.configure(bg=bg)

        self.canvas = tk.Canvas(self, width=self.SIZE, height=self.SIZE, bg=bg,
                                highlightthickness=0, bd=0, cursor='hand2')
        self.canvas.pack(fill=BOTH, expand=YES)
        self.ball_item = self.canvas.create_image(self.SIZE / 2, self.SIZE / 2)

        self.canvas.bind('<Button-1>', self._on_press)
        self.canvas.bind('<B1-Motion>', self._on_drag)
        self.canvas.bind('<ButtonRelease-1>', self._on_release)
        self.canvas.bind('<Double-Button-1>', self._on_double)
        self.canvas.bind('<Button-3>', self._on_menu)
        self.canvas.bind('<Enter>', lambda _e: self._show_tip(self.TIP))
        self.canvas.bind('<Leave>', lambda _e: self._hide_tip())

        self._restore_position()
        self._paint('idle')
        # 窗口 map 之后 HWND 才稳定，多试几次（Tk 可能重建 wrapper 窗口）
        self._safe_after(30, self._setup_layer)
        self._safe_after(200, self._setup_layer)
        self._safe_after(700, self._setup_layer)

    # ------------------------------------------------------------ 分层窗口
    def _hwnd(self):
        try:
            return int(self.wm_frame(), 16)
        except Exception:
            try:
                return self.winfo_id()
            except Exception:
                return None

    def _setup_layer(self):
        """把窗口变成逐像素 alpha 的分层窗口，这样球边才是平滑的。"""
        hwnd = self._hwnd()
        if not hwnd or os.name != 'nt':
            self._layered = False
            return
        ok = make_layered(hwnd) and self._push_layered()
        if not ok:
            # 退路：老方案，系统级裁圆（边缘会有锯齿，但至少不是方块）
            self._layered = False
            self._apply_region()
        self._layered = bool(ok)

    def _push_layered(self):
        if self._sprite is None:
            return False
        hwnd = self._hwnd()
        if not hwnd:
            return False
        # 必须用窗口的真实位置：Tk 的 geometry 和分层位图的位置是两套坐标，
        # 一旦不一致，球就会画在别处（看起来像「球不见了」）。
        return apply_layered_bitmap(hwnd, self._sprite, self._window_origin(hwnd))

    def _window_origin(self, hwnd):
        try:
            import ctypes
            from ctypes import wintypes
            rect = wintypes.RECT()
            ctypes.windll.user32.GetWindowRect(wintypes.HWND(hwnd), ctypes.byref(rect))
            return rect.left, rect.top
        except Exception:
            return self._pos or (self.winfo_x(), self.winfo_y())

    def _apply_region(self):
        """退路：把窗口裁成圆形（没有抗锯齿）。"""
        if os.name != 'nt':
            return
        try:
            import ctypes
        except Exception:
            return
        hwnd = self._hwnd()
        if not hwnd:
            return
        try:
            gdi32, user32 = ctypes.windll.gdi32, ctypes.windll.user32
            rgn = gdi32.CreateEllipticRgn(0, 0, self.SIZE + 1, self.SIZE + 1)
            if rgn and not user32.SetWindowRgn(hwnd, rgn, True):
                gdi32.DeleteObject(rgn)
        except Exception as exc:
            print(f'[ball] 圆形窗口设置失败：{exc}')

    # ------------------------------------------------------------ 外观
    def _paint(self, state):
        self._state = state
        fill, glyph = self.STATES.get(state, self.STATES['idle'])
        self._sprite_glyph = glyph
        self._sprite = ball_sprite(fill, self.BALL, shadow=True, glyph=glyph)
        bg = '#%02x%02x%02x' % _mix(fill, '#000000', 0.12)
        try:
            self.canvas.configure(bg=bg)
        except tk.TclError:
            pass

        if self._layered:
            self._push_layered()
            return
        # 退路：走普通窗口 + Canvas 贴图
        if self._sprite is not None:
            from PIL import ImageTk
            try:
                self._ball_photo = ImageTk.PhotoImage(self._sprite)
                self.canvas.itemconfigure(self.ball_item, image=self._ball_photo)
                self.canvas.configure(bg=bg)
            except Exception as exc:
                print(f'[ball] 贴图失败：{exc}')

    def _reset_state(self):
        if not self._busy:
            self._paint('idle')

    def on_theme_changed(self):
        self._paint(self._state)

    # ------------------------------------------------------------ 气泡
    def _show_tip(self, text, ms=None):
        if not text:
            return None
        self._hide_tip()
        colours = tb.Style().colors
        win = tk.Toplevel(self)
        win.overrideredirect(True)
        win.attributes('-topmost', True)
        try:
            win.attributes('-alpha', 0.97)
        except tk.TclError:
            pass
        frame = tk.Frame(win, bg=colours.bg, highlightthickness=1,
                         highlightbackground=colours.border)
        frame.pack()
        tk.Label(frame, text=text, bg=colours.bg, fg=colours.fg, font=FONT_SMALL,
                 padx=12, pady=7, justify='left').pack()
        win.update_idletasks()
        width, height = win.winfo_width(), win.winfo_height()
        left, top, right, bottom = screen_workarea(self.winfo_x() + self.SIZE // 2,
                                                   self.winfo_y() + self.SIZE // 2)
        x = self.winfo_x() - width - 6
        if x < left + 8:
            x = self.winfo_x() + self.SIZE + 6
        x = min(x, right - width - 8)
        y = self.winfo_y() + (self.SIZE - height) // 2
        y = max(top + 8, min(y, bottom - height - 8))
        win.geometry(f'+{x}+{y}')
        self._tip = win
        if ms:
            self._tip_job = self.after(ms, self._hide_tip)
        return win

    def _hide_tip(self):
        if self._tip_job is not None:
            try:
                self.after_cancel(self._tip_job)
            except Exception:
                pass
            self._tip_job = None
        if self._tip is not None:
            try:
                self._tip.destroy()
            except tk.TclError:
                pass
            self._tip = None

    def _toast(self, text, ms=2400):
        if text:
            self._show_tip(text, ms)

    # ------------------------------------------------------------ 状态文案
    def set_status(self, text, hint=None):
        self._toast(text)

    def set_busy(self, text=None):
        self._busy = True
        self._paint('busy')
        self._toast(text or '处理中…')

    def set_idle(self, text=None):
        self._busy = False
        failed = bool(text) and any(word in text for word in ('失败', '错误', '未找到', '不可用'))
        self._paint('error' if failed else 'done')
        self._toast(text or '完成')
        self._safe_after(1800, self._reset_state)

    def _safe_after(self, ms, func):
        try:
            return self.after(ms, func)
        except tk.TclError:
            return None

    def on_hotkey_state(self, ok):
        pass

    # ------------------------------------------------------------ 位置
    def _restore_position(self):
        x = y = None
        raw = (self.app_config.ball_pos or '').strip()
        if ',' in raw:
            try:
                x, y = (int(part) for part in raw.split(',', 1))
            except ValueError:
                x = y = None
        if x is None or y is None:
            left, top, right, bottom = screen_workarea()
            x = right - self.SIZE - 48
            y = top + int((bottom - top) * 0.42)
        # 夹到「球所在的那块屏」的工作区里：多显示器下副屏也能放
        left, top, right, bottom = screen_workarea(x + self.SIZE // 2, y + self.SIZE // 2)
        x = max(left, min(x, right - self.SIZE))
        y = max(top, min(y, bottom - self.SIZE))
        self._pos = (x, y)
        self.geometry(f'{self.SIZE}x{self.SIZE}+{x}+{y}')

    def _move_to(self, x, y):
        """记录并移动。geometry() 之后 winfo_x() 可能还是旧值，所以自己记一份。"""
        self._pos = (int(x), int(y))
        try:
            self.geometry(f'+{int(x)}+{int(y)}')
        except tk.TclError:
            return
        if self._layered:
            self._push_layered()

    def _save_position(self):
        try:
            x, y = self._pos or (self.winfo_x(), self.winfo_y())
            self.app_config.ball_pos = f'{x},{y}'
            self.schedule_save()
        except tk.TclError:
            pass

    def _snap_to_edge(self):
        x, y = self._pos or (self.winfo_x(), self.winfo_y())
        left, top, right, bottom = screen_workarea(x + self.SIZE // 2, y + self.SIZE // 2)
        if x - left < 24:
            x = left + 10
        elif right - (x + self.SIZE) < 24:
            x = right - self.SIZE - 10
        if y - top < 24:
            y = top + 10
        elif bottom - (y + self.SIZE) < 24:
            y = bottom - self.SIZE - 10
        self._move_to(x, y)

    # ------------------------------------------------------------ 拖拽 / 点击
    def _on_press(self, event):
        self._hide_tip()
        self._drag = (event.x_root, event.y_root, self.winfo_x(), self.winfo_y())
        self._moved = False

    def _on_drag(self, event):
        if not self._drag:
            return
        start_x, start_y, win_x, win_y = self._drag
        dx, dy = event.x_root - start_x, event.y_root - start_y
        if abs(dx) > 3 or abs(dy) > 3:
            self._moved = True
        if self._moved:
            self._move_to(win_x + dx, win_y + dy)

    def _on_release(self, _event=None):
        moved = self._moved
        self._drag = None
        self._moved = False
        if moved:
            self._snap_to_edge()
            self._save_position()
            return
        # 延后一点再截图，好让双击有机会取消它
        self._click_job = self.after(200, self._do_click)

    def _do_click(self):
        self._click_job = None
        self.area_capture()

    def _on_double(self, _event=None):
        if self._click_job is not None:
            try:
                self.after_cancel(self._click_job)
            except Exception:
                pass
            self._click_job = None
        self.switch_mode()

    # ------------------------------------------------------------ 截图
    def area_capture(self):
        if self.capturing:
            return
        self.capturing = True
        self._hide_tip()
        self._paint('busy')
        try:
            self.withdraw()
        except tk.TclError:
            pass
        self.after(150, self._open_capture)

    def on_capture_done(self, path):
        self.capturing = False
        try:
            self.deiconify()
            self.lift()
            self.attributes('-topmost', True)
        except tk.TclError:
            pass
        self._safe_after(30, self._setup_layer)
        if not path:
            self._paint('idle')
            self._toast('已取消截图')
            return
        self._paint('done')
        self._toast('已保存 ' + os.path.basename(path))
        self._safe_after(1200, self._reset_state)
        if self.app_config.auto_play:
            self.handle_new_image(path)

    # ------------------------------------------------------------ 菜单
    def _build_menu(self):
        colours = tb.Style().colors
        engine = self.app_config.engine
        menu = tk.Menu(self, tearoff=False, bd=0, bg=colours.bg, fg=colours.fg,
                       activebackground=colours.primary, activeforeground=colours.selectfg)
        menu.add_command(label='截取五线谱', command=self.area_capture)
        menu.add_command(label='从剪贴板导入', command=self.clipboard_add)
        menu.add_separator()
        menu.add_checkbutton(label='截完自动识别', variable=self._auto_var,
                             command=self._on_auto_toggle)
        menu.add_command(label=f'引擎：{ENGINE_LABEL.get(engine, engine)} ›',
                         command=self.toggle_engine)
        menu.add_command(label='切换亮/暗主题', command=self.toggle_theme)
        menu.add_separator()
        menu.add_command(label='打开完整界面', command=self.switch_mode)
        menu.add_command(label='打开截图文件夹', command=lambda: self.open_folder(SCREENSHOT_DIR))
        menu.add_separator()
        menu.add_command(label='退出程序', command=self.on_close)
        return menu

    def _on_menu(self, event):
        menu = self._build_menu()
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _on_auto_toggle(self):
        self.app_config.auto_play = bool(self._auto_var.get())
        self.app_config.save()
        self._toast('截完自动识别：' + ('开' if self.app_config.auto_play else '关'))

    def toggle_engine(self):
        super().toggle_engine()
        self._toast('引擎：' + ENGINE_LABEL.get(self.app_config.engine, self.app_config.engine))

    def open_folder(self, directory):
        try:
            os.startfile(directory)  # noqa: S606
        except Exception as exc:
            self._toast(f'打开失败：{exc}')

    # ------------------------------------------------------------ 其它
    def clipboard_add(self):
        try:
            from PIL import ImageGrab
        except Exception:
            self._toast('缺少 Pillow，读不了剪贴板')
            return
        img = ImageGrab.grabclipboard()
        if img is None:
            self._toast('剪贴板里没有图片')
            return
        if isinstance(img, list):
            self._toast('剪贴板里是文件，请拖进来')
            return
        stamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        path = os.path.join(SCREENSHOT_DIR, f'clip_{stamp}.png')
        img.save(path)
        self._toast('已导入 ' + os.path.basename(path))
        if self.app_config.auto_play:
            self.handle_new_image(path)

    def play_midi(self, midi_path):
        self._paint('playing')
        self._toast('♪  ' + os.path.basename(midi_path))
        super().play_midi(midi_path)

    def _on_process_done(self, result):
        error = result.get('error')
        midi = result.get('midi')
        if error:
            self._paint('error')
            self._toast(error)
            self._safe_after(2200, self._reset_state)
            return
        self._paint('done')
        self._toast('完成：' + os.path.basename(midi) if midi else '完成')
        self._safe_after(1400, self._reset_state)
        if midi and self.app_config.auto_play:
            self.play_midi(midi)

    def refresh_screenshots(self):
        pass

    def refresh_files(self):
        pass

    def update_engine_ui(self):
        pass

    def refresh_soundfonts(self):
        pass

    def handle_new_image(self, path):
        self.process_image(path)


