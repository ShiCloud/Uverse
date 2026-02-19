# AGENTS.md

该文档描述了本项目的需求，请按照以下需求执行

## 项目概览

这个项目是一个本地知识库工具软件，基于以下技术栈构建:

前端：React， Shadcn/ui，‌ Tailwind CSS， Vite， Electronß
后端：Python， Langchain
数据库：Postgressql， Pgvector

## 解析架构

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