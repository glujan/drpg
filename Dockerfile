FROM python:3.12-slim AS builder

WORKDIR /app

# Install build dependencies
RUN pip install --no-cache-dir build

# Copy project files
COPY pyproject.toml README.md ./
COPY drpg/ ./drpg/

# Build the wheel
RUN python -m build --wheel

FROM python:3.12-slim

WORKDIR /app

# Copy the built wheel from builder stage
COPY --from=builder /app/dist/*.whl /tmp/

# Install the package
RUN pip install --no-cache-dir /tmp/*.whl && rm /tmp/*.whl

# Create a non-root user
RUN useradd --create-home --shell /bin/bash drpg
USER drpg

# Set working directory for downloads
WORKDIR /downloads

ENTRYPOINT ["drpg"]
