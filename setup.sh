#!/usr/bin/env bash
###############################################################################
# Minder Platform — Setup & Lifecycle Management (thin shim)
#
# Stage 2 (#7) is complete: the implementation is now native Python under
# scripts/setup/. This shim forwards every verb to `python -m scripts.setup`,
# so `bash setup.sh <verb>` keeps working exactly as documented while the logic
# runs cross-platform (Linux/macOS/Windows) with no bash dependency.
#
# The original bash implementation is preserved verbatim at setup.bash.sh and is
# used ONLY by the behavior gate (scripts/gate/) as the bash-parity reference that
# keeps the Python port honest — it is not part of the runtime path.
###############################################################################
set -euo pipefail

# Resolve the repo root (this script's dir) so `python -m scripts.setup` can import
# the `scripts` package regardless of the caller's working directory.
cd "$(dirname "$0")" || exit 1

for _py in python3 python; do
    if command -v "$_py" >/dev/null 2>&1; then
        exec "$_py" -m scripts.setup "$@"
    fi
done

echo "error: python3/python not found. Minder's setup is now native Python (#7) —" >&2
echo "       install Python 3 (the platform ships it on the Pi image)." >&2
exit 127
