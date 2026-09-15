FROM python:3.10-slim

RUN apt-get update && \
    apt-get install -y --no-install-recommends poppler-utils curl jq git ca-certificates && \
    rm -rf /var/lib/apt/lists/*
# PyYAML is required by pipeline/config.py to load the checked-in location YAML.
# Patchright is a Playwright-compatible Chromium driver with browser-detection
# patches. Keep its browser revision and Python package installed together.
RUN pip install --no-cache-dir openai scrapy htmlmin lxml lxml_html_clean boto3 pyyaml \
    patchright==1.62.3
# Install Chromium and all Debian runtime libraries needed by headless mode.
# Use a shared cache so a future non-root runtime user can still launch it.
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
RUN patchright install --with-deps chromium && \
    chmod -R a+rX /ms-playwright
ENV NVM_DIR /usr/local/nvm
ENV NODE_VERSION lts/iron
RUN mkdir -p /usr/local/nvm && apt-get update && echo "y" | apt-get install curl
RUN curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.7/install.sh | bash && \
    chmod +x $NVM_DIR/nvm.sh && \
    . $NVM_DIR/nvm.sh && \
    nvm install --latest-npm "$NODE_VERSION" && \
    nvm alias default "$NODE_VERSION" && \
    nvm use default && \
    DEFAULT_NODE_VERSION=$(nvm version default) && \
    ln -sf $NVM_DIR/versions/node/$DEFAULT_NODE_VERSION/bin/node /usr/bin/nodejs && \
    ln -sf $NVM_DIR/versions/node/$DEFAULT_NODE_VERSION/bin/node /usr/bin/node && \
    ln -sf $NVM_DIR/versions/node/$DEFAULT_NODE_VERSION/bin/npm /usr/bin/npm
