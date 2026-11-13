"""Loopback-only launcher for an independent, text-only account deployment."""
import argparse
import os
from pathlib import Path
import stat
from urllib.parse import urlsplit

from site_store import SiteError, Store

ROOT = Path(__file__).resolve().parent
MARKER = '.workbench-text-cloud'
MODEL_KEY_NAMES = {'DEEPSEEK_API_KEY', 'QWEN_API_KEY'}


def read_model_keys(path):
    # Parse data, never source it as shell code. Do not include values in errors.
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o600:
            raise ValueError('模型密钥文件必须属于运行工作台的用户，权限为 600')
        raw = stream.read(4097)
    if len(raw) > 4096:
        raise ValueError('模型密钥文件过大')
    keys = {}
    for line in raw.splitlines():
        if not line:
            continue
        name, sep, value = line.partition(b'=')
        if not sep or name not in (b'DEEPSEEK_API_KEY', b'QWEN_API_KEY') or name.decode() in keys:
            raise ValueError('模型密钥文件包含未知或重复字段')
        if not value or any(byte < 33 or byte > 126 for byte in value):
            raise ValueError('模型密钥不能为空，也不能含空格或不可见字符')
        keys[name.decode()] = value.decode()
    if keys.keys() != MODEL_KEY_NAMES:
        raise ValueError('模型密钥文件必须包含 DeepSeek 和千问两项')
    return keys


def configure(data_dir, origin):
    origin = origin.rstrip('/')
    url = urlsplit(origin)
    # Access url.port here so invalid port strings fail before any disk writes.
    if (not url.hostname or url.username is not None or url.password is not None or
            url.path or url.query or url.fragment or any(c.isspace() for c in origin) or
            url.port == 0 or not (url.scheme == 'https' or
                                  (url.scheme == 'http' and url.hostname in ('127.0.0.1', 'localhost')))):
        raise ValueError('请提供 HTTPS 访问地址；HTTP 仅允许在本机预览')
    data = Path(data_dir).expanduser().resolve()
    if data == ROOT or ROOT in data.parents or data in ROOT.parents:
        raise ValueError('请为云端使用程序目录之外的独立数据目录')
    data.mkdir(parents=True, exist_ok=True, mode=0o700)
    marker = data / MARKER
    if not marker.is_file():
        if any(data.iterdir()):
            raise ValueError('云端数据目录必须是新建的空目录，禁止直接使用本机资料目录')
        marker.touch(exist_ok=True)
    store = Store(data)
    with store.db() as db:
        if db.execute("SELECT 1 FROM site_settings WHERE key='legacy_owner'").fetchone():
            raise ValueError('云端试用不接受绑定本机访谈的账号库')
    os.environ.update(SITE_HOME=str(data), SITE_ORIGIN=origin,
                      SITE_ALLOW_HTTP='1' if url.scheme == 'http' else '0', WORKBENCH_TEXT_ONLY='1')
    return store


def main():
    parser = argparse.ArgumentParser(description='启动文本版工作台（仅在服务器本机监听）')
    parser.add_argument('--data-dir', required=True)
    parser.add_argument('--origin', default='http://127.0.0.1:8765')
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--model-keys-file', type=Path, help='启动时读取权限为 600 的模型密钥文件（Linux）')
    setup = parser.add_mutually_exclusive_group()
    setup.add_argument('--init-admin', metavar='USERNAME', help='为全新云端站点生成一次性管理员激活链接')
    setup.add_argument('--reset-admin', metavar='USERNAME', help='为现有管理员生成一次性密码重设链接，不启动服务')
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error('无效的监听端口')
    try:
        if args.model_keys_file is not None:
            os.environ.update(read_model_keys(args.model_keys_file))
        store = configure(args.data_dir, args.origin)
        if args.init_admin:
            invite = store.invite(args.init_admin, bootstrap=True)
            print('一次性管理员激活链接（1小时有效，不要转发）：')
            print(os.environ['SITE_ORIGIN'] + '/account#invite=' + invite['token'])
            return
        if args.reset_admin:
            reset = store.admin_recovery(args.reset_admin)
            print('管理员一次性密码重设链接（1小时有效，请勿公开）：')
            print(os.environ['SITE_ORIGIN'] + '/account#reset=' + reset['token'])
            return
    except (OSError, ValueError, SiteError) as exc:
        parser.error(str(exc))
    import uvicorn
    uvicorn.run('site_app:app', host='127.0.0.1', port=args.port, app_dir=str(ROOT),
                access_log=False, workers=1, proxy_headers=True, forwarded_allow_ips='127.0.0.1')


if __name__ == '__main__':
    main()
