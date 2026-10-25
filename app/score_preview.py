# -*- coding: utf-8 -*-
"""把 MIDI 画成一份简易五线谱，用来核对识别结果对不对。

为什么自己画：环境里没有 MuseScore，没法把 MusicXML 排成真谱。
但核对「音高/节奏对不对」不需要排版精度——五线谱 + 符头 + 小节线就够。
"""
import os

import mido
from PIL import Image, ImageDraw, ImageFont

LINE_GAP = 12          # 相邻谱线间距
STEP = LINE_GAP // 2   # 相邻音级（一线一间）的垂直距离
PX_PER_BEAT = 44
LEFT = 74
RIGHT = 24

LETTERS = 'CDEFGAB'
TREBLE_BOTTOM = (4, 'E')   # 高音谱表最下一线
BASS_BOTTOM = (2, 'G')     # 低音谱表最下一线
PC_TO_LETTER = {
    0: ('C', 0), 1: ('C', 1), 2: ('D', 0), 3: ('D', 1), 4: ('E', 0), 5: ('F', 0),
    6: ('F', 1), 7: ('G', 0), 8: ('G', 1), 9: ('A', 0), 10: ('A', 1), 11: ('B', 0),
}


def _font(size):
    for name in ('msyh.ttc', 'simhei.ttf', 'arial.ttf'):
        path = os.path.join(os.environ.get('WINDIR', r'C:\Windows'), 'Fonts', name)
        if os.path.isfile(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()


def read_notes(midi_path):
    """读出 (起始拍, 时值拍, 音高)。"""
    midi = mido.MidiFile(midi_path)
    ticks_per_beat = midi.ticks_per_beat or 480
    notes = []
    for track in midi.tracks:
        now = 0
        opened = {}
        for msg in track:
            now += msg.time
            if msg.type == 'note_on' and msg.velocity > 0:
                opened.setdefault(msg.note, []).append(now)
            elif msg.type == 'note_off' or (msg.type == 'note_on' and msg.velocity == 0):
                starts = opened.get(msg.note)
                if starts:
                    start = starts.pop(0)
                    notes.append((start / ticks_per_beat,
                                  max(0.08, (now - start) / ticks_per_beat), msg.note))
    notes.sort(key=lambda item: (item[0], item[2]))
    return notes


def _diatonic(octave, letter):
    return octave * 7 + LETTERS.index(letter)


def _scientific(midi_pitch):
    """MIDI 60 = C4（科学音高），注意 MIDI 的八度编号比这大 1。"""
    return midi_pitch // 12 - 1, midi_pitch % 12


def _clef_for(notes):
    if not notes:
        return 'treble'
    pitches = [item[2] for item in notes]
    low, high = min(pitches), max(pitches)
    if high - low <= 22:
        return 'treble' if (low + high) / 2 >= 57 else 'bass'
    if high <= 62:
        return 'bass'
    return 'grand'


def _steps(pitch, clef, staff_index):
    """相对该谱表最下一线有多少个音级（正数往上）。"""
    octave, pitch_class = _scientific(pitch)
    letter, sharp = PC_TO_LETTER[pitch_class]
    reference = TREBLE_BOTTOM if (clef == 'treble' or (clef == 'grand' and staff_index == 0)) \
        else BASS_BOTTOM
    return _diatonic(octave, letter) - _diatonic(*reference), sharp


CLEF_GLYPHS = {'treble': '\U0001D11E', 'bass': '\U0001D122'}


def _clef_font(size):
    for name in ('seguisym.ttf', 'SEGUIEMJ.TTF', 'arialuni.ttf'):
        path = os.path.join(os.environ.get('WINDIR', r'C:\Windows'), 'Fonts', name)
        if os.path.isfile(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return None


def draw_clef(draw, x, bottom, kind, ink, staff_height):
    """在谱表左侧画谱号；字体缺失时退回文字。"""
    font = _clef_font(int(staff_height * 1.35))
    if font is not None:
        glyph = CLEF_GLYPHS.get(kind)
        try:
            y = bottom - staff_height * (1.0 if kind == 'treble' else 0.62)
            draw.text((x, y), glyph, fill=ink, font=font)
            return
        except Exception:
            pass
    draw.text((x, bottom - 3 * LINE_GAP - 8), '高音' if kind == 'treble' else '低音',
              fill=ink, font=_font(11))


def render_preview(midi_path, theme='light'):
    """画一张简易五线谱，返回 PIL Image。"""
    notes = read_notes(midi_path)
    clef = _clef_for(notes)
    staves = 2 if clef == 'grand' else 1

    items = []
    for start, duration, pitch in notes:
        staff_index = 0 if (clef != 'grand' or pitch >= 60) else 1
        steps, sharp = _steps(pitch, clef, staff_index)
        items.append({'beat': start, 'dur': duration, 'staff': staff_index,
                      'steps': steps, 'sharp': sharp, 'pitch': pitch})

    # 每张谱表按它自己的音域留上方空间
    tops = []
    for index in range(staves):
        subset = [item['steps'] for item in items if item['staff'] == index]
        tops.append(max(subset) if subset else 4)
    headroom = max(0, max(tops) - 5) * STEP + 34

    staff_height = 4 * LINE_GAP
    staff_boxes = []
    for index in range(staves):
        bottom = headroom + index * (staff_height + 38) + staff_height
        staff_boxes.append(bottom)

    total_beats = max([item['beat'] + item['dur'] for item in items], default=4)
    width = max(520, int(LEFT + max(4, total_beats + 1) * PX_PER_BEAT + RIGHT))
    height = staff_boxes[-1] + 30

    paper = '#ffffff' if theme != 'dark' else '#141414'
    ink = '#111111' if theme != 'dark' else '#eaeaea'
    image = Image.new('RGB', (width, height), paper)
    draw = ImageDraw.Draw(image)
    small = _font(11)

    for bottom in staff_boxes:
        for line in range(5):
            y_line = bottom - line * LINE_GAP
            draw.line([(LEFT - 10, y_line), (width - RIGHT, y_line)], fill=ink, width=1)

    for index, bottom in enumerate(staff_boxes):
        kind = 'treble' if (clef == 'treble' or (clef == 'grand' and index == 0)) else 'bass'
        draw_clef(draw, LEFT - 40, bottom, kind, ink, staff_height)

    # 小节线（按 4/4 估）
    for beat in range(4, int(total_beats) + 8, 4):
        x = LEFT + beat * PX_PER_BEAT
        if x >= width - RIGHT:
            break
        for bottom in staff_boxes:
            draw.line([(x, bottom - staff_height), (x, bottom)], fill=ink, width=1)

    used = {}
    for item in items:
        bottom = staff_boxes[item['staff']]
        y_note = bottom - item['steps'] * STEP
        key = (item['staff'], round(item['beat'], 2))
        offset = used.get(key, 0)
        used[key] = offset + 1
        x = LEFT + item['beat'] * PX_PER_BEAT + offset * 11
        if x > width - RIGHT - 8 or y_note < 4 or y_note > height - 4:
            continue

        top_line, bottom_line = bottom - staff_height, bottom
        step_y = top_line - LINE_GAP
        while y_note <= step_y:
            draw.line([(x - 7, step_y), (x + 7, step_y)], fill=ink, width=1)
            step_y -= LINE_GAP
        step_y = bottom_line + LINE_GAP
        while y_note >= step_y:
            draw.line([(x - 7, step_y), (x + 7, step_y)], fill=ink, width=1)
            step_y += LINE_GAP

        draw.ellipse([x - 5, y_note - 3, x + 5, y_note + 3], outline=ink, fill=ink)
        if item['dur'] >= 0.5:
            if item['steps'] < 5:
                draw.line([(x + 5, y_note), (x + 5, y_note - 3 * LINE_GAP)], fill=ink, width=1)
            else:
                draw.line([(x - 5, y_note), (x - 5, y_note + 3 * LINE_GAP)], fill=ink, width=1)
        if item['sharp']:
            draw.text((x - 13, y_note - 8), '#', fill=ink, font=small)

    draw.text((6, 6), '识别结果（对照原谱核对音高/节奏）', fill=ink, font=small)
    return image


def render_to_file(midi_path, out_path, theme='light'):
    image = render_preview(midi_path, theme=theme)
    image.save(out_path)
    return out_path


if __name__ == '__main__':
    import sys
    if len(sys.argv) < 2:
        print('用法: python score_preview.py <midi> [out.png]')
        raise SystemExit(2)
    out = sys.argv[2] if len(sys.argv) > 2 else 'preview.png'
    render_to_file(sys.argv[1], out)
    print('已生成', out)


def save_musicxml(source, target):
    """把 MusicXML / MXL 统一存成真正的 MusicXML 文本。

    Audiveris 输出的是 .mxl（zip 包），直接改名成 .musicxml 会让
    MuseScore 读到二进制内容然后卡住。
    """
    import shutil
    import zipfile
    if not source or not os.path.isfile(source):
        return False
    folder = os.path.dirname(target)
    if folder:
        os.makedirs(folder, exist_ok=True)
    if source.lower().endswith('.mxl'):
        try:
            with zipfile.ZipFile(source) as archive:
                inner = [name for name in archive.namelist() if name.endswith('.xml')]
                if not inner:
                    return False
                data = archive.read(inner[0])
            with open(target, 'wb') as handle:
                handle.write(data)
            return True
        except Exception:
            return False
    try:
        shutil.copyfile(source, target)
        return True
    except Exception:
        return False


class PreviewWindow:
    """一个常驻小窗：每次生成新的试听音频，就把对应的五线谱画进来。"""

    def __init__(self, master, theme='light', on_action=None):
        self.master = master
        self.theme = theme
        self.top = None
        self._photo = None
        self.image = None
        self.on_action = on_action      # (action) -> None，按钮回调

    def _ensure(self):
        import ttkbootstrap as tb
        if self.top is not None and self.top.winfo_exists():
            return
        self.top = tb.Toplevel(self.master)
        self.top.title('识别结果 · 五线谱')
        self.top.attributes('-topmost', True)
        try:
            self.top.configure(padx=10, pady=10)
        except Exception:
            pass
        self.label = tb.Label(self.top)
        self.label.pack()
        self.actions = tb.Frame(self.top)
        self.actions.pack(fill='x', pady=(6, 0))
        for text, action, style, width in (
                ('↑ 八度', 'octave_up', 'secondary-outline', 8),
                ('↓ 八度', 'octave_down', 'secondary-outline', 8),
                ('♯ 半音', 'sharp', 'secondary-outline', 8),
                ('♭ 半音', 'flat', 'secondary-outline', 8),
                ('换引擎重试', 'retry_engine', 'info-outline', 11),
                ('MuseScore 编辑', 'open_musescore', 'warning-outline', 14),
                ('重新载入', 'reload', 'success-outline', 10)):
            button = tb.Button(self.actions, text=text, bootstyle=style, width=width,
                               command=lambda a=action: self._fire(a))
            button.pack(side='left', padx=(0, 6))
        self.notice = tb.Label(self.top, text='', font=('Microsoft YaHei UI', 9, 'bold'),
                               bootstyle='warning')
        self.notice.pack(anchor='w', pady=(6, 0))
        self.info = tb.Label(self.top, text='', font=('Microsoft YaHei UI', 9),
                             bootstyle='secondary')
        self.info.pack(anchor='w', pady=(6, 0))
        self.hint = tb.Label(self.top, text='点右上角关闭；下次点谱会自动更新',
                             font=('Microsoft YaHei UI', 9), bootstyle='secondary')
        self.hint.pack(anchor='w')
        self.top.protocol('WM_DELETE_WINDOW', self.hide)

    def show(self, midi_path, theme=None, note_count=None):
        from PIL import ImageTk
        theme = theme or self.theme
        self._ensure()
        image = render_preview(midi_path, theme=theme)
        self.image = image
        self._photo = ImageTk.PhotoImage(image)
        self.label.configure(image=self._photo)
        count = note_count if note_count is not None else len(read_notes(midi_path))
        clef_name = {'treble': '高音谱表', 'bass': '低音谱表', 'grand': '大谱表'}
        clef = _clef_for(read_notes(midi_path))
        self.info.configure(text=f'{count} 个音 · {clef_name.get(clef, clef)} · '
                                f'来自 {os.path.basename(midi_path)}')
        self._place()
        self.top.deiconify()
        self.top.lift()
        return image

    def _max_height(self):
        """预览图的最高高度（屏幕装得下即可，留出窗体和按钮的位置）。"""
        try:
            screen = self.top.winfo_screenheight() if self.top else 900
        except Exception:
            screen = 900
        return max(360, int(screen * 0.78))

    def show_image(self, png_path, caption=''):
        """直接显示一张已经排好的图（MuseScore 输出）。"""
        from PIL import Image, ImageTk
        if not png_path or not os.path.isfile(png_path):
            return None
        self._ensure()
        image = Image.open(png_path)
        if image.width > 1100:
            ratio = 1100 / image.width
            image = image.resize((1100, max(1, int(image.height * ratio))), Image.LANCZOS)
        limit = self._max_height()
        if image.height > limit:
            ratio = limit / image.height
            image = image.resize((max(1, int(image.width * ratio)), limit), Image.LANCZOS)
        self.image = image
        self._photo = ImageTk.PhotoImage(image)
        self.label.configure(image=self._photo)
        self.info.configure(text=caption or os.path.basename(png_path))
        self._place()
        self.top.deiconify()
        self.top.lift()
        return image

    def show_pair(self, original_png, engraved_png, caption=''):
        """原谱截图（上）+ 识别结果（下），中间画一条分隔线。"""
        from PIL import Image, ImageDraw, ImageTk
        if not engraved_png or not os.path.isfile(engraved_png):
            return self.show_image(original_png, caption)
        parts = []
        try:
            if original_png and os.path.isfile(original_png):
                parts.append(Image.open(original_png).convert('RGB'))
            parts.append(Image.open(engraved_png).convert('RGB'))
        except Exception:
            return self.show_image(engraved_png, caption)

        width = max(part.width for part in parts)
        width = min(max(width, 520), 1100)
        scaled = []
        for part in parts:
            if part.width != width:
                ratio = width / part.width
                part = part.resize((width, max(1, int(part.height * ratio))), Image.LANCZOS)
            scaled.append(part)

        gap, label_height = 10, 16
        height = sum(part.height for part in scaled) + gap * (len(scaled) + 1) + label_height * len(scaled)
        canvas = Image.new('RGB', (width, height), 'white')
        draw = ImageDraw.Draw(canvas)
        font = _font(11)
        ink = '#444444'
        y = 4
        titles = ['原谱（点选的那一段）', '识别结果'] if len(scaled) == 2 else ['识别结果']
        for index, part in enumerate(scaled):
            draw.text((4, y), titles[index], fill=ink, font=font)
            y += label_height
            canvas.paste(part, (0, y))
            y += part.height + gap
            if index == 0 and len(scaled) == 2:
                draw.line([(0, y - gap // 2), (width, y - gap // 2)], fill='#cccccc', width=1)

        # 太高就整体缩小：窗口装不下的部分会被直接截掉，看起来像「下半截没了」
        limit = self._max_height()
        if limit and canvas.height > limit:
            ratio = limit / canvas.height
            canvas = canvas.resize((max(1, int(canvas.width * ratio)), limit), Image.LANCZOS)

        self._ensure()
        self.image = canvas
        self._photo = ImageTk.PhotoImage(canvas)
        self.label.configure(image=self._photo)
        self.info.configure(text=caption or '上：原谱　下：识别结果')
        self._place()
        self.top.deiconify()
        self.top.lift()
        return canvas

    def _fire(self, action):
        if not self.on_action:
            return
        try:
            self.on_action(action)
        except Exception as exc:
            try:
                self.info.configure(text=f'操作失败：{type(exc).__name__}: {exc}')
            except Exception:
                pass

    def set_notice(self, text=''):
        """「有改动」这类提示；空字符串表示清掉。"""
        try:
            self.notice.configure(text=text or '')
        except Exception:
            pass

    def set_status(self, text):
        try:
            self.info.configure(text=text)
        except Exception:
            pass

    def _place(self):
        try:
            self.top.update_idletasks()
            width = self.top.winfo_reqwidth()
            height = self.top.winfo_reqheight()
            x = self.master.winfo_rootx() + max(0, self.master.winfo_width() - width - 40)
            y = self.master.winfo_rooty() + 110
            self.top.geometry(f'+{max(0, x)}+{max(0, y)}')
        except Exception:
            pass

    def hide(self):
        if self.top is not None and self.top.winfo_exists():
            self.top.withdraw()

    def destroy(self):
        if self.top is not None and self.top.winfo_exists():
            self.top.destroy()
        self.top = None
