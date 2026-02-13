#!/bin/bash
#
# SieshKa-Site File Integrity Checker
# Verifies all required files exist and are valid
#

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Counters
ERRORS=0
WARNINGS=0

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[✓]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[⚠]${NC} $1"
    WARNINGS=$((WARNINGS+1))
}

log_error() {
    echo -e "${RED}[✗]${NC} $1"
    ERRORS=$((ERRORS+1))
}

# Check if file exists
check_file() {
    local file=$1
    local required=$2
    
    if [ -f "$file" ]; then
        log_success "File exists: $file"
        return 0
    else
        if [ "$required" == "true" ]; then
            log_error "Required file missing: $file"
        else
            log_warning "Optional file missing: $file"
        fi
        return 1
    fi
}

# Check if directory exists
check_dir() {
    local dir=$1
    local required=$2
    
    if [ -d "$dir" ]; then
        log_success "Directory exists: $dir"
        return 0
    else
        if [ "$required" == "true" ]; then
            log_error "Required directory missing: $dir"
        else
            log_warning "Optional directory missing: $dir"
        fi
        return 1
    fi
}

# Check file is not empty
check_not_empty() {
    local file=$1
    
    if [ -s "$file" ]; then
        local size=$(stat -f%z "$file" 2>/dev/null || stat -c%s "$file" 2>/dev/null || echo "0")
        log_success "File not empty: $file (${size} bytes)"
        return 0
    else
        log_error "File is empty: $file"
        return 1
    fi
}

# Check YAML syntax
check_yaml() {
    local file=$1
    
    if command -v python3 &> /dev/null; then
        if python3 -c "import yaml; yaml.safe_load(open('$file'))" 2>/dev/null; then
            log_success "Valid YAML: $file"
            return 0
        else
            log_error "Invalid YAML syntax: $file"
            return 1
        fi
    else
        log_warning "Cannot validate YAML (python3 not available): $file"
        return 0
    fi
}

# Check Python syntax
check_python() {
    local file=$1
    
    if python3 -m py_compile "$file" 2>/dev/null; then
        log_success "Valid Python: $file"
        return 0
    else
        log_error "Invalid Python syntax: $file"
        return 1
    fi
}

# Check shell script syntax
check_shell() {
    local file=$1
    
    if bash -n "$file" 2>/dev/null; then
        log_success "Valid Shell script: $file"
        return 0
    else
        log_error "Invalid Shell syntax: $file"
        return 1
    fi
}

# Main validation function
main() {
    echo "========================================"
    echo "  SieshKa-Site File Integrity Check"
    echo "========================================"
    echo ""
    
    log_info "Checking required configuration files..."
    echo ""
    
    # Configuration files
    check_file "docker-compose.yml" "true" && check_yaml "docker-compose.yml"
    check_file "Dockerfile" "true" && check_not_empty "Dockerfile"
    check_file "requirements.txt" "true" && check_not_empty "requirements.txt"
    check_file ".env.example" "true" && check_not_empty ".env.example"
    check_file "alembic.ini" "true" && check_not_empty "alembic.ini"
    check_file "Makefile" "false"
    check_file "README.md" "true" && check_not_empty "README.md"
    check_file "REPOSITORY_MANIFEST.json" "true" && check_not_empty "REPOSITORY_MANIFEST.json"
    
    echo ""
    log_info "Checking application files..."
    echo ""
    
    # Application files
    check_file "app/main.py" "true" && check_python "app/main.py"
    check_file "app/models.py" "true" && check_python "app/models.py"
    check_file "app/schemas.py" "true" && check_python "app/schemas.py"
    check_file "app/db.py" "true" && check_python "app/db.py"
    check_file "app/admin.py" "true" && check_python "app/admin.py"
    check_file "app/telegram.py" "true" && check_python "app/telegram.py"
    
    check_file "config/settings.py" "true" && check_python "config/settings.py"
    check_file "config/constants.py" "true" && check_python "config/constants.py"
    
    echo ""
    log_info "Checking migration files..."
    echo ""
    
    check_file "alembic/env.py" "true" && check_python "alembic/env.py"
    check_file "alembic/versions/0001_full_schema.py" "true" && check_python "alembic/versions/0001_full_schema.py"
    
    echo ""
    log_info "Checking frontend files..."
    echo ""
    
    check_file "app/templates/base.html" "true" && check_not_empty "app/templates/base.html"
    check_file "app/templates/index.html" "true" && check_not_empty "app/templates/index.html"
    check_file "app/templates/cart.html" "true" && check_not_empty "app/templates/cart.html"
    check_file "app/templates/checkout.html" "true" && check_not_empty "app/templates/checkout.html"
    check_file "app/templates/thanks.html" "true" && check_not_empty "app/templates/thanks.html"
    check_file "app/templates/closed.html" "true" && check_not_empty "app/templates/closed.html"
    check_file "app/static/app.js" "true" && check_not_empty "app/static/app.js"
    
    echo ""
    log_info "Checking infrastructure files..."
    echo ""
    
    check_file "nginx/default.conf" "true" && check_not_empty "nginx/default.conf"
    check_file "scripts/backup.sh" "true" && check_shell "scripts/backup.sh"
    check_file "deploy.sh" "false" && check_shell "deploy.sh"
    check_file "cleanup.sh" "false" && check_shell "cleanup.sh"
    
    echo ""
    log_info "Checking directory structure..."
    echo ""
    
    check_dir "app" "true"
    check_dir "app/templates" "true"
    check_dir "app/static" "true"
    check_dir "config" "true"
    check_dir "alembic" "true"
    check_dir "alembic/versions" "true"
    check_dir "nginx" "true"
    check_dir "scripts" "true"
    check_dir "backups" "false"
    check_dir "logs" "false"
    
    echo ""
    log_info "Checking ignore files..."
    echo ""
    
    check_file ".gitignore" "true" && check_not_empty ".gitignore"
    check_file ".dockerignore" "true" && check_not_empty ".dockerignore"
    
    echo ""
    log_info "Checking for unwanted files..."
    echo ""
    
    # Check for files that shouldn't be in production
    if [ -d ".git" ]; then
        log_warning "Git repository found (should be removed for production)"
    fi
    
    if [ -d "venv" ] || [ -d ".venv" ]; then
        log_warning "Virtual environment found (should be removed for production)"
    fi
    
    if find . -name "__pycache__" -type d 2>/dev/null | grep -q .; then
        log_warning "Python cache directories found (should be removed for production)"
    fi
    
    if [ -f ".env" ]; then
        log_warning ".env file found (ensure it contains production values)"
    fi
    
    # Summary
    echo ""
    echo "========================================"
    echo "  Integrity Check Summary"
    echo "========================================"
    echo ""
    
    if [ $ERRORS -eq 0 ] && [ $WARNINGS -eq 0 ]; then
        log_success "All checks passed! Project is ready for deployment."
        exit 0
    elif [ $ERRORS -eq 0 ]; then
        log_warning "All required files present, but $WARNINGS warning(s) found."
        log_info "Review warnings above before deploying to production."
        exit 0
    else
        log_error "Found $ERRORS error(s) and $WARNINGS warning(s)."
        log_error "Please fix errors before deploying."
        exit 1
    fi
}

# Run main function
main
