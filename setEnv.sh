#!/bin/bash

# ── 颜色 ──────────────────────────────────────────────────────────
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo ""
echo -e "${BLUE}======================================${NC}"
echo -e "${BLUE}   Claude 环境检查 & 设置工具         ${NC}"
echo -e "${BLUE}======================================${NC}"
echo ""

# ── 1. 检查当前变量状态 ───────────────────────────────────────────
echo -e "${YELLOW}[1] 检查当前环境变量...${NC}"

check_var() {
    local name=$1
    local val=${!name}
    if [ -n "$val" ]; then
        echo -e "  ${GREEN}✓${NC} $name = ${val:0:20}..."
    else
        echo -e "  ${RED}✗${NC} $name 未设置"
    fi
}

check_var "ANTHROPIC_AUTH_TOKEN"
check_var "ANTHROPIC_API_KEY"

echo ""

# ── 2. 检查 .zprofile 里的内容 ────────────────────────────────────
echo -e "${YELLOW}[2] 检查 ~/.zprofile 配置...${NC}"
if grep -q "ANTHROPIC" ~/.zprofile 2>/dev/null; then
    echo -e "  ${GREEN}✓${NC} ~/.zprofile 中找到以下 Anthropic 配置："
    grep "ANTHROPIC" ~/.zprofile | sed 's/^/    /'
else
    echo -e "  ${RED}✗${NC} ~/.zprofile 中没有 Anthropic 配置"
fi

echo ""

# ── 3. 检查 Claude Code ───────────────────────────────────────────
echo -e "${YELLOW}[3] 检查 Claude Code...${NC}"
if command -v claude &>/dev/null; then
    VERSION=$(claude --version 2>/dev/null)
    echo -e "  ${GREEN}✓${NC} Claude Code 已安装: $VERSION"
else
    echo -e "  ${RED}✗${NC} Claude Code 未安装"
fi

echo ""

# ── 4. 检查 Python / pip ──────────────────────────────────────────
echo -e "${YELLOW}[4] 检查 Python 环境...${NC}"
if command -v python3 &>/dev/null; then
    PY_VER=$(python3 --version 2>/dev/null)
    echo -e "  ${GREEN}✓${NC} $PY_VER ($(which python3))"
else
    echo -e "  ${RED}✗${NC} Python3 未安装"
fi

echo ""

# ── 5. 设置 Token ────────────────────────────────────────────────
echo -e "${YELLOW}[5] 设置 Token${NC}"
echo -e "  是否要现在设置 / 更新 ANTHROPIC_AUTH_TOKEN？(y/n)"
read -r answer

if [ "$answer" = "y" ] || [ "$answer" = "Y" ]; then
    echo -e "  请粘贴你的 OAuth Token (sk-ant-oat01-...)："
    read -r token

    if [[ "$token" == sk-ant-oat01-* ]]; then
        # 删除旧的配置（避免重复）
        sed -i '' '/ANTHROPIC_AUTH_TOKEN/d' ~/.zprofile 2>/dev/null
        sed -i '' '/ANTHROPIC_API_KEY/d' ~/.zprofile 2>/dev/null

        # 写入新配置（两个名字都写，兼容 LiteLLM）
        echo "" >> ~/.zprofile
        echo "export ANTHROPIC_AUTH_TOKEN=\"$token\"" >> ~/.zprofile
        echo "export ANTHROPIC_API_KEY=\"$token\"" >> ~/.zprofile

        # 当前 session 立即生效
        export ANTHROPIC_AUTH_TOKEN="$token"
        export ANTHROPIC_API_KEY="$token"

        echo -e "  ${GREEN}✓${NC} Token 已写入 ~/.zprofile 并立即生效"
    else
        echo -e "  ${RED}✗${NC} Token 格式不对，应该以 sk-ant-oat01- 开头"
    fi
fi

echo ""

# ── 6. 最终状态汇总 ───────────────────────────────────────────────
echo -e "${BLUE}======================================${NC}"
echo -e "${YELLOW}最终状态：${NC}"
check_var "ANTHROPIC_AUTH_TOKEN"
check_var "ANTHROPIC_API_KEY"
echo -e "${BLUE}======================================${NC}"
echo ""