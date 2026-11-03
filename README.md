# 秋招助手 · 求职投递管理 + AI 提效

一个自己秋招时做的管理工具，整理成可演示的版本。跟踪投了哪些公司、各自走到哪一步，用 AI 生成周报、选岗建议和面试准备。

## 能做什么

- 投递进度跟踪：五分区看板（待投递 / 待推进 / 只投了简历 / 已推进 / 已完成），快截止的自动高亮，需要作品集的岗位带徽标
- 邮件自动识别：IMAP 拉取企业回复，自动判定测评、笔试、面试、offer、拒绝、调剂并更新阶段，处理了调剂到别的岗位却被当成拒绝这种边角
- AI 四个入口：周报、选岗、面试准备、作品集识别，输入输出固定，可脱敏、成本可控
- 双端：网页版 + Electron 桌面版

## 在线体验

http://119.28.16.198:8001

演示数据是虚构的（36 家假企业、一个虚构简历），AI 结果走预生成缓存，不用配 key 也能玩通；写操作有保护，不会碰到任何真实数据。

## 本地运行

```bash
# 1. 装依赖
python3 -m venv .venv
source .venv/bin/activate
pip install flask openpyxl requests paramiko python-docx

# 2. 配置密钥（真实模式才需要，演示模式跳过）
cp backend/.env.example backend/.env
# 编辑 backend/.env，填 EMAIL_ADDR、EMAIL_PASS、LLM_API_KEY

# 3. 演示模式
cd backend
DEMO_MODE=1 python seed_demo.py    # 生成虚构演示数据
DEMO_MODE=1 python app.py          # 启动，浏览器开 http://127.0.0.1:8001

# 真实模式（自己的投递数据）
python app.py
```

桌面版：

```bash
cd desktop
npm install
npm start
```

## 技术栈

Flask + SQLite + 单文件前端 + Electron，AI 走 DeepSeek API。

## 目录结构

```
backend/   Flask 应用、AI 助手、邮件检测、演示数据生成脚本
frontend/  网页端（index.html、widget.html）
desktop/   Electron 桌面版
```

## 脱敏说明

仓库里没有以下内容，都在本地、已加入 .gitignore：

- data/：真实简历和投递记录
- backend/.env：邮箱授权码、DeepSeek key
- backend/cvm_pw.txt、backend/demo_mailbox.txt：服务器密码、演示邮箱授权码
- demo_data/、backend/demo_cache/：演示数据和预生成缓存，可用脚本重新生成
