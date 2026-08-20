#!/bin/sh
# Container entrypoint.
#
# The reproduction pipeline writes results back into its own inputs: results
# land beside the cached predictions they were replayed from, and the sampler
# materialises a table into the tier database on first use. Running that
# directly against the baked image would mutate the artefact, and a partially
# failed run could truncate the cache that makes offline reproduction possible.
#
# So the image is immutable and read-only, and the tree is copied once into the
# output mount. Inputs and outputs then sit side by side on the host, and a
# botched run is repaired by deleting a directory.

set -eu

BAKED="${MS_BAKED:-/opt/messy-streets}"
OUT="${MS_OUT:-/out}"
WORK="${MS_WORK:-$OUT/work}"
STAMP="$WORK/.artefact-revision"

if [ ! -d "$OUT" ]; then
    echo "messy-streets: output directory '$OUT' does not exist." >&2
    echo "  Mount one with:  -v \"\$PWD/out:$OUT\"" >&2
    exit 2
fi

if ! touch "$OUT/.write-probe" 2>/dev/null; then
    echo "messy-streets: output directory '$OUT' is not writable by uid $(id -u)." >&2
    echo "  Run with:  --user \$(id -u):\$(id -g)" >&2
    echo "  On SELinux hosts the mount also needs a :Z suffix." >&2
    exit 2
fi
rm -f "$OUT/.write-probe"

REVISION="$(cat "$BAKED/.artefact-revision" 2>/dev/null || echo unknown)"

if [ ! -f "$STAMP" ] || [ "$(cat "$STAMP")" != "$REVISION" ]; then
    echo "messy-streets: preparing working copy in $WORK (revision $REVISION)" >&2
    rm -rf "$WORK.tmp"
    mkdir -p "$WORK.tmp"
    # -a would try to preserve ownership; the caller's uid may not own the
    # baked files, so copy contents and let them land as the caller.
    cp -R "$BAKED/." "$WORK.tmp/"
    rm -rf "$WORK"
    mv "$WORK.tmp" "$WORK"
    printf '%s' "$REVISION" > "$STAMP"
fi

# Everything from here reads and writes the working copy, never the image.
export MS_ROOT="$WORK"
export MS_OUT="$OUT"
export PYTHONPATH="$WORK/src"

if [ "${1:-}" = "shell" ]; then
    shift
    cd "$WORK"
    exec /bin/sh "$@"
fi

exec python -m messy_streets "$@"
