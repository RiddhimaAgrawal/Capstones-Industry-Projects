#!/usr/bin/env bash
# Generates client SDKs from the live OpenAPI spec using OpenAPI Generator (via Docker).
# Usage: ./scripts/generate_sdks.sh [http://localhost:8000]
set -euo pipefail
HOST="${1:-http://localhost:8000}"
mkdir -p sdks
curl -sf "$HOST/openapi.json" -o sdks/openapi.json
for LANG in python typescript-fetch; do
  docker run --rm -v "$PWD/sdks:/local" openapitools/openapi-generator-cli generate \
    -i /local/openapi.json -g "$LANG" -o "/local/$LANG" \
    --additional-properties=packageName=textapi_client
  echo "generated sdks/$LANG"
done
