#!/usr/bin/env bash
# ============================================================
#  一键启动/更新全部服务 (shiso_stock_tracker + Caddy 反向代理)
#  适用于: Ubuntu / Debian / CentOS / Alpine
#  用法:   bash startall.sh [选项]
#  选项:
#    --domain DOMAIN        基础域名 (如 example.com)
#    --port PORT            shiso_stock_tracker 端口 (默认: 8000)
#    --subdomain NAME       shiso 子域名 (默认: stock)
#    --skip-docker          跳过 Docker 安装检查
#    --force                强制重装 Caddy（删除旧配置后重新部署）
#    -h, --help             显示帮助
#
#  行为:
#    首次执行: 安装 Docker → 部署 shiso_stock_tracker → 部署 Caddy → 添加反代
#    再次执行: 更新 shiso_stock_tracker → 重启 → 重载 Caddy
# ============================================================

set -uo pipefail

# -------------------- 脚本所在目录 --------------------
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# -------------------- 颜色定义 --------------------
if [[ -t 1 ]] && command -v tput &>/dev/null && [[ $(tput colors 2>/dev/null || echo 0) -ge 8 ]]; then
    RED='\033[0;31m'
    GREEN='\033[0;32m'
    YELLOW='\033[1;33m'
    CYAN='\033[0;36m'
    BOLD='\033[1m'
    NC='\033[0m'
else
    RED='' GREEN='' YELLOW='' CYAN='' BOLD='' NC=''
fi

info()    { echo -e "${CYAN}[INFO]${NC} $*"; }
success() { echo -e "${GREEN}[OK]${NC} $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC} $*"; }
error()   { echo -e "${RED}[ERROR]${NC} $*"; }
die()     { error "$@"; exit 1; }

# -------------------- 默认配置 --------------------
BASE_DOMAIN=""
SHISO_PORT=8000
SUBDOMAIN="stock"
SKIP_DOCKER=false
FORCE=false

# -------------------- 参数解析 --------------------
while [[ $# -gt 0 ]]; do
    case "$1" in
        --domain)
            BASE_DOMAIN="$2"; shift 2 ;;
        --port)
            SHISO_PORT="$2"; shift 2 ;;
        --subdomain)
            SUBDOMAIN="$2"; shift 2 ;;
        --skip-docker)
            SKIP_DOCKER=true; shift ;;
        --force)
            FORCE=true; shift ;;
        -h|--help)
            cat <<EOF
用法: bash $0 [选项]

选项:
  --domain DOMAIN        基础域名 (如 example.com，用于 Caddy 子域名反代)
  --port PORT            shiso_stock_tracker 端口 (默认: 8000)
  --subdomain NAME       shiso_stock_tracker 子域名 (默认: stock)
  --skip-docker          跳过 Docker 安装检查
  --force                强制重装 Caddy（删除旧配置后重新部署）
  -h, --help             显示帮助

示例:
  bash $0                                    # 默认部署
  bash $0 --domain example.com              # 指定域名
  bash $0 --domain example.com --port 9000  # 自定义域名和端口
  bash $0 --domain example.com --force      # 强制重装 Caddy
EOF
            exit 0 ;;
        *)
            die "未知参数: $1 (使用 -h 查看帮助)" ;;
    esac
done

# -------------------- 脚本文件检查 --------------------
DEPLOY_SCRIPT="${SCRIPT_DIR}/shiso_deploy.sh"
CADDY_SCRIPT="${SCRIPT_DIR}/caddy_deploy.sh"

for f in "$DEPLOY_SCRIPT" "$CADDY_SCRIPT"; do
    if [[ ! -f "$f" ]]; then
        die "找不到脚本: $f (请确保与 startall.sh 在同一目录)"
    fi
done

# -------------------- 构建公共参数 --------------------
DOCKER_ARG=""
$SKIP_DOCKER && DOCKER_ARG="--skip-docker"

CADDY_DIR_ARG=""
CADDY_DOMAIN_ARG=""
FORCE_ARG=""
[[ -n "$BASE_DOMAIN" ]] && CADDY_DOMAIN_ARG="--domain ${BASE_DOMAIN}"
$FORCE && FORCE_ARG="--force"

# -------------------- 判断首次/更新 / Caddy 配置是否有效 --------------------
FIRST_RUN=false
CADDY_NEED_REBUILD=false

if [[ ! -d "/opt/caddy" ]] || [[ ! -f "/opt/caddy/docker-compose.yml" ]]; then
    FIRST_RUN=true
fi

# 检测 Caddyfile 是否有效
if [[ -f "/opt/caddy/Caddyfile" ]]; then
    if grep -q "auto_https off" /opt/caddy/Caddyfile 2>/dev/null; then
        warn "检测到旧版 Caddyfile (auto_https off)，需要重建"
        CADDY_NEED_REBUILD=true
    fi
    # 检查是否包含任何反代域名条目
    if ! grep -v "^#" /opt/caddy/Caddyfile 2>/dev/null | grep -v "^{" | grep -v "^}" | grep -q "[a-zA-Z]"; then
        warn "Caddyfile 中无反向代理条目，需要重建"
        CADDY_NEED_REBUILD=true
    fi
else
    CADDY_NEED_REBUILD=true
fi

# 如果需要重建，先强制清理旧配置
if $CADDY_NEED_REBUILD && ! $FORCE; then
    info "Caddy 配置需要重建，自动启用 --force"
    FORCE=true
    FORCE_ARG="--force"
fi

# -------------------- 主流程 --------------------
echo ""
echo -e "${CYAN}============================================================${NC}"
echo -e "${CYAN}  一键启动全部服务${NC}"
echo -e "${CYAN}============================================================${NC}"
echo ""
info "shiso_stock_tracker 端口: ${SHISO_PORT}"
[[ -n "$BASE_DOMAIN" ]] && info "基础域名: ${BASE_DOMAIN}"
[[ -n "$BASE_DOMAIN" ]] && info "访问地址: https://${SUBDOMAIN}.${BASE_DOMAIN}"
if $FIRST_RUN; then
    info "模式: 首次部署"
elif $CADDY_NEED_REBUILD; then
    info "模式: Caddy 配置重建"
else
    info "模式: 更新重启"
fi
echo ""

# ---- Step 1: 部署/更新 shiso_stock_tracker ----
info "========== [1/3] 部署 shiso_stock_tracker =========="
bash "$DEPLOY_SCRIPT" \
    --port "$SHISO_PORT" \
    --skip-firewall \
    $DOCKER_ARG
if [[ $? -ne 0 ]]; then
    die "shiso_stock_tracker 部署失败，终止执行"
fi
echo ""

# ---- Step 2: 部署/重启 Caddy ----
info "========== [2/3] 部署 Caddy =========="
if $FIRST_RUN || $FORCE; then
    bash "$CADDY_SCRIPT" \
        $CADDY_DIR_ARG \
        $CADDY_DOMAIN_ARG \
        $FORCE_ARG \
        $DOCKER_ARG
    if [[ $? -ne 0 ]]; then
        die "Caddy 部署失败，终止执行"
    fi
else
    bash "$CADDY_SCRIPT" \
        $CADDY_DIR_ARG \
        $CADDY_DOMAIN_ARG \
        $FORCE_ARG \
        $DOCKER_ARG \
        restart
    if [[ $? -ne 0 ]]; then
        die "Caddy 重启失败，终止执行"
    fi
fi
echo ""

# ---- Step 3: 配置反向代理 ----
info "========== [3/3] 配置反向代理 =========="
if [[ -n "$BASE_DOMAIN" ]]; then
    bash "$CADDY_SCRIPT" \
        $CADDY_DIR_ARG \
        $CADDY_DOMAIN_ARG \
        $FORCE_ARG \
        $DOCKER_ARG \
        add "$SUBDOMAIN" "127.0.0.1:${SHISO_PORT}"
else
    warn "未指定 --domain，跳过 Caddy 反代配置"
    warn "如需配置反代，请执行:"
    warn "  bash caddy_deploy.sh add ${SUBDOMAIN} 127.0.0.1:${SHISO_PORT}"
fi
echo ""

# ---- 完成 ----
echo "============================================================"
echo -e "${GREEN}${BOLD}  全部服务启动完成！${NC}"
echo "============================================================"
echo ""
echo "  服务状态:"
echo "    shiso_stock_tracker:  127.0.0.1:${SHISO_PORT}"
if [[ -n "$BASE_DOMAIN" ]]; then
    echo "    Caddy 反代: https://${SUBDOMAIN}.${BASE_DOMAIN}"
fi
echo ""
echo "  常用命令:"
echo "    更新全部:   bash $0 $([[ -n "$BASE_DOMAIN" ]] && echo "--domain ${BASE_DOMAIN}")"
echo "    查看 shiso 日志: cd /opt/shiso_stock_tracker && docker compose logs -f"
echo "    查看 Caddy 日志:    cd /opt/caddy && docker compose logs -f"
echo ""
echo "============================================================"
