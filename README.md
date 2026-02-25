# Uverse - 本地知识库工具

<p align="center">
  <img src="frontend/src/assets/icon.png" width="120" alt="Uverse Logo">
</p>

---

## 📖 项目简介

**Uverse** 是一款本地知识库工具软件，支持多种文档格式（PDF、Word、TXT 等）的智能解析，所有数据本地存储，确保隐私安全。

### 核心优势

- 🔒 **完全本地运行** - 数据和模型都在本地，无需联网，保护隐私
- 🤖 **AI 驱动的文档解析** - 基于 MinerU 的智能 PDF 解析，支持图文混排
- 📦 **嵌入式数据库** - 内置 PostgreSQL，无需额外配置数据库服务
- 💻 **跨平台桌面应用** - 提供解压即用体验，基于 Electron，支持 macOS 和 Windows

---

## ✨ 功能特性

### 文档管理
- 📄 支持 PDF、Word (.docx)、TXT、CSV 等多种格式
- 📤 拖拽上传 / 批量上传
- 🔍 文档内容预览，在线修改及下载

### 智能解析
- 🧠 **MinerU 智能解析** - 支持复杂版面分析、表格识别、公式提取
- 🖼️ **图像提取与 OCR** - 自动提取文档中的图片并进行文字识别
- 📊 **表格识别** - 智能识别文档中的表格结构

## 🚀 快速开始

### 环境要求

- **操作系统**: macOS 12+ (Apple Silicon/Intel) 或 Windows 10/11
- **内存**: 建议 16GB+（MinerU 解析需要）
- **磁盘空间**: 10GB+（包含模型文件）

### 安装步骤

# Windows:
- **网盘地址：解压即用**
- **https://pan.baidu.com/s/19cqBEHWWZ1X571ndtNeR9Q?pwd=y8w1**


# macOS:
- **先安装程序，后将models，postgres，store，out文件夹复制到 ~/Library/Application Support/Uverse/，或者自己选择的目录，程序第一次启动，如果找不到默认目录下的程序会跳转到配置页面，配置相关目录，**

```bash
sudo xattr -r -d com.apple.quarantine /Users/shifeng/Library/Application\ Support/Uverse/postgres
sudo xattr -r -d com.apple.provenance /Users/shifeng/Library/Application\ Support/Uverse/postgres

sudo xattr -r -d com.apple.quarantine /Users/shifeng/Library/Application\ Support/Uverse/store
sudo xattr -r -d com.apple.provenance /Users/shifeng/Library/Application\ Support/Uverse/store
```
- **网盘地址：**



## 🚀 开发调试

#### 1. 克隆仓库

```bash
git clone <repository-url>
cd Uverse
```

#### 2. 安装后端依赖

```bash
cd backend

# 创建虚拟环境
python -m venv .venv

# 激活虚拟环境
# macOS/Linux:
source .venv/bin/activate
# Windows:
.venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt
```

#### 3. 安装前端依赖

```bash
cd ../frontend
npm install
```


### 打包

```bash
# macOS
npm run electron:build:mac

# Windows
npm run electron:build:win
```

---

## ⚙️ 配置说明

### 核心环境变量

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `USE_EMBEDDED_PG` | `true` | 是否使用嵌入式 PostgreSQL |
| `DATABASE_HOST` | `localhost` | 数据库主机（外部模式） |
| `DATABASE_PORT` | `15432` | 数据库端口 |
| `DATABASE_NAME` | `knowledge_base` | 数据库名 |
| `DATABASE_USER` | `postgres` | 数据库用户 |
| `DATABASE_PASSWORD` | `postgres` | 数据库密码 |
| `POSTGRES_DIR` | `postgres` | PostgreSQL 目录路径 |
| `STORE_DIR` | `store` | 文件存储目录路径 |
| `MODELS_DIR` | `models` | AI 模型目录路径 |
| `MINERU_BACKEND` | `pipeline` | PDF 解析后端模式 |
| `MINERU_DEVICE` | `cpu` | 解析设备 (cpu/cuda/mps) |

---

## 📄 许可证

本项目采用 [GNU Affero General Public License v3.0 (AGPL-3.0)](LICENSE) 开源许可证。

---

## 🙏 致谢

- [MinerU](https://github.com/opendatalab/MinerU) - 开源的 PDF 智能解析工具
- [FastAPI](https://fastapi.tiangolo.com/) - 现代 Python Web 框架
- [Shadcn/ui](https://ui.shadcn.com/) - 精美的 React 组件库

---

<p align="center">
  Made with ❤️ for local-first AI
</p>
