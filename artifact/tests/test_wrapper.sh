#!/usr/bin/env bash
# Exercises the ./messy-streets preflight ladder against a stubbed runtime.
#
# Every state the preflight is supposed to detect — daemon down, image absent,
# emulation, no isolation — is simulated here, because none of them can be
# produced on a machine that has no container runtime at all.

set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(dirname "$HERE")"
WRAPPER="$REPO/messy-streets"
PASS=0; FAIL=0

check() {
    if [[ "$2" == *"$3"* ]]; then printf '  ok   %s\n' "$1"; PASS=$((PASS+1))
    else printf '  FAIL %s\n       expected: %s\n       got: %s\n' "$1" "$3" "$2"; FAIL=$((FAIL+1)); fi
}
check_absent() {
    if [[ "$2" != *"$3"* ]]; then printf '  ok   %s\n' "$1"; PASS=$((PASS+1))
    else printf '  FAIL %s: unexpectedly found %s\n' "$1" "$3"; FAIL=$((FAIL+1)); fi
}
check_rc() {
    if [[ "$2" == "$3" ]]; then printf '  ok   %s (exit %s)\n' "$1" "$2"; PASS=$((PASS+1))
    else printf '  FAIL %s: exit %s, expected %s\n' "$1" "$2" "$3"; FAIL=$((FAIL+1)); fi
}

SANDBOX="$(mktemp -d)"
trap 'rm -rf "$SANDBOX"' EXIT
RUN_LOG="$SANDBOX/run.argv"

wrapper() { # wrapper <extra-env...> -- <args...>
    env PATH="$HERE/fakes:$PATH" MS_OUT_DIR="$SANDBOX/out" FAKE_RUN_LOG="$RUN_LOG" "$@" 2>&1
}

echo "messy-streets preflight"

# --- runtime present but daemon not responding ---
OUTPUT="$(wrapper FAKE_DAEMON=down "$WRAPPER" --preflight)"; RC=$?
check "daemon down is diagnosed" "$OUTPUT" "not responding"
check "daemon down suggests a fix" "$OUTPUT" "systemctl start docker"
check_rc "daemon down exits 2" "$RC" 2

# --- image neither present nor pullable ---
OUTPUT="$(wrapper FAKE_HAS_IMAGE=0 FAKE_CAN_PULL=0 "$WRAPPER" --preflight)"; RC=$?
check "unresolvable image is diagnosed" "$OUTPUT" "cannot resolve"
check "unresolvable image offers a local build" "$OUTPUT" "build -t"
check_rc "unresolvable image exits 2" "$RC" 2

# --- image absent locally but pullable ---
OUTPUT="$(wrapper FAKE_HAS_IMAGE=0 FAKE_CAN_PULL=1 "$WRAPPER" --preflight)"; RC=$?
check "pullable image is pulled" "$OUTPUT" "pulled"
check_rc "pullable image passes preflight" "$RC" 0

# --- a tag pin must be called out; a digest must not ---
OUTPUT="$(wrapper "$WRAPPER" --preflight)"
check "tag pin warns about mutability" "$OUTPUT" "pinned by tag, not digest"
cp "$REPO/IMAGE" "$SANDBOX/IMAGE.bak"
echo "ghcr.io/edgaere/messy-streets@sha256:$(printf 'a%.0s' {1..64})" > "$REPO/IMAGE"
OUTPUT="$(wrapper "$WRAPPER" --preflight)"
check_absent "digest pin does not warn" "$OUTPUT" "pinned by tag"
cp "$SANDBOX/IMAGE.bak" "$REPO/IMAGE"

# --- architecture mismatch is a warning, not a failure ---
HOST_ARCH=amd64; [[ "$(uname -m)" =~ ^(aarch64|arm64)$ ]] && HOST_ARCH=arm64
OTHER=arm64; [[ "$HOST_ARCH" == arm64 ]] && OTHER=amd64
OUTPUT="$(wrapper FAKE_ARCH="$OTHER" "$WRAPPER" --preflight)"; RC=$?
check "foreign architecture warns" "$OUTPUT" "running under emulation"
check_rc "foreign architecture still passes" "$RC" 0
OUTPUT="$(wrapper FAKE_ARCH="$HOST_ARCH" "$WRAPPER" --preflight)"
check "native architecture is reported" "$OUTPUT" "native"

# --- isolation probe ---
OUTPUT="$(wrapper FAKE_NETNONE=0 "$WRAPPER" --preflight)"; RC=$?
check "missing isolation warns" "$OUTPUT" "could not verify --network none"
check_rc "missing isolation does not block" "$RC" 0

# --- unwritable output directory ---
RO="$SANDBOX/ro"; mkdir -p "$RO"; chmod 500 "$RO"
OUTPUT="$(env PATH="$HERE/fakes:$PATH" MS_OUT_DIR="$RO" "$WRAPPER" --preflight 2>&1)"; RC=$?
check "unwritable out is diagnosed" "$OUTPUT" "not writable"
check_rc "unwritable out exits 2" "$RC" 2
chmod 700 "$RO"

echo
echo "messy-streets dispatch"

# --- offline verbs must be run air-gapped; that is the whole claim ---
rm -f "$RUN_LOG"; wrapper "$WRAPPER" doctor >/dev/null
ARGV="$(tr '\n' ' ' < "$RUN_LOG")"
check "offline verb gets --network none" "$ARGV" "--network none"
check "run is read-only"                 "$ARGV" "--read-only"
check "run maps the caller's uid"        "$ARGV" "--user $(id -u):$(id -g)"
check "run mounts the output dir"        "$ARGV" "$SANDBOX/out:/out"
check "verb reaches the container"       "$ARGV" "doctor"

# --- the one verb that needs the network must not be isolated ---
rm -f "$RUN_LOG"; wrapper "$WRAPPER" geocode >/dev/null
ARGV="$(tr '\n' ' ' < "$RUN_LOG")"
check_absent "networked verb is not isolated" "$ARGV" "--network none"
check "networked verb still reaches the container" "$ARGV" "geocode"

# --- credentials reach only the verb that needs them, and only read-only ---
CREDS="$SANDBOX/credentials.hjson"
printf '{geocoders:{HERE_API_KEY: "x"}}\n' > "$CREDS"

rm -f "$RUN_LOG"; wrapper "$WRAPPER" geocode --credentials "$CREDS" >/dev/null
ARGV="$(tr '\n' ' ' < "$RUN_LOG")"
check "geocode mounts the credentials file" "$ARGV" "$CREDS:/run/messy-streets/credentials.hjson:ro"
check "the mount is read-only"              "$ARGV" ":ro"
check_absent "values never enter the container config" "$ARGV" "--env-file"

rm -f "$RUN_LOG"; wrapper "$WRAPPER" doctor --credentials "$CREDS" >/dev/null
check_absent "offline verbs never see credentials" "$(tr '\n' ' ' < "$RUN_LOG")" "credentials.hjson"

# --- the host-side verb must never start a container at all ---
rm -f "$RUN_LOG"
wrapper "$WRAPPER" credentials --credentials "$CREDS" >/dev/null 2>&1
[[ ! -f "$RUN_LOG" ]] && { echo "  ok   credentials runs on the host, not in a container"; PASS=$((PASS+1)); } \
                      || { echo "  FAIL credentials started a container"; FAIL=$((FAIL+1)); }

# --- unknown verbs are refused before anything starts ---
rm -f "$RUN_LOG"
OUTPUT="$(wrapper "$WRAPPER" nonsense)"; RC=$?
check "unknown verb is named" "$OUTPUT" "unknown command 'nonsense'"
check_rc "unknown verb exits 64" "$RC" 64
[[ ! -f "$RUN_LOG" ]] && { echo "  ok   unknown verb starts no container"; PASS=$((PASS+1)); } \
                      || { echo "  FAIL unknown verb started a container"; FAIL=$((FAIL+1)); }

# --- a failed preflight must not start a container ---
rm -f "$RUN_LOG"
wrapper FAKE_DAEMON=down "$WRAPPER" doctor >/dev/null
[[ ! -f "$RUN_LOG" ]] && { echo "  ok   failed preflight starts no container"; PASS=$((PASS+1)); } \
                      || { echo "  FAIL container started despite failed preflight"; FAIL=$((FAIL+1)); }

printf '\n  %s passed, %s failed\n' "$PASS" "$FAIL"
[[ "$FAIL" -eq 0 ]]
