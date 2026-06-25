#!/usr/bin/env bash
# ============================================================
#  Caddy 反向代理一键部署脚本
#  功能: 自动部署 Caddy + 子域名反向代理 + 自动 HTTPS
#  适用于: Ubuntu / Debian / CentOS / Alpine (Docker 环境)
#  用法:   bash caddy_deploy.sh [选项] [命令]
#
#  选项:
#    -d, --dir DIR          Caddy 工作目录 (默认: /opt/caddy)
#    --domain DOMAIN        基础域名 (用于生成默认配置)
#    --skip-docker          跳过 Docker 安装检查
#    --skip-firewall        跳过防火墙配置
#    --force                强制重装（删除旧配置后重新部署）
#    -h, --help             显示帮助
#
#  命令:
#    add <子域名> <目标地址>   添加反向代理条目
#    del <子域名>              删除反向代理条目
#    reload                    重新加载 Caddy 配置 (不重启容器)
#    restart                   重启 Caddy 容器
#
#  示例:
#    bash caddy_deploy.sh                            # 首次部署
#    bash caddy_deploy.sh add grok2api 127.0.0.1:8000  # 添加 grok2api 反代
#    bash caddy_deploy.sh add blog 127.0.0.1:3000    # 添加 blog 反代
#    bash caddy_deploy.sh reload                      # 热重载配置
#    bash caddy_deploy.sh restart                     # 重启容器
# ============================================================

set -uo pipefail

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
CADDY_DIR="/opt/caddy"
CADDYFILE="${CADDY_DIR}/Caddyfile"
COMPOSE_FILE="${CADDY_DIR}/docker-compose.yml"
BASE_DOMAIN=""
SKIP_DOCKER=false
SKIP_FIREWALL=false
FORCE=false
COMMAND=""
SUBDOMAIN=""
TARGET=""

# -------------------- 参数解析 --------------------
parse_args() {
    while [[ $# -gt 0 ]]; do
        case "$1" in
            -d|--dir)
                CADDY_DIR="$2"; shift 2 ;;
            --domain)
                BASE_DOMAIN="$2"; shift 2 ;;
            --skip-docker)
                SKIP_DOCKER=true; shift ;;
            --skip-firewall)
                SKIP_FIREWALL=true; shift ;;
            --force)
                FORCE=true; shift ;;
            -h|--help)
                show_help; exit 0 ;;
            add|del|reload|restart)
                COMMAND="$1"
                if [[ "$COMMAND" == "add" ]]; then
                    SUBDOMAIN="$2"
                    TARGET="$3"
                    shift 3
                elif [[ "$COMMAND" == "del" ]]; then
                    SUBDOMAIN="$2"
                    shift 2
                else
                    shift
                fi
                ;;
            *)
                die "未知参数: $1 (使用 -h 查看帮助)" ;;
        esac
    done
    # 重新计算路径
    CADDYFILE="${CADDY_DIR}/Caddyfile"
    COMPOSE_FILE="${CADDY_DIR}/docker-compose.yml"
}

show_help() {
    cat <<'EOF'
用法: bash caddy_deploy.sh [选项] [命令]

选项:
  -d, --dir DIR          Caddy 工作目录 (默认: /opt/caddy)
  --domain DOMAIN        基础域名 (如 example.com)
  --skip-docker          跳过 Docker 安装检查
  --skip-firewall        跳过防火墙配置
  --force                强制重装（清理旧配置）
  -h, --help             显示此帮助信息

命令:
  add <子域名> <目标>    添加反向代理条目 (目标如 127.0.0.1:8000)
  del <子域名>           删除反向代理条目
  reload                 热重载 Caddy 配置 (不重启容器)
  restart                重启 Caddy 容器

示例:
  bash caddy_deploy.sh                             # 首次部署 Caddy
  bash caddy_deploy.sh --domain example.com        # 指定基础域名部署
  bash caddy_deploy.sh --force                     # 强制重装（清理旧配置）
  bash caddy_deploy.sh add grok2api 127.0.0.1:8000 # 添加反代
  bash caddy_deploy.sh add blog 127.0.0.1:3000    # 添加第二个反代
  bash caddy_deploy.sh reload                      # 热重载配置
  bash caddy_deploy.sh restart                     # 重启容器
EOF
}

# -------------------- 前置检查 --------------------
check_prerequisites() {
    if [[ $EUID -ne 0 ]]; then
        die "请使用 root 用户运行此脚本 (或 sudo bash $0)"
    fi

    local missing_tools=()
    for tool in curl; do
        if ! command -v "$tool" &>/dev/null; then
            missing_tools+=("$tool")
        fi
    done

    if [[ ${#missing_tools[@]} -gt 0 ]]; then
        info "正在安装缺失工具: ${missing_tools[*]}..."
        if command -v apt-get &>/dev/null; then
            apt-get update -qq && apt-get install -y -qq "${missing_tools[@]}"
        elif command -v yum &>/dev/null; then
            yum install -y -q "${missing_tools[@]}"
        elif command -v apk &>/dev/null; then
            apk add --no-cache "${missing_tools[@]}"
        else
            die "缺少必要工具: ${missing_tools[*]}，请手动安装"
        fi
        success "工具安装完成"
    fi
}

# -------------------- Docker 安装 (幂等) --------------------
install_docker() {
    if $SKIP_DOCKER; then
        info "跳过 Docker 检查"
        return
    fi

    # 检查 docker 命令 + daemon
    if command -v docker &>/dev/null && docker info &>/dev/null; then
        success "Docker 已就绪: $(docker --version)"
        if docker compose version &>/dev/null || command -v docker-compose &>/dev/null; then
            success "Docker Compose 已就绪"
        fi
        return
    fi

    # Docker 已安装但 daemon 未运行
    if command -v docker &>/dev/null; then
        warn "Docker daemon 未运行，尝试启动..."
        start_docker_daemon
        if docker info &>/dev/null; then
            success "Docker daemon 启动成功"
            return
        fi
    fi

    # 安装 Docker
    info "正在安装 Docker..."
    local failed=false
    if command -v curl &>/dev/null; then
        curl -fsSL https://get.docker.com | sh || failed=true
    elif command -v wget &>/dev/null; then
        wget -qO- https://get.docker.com | sh || failed=true
    else
        failed=true
    fi

    if $failed; then
        warn "官方脚本失败，尝试包管理器..."
        install_docker_from_pkg || die "Docker 安装失败"
    fi

    start_docker_daemon
    success "Docker 安装完成"
}

start_docker_daemon() {
    if command -v systemctl &>/dev/null; then
        systemctl enable docker 2>/dev/null || true
        systemctl start docker 2>/dev/null || true
        local retries=0
        while ! docker info &>/dev/null && [[ $retries -lt 15 ]]; do
            sleep 1; ((retries++))
        done
    elif command -v service &>/dev/null; then
        service docker start 2>/dev/null || true; sleep 3
    elif [[ -x /etc/init.d/docker ]]; then
        /etc/init.d/docker start 2>/dev/null || true; sleep 3
    else
        dockerd &>/dev/null &
        sleep 3
    fi
}

install_docker_from_pkg() {
    if command -v apt-get &>/dev/null; then
        apt-get update -qq && apt-get install -y -qq docker.io docker-compose-plugin
    elif command -v yum &>/dev/null; then
        yum install -y -q docker docker-compose
    elif command -v apk &>/dev/null; then
        apk add --no-cache docker docker-compose
    else
        return 1
    fi
}

# -------------------- Caddy 目录与文件初始化 --------------------
init_caddy_dir() {
    if $FORCE && [[ -d "$CADDY_DIR" ]]; then
        info "强制重装: 正在清理旧 Caddy 配置..."
        docker compose -f "$COMPOSE_FILE" down 2>/dev/null || true
        docker rm -f caddy 2>/dev/null || true
        rm -rf "$CADDY_DIR"
        success "旧配置已清理"
    fi

    if [[ ! -d "$CADDY_DIR" ]]; then
        mkdir -p "$CADDY_DIR"
        info "创建 Caddy 目录: ${CADDY_DIR}"
    fi

    # 创建 docker-compose.yml（使用 host 网络模式，使 Caddy 能直接访问宿主机服务）
    if [[ ! -f "$COMPOSE_FILE" ]]; then
        cat > "$COMPOSE_FILE" <<'COMPOSEOF'
services:
  caddy:
    container_name: caddy
    image: caddy:2
    network_mode: host
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile
      - caddy_data:/data
      - caddy_config:/config
    restart: unless-stopped

volumes:
  caddy_data:
  caddy_config:
COMPOSEOF
        success "docker-compose.yml 已创建"
    fi

    # 创建 Caddyfile（如果不存在）
    if [[ ! -f "$CADDYFILE" ]]; then
        cat > "$CADDYFILE" <<'CADDYEOF'
# Caddy 反向代理配置
# 添加条目: bash caddy_deploy.sh add <子域名> <目标地址>
# 示例:     bash caddy_deploy.sh add api 127.0.0.1:8000

# 默认全局配置
{
    http_port 80
    https_port 443
}

# === 子域名反向代理 ===

CADDYEOF
        success "Caddyfile 已创建"
    fi
}

# -------------------- 添加反向代理条目 --------------------
add_proxy() {
    local subdomain="$1"
    local target="$2"

    if [[ -z "$subdomain" || -z "$target" ]]; then
        die "用法: bash $0 add <子域名> <目标地址(如 127.0.0.1:8000)>"
    fi

    # 计算完整域名
    local full_domain
    if [[ -n "$BASE_DOMAIN" ]]; then
        full_domain="${subdomain}.${BASE_DOMAIN}"
    else
        full_domain="${subdomain}"
    fi

    # 检查是否已存在
    if grep -q "^${full_domain} {" "$CADDYFILE" 2>/dev/null; then
        warn "条目 ${full_domain} 已存在，正在更新..."
        # 删除旧条目
        del_proxy "$subdomain" --silent
    fi

    # 追加新条目
    cat >> "$CADDYFILE" <<EOF

${full_domain} {
    reverse_proxy ${target}
    encode gzip
    header {
        X-Real-IP {remote_host}
        X-Forwarded-For {remote_host}
        X-Forwarded-Proto {scheme}
    }
}
EOF

    success "已添加反代: ${full_domain} -> ${target}"
}

# -------------------- 删除反向代理条目 --------------------
del_proxy() {
    local subdomain="$1"
    local silent="${2:-}"

    if [[ -z "$subdomain" ]]; then
        die "用法: bash $0 del <子域名>"
    fi

    local full_domain
    if [[ -n "$BASE_DOMAIN" ]]; then
        full_domain="${subdomain}.${BASE_DOMAIN}"
    else
        full_domain="${subdomain}"
    fi

    if ! grep -q "^${full_domain} {" "$CADDYFILE" 2>/dev/null; then
        [[ -z "$silent" ]] && warn "条目 ${full_domain} 不存在"
        return 1
    fi

    # 使用 awk 精确删除条目块
    awk -v domain="${full_domain}" '
        BEGIN { in_block=0 }
        /^[^#[:space:]]/ { in_block=0 }
        $0 == domain " {" { in_block=1; next }
        in_block && /^\}/ { in_block=0; next }
        !in_block { print }
    ' "$CADDYFILE" > "${CADDYFILE}.tmp" && mv "${CADDYFILE}.tmp" "$CADDYFILE"

    [[ -z "$silent" ]] && success "已删除反代: ${full_domain}"
}

# -------------------- 重新加载 Caddy 配置 --------------------
reload_caddy() {
    info "正在重新加载 Caddy 配置..."

    if ! docker ps --format '{{.Names}}' 2>/dev/null | grep -q "^caddy$"; then
        warn "Caddy 容器未运行，尝试启动..."
        start_caddy
        return
    fi

    # 尝试热重载
    if docker compose -f "$COMPOSE_FILE" exec -T caddy caddy reload --config /etc/caddy/Caddyfile --adapter caddyfile 2>/dev/null; then
        success "Caddy 配置热重载成功"
    else
        warn "热重载失败，尝试重启容器..."
        restart_caddy
    fi
}

# -------------------- 启动/重启 Caddy --------------------
start_caddy() {
    cd "$CADDY_DIR"

    # 检查容器是否已存在
    if docker ps -a --format '{{.Names}}' 2>/dev/null | grep -q "^caddy$"; then
        info "Caddy 容器已存在，正在重启..."
        docker compose -f "$COMPOSE_FILE" down 2>/dev/null || true
    fi

    info "正在启动 Caddy..."
    docker compose -f "$COMPOSE_FILE" up -d

    # 等待启动
    local retries=0
    while [[ $retries -lt 15 ]]; do
        if docker ps --format '{{.Names}}' 2>/dev/null | grep -q "^caddy$"; then
            break
        fi
        sleep 1; ((retries++))
    done

    if docker ps --format '{{.Names}}' 2>/dev/null | grep -q "^caddy$"; then
        success "Caddy 启动成功"
    else
        die "Caddy 启动失败，请检查日志: cd ${CADDY_DIR} && docker compose logs"
    fi
}

restart_caddy() {
    cd "$CADDY_DIR"
    docker compose -f "$COMPOSE_FILE" down 2>/dev/null || true
    docker compose -f "$COMPOSE_FILE" up -d
    success "Caddy 已重启"
}

# -------------------- 防火墙配置 --------------------
setup_firewall() {
    if $SKIP_FIREWALL; then
        info "跳过防火墙配置"
        return
    fi

    info "配置防火墙放行 80/443..."

    for port in 80 443; do
        if command -v ufw &>/dev/null && ufw status 2>/dev/null | grep -q "active"; then
            ufw allow "${port}/tcp" 2>/dev/null
        elif command -v firewall-cmd &>/dev/null && systemctl is-active --quiet firewalld 2>/dev/null; then
            firewall-cmd --permanent --add-port="${port}/tcp" 2>/dev/null
        elif command -v iptables &>/dev/null; then
            iptables -C INPUT -p tcp --dport "$port" -j ACCEPT 2>/dev/null \
                || iptables -A INPUT -p tcp --dport "$port" -j ACCEPT 2>/dev/null
        fi
    done

    if command -v firewall-cmd &>/dev/null && systemctl is-active --quiet firewalld 2>/dev/null; then
        firewall-cmd --reload 2>/dev/null
    fi

    success "防火墙已放行 80/443"
}

# -------------------- 显示信息 --------------------
show_info() {
    echo ""
    echo "============================================================"
    echo -e "${GREEN}${BOLD}  Caddy 反向代理部署完成！${NC}"
    echo "============================================================"
    echo ""
    echo "  工作目录:   ${CADDY_DIR}"
    echo "  Caddyfile:  ${CADDYFILE}"
    echo "  Compose:    ${COMPOSE_FILE}"
    echo ""
    echo "  常用命令:"
    echo "    查看日志:   cd ${CADDY_DIR} && docker compose logs -f"
    echo "    热重载:     bash ${0} -d ${CADDY_DIR} reload"
    echo "    重启容器:   bash ${0} -d ${CADDY_DIR} restart"
    echo "    添加反代:   bash ${0} -d ${CADDY_DIR} add <子域名> <目标地址>"
    echo "    删除反代:   bash ${0} -d ${CADDY_DIR} del <子域名>"
    echo ""
    echo "  示例:"
    echo "    bash ${0} -d ${CADDY_DIR} add grok2api 127.0.0.1:8000"
    echo "    bash ${0} -d ${CADDY_DIR} add blog 127.0.0.1:3000"
    echo ""
    echo "============================================================"
}

# -------------------- 主流程 --------------------
main() {
    parse_args "$@"

    echo ""
    echo -e "${CYAN}============================================================${NC}"
    echo -e "${CYAN}  Caddy 反向代理一键部署脚本${NC}"
    echo -e "${CYAN}============================================================${NC}"
    echo ""

    info "工作目录: ${CADDY_DIR}"
    [[ -n "$BASE_DOMAIN" ]] && info "基础域名: ${BASE_DOMAIN}"
    echo ""

    # 执行子命令
    case "$COMMAND" in
        add)
            check_prerequisites
            install_docker
            init_caddy_dir
            add_proxy "$SUBDOMAIN" "$TARGET"
            reload_caddy
            ;;
        del)
            check_prerequisites
            install_docker
            init_caddy_dir
            del_proxy "$SUBDOMAIN"
            reload_caddy
            ;;
        reload)
            check_prerequisites
            install_docker
            init_caddy_dir
            reload_caddy
            ;;
        restart)
            check_prerequisites
            install_docker
            init_caddy_dir
            restart_caddy
            ;;
        "")
            # 无命令 = 首次部署
            check_prerequisites
            install_docker
            init_caddy_dir
            start_caddy
            setup_firewall
            show_info
            ;;
        *)
            die "未知命令: $COMMAND" ;;
    esac
}

main "$@"
