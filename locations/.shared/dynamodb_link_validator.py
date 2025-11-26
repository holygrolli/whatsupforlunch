"""
DynamoDB Link Validator Helper

This module provides utilities to check and store scraped links in AWS DynamoDB
with TTL-based expiration to avoid reprocessing the same content.
"""

import boto3
from datetime import datetime, timedelta
from typing import Optional
from botocore.exceptions import ClientError


class LinkValidator:
    """
    Helper class to validate and store links in DynamoDB with TTL support.
    
    Table schema:
    - Partition key: link (String)
    - Sort key: timestamp (Number) - used as TTL attribute
    """
    
    def __init__(
        self,
        table_name: str = "lunchdeal",
        region_name: str = "eu-central-1",
        aws_account_id: str = "840940990295"
    ):
        """
        Initialize the LinkValidator with DynamoDB connection.
        
        Args:
            table_name: Name of the DynamoDB table
            region_name: AWS region
            aws_account_id: AWS account ID (for reference)
        """
        self.table_name = table_name
        self.region_name = region_name
        self.aws_account_id = aws_account_id
        
        # Initialize DynamoDB resource
        self.dynamodb = boto3.resource('dynamodb', region_name=region_name)
        self.table = self.dynamodb.Table(table_name)
    
    def link_exists(self, link: str) -> bool:
        """
        Check if a link already exists in DynamoDB and has not expired.
        
        Args:
            link: The URL to check
            
        Returns:
            True if the link exists and has not expired, False otherwise
        """
        try:
            current_timestamp = int(datetime.now().timestamp())
            
            # Query for the link with timestamp >= current time
            response = self.table.query(
                KeyConditionExpression=boto3.dynamodb.conditions.Key('link').eq(link) & 
                                     boto3.dynamodb.conditions.Key('timestamp').gte(current_timestamp),
                Limit=1
            )
            
            # If we found any items, the link exists and is not expired
            return len(response.get('Items', [])) > 0
            
        except ClientError as e:
            print(f"Error checking link existence: {e}")
            # On error, assume link doesn't exist to avoid skipping content
            return False
    
    def add_link(self, link: str, ttl_weeks: int = 8) -> bool:
        """
        Add a link to DynamoDB with a TTL timestamp.
        
        Args:
            link: The URL to store
            ttl_weeks: Number of weeks until the link expires (default: 8)
            
        Returns:
            True if successfully added, False otherwise
        """
        try:
            current_time = datetime.now()
            expiry_time = current_time + timedelta(weeks=ttl_weeks)
            timestamp = int(expiry_time.timestamp())
            
            # Put item in DynamoDB
            self.table.put_item(
                Item={
                    'link': link,
                    'timestamp': timestamp,
                    'created_at': current_time.isoformat(),
                    'expires_at': expiry_time.isoformat()
                }
            )
            
            print(f"Successfully added link: {link} (expires: {expiry_time.isoformat()})")
            return True
            
        except ClientError as e:
            print(f"Error adding link: {e}")
            return False
    
    def mark_link_processed(self, link: str, ttl_weeks: int = 8) -> bool:
        """
        Convenience method to mark a link as processed (alias for add_link).
        
        Args:
            link: The URL to mark as processed
            ttl_weeks: Number of weeks until the link expires (default: 8)
            
        Returns:
            True if successfully marked, False otherwise
        """
        return self.add_link(link, ttl_weeks)


def get_validator() -> LinkValidator:
    """
    Factory function to create a LinkValidator instance with default settings.
    
    Returns:
        LinkValidator instance configured for the lunchdeal table
    """
    return LinkValidator()


# Standalone functions for easier imports
def check_link(link: str) -> bool:
    """
    Check if a link exists in DynamoDB (standalone function).
    
    Args:
        link: The URL to check
        
    Returns:
        True if link exists and has not expired, False otherwise
    """
    validator = get_validator()
    return validator.link_exists(link)


def mark_processed(link: str, ttl_weeks: int = 8) -> bool:
    """
    Mark a link as processed in DynamoDB (standalone function).
    
    Args:
        link: The URL to mark as processed
        ttl_weeks: Number of weeks until expiration (default: 8)
        
    Returns:
        True if successfully marked, False otherwise
    """
    validator = get_validator()
    return validator.add_link(link, ttl_weeks)
