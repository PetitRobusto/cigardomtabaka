# cigardomtabaka.com 部署指南
# ==========================
# 服务器: 103.110.65.50 (Ubuntu 24.04 LTS)
# 用户: jason (sudo) / root

## 一、已完成的服务器配置

- ✅ UFW 防火墙：22/80/443 开放
- ✅ Fail2ban：SSH 防爆破
- ✅ Nginx + Gunicorn (systemd)
- ✅ HTTPS (Let's Encrypt, 自动续期)
- ✅ GitHub Actions CI/CD (push main 自动部署)

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

```bash
cd /opt/cigardomtabaka
git pull origin main
source venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py collectstatic --noinput
cd frontend && npm ci && npm run build && cd ..
sudo systemctl restart gunicorn
sudo nginx -t && sudo systemctl reload nginx
```

## 五、环境变量

`.env` 文件位于 `/opt/cigardomtabaka/.env`：

```
DJANGO_DEBUG=False
DJANGO_SECRET_KEY=<生产密钥>
LCDH_DL_PASSWORD=<刮刀密码>
```
