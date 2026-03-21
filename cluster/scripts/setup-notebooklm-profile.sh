#!/bin/bash
# Interactive helper for setting up the NotebookLM Chrome profile.
# Run on the Leader device AFTER install.sh completes.
#
# This script:
#   1. Verifies Chrome is installed
#   2. Creates the profile directory if needed
#   3. Launches Chrome with the correct user-data-dir
#   4. Waits for the user to sign in and verify NotebookLM access
#   5. Validates the profile has session cookies

set -uo pipefail

DARKLAB_HOME="${DARKLAB_HOME:-${HOME}/.darklab}"
PROFILES_DIR="${DARKLAB_HOME}/browser-profiles"
PROFILE_NAME="notebooklm-research"
PROFILE_DIR="${PROFILES_DIR}/${PROFILE_NAME}"

echo "=== DarkLab NotebookLM Profile Setup ==="
echo ""

# Step 1: Find Chrome
CHROME_BIN=""
if [[ -d "/Applications/Google Chrome.app" ]]; then
    CHROME_BIN="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
elif [[ -d "/Applications/Chromium.app" ]]; then
    CHROME_BIN="/Applications/Chromium.app/Contents/MacOS/Chromium"
else
    echo "ERROR: Google Chrome not found."
    echo "Install it with: brew install --cask google-chrome"
    exit 1
fi
echo "Chrome: ${CHROME_BIN}"

# Step 2: Check Playwright is installed (used by browser-use)
if command -v playwright &>/dev/null; then
    echo "Playwright: OK"
elif [[ -f "${DARKLAB_HOME}/.venv/bin/playwright" ]]; then
    echo "Playwright: OK (in venv)"
else
    echo ""
    echo "WARNING: Playwright not found. browser-use requires it."
    echo "Install with: ${DARKLAB_HOME}/.venv/bin/python -m playwright install chromium"
fi

# Step 3: Create profile directory
mkdir -p "${PROFILE_DIR}"
echo "Profile dir: ${PROFILE_DIR}"
echo ""

# Step 4: Check if profile already has session data
if [[ -f "${PROFILE_DIR}/Default/Cookies" ]] || [[ -f "${PROFILE_DIR}/Default/Login Data" ]]; then
    echo "Existing profile detected with session data."
    read -p "Re-authenticate? This will open Chrome. [y/N]: " redo
    if [[ ! "$redo" =~ ^[Yy]$ ]]; then
        echo ""
        echo "Profile already set up. To verify, run:"
        echo "  \"${CHROME_BIN}\" --user-data-dir=\"${PROFILE_DIR}\" https://notebooklm.google.com"
        echo ""
        exit 0
    fi
fi

echo "--- Instructions ---"
echo ""
echo "Chrome will open with a dedicated profile for NotebookLM."
echo "Please complete these steps:"
echo ""
echo "  1. Sign into your Google account"
echo "  2. Navigate to notebooklm.google.com (it should open automatically)"
echo "  3. Verify you can see the NotebookLM interface"
echo "  4. Create a test notebook to confirm write access"
echo "  5. Close Chrome when done"
echo ""
read -p "Press ENTER to launch Chrome..."

# Step 5: Launch Chrome with the profile
"${CHROME_BIN}" \
    --user-data-dir="${PROFILE_DIR}" \
    --no-first-run \
    --no-default-browser-check \
    "https://notebooklm.google.com" &
CHROME_PID=$!

echo ""
echo "Chrome launched (PID: ${CHROME_PID})"
echo "Waiting for you to sign in and close Chrome..."
echo ""

# Wait for Chrome to exit
wait $CHROME_PID 2>/dev/null

# Step 6: Validate profile was created
echo ""
echo "--- Validating Profile ---"

PASS=true

if [[ -d "${PROFILE_DIR}/Default" ]]; then
    echo "  PASS: Default profile directory created"
else
    echo "  FAIL: No Default profile directory — Chrome may not have saved the session"
    PASS=false
fi

if [[ -f "${PROFILE_DIR}/Default/Cookies" ]]; then
    echo "  PASS: Cookies database exists"
else
    echo "  WARN: No cookies file — session may not persist"
fi

if [[ -f "${PROFILE_DIR}/Default/Login Data" ]]; then
    echo "  PASS: Login data exists"
else
    echo "  WARN: No login data — Google account may not be signed in"
fi

# Check profile size as a sanity check (should be > 1MB after login)
PROFILE_SIZE=$(du -sm "${PROFILE_DIR}" 2>/dev/null | cut -f1)
if [[ "${PROFILE_SIZE:-0}" -gt 1 ]]; then
    echo "  PASS: Profile size ${PROFILE_SIZE}MB (looks reasonable)"
else
    echo "  WARN: Profile size ${PROFILE_SIZE:-0}MB (may be too small — did you sign in?)"
fi

echo ""
if $PASS; then
    echo "=== NotebookLM Profile Setup Complete ==="
    echo ""
    echo "The notebooklm agent can now automate NotebookLM via browser-use."
    echo "Profile: ${PROFILE_DIR}"
else
    echo "=== Setup may be incomplete ==="
    echo "Try running this script again and ensure you sign into Google."
fi
echo ""
