# MESSY STREETS reproduction artefact.
#
# Single stage, no toolchain. Every pinned dependency has a prebuilt wheel for
# both linux/amd64 and linux/arm64, so the image builds natively on either
# without compiling anything.

# ---------------------------------------------------------------- runtime ---
FROM python:3.12.3-slim

# Pinned so that runs are comparable across machines. The DuckDB thread count
# matters: the benchmark sampler uses reservoir sampling, whose result can
# depend on how work is scheduled across cores.
ENV TZ=UTC \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    PYTHONHASHSEED=0 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    MS_DUCKDB_THREADS=1 \
    MS_ROOT=/opt/messy-streets \
    MS_OUT=/out

# --only-binary=:all: is an assertion, not an optimisation: every dependency
# has a prebuilt wheel for both linux/amd64 and linux/arm64, so no compiler is
# needed and the image is identical in shape on either architecture. If a
# future dependency needs building, this fails loudly rather than silently
# adding a toolchain.
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir --only-binary=:all: -r /tmp/requirements.txt \
 && rm -rf /tmp/requirements.txt

WORKDIR /opt/messy-streets

# Everything the repository tracks, minus what .dockerignore excludes.
#
# Deliberately not an enumeration. Listing directories individually left
# croissant.json out of the image while it was in the checksum manifest, and
# left LICENSE, LICENSE-DATA and pipeline/ out entirely -- so a reviewer
# running the container could not read the licence terms, and `pipeline show 9`
# would have failed on a missing script. `doctor` caught the first of those;
# the other two it could not see.
COPY . .

RUN install -m 0755 docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh \
 && pip install --no-cache-dir --no-deps -e . \
 && mkdir -p /out && chmod 777 /out

# The vendored dependency closure resolves relative to PYTHONPATH, exactly as
# it did in the source tree that produced the paper.
ENV PYTHONPATH=/opt/messy-streets/src

# Runs as whatever --user the caller passes, so output on a bind mount is owned
# by the caller rather than root. Nothing here needs privileges.
USER 1000:1000

ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["--help"]

LABEL org.opencontainers.image.title="MESSY STREETS reproduction artefact" \
      org.opencontainers.image.description="Reproduce the results of MESSY STREETS: A Benchmark for Geocoding Real-World Addresses (ACM SIGSPATIAL)" \
      org.opencontainers.image.licenses="TBD" \
      org.opencontainers.image.source="https://github.com/EdGaere/MessyStreets"