#!/usr/bin/env bash
# 离线演示：不调用任何真实模型，全部由 MockProvider 生成。
# 演示三件事：存基线 -> 跑新版本 -> 检测出回归并以退出码阻断。
set -uo pipefail

cd "$(dirname "$0")/.."
PY="${PYTHON:-python3}"
OUT="build"
mkdir -p "$OUT"

echo "==> 1/3 用 v1 生成基线"
"$PY" -m promptdiff run \
  --suite examples/cases.jsonl \
  --provider mock --mock-variant v1 \
  --out "$OUT/baseline.json" --report "$OUT/baseline.md" --quiet

echo
echo "==> 2/3 用 v2（模拟提示词改动）跑一遍，并与基线对比"
"$PY" -m promptdiff run \
  --suite examples/cases.jsonl \
  --provider mock --mock-variant v2 \
  --out "$OUT/current.json" --report "$OUT/current.md" \
  --baseline "$OUT/baseline.json" --fail-on-regression --quiet
GATE=$?
echo "    退出码 = ${GATE}（1 表示检测到回归，CI 应当阻断合并）"

echo
echo "==> 3/3 单独生成差异报告"
"$PY" -m promptdiff compare \
  --baseline "$OUT/baseline.json" --current "$OUT/current.json" \
  --report "$OUT/diff.md"

echo
echo "产物：$OUT/baseline.md  $OUT/current.md  $OUT/diff.md"
