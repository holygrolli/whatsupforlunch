#!/usr/bin/env python3
"""
Standalone script to mark a link as processed in DynamoDB.

This script is designed to be called from CI/CD workflows after
successfully processing a scraped link.

Usage:
    python mark_link_processed.py <url>
    python mark_link_processed.py <url> --ttl-weeks 8

Examples:
    python mark_link_processed.py "https://www.l.de/example/page"
    python mark_link_processed.py "https://www.l.de/example/page" --ttl-weeks 4
"""

import sys
import argparse
from dynamodb_link_validator import mark_processed


def main():
    parser = argparse.ArgumentParser(
        description='Mark a scraped link as processed in DynamoDB'
    )
    parser.add_argument(
        'url',
        help='The URL to mark as processed'
    )
    parser.add_argument(
        '--ttl-weeks',
        type=int,
        default=8,
        help='Number of weeks until the link expires (default: 8)'
    )
    
    args = parser.parse_args()
    
    try:
        success = mark_processed(args.url, ttl_weeks=args.ttl_weeks)
        if success:
            print(f"✓ Successfully marked link as processed: {args.url}")
            sys.exit(0)
        else:
            print(f"✗ Failed to mark link as processed: {args.url}", file=sys.stderr)
            sys.exit(1)
    except Exception as e:
        print(f"✗ Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
