# Linux 服务器部署指南

本文档介绍如何在国内 Linux 服务器上部署股票分析系统，并配置代理访问海外 API（Gemini/OpenAI/Telegram）。

## 架构说明

```
国内 Linux 服务器
    │
    ├── 金融数据 API ──→ 直连（NO_PROXY）
    │   - 东方财富 (eastmoney.com)
    │   - 新浪财经 (sina.com.cn)
    │   - 腾讯财经 (gtimg.cn)
    │
    └── 海外 API ──→ 代理（http_proxy）
        - Gemini API
        - OpenAI API
        - Telegram Bot
```

## 前置条件

- 国内云服务器（阿里云/腾讯云/华为云等）
- Python 3.10+
- 海外代理节点（自建 VPS 或机场订阅）

---

## 步骤 1：安装 Clash 代理客户端

### 1.1 下载 Clash

```bash
# 创建目录
mkdir -p /opt/clash && cd /opt/clash

# 下载 Clash（选择对应架构）
# AMD64
wget https://github.com/Dreamacro/clash/releases/download/v1.18.0/clash-linux-amd64-v1.18.0.gz
gunzip clash-linux-amd64-v1.18.0.gz
mv clash-linux-amd64-v1.18.0 clash

# ARM64（如果是 ARM 服务器）
# wget https://github.com/Dreamacro/clash/releases/download/v1.18.0/clash-linux-arm64-v1.18.0.gz

# 添加执行权限
chmod +x clash
```

### 1.2 配置 Clash

```bash
# 创建配置目录
mkdir -p ~/.config/clash

# 方式 A：从订阅链接下载配置
wget -O ~/.config/clash/config.yaml "你的机场订阅链接"

# 方式 B：手动创建配置文件
cat > ~/.config/clash/config.yaml << 'EOF'
port: 7890
socks-port: 7891
allow-lan: false
mode: rule
log-level: info

proxies:
  - name: "proxy-server"
    type: vmess
    server: your-server.com
    port: 443
    uuid: your-uuid
    alterId: 0
    cipher: auto
    tls: true

proxy-groups:
  - name: "PROXY"
    type: select
    proxies:
      - proxy-server

rules:
  # 国内直连
  - DOMAIN-SUFFIX,eastmoney.com,DIRECT
  - DOMAIN-SUFFIX,sina.com.cn,DIRECT
  - DOMAIN-SUFFIX,sinajs.cn,DIRECT
  - DOMAIN-SUFFIX,gtimg.cn,DIRECT
  - DOMAIN-SUFFIX,163.com,DIRECT
  - DOMAIN-SUFFIX,tushare.pro,DIRECT
  - DOMAIN-SUFFIX,baostock.com,DIRECT
  - GEOIP,CN,DIRECT
  # 其他走代理
  - MATCH,PROXY
EOF
```

### 1.3 创建 systemd 服务

```bash
cat > /etc/systemd/system/clash.service << 'EOF'
[Unit]
Description=Clash Proxy Service
After=network.target

[Service]
Type=simple
User=root
ExecStart=/opt/clash/clash -d /root/.config/clash
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

# 重载 systemd
systemctl daemon-reload

# 启动 Clash
systemctl start clash

# 设置开机自启
systemctl enable clash

# 查看状态
systemctl status clash
```

### 1.4 验证代理

```bash
# 测试代理是否工作（应该返回 Google 页面）
curl -x http://127.0.0.1:7890 https://www.google.com -I

# 测试国内 API 直连（不走代理）
curl https://push2.eastmoney.com -I
```

---

## 步骤 2：部署股票分析项目

### 2.1 克隆项目

```bash
cd /opt
git clone https://github.com/your-repo/daily_stock_analysis.git
cd daily_stock_analysis
```

### 2.2 创建虚拟环境

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2.3 配置环境变量

```bash
cp .env.example .env
vim .env
```

`.env` 文件关键配置：

```env
# ========== 代理配置 ==========
USE_PROXY=true
PROXY_HOST=127.0.0.1
PROXY_PORT=7890

# ========== 股票列表 ==========
STOCK_LIST=600519,000001,300750

# ========== AI 配置（二选一）==========
# 方式 A：使用 Gemini（需要代理）
GEMINI_API_KEY=your-gemini-api-key

# 方式 B：使用国产 AI（无需代理，推荐）
# OPENAI_API_KEY=sk-xxx
# OPENAI_BASE_URL=https://api.deepseek.com/v1

# ========== 推送配置 ==========
# 飞书（国内直连）
FEISHU_WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/xxx

# 企业微信（国内直连）
WECHAT_WEBHOOK_URL=https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxx

# Telegram（需要代理）
TELEGRAM_BOT_TOKEN=your-bot-token
TELEGRAM_CHAT_ID=your-chat-id
```

---

## 步骤 3：创建启动脚本

```bash
cat > /opt/daily_stock_analysis/run.sh << 'EOF'
#!/bin/bash
set -e

# 切换到项目目录
cd /opt/daily_stock_analysis

# 激活虚拟环境
source venv/bin/activate

# 设置代理环境变量（给 Gemini/OpenAI/Telegram 用）
export http_proxy=http://127.0.0.1:7890
export https_proxy=http://127.0.0.1:7890

# 国内金融 API 不走代理
export NO_PROXY=eastmoney.com,push2.eastmoney.com,quote.eastmoney.com,datacenter.eastmoney.com,data.eastmoney.com,sina.com.cn,hq.sinajs.cn,163.com,tushare.pro,baostock.com,sse.com.cn,szse.cn,csindex.com.cn,cninfo.com.cn,gtimg.cn,qt.gtimg.cn,localhost,127.0.0.1
export no_proxy=$NO_PROXY

# 运行分析
python main.py "$@"
EOF

chmod +x /opt/daily_stock_analysis/run.sh
```

---

## 步骤 4：配置定时任务

### 4.1 使用 crontab

```bash
# 编辑 crontab
crontab -e

# 添加定时任务（每个交易日 15:30 执行）
30 15 * * 1-5 /opt/daily_stock_analysis/run.sh >> /var/log/stock-analysis.log 2>&1

# 查看已配置的任务
crontab -l
```

### 4.2 使用 systemd timer（推荐）

```bash
# 创建 service 文件
cat > /etc/systemd/system/stock-analysis.service << 'EOF'
[Unit]
Description=Daily Stock Analysis
After=network.target clash.service

[Service]
Type=oneshot
ExecStart=/opt/daily_stock_analysis/run.sh
WorkingDirectory=/opt/daily_stock_analysis
User=root

[Install]
WantedBy=multi-user.target
EOF

# 创建 timer 文件
cat > /etc/systemd/system/stock-analysis.timer << 'EOF'
[Unit]
Description=Run Stock Analysis Daily

[Timer]
OnCalendar=Mon-Fri 15:30
Persistent=true

[Install]
WantedBy=timers.target
EOF

# 启用定时器
systemctl daemon-reload
systemctl enable stock-analysis.timer
systemctl start stock-analysis.timer

# 查看定时器状态
systemctl list-timers --all | grep stock
```

---

## 步骤 5：日志管理

### 5.1 查看日志

```bash
# 查看最新日志
tail -f /opt/daily_stock_analysis/logs/stock_analysis_$(date +%Y%m%d).log

# 查看 systemd 服务日志
journalctl -u stock-analysis.service -f
```

### 5.2 配置日志轮转

```bash
cat > /etc/logrotate.d/stock-analysis << 'EOF'
/opt/daily_stock_analysis/logs/*.log {
    daily
    rotate 30
    compress
    delaycompress
    missingok
    notifempty
    create 644 root root
}
EOF
```

---

## 常见问题

### Q1: Clash 无法启动

```bash
# 检查端口占用
netstat -tlnp | grep 7890

# 查看 Clash 日志
journalctl -u clash.service -n 50
```

### Q2: 代理不生效

```bash
# 确认环境变量已设置
echo $http_proxy
echo $NO_PROXY

# 测试代理
curl -x http://127.0.0.1:7890 https://api.openai.com -I
```

### Q3: 金融 API 超时

```bash
# 确认 NO_PROXY 包含所有国内域名
# 检查是否误走代理
curl -v https://push2.eastmoney.com 2>&1 | grep -i proxy
```

### Q4: 定时任务未执行

```bash
# 检查 crontab
crontab -l

# 检查 systemd timer
systemctl status stock-analysis.timer

# 手动测试
/opt/daily_stock_analysis/run.sh
```

---

## 替代方案：使用国产 AI（无需代理）

如果不想配置代理，可以使用国产 AI 服务：

```env
# .env 配置
GEMINI_API_KEY=           # 留空
OPENAI_API_KEY=sk-xxx     # DeepSeek/通义千问 API Key
OPENAI_BASE_URL=https://api.deepseek.com/v1
```

| 服务 | API 地址 | 价格 |
|------|----------|------|
| DeepSeek | https://api.deepseek.com/v1 | 便宜 |
| 通义千问 | https://dashscope.aliyuncs.com/compatible-mode/v1 | 有免费额度 |
| 智谱 GLM | https://open.bigmodel.cn/api/paas/v4 | 有免费额度 |

这样只需要配置国内推送渠道（飞书/企业微信/钉钉），完全不需要代理。
