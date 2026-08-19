# ============================================================================
# Minder — daily automated backup wrapper for Windows dev hosts (hantal)
# ============================================================================
# Runs `python -m scripts.setup backup` and logs the result. Exists because
# hantal (the primary dev host, more resources than the Pi) had NO scheduled
# backup at all — confirmed live 2026-08-19: the newest backup on disk was
# from 2026-08-04, 15 days stale, while scripts/setup/backup.py itself (100%
# unit-tested, sabotage-tested) has worked correctly the whole time. Nothing
# was ever wired up to actually call it on a schedule.
#
# Register as a daily Windows Scheduled Task:
#   schtasks /Create /TN "MinderDailyBackup" /SC DAILY /ST 03:00 /F /TR ^
#     "powershell -NoProfile -ExecutionPolicy Bypass -File <repo>\scripts\dev\scheduled-backup.ps1"
#
# KNOWN LIMITATION: a plain `schtasks /Create` without /RU + /RP registers the
# task as "Logon Mode: Interactive only" — it will NOT run if the user isn't
# logged into an active session at the scheduled time (confirmed live via
# `schtasks /Query /TN MinderDailyBackup /FO LIST /V`). Making it run whether
# logged on or not needs either the user's real Windows password (`/RU <user>
# /RP <password>`, not something to embed in a script or type over SSH) or
# switching /RU to SYSTEM -- untested here, and risky: `python` on this host
# resolves through a per-user Windows Store execution alias
# (C:\Users\<user>\AppData\Local\Microsoft\WindowsApps\...), which SYSTEM may
# not have on PATH or permission to invoke at all. Left as interactive-only
# rather than risk silently breaking the task in an unverifiable way — still
# a large improvement over zero automated backups, on a host that's normally
# logged in. Revisit if hantal starts running headless/logged-out overnight.
#
# Logs to <repo>\logs\scheduled-backup.log (append-only, not rotated -- same
# as backup-test.sh's own log file on the Pi).

$repo = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$logDir = Join-Path $repo "logs"
if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir | Out-Null }
$logFile = Join-Path $logDir "scheduled-backup.log"
$timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"

Set-Location $repo
# Don't use $ErrorActionPreference = "Stop" here: tar (invoked by scripts.setup
# backup) writes a harmless informational line to stderr ("Removing leading
# '/' from member names"), and under "Stop" a native command's stderr output
# gets turned into a terminating error via `2>&1`, wrongly reporting a
# successful backup as failed (caught live while testing this very script).
# Use the real exit code instead.
$output = & python -m scripts.setup backup 2>&1 | Out-String
if ($LASTEXITCODE -eq 0) {
    Add-Content -Path $logFile -Value "[$timestamp] Backup OK:`r`n$output"
} else {
    Add-Content -Path $logFile -Value "[$timestamp] Backup FAILED (exit $LASTEXITCODE):`r`n$output"
}
