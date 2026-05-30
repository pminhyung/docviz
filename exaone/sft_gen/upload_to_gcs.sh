#!/usr/bin/env bash
# Upload local SFT trajectory + auxiliary JSONLs to GCS.
# Mirror layout: local SFT/<mode>/<kind>/<YYMMDD>/train.jsonl
# ↔ remote gs://<bucket>/SFT/<mode>/<kind>/<YYMMDD>/train.jsonl
set -euo pipefail

BUCKET="${GCS_BUCKET:-gs://llm-agent-bucket}"
PREFIX="${GCS_PREFIX:-chatexaone_refactoring_dataset/SFT/docqa}"
LOCAL_ROOT="${LOCAL_ROOT:-train_data/SFT/docqa/}"
DATE="${DATE:-260527}"

files=(
  "trajectory/${DATE}/train.jsonl"
  "web_extract/${DATE}/train.jsonl"
  "readfulldocument/${DATE}/train.jsonl"
)

echo "=== uploads ==="
for rel in "${files[@]}"; do
  src="${LOCAL_ROOT}${rel}"
  dst="${BUCKET}/${PREFIX}/${rel}"
  if [ ! -f "$src" ]; then
    echo "  SKIP (missing): $src"
    continue
  fi
  count=$(wc -l < "$src")
  size=$(du -h "$src" | cut -f1)
  echo "  ${src} (${count} lines, ${size}) → ${dst}"
  gsutil -m cp "$src" "$dst"
done

echo ""
echo "=== sample counts (after upload) ==="
for rel in "${files[@]}"; do
  src="${LOCAL_ROOT}${rel}"
  [ -f "$src" ] || continue
  count=$(wc -l < "$src")
  kind=$(echo "$rel" | cut -d/ -f1)
  echo "  ${kind}: ${count} samples"
done
