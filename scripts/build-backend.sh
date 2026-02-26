#!/bin/bash
set -e

# ============================================
# 构建 Uverse 后端可执行文件
# 使用 PyInstaller 打包 Python 后端
# ============================================

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="$PROJECT_ROOT/backend"
BUILD_DIR="$BACKEND_DIR/build"
# 直接输出到 backend/dist
OUTPUT_DIR="$BACKEND_DIR/dist"

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  构建 Uverse 后端可执行文件${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# 检查虚拟环境
if [ ! -d "$BACKEND_DIR/.venv" ]; then
    echo -e "${RED}❌ 后端虚拟环境不存在: $BACKEND_DIR/.venv${NC}"
    exit 1
fi

# 检查 PyInstaller
if ! "$BACKEND_DIR/.venv/bin/pip" show pyinstaller &> /dev/null; then
    echo -e "${YELLOW}⚠️  PyInstaller 未安装，正在安装...${NC}"
    cd "$BACKEND_DIR"
    source .venv/bin/activate
    pip install pyinstaller
fi

# 清理并创建输出目录
echo -e "${YELLOW}🧹 清理构建目录...${NC}"
rm -rf "$BUILD_DIR"
# 清理旧的构建输出
rm -rf "$OUTPUT_DIR"
mkdir -p "$OUTPUT_DIR"

# 构建后端可执行文件
echo -e "${YELLOW}🔨 构建后端可执行文件...${NC}"
cd "$BACKEND_DIR"
source .venv/bin/activate

# 使用合并 spec 文件构建（共享库）
# 优先使用优化版 spec
if [ -f "combined_optimized.spec" ]; then
    echo -e "${BLUE}   使用 combined_optimized.spec 构建（优化模式）...${NC}"
    pyinstaller combined_optimized.spec \
        --noconfirm \
        --distpath "$OUTPUT_DIR" \
        --workpath "$BUILD_DIR/pyinstaller-work"
    
    echo -e "${GREEN}✅ uverse-backend 和 pdf-worker 已构建到同一目录，共享库（优化版）${NC}"
elif [ -f "combined.spec" ]; then
    echo -e "${BLUE}   使用 combined.spec 构建（共享库模式）...${NC}"
    pyinstaller combined.spec \
        --noconfirm \
        --distpath "$OUTPUT_DIR" \
        --workpath "$BUILD_DIR/pyinstaller-work"
    
    echo -e "${GREEN}✅ uverse-backend 和 pdf-worker 已构建到同一目录，共享库${NC}"
# 回退到分开构建（旧模式）
elif [ -f "uverse.spec" ]; then
    echo -e "${YELLOW}⚠️  combined.spec 不存在，使用分开构建模式${NC}"
    echo -e "${BLUE}   使用 uverse.spec 构建主后端...${NC}"
    pyinstaller uverse.spec \
        --noconfirm \
        --distpath "$OUTPUT_DIR" \
        --workpath "$BUILD_DIR/pyinstaller-work"
    
    if [ -f "pdf_worker.spec" ]; then
        echo -e "${BLUE}   使用 pdf_worker.spec 构建 PDF Worker...${NC}"
        pyinstaller pdf_worker.spec \
            --noconfirm \
            --distpath "$OUTPUT_DIR" \
            --workpath "$BUILD_DIR/pyinstaller-work-pdf"
    fi
else
    echo -e "${RED}❌ 未找到 spec 文件${NC}"
    exit 1
fi

# 检查构建结果（onedir 模式下检查目录中的可执行文件）
if [ ! -d "$OUTPUT_DIR/uverse-backend" ] || [ ! -f "$OUTPUT_DIR/uverse-backend/uverse-backend" ]; then
    echo -e "${RED}❌ 后端可执行文件构建失败${NC}"
    exit 1
fi

# 检查 pdf-worker 是否也在同一目录下（共享库模式）
if [ -f "$OUTPUT_DIR/uverse-backend/pdf-worker" ]; then
    echo -e "${GREEN}✅ 后端可执行文件已构建（共享库模式）${NC}"
    echo -e "${BLUE}   - uverse-backend${NC}"
    echo -e "${BLUE}   - pdf-worker（共享 _internal）${NC}"
else
    # 检查独立 pdf-worker 目录（旧模式兼容）
    if [ -f "$OUTPUT_DIR/pdf-worker/pdf-worker" ]; then
        echo -e "${YELLOW}⚠️  pdf-worker 独立构建（非共享库模式）${NC}"
    fi
    echo -e "${GREEN}✅ 后端可执行文件已构建${NC}"
fi

# 复制资源目录
echo -e "${YELLOW}📂 复制资源目录...${NC}"

# 注意：models/postgres/store 不再打包，需要用户手动配置或运行时下载
echo -e "${YELLOW}⚠️  models/postgres/store 不包含在包中（减小体积）${NC}"
echo -e "${YELLOW}    用户需要在设置中配置这些路径${NC}"

# 复制 .env（包含默认空路径配置）到可执行文件所在目录
if [ -f "$BACKEND_DIR/.env" ]; then
    cp "$BACKEND_DIR/.env" "$OUTPUT_DIR/uverse-backend/.env"
    echo -e "${GREEN}✅ .env 已复制到 uverse-backend/ 目录${NC}"
fi

# 复制 mineru.json（MinerU 配置文件模板）到 models/ 目录
# 应用运行时将从 MODELS_DIR 或 Support 目录读取此文件
if [ -f "$BACKEND_DIR/models/mineru.json" ]; then
    mkdir -p "$OUTPUT_DIR/uverse-backend/models"
    cp "$BACKEND_DIR/models/mineru.json" "$OUTPUT_DIR/uverse-backend/models/mineru.json"
    echo -e "${GREEN}✅ mineru.json 已复制到 uverse-backend/models/ 目录${NC}"
else
    echo -e "${RED}⚠️  mineru.json 不存在于 $BACKEND_DIR/models/，打包后的应用可能无法正常工作${NC}"
fi

# 显示结果
echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  后端构建完成！${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "📦 输出目录: $OUTPUT_DIR"
echo ""
echo "📊 目录结构:"
ls -lh "$OUTPUT_DIR/uverse-backend/" 2>/dev/null | grep -E "(uverse-backend|pdf-worker)"
echo ""
echo "📊 总大小:"
du -sh "$OUTPUT_DIR/uverse-backend" 2>/dev/null

# 如果是共享库模式，显示节省的空间
if [ -f "$OUTPUT_DIR/uverse-backend/pdf-worker" ] && [ ! -d "$OUTPUT_DIR/pdf-worker" ]; then
    echo ""
    echo -e "${BLUE}💡 共享库模式已启用，pdf-worker 与 uverse-backend 共用 _internal 目录${NC}"
fi
echo ""
