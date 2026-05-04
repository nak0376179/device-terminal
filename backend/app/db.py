"""DynamoDB client helpers with Floci / LocalStack support."""

from __future__ import annotations

import os
from functools import lru_cache

import boto3

LOCALSTACK_ENDPOINT = os.environ.get("LOCALSTACK_ENDPOINT")

TABLE_GROUPS = os.environ.get("TABLE_GROUPS", "Groups")
TABLE_DEVICES = os.environ.get("TABLE_DEVICES", "Devices")


@lru_cache(maxsize=1)
def _resource():
    return boto3.resource("dynamodb", endpoint_url=LOCALSTACK_ENDPOINT)


def groups_table():
    return _resource().Table(TABLE_GROUPS)


def devices_table():
    return _resource().Table(TABLE_DEVICES)
