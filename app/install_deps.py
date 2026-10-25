# -*- coding: utf-8 -*-
"""依赖检查与引导：本程序不打包 homr / MuseScore，用官方渠道自取。

用法：
    python install_deps.py            # 只检查，打印状态与官方下载页
    python install_deps.py --open     # 检查后打开缺失项的官方下载页
    python install_deps.py --json     # 机器可读输出（给界面用）
"""
import argparse
import json
import os
import shutil
import sys
import webbrowser

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE) if os.path.basename(HERE) == 'app' else HERE

LINKS = {
    'homr': ('homr（谱面识别，AGPL-3.0）', 'https://github.com/liebharc/homr'),
    'musescore': ('MuseScore（排版，GPL-3.0）', 'https://musescore.org/download'),
    'audiveris': ('Audiveris（可选识别引擎，AGPL-3.0）',
                  'https://github.com/Audiveris/audiveris/releases'),
    'soundfont': ('音色库 SoundFont（GeneralUser GS）',
                  'https://schristiancollins.com/generaluser.php'),
    'python': ('Python 3.11', 'https://www.python.org/downloads/'),
}


def _homr_state():
    """homr 在不在：先看发布包 lib 里有没有，再看 import。"""
    bundled = os.path.join(ROOT, 'lib', 'homr')
    if os.path.isdir(bundled) and os.path.isfile(os.path.join(bundled, '__init__.py')):
        return True, bundled
    for folder in ('homr07', 'homr'):
        candidate = os.path.join(ROOT, folder)
        if os.path.isdir(candidate):
            hits = [name for name in os.listdir(candidate) if 'homr' in name.lower()]
            if hits:
                return True, os.path.join(candidate, hits[0])
    try:
        import homr  # noqa: F401
        return True, getattr(homr, '__file__', '') or 'site-packages'
    except Exception:
        return False, ''


def _musescore_state():
    try:
        for path in (HERE, os.path.join(HERE, 'recovered')):
            if os.path.isdir(path) and path not in sys.path:
                sys.path.insert(0, path)
        import musescore_cli
        found = musescore_cli.find_musescore()
        return bool(found), found or ''
    except Exception:
        return False, ''


def _soundfont_state():
    """音色库可能在几个地方：随包的 vendor、用户的 data、开发时的 preview_data。"""
    candidates = [
        os.path.join(ROOT, 'preview_data', 'soundfonts'),
        os.path.join(ROOT, 'vendor', 'soundfonts'),
        os.path.join(ROOT, 'data', 'soundfonts'),
    ]
    for folder in candidates:
        if not os.path.isdir(folder):
            continue
        for name in sorted(os.listdir(folder)):
            if not name.lower().endswith(('.sf2', '.sf3')):
                continue
            path = os.path.join(folder, name)
            try:
                if os.path.getsize(path) > 100000:
                    return True, path
            except OSError:
                continue
    return False, ''


def _python_state():
    ok = sys.version_info >= (3, 9)
    return ok, '%d.%d.%d' % sys.version_info[:3]


def _audiveris_state():
    """Audiveris 是可选的第二个识别引擎，装了会自动出现在「更多设置」里。"""
    candidates = []
    env = os.environ.get('XIAOHUA_AUDIVERIS') or ''
    if env:
        candidates.append(env)
    for base in (ROOT, HERE, os.path.join(ROOT, 'vendor'),
                 os.path.join(ROOT, 'app')):
        candidates.append(os.path.join(base, 'Audiveris', 'Audiveris.exe'))
        candidates.append(os.path.join(base, 'audiveris', 'Audiveris.exe'))
    for path in candidates:
        if os.path.isfile(path):
            return True, path
    found = shutil.which('Audiveris.exe') or shutil.which('Audiveris')
    if found:
        return True, found
    return False, '未安装（可选；装了可以换引擎重试）'


def _llm_state():
    config = os.path.join(ROOT, 'data', 'llm.json')
    if not os.path.isfile(config):
        return False, '未配置（不影响其他功能）'
    try:
        with open(config, encoding='utf-8-sig') as handle:
            data = json.load(handle)
        model = data.get('model') or ''
        key = data.get('api_key') or ''
        if model and key:
            return True, model
        return False, '配置不完整'
    except Exception:
        return False, '配置读取失败'


CHECKS = (
    ('python', _python_state, True),
    ('homr', _homr_state, False),
    ('musescore', _musescore_state, False),
    ('soundfont', _soundfont_state, False),
    ('audiveris', _audiveris_state, False),
)


def collect():
    rows = []
    for key, func, required in CHECKS:
        try:
            ok, detail = func()
        except Exception as exc:
            ok, detail = False, '%s: %s' % (type(exc).__name__, exc)
        label, url = LINKS.get(key, (key, ''))
        rows.append({'key': key, 'label': label, 'url': url,
                     'ok': bool(ok), 'detail': detail, 'required': required})
    return rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--open', action='store_true', help='打开缺失项的官方下载页')
    parser.add_argument('--json', action='store_true', help='输出 JSON')
    args = parser.parse_args()

    rows = collect()
    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return 0

    print('依赖检查（本程序不打包 homr / MuseScore，请用官方渠道自取）')
    print('-' * 62)
    missing = []
    for row in rows:
        mark = 'OK  ' if row['ok'] else ('缺失' if row['required'] else '可选缺')
        print('%-6s %-8s %-38s %s' % (mark, row['key'], row['label'], row['detail']))
        if not row['ok']:
            missing.append(row)
    print('-' * 62)
    if not missing:
        print('全部就绪。')
        return 0

    print('缺失项的官方地址：')
    for row in missing:
        print('  %-40s %s' % (row['label'], row['url']))
    if args.open:
        for row in missing:
            if row['url']:
                webbrowser.open(row['url'])
        print('已在浏览器打开上述页面。')
    return 1


if __name__ == '__main__':
    sys.exit(main())
