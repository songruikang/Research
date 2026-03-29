#!/bin/bash

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo ""
echo -e "${BLUE}======================================${NC}"
echo -e "${BLUE}   Token 环境修复工具                 ${NC}"
echo -e "${BLUE}======================================${NC}"
echo ""

# ── 1. 读取现有 token ─────────────────────────────────────────────
TOKEN="${ANTHROPIC_AUTH_TOKEN:-${ANTHROPIC_API_KEY:-}}"

if [ -z "$TOKEN" ]; then
    # 尝试从 .zprofile 读取
    TOKEN=$(grep "ANTHROPIC_AUTH_TOKEN" ~/.zprofile 2>/dev/null | sed 's/.*"\(.*\)"/\1/' | head -1)
fi

if [ -z "$TOKEN" ]; then
    echo -e "${YELLOW}未检测到已有 Token，请粘贴你的 OAuth Token (sk-ant-oat01-...):${NC}"
    read -r TOKEN
fi

if [[ "$TOKEN" != sk-ant-oat01-* ]]; then
    echo -e "${RED}✗ Token 格式不对，应以 sk-ant-oat01- 开头，退出。${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Token 已获取: ${TOKEN:0:20}...${NC}"
echo ""

# ── 2. 写入 .zshrc（虚拟环境也能读到）────────────────────────────
echo -e "${YELLOW}[1] 写入 ~/.zshrc ...${NC}"
sed -i '' '/ANTHROPIC_AUTH_TOKEN/d' ~/.zshrc 2>/dev/null
sed -i '' '/ANTHROPIC_API_KEY/d' ~/.zshrc 2>/dev/null
echo "" >> ~/.zshrc
echo "export ANTHROPIC_AUTH_TOKEN=\"$TOKEN\"" >> ~/.zshrc
echo "export ANTHROPIC_API_KEY=\"$TOKEN\"" >> ~/.zshrc
source ~/.zshrc
echo -e "${GREEN}✓ 已写入 ~/.zshrc${NC}"

# ── 3. 清理 .zprofile 里的旧配置 ─────────────────────────────────
echo -e "${YELLOW}[2] 清理 ~/.zprofile 旧配置 ...${NC}"
sed -i '' '/ANTHROPIC_AUTH_TOKEN/d' ~/.zprofile 2>/dev/null
sed -i '' '/ANTHROPIC_API_KEY/d' ~/.zprofile 2>/dev/null
echo -e "${GREEN}✓ 已清理 ~/.zprofile${NC}"

# ── 4. 写入项目 .env 文件 ─────────────────────────────────────────
echo -e "${YELLOW}[3] 写入项目 .env 文件 ...${NC}"

PROJECT_DIRS=(
    "$HOME/Research/data-agent"
    "$HOME/Research/industry-insights"
    "$HOME/Research/tools"
)

for dir in "${PROJECT_DIRS[@]}"; do
    if [ -d "$dir" ]; then
        ENV_FILE="$dir/.env"
        # 删旧的，写新的
        sed -i '' '/ANTHROPIC_AUTH_TOKEN/d' "$ENV_FILE" 2>/dev/null
        sed -i '' '/ANTHROPIC_API_KEY/d' "$ENV_FILE" 2>/dev/null
        echo "ANTHROPIC_AUTH_TOKEN=$TOKEN" >> "$ENV_FILE"
        echo "ANTHROPIC_API_KEY=$TOKEN" >> "$ENV_FILE"
        # 加入 .gitignore
        touch "$dir/.gitignore"
        grep -q ".env" "$dir/.gitignore" || echo ".env" >> "$dir/.gitignore"
        echo -e "  ${GREEN}✓${NC} $dir/.env"
    fi
done

# ── 5. 当前 session 立即生效 ──────────────────────────────────────
export ANTHROPIC_AUTH_TOKEN="$TOKEN"
export ANTHROPIC_API_KEY="$TOKEN"

# ── 6. 最终验证 ───────────────────────────────────────────────────
echo ""
echo -e "${BLUE}======================================${NC}"
echo -e "${YELLOW}验证结果：${NC}"

[ -n "$ANTHROPIC_AUTH_TOKEN" ] && echo -e "  ${GREEN}✓${NC} ANTHROPIC_AUTH_TOKEN 已生效" || echo -e "  ${RED}✗${NC} ANTHROPIC_AUTH_TOKEN 未生效"
[ -n "$ANTHROPIC_API_KEY" ]    && echo -e "  ${GREEN}✓${NC} ANTHROPIC_API_KEY 已生效"    || echo -e "  ${RED}✗${NC} ANTHROPIC_API_KEY 未生效"

echo ""
echo -e "${YELLOW}提示：${NC}新开 Terminal 或进入虚拟环境后变量会自动生效"
echo -e "${YELLOW}提示：${NC}Python 代码里加 ${GREEN}load_dotenv()${NC} 可从 .env 读取"
echo -e "${BLUE}======================================${NC}"
echo ""