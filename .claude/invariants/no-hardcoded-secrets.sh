#!/bin/bash
# Check for hardcoded secrets in source files.
# Exit 1 on violation, print offending lines to stderr.
PATTERNS='(API_KEY|SECRET_KEY|PASSWORD|TOKEN|PRIVATE_KEY)\s*=\s*["\x27][A-Za-z0-9+/=]{16,}'

FOUND=$(grep -rn -E "$PATTERNS" \
  --include="*.py" --include="*.js" --include="*.ts" \
  --include="*.yaml" --include="*.yml" . 2>/dev/null \
  | grep -v node_modules | grep -v .git | grep -v __pycache__ | grep -v '.env' \
  | head -5)

if [ -n "$FOUND" ]; then
  echo "Potential hardcoded secrets found:" >&2
  echo "$FOUND" >&2
  exit 1
fi
exit 0
