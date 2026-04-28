#!/bin/bash
# ============================================================
# WrenAI 云主机部署脚本
# 位置: Research/deploy.sh
#
# 用法:
#   bash deploy.sh build [ui|ai|chart|all]  构建镜像
#   bash deploy.sh up                       启动所有服务
#   bash deploy.sh down                     停止所有服务
#   bash deploy.sh restart [ui|ai|...]      重启服务
#   bash deploy.sh rebuild [ui|ai|all]      构建 + 重启（最常用）
#   bash deploy.sh logs [ui|ai|...]         查看日志
#   bash deploy.sh status                   查看服务状态
#   bash deploy.sh clean                    清理悬空镜像
#   bash deploy.sh check                    网络诊断
# ============================================================

set -e

# ---- 路径配置 ----
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# Research/
PROJECT_ROOT="$SCRIPT_DIR"
# Research/data-agent/WrenAI/
WRENAI_ROOT="$PROJECT_ROOT/data-agent/WrenAI"
DOCKER_DIR="$WRENAI_ROOT/docker"
UI_DIR="$WRENAI_ROOT/wren-ui"
AI_DIR="$WRENAI_ROOT/wren-ai-service"
CHART_DIR="$PROJECT_ROOT/data-agent/chart_engine"
COMPOSE_FILE="$DOCKER_DIR/docker-compose-dev.yaml"

# ---- 代理配置 ----
# Docker 桥接网关 IP（daemon.json 配的 172.20.0.0/16）
DOCKER_BRIDGE_IP="172.20.0.1"
PROXY_URL="http://${DOCKER_BRIDGE_IP}:3128"

# ---- Ollama ----
OLLAMA_HOST="10.220.239.55"
OLLAMA_PORT="11434"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

info()  { echo -e "${GREEN}>>>${NC} $1"; }
warn()  { echo -e "${YELLOW}>>>${NC} $1"; }
error() { echo -e "${RED}>>>${NC} $1"; exit 1; }

# ---- 前置检查 ----
preflight() {
    # Docker 是否运行
    docker info >/dev/null 2>&1 || error "Docker 未运行，请先 systemctl start docker"

    # socat 转发是否在（systemd 服务自动管理）
    if ! ss -tlnp | grep -q "${DOCKER_BRIDGE_IP}:3128"; then
        warn "socat 转发未运行，容器 build 可能无法访问代理"
        warn "检查: systemctl status socat-docker-proxy"
    fi

    # iptables FORWARD
    local policy=$(iptables -L FORWARD -n 2>/dev/null | head -1 | grep -oP '\(policy \K[A-Z]+')
    if [ "$policy" != "ACCEPT" ]; then
        info "修复 iptables FORWARD 策略..."
        iptables -P FORWARD ACCEPT
    fi
}

# ---- 构建 ----
build_ui() {
    preflight
    info "构建 wren-ui 镜像（使用 Dockerfile.cloud）..."
    cd "$UI_DIR"
    DOCKER_BUILDKIT=0 docker build \
        --build-arg HTTP_PROXY=$PROXY_URL \
        --build-arg HTTPS_PROXY=$PROXY_URL \
        -t wrenai-wren-ui:latest \
        -f Dockerfile.cloud .
    info "wren-ui 构建完成"
}

build_ai() {
    preflight
    info "构建 wren-ai-service 镜像（使用 Dockerfile.cloud）..."
    cd "$AI_DIR"
    DOCKER_BUILDKIT=0 docker build \
        --build-arg HTTP_PROXY=$PROXY_URL \
        --build-arg HTTPS_PROXY=$PROXY_URL \
        -t wrenai-wren-ai-service:latest \
        -f docker/Dockerfile.cloud .
    info "wren-ai-service 构建完成"
}

build_chart() {
    preflight
    info "构建 chart-engine 镜像..."
    cd "$CHART_DIR"
    DOCKER_BUILDKIT=0 docker build \
        --build-arg HTTP_PROXY=$PROXY_URL \
        --build-arg HTTPS_PROXY=$PROXY_URL \
        -t chart-engine:latest \
        -f Dockerfile .
    info "chart-engine 构建完成"
}

# ---- Compose 操作 ----
compose_up() {
    preflight
    info "启动所有服务..."
    cd "$DOCKER_DIR"
    docker compose -f "$COMPOSE_FILE" up -d --no-build --pull never
    info "服务已启动"
    sleep 3
    compose_status
}

compose_down() {
    info "停止所有服务..."
    cd "$DOCKER_DIR"
    docker compose -f "$COMPOSE_FILE" down
    info "服务已停止"
}

compose_restart_service() {
    local service=$1
    info "重启 $service..."
    cd "$DOCKER_DIR"
    docker compose -f "$COMPOSE_FILE" restart "$service"
    info "$service 已重启"
}

compose_status() {
    cd "$DOCKER_DIR"
    docker compose -f "$COMPOSE_FILE" ps
}

compose_logs() {
    local service=$1
    cd "$DOCKER_DIR"
    if [ -n "$service" ]; then
        docker compose -f "$COMPOSE_FILE" logs -f --tail 50 "$service"
    else
        docker compose -f "$COMPOSE_FILE" logs -f --tail 50
    fi
}

# ---- 服务名映射 ----
resolve_service() {
    case "$1" in
        ui)     echo "wren-ui" ;;
        ai)     echo "wren-ai-service" ;;
        chart)  echo "chart-engine" ;;
        engine) echo "wren-engine" ;;
        ibis)   echo "ibis-server" ;;
        qdrant) echo "qdrant" ;;
        *)      echo "$1" ;;
    esac
}

# ---- 网络诊断 ----
check_network() {
    echo "============================================================"
    echo "  WrenAI 网络诊断 — $(date)"
    echo "============================================================"
    echo ""

    # 1. cntlm
    echo "1. 本地代理 (cntlm)"
    if ss -tlnp | grep -q "127.0.0.1:3128"; then
        echo -e "  ${GREEN}✓${NC} cntlm 在监听 127.0.0.1:3128"
    else
        echo -e "  ${RED}✗${NC} cntlm 未运行"
    fi

    # 2. socat
    echo ""
    echo "2. socat 转发"
    if ss -tlnp | grep -q "${DOCKER_BRIDGE_IP}:3128"; then
        echo -e "  ${GREEN}✓${NC} socat 在监听 ${DOCKER_BRIDGE_IP}:3128"
    else
        echo -e "  ${RED}✗${NC} socat 未运行 — systemctl start socat-docker-proxy"
    fi

    # 3. 外网
    echo ""
    echo "3. 代理出外网"
    local code=$(curl -x http://127.0.0.1:3128 -k -s -o /dev/null -w "%{http_code}" --connect-timeout 10 https://github.com 2>/dev/null)
    if [ "$code" = "200" ] || [ "$code" = "301" ]; then
        echo -e "  ${GREEN}✓${NC} GitHub 可达 (HTTP $code)"
    else
        echo -e "  ${RED}✗${NC} GitHub 不可达 (HTTP $code) — 检查上游代理"
    fi

    # 4. GitHub SSH
    echo ""
    echo "4. GitHub SSH"
    local ssh_result=$(ssh -T git@github.com 2>&1 | head -1)
    if echo "$ssh_result" | grep -q "successfully"; then
        echo -e "  ${GREEN}✓${NC} GitHub SSH 认证成功"
    else
        echo -e "  ${RED}✗${NC} GitHub SSH: $ssh_result"
    fi

    # 5. Ollama
    echo ""
    echo "5. Ollama ($OLLAMA_HOST)"
    local model_count=$(curl -s "http://${OLLAMA_HOST}:${OLLAMA_PORT}/api/tags" 2>/dev/null | python3 -c "import sys,json; print(len(json.load(sys.stdin).get('models',[])))" 2>/dev/null)
    if [ -n "$model_count" ] && [ "$model_count" -gt 0 ]; then
        echo -e "  ${GREEN}✓${NC} Ollama 正常，$model_count 个模型"
    else
        echo -e "  ${RED}✗${NC} Ollama 不可达"
    fi

    # 6. Docker
    echo ""
    echo "6. Docker"
    if docker info >/dev/null 2>&1; then
        echo -e "  ${GREEN}✓${NC} Docker daemon 运行中"
    else
        echo -e "  ${RED}✗${NC} Docker 未运行"
    fi
    local policy=$(iptables -L FORWARD -n 2>/dev/null | head -1 | grep -oP '\(policy \K[A-Z]+')
    if [ "$policy" = "ACCEPT" ]; then
        echo -e "  ${GREEN}✓${NC} iptables FORWARD: ACCEPT"
    else
        echo -e "  ${RED}✗${NC} iptables FORWARD: $policy — 需要 iptables -P FORWARD ACCEPT"
    fi

    # 7. 容器内 Ollama
    echo ""
    echo "7. 容器内访问 Ollama"
    local test=$(docker run --rm python:3.12.0-slim-bookworm python3 -c "
import urllib.request
try:
    r = urllib.request.urlopen('http://${OLLAMA_HOST}:${OLLAMA_PORT}/api/tags', timeout=5)
    print('OK')
except Exception as e:
    print(f'FAIL: {e}')
" 2>/dev/null)
    if echo "$test" | grep -q "OK"; then
        echo -e "  ${GREEN}✓${NC} 容器内可访问 Ollama"
    else
        echo -e "  ${RED}✗${NC} 容器内无法访问 Ollama: $test"
    fi

    # 8. PLATFORM
    echo ""
    echo "8. 配置检查"
    local env_file="$DOCKER_DIR/.env"
    if [ -f "$env_file" ]; then
        local platform=$(grep "^PLATFORM=" "$env_file" | cut -d= -f2)
        local arch=$(uname -m)
        if [ "$arch" = "x86_64" ] && [ "$platform" = "linux/amd64" ]; then
            echo -e "  ${GREEN}✓${NC} PLATFORM=$platform 匹配 $arch"
        else
            echo -e "  ${RED}✗${NC} PLATFORM=$platform 与 $arch 不匹配！"
        fi
    else
        echo -e "  ${YELLOW}!${NC} .env 不存在"
    fi

    echo ""
    echo "============================================================"
}

# ---- 主逻辑 ----
case "${1:-help}" in
    build)
        case "${2:-all}" in
            ui)    build_ui ;;
            ai)    build_ai ;;
            chart) build_chart ;;
            all)   build_ui; build_ai; build_chart ;;
            *)     error "未知服务: $2 (可选: ui, ai, chart, all)" ;;
        esac
        ;;

    up)
        compose_up
        ;;

    down)
        compose_down
        ;;

    restart)
        service=$(resolve_service "${2:-}")
        if [ -n "$2" ]; then
            compose_restart_service "$service"
        else
            compose_down
            compose_up
        fi
        ;;

    rebuild)
        case "${2:-all}" in
            ui)
                build_ui
                compose_restart_service "wren-ui"
                ;;
            ai)
                build_ai
                compose_restart_service "wren-ai-service"
                ;;
            chart)
                build_chart
                compose_restart_service "chart-engine"
                ;;
            all)
                build_ui
                build_ai
                build_chart
                compose_down
                compose_up
                ;;
            *)
                error "未知服务: $2 (可选: ui, ai, chart, all)"
                ;;
        esac
        ;;

    logs)
        service=$(resolve_service "${2:-}")
        compose_logs "$service"
        ;;

    status)
        compose_status
        ;;

    clean)
        info "清理悬空镜像和停止的容器..."
        docker container prune -f
        docker image prune -f
        info "清理完成"
        ;;

    check)
        check_network
        ;;

    help|*)
        echo "WrenAI 云主机部署脚本"
        echo ""
        echo "用法: bash deploy.sh <命令> [服务]"
        echo ""
        echo "命令:"
        echo "  build [ui|ai|chart|all]  构建镜像（默认 all）"
        echo "  up                       启动所有服务"
        echo "  down                     停止所有服务"
        echo "  restart [ui|ai|...]      重启服务（默认全部）"
        echo "  rebuild [ui|ai|chart|all] 构建 + 重启（最常用）"
        echo "  logs [ui|ai|chart|...]   查看日志"
        echo "  status                   查看服务状态"
        echo "  clean                    清理悬空镜像/容器"
        echo "  check                    网络诊断"
        echo ""
        echo "日常操作:"
        echo "  bash deploy.sh rebuild ui      # 改了前端代码"
        echo "  bash deploy.sh rebuild ai      # 改了 AI service"
        echo "  bash deploy.sh rebuild chart   # 改了 chart-engine"
        echo "  bash deploy.sh rebuild all     # 全部重建"
        echo "  bash deploy.sh logs ai         # 看 AI service 日志"
        echo "  bash deploy.sh check           # 网络不通时排查"
        ;;
esac
