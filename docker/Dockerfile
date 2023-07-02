FROM python:3.10-slim

RUN apt-get update && \
    apt-get install -y poppler-utils curl jq
RUN pip install amazon-textract-textractor[pdf,pandas] openai scrapy