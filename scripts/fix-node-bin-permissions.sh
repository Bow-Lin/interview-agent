#!/usr/bin/env bash

set -euo pipefail

if [[ ! -d node_modules ]]; then
  exit 0
fi

while IFS= read -r -d '' path; do
  chmod a+x "$path"
done < <(
  find node_modules \
    \( -path 'node_modules/.bin/*' -o -path 'node_modules/*/bin/*' -o -path 'node_modules/@*/*/bin/*' -o -path 'node_modules/*/dist/bin/*' -o -path 'node_modules/@*/*/dist/bin/*' \) \
    -type f \
    -print0
)
