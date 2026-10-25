# -*- coding: utf-8 -*-

import subprocess
import sys
import os
import glob
import shutil
import cv2
import numpy as np

from settings import (AUDIVERIS_TEMP_DIR, HOMR_WORK_DIR, PREPROCESSED_DIR,
                      STAGING_DIR)

if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def resource_path(relative_path):
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(BASE_DIR, relative_path)


TEMP_DIR = AUDIVERIS_TEMP_DIR

# 哪些后缀算「图片」——识别过程中被引擎顺手写出来的图要挪走，不能留在截图目录
IMAGE_SUFFIXES = ('.jpg', '.jpeg', '.png', '.bmp', '.tif', '.tiff', '.webp')


def _safe_makedirs(path):
    try:
        os.makedirs(path, exist_ok=True)
    except OSError:
        pass


def _move_new_images(source_dir, target_dir, before):
    """把识别期间新出现在 source_dir 里的图片移到 target_dir。

    引擎（尤其 homr）会把带五线谱的切片图写在自己的工作目录里；如果工作目录就是
    截图目录，这些图就会和原始截图混在一起，甚至出现在界面缩略图里。
    """
    moved = []
    try:
        current = set(os.listdir(source_dir))
    except OSError:
        return moved
    for name in sorted(current - before):
        if not name.lower().endswith(IMAGE_SUFFIXES):
            continue
        src = os.path.join(source_dir, name)
        dst = os.path.join(target_dir, name)
        try:
            if os.path.exists(dst):
                os.remove(dst)
            shutil.move(src, dst)
            moved.append(name)
        except OSError as exc:
            print(f'[清理] 移动 {name} 失败: {exc}')
    if moved:
        print(f'[清理] 已将 {len(moved)} 个识别中间图移到 {target_dir}')
    return moved


def _pad_for_audiveris(image_path, tag=''):
    """把碎片图放大并补白边，让 Audiveris 当成一页纸。"""
    try:
        with open(image_path, 'rb') as fp:
            data = fp.read()
        array = np.frombuffer(data, np.uint8)
        img = cv2.imdecode(array, cv2.IMREAD_GRAYSCALE)
        if img is None:
            return image_path
        height, width = img.shape
        # 太小的放大到高度 600（Audiveris 对碎片很敏感）
        if height < 600:
            ratio = 600.0 / height
            img = cv2.resize(img, (int(width * ratio), 600),
                             interpolation=cv2.INTER_CUBIC)
            height, width = img.shape
        border = max(160, int(height * 0.22))
        padded = cv2.copyMakeBorder(img, border, border, border, border,
                                    cv2.BORDER_CONSTANT, value=255)
        stem = os.path.splitext(os.path.basename(image_path))[0]
        out_path = os.path.join(PREPROCESSED_DIR, f'{stem}{tag}_sheet.png')
        _safe_makedirs(PREPROCESSED_DIR)
        cv2.imwrite(out_path, padded)
        return out_path
    except Exception as exc:
        print(f'补白失败：{exc}')
        return image_path


def preprocess_image(image_path, output_path=None):

    try:
        with open(image_path, 'rb') as f:
            data = f.read()
        img_array = np.frombuffer(data, np.uint8)
        img = cv2.imdecode(img_array, cv2.IMREAD_GRAYSCALE)
    except Exception as e:
        print(f'预处理：读取图片失败，错误: {e}')
        return image_path

    if img is None:
        print('预处理：无法解码图片，返回原图')
        return image_path

    h, w = img.shape
    target_width = 1200
    if w < target_width:
        scale = target_width / w
        new_w = int(w * scale)
        new_h = int(h * scale)
        img = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_CUBIC)

    block_size = max(11, (img.shape[0] // 20) | 1)
    binary = cv2.adaptiveThreshold(img, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                   cv2.THRESH_BINARY, block_size, 2)
    kernel = np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]])
    sharpened = cv2.filter2D(binary, -1, kernel)

    if output_path is None:
        _safe_makedirs(PREPROCESSED_DIR)
        stem = os.path.splitext(os.path.basename(image_path))[0]
        output_path = os.path.join(PREPROCESSED_DIR, f'{stem}_pre.png')
    _safe_makedirs(os.path.dirname(output_path) or '.')
    cv2.imwrite(output_path, sharpened)
    return output_path


def recognize(image_path, preprocess=True, engine='audiveris'):
    engine = (engine or '').strip().lower()
    print(f'[recognize] 当前引擎：{engine}')
    if engine == 'homr':
        return recognize_homr(image_path)
    if engine != 'audiveris':
        # 原版这里会调用未定义的 recognize_oemer()，直接把识别流程抛成 NameError；
        # 而打包里的 oemer 只是一个残缺的空壳包，也不具备可用能力，所以明确回退。
        print(f'[recognize] 不支持的引擎 {engine!r}，回退到 audiveris')

    print(f'[识别] 开始处理: {image_path}')
    if not os.path.exists(image_path):
        print(f'错误：找不到图片文件 {image_path}')
        return None


    temp_dir = TEMP_DIR
    if os.path.exists(temp_dir):
        shutil.rmtree(temp_dir, ignore_errors=True)
    _safe_makedirs(temp_dir)


    if preprocess:
        base_name = os.path.splitext(os.path.basename(image_path))[0]
        _safe_makedirs(PREPROCESSED_DIR)
        # 预处理图单独放到 preprocessed/，绝不写进截图目录
        preprocessed_image = os.path.join(PREPROCESSED_DIR, f'{base_name}_pre.png')
        preprocessed_image = preprocess_image(image_path, preprocessed_image)
        preprocessed_image = _pad_for_audiveris(preprocessed_image)
    else:
        preprocessed_image = image_path


    audiveris_exe = os.environ.get('XIAOHUA_AUDIVERIS') or resource_path(
        os.path.join('Audiveris', 'Audiveris.exe'))

    if not os.path.exists(audiveris_exe):
        print('Audiveris 未找到')
        shutil.rmtree(temp_dir, ignore_errors=True)
        return None


    cmd = [audiveris_exe, '-batch', '-export', '-output', temp_dir, preprocessed_image]
    print(f'[识别] 执行命令: {" ".join(cmd)}')

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        print(f'[识别] Audiveris 返回码: {result.returncode}')
        if result.stdout:
            print(f'[stdout] {result.stdout[-500:]}')
        if result.stderr:
            print(f'[stderr] {result.stderr[-500:]}')
    except subprocess.TimeoutExpired:
        print('错误：Audiveris 进程超时（超过 2 分钟）')
        shutil.rmtree(temp_dir, ignore_errors=True)
        return None
    except FileNotFoundError:
        print('错误：找不到 Audiveris.exe')
        shutil.rmtree(temp_dir, ignore_errors=True)
        return None

    xml_files = glob.glob(os.path.join(temp_dir, '*.xml')) + glob.glob(os.path.join(temp_dir, '*.mxl'))
    xml_files = [f for f in xml_files if not f.lower().endswith('.omr')]

    if not xml_files:
        print('警告：未找到 Audiveris 生成的 MusicXML 文件。')
        shutil.rmtree(temp_dir, ignore_errors=True)
        return None

    generated = xml_files[0]
    # 先落到 staging，再由 pipeline 归入 xml_outputs；程序根目录保持干净
    _safe_makedirs(STAGING_DIR)
    dest = os.path.join(STAGING_DIR, os.path.basename(generated))
    if os.path.abspath(generated) != os.path.abspath(dest):
        shutil.move(generated, dest)
    generated = dest

    if os.path.getsize(generated) < 100:
        print('警告：生成的 MusicXML 文件过小，可能识别失败。')
        os.remove(generated)
        shutil.rmtree(temp_dir, ignore_errors=True)
        return None

    print(f'MusicXML 已生成为: {generated}')
    shutil.rmtree(temp_dir, ignore_errors=True)
    return generated


def recognize_homr(image_path):
    import io, sys, os, glob, traceback, shutil


    image_path = os.path.abspath(image_path)
    screenshot_dir = os.path.dirname(image_path)
    homr_output_dir = os.path.join(BASE_DIR, 'homr_output')
    work_dir = HOMR_WORK_DIR
    _safe_makedirs(work_dir)
    _safe_makedirs(homr_output_dir)
    # homr 的工作目录就是它写中间图的地方；放在 HOMR_WORK_DIR，
    # 结果 XML 可能落在工作目录、homr_output 或截图目录，三处都找。
    search_dirs = [work_dir, homr_output_dir, screenshot_dir, BASE_DIR]
    images_before = set()
    try:
        images_before = set(os.listdir(screenshot_dir))
    except OSError:
        pass


    base_name = os.path.splitext(os.path.basename(image_path))[0]
    for ext in ('.musicxml', '.mxl', '.xml'):
        for d in search_dirs:
            fp = os.path.join(d, base_name + ext)
            if os.path.isfile(fp):
                try:
                    os.remove(fp)
                except:
                    pass


    if getattr(sys, 'frozen', False):
        schema_dir = os.path.join(sys._MEIPASS, 'musicxml', 'generate_classes')
        rapidocr_dir = os.path.join(sys._MEIPASS, 'rapidocr_onnxruntime')
    else:
        import musicxml
        schema_dir = os.path.join(os.path.dirname(musicxml.__file__), 'generate_classes')
        import rapidocr_onnxruntime
        rapidocr_dir = os.path.dirname(rapidocr_onnxruntime.__file__)
    os.environ['MUSICXML_XSD_DIR'] = schema_dir
    os.environ['MUSICXML_SCHEMA_PATH'] = schema_dir
    os.environ['RAPIDOCR_PATH'] = rapidocr_dir
    os.environ['RAPIDOCR_MODEL_DIR'] = rapidocr_dir


    try:
        from homr.main import main as homr_main
    except Exception as e:
        print(f'[homr] 导入失败: {e}')
        traceback.print_exc()
        return None


    old_cwd = os.getcwd()
    os.chdir(work_dir)
    old_argv = sys.argv
    sys.argv = ['homr', image_path]

    try:
        old_stdout = sys.stdout
        sys.stdout = buffer = io.StringIO()
        print('[homr] 调用 main...', flush=True)
        try:
            homr_main()
        except SystemExit:
            pass
        finally:
            sys.stdout = old_stdout
            out = buffer.getvalue()
            if out.strip():
                print(out, flush=True)
    except Exception as e:
        print(f'[homr] 运行错误: {e}')
        traceback.print_exc()
    finally:
        os.chdir(old_cwd)
        sys.argv = old_argv
        # 不管成功失败，都把这次识别新冒到截图目录里的图挪走
        _move_new_images(screenshot_dir, work_dir, images_before)

    candidates = []
    for d in search_dirs:
        for ext in ('.musicxml', '.mxl', '.xml'):
            candidates.extend(glob.glob(os.path.join(d, base_name + '*' + ext)))
    candidates = [f for f in candidates if not f.endswith('.omr')]

    if not candidates:
        print('[homr] 未找到 XML', flush=True)
        return None

    src = candidates[0]
    _safe_makedirs(STAGING_DIR)
    dest = os.path.join(STAGING_DIR, os.path.basename(src))
    if os.path.abspath(src) != os.path.abspath(dest):
        shutil.move(src, dest)
    print(f'[homr] 生成 XML: {dest}', flush=True)
    return dest
