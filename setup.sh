#!/bin/bash
set -e  # Exit on error

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
NC='\033[0m'

# Find latest Python 3 version
PYTHON_CMD=""
for cmd in python3.13 python3.12 python3.11 python3.10 python3.9 python3.8 python3.7 python3; do
    if command -v $cmd &> /dev/null; then
        PYTHON_CMD=$cmd
        break
    fi
done

if [ -z "$PYTHON_CMD" ]; then
    echo -e "${RED}Error: No Python 3.x installation found${NC}"
    exit 1
fi

echo -e "${GREEN}Using Python: $($PYTHON_CMD --version)${NC}"

# Check if uv is installed
if ! command -v uv &> /dev/null; then
    echo -e "${RED}Error: uv is not installed. Please install uv using: 'pip install uv' or 'curl -sSf https://astral.sh/uv/install.sh | bash'${NC}"
    exit 1
fi

# Modern uv workflow doesn't require manual venv creation
# uv sync will automatically create and manage the virtual environment
echo -e "${GREEN}uv will automatically manage virtual environment...${NC}"

# Note: uv sync creates .venv automatically, activation happens via 'uv run'
# For manual activation after setup:
if [[ "$OSTYPE" == "msys" || "$OSTYPE" == "cygwin" ]]; then
    ACTIVATE_CMD="source .venv/Scripts/activate"
else
    ACTIVATE_CMD="source .venv/bin/activate"
fi
echo -e "${GREEN}Virtual environment will be available at .venv${NC}"

# Install dependencies using modern uv sync  
echo -e "${GREEN}Installing dependencies from pyproject.toml...${NC}"
uv sync --extra dev

# Check for required commands
for cmd in tr openssl awk; do
    if ! command -v $cmd &> /dev/null; then
        echo -e "${RED}Error: $cmd is required but not installed.${NC}"
        exit 1
    fi
done

# Function to generate secure random string
generate_secure_string() {
    local length=$1
    if command -v openssl &> /dev/null; then
        openssl rand -base64 $length | tr -dc 'A-Za-z0-9@#$%^&*' | head -c $length
    else
        LC_ALL=C tr -dc 'A-Za-z0-9@#$%^&*' < /dev/urandom | head -c $length
    fi
}

# The env sample ships with the app template
ENV_SAMPLE=stk/scaffold/app/env-sample
if [ ! -f "$ENV_SAMPLE" ]; then
    echo -e "${RED}Error: $ENV_SAMPLE not found${NC}"
    exit 1
fi

# Check if .env already exists
if [ -f .env ]; then
    REPLY=n
    if [ -t 0 ]; then
        read -p "A .env file already exists. Do you want to overwrite it? (y/N) " -n 1 -r
        echo
    fi
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo -e "${YELLOW}Keeping the existing .env.${NC}"
        exit 1
    fi
    # Backup existing .env
    BACKUP_FILE=".env.backup.$(date +%Y%m%d_%H%M%S)"
    if ! cp .env "$BACKUP_FILE"; then
        echo -e "${RED}Error: Failed to create backup file${NC}"
        exit 1
    fi
    echo -e "${GREEN}Created backup of existing .env at $BACKUP_FILE${NC}"
fi

# Copy the sample file
if ! cp "$ENV_SAMPLE" .env; then
    echo -e "${RED}Error: Failed to copy $ENV_SAMPLE to .env${NC}"
    exit 1
fi

# Generate secure random values
SECRET_KEY=$(generate_secure_string 32)
PASSWORD_SALT=$(generate_secure_string 32)

# Validate generated values
if [ -z "$SECRET_KEY" ] || [ -z "$PASSWORD_SALT" ]; then
    echo -e "${RED}Error: Failed to generate secure values${NC}"
    exit 1
fi

# Process the .env file
if ! awk -v sk="$SECRET_KEY" -v ps="$PASSWORD_SALT" '
{
    if ($0 ~ /^SECRET_KEY=/) {
        print "SECRET_KEY=\"" sk "\""
    }
    else if ($0 ~ /^SECURITY_PASSWORD_SALT=/) {
        print "SECURITY_PASSWORD_SALT=\"" ps "\""
    }
    else if ($0 ~ /^SQLALCHEMY_DATABASE_URI=/) {
        # Skip - use default from settings.py (instance/stk.db)
        next
    }
    else {
        print $0
    }
}' .env > .env.new; then
    echo -e "${RED}Error: Failed to process .env file${NC}"
    exit 1
fi

if ! mv .env.new .env; then
    echo -e "${RED}Error: Failed to save .env file${NC}"
    rm -f .env.new
    exit 1
fi

# Verify the file was created
if [ ! -f .env ]; then
    echo -e "${RED}Error: .env file was not created${NC}"
    exit 1
fi

echo -e "${GREEN}Successfully generated .env file with secure keys${NC}"
echo -e "${GREEN}Generated secure values for: SECRET_KEY, SECURITY_PASSWORD_SALT${NC}"
echo -e "${GREEN}The bundled example app keeps its SQLite database in examples/minimal/instance/stk.db${NC}"
echo
echo -e "${GREEN}Next steps:${NC}"
echo -e "1. Update the remaining values in your .env file (mail settings, etc.)"
echo -e "2. Modern uv workflow - use these commands:"
echo -e "   ${GREEN}uv run stk create-db${NC}   # Initialize database"
echo -e "   ${GREEN}uv run stk install${NC}     # Create admin user"
echo -e "   ${GREEN}uv run stk run${NC}         # Start development server"
echo -e "   ${GREEN}uv run ruff check --fix .${NC} # Lint and auto-fix code"
echo -e "   ${GREEN}uv run ruff format .${NC}      # Format code"
echo -e "   ${GREEN}uv run pre-commit install${NC} # Install pre-commit hooks"
echo -e ""
echo -e "3. Or activate manually: ${GREEN}$ACTIVATE_CMD${NC}"
if [[ "$OSTYPE" == "msys" || "$OSTYPE" == "cygwin" ]]; then
    echo -e "${YELLOW}Note: On Windows, uWSGI is automatically excluded${NC}"
fi
if [ "$DOCKER_CONFIG" = true ]; then
    echo -e "4. For Docker: ${GREEN}docker compose up -d${NC}"
fi 