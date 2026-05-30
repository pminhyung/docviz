"""OpenAI-compatible chat completions server backed by HuggingFace
transformers.generate (no vLLM / no sglang).

Use when binary inference engines have driver/ABI mismatches but
transformers itself can load the model. Slower than vLLM (no continuous
batching, no paged attention), but works on driver 535.x + CUDA 12.2.

Usage:
    GEMMA4_GPUS=0,1 PORT=9401 \
        python scripts/gemma4_hf_server.py
"""
from __future__ import annotations

import json
import os
import time
import uuid
from typing import Any, Dict, List

import torch
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from transformers import AutoConfig, AutoTokenizer, AutoModelForCausalLM
import uvicorn

MODEL_PATH = os.environ.get(
    "GEMMA4_MODEL_PATH", "/ex_disk2/mhpark/poc/chartvr/models/gemma-4-31B-it"
)
MODEL_ID = os.environ.get("GEMMA4_MODEL_ID", "gemma-4-31b-it")
PORT = int(os.environ.get("PORT", "9401"))

print(f"[gemma4_hf] loading {MODEL_PATH} on GPUs {os.environ.get('CUDA_VISIBLE_DEVICES','all')}", flush=True)
t0 = time.time()

tokenizer = AutoTokenizer.from_pretrained(MODEL_PATH)
# device_map="auto" balances across visible GPUs (CUDA_VISIBLE_DEVICES already restricts)
n_gpus = torch.cuda.device_count()
# Reserve ~10 GB per GPU for activations/KV cache; this prevents the
# device_map="auto" from packing 37+ GB into one GPU and OOMing at
# generate-time. With TP=4 across 40 GB GPUs we cap each at 28 GiB.
max_mem_per_gpu = "28GiB"
max_memory = {i: max_mem_per_gpu for i in range(n_gpus)}
print(f"[gemma4_hf] device_map=balanced across {n_gpus} gpus, max_memory={max_memory}", flush=True)

model = AutoModelForCausalLM.from_pretrained(
    MODEL_PATH,
    torch_dtype=torch.bfloat16,
    device_map="auto",
    max_memory=max_memory,
    low_cpu_mem_usage=True,
    trust_remote_code=False,
)
model.eval()
print(f"[gemma4_hf] loaded in {time.time()-t0:.0f}s", flush=True)


# ── OpenAI-compatible schemas ────────────────────────────────────────────
class ChatMessage(BaseModel):
    role: str
    content: str | list


class ChatCompletionRequest(BaseModel):
    model: str
    messages: List[ChatMessage]
    max_tokens: int | None = 512
    temperature: float | None = 0.7
    top_p: float | None = 0.95
    seed: int | None = None
    response_format: Dict[str, Any] | None = None
    stop: list | None = None
    n: int | None = 1


app = FastAPI()


@app.get("/health")
def health():
    return {"status": "healthy"}


@app.get("/v1/models")
def models():
    return {"object": "list", "data": [{"id": MODEL_ID, "object": "model", "owned_by": "hf_transformers"}]}


@app.post("/v1/chat/completions")
def chat_completions(req: ChatCompletionRequest):
    # Build messages list with string contents (drop multimodal parts)
    msgs = []
    for m in req.messages:
        content = m.content
        if isinstance(content, list):
            text_parts = [p.get("text", "") for p in content if isinstance(p, dict) and p.get("type") == "text"]
            content = "\n".join(text_parts)
        msgs.append({"role": m.role, "content": content})

    try:
        prompt = tokenizer.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"chat template error: {e}")
    inputs = tokenizer(prompt, return_tensors="pt").to(model.device)

    gen_kwargs = dict(
        max_new_tokens=req.max_tokens or 512,
        do_sample=(req.temperature is not None and req.temperature > 0),
        temperature=req.temperature if (req.temperature and req.temperature > 0) else 1.0,
        top_p=req.top_p if req.top_p is not None else 0.95,
        pad_token_id=tokenizer.eos_token_id,
    )
    if req.seed is not None:
        torch.manual_seed(req.seed)

    with torch.inference_mode():
        out_ids = model.generate(**inputs, **gen_kwargs)

    # Strip prompt tokens
    new_tokens = out_ids[0][inputs["input_ids"].shape[1]:]
    text = tokenizer.decode(new_tokens, skip_special_tokens=True)
    prompt_tokens = int(inputs["input_ids"].shape[1])
    completion_tokens = int(new_tokens.shape[0])

    return {
        "id": f"chatcmpl-{uuid.uuid4().hex[:24]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": MODEL_ID,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": text},
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        },
    }


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="warning")
