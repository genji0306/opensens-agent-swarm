#!/bin/bash
# DarkLab Connectivity Test
# Run from any device to verify network connectivity to the cluster
# Tests: DNS, TCP, HTTP, OpenClaw service, exec approvals, Paperclip

set -uo pipefail

DARKLAB_HOME="${DARKLAB_HOME:-${HOME}/.darklab}"
PASS=0
FAIL=0

pass() { echo "  [PASS] $1"; ((PASS++)); }
fail() { echo "  [FAIL] $1"; ((FAIL++)); }

echo "=== DarkLab Connectivity Test ==="
echo "Timestamp: $(date -u +"%Y-%m-%dT%H:%M:%SZ")"
echo "Device:    $(hostname)"
echo ""

# Detect role and Leader host
if [[ -f "${DARKLAB_HOME}/.env" ]]; then
    source "${DARKLAB_HOME}/.env"
fi
ROLE="${DARKLAB_ROLE:-unknown}"
LEADER_HOST="${DARKLAB_LEADER_HOST:-${DARKLAB_LEADER:-leader.local}}"
LEADER_PORT="${DARKLAB_LEADER_PORT:-18789}"
PAPERCLIP_PORT="${PAPERCLIP_PORT:-3100}"

echo "Role:      ${ROLE}"
echo "Leader:    ${LEADER_HOST}:${LEADER_PORT}"
echo ""

# Test 1: DNS Resolution
echo "--- Test 1: DNS Resolution ---"
if python3 -c "
import socket
try:
    ip = socket.gethostbyname('${LEADER_HOST}')
    print(f'  Resolved ${LEADER_HOST} -> {ip}')
except socket.gaierror as e:
    print(f'  DNS failed: {e}')
    exit(1)
" 2>/dev/null; then
    pass "DNS resolution of ${LEADER_HOST}"
else
    fail "DNS resolution of ${LEADER_HOST}"
fi

# Test 2: TCP Port Reachability
echo ""
echo "--- Test 2: TCP Port ${LEADER_PORT} ---"
if python3 -c "
import socket
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.settimeout(5)
try:
    s.connect(('${LEADER_HOST}', ${LEADER_PORT}))
    s.close()
except Exception as e:
    print(f'  TCP connect failed: {e}')
    exit(1)
" 2>/dev/null; then
    pass "TCP port ${LEADER_PORT} reachable on ${LEADER_HOST}"
else
    fail "TCP port ${LEADER_PORT} not reachable on ${LEADER_HOST}"
fi

# Test 3: HTTP Health Endpoint
echo ""
echo "--- Test 3: HTTP /health ---"
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "http://${LEADER_HOST}:${LEADER_PORT}/health" 2>/dev/null || echo "000")
if [[ "$HTTP_CODE" == "200" ]]; then
    pass "HTTP /health returned 200 at ${LEADER_HOST}:${LEADER_PORT}"
else
    fail "HTTP /health returned ${HTTP_CODE} at ${LEADER_HOST}:${LEADER_PORT}"
fi

# Test 4: OpenClaw Service Status
echo ""
echo "--- Test 4: OpenClaw Service ---"
if [[ "$ROLE" == "leader" ]]; then
    OC_STATUS=$(openclaw gateway status 2>/dev/null) || OC_STATUS=""
    if [[ -n "$OC_STATUS" ]]; then
        pass "OpenClaw gateway service responding"
    else
        fail "OpenClaw gateway service not responding"
    fi
elif [[ "$ROLE" == "academic" ]] || [[ "$ROLE" == "experiment" ]]; then
    OC_STATUS=$(openclaw node status 2>/dev/null) || OC_STATUS=""
    if [[ -n "$OC_STATUS" ]]; then
        pass "OpenClaw node service responding"
    else
        fail "OpenClaw node service not responding"
    fi
else
    # Boss or unknown — check gateway remotely
    if [[ "$HTTP_CODE" == "200" ]]; then
        pass "OpenClaw gateway reachable from this device"
    else
        fail "OpenClaw gateway not reachable from this device"
    fi
fi

# Test 5: Exec Approvals
echo ""
echo "--- Test 5: Exec Approvals ---"
EXEC_FILE="${HOME}/.openclaw/exec-approvals.json"
if [[ -f "$EXEC_FILE" ]]; then
    pass "exec-approvals.json exists at ${EXEC_FILE}"
else
    if [[ "$ROLE" == "boss" ]]; then
        pass "exec-approvals.json not needed for Boss role"
    else
        fail "exec-approvals.json missing (system.run commands will be denied)"
    fi
fi

# Test 6: Paperclip Dashboard
echo ""
echo "--- Test 6: Paperclip Dashboard ---"
PAPERCLIP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "http://${LEADER_HOST}:${PAPERCLIP_PORT}" 2>/dev/null || echo "000")
if [[ "$PAPERCLIP_CODE" == "200" ]] || [[ "$PAPERCLIP_CODE" == "302" ]]; then
    pass "Paperclip dashboard reachable at ${LEADER_HOST}:${PAPERCLIP_PORT}"
else
    fail "Paperclip dashboard not reachable at ${LEADER_HOST}:${PAPERCLIP_PORT} (HTTP ${PAPERCLIP_CODE})"
fi

# Summary
echo ""
echo "============================================"
echo "  CONNECTIVITY TEST SUMMARY"
echo "============================================"
echo "  PASS: ${PASS}"
echo "  FAIL: ${FAIL}"
echo ""

if [[ $FAIL -eq 0 ]]; then
    echo "  Status: ALL TESTS PASSED"
    exit 0
else
    echo "  Status: ${FAIL} TEST(S) FAILED"
    echo ""
    echo "  Troubleshooting:"
    echo "    - Ensure Leader gateway is running: openclaw gateway start"
    echo "    - Check firewall allows ports ${LEADER_PORT} and ${PAPERCLIP_PORT}"
    echo "    - Verify devices are on the same network"
    echo "    - Check Tailscale: tailscale status"
    exit 1
fi
