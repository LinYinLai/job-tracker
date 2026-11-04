# 秋招助手（Job Tracker）

面向应届生求职者的投递管理 + AI 提效工具，覆盖投递记录、进度跟踪、邮件识别到 AI 生成的全流程，支持网页版与 Electron 桌面版。

## 功能

### 投递进度管理

五分区看板（待投递、待推进、只投了简历、已推进、已完成）一眼看清整体进度；临近截止的岗位自动高亮，需要作品集的岗位标注徽标；支持备注置顶，快速定位重点岗位。

### 邮件自动识别

通过 IMAP 拉取企业回复邮件，自动判定测评、笔试、面试、offer、拒绝、调剂等阶段，判定结果自动更新投递阶段、无需手动同步；针对"调剂到其他岗位"易被误判为"拒绝"的边角场景做了特殊处理。

### AI 能力（四个固定入口）

提供周报、选岗、面试准备、作品集识别四个固定入口：周报按投递进度自动生成；选岗基于简历从岗位库收敛出三档推荐（金融 / AI / 热门新兴），每条附推荐理由与投递链接；面试准备基于简历生成材料；作品集识别对作品集内容做分析。采用固定入口而非自由对话，输出结构化、可脱敏、成本可控。

### 双端与数据隔离

支持网页版与 Electron 桌面版（macOS 原生应用）。DEMO_MODE 将真实数据与演示数据完全隔离，线上演示使用虚构企业与虚构简历，AI 走预生成缓存，无需配置 API Key。

## 在线体验

http://119.28.16.198:8001

## 技术栈

Flask + SQLite + 单文件前端 + Electron，AI 走 DeepSeek API。

## 本地运行

```bash
# 1. 安装依赖
python3 -m venv .venv
source .venv/bin/activate
pip install flask openpyxl requests paramiko python-docx

# 2. 配置密钥（仅真实模式需要）
cp backend/.env.example backend/.env
# 编辑 backend/.env，填入 EMAIL_ADDR、EMAIL_PASS、LLM_API_KEY

# 3. 演示模式（虚构数据，无需密钥）
cd backend
DEMO_MODE=1 python seed_demo.py   # 生成虚构演示数据
DEMO_MODE=1 python app.py         # 启动后访问 http://127.0.0.1:8001

# 真实模式（个人投递数据）
python app.py
```

桌面版：

```bash
cd desktop
npm install
npm start
```

## 目录结构

```
backend/   Flask 应用、AI 助手、邮件检测、演示数据生成脚本
frontend/  网页端（index.html、widget.html）
desktop/   Electron 桌面版
```

## 脱敏说明

仓库不包含以下内容（均在本地、已加入 .gitignore）：

- data/：真实简历与投递记录
- backend/.env：邮箱授权码、DeepSeek API Key
- backend/cvm_pw.txt、backend/demo_mailbox.txt：服务器密码、演示邮箱授权码
- demo_data/、backend/demo_cache/：演示数据与预生成缓存（可由脚本重新生成）
