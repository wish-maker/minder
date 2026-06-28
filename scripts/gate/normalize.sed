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
s#[0-9]+/[0-9]+ endpoints healthy#N/N endpoints healthy#g
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
s/Disk space: [0-9]+GB free/Disk space: NNNGB free/g
s/GPU Memory: [0-9]+ MiB/GPU Memory: N MiB/g
s/GPUs detected: [0-9]+/GPUs detected: N/g
