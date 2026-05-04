#!/usr/bin/env bash
# Create DynamoDB tables in Floci (LocalStack-compatible endpoint).
set -euo pipefail

ENDPOINT="${LOCALSTACK_ENDPOINT:-http://localhost:4566}"
AWS="aws --endpoint-url $ENDPOINT --region ap-northeast-1"

echo "Using endpoint: $ENDPOINT"

# Groups
$AWS dynamodb create-table \
  --table-name Groups \
  --attribute-definitions AttributeName=group_id,AttributeType=S \
  --key-schema AttributeName=group_id,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST \
  2>/dev/null && echo "Created: Groups" || echo "Exists:  Groups"

# Devices  (PK: group_id, SK: dev_id, GSI: api_key-index)
$AWS dynamodb create-table \
  --table-name Devices \
  --attribute-definitions \
    AttributeName=group_id,AttributeType=S \
    AttributeName=dev_id,AttributeType=S \
    AttributeName=api_key,AttributeType=S \
  --key-schema \
    AttributeName=group_id,KeyType=HASH \
    AttributeName=dev_id,KeyType=RANGE \
  --global-secondary-indexes '[
    {
      "IndexName": "api_key-index",
      "KeySchema": [{"AttributeName":"api_key","KeyType":"HASH"}],
      "Projection": {"ProjectionType":"ALL"}
    }
  ]' \
  --billing-mode PAY_PER_REQUEST \
  2>/dev/null && echo "Created: Devices" || echo "Exists:  Devices"

echo "Tables ready."
