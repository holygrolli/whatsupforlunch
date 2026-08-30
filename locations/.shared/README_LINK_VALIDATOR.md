# DynamoDB Link Validator

This module provides link validation and tracking functionality using AWS DynamoDB to prevent reprocessing of already-scraped content.

## Overview

The link validator uses a DynamoDB table to track which links have been processed, with automatic TTL (Time To Live) expiration to allow re-processing after a configurable period (default: 8 weeks).

## DynamoDB Table Configuration

**Table Name:** `lunchdeal`  
**AWS Account:** `840940990295`  
**Region:** `eu-central-1`

**Table Schema:**
- **Partition Key:** `link` (String) - The URL being tracked
- **Sort Key:** `timestamp` (Number) - Unix timestamp used for TTL
- **TTL Attribute:** `timestamp` - Automatically removes expired entries

## Files

- `dynamodb_link_validator.py` - Main helper module with LinkValidator class
- `mark_link_processed.py` - Standalone script for marking links as processed (used in CI/CD)

## Usage

### In Scrapy Spiders

```python
import sys
from pathlib import Path

# Add shared modules to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / '.shared'))
from dynamodb_link_validator import LinkValidator

class MySpider(scrapy.Spider):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.link_validator = LinkValidator()
    
    def parse(self, response):
        links = response.xpath('//a/@href').getall()
        for link in links:
            # Check if link was already processed
            if self.link_validator.link_exists(link):
                print(f"Skipping already processed link: {link}")
                continue
            
            # Process new link
            yield scrapy.Request(url=link, callback=self.parse_detail)
```

### Marking Links as Processed (CI/CD)

After successfully processing a link in your workflow:

```bash
python locations/.shared/mark_link_processed.py "https://example.com/page"
```

With custom TTL (4 weeks instead of default 8):

```bash
python locations/.shared/mark_link_processed.py "https://example.com/page" --ttl-weeks 4
```

### Standalone Functions

```python
from dynamodb_link_validator import check_link, mark_processed

# Check if a link exists
if check_link("https://example.com/page"):
    print("Link already processed")

# Mark a link as processed
mark_processed("https://example.com/page", ttl_weeks=8)
```

## AWS Credentials

The module uses boto3 which requires AWS credentials. Credentials can be provided via:

1. **Environment variables:**
   ```bash
   export AWS_ACCESS_KEY_ID=your_key_id
   export AWS_SECRET_ACCESS_KEY=your_secret_key
   export AWS_DEFAULT_REGION=eu-central-1
   ```

2. **GitHub Secrets (for workflows):**
   - `AWS_ACCESS_KEY_ID`
   - `AWS_SECRET_ACCESS_KEY`

3. **AWS credentials file** (`~/.aws/credentials`)

4. **IAM role** (for EC2/ECS/Lambda)

## Required IAM Permissions

The AWS credentials need the following permissions on the `lunchdeal` table:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "dynamodb:Query",
        "dynamodb:PutItem"
      ],
      "Resource": "arn:aws:dynamodb:eu-central-1:840940990295:table/lunchdeal"
    }
  ]
}
```

## TTL Configuration

The system uses an 8-week default TTL, meaning:
- Links are tracked for 8 weeks after processing
- After 8 weeks, DynamoDB automatically removes the entry
- The link becomes available for reprocessing

To change the TTL period, use the `ttl_weeks` parameter:

```python
validator.add_link("https://example.com", ttl_weeks=4)  # 4 weeks instead of 8
```

## Error Handling

The validator is designed to fail gracefully:
- If DynamoDB is unavailable, links are **not skipped** (processing continues)
- Errors are logged but don't stop the scraping process
- This ensures scrapers continue working even if the validation service is down

## Testing Locally

```bash
# Install dependencies
pipenv install

# Test link checking with the shared helper
python -c "import sys; sys.path.insert(0, 'locations/.shared'); from dynamodb_link_validator import check_link; print(check_link('https://test.com'))"

# The production runner is the preferred integration path
python -m pipeline ratskeller scrape

# Test marking as processed (only for an intentional manual check)
python locations/.shared/mark_link_processed.py "https://test.com"
```

## Integration in the location pipeline

The common `.github/workflows/location.yaml` workflow invokes the runner for every
location. The runner:
1. **Scrape stage:** checks discovered links against DynamoDB before downloading
2. **Publish stage:** marks a link only after its menu JSON has passed validation and
   has been written
3. **Failure handling:** a failed extraction is not marked, so the next run retries it

During the state migration release, `--legacy-state` may also read the old marker file;
all new writes still go only to DynamoDB.

## Troubleshooting

### "Access Denied" error
Verify AWS credentials have correct permissions on the DynamoDB table.

### Links still being reprocessed
Check that the TTL hasn't expired (8 weeks by default) and that DynamoDB TTL is enabled on the table.

### Import errors
Ensure boto3 is installed: `pipenv install boto3`

### DynamoDB connection timeout
Verify network connectivity to AWS and correct region configuration (eu-central-1).
