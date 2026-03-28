FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    bash \
    coreutils \
    curl \
    jq \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install Python packages including Playwright
RUN pip install --no-cache-dir \
    playwright \
    requests \
    beautifulsoup4 \
    lxml

# Create sandbox user first, then install Chromium as that user
RUN useradd -m -s /bin/bash sandbox

# Install Chromium as sandbox user so the path is correct
USER sandbox
RUN playwright install chromium
USER root

# Install Chromium system dependencies
RUN playwright install-deps chromium

USER sandbox
WORKDIR /workspace

CMD ["sleep", "infinity"]
