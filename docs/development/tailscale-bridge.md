# Reaching the Windows dev box from a sandboxed dev host

The Windows dev box ("hantal") runs its own full local Docker stack of Minder
and is reached over Tailscale for remote command execution
(`scripts/dev/hantal_ssh.py`). Some dev hosts — notably sandboxed
containers/VMs used for AI-assisted development — have no `/dev/net/tun` and
no `tun` kernel module available, since they don't own their own kernel. This
breaks Tailscale's normal networking mode, which needs a TUN device to create
its virtual `tailscale0` interface.

## Symptom

```
is CONFIG_TUN enabled in your kernel? `modprobe tun` failed with: modprobe:
FATAL: Module tun not found in directory /lib/modules/<kernel>
tun module not loaded nor found on disk
wgengine.NewUserspaceEngine(tun "tailscale0") error: tstun.New("tailscale0")
failed; /dev/net/tun does not exist
```

## Fix: userspace-networking mode + a SOCKS5 proxy

Tailscale has a fallback mode for exactly this: `--tun=userspace-networking`.
It skips the TUN interface entirely and instead exposes a SOCKS5/HTTP proxy
that other processes on the same host can use to reach tailnet peers — there's
no way to get real IP-level routing to tailnet addresses without a TUN device,
so anything that needs to talk to a peer (`ssh`, `curl`, etc.) has to be told
to go through that proxy explicitly.

`scripts/dev/tailscale_bootstrap.sh` automates the whole thing — install,
detect whether `/dev/net/tun` exists, configure the systemd override if not,
and report the login/status. Run it once per fresh sandbox:

```bash
bash scripts/dev/tailscale_bootstrap.sh
# then approve the printed login URL in a browser if it asks
```

Manually, the pieces are:

```bash
curl -fsSL https://tailscale.com/install.sh | sh
apt-get install -y socat   # SOCKS5-aware netcat replacement; plain nc doesn't support -x/-X

mkdir -p /etc/systemd/system/tailscaled.service.d
cat > /etc/systemd/system/tailscaled.service.d/override.conf <<'EOF'
[Service]
ExecStart=
ExecStart=/usr/sbin/tailscaled --state=/var/lib/tailscale/tailscaled.state --socket=/run/tailscale/tailscaled.sock --port=${PORT} --tun=userspace-networking --socks5-server=localhost:1055 --outbound-http-proxy-listen=localhost:1055
EOF
systemctl daemon-reload
systemctl restart tailscaled

tailscale up --hostname=$(hostname)-claude   # prints a login URL to approve
```

## Using the proxy

Any tool that supports a SOCKS5 proxy can now reach tailnet peers via
`localhost:1055`. For plain `ssh` (no native SOCKS5 support), route through
`socat` as the `ProxyCommand`:

```bash
ssh -o ProxyCommand="socat - SOCKS5:localhost:%h:%p,socksport=1055" \
    -i ~/.ssh/hantal_windows utkan.sevimli@outlook.com@100.123.71.54 'whoami'
```

Or add it once to `~/.ssh/config`:

```
Host hantal
    HostName 100.123.71.54
    User utkan.sevimli@outlook.com
    IdentityFile ~/.ssh/hantal_windows
    ProxyCommand socat - SOCKS5:localhost:%h:%p,socksport=1055
```

`scripts/dev/hantal_ssh.py` does the SOCKS5-via-`socat` step itself (as a
paramiko `ProxyCommand`) whenever `HANTAL_SOCKS5` is set in `scripts/dev/.env`
— see `scripts/dev/README.md`. Leave `HANTAL_SOCKS5` unset when running from a
host that's already a normal tailnet peer (a real `tailscale0` interface
exists) — direct TCP is used instead and no proxy is needed.

## SSH key auth on the Windows side (one-time, done on hantal itself)

Windows' OpenSSH Server needs enabling and a public key added:

```powershell
Add-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0
Start-Service sshd
Set-Service -Name sshd -StartupType Automatic
New-NetFirewallRule -Name sshd -DisplayName 'OpenSSH SSH Server' -Enabled True -Direction Inbound -Protocol TCP -Action Allow -LocalPort 22
```

If the account is an **administrator**, Windows' OpenSSH ignores the per-user
`authorized_keys` and requires the key in
`%ProgramData%\ssh\administrators_authorized_keys` instead, with locked-down
ACLs (only SYSTEM + Administrators) or `sshd` rejects it:

```powershell
Add-Content -Path "$env:ProgramData\ssh\administrators_authorized_keys" -Value "<public key>"
icacls.exe "$env:ProgramData\ssh\administrators_authorized_keys" /inheritance:r /grant "Administrators:F" /grant "SYSTEM:F"
```

A Windows Hello **PIN cannot be used for this** — it's bound to that device's
TPM for local interactive logon only. Network auth (SSH/WinRM/RDP) needs a
real account password or, as set up here, a key pair.
