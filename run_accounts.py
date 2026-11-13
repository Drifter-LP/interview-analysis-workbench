"""Supported local entrypoint: current workbench behind invitation login."""
import os
import socket
from pathlib import Path
import uvicorn

ROOT = Path(__file__).resolve().parent


def main():
    # Local mode only. A future public deployment must configure HTTPS separately.
    os.environ['SITE_HOME'] = str(ROOT / '.site-data')
    os.environ['SITE_ORIGIN'] = 'http://127.0.0.1:8765'
    os.environ['SITE_ALLOW_HTTP'] = '1'
    with socket.socket() as probe:
        if probe.connect_ex(('127.0.0.1', 8765)) == 0:
            raise SystemExit('8765端口已在使用，请先确认当前服务与任务，禁止重复启动')
    uvicorn.run('site_app:app', host='127.0.0.1', port=8765, app_dir=str(ROOT), access_log=False)


if __name__ == '__main__':
    main()
