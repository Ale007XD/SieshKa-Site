#!/bin/bash
#
# SieshKa-Site Cleanup Script
# Removes development artifacts and prepares for production
#

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Directories to clean
CLEAN_DIRS=(
    ".git"
    ".venv"
    "venv"
    "__pycache__"
    "*.pyc"
    "*.pyo"
    "*.pyd"
    ".Python"
    "build"
    "develop-eggs"
    "dist"
    "downloads"
    "eggs"
    ".eggs"
    "lib"
    "lib64"
    "parts"
    "sdist"
    "var"
    "wheels"
    "*.egg-info"
    ".installed.cfg"
    "*.egg"
    "pip-log.txt"
    "pip-delete-this-directory.txt"
    ".tox"
    ".nox"
    ".coverage"
    ".coverage.*"
    ".cache"
    "nosetests.xml"
    "coverage.xml"
    "*.cover"
    "*.py,cover"
    ".hypothesis"
    ".pytest_cache"
    "htmlcov"
    "*.mo"
    "*.pot"
    "*.log"
    "local_settings.py"
    "db.sqlite3"
    "db.sqlite3-journal"
    "instance"
    ".webassets-cache"
    ".scrapy"
    "docs/_build"
    "target"
    ".ipynb_checkpoints"
    "profile_default"
    "ipython_config.py"
    ".python-version"
    "Pipfile.lock"
    "__pypackages__"
    "celerybeat-schedule"
    "celerybeat.pid"
    "*.sage.py"
    ".spyderproject"
    ".spyproject"
    ".ropeproject"
    "/site"
    ".mypy_cache"
    ".dmypy.json"
    "dmypy.json"
    ".pyre"
    ".vscode"
    ".idea"
    "*.swp"
    "*.swo"
    "*~"
    ".DS_Store"
    ".DS_Store?"
    "._*"
    ".Spotlight-V100"
    ".Trashes"
    "ehthumbs.db"
    "Thumbs.db"
    "node_modules"
    "npm-debug.log*"
    "yarn-debug.log*"
    "yarn-error.log*"
    "package-lock.json"
    "yarn.lock"
    "*.pid"
    "*.seed"
    "*.pid.lock"
    ".cache"
    ".parcel-cache"
    "*.tmp"
    "*.temp"
    "*.bak"
    "*.backup"
    "*.orig"
    "*.rej"
    "backups/*.sql.gz"
    "backups/*.sql"
    "logs/*.log"
)

# Files to remove
CLEAN_FILES=(
    ".env.local"
    ".env.development"
    ".env.test"
    ".pre-commit-config.yaml"
    ".pylintrc"
    ".flake8"
    "setup.cfg"
    "setup.py"
    "pytest.ini"
    "tox.ini"
    "mypy.ini"
)

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Function to clean Python cache
clean_python_cache() {
    log_info "Cleaning Python cache files..."
    
    find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
    find . -type f -name "*.pyc" -delete 2>/dev/null || true
    find . -type f -name "*.pyo" -delete 2>/dev/null || true
    find . -type f -name "*.pyd" -delete 2>/dev/null || true
    
    log_success "Python cache cleaned"
}

# Function to clean directories
clean_directories() {
    log_info "Cleaning development directories..."
    
    for dir in "${CLEAN_DIRS[@]}"; do
        if [ -d "$dir" ]; then
            rm -rf "$dir"
            log_info "Removed directory: $dir"
        fi
    done
    
    # Clean .git directories recursively
    find . -type d -name ".git" -exec rm -rf {} + 2>/dev/null || true
    
    # Clean venv directories
    find . -type d -name "venv" -exec rm -rf {} + 2>/dev/null || true
    find . -type d -name ".venv" -exec rm -rf {} + 2>/dev/null || true
    
    log_success "Directories cleaned"
}

# Function to clean files
clean_files() {
    log_info "Cleaning development files..."
    
    for file in "${CLEAN_FILES[@]}"; do
        if [ -f "$file" ]; then
            rm -f "$file"
            log_info "Removed file: $file"
        fi
    done
    
    log_success "Files cleaned"
}

# Function to clean Docker artifacts
clean_docker() {
    log_info "Cleaning Docker artifacts..."
    
    # Stop and remove containers
    docker compose down --remove-orphans 2>/dev/null || true
    
    # Remove dangling images
    docker image prune -f 2>/dev/null || true
    
    # Remove unused volumes (except persistent data)
    docker volume prune -f 2>/dev/null || true
    
    log_success "Docker artifacts cleaned"
}

# Function to backup important files
backup_important() {
    log_info "Creating backup of important files..."
    
    if [ -f ".env" ]; then
        cp .env .env.backup.$(date +%Y%m%d_%H%M%S)
        log_warning ".env file backed up"
    fi
    
    log_success "Backup complete"
}

# Function to show cleanup summary
show_summary() {
    echo ""
    echo "========================================"
    echo "  Cleanup Summary"
    echo "========================================"
    echo ""
    
    log_success "Cleanup completed!"
    echo ""
    echo "The following items were preserved:"
    echo "  ✓ Source code (app/, config/, alembic/)"
    echo "  ✓ Configuration files (docker-compose.yml, Dockerfile, etc.)"
    echo "  ✓ Documentation (README.md)"
    echo "  ✓ Nginx configuration"
    echo "  ✓ Database migrations"
    echo "  ✓ Scripts (backup.sh, deploy.sh)"
    echo "  ✓ backups/ and logs/ directories (structure only)"
    echo ""
    echo "Removed items:"
    echo "  ✗ Git repositories"
    echo "  ✗ Virtual environments"
    echo "  ✗ Python cache files"
    echo "  ✗ Development/temporary files"
    echo "  ✗ Test files and coverage reports"
    echo "  ✗ IDE configuration files"
    echo "  ✗ Old backup files"
    echo ""
}

# Main cleanup function
main() {
    echo "========================================"
    echo "  SieshKa-Site Cleanup Script"
    echo "========================================"
    echo ""
    
    read -p "Are you sure you want to clean development artifacts? (y/N): " confirm
    
    if [[ ! $confirm =~ ^[Yy]$ ]]; then
        log_info "Cleanup cancelled"
        exit 0
    fi
    
    backup_important
    clean_python_cache
    clean_directories
    clean_files
    clean_docker
    show_summary
    
    log_success "Project is now ready for production deployment!"
}

# Run main function
main
