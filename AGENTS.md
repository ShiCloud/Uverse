# AGENTS.md

## 项目概览

Uverse 是一个本地知识库工具软件，基于以下技术栈构建:

- **前端**: React, Shadcn/ui, Tailwind CSS, Vite, Electron
- **后端**: Python, FastAPI, MinerU
- **数据库**: PostgreSQL, Pgvector

## 配置文件路径

| 模式 | macOS | Windows |
|------|-------|---------|
| 调试模式 | `backend/.env` | `backend/.env` |
| 打包模式 | `~/Library/Application Support/Uverse/.env` | `%APPDATA%/Uverse/.env` |

## 解析架构

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

## 关键实现细节

### 1. MinerU 配置处理

**mineru.json 路径更新逻辑**:
- 前端保存配置时更新一次
- 后端启动时再次检查并更新
- 始终使用基于当前 `MODELS_DIR` 的标准路径
- 标准路径: `MODELS_DIR/OpenDataLab/PDF-Extract-Kit-1___0`

### 2. 打包模式 vs 调试模式

使用 `app.isPackaged` 区分:
- **调试模式**: 使用源码目录 `backend/.env`
- **打包模式**: 使用 `userData/.env`，首次从 Resources 复制

### 3. 后端可执行文件

PyInstaller 构建:
- `uverse-backend`: 主后端服务
- `pdf-worker`: PDF 解析工作进程（支持热更新）

## 修复记录

所有修复记录详见: [docs/CHANGELOG.md](./docs/CHANGELOG.md)

> 注意：所有代码修改必须同步更新 CHANGELOG.md

**最新修复 (2026-02-26)**:
1. PDF Worker 参数传递修复
2. Electron 路径验证与 mineru.json 更新修复
3. 后端 mineru.json 路径更新逻辑修复
4. 构建配置修复
5. Electron 主进程打包模式路径修复

## 开发注意事项

1. **路径处理**: 始终考虑打包模式和调试模式的差异
2. **配置更新**: 修改 MODELS_DIR 时必须同步更新 mineru.json
3. **构建顺序**: 先构建后端 (`pyinstaller combined.spec`)，再构建前端
4. **日志查看**: 
   - 调试模式: `frontend/logs/`
   - 打包模式: `~/Library/Application Support/Uverse/logs/` (macOS)
