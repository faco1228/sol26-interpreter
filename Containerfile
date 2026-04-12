### podman

# =============================================================================
# check — quality tools for int (Python) and tester (TypeScript)
# bind mounts: /src/int, /src/tester
# =============================================================================
FROM python:3.14-slim AS check

# node.js 24 LTS
RUN apt-get update && \
    apt-get install -y --no-install-recommends ca-certificates curl && \
    curl -fsSL https://deb.nodesource.com/setup_24.x | bash - && \
    apt-get install -y --no-install-recommends nodejs && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# python tools: ruff, mypy + runtime deps for type resolution
COPY int/pyproject.toml int/uv.lock /tmp/int/
RUN cd /tmp/int && \
    uv export --format requirements-txt --no-hashes -o /tmp/reqs.txt && \
    uv pip install --system --no-cache -r /tmp/reqs.txt && \
    rm -rf /tmp/int /tmp/reqs.txt

# typescript tools: install at /node_modules so ESM imports in eslint.config.mjs resolve
COPY tester/package.json tester/package-lock.json /tmp/tester/
RUN cd /tmp/tester && \
    npm ci --ignore-scripts && \
    mv node_modules /node_modules && \
    ln -s /node_modules/.bin/eslint   /usr/local/bin/eslint && \
    ln -s /node_modules/.bin/prettier /usr/local/bin/prettier && \
    rm -rf /tmp/tester

WORKDIR /src
ENTRYPOINT ["bash"]

# =============================================================================
# build-test — compile TypeScript tester to JavaScript
# =============================================================================
FROM node:24-slim AS build-test

WORKDIR /build
COPY tester/ ./
RUN npm ci && npm run build

# =============================================================================
# runtime — lean image running the Python interpreter
# =============================================================================
FROM python:3.14-slim AS runtime

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# runtime deps only, no dev tools
COPY int/pyproject.toml int/uv.lock /tmp/int/
RUN cd /tmp/int && \
    uv export --format requirements-txt --no-hashes --no-dev -o /tmp/reqs.txt && \
    uv pip install --system --no-cache -r /tmp/reqs.txt && \
    rm -rf /tmp/int /tmp/reqs.txt /usr/local/bin/uv

WORKDIR /app
COPY int/src ./src

ENTRYPOINT ["python", "src/solint.py"]

# =============================================================================
# test — runtime + compiled tester for integration testing
# =============================================================================
FROM runtime AS test

# node.js runtime for the compiled tester
RUN apt-get update && \
    apt-get install -y --no-install-recommends nodejs && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

COPY --from=build-test /build/dist         /app/tester/dist
COPY --from=build-test /build/node_modules /app/tester/node_modules

ENTRYPOINT ["node", "/app/tester/dist/tester.js"]
