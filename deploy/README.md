# cigardomtabaka.com 部署指南
# ==========================

## 一、VPS 基础环境

```bash
# 系统包
sudo apt update && sudo apt install -y python3.11 python3.11-venv nginx git nodejs npm

# 创建目录
sudo mkdir -p /opt/cigardomtabaka /var/log/gunicorn
sudo chown -R $USER:$USER /opt/cigardomtabaka

# 准备 SSH deploy key（仅读权限）
ssh-keygen -t ed25519 -C "deploy@cigardomtabaka" -f ~/.ssh/deploy_github
# 把 ~/.ssh/deploy_github.pub 加到 GitHub repo → Settings → Deploy keys
```

## 二、首次部署

```bash
cd /opt
git clone git@github.com:PetitRobusto/cigardomtabaka.git
cd cigardomtabaka

# 虚拟环境
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
playwright install chromium  # 如果爬虫要用

# 环境变量
cp .env.example .env
nano .env   # 填入真实的 SECRET_KEY 等

# 数据库初始化
python manage.py migrate
python manage.py collectstatic --noinput

# 前端
cd frontend && npm ci && npm run build && cd ..
```

## 三、Gunicorn 服务

```bash
sudo cp deploy/gunicorn.service /etc/systemd/system/
sudo mkdir -p /var/log/gunicorn
sudo chown www-data:www-data /var/log/gunicorn
sudo systemctl daemon-reload
sudo systemctl enable --now gunicorn
```

## 四、Nginx

```bash
sudo cp deploy/nginx.conf /etc/nginx/sites-available/cigardomtabaka
sudo ln -s /etc/nginx/sites-available/cigardomtabaka /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx

# HTTPS（Certbot）
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d cigardomtabaka.com -d www.cigardomtabaka.com
```

## 五、GitHub Secrets

在仓库 Settings → Secrets and variables → Actions 添加：

| Secret | 说明 |
|--------|------|
| `SSH_HOST` | VPS IP |
| `SSH_PORT` | SSH 端口（默认 22） |
| `SSH_USER` | SSH 用户名 |
| `SSH_PRIVATE_KEY` | 私钥内容（`cat ~/.ssh/deploy_github`） |

## 六、权限

```bash
sudo chown -R www-data:www-data /opt/cigardomtabaka/media/
sudo chown -R www-data:www-data /opt/cigardomtabaka/staticfiles/
sudo usermod -a -G www-data $USER
```

每次 `git push master` 后 GitHub Actions 自动部署。
