# Gate normalization — VALUE-ONLY masking.
# Principle: mask values that legitimately vary between runs (timestamps, health
# results, disk/GPU readings); PRESERVE structure (command set + order, step order,
# service groups, endpoints). If two runs differ only in masked values, the diff is
# empty. If the STRUCTURE changes, the diff shows it — that's the regression signal.
#
# Two machine-specific masks (hostname, absolute repo path) are injected at run time
# by run-gate.sh so this file stays portable across machines/checkouts.

# strip CR (CRLF -> LF) and ANSI color / OSC escapes
s/.*\r//
s/\x1b\[[0-9;?]*[A-Za-z]//g
s/\x1b\][^\x07]*\x07//g

# timestamps / log filenames / ISO dates
s/setup-[0-9]{8}-[0-9]{6}\.log/setup-TS.log/g
s/[0-9]{2}:[0-9]{2}:[0-9]{2}/HH:MM:SS/g
s/[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9:]+Z/DATE/g

# health-probe results (network/service state must not affect the trace)
s#http://[^ ]+#HEALTHRESULT#g
s#\(container not running\)#HEALTHRESULT#g
s#\(TCP port check\)#HEALTHRESULT#g
s#\(not yet reachable\)#HEALTHRESULT#g
# #3 health SUMMARY — collapse BOTH live-state branches to ONE canonical line:
#   success (log_success): "N/N endpoints healthy 🎉"
#   warn    (log_warn):    "M/N endpoints reachable — K still starting"
# Both go through _log (icon + ts prefix), but we replace the WHOLE line so the result
# is prefix/count/emoji-independent → byte-identical regardless of which branch fires.
# Structure is still preserved: the per-service SET is carried by the per-endpoint
# "MARK <name> HEALTHRESULT" lines below, and removing the summary entirely leaves no
# match here → the diff shows it.
/endpoints healthy/   s/.*/  MARK HEALTHSUMMARY/
/endpoints reachable/ s/.*/  MARK HEALTHSUMMARY/
# warn-only "Re-check: ./setup.sh status" hint (log_detail; present only when warn_count>0)
/Re-check: /d
# influxdb uses a raw bash >/dev/tcp probe (not shimmable, not DRY_RUN-gated), so its
# branch flaps with live host-port state: success emits url + "(TCP port check)" (two
# masked tokens), warn emits url + "(not yet reachable)" (two). Collapse repeated
# HEALTHRESULT so both branches normalize identically. SCOPED to the health-line shape
# (icon + service + HEALTHRESULT) so it can never merge two distinct services (always
# on separate lines) or any non-health structure.
/^ *[^ ]+ +[A-Za-z0-9_-]+ +HEALTHRESULT/ s/HEALTHRESULT([[:space:]]+HEALTHRESULT)+/HEALTHRESULT/g
/HEALTHRESULT/ s/^ *[^ ]+ +([A-Za-z0-9_-]+ +HEALTHRESULT)/  MARK \1/
# preflight busy-port advisory: a raw >/dev/tcp scan of host ports (preflight.sh) whose
# list is pure live-host state with no setup.sh command structure — drop it entirely.
/Ports already in use \(may conflict\)/d

# host resource readings
# #5 disk-space advisory — collapse BOTH live-state branches to ONE canonical line:
#   ok   (log_detail): "  Disk space: NGB free"            (2-space prefix, no icon/ts)
#   warn (log_warn):   "⚠ HH:MM:SS  Low disk space: NGB free (recommend ≥10GB)"
# `df` is live host state; the branches differ in message AND prefix, so replace the
# WHOLE line (matched case-insensitively on the shared "disk space: NGB free" anchor)
# to force byte-identical output. Line still present → a removed disk check shows as a diff.
/[Dd]isk space: [0-9]+GB free/ s/.*/  MARK DISKSPACE/
s/GPU Memory: [0-9]+ MiB/GPU Memory: N MiB/g
s/GPUs detected: [0-9]+/GPUs detected: N/g
