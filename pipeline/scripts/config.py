"""Central configuration for VisuBench research pipeline."""
import os

# ── Paths ──────────────────────────────────────────────────────────────────
VISUBENCH_ROOT = "/ex_disk2/mhpark/poc/visubench"
DOCAI_BASE = "/ex_disk2/mhpark/poc/docai/out"
DATA_DIR = os.path.join(VISUBENCH_ROOT, "data")
RESULTS_DIR = os.path.join(VISUBENCH_ROOT, "results")

SIDECAR_MERMAID_URL = "http://localhost:3005"
SIDECAR_MINDMAP_URL = "http://localhost:3004"

# ── Visualization Types ────────────────────────────────────────────────────
VIZ_TYPES = ["mindmap", "diagram", "chart"]

# Expanded 2026-04-09 for viz layer redesign (Guide 1 §2.2 / §3.1).
# Chart 5→8 (Vega-Lite backed), Diagram 5→7 (classDiagram + stateDiagram added).
DIAGRAM_SUBTYPES = [
    "flowchart", "sequenceDiagram", "classDiagram", "stateDiagram",
    "erDiagram", "gantt", "sankey",
]
CHART_SUBTYPES = [
    "bar", "line", "pie", "scatter", "combo", "area", "radar", "doughnut",
]

# Legacy narrow lists (pre-2026-04-09) retained for any archived scripts that
# still reference the short form. Do NOT import these in new code.
LEGACY_DIAGRAM_SUBTYPES = ["flowchart", "sequenceDiagram", "gantt", "sankey", "erDiagram"]
LEGACY_CHART_SUBTYPES = ["bar", "combo", "pie", "line", "scatter"]

# ── GPU Policy ─────────────────────────────────────────────────────────────
# GPU 2-9: OFF LIMITS. Use only: 0, 1, 10, 11, 12, 13, 14, 15 (8 GPUs)
ALLOWED_GPUS = [0, 1, 10, 11, 12, 13, 14, 15]

# ── Model Configs ──────────────────────────────────────────────────────────
MODEL_CONFIGS = {
    "qwen397b": {
        "type": "llmpool",
        "model": "Qwen3.5-397B-A17B-FP8",
        "hosts": ["10.1.211.148", "10.1.211.169", "10.1.211.170"],
        "port": 8000,
    },
    "gpt5": {
        "type": "openai",
        "model": "gpt-5",
    },
    "claude46": {
        "type": "anthropic",
        "model": "claude-opus-4-6",
    },
    "gemini25": {
        "type": "google",
        "model": "gemini-2.5-pro",
    },
    "qwen9b": {
        "type": "vllm_multi",
        "model": "/ex_disk2/mhpark/poc/chartvr/models/qwen3.5-9b",
        "gpus": [3],
        "ports": [8100],  # D14 retry 2026-04-09: GPU 3 (0-2 have zombie memory)
        "thinking_toggle": False,  # Qwen3.5: must disable thinking
    },
    "internvl3": {
        "type": "vllm_multi",
        "model": "OpenGVLab/InternVL3-8B",
        "gpus": [12, 13, 14, 15],
        "ports": [8112, 8113, 8114, 8115],
    },
    # ── Open-source models (Unsloth versions) ──────────────────────────────
    "gpt_oss_20b": {
        "type": "vllm_multi",
        "model": "/ex_disk2/mhpark/poc/chartvr/models/gpt-oss-20b",
        "gpus": [4],
        "ports": [8101],  # D14 retry 2026-04-09: GPU 4
        "note": "Unsloth/gpt-oss-20b, active 3.6B, TP=1×8, reasoning model",
    },
    "llama4_scout": {
        "type": "vllm_multi",
        "model": "/ex_disk2/mhpark/poc/chartvr/models/llama4-scout",
        "gpus": ALLOWED_GPUS,
        "ports": [8100],
        "tp": 8,
        "note": "Unsloth/Llama-4-Scout-17B-16E-Instruct, MoE 203GB, TP=8×1",
    },
    "gemma3_4b": {
        "type": "vllm_multi",
        "model": "/ex_disk2/mhpark/poc/chartvr/models/gemma3-4b-it",
        "gpus": [5],
        "ports": [8102],  # D14 retry 2026-04-09: GPU 5
        "note": "Unsloth/gemma-3-4b-it, 4B, TP=1×8",
    },
    "mistral_small_3_24b": {
        "type": "vllm_multi",
        "model": "/ex_disk2/mhpark/poc/chartvr/models/mistral-small-3.1-24b-instruct",
        "gpus": [0, 1],
        "ports": [8103],
        "tp": 2,
        "note": "mistralai/Mistral-Small-3.1-24B-Instruct-2503, 24B dense, TP=2, Apache 2.0",
    },
    "claude_sonnet_4_6": {
        "type": "claude_cli",
        "model": "claude-sonnet-4-6",
        "note": "Frontier representative via `claude -p --model sonnet` subprocess; "
                "parallel=8. D21 2026-04-13 added to gate closed-model spend.",
    },
}

# ── VLM Judge mapping ──────────────────────────────────────────────────────
# NOTE: Closed APIs (gpt5, claude46, gemini25) disabled until user enables.
# For now, all models judged by qwen397b (on-premise).
# Once closed APIs enabled, restore circular eval prevention:
#   qwen397b→gpt5, gpt5→qwen397b, others→qwen397b
JUDGE_FOR_MODEL = {
    "qwen397b": "qwen397b",  # circular skip handled in step5
    "qwen9b": "qwen397b",
    "internvl3": "qwen397b",
    "gpt_oss_20b": "qwen397b",
    "llama4_scout": "qwen397b",
    "gemma3_4b": "qwen397b",
    "mistral_small_3_24b": "qwen397b",
    "claude_sonnet_4_6": "qwen397b",
    # Closed APIs (activate on user request):
    # "gpt5": "qwen397b",
    # "claude46": "qwen397b",
    # "gemini25": "qwen397b",
}

# ── Domain → directory mapping ─────────────────────────────────────────────
DOMAIN_DIRS = {
    "finance": [
        "27_ko_dart_annual_report", "29_ko_dart_quarterly_report",
        "28_ko_dart_audit_report", "30_findoc_secgov_10K",
        "31_findoc_secgov_10Q", "32_IM증권",
        "32_Konex_KRP_analysis_report", "33_KoreanIR_analysis_report",
        "5_하나금융연구소", "8_KB경영연구소",
    ],
    "tech": [
        "13_etri", "29_ETRI", "12_한국산업기술진흥원",
        "27_en_NASA", "26_en_NIST",
    ],
    "science": [
        "14_kistep", "31_KISTEP", "10_과학기술정책연구원",
        "28_en_MDPI", "18_en_paper_renamed",
    ],
    "general": [
        "19_en_document", "21_en_mckinsey", "20_en_bcg",
        "3_pwc", "22_en_rand",
    ],
    "mixed": [
        "4_국회미래연구원", "6_포스코경영연구원", "7_현대경제연구원",
        "9_LG경영연구원", "23_en_aie", "24_en_idc",
        "25_en_piie", "38_KITA", "11_한국에너지경제연구원",
        "1_한국신용정보원", "30_KATS", "26_ko_paper",
    ],
}

# Reverse lookup: directory → domain
DIR_TO_DOMAIN = {}
for domain, dirs in DOMAIN_DIRS.items():
    for d in dirs:
        DIR_TO_DOMAIN[d] = domain

# ── Corpus targets ─────────────────────────────────────────────────────────
CORPUS_SIZE = 500
DOCS_PER_DOMAIN = 100
LANG_TARGETS = {"en": 200, "ko": 200, "zh": 100}
