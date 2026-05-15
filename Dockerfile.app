# Code-only layer on top of Dockerfile.base (deps, OS, Playwright, uv sync,
# permissions, runtime ENV/VOLUME/ENTRYPOINT all live in the base image).
#
#   docker build -f Dockerfile.base -t hermes-agent-base:latest .
#   docker build -f Dockerfile.app -t hermes-agent:app .
#
# Optional: docker build -f Dockerfile.app --build-arg BASE_IMAGE=hermes-agent-base:mytag -t hermes-agent:app .
#
ARG BASE_IMAGE=hermes-agent-base:latest
FROM ${BASE_IMAGE}

COPY --chown=hermes:hermes . .

RUN cd web && npm run build && \
    cd ../ui-tui && npm run build

RUN uv pip install --no-cache-dir --no-deps -e "."
