#!/bin/bash
# Bootstrap Tailscale connectivity from a sandboxed dev host (container/VM with
# no /dev/net/tun) so scripts/dev/hantal_ssh.py can reach the Windows dev box.
# Idempotent — safe to re-run. See docs/development/tailscale-bridge.md for the
# full explanation of why userspace-networking + a SOCKS5 proxy are needed here.
#
# Usage: bash scripts/dev/tailscale_bootstrap.sh
# Requires root (installs packages, writes a systemd drop-in).

set -euo pipefail

SOCKS_PORT="${TAILSCALE_SOCKS_PORT:-1055}"

if ! command -v tailscale >/dev/null 2>&1; then
    echo "[bootstrap] installing tailscale..."
    curl -fsSL https://tailscale.com/install.sh | sh
fi

if ! command -v socat >/dev/null 2>&1; then
    echo "[bootstrap] installing socat..."
    apt-get install -y socat
fi

if [ ! -e /dev/net/tun ]; then
    echo "[bootstrap] /dev/net/tun not present — configuring userspace-networking mode"
    mkdir -p /etc/systemd/system/tailscaled.service.d
    cat > /etc/systemd/system/tailscaled.service.d/override.conf <<EOF
[Service]
ExecStart=
ExecStart=/usr/sbin/tailscaled --state=/var/lib/tailscale/tailscaled.state --socket=/run/tailscale/tailscaled.sock --port=\${PORT} --tun=userspace-networking --socks5-server=localhost:${SOCKS_PORT} --outbound-http-proxy-listen=localhost:${SOCKS_PORT}
EOF
    systemctl daemon-reload
else
    echo "[bootstrap] /dev/net/tun present — normal tailscaled mode, no override needed"
fi

systemctl enable --now tailscaled >/dev/null 2>&1 || systemctl restart tailscaled
sleep 2

if ! tailscale status >/dev/null 2>&1; then
    echo "[bootstrap] not logged in — run this and approve the URL in a browser:"
    echo "    tailscale up --hostname=\$(hostname)-claude"
    exit 0
fi

echo "[bootstrap] tailscale is up:"
tailscale status

if [ ! -e /dev/net/tun ]; then
    echo
    echo "[bootstrap] userspace-networking mode: set HANTAL_SOCKS5=localhost:${SOCKS_PORT}"
    echo "in scripts/dev/.env so hantal_ssh.py routes through the proxy above."
fi
