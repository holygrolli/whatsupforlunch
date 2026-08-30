"""DynamoDB state backend — the only state backend for the pipeline.

Moved and trimmed from ``locations/.shared/dynamodb_link_validator.py``. Under
decision 3 of the plan only the two table fields are written: the URL/tracking
value in the ``link`` key and the Unix expiry value in the ``timestamp`` TTL
field. No audit attributes, no second state table.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta

DEFAULT_TABLE = "lunchdeal"
DEFAULT_REGION = "eu-central-1"
DEFAULT_TTL_WEEKS = 8


class StateBackendUnavailable(Exception):
    """Raised when the state backend cannot be reached (exit code 3)."""


class LinkState:
    """Processed-content check against the DynamoDB ``lunchdeal`` table.

    Table key shape (unchanged): partition key ``link`` (String), sort key
    ``timestamp`` (Number, Unix expiry used as TTL attribute).
    """

    def __init__(self, table_name: str | None = None, region_name: str | None = None,
                 table=None):
        self.table_name = table_name or os.environ.get("PIPELINE_STATE_TABLE", DEFAULT_TABLE)
        self.region_name = region_name or os.environ.get(
            "AWS_DEFAULT_REGION", DEFAULT_REGION
        )
        if table is not None:
            # Injected table (tests / local backends).
            self.table = table
        else:
            try:
                import boto3

                dynamodb = boto3.resource("dynamodb", region_name=self.region_name)
                self.table = dynamodb.Table(self.table_name)
            except Exception as exc:  # pragma: no cover - environment dependent
                raise StateBackendUnavailable(
                    f"cannot initialize DynamoDB table {self.table_name}: {exc}"
                ) from exc

    def link_exists(self, link: str) -> bool:
        """True if the link exists in the table and has not expired."""
        try:
            from boto3.dynamodb.conditions import Key

            current_timestamp = int(datetime.now().timestamp())
            response = self.table.query(
                KeyConditionExpression=Key("link").eq(link)
                & Key("timestamp").gte(current_timestamp),
                Limit=1,
            )
            return len(response.get("Items", [])) > 0
        except StateBackendUnavailable:
            raise
        except Exception as exc:
            raise StateBackendUnavailable(f"error checking link existence: {exc}") from exc

    def add_link(self, link: str, ttl_weeks: int = DEFAULT_TTL_WEEKS) -> bool:
        """Store a link with a TTL ``ttl_weeks`` in the future (decision 4).

        Only the ``link`` and ``timestamp`` fields are written (decision 3).
        """
        try:
            expiry_time = datetime.now() + timedelta(weeks=ttl_weeks)
            self.table.put_item(
                Item={"link": link, "timestamp": int(expiry_time.timestamp())}
            )
            return True
        except Exception as exc:
            raise StateBackendUnavailable(f"error adding link: {exc}") from exc

    def mark_link_processed(self, link: str, ttl_weeks: int = DEFAULT_TTL_WEEKS) -> bool:
        return self.add_link(link, ttl_weeks)
