# Uverse - 本地知识库工具

<p align="center">
  <img src="frontend/src/assets/icon.png" width="120" alt="Uverse Logo">
</p>

<p align="center">
  <strong>基于 RAG 技术的本地智能知识库管理工具</strong>
</p>

<p align="center">
  <a href="#功能特性">功能特性</a> •
  <a href="#技术架构">技术架构</a> •
  <a href="#快速开始">快速开始</a> •
  <a href="#开发指南">开发指南</a> •
  <a href="#配置说明">配置说明</a>
</p>

---

## 📖 项目简介

**Uverse** 是一款基于 RAG（检索增强生成）技术的本地知识库工具软件，支持多种文档格式（PDF、Word、TXT 等）的智能解析、向量化存储和语义检索。所有数据本地存储，确保隐私安全。

### 核心优势

- 🔒 **完全本地运行** - 数据和模型都在本地，无需联网，保护隐私
- 🤖 **AI 驱动的文档解析** - 基于 MinerU 的智能 PDF 解析，支持图文混排
- 🧠 **多模态向量检索** - 文本向量 + 视觉向量 + OCR 向量三重检索
- 📦 **嵌入式数据库** - 内置 PostgreSQL，无需额外配置数据库服务
- 💻 **跨平台桌面应用** - 基于 Electron，支持 macOS 和 Windows

---

## ✨ 功能特性

### 文档管理
- 📄 支持 PDF、Word (.docx)、TXT、CSV 等多种格式
- 📤 拖拽上传 / 批量上传
- 📂 文件夹管理和分类
- 🔍 文档内容预览和全文检索

### 智能解析
- 🧠 **MinerU 智能解析** - 支持复杂版面分析、表格识别、公式提取
- 🖼️ **图像提取与 OCR** - 自动提取文档中的图片并进行文字识别
- 📊 **表格识别** - 智能识别文档中的表格结构
- ⏳ **后台异步处理** - 大文件解析不阻塞界面

### 向量检索
- 🔢 **bge-m3 向量化** - 1024 维文本向量，支持多语言
- 🎨 **CLIP 视觉向量** - 512 维图像向量，支持以图搜图
- 📝 **OCR 向量** - 图片文字内容向量化
- 🎯 **混合检索** - 语义相似度 + 关键词匹配

### 对话问答
- 💬 基于检索结果的智能问答
- 📝 支持多轮对话上下文
- 🔗 答案溯源，显示参考文档

---

## 🏗️ 技术架构

### 系统架构图

```
┌─────────────────────────────────────────────────────────────────┐
│                        Electron 桌面应用                         │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                    React + TypeScript                    │   │
│  │              (Shadcn/ui + Tailwind CSS)                  │   │
│  └─────────────────────────────────────────────────────────┘   │
└────────────────────────┬────────────────────────────────────────┘
                         │ IPC / HTTP
┌────────────────────────▼────────────────────────────────────────┐
│                      Python 后端服务                             │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                     FastAPI                              │   │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────────┐  │   │
│  │  │  文档路由    │  │  对话路由    │  │   配置/日志路由  │  │   │
│  │  │  Documents  │  │    Chat     │  │  Config/Logs    │  │   │
│  │  └─────────────┘  └─────────────┘  └─────────────────┘  │   │
│  └─────────────────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                    核心服务层                            │   │
│  │   PDF Parser (MinerU)    Word Parser    Text Parser     │   │
│  │   Vector Store (pgvector)    RustFS Storage (S3)        │   │
│  └─────────────────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                    Langchain 框架                        │   │
│  │         RAG Pipeline    Text Splitter    Embeddings     │   │
│  └─────────────────────────────────────────────────────────┘   │
└────────────────────────┬────────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────────┐
│                        数据存储层                                │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐  │
│  │   PostgreSQL    │  │    RustFS       │  │    bge-m3       │  │
│  │  + pgvector     │  │  (对象存储)      │  │   (Embedding)   │  │
│  │                 │  │                 │  │   CLIP (视觉)    │  │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

### 解析架构

```
Word 文档 (.docx)
    │
    ├── 文本内容 ──→ 分块 ──→ bge-m3 ──→ 文本向量 (1024维)
    │                    │
    └── 图片 ───────→ 提取 ──┼──→ CLIP ───→ 视觉向量 (512维)
                             │
                             └──→ OCR ────→ 文字 ──→ bge-m3 ──→ OCR向量

PDF 文档
    │
    ├── 文本层 ──→ 提取 ──→ 分块 ──→ bge-m3 ──→ 文本向量 (1024维)
    │       │
    └── 图片层 ──→ 提取 ──┼──→ CLIP ───→ 视觉向量 (512维)
                          │
                          └──→ OCR ────→ 文字 ──→ bge-m3 ──→ OCR向量
```

### 技术栈

| 层级 | 技术 | 说明 |
|------|------|------|
| **前端** | React 18 | 用户界面框架 |
| | TypeScript | 类型安全的 JavaScript |
| | Vite | 构建工具 |
| | Electron | 桌面应用框架 |
| | Tailwind CSS | 原子化 CSS 框架 |
| | Shadcn/ui | UI 组件库 |
| | Radix UI | 无样式 UI 组件底层 |
| **后端** | Python 3.10+ | 编程语言 |
| | FastAPI | Web 框架 |
| | Uvicorn | ASGI 服务器 |
| | Langchain | LLM 应用框架 |
| | LangGraph | 工作流编排 |
| | SQLAlchemy | ORM 框架 |
| | PyInstaller | 打包工具 |
| **数据库** | PostgreSQL 15+ | 关系型数据库 |
| | pgvector | 向量扩展 |
| | asyncpg | 异步 PostgreSQL 驱动 |
| **存储** | RustFS | S3 兼容对象存储 |
| **AI/ML** | MinerU | PDF 智能解析 |
| | transformers | Hugging Face 模型库 |
| | PyTorch | 深度学习框架 |
| | bge-m3 | 文本 Embedding 模型 |
| | CLIP | 视觉 Embedding 模型 |
| | OpenAI API | LLM 对话接口 |

---

## 🚀 快速开始

### 环境要求

- **操作系统**: macOS 12+ (Apple Silicon/Intel) 或 Windows 10/11
- **Python**: 3.10 - 3.12
- **Node.js**: 18.x 或更高
- **内存**: 建议 8GB+（MinerU 解析需要）
- **磁盘空间**: 10GB+（包含模型文件）

### 安装步骤

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
# .venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt
```

#### 3. 安装前端依赖

```bash
cd ../frontend
npm install
```

#### 4. 配置环境变量

```bash
cd ../backend
cp .env.example .env

# 编辑 .env 文件，配置必要的参数
# 特别是 OpenAI API Key
```

### 启动开发环境

#### 方式一：分别启动前后端

```bash
# 终端 1: 启动后端
cd backend
python main.py

# 终端 2: 启动前端
cd frontend
npm run electron:dev
```

#### 方式二：完整构建测试

```bash
# macOS
npm run electron:build:mac

# Windows
npm run electron:build:win
```

---

## 🛠️ 开发指南

### 项目结构

```
Uverse/
├── frontend/                 # 前端项目
│   ├── electron/            # Electron 主进程代码
│   │   ├── main.ts          # 主进程入口
│   │   └── preload.ts       # 预加载脚本
│   ├── src/
│   │   ├── components/      # React 组件
│   │   │   └── ui/          # Shadcn/ui 组件
│   │   ├── pages/           # 页面组件
│   │   │   ├── Documents.tsx    # 文档管理页
│   │   │   ├── KnowledgeBase.tsx # 知识库页
│   │   │   ├── Settings.tsx     # 设置页
│   │   │   └── Loading.tsx      # 加载页
│   │   ├── utils/           # 工具函数
│   │   │   ├── api.ts       # API 请求封装
│   │   │   ├── electron.ts  # Electron 相关
│   │   │   └── storage_api.ts   # 存储 API
│   │   ├── App.tsx          # 应用根组件
│   │   └── main.tsx         # 前端入口
│   ├── build/               # 构建资源
│   └── package.json         # 前端依赖
│
├── backend/                  # 后端项目
│   ├── core/                # 核心模块
│   │   ├── database.py      # 数据库连接
│   │   ├── vector_store.py  # 向量存储
│   │   ├── storage.py       # 文件记录存储
│   │   ├── postgres_manager.py  # PostgreSQL 管理
│   │   ├── file_logger.py   # 文件日志
│   │   └── app_logger.py    # 应用日志
│   ├── routers/             # API 路由
│   │   ├── documents.py     # 文档管理
│   │   ├── chat.py          # 对话
│   │   ├── config.py        # 配置
│   │   ├── logs.py          # 日志
│   │   └── health.py        # 健康检查
│   ├── services/            # 业务服务
│   │   ├── pdf_parser.py    # PDF 解析 (MinerU)
│   │   ├── word_parser.py   # Word 解析
│   │   ├── text_parser.py   # 文本解析
│   │   └── rustfs_storage.py    # 对象存储
│   ├── models/              # 数据模型
│   ├── workers/             # 后台任务
│   ├── utils/               # 工具函数
│   ├── main.py              # 后端入口
│   ├── requirements.txt     # Python 依赖
│   └── .env.example         # 环境变量示例
│
├── scripts/                  # 构建脚本
│   ├── build-backend.sh     # 后端构建
│   └── build-and-install-mac.sh   # macOS 完整构建
│
└── README.md                # 项目说明
```

### 开发工作流

#### 添加新的 API 接口

1. 在 `backend/routers/` 创建新的路由文件或修改现有路由
2. 在 `backend/main.py` 中注册路由
3. 在 `frontend/src/utils/api.ts` 添加对应的 API 调用函数
4. 在组件中使用新接口

#### 添加新的页面

1. 在 `frontend/src/pages/` 创建新的页面组件
2. 在 `frontend/src/App.tsx` 中添加路由配置
3. 在侧边栏添加导航项

#### 修改数据库模型

1. 在 `backend/core/storage.py` 修改模型定义
2. 重启后端服务，自动创建新表

### 调试技巧

#### 后端调试

```bash
# 开启调试模式
cd backend
DEBUG=true python main.py

# 查看详细日志
tail -f logs/app.log
```

#### 前端调试

```bash
# 开发模式（带热重载）
cd frontend
npm run electron:dev

# 打开 DevTools
# macOS: Cmd + Option + I
# Windows: Ctrl + Shift + I
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
| `OPENAI_API_KEY` | - | OpenAI API 密钥 |
| `POSTGRES_DIR` | `postgres` | PostgreSQL 目录路径 |
| `STORE_DIR` | `store` | 文件存储目录路径 |
| `MODELS_DIR` | `models` | AI 模型目录路径 |
| `MINERU_BACKEND` | `pipeline` | PDF 解析后端模式 |
| `MINERU_DEVICE` | `cpu` | 解析设备 (cpu/cuda/mps) |

### MinerU 解析模式

| 模式 | 说明 | 推荐场景 |
|------|------|----------|
| `pipeline` | 通用解析模式，速度快，资源占用少 | 日常文档处理（推荐） |
| `vlm-auto-engine` | 高精度本地推理，需要 ~10GB 模型 | 复杂版面文档 |
| `hybrid-auto-engine` | 下一代高精度本地推理 | 质量要求极高的场景 |

### 数据库模式选择

**嵌入式模式**（默认）
- ✅ 无需额外安装 PostgreSQL
- ✅ 应用启动时自动启动数据库
- ✅ 适合桌面应用场景
- ⚠️ 数据存储在用户目录

**外部模式**
- ✅ 使用独立的 PostgreSQL 服务器
- ✅ 适合多用户/服务器部署
- ⚠️ 需要手动配置连接信息

切换方式：修改 `.env` 中的 `USE_EMBEDDED_PG=false`

---

## 📦 构建发布

### macOS 构建

```bash
# 完整构建并安装到 Applications
./scripts/build-and-install-mac.sh

# 或手动构建
cd frontend
npm run electron:build:mac
```

构建输出：`frontend/release/Uverse-0.1.0-arm64.dmg`

### Windows 构建

```bash
cd frontend
npm run electron:build:win
```

构建输出：`frontend/release/Uverse 0.1.0.exe`

### 构建配置

构建配置位于 `frontend/package.json` 的 `build` 字段：

```json
{
  "build": {
    "appId": "com.uverse.app",
    "productName": "Uverse",
    "directories": {
      "output": "release"
    },
    "mac": {
      "target": ["dmg"],
      "category": "public.app-category.productivity"
    },
    "win": {
      "target": ["portable"]
    }
  }
}
```

---

## 🔧 常见问题

### 1. 后端服务启动失败

**问题**: 端口 8000 被占用

**解决**:
```bash
# 查找并结束占用进程
lsof -ti:8000 | xargs kill -9
```

### 2. PostgreSQL 启动失败

**问题**: 数据目录权限错误或端口冲突

**解决**:
```bash
# 清理 PostgreSQL 数据目录
cd backend
rm -rf postgres/data
# 重新启动会自动初始化
```

### 3. MinerU 解析失败

**问题**: 模型文件缺失或 CUDA 内存不足

**解决**:
- 检查 `models/OpenDataLab` 目录是否存在模型文件
- 修改 `.env` 使用 CPU 模式：`MINERU_DEVICE=cpu`
- 或调整显存限制：`MINERU_VRAM=4096`

### 4. 前端构建失败

**问题**: Node.js 版本不兼容或依赖冲突

**解决**:
```bash
cd frontend
rm -rf node_modules package-lock.json
npm install
```

---

## 📄 许可证

本项目采用 [MIT License](LICENSE) 开源许可证。

---

## 🙏 致谢

- [MinerU](https://github.com/opendatalab/MinerU) - 开源的 PDF 智能解析工具
- [Langchain](https://github.com/langchain-ai/langchain) - LLM 应用开发框架
- [FastAPI](https://fastapi.tiangolo.com/) - 现代 Python Web 框架
- [Shadcn/ui](https://ui.shadcn.com/) - 精美的 React 组件库

---

<p align="center">
  Made with ❤️ for local-first AI
</p>
