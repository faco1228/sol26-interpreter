FROM python:3.13-slim

WORKDIR /app

# install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# copy interpreter project files
COPY python/int/pyproject.toml python/int/uv.lock ./
COPY python/int/src ./src

# install dependencies via uv (no venv, system install)
RUN uv pip install --system -r <(uv export --no-dev --format requirements-txt)

# entry point: python -m solint (or direct script)
ENTRYPOINT ["python", "src/solint.py"]
