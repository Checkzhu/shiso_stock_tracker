#!/usr/bin/env bash
# ============================================================
#  shiso_stock_tracker 一键部署脚本 (幂等版)
#  适用于: Ubuntu 20.04+ / Debian 11+ / CentOS 7+ / Alpine
#  用法:   bash shiso_deploy.sh [选项]
#  选项:
#    -p, --port PORT       服务端口 (默认: 8000)
#    -d, --dir DIR         项目目录 (默认: /opt/shiso_stock_tracker)
#    -r, --repo URL        Git 仓库地址
#    -b, --branch BRANCH   Git 分支 (默认: main)
#    --skip-docker         跳过 Docker 安装检查
#    --skip-firewall       跳过防火墙配置
#    -h, --help            显示帮助
# ============================================================

# -------------------- 严格模式 --------------------
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
PROJECT_DIR="/opt/shiso_stock_tracker"
COMPOSE_FILE="${PROJECT_DIR}/docker-compose.yml"
ENV_FILE="${PROJECT_DIR}/.env"
HOST_PORT=8000
GIT_REPO="https://github.com/Checkzhu/shiso_stock_tracker.git"
GIT_BRANCH="main"
SKIP_DOCKER=false
SKIP_FIREWALL=false

# -------------------- 参数解析 --------------------
parse_args() {
    while [[ $# -gt 0 ]]; do
        case "$1" in
            -p|--port)
                HOST_PORT="$2"; shift 2 ;;
            -d|--dir)
                PROJECT_DIR="$2"; shift 2 ;;
            -r|--repo)
                GIT_REPO="$2"; shift 2 ;;
            -b|--branch)
                GIT_BRANCH="$2"; shift 2 ;;
            --skip-docker)
                SKIP_DOCKER=true; shift ;;
            --skip-firewall)
                SKIP_FIREWALL=true; shift ;;
            -h|--help)
                show_help; exit 0 ;;
            *)
                die "未知参数: $1 (使用 -h 查看帮助)" ;;
        esac
    done
    # 重新计算依赖路径
    COMPOSE_FILE="${PROJECT_DIR}/docker-compose.yml"
    ENV_FILE="${PROJECT_DIR}/.env"
}

show_help() {
    cat <<EOF
用法: bash $0 [选项]

选项:
  -p, --port PORT         服务端口 (默认: 8000)
  -d, --dir DIR           项目安装目录 (默认: /opt/shiso_stock_tracker)
  -r, --repo URL          Git 仓库地址
  -b, --branch BRANCH     Git 分支 (默认: main)
  --skip-docker           跳过 Docker 安装检查
  --skip-firewall         跳过防火墙配置
  -h, --help              显示此帮助信息

示例:
  bash $0                              # 默认部署
  bash $0 -p 9000                      # 使用 9000 端口
  bash $0 --skip-docker --skip-firewall  # 仅部署应用
EOF
}

# -------------------- 前置检查 --------------------
check_prerequisites() {
    # 检查 root 权限
    if [[ $EUID -ne 0 ]]; then
        die "请使用 root 用户运行此脚本 (或 sudo bash $0)"
    fi

    # 检查基本工具
    local missing_tools=()
    for tool in curl git; do
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

check_os() {
    local os_name="Unknown"
    local os_version=""

    if [[ -f /etc/os-release ]]; then
        . /etc/os-release
        os_name="${NAME:-Unknown}"
        os_version="${VERSION_ID:-}"
    elif [[ -f /etc/alpine-release ]]; then
        os_name="Alpine Linux"
        os_version=$(cat /etc/alpine-release)
    elif command -v lsb_release &>/dev/null; then
        os_name=$(lsb_release -si 2>/dev/null)
        os_version=$(lsb_release -sr 2>/dev/null)
    elif [[ -f /etc/redhat-release ]]; then
        os_name=$(cat /etc/redhat-release)
    fi

    info "操作系统: ${os_name} ${os_version}"
}

# -------------------- Docker 安装与管理 --------------------
install_docker() {
    if $SKIP_DOCKER; then
        info "跳过 Docker 检查 (按 --skip-docker)"
        return
    fi

    # 检查 docker 命令是否可用
    if command -v docker &>/dev/null; then
        # 检查 docker daemon 是否运行
        if docker info &>/dev/null; then
            success "Docker 已安装且运行中: $(docker --version)"
            # 检查 docker compose
            if docker compose version &>/dev/null; then
                success "Docker Compose 插件已就绪"
            elif command -v docker-compose &>/dev/null; then
                success "Docker Compose (standalone) 已就绪"
            else
                warn "未检测到 Docker Compose，尝试安装..."
                install_docker_compose
            fi
            return
        else
            warn "Docker 已安装但 daemon 未运行，尝试启动..."
            start_docker_daemon
            if docker info &>/dev/null; then
                success "Docker daemon 启动成功"
                return
            fi
        fi
    fi

    info "正在安装 Docker..."
    local install_script_failed=false

    # 方法1: 官方安装脚本
    if command -v curl &>/dev/null; then
        if curl -fsSL https://get.docker.com | sh; then
            success "Docker 安装完成"
        else
            install_script_failed=true
        fi
    elif command -v wget &>/dev/null; then
        if wget -qO- https://get.docker.com | sh; then
            success "Docker 安装完成"
        else
            install_script_failed=true
        fi
    else
        install_script_failed=true
    fi

    if $install_script_failed; then
        # 方法2: 包管理器安装
        warn "官方安装脚本失败，尝试包管理器安装..."
        install_docker_from_package_manager || die "Docker 安装失败，请手动安装: https://docs.docker.com/engine/install/"
    fi

    start_docker_daemon
    success "Docker 安装并启动完成: $(docker --version)"
}

start_docker_daemon() {
    # 尝试多种方式启动 Docker daemon
    if command -v systemctl &>/dev/null; then
        systemctl enable docker 2>/dev/null || true
        systemctl start docker 2>/dev/null || true
        # 等待 daemon 就绪
        local retries=0
        while ! docker info &>/dev/null && [[ $retries -lt 15 ]]; do
            sleep 1
            ((retries++))
        done
    elif command -v service &>/dev/null; then
        service docker start 2>/dev/null || true
        sleep 3
    elif [[ -x /etc/init.d/docker ]]; then
        /etc/init.d/docker start 2>/dev/null || true
        sleep 3
    else
        # dockerd 直接启动 (容器环境常见)
        dockerd &>/dev/null &
        sleep 3
    fi
}

install_docker_compose() {
    local arch
    arch=$(uname -m)
    case "$arch" in
        x86_64)  arch="x86_64" ;;
        aarch64) arch="aarch64" ;;
        armv7l)  arch="armv7l" ;;
        *)       die "不支持的架构: $arch" ;;
    esac

    local compose_url="https://github.com/docker/compose/releases/latest/download/docker-compose-linux-${arch}"
    info "正在下载 Docker Compose (${arch})..."
    curl -fsSL "$compose_url" -o /usr/local/bin/docker-compose \
        && chmod +x /usr/local/bin/docker-compose \
        && success "Docker Compose 安装完成"
}

install_docker_from_package_manager() {
    if command -v apt-get &>/dev/null; then
        apt-get update -qq
        apt-get install -y -qq docker.io docker-compose-plugin
    elif command -v yum &>/dev/null; then
        yum install -y -q docker docker-compose
    elif command -v apk &>/dev/null; then
        apk add --no-cache docker docker-compose
    else
        return 1
    fi
}

# -------------------- 项目部署 (幂等) --------------------
deploy() {
    local is_update=false

    if [[ -d "$PROJECT_DIR" && -d "${PROJECT_DIR}/.git" ]]; then
        is_update=true
        info "检测到已部署项目，正在更新..."
        cd "$PROJECT_DIR"
        git fetch origin "$GIT_BRANCH" 2>/dev/null || warn "git fetch 失败"
        git checkout "$GIT_BRANCH" 2>/dev/null || warn "git checkout 失败"
        if git pull origin "$GIT_BRANCH" 2>/dev/null; then
            success "代码更新成功"
        else
            warn "git pull 失败，使用现有代码"
        fi
        cd -
    elif [[ -d "$PROJECT_DIR" ]]; then
        warn "目录存在但不是 Git 仓库，跳过更新"
    else
        info "正在克隆项目..."
        mkdir -p "$(dirname "$PROJECT_DIR")"
        git clone -b "$GIT_BRANCH" --depth 1 "$GIT_REPO" "$PROJECT_DIR" \
            || die "克隆仓库失败: ${GIT_REPO}"
        success "项目克隆完成"
    fi

    # 处理 .env 文件
    handle_env_file

    # 创建必要的目录
    mkdir -p "${PROJECT_DIR}/data" "${PROJECT_DIR}/reports" "${PROJECT_DIR}/source"

    cd "$PROJECT_DIR"

    if $is_update; then
        info "正在拉取最新镜像并重启服务..."
        docker compose -f "$COMPOSE_FILE" pull 2>/dev/null || warn "拉取镜像失败，使用本地镜像"
        info "正在停止旧容器..."
        docker compose -f "$COMPOSE_FILE" down 2>/dev/null || true
    else
        info "正在拉取最新镜像..."
        docker compose -f "$COMPOSE_FILE" pull 2>/dev/null || warn "拉取镜像失败，尝试使用本地镜像"
    fi

    info "正在启动服务..."
    docker compose -f "$COMPOSE_FILE" up -d

    # 等待服务启动
    info "等待服务启动..."
    local retries=0
    local max_retries=30
    while [[ $retries -lt $max_retries ]]; do
        if docker compose -f "$COMPOSE_FILE" ps --format '{{.State}}' 2>/dev/null | grep -q "running"; then
            break
        fi
        sleep 2
        ((retries++))
    done

    # 检查服务状态
    if docker compose -f "$COMPOSE_FILE" ps 2>/dev/null | grep -q "running\|Up"; then
        if $is_update; then
            success "服务更新并重启成功！"
        else
            success "服务启动成功！"
        fi
    else
        warn "服务可能未完全启动，请检查日志:"
        warn "  cd ${PROJECT_DIR} && docker compose logs -f"
    fi
}

handle_env_file() {
    if [[ ! -f "$ENV_FILE" ]]; then
        if [[ -f "${PROJECT_DIR}/.env.example" ]]; then
            cp "${PROJECT_DIR}/.env.example" "$ENV_FILE"
            success ".env 文件已从模板创建"
        else
            cat > "$ENV_FILE" <<'ENVEOF'
# shiso_stock_tracker 配置文件
APP_PORT=8000
DATABASE_URL=sqlite:///./data/stock_tracker.db
REPORTS_DIR=./reports
SOURCE_DIR=./source
TZ=Asia/Shanghai
ENVEOF
            warn ".env.example 不存在，已创建基础 .env"
        fi
    else
        info ".env 文件已存在，保留现有配置"
    fi

    # 确保 APP_PORT 写入 .env
    if ! grep -q "^APP_PORT=" "$ENV_FILE" 2>/dev/null; then
        echo "APP_PORT=${HOST_PORT}" >> "$ENV_FILE"
    else
        # 更新已有 APP_PORT
        sed -i.bak "s/^APP_PORT=.*/APP_PORT=${HOST_PORT}/" "$ENV_FILE" 2>/dev/null \
            && rm -f "${ENV_FILE}.bak" \
            || sed -i "s/^APP_PORT=.*/APP_PORT=${HOST_PORT}/" "$ENV_FILE" 2>/dev/null \
            || warn "无法更新 APP_PORT，请手动编辑 ${ENV_FILE}"
    fi
}

# -------------------- 防火墙配置 --------------------
setup_firewall() {
    if $SKIP_FIREWALL; then
        info "跳过防火墙配置 (按 --skip-firewall)"
        return
    fi

    info "配置防火墙放行端口 ${HOST_PORT}..."

    if command -v ufw &>/dev/null; then
        if ufw status 2>/dev/null | grep -q "active"; then
            ufw allow "${HOST_PORT}/tcp" 2>/dev/null
            success "UFW 防火墙已放行端口 ${HOST_PORT}"
        else
            info "UFW 未启用，跳过"
        fi
    elif command -v firewall-cmd &>/dev/null; then
        if systemctl is-active --quiet firewalld 2>/dev/null; then
            firewall-cmd --permanent --add-port="${HOST_PORT}/tcp" 2>/dev/null
            firewall-cmd --reload 2>/dev/null
            success "Firewalld 已放行端口 ${HOST_PORT}"
        else
            info "Firewalld 未运行，跳过"
        fi
    elif command -v iptables &>/dev/null; then
        iptables -C INPUT -p tcp --dport "$HOST_PORT" -j ACCEPT 2>/dev/null \
            || iptables -A INPUT -p tcp --dport "$HOST_PORT" -j ACCEPT 2>/dev/null
        success "iptables 已放行端口 ${HOST_PORT}"
    else
        warn "未检测到防火墙工具，请手动放行端口 ${HOST_PORT}"
    fi
}

# -------------------- 显示部署信息 --------------------
show_info() {
    local ip
    ip=$(curl -s4 --connect-timeout 5 ifconfig.me 2>/dev/null \
        || curl -s4 --connect-timeout 5 ip.sb 2>/dev/null \
        || curl -s4 --connect-timeout 5 ipinfo.io/ip 2>/dev/null \
        || echo "<你的服务器IP>")

    echo ""
    echo "============================================================"
    echo -e "${GREEN}${BOLD}  shiso_stock_tracker 部署完成！${NC}"
    echo "============================================================"
    echo ""
    echo -e "  服务地址:   ${CYAN}http://${ip}:${HOST_PORT}${NC}"
    echo -e "  API 端点:   ${CYAN}http://${ip}:${HOST_PORT}/api${NC}"
    echo -e "  默认账号:   ${YELLOW}admin${NC} / ${YELLOW}admin123${NC}"
    echo ""
    echo "  项目目录:   ${PROJECT_DIR}"
    echo "  配置文件:   ${ENV_FILE}"
    echo "  数据目录:   ${PROJECT_DIR}/data"
    echo "  报告目录:   ${PROJECT_DIR}/reports"
    echo ""
    echo "  常用命令:"
    echo "    查看状态:   cd ${PROJECT_DIR} && docker compose ps"
    echo "    查看日志:   cd ${PROJECT_DIR} && docker compose logs -f"
    echo "    重启服务:   cd ${PROJECT_DIR} && docker compose restart"
    echo "    停止服务:   cd ${PROJECT_DIR} && docker compose down"
    echo "    更新服务:   cd ${PROJECT_DIR} && git pull && docker compose pull && docker compose up -d"
    echo ""
    echo "============================================================"
}

# -------------------- 主流程 --------------------
main() {
    parse_args "$@"

    echo ""
    echo -e "${CYAN}============================================================${NC}"
    echo -e "${CYAN}  shiso_stock_tracker 一键部署脚本 (幂等版)${NC}"
    echo -e "${CYAN}============================================================${NC}"
    echo ""

    info "配置: 端口=${HOST_PORT}, 目录=${PROJECT_DIR}, 分支=${GIT_BRANCH}"
    echo ""

    check_prerequisites
    check_os
    install_docker
    deploy
    setup_firewall
    show_info
}

main "$@"
