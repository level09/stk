#!/bin/bash
set -e

VERSION="1.0.0"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color
BOLD='\033[1m'

# Utilities
log()   { echo -e "${BLUE}[$(date '+%H:%M:%S')]${NC} $1"; }
info()  { echo -e "${CYAN}ℹ${NC}  $1"; }
ok()    { echo -e "${GREEN}✓${NC}  $1"; }
warn()  { echo -e "${YELLOW}⚠${NC}  $1"; }
error() { echo -e "${RED}✗${NC}  $1" >&2; exit 1; }

step() {
    CURRENT_STEP=$((CURRENT_STEP + 1))
    echo -ne "${BOLD}[${CURRENT_STEP}/${TOTAL_STEPS}]${NC} $1..."
}

step_done() { echo -e " ${GREEN}✓${NC}"; }

# Header
header() {
    echo ""
    echo -e "${BOLD}⚡ stk deploy v${VERSION}${NC} - Production Install"
    echo "────────────────────────────────────────"
    echo ""
}

# Interactive setup
interactive_setup() {
    header

    read -r -p "? Domain name: " DOMAIN
    [ -z "$DOMAIN" ] && error "Domain is required"

    read -r -p "? Git repository [level09/stk]: " input
    REPO="${input:-level09/stk}"

    read -r -p "? Branch [master]: " input
    BRANCH="${input:-master}"

    read -r -p "? Database (sqlite/postgres) [sqlite]: " input
    DB="${input:-sqlite}"

    echo ""
    echo "────────────────────────────────────────"
    echo ""
}

# Validation
validate() {
    [ "$EUID" -eq 0 ] || error "Must run as root (use sudo)"
    [ -z "$DOMAIN" ] && error "DOMAIN is required"
    [ "$DB" = "sqlite" ] || [ "$DB" = "postgres" ] || error "DB must be sqlite or postgres"

    # Derive defaults
    APP_USER="${APP_USER:-${DOMAIN%%.*}}"
    # useradd rejects names starting with a digit (e.g. DOMAIN is an IP)
    [[ "$APP_USER" =~ ^[a-z_] ]] || APP_USER="stk"
    # admin@<IP> is invalid email syntax and the login form would reject it
    if [[ "$DOMAIN" =~ ^[0-9.]+$ ]]; then
        ADMIN_EMAIL="${ADMIN_EMAIL:-admin@example.com}"
    else
        ADMIN_EMAIL="${ADMIN_EMAIL:-admin@${DOMAIN}}"
    fi
    ADMIN_PASSWORD="${ADMIN_PASSWORD:-$(openssl rand -base64 16)}"
    PYTHON_PORT="${PYTHON_PORT:-5000}"

    APP_DIR="/home/${APP_USER}/${DOMAIN}"
    GIT_URL="https://github.com/${REPO}.git"

    TOTAL_STEPS=14
    if [ "$DB" = "postgres" ]; then TOTAL_STEPS=15; fi
}

# Install system packages
install_packages() {
    step "Installing system packages"
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -qq >/dev/null
    apt-get install -y -qq git curl wget >/dev/null 2>&1
    step_done
}

# Install Caddy
install_caddy() {
    step "Installing Caddy"
    if ! command -v caddy &>/dev/null; then
        apt-get install -y -qq debian-keyring debian-archive-keyring apt-transport-https >/dev/null 2>&1
        curl -sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg 2>/dev/null
        curl -sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | tee /etc/apt/sources.list.d/caddy-stable.list >/dev/null
        chmod o+r /usr/share/keyrings/caddy-stable-archive-keyring.gpg
        chmod o+r /etc/apt/sources.list.d/caddy-stable.list
        apt-get update -qq >/dev/null && apt-get install -y -qq caddy >/dev/null 2>&1
    fi
    step_done
}

# Install PostgreSQL + Redis (full mode only)
install_postgres() {
    if [ "$DB" = "postgres" ]; then
        step "Installing PostgreSQL + Redis"
        apt-get install -y -qq postgresql postgresql-contrib redis-server >/dev/null 2>&1
        systemctl enable --now postgresql >/dev/null 2>&1
        systemctl enable --now redis-server >/dev/null 2>&1

        DB_PASSWORD=$(openssl rand -hex 16)
        sudo -u postgres createuser "$APP_USER" 2>/dev/null || true
        sudo -u postgres createdb "$APP_USER" -O "$APP_USER" 2>/dev/null || true
        sudo -u postgres psql -qc "ALTER USER \"${APP_USER}\" WITH PASSWORD '${DB_PASSWORD}';" >/dev/null
        step_done
    fi
}

# Create application user
create_user() {
    step "Creating user '${APP_USER}'"
    if ! id "$APP_USER" &>/dev/null; then
        getent group "$APP_USER" >/dev/null || groupadd "$APP_USER"
        useradd -m -s /bin/bash -g "$APP_USER" "$APP_USER"
    fi
    # Add caddy to app user's group so it can serve static files
    usermod -aG "$APP_USER" caddy 2>/dev/null || true
    step_done
}

# Setup SSH access for app user
setup_ssh() {
    step "Setting up SSH access"
    local user_ssh="/home/${APP_USER}/.ssh"
    mkdir -p "$user_ssh"

    # Copy root's authorized keys if they exist
    if [ -f /root/.ssh/authorized_keys ]; then
        cp /root/.ssh/authorized_keys "$user_ssh/"
    fi

    chown -R "${APP_USER}:${APP_USER}" "$user_ssh"
    chmod 700 "$user_ssh"
    chmod 600 "$user_ssh/authorized_keys" 2>/dev/null || true

    # Sudoers: only allow managing the app service
    echo "${APP_USER} ALL=(ALL) NOPASSWD: /bin/systemctl start ${DOMAIN}.service, /bin/systemctl stop ${DOMAIN}.service, /bin/systemctl restart ${DOMAIN}.service, /bin/systemctl status ${DOMAIN}.service" > "/etc/sudoers.d/${APP_USER}"
    chmod 440 "/etc/sudoers.d/${APP_USER}"

    # Allow app user to read logs without sudo
    usermod -aG systemd-journal "$APP_USER" 2>/dev/null || true
    step_done
}

# Clone repository
clone_repo() {
    step "Cloning repository"
    if [ -d "$APP_DIR" ]; then
        rm -rf "$APP_DIR"
    fi
    sudo -u "$APP_USER" git clone -q --branch "$BRANCH" "$GIT_URL" "$APP_DIR"
    step_done
}

# Install uv + Python 3.13 + dependencies (uv downloads its own CPython)
setup_python() {
    step "Setting up Python 3.13 + uv"

    if [ ! -f /usr/local/bin/uv ]; then
        curl -LsSf https://astral.sh/uv/install.sh | sh >/dev/null 2>&1
        cp ~/.local/bin/uv /usr/local/bin/ 2>/dev/null || cp ~/.cargo/bin/uv /usr/local/bin/ 2>/dev/null || true
        chmod 755 /usr/local/bin/uv
    fi

    local extras=""
    [ "$DB" = "postgres" ] && extras="--extra full"
    # shellcheck disable=SC2086
    sudo -u "$APP_USER" bash -c "cd $APP_DIR && /usr/local/bin/uv sync --frozen --no-dev --python 3.13 $extras" >/dev/null 2>&1
    step_done
}

# Generate .env file
generate_env() {
    step "Generating .env file"

    local cookie_secure="True"
    [ "$SKIP_SSL" = "true" ] && cookie_secure="False"

    cat > "${APP_DIR}/.env" << EOF
QUART_APP=run.py
SECRET_KEY=$(openssl rand -hex 32)
SECURITY_PASSWORD_SALT=$(openssl rand -hex 32)
SESSION_COOKIE_SECURE=${cookie_secure}
SECURITY_REGISTERABLE=${SECURITY_REGISTERABLE:-False}

# Qarina research providers
OPENROUTER_API_KEY=${OPENROUTER_API_KEY:-}
SERPER_API_KEY=${SERPER_API_KEY:-}
MODEL=${MODEL:-google/gemini-3.1-flash-lite}
KNOWLEDGE_MODEL=${KNOWLEDGE_MODEL:-deepseek/deepseek-chat}
EMBEDDING_MODEL=${EMBEDDING_MODEL:-openai/text-embedding-3-small}
EMBEDDING_DIM=${EMBEDDING_DIM:-1536}
QUARINA_MAX_CONCURRENT_RUNS=${QUARINA_MAX_CONCURRENT_RUNS:-2}
EOF

    if [ "$DB" = "postgres" ]; then
        cat >> "${APP_DIR}/.env" << EOF
SQLALCHEMY_DATABASE_URI=postgresql+asyncpg://${APP_USER}:${DB_PASSWORD}@127.0.0.1:5432/${APP_USER}
REDIS_URL=redis://localhost:6379/1
EOF
    fi

    chown "$APP_USER:$APP_USER" "${APP_DIR}/.env"
    chmod 600 "${APP_DIR}/.env"
    step_done
}

# Initialize database (Alembic migrations to head)
init_database() {
    step "Initializing database"
    sudo -u "$APP_USER" bash -c "cd $APP_DIR && export QUART_APP=run.py && /usr/local/bin/uv run --no-sync quart create-db" >/dev/null 2>&1
    step_done
}

# Create admin user
create_admin() {
    step "Creating admin user"
    sudo -u "$APP_USER" bash -c "cd $APP_DIR && export QUART_APP=run.py && /usr/local/bin/uv run --no-sync quart install -e '${ADMIN_EMAIL}' -p '${ADMIN_PASSWORD}'" >/dev/null 2>&1

    # Save credentials
    cat > "/home/${APP_USER}/.credentials" << EOF
stk Deployment Credentials
─────────────────────────────
Domain: ${DOMAIN}
Admin Email: ${ADMIN_EMAIL}
Admin Password: ${ADMIN_PASSWORD}
─────────────────────────────
EOF
    chown "$APP_USER:$APP_USER" "/home/${APP_USER}/.credentials"
    chmod 600 "/home/${APP_USER}/.credentials"
    step_done
}

# Create systemd service
create_systemd_service() {
    step "Creating systemd service"

    local after="network.target"
    [ "$DB" = "postgres" ] && after="network.target postgresql.service redis-server.service"

    cat > "/etc/systemd/system/${DOMAIN}.service" << EOF
[Unit]
Description=stk App - ${DOMAIN}
After=${after}

[Service]
User=${APP_USER}
Group=${APP_USER}
WorkingDirectory=${APP_DIR}
EnvironmentFile=${APP_DIR}/.env
ExecStart=${APP_DIR}/.venv/bin/uvicorn run:app --host 127.0.0.1 --port ${PYTHON_PORT}
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

    systemctl daemon-reload
    step_done
}

# Configure Caddy
configure_caddy() {
    step "Configuring Caddy"

    local site="${DOMAIN}"
    local hsts='Strict-Transport-Security "max-age=31536000; includeSubDomains; preload"'
    if [ "$SKIP_SSL" = "true" ] || [ "$DOMAIN" = "localhost" ]; then
        site=":80"
        hsts=""
    fi

    cat > /etc/caddy/Caddyfile << EOF
${site} {
    # Compression
    encode zstd gzip

    # Security headers
    header {
        ${hsts}
        X-Content-Type-Options "nosniff"
        X-Frame-Options "SAMEORIGIN"
        Referrer-Policy "strict-origin-when-cross-origin"
        Permissions-Policy "geolocation=(), microphone=(), camera=()"
        -Server
    }

    # Static files with caching
    handle_path /static/* {
        root * ${APP_DIR}/stk/static
        file_server
        header Cache-Control "public, max-age=31536000, immutable"
    }

    # App
    reverse_proxy 127.0.0.1:${PYTHON_PORT} {
        header_up X-Real-IP {remote_host}
        header_up X-Forwarded-Proto {scheme}
    }

    # Logging
    log {
        output file /var/log/caddy/${DOMAIN}.log {
            roll_size 10mb
            roll_keep 5
        }
        format json
    }
}
EOF

    # Create log directory
    mkdir -p /var/log/caddy
    chown caddy:caddy /var/log/caddy

    step_done
}

# Harden SSH
harden_ssh() {
    step "Hardening SSH"

    # Key-only authentication
    sed -i 's/^#\?PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config
    sed -i 's/^#\?ChallengeResponseAuthentication.*/ChallengeResponseAuthentication no/' /etc/ssh/sshd_config
    systemctl restart ssh >/dev/null 2>&1

    # Brute-force protection
    apt-get install -y -qq fail2ban >/dev/null 2>&1
    systemctl enable --now fail2ban >/dev/null 2>&1
    step_done
}

# Setup firewall
setup_firewall() {
    step "Configuring firewall"
    if command -v ufw &>/dev/null; then
        ufw --force enable >/dev/null 2>&1
        ufw allow 22/tcp >/dev/null 2>&1
        ufw allow 80/tcp >/dev/null 2>&1
        ufw allow 443/tcp >/dev/null 2>&1
    fi
    step_done
}

# Start all services
start_services() {
    step "Starting services"
    systemctl enable --now "${DOMAIN}.service" >/dev/null 2>&1
    systemctl enable --now caddy >/dev/null 2>&1
    systemctl restart caddy >/dev/null 2>&1
    step_done
}

# Success message
success_message() {
    local url
    if [ "$SKIP_SSL" = "true" ] || [ "$DOMAIN" = "localhost" ]; then
        url="http://${DOMAIN}"
    else
        url="https://${DOMAIN}"
    fi

    echo ""
    echo "────────────────────────────────────────"
    echo -e "${GREEN}${BOLD}🚀 Deployed!${NC} ${url}"
    echo ""
    echo -e "   ${BOLD}SSH:${NC} ssh ${APP_USER}@${DOMAIN}"
    echo -e "   ${BOLD}Email:${NC} ${ADMIN_EMAIL}"
    echo -e "   ${BOLD}Password:${NC} (saved to /home/${APP_USER}/.credentials)"
    echo "────────────────────────────────────────"
    echo ""
}

# Main
main() {
    CURRENT_STEP=0
    REPO="${REPO:-level09/stk}"
    BRANCH="${BRANCH:-master}"
    DB="${DB:-sqlite}"
    SKIP_SSL="${SKIP_SSL:-false}"

    # Check if interactive mode (no DOMAIN set)
    if [ -z "$DOMAIN" ]; then
        # Can't do interactive if stdin is not a terminal (e.g., curl | bash)
        if [ ! -t 0 ]; then
            echo -e "${RED}Error:${NC} DOMAIN is required when running non-interactively"
            echo ""
            echo "Usage: wget -qO /tmp/deploy.sh https://raw.githubusercontent.com/level09/stk/master/deploy.sh && sudo DOMAIN=example.com bash /tmp/deploy.sh"
            exit 1
        fi
        interactive_setup
    else
        header
    fi

    validate

    install_packages
    install_caddy
    install_postgres
    create_user
    setup_ssh
    clone_repo
    setup_python
    generate_env
    init_database
    create_admin
    create_systemd_service
    configure_caddy
    harden_ssh
    setup_firewall
    start_services

    success_message
}

main "$@"
