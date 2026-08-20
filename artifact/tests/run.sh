#!/usr/bin/env bash
# All tests that do not need a container runtime.
#
# The Dockerfile itself is the only part of slice 1 these cannot cover: whether
# the image builds, on both architectures, is verified in CI. Everything else —
# the entrypoint's logic and the wrapper's preflight ladder — is shell, and is
# driven here against a stubbed runtime.

set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FAILED=0

echo "== syntax =="
bash -n "$HERE/../messy-streets"       && echo "  ok   messy-streets"       || FAILED=1
sh   -n "$HERE/../docker-entrypoint.sh" && echo "  ok   docker-entrypoint.sh" || FAILED=1
echo

echo "== doctor =="
python3 "$HERE/test_doctor.py" 2>&1 | tail -4 || FAILED=1
echo

echo "== smoke =="
python3 "$HERE/test_smoke.py" 2>&1 | tail -4 || FAILED=1
echo

echo "== tables =="
python3 "$HERE/test_tables.py" 2>&1 | tail -4 || FAILED=1
echo

echo "== stats and inspect =="
python3 "$HERE/test_stats.py" 2>&1 | tail -4 || FAILED=1
echo

echo "== sample =="
python3 "$HERE/test_sample.py" 2>&1 | tail -4 || FAILED=1
echo

echo "== pipeline =="
python3 "$HERE/test_pipeline.py" 2>&1 | tail -4 || FAILED=1
echo

echo "== geocode (plan only; the live path needs the network) =="
python3 "$HERE/test_geocode.py" 2>&1 | tail -4 || FAILED=1
echo

echo "== credentials and the secret sweep =="
python3 "$HERE/test_credentials.py" 2>&1 | tail -4 || FAILED=1
echo

echo "== vendored tree audit =="
python3 "$HERE/../tools/audit.py" || FAILED=1
echo

echo "== vendored tree matches the source =="
if [ -d "${MS_SOURCE_TREE:-/local/home/gaeree/phd}/phd" ]; then
    python3 "$HERE/../tools/vendor.py" --source "${MS_SOURCE_TREE:-/local/home/gaeree/phd}" --check || FAILED=1
else
    echo "  -- source tree not present; skipped"
fi
echo

"$HERE/test_entrypoint.sh" || FAILED=1
echo
"$HERE/test_wrapper.sh" || FAILED=1

echo
if [[ "$FAILED" -eq 0 ]]; then echo "all suites passed"; else echo "SUITES FAILED"; fi
exit "$FAILED"
