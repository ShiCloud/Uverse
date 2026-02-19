#!/bin/bash
# macOS 完整构建、卸载、安装、启动脚本

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_NAME="Uverse"
APP_PATH="/Applications/${APP_NAME}.app"
RELEASE_DIR="${PROJECT_ROOT}/frontend/release"

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  ${APP_NAME} macOS 完整构建流程${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# 第1步：打包
echo -e "${YELLOW}📦 第1步：打包应用...${NC}"
cd "$PROJECT_ROOT/frontend"
npm run build
echo -e "${GREEN}✅ 前端构建完成${NC}"
echo ""

# 构建 Electron 主进程
echo -e "${YELLOW}🔨 构建 Electron 主进程...${NC}"
npm run build:electron
echo -e "${GREEN}✅ Electron 主进程构建完成${NC}"
echo ""

# 构建后端
echo -e "${YELLOW}⚙️  构建后端...${NC}"
cd "$PROJECT_ROOT"
./scripts/build-backend.sh
echo -e "${GREEN}✅ 后端构建完成${NC}"
echo ""

# 打包 Electron 应用
echo -e "${YELLOW}📱 打包 Electron 应用...${NC}"
cd "$PROJECT_ROOT/frontend"
electron-builder --mac
echo -e "${GREEN}✅ Electron 打包完成${NC}"
echo ""

# 查找生成的 dmg 文件
DMG_FILE=$(find "$RELEASE_DIR" -name "*.dmg" -type f | head -1)

if [ -z "$DMG_FILE" ]; then
    echo -e "${RED}❌ 未找到生成的 DMG 文件${NC}"
    exit 1
fi

echo -e "${BLUE}📦 找到安装包: $(basename "$DMG_FILE")${NC}"
echo ""

# 第2步：卸载（如果已安装）
echo -e "${YELLOW}🗑️  第2步：卸载旧版本...${NC}"
if [ -d "$APP_PATH" ]; then
    echo "   删除 ${APP_PATH}..."
    rm -rf "$APP_PATH"
    echo -e "${GREEN}✅ 已卸载旧版本${NC}"
else
    echo -e "${BLUE}   未安装旧版本，跳过${NC}"
fi
echo ""

# 第3步：安装
echo -e "${YELLOW}📥 第3步：安装应用...${NC}"

# 创建临时挂载点
MOUNT_DIR=$(mktemp -d)
echo "   挂载 DMG..."

# 挂载 dmg
hdiutil attach "$DMG_FILE" -mountpoint "$MOUNT_DIR" -nobrowse -quiet

# 复制应用到 /Applications
echo "   复制应用到 /Applications..."
cp -R "${MOUNT_DIR}/${APP_NAME}.app" "/Applications/"

# 卸载 dmg
echo "   卸载 DMG..."
hdiutil detach "$MOUNT_DIR" -quiet

# 清理临时目录
rm -rf "$MOUNT_DIR"

echo -e "${GREEN}✅ 安装完成${NC}"
echo ""

# 第4步：启动
echo -e "${YELLOW}🚀 第4步：启动应用...${NC}"
echo "   正在启动 ${APP_NAME}..."

# 等待一会儿确保文件系统同步
sleep 1

# 启动应用
open "$APP_PATH"

echo -e "${GREEN}✅ 应用已启动${NC}"
echo ""

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  🎉 全部完成！${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "应用已安装到: ${APP_PATH}"
echo ""
