#!/bin/bash
set -e

# Refplatinator Installation Script
# This script downloads and sets up refplatinator for Cisco image extraction

echo "========================================="
echo "Refplatinator Installer"
echo "========================================="
echo ""

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored messages
print_success() {
    echo -e "${GREEN}✓${NC} $1"
}

print_error() {
    echo -e "${RED}✗${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}⚠${NC} $1"
}

print_info() {
    echo -e "  $1"
}

# Check if running as root (warn if so)
if [ "$EUID" -eq 0 ]; then
    print_warning "Running as root is not recommended"
    read -p "Continue anyway? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Check prerequisites
echo "Checking prerequisites..."
echo ""

MISSING_DEPS=0

# Check for Python 3
if command -v python3 &> /dev/null; then
    PYTHON_VERSION=$(python3 --version | cut -d' ' -f2)
    print_success "Python 3 found (version $PYTHON_VERSION)"
else
    print_error "Python 3 not found"
    MISSING_DEPS=1
fi

# Check for pip
if command -v pip3 &> /dev/null || command -v pip &> /dev/null; then
    print_success "pip found"
else
    print_error "pip not found"
    MISSING_DEPS=1
fi

# Check for Docker
if command -v docker &> /dev/null; then
    if docker info &> /dev/null; then
        print_success "Docker found and running"
    else
        print_warning "Docker found but not running or permission denied"
        print_info "You may need to start Docker or add your user to the docker group"
    fi
else
    print_error "Docker not found"
    MISSING_DEPS=1
fi

# Check for Git
if command -v git &> /dev/null; then
    print_success "Git found"
else
    print_error "Git not found"
    MISSING_DEPS=1
fi

echo ""

if [ $MISSING_DEPS -eq 1 ]; then
    print_error "Missing required dependencies. Please install them and try again."
    echo ""
    echo "Installation instructions:"
    echo "  - Python 3: https://www.python.org/downloads/"
    echo "  - Docker: https://docs.docker.com/get-docker/"
    echo "  - Git: https://git-scm.com/downloads"
    exit 1
fi

# Determine installation directory
INSTALL_DIR="${INSTALL_DIR:-$HOME/refplatinator}"

echo "Installation directory: $INSTALL_DIR"
echo ""

# Ask for confirmation
read -p "Proceed with installation? (Y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Nn]$ ]]; then
    echo "Installation cancelled."
    exit 0
fi

echo ""
echo "Installing refplatinator..."
echo ""

# Create installation directory if it doesn't exist
if [ ! -d "$INSTALL_DIR" ]; then
    mkdir -p "$INSTALL_DIR"
    print_success "Created installation directory: $INSTALL_DIR"
else
    print_warning "Directory already exists: $INSTALL_DIR"
    read -p "Continue and overwrite? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

cd "$INSTALL_DIR"

# Clone or update repository
if [ -d ".git" ]; then
    print_info "Updating existing repository..."
    git pull
else
    print_info "Downloading refplatinator..."
    # Check if directory is empty
    if [ "$(ls -A)" ]; then
        print_error "Directory is not empty and not a git repository"
        exit 1
    fi
    git clone https://github.com/torbbang/clab-refplatinator.git .
fi

print_success "Repository downloaded"

# Install Python dependencies
print_info "Installing Python dependencies..."
if command -v pip3 &> /dev/null; then
    pip3 install -r requirements.txt --user
else
    pip install -r requirements.txt --user
fi

print_success "Python dependencies installed"

# Create refplats directory
if [ ! -d "refplats" ]; then
    mkdir -p refplats
    print_success "Created refplats directory"
fi

# Make the script executable
chmod +x refplatinator.py 2>/dev/null || true

echo ""
echo "========================================="
print_success "Installation complete!"
echo "========================================="
echo ""
echo "Next steps:"
echo "  1. cd $INSTALL_DIR"
echo "  2. Place your Cisco refplat ZIP/ISO files in the 'refplats/' directory"
echo "  3. Run: python3 refplatinator.py"
echo ""
echo "For help: python3 refplatinator.py --help"
echo ""
