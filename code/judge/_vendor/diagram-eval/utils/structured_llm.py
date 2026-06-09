"""
StructuredLLM: Helper class that prompts an LLM and parses the response
into a Pydantic model.

StructuredMLLM: Helper class for multimodal LLM with vision capabilities.
Supports extracting structured information from images.
"""

from __future__ import annotations

import base64
import os
import time
from pathlib import Path
from typing import Any, Dict, Optional, Type, Union

import yaml
from pydantic import BaseModel

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI
try:  # google backend optional — we use nvidia (OpenAI-compat) for Qwen
    from langchain_google_genai import ChatGoogleGenerativeAI
except ImportError:
    ChatGoogleGenerativeAI = None

import openai as _openai_sdk
_OAI_CLIENTS = {}
def _qwen_client(base_url, api_key):
    if base_url not in _OAI_CLIENTS:
        _OAI_CLIENTS[base_url] = _openai_sdk.OpenAI(base_url=base_url, api_key=api_key or "EMPTY", timeout=300)
    return _OAI_CLIENTS[base_url]

def _fmt(parser):
    """Concise schema hint per response_model — the auto-generated Pydantic dump
    (with $defs) confuses Qwen into echoing the schema. Hand-written is reliable."""
    n = getattr(getattr(parser, "pydantic_object", None), "__name__", "")
    if n == "GraphSpec":
        return ('Return JSON: {"nodes": [{"id": "n1", "text": "<exact node label>"}], '
                '"edges": [{"source": "n1", "target": "n2"}]}. List every node and every '
                'directed arrow. JSON only, no schema, no commentary.')
    if n == "NodeAlignmentResponse":
        return ('Return JSON: {"matches": [{"source_id": "<id in graph A>", '
                '"target_id": "<id in graph B>"}]}. Match semantically equivalent nodes. '
                'JSON only.')
    return parser.get_format_instructions()


def _repair_json(raw):
    """Best-effort close of a truncated JSON object (unbalanced braces/brackets)."""
    import json as _json
    try:
        return _json.loads(raw)
    except Exception:
        pass
    s = raw.rstrip().rstrip(",")
    # drop a dangling partial token after the last complete value
    for _ in range(len(s)):
        opens = s.count("{") - s.count("}")
        brk = s.count("[") - s.count("]")
        cand = s + "]" * max(brk, 0) + "}" * max(opens, 0)
        try:
            return _json.loads(cand)
        except Exception:
            s = s[:-1]
            if not s:
                break
    raise ValueError("unrepairable JSON")


def _qwen_structured(qwen, messages, parser, max_tokens=20000, max_retries=3):
    """Direct OpenAI-SDK call to Qwen (thinking ON). temp 0.6 makes the JSON
    quality vary run-to-run, so retry on parse failure (a re-roll usually parses)."""
    last = None
    for _ in range(max_retries):
        try:
            return _qwen_once(qwen, messages, parser, max_tokens)
        except Exception as exc:
            last = exc
    raise last


def _qwen_once(qwen, messages, parser, max_tokens):
    base_url, api_key, model = qwen
    resp = _qwen_client(base_url, api_key).chat.completions.create(
        model=model, messages=messages, temperature=0.6, top_p=0.95, max_tokens=max_tokens,
        extra_body={"top_k": 20, "min_p": 0, "chat_template_kwargs": {"enable_thinking": True}})
    msg = resp.choices[0].message
    content = (getattr(msg, "content", None) or "").strip()
    # fall back to reasoning_content only if content empty; strip any inline think
    if not content:
        content = (getattr(msg, "reasoning_content", None) or "").strip()
    import re as _re, json as _json
    content = _re.sub(r"<think>[\s\S]*?</think>", "", content).strip()
    # extract the first JSON object (tolerant of fences / prose around it)
    mfence = _re.search(r"```[a-z]*\s*([\s\S]*?)```", content)
    if mfence:
        content = mfence.group(1).strip()
    mobj = _re.search(r"\{[\s\S]*\}", content)
    raw = mobj.group(0) if mobj else content
    try:
        d = _repair_json(raw)  # tolerant: handles truncation/unbalanced braces
    except Exception:
        return parser.parse(content)  # last resort
    model = getattr(parser, "pydantic_object", None)
    name = getattr(model, "__name__", "")
    if name == "GraphSpec":
        nodes = []
        for i, n in enumerate(d.get("nodes") or []):
            if isinstance(n, str):
                nodes.append({"id": str(i + 1), "text": n})
            elif isinstance(n, dict):
                txt = n.get("text") or n.get("label") or n.get("name") or ""
                nodes.append({"id": str(n.get("id", i + 1)), "text": str(txt)})
        edges = []
        for e in d.get("edges") or []:
            if isinstance(e, (list, tuple)) and len(e) >= 2:
                edges.append({"source": str(e[0]), "target": str(e[1])})
            elif isinstance(e, dict):
                s = e.get("source") or e.get("src") or e.get("from")
                t = e.get("target") or e.get("dst") or e.get("to")
                if s is not None and t is not None:
                    edges.append({"source": str(s), "target": str(t)})
        return model(nodes=[n for n in nodes if n["text"].strip()], edges=edges)
    if name == "NodeAlignmentResponse":
        matches = []
        for m in d.get("matches") or []:
            if isinstance(m, dict):
                s = m.get("source_id") or m.get("source") or m.get("a")
                t = m.get("target_id") or m.get("target") or m.get("b")
                if s is not None and t is not None:
                    matches.append({"source_id": str(s), "target_id": str(t)})
        return model(matches=matches)
    return parser.parse(raw)


class StructuredLLM:
    """
    Wraps LangChain chat models to guarantee JSON-conformant responses.

    The configuration can be:
    1. A path to a YAML file containing the config
    2. A path with section (e.g., "config.yaml:section_name")
    3. A dictionary with the config directly

    Config format:
        api_type: "openai" | "google" | "nvidia"
        model: Model identifier for the target provider
        key_file: Relative path to the YAML file storing API keys
        api_key: Key name within ``key_file`` containing the actual token
        base_url: Optional base URL (used by e.g. NVIDIA NIM)
    """

    def __init__(self, config_path: str, response_model: Type[BaseModel], config_section: str = None):
        """
        (config_path: str, response_model: Type[BaseModel], config_section: str = None) -> None: 
        Load configuration, keys, and instantiate a typed LangChain pipeline.
        
        Args:
            config_path: Path to YAML config file
            response_model: Pydantic model for response validation
            config_section: Optional section name within the config file
        """
        if not os.path.exists(config_path):
            raise FileNotFoundError(f"Configuration file not found: {config_path}")

        with open(config_path, "r", encoding="utf-8") as file:
            full_config = yaml.safe_load(file)
        
        # Extract section if specified
        if config_section:
            if config_section not in full_config:
                raise ValueError(f"Config section '{config_section}' not found in {config_path}")
            config = full_config[config_section]
        else:
            config = full_config

        self.api_type: str = config.get("api_type", "")
        model_name: str = config.get("model", "")
        key_file: Optional[str] = config.get("key_file")
        api_key_name: Optional[str] = config.get("api_key")
        base_url: Optional[str] = config.get("base_url")

        if not model_name:
            raise ValueError("Model name missing in configuration file.")
        if not key_file or not api_key_name:
            raise ValueError("key_file and api_key entries are required in configuration.")

        config_dir = os.path.dirname(config_path)
        key_file_path = os.path.join(config_dir, key_file)
        if not os.path.exists(key_file_path):
            raise FileNotFoundError(f"Key file not found: {key_file_path}")

        with open(key_file_path, "r", encoding="utf-8") as file:
            key_store = yaml.safe_load(file)

        api_key = key_store.get(api_key_name)
        if not api_key:
            raise ValueError(f"API key '{api_key_name}' not found in {key_file_path}")

        if self.api_type == "google":
            self._client = ChatGoogleGenerativeAI(model=model_name, google_api_key=api_key)
        elif self.api_type == "openai":
            self._client = ChatOpenAI(model=model_name, api_key=api_key)
        elif self.api_type == "nvidia":
            if not base_url:
                raise ValueError("base_url must be provided for 'nvidia' API type.")
            # Qwen3.5 (thinking ON): call via OpenAI SDK directly so reasoning_content
            # and content are separated (langchain mishandles this → minutes-long hangs).
            self._qwen = (base_url, api_key, model_name)
            self._client = ChatOpenAI(model=model_name, api_key=api_key, base_url=base_url)
        else:
            raise ValueError(f"Unsupported api_type '{self.api_type}'.")

        self._parser = JsonOutputParser(pydantic_object=response_model)
        self._prompt = ChatPromptTemplate.from_template(
            "You are an assistant that replies in JSON only.\n"
            "{format_instructions}\n"
            "{query}\n"
        )

    def query(self, prompt: str, *, max_retries: int = 1) -> BaseModel:
        """
        (prompt: str, max_retries: int=1) -> BaseModel: Execute the pipeline and parse the structured response.
        """
        if max_retries < 1:
            raise ValueError("max_retries must be >= 1.")

        if getattr(self, "_qwen", None):
            msgs = [{"role": "user", "content":
                     f"You are an assistant that replies in JSON only.\n"
                     f"{_fmt(self._parser)}\n{prompt}\n"}]
            return _qwen_structured(self._qwen, msgs, self._parser)

        chain = self._prompt | self._client | self._parser

        for attempt in range(max_retries):
            try:
                return chain.invoke(
                    {
                        "query": prompt,
                        "temperature": 0.0,
                        "format_instructions": _fmt(self._parser),
                    }
                )
            except Exception:
                if attempt + 1 == max_retries:
                    raise
                time.sleep(2**attempt)

    def raw_invoke(self, payload: Dict[str, Any]) -> Any:
        """
        (payload: Dict[str, Any]) -> Any: Invoke the underlying chain with a custom payload.
        """
        chain = self._prompt | self._client | self._parser
        return chain.invoke(payload)


class StructuredMLLM:
    """
    Wraps LangChain multimodal chat models to guarantee JSON-conformant responses
    from vision+text inputs.

    The configuration can be:
    1. A path to a YAML file containing the config
    2. A path with section (e.g., "config.yaml:section_name")

    Config format:
        api_type: "openai" | "google" | "nvidia"
        model: Model identifier for the target provider
        key_file: Relative path to the YAML file storing API keys
        api_key: Key name within ``key_file`` containing the actual token
        base_url: Optional base URL (used by e.g. NVIDIA NIM)
    """

    def __init__(self, config_path: str, response_model: Type[BaseModel], config_section: str = None):
        """
        (config_path: str, response_model: Type[BaseModel], config_section: str = None) -> None: 
        Load configuration, keys, and instantiate a typed LangChain pipeline.
        
        Args:
            config_path: Path to YAML config file
            response_model: Pydantic model for response validation
            config_section: Optional section name within the config file
        """
        if not os.path.exists(config_path):
            raise FileNotFoundError(f"Configuration file not found: {config_path}")

        with open(config_path, "r", encoding="utf-8") as file:
            full_config = yaml.safe_load(file)
        
        # Extract section if specified
        if config_section:
            if config_section not in full_config:
                raise ValueError(f"Config section '{config_section}' not found in {config_path}")
            config = full_config[config_section]
        else:
            config = full_config

        self.api_type: str = config.get("api_type", "")
        model_name: str = config.get("model", "")
        key_file: Optional[str] = config.get("key_file")
        api_key_name: Optional[str] = config.get("api_key")
        base_url: Optional[str] = config.get("base_url")

        if not model_name:
            raise ValueError("Model name missing in configuration file.")
        if not key_file or not api_key_name:
            raise ValueError("key_file and api_key entries are required in configuration.")

        config_dir = os.path.dirname(config_path)
        key_file_path = os.path.join(config_dir, key_file)
        if not os.path.exists(key_file_path):
            raise FileNotFoundError(f"Key file not found: {key_file_path}")

        with open(key_file_path, "r", encoding="utf-8") as file:
            key_store = yaml.safe_load(file)

        api_key = key_store.get(api_key_name)
        if not api_key:
            raise ValueError(f"API key '{api_key_name}' not found in {key_file_path}")

        # Initialize the appropriate vision-capable model
        if self.api_type == "google":
            self._client = ChatGoogleGenerativeAI(
                model=model_name,
                google_api_key=api_key,
            )
        elif self.api_type == "openai":
            self._client = ChatOpenAI(
                model=model_name,
                api_key=api_key,
            )
        elif self.api_type == "nvidia":
            if not base_url:
                raise ValueError("base_url must be provided for 'nvidia' API type.")
            # Qwen3.5 (thinking ON): OpenAI SDK directly (reasoning_content/content split).
            self._qwen = (base_url, api_key, model_name)
            self._client = ChatOpenAI(model=model_name, api_key=api_key, base_url=base_url)
        else:
            raise ValueError(f"Unsupported api_type '{self.api_type}'.")

        self._parser = JsonOutputParser(pydantic_object=response_model)
        self._response_model = response_model

    def query_with_image(
        self,
        prompt: str,
        image_path: Union[str, Path],
        *,
        max_retries: int = 1
    ) -> BaseModel:
        """
        (prompt: str, image_path: Union[str, Path], max_retries: int=1) -> BaseModel: 
        Execute the pipeline with an image and parse the structured response.
        """
        if max_retries < 1:
            raise ValueError("max_retries must be >= 1.")

        image_path = Path(image_path)
        if not image_path.exists():
            raise FileNotFoundError(f"Image not found: {image_path}")

        # Read and encode image
        with open(image_path, "rb") as f:
            image_data = base64.b64encode(f.read()).decode("utf-8")

        # Determine image format
        suffix = image_path.suffix.lower()
        if suffix == ".png":
            image_format = "image/png"
        elif suffix in [".jpg", ".jpeg"]:
            image_format = "image/jpeg"
        else:
            raise ValueError(f"Unsupported image format: {suffix}")

        full_prompt = (
            f"{prompt}\n\n"
            f"Format your response as JSON matching this schema:\n"
            f"{_fmt(self._parser)}"
        )
        if getattr(self, "_qwen", None):
            msgs = [{"role": "user", "content": [
                {"type": "text", "text": full_prompt},
                {"type": "image_url",
                 "image_url": {"url": f"data:{image_format};base64,{image_data}"}}]}]
            return _qwen_structured(self._qwen, msgs, self._parser)

        for attempt in range(max_retries):
            try:
                # Build the message with image
                if self.api_type == "google":
                    # Google's format
                    message = HumanMessage(
                        content=[
                            {"type": "text", "text": full_prompt},
                            {
                                "type": "image_url",
                                "image_url": f"data:{image_format};base64,{image_data}",
                            },
                        ]
                    )
                else:
                    # OpenAI/NVIDIA format
                    message = HumanMessage(
                        content=[
                            {"type": "text", "text": full_prompt},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:{image_format};base64,{image_data}"
                                },
                            },
                        ]
                    )

                response = self._client.invoke([message])
                
                # Parse the response
                parsed = self._parser.parse(response.content)
                return parsed

            except Exception:
                if attempt + 1 == max_retries:
                    raise
                time.sleep(2**attempt)

    def query(self, prompt: str, *, max_retries: int = 1) -> BaseModel:
        """
        (prompt: str, max_retries: int=1) -> BaseModel: 
        Execute the pipeline without an image (text-only) and parse the structured response.
        """
        if max_retries < 1:
            raise ValueError("max_retries must be >= 1.")

        full_prompt = (
            f"{prompt}\n\n"
            f"Format your response as JSON matching this schema:\n"
            f"{_fmt(self._parser)}"
        )
        if getattr(self, "_qwen", None):
            return _qwen_structured(self._qwen,
                                    [{"role": "user", "content": full_prompt}],
                                    self._parser)

        for attempt in range(max_retries):
            try:
                message = HumanMessage(content=full_prompt)
                response = self._client.invoke([message])
                
                # Parse the response
                parsed = self._parser.parse(response.content)
                return parsed

            except Exception:
                if attempt + 1 == max_retries:
                    raise
                time.sleep(2**attempt)


__all__ = ["StructuredLLM", "StructuredMLLM"]
