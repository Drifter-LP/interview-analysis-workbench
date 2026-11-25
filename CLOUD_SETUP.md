# Ubuntu 24.04：访谈工作台文本版试运行

这一版使用账号网关，不安装本地录音转录、对齐和 GPU 依赖，不复制 Windows 上的账号、访谈、研究项目、用量或 API 密钥。云端管理员从空白工作区开始。Windows 本机仍用原启动方式。

访客可导入 TXT/DOCX、AI 文字校订、做单篇访谈分析；不开放跨访谈研究（主题研究、发现核查、词语探索、表述对照等）。既有访客资料不因权限调整而删除；仍可到期前登录并保留。访客期限与调用、上传额度不变。访客的 AI 校订与单篇分析使用服务端配置的 DeepSeek 密钥。

## 安装与私有预览

1. 在服务器普通用户下，把 `workbench-text-ubuntu.zip` 解压到一个新目录，进入包含 `run_cloud.py` 的目录。不要把本机工作台的整个目录传上来。
2. 确保服务器有 Python 3.12、`python3-venv` 和 `unzip`。在程序目录执行：

   ```sh
   python3 -m venv .venv
   .venv/bin/python -m pip install -r requirements-cloud.txt
   .venv/bin/python -m pip check
   ```

3. 管理员首次创建，用不同于本机的独立数据目录，在私有终端执行以下两条命令。第一条输出的链接只能自己使用，不要贴到聊天或日志里。

   ```sh
   .venv/bin/python run_cloud.py --data-dir "$HOME/workbench-cloud-data" --init-admin owner
   .venv/bin/python run_cloud.py --data-dir "$HOME/workbench-cloud-data"
   ```

4. 在服务器另一终端执行 `curl -fsS http://127.0.0.1:8765/health`，应看到 `{"ok":true}`。浏览器验收应通过私有隧道访问，保持工作台仅监听服务器自己的 `127.0.0.1`，不要对公网开放 8765 或内部分析端口。如果 Windows 本机 8765 被占用，先为云端预览选一个单独端口，同时指定相同的 `--port` 和 `--origin`，激活和运行两条命令保持一致。
5. 用虚构 TXT、DOCX 验证管理员激活、普通成员及访客上传、项目保存、账号隔离、访客过期和额度。实际模型验证前，在服务器进程环境中单独配置 `DEEPSEEK_API_KEY` 和 `QWEN_API_KEY`，不把密钥写进代码或发到聊天。纯上传测试不需要密钥。未配置密钥时模型分析不会工作。

## 管理员忘记密码

已有管理员的唯一账号密码遗失时，在运行工作台的服务器上，以工作台运行账号进入当前程序目录，使用同一 Python 环境和数据目录执行：

```sh
.venv/bin/python run_cloud.py --data-dir "$HOME/workbench-cloud-data" --reset-admin owner
```

将 `owner` 改为实际管理员账号名。若启动时设置了 `--origin`，这里也传入同样的地址。命令不会重启服务或创建新账号。只在私有终端读取重设链接；链接 1 小时有效、仅使用一次。设置新密码后，需要用新密码重新登录。

## 对外开放前

- 私有试运行不是正式上线。面向同学的域名、备案、HTTPS、服务自动启动和备份应单独设置并验收。通过本机 HTTPS 反向代理访问时，启动参数 `--origin` 改为实际的 `https://域名`；代理应保留实际 Host，覆盖来自用户的转发头，并按部署方信任范围配置真实来源地址。不要同时启动多个指向同一数据目录的网关。
- 用新账号和虚构资料再测一次上传、并发、用量、访客清理和备份恢复；未经确认不要迁入原始研究资料。本文件不表示真实服务器已经通过这些检查。

## 云端常驻服务

### 正式域名入口（2026-11-25）

已启用 `https://sociolab.cn`。DNSPod 的根域名 A 记录指向现有轻量服务器；Nginx 对外监听 80/443，HTTP 自动跳转 HTTPS。工作台服务启动参数已指定 `--origin https://sociolab.cn`，内部仍仅监听 `127.0.0.1:8765`，保留原资料目录及模型密钥文件。

证书由 Certbot 管理；`certbot.timer` 定时续期，`/etc/letsencrypt/renewal-hooks/deploy/sociolab-nginx` 在成功续期后检查配置并重载 Nginx。只申请了 `sociolab.cn`，未启用 `www` 子域名。

正式入口切换后，旧 SSH 通道地址不能作为正常登录入口（Host、Origin 和安全 Cookie 都以正式 HTTPS 域名为准）。服务器本机检查可用 `curl -fsS -H 'Host: sociolab.cn' http://127.0.0.1:8765/health`；外部检查使用 `curl -fsS https://sociolab.cn/health`。不要为恢复旧地址而降低来源校验或安全 Cookie 设置。

现有腾讯云部署由 `workbench.service` 管理，以 `ubuntu` 用户运行，开机自启、异常退出后自动重启。继续使用原数据目录和原模型密钥文件，只在服务器的 `127.0.0.1:8765` 监听。

```sh
systemctl is-enabled workbench.service
systemctl is-active workbench.service
curl -fsS -H 'Host: sociolab.cn' http://127.0.0.1:8765/health
sudo journalctl -u workbench.service -n 50 --no-pager
```

更新版本时，先在独立目录解包和检查，确认无正在运行的分析或访客任务，再变更服务的 `WorkingDirectory`，保留正式的 `--origin` 参数，重新加载服务配置、重启并校验；失败则切回上一版目录。不要再用 `nohup`、旧的单进程切换脚本或另一份服务启动同一个数据目录。日常查看页面使用正式 HTTPS 域名，无需 SSH 通道。
