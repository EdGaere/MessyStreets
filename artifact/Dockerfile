# MESSY STREETS reproduction artefact.
#
# Two stages: wheels are compiled once in a builder that has a toolchain
# (python-geohash 0.8.5 ships no wheels and needs gcc), then installed into a
# slim runtime that has none. Keeps the image small and identical across
# linux/amd64 and linux/arm64.

# ---------------------------------------------------------------- builder ---
FROM python:3.12.3-slim AS builder

RUN apt-get update \
 && apt-get install --no-install-recommends -y build-essential \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /wheels
COPY requirements.txt .
RUN pip wheel --no-cache-dir --wheel-dir /wheels -r requirements.txt

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

COPY --from=builder /wheels /wheels
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir --no-index --find-links /wheels -r /tmp/requirements.txt \
 && rm -rf /wheels /tmp/requirements.txt

WORKDIR /opt/messy-streets
COPY pyproject.toml requirements.txt README.md .artefact-revision ./
COPY messy_streets/ ./messy_streets/
COPY src/ ./src/
COPY data/ ./data/
COPY docker-entrypoint.sh /usr/local/bin/

RUN pip install --no-cache-dir --no-deps -e . \
 && chmod +x /usr/local/bin/docker-entrypoint.sh \
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