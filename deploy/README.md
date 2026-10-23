# cigardomtabaka.com 部署指南
# ==========================
# 服务器: 103.110.65.50 (Ubuntu 24.04 LTS)
# 用户: jason (sudo) / root

## 一、已完成的服务器配置

- ✅ UFW 防火墙：22/80/443 开放
- ✅ Fail2ban：SSH 防爆破
- ✅ Nginx + Gunicorn (systemd)
- ✅ HTTPS (Let's Encrypt, 自动续期)
- ✅ GitHub Actions CI/CD（push main 后，只有 CI 全绿才自动部署）

自动部署链路：

```text
push main → CI 全绿 → Deploy production → /opt/cigardomtabaka
```

CI 并行运行普通后端测试、两组迁移测试和前端检查；各后端组内部保持单进程。
前端 job 检查 TypeScript、ESLint、Vitest 并构建 production 产物。任意一组失败都会阻止 production 部署。
原有 `test` required check 保留为三个后端分组的汇总门禁。

Deploy 仅接受本仓库 `push/main` 的成功 CI，固定使用该 run 的提交 SHA 和前端 artifact；
如果 `main` 已前进，则跳过旧 CI 的部署。
前端完整目录（含 `.vite/manifest.json`）打包为 `frontend.tar.gz`，随附 commit 和 SHA-256 元数据，
artifact 名为 `frontend-<commit SHA>`，保留 7 天。Deploy 按触发 CI 的 run ID 下载，
在 runner 和 VPS 上校验提交、摘要、manifest 与引用资源，校验失败会在修改生产代码或数据库前退出。
VPS 使用独立 run/attempt 暂存目录，安装时先验证并解包到同文件系统，替换失败恢复旧目录；
安装成功后仍执行 `collectstatic`，不再在 VPS 上运行 `npm ci` 或前端构建。


## 二、GitHub Secrets

在仓库 Settings → Secrets and variables → Actions 添加：

| Secret | 值 |
|--------|-----|
| `SSH_HOST` | 103.110.65.50 |
| `SSH_PORT` | 22 |
| `SSH_USER` | root |
| `SSH_PRIVATE_KEY` | VPS deploy key 私钥 |

Deploy key 已添加到服务器 `~/.ssh/authorized_keys`。

## 三、服务管理

```bash
# 重启 Django
sudo systemctl restart gunicorn

# 重载 Nginx
sudo systemctl reload nginx

# 查看日志
journalctl -u gunicorn -f
tail -f /var/log/gunicorn/error.log
tail -f /var/log/nginx/access.log
```

## 四、手动部署

### SQLite 运行时权限

生产数据库及其 WAL/SHM 文件统一使用 `www-data` 组，并保持组可读写。
数据库所在目录 `/opt/cigardomtabaka` 设置 setgid（当前标准权限为 `2775`），
使维护用户创建的新文件继承 `www-data` 组。`jason` 已在该组中，但仅加入组
不会改变其新建文件的默认所属组。SQLite 创建 WAL/SHM 时沿用数据库文件的
权限，因此必须同时保证 `cigars.db` 组可读写；部署流程会维护这些条件。
不要递归修改整个仓库或 `.env` 的权限。

生产数据库的排查、备份脚本和 Django 数据库管理命令统一以 `www-data` 执行；
例如已获授权的迁移使用 `sudo -u www-data env DJANGO_DEBUG=False venv/bin/python manage.py migrate`。
只读排查使用 SQLite URI `file:/opt/cigardomtabaka/cigars.db?mode=ro`，
不要使用 `immutable=1` 绕过 WAL，否则可能读到过期状态。

权限修复后，用服务用户执行 `BEGIN IMMEDIATE; ROLLBACK;` 验证写锁，
不通过真实付款验证，也不删除 WAL/SHM 文件。权限修复不需要重启应用。

### 发布流程

优先在 GitHub Actions 中重新运行对应成功 CI 的 Deploy workflow，继续使用该 run 的准确 SHA 与 artifact。
若 artifact 已过期，重新运行该提交的完整 CI 以产生新的已验证 artifact；不回退到服务器临时构建。
旧提交不是当前 `main` 时仍会被过期检查拒绝；回滚应通过新的回滚提交并重新通过 CI。
手动生产操作仍需明确授权，不能用 `git pull main` 替代准确 SHA 的验证门禁。

## 五、环境变量

`.env` 文件位于 `/opt/cigardomtabaka/.env`：

```
DJANGO_DEBUG=False
DJANGO_SECRET_KEY=<生产密钥>
LCDH_DL_PASSWORD=<刮刀密码>
TELEGRAM_BOT_TOKEN=<BotFather Token>
TELEGRAM_BUSINESS_CHAT_ID=-1003900174592
TELEGRAM_ERROR_CHAT_ID=8206776258
INTERNAL_SITE_URL=https://cigardomtabaka.com
```

Telegram Bot 只向以上固定目标发送消息，不接收业务命令。负责人需要先主动私聊 Bot
一次，Bot 才能向该私聊发送故障告警。两个 Chat ID 已在 Django settings 中作为固定
默认值，服务器 `.env` 可覆盖；真实 Token 只保存在服务器 `.env` 或 CI secret 中。
