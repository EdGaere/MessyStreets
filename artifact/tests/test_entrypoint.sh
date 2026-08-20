#!/usr/bin/env bash
# Exercises docker-entrypoint.sh without a container.
#
# The entrypoint is plain POSIX shell, so its real logic — the write probe, the
# working-copy revision stamp, the environment it exports — can be driven
# directly. Only the image build itself needs a daemon, and that is CI's job.

set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(dirname "$HERE")"
ENTRY="$REPO/docker-entrypoint.sh"
PASS=0; FAIL=0

check() { # check <name> <condition-description> <actual> <expected-substring>
    if [[ "$3" == *"$4"* ]]; then printf '  ok   %s\n' "$1"; PASS=$((PASS+1))
    else printf '  FAIL %s\n       expected to contain: %s\n       got: %s\n' "$1" "$4" "$3"; FAIL=$((FAIL+1)); fi
}
check_rc() {
    if [[ "$2" == "$3" ]]; then printf '  ok   %s (exit %s)\n' "$1" "$2"; PASS=$((PASS+1))
    else printf '  FAIL %s: exit %s, expected %s\n' "$1" "$2" "$3"; FAIL=$((FAIL+1)); fi
}

SANDBOX="$(mktemp -d)"
trap 'rm -rf "$SANDBOX"' EXIT
BAKED="$SANDBOX/baked"
mkdir -p "$BAKED/src/phd" "$BAKED/data"
echo "cached-prediction" > "$BAKED/data/results.json"
printf '%s' "rev-one" > "$BAKED/.artefact-revision"

run_entry() { # run_entry <out-dir> [args...]
    local out="$1"; shift
    env PATH="$HERE/fakes:$PATH" MS_BAKED="$BAKED" MS_OUT="$out" \
        sh "$ENTRY" "$@" 2>&1
}

echo "docker-entrypoint.sh"

# --- 1. missing output mount is named, not guessed at ---
OUTPUT="$(run_entry "$SANDBOX/does-not-exist" doctor)"; RC=$?
check "missing mount is diagnosed" "" "$OUTPUT" "does not exist"
check_rc "missing mount exits 2" "$RC" 2

# --- 2. unwritable mount tells you the --user fix ---
RO="$SANDBOX/readonly"; mkdir -p "$RO"; chmod 500 "$RO"
OUTPUT="$(run_entry "$RO" doctor)"; RC=$?
check "unwritable mount is diagnosed" "" "$OUTPUT" "not writable"
check "unwritable mount suggests --user" "" "$OUTPUT" "--user"
check "unwritable mount mentions SELinux" "" "$OUTPUT" "SELinux"
check_rc "unwritable mount exits 2" "$RC" 2
chmod 700 "$RO"

# --- 3. first run builds the working copy ---
OUT="$SANDBOX/out"; mkdir -p "$OUT"
OUTPUT="$(run_entry "$OUT" doctor)"; RC=$?
check "first run prepares working copy" "" "$OUTPUT" "preparing working copy"
check_rc "first run succeeds" "$RC" 0
[[ -f "$OUT/work/data/results.json" ]] \
    && { echo "  ok   data copied into the working copy"; PASS=$((PASS+1)); } \
    || { echo "  FAIL data not copied"; FAIL=$((FAIL+1)); }

# --- 4. the image is never the thing that gets written to ---
echo "mutated" > "$OUT/work/data/results.json"
check "baked tree untouched by a run" "" "$(cat "$BAKED/data/results.json")" "cached-prediction"

# --- 5. environment handed to the CLI points at the copy, not the image ---
OUTPUT="$(run_entry "$OUT" doctor)"
check "MS_ROOT points at the working copy" "" "$OUTPUT" "MS_ROOT=$OUT/work"
check "PYTHONPATH points at the working copy" "" "$OUTPUT" "PYTHONPATH=$OUT/work/src"
check "verb is forwarded to the CLI"  "" "$OUTPUT" "PYTHON_ARGS=-m messy_streets doctor"

# --- 6. second run reuses rather than rebuilding ---
if [[ "$OUTPUT" != *"preparing working copy"* ]]; then
    echo "  ok   second run reuses the working copy"; PASS=$((PASS+1))
else
    echo "  FAIL second run rebuilt the working copy"; FAIL=$((FAIL+1))
fi

# --- 7. a new artefact revision forces a rebuild ---
printf '%s' "rev-two" > "$BAKED/.artefact-revision"
OUTPUT="$(run_entry "$OUT" doctor)"
check "revision change rebuilds" "" "$OUTPUT" "preparing working copy"
check "rebuild restores the baked data" "" "$(cat "$OUT/work/data/results.json")" "cached-prediction"

# --- 8. shell verb drops into a prompt instead of the CLI ---
OUTPUT="$(run_entry "$OUT" shell -c 'echo INSIDE:$PWD')"
check "shell runs in the working copy" "" "$OUTPUT" "INSIDE:$OUT/work"

printf '\n  %s passed, %s failed\n' "$PASS" "$FAIL"
[[ "$FAIL" -eq 0 ]]
