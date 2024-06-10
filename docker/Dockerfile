FROM python:3.10-slim

RUN apt-get update && \
    apt-get install -y poppler-utils curl jq git
RUN pip install amazon-textract-textractor[pdf,pandas] openai scrapy htmlmin
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