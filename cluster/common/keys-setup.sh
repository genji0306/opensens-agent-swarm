#!/bin/bash
# Generate Ed25519 signing keys for secure inter-device communication

KEYS_DIR="${DARKLAB_HOME}/keys"
mkdir -p "$KEYS_DIR"

echo "[keys] Setting up Ed25519 signing keys..."

if [[ -f "${KEYS_DIR}/signing.key" ]]; then
    echo "[keys] Signing key already exists at ${KEYS_DIR}/signing.key"
    read -p "Regenerate keys? (existing key will be backed up) [y/N]: " regen
    if [[ "$regen" =~ ^[Yy]$ ]]; then
        cp "${KEYS_DIR}/signing.key" "${KEYS_DIR}/signing.key.bak.$(date +%s)"
        cp "${KEYS_DIR}/signing.pub" "${KEYS_DIR}/signing.pub.bak.$(date +%s)" 2>/dev/null || true
    else
        echo "[keys] Keeping existing keys."
        return 0
    fi
fi

echo "[keys] Generating Ed25519 keypair..."
python3 -c "
from nacl.signing import SigningKey
import os

key = SigningKey.generate()
keys_dir = os.path.expanduser('${KEYS_DIR}')

with open(os.path.join(keys_dir, 'signing.key'), 'wb') as f:
    f.write(key.encode())

with open(os.path.join(keys_dir, 'signing.pub'), 'wb') as f:
    f.write(key.verify_key.encode())

print('[keys] Ed25519 keypair generated successfully.')
print(f'[keys] Private key: {keys_dir}/signing.key')
print(f'[keys] Public key:  {keys_dir}/signing.pub')
" 2>/dev/null || {
    echo "[keys] PyNaCl not yet installed. Keys will be generated after Python setup."
    echo "[keys] Run: python3 -c \"from nacl.signing import SigningKey; k=SigningKey.generate(); open('${KEYS_DIR}/signing.key','wb').write(k.encode()); open('${KEYS_DIR}/signing.pub','wb').write(k.verify_key.encode())\""
}

# Set restrictive permissions
chmod 600 "${KEYS_DIR}/signing.key" 2>/dev/null || true
chmod 644 "${KEYS_DIR}/signing.pub" 2>/dev/null || true
