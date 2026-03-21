#!/bin/bash
# Configure Chrome profiles for browser automation

ROLE="${1:-none}"

echo "[browser] Setting up browser profiles for role: ${ROLE}..."

# Check for Chrome
if [[ -d "/Applications/Google Chrome.app" ]]; then
    echo "[browser] Google Chrome: OK"
elif [[ -d "/Applications/Chromium.app" ]]; then
    echo "[browser] Chromium: OK"
else
    echo "[browser] No Chrome/Chromium found."
    read -p "Install Google Chrome? [y/N]: " install_chrome
    if [[ "$install_chrome" =~ ^[Yy]$ ]]; then
        brew install --cask google-chrome
    else
        echo "[browser] WARNING: Browser automation skills will not work without Chrome."
    fi
fi

# Create profile directories
PROFILES_DIR="${DARKLAB_HOME}/browser-profiles"
mkdir -p "$PROFILES_DIR"

case $ROLE in
    leader)
        echo "[browser] Creating NotebookLM profile..."
        mkdir -p "${PROFILES_DIR}/notebooklm-research"
        echo ""
        echo "IMPORTANT: To set up NotebookLM browser automation:"
        echo "  1. Open Chrome with this profile:"
        echo "     /Applications/Google\\ Chrome.app/Contents/MacOS/Google\\ Chrome --user-data-dir=${PROFILES_DIR}/notebooklm-research"
        echo "  2. Sign into your Google account"
        echo "  3. Navigate to notebooklm.google.com and verify access"
        echo "  4. Close Chrome (the profile will be saved)"
        echo ""
        ;;
    academic)
        echo "[browser] Creating Perplexity profile..."
        mkdir -p "${PROFILES_DIR}/perplexity-research"
        echo "[browser] Creating Google Research profile..."
        mkdir -p "${PROFILES_DIR}/google-research"
        echo ""
        echo "IMPORTANT: To set up browser automation profiles:"
        echo ""
        echo "  Perplexity:"
        echo "  1. Open Chrome: /Applications/Google\\ Chrome.app/Contents/MacOS/Google\\ Chrome --user-data-dir=${PROFILES_DIR}/perplexity-research"
        echo "  2. Sign into Perplexity Pro"
        echo "  3. Close Chrome"
        echo ""
        echo "  Google Research:"
        echo "  1. Open Chrome: /Applications/Google\\ Chrome.app/Contents/MacOS/Google\\ Chrome --user-data-dir=${PROFILES_DIR}/google-research"
        echo "  2. Sign into Google account (for Scholar, etc.)"
        echo "  3. Close Chrome"
        echo ""
        ;;
    *)
        echo "[browser] No browser profiles needed for this role."
        ;;
esac

echo "[browser] Browser setup complete."
