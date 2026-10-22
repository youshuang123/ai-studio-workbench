"""Generic HTTP provider adapter.

Every vendor has a different payload/response shape. This adapter covers the
common case: POST JSON, receive an image URL or text. For real vendors, subclass
this and override `build_payload` / `parse_response`.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

import httpx

from studio.models import GenerationRequest, GenerationResult
from studio.providers.base import Provider


class HTTPProvider(Provider):
    def __init__(self, name: str, config: dict[str, Any]):
        super().__init__(name, config.get("models") or {})
        self.base_url = str(config.get("base_url", "")).rstrip("/")
        self.endpoint = str(config.get("endpoint", "/v1/generate"))
        self.api_key_env = config.get("api_key_env")
        self.timeout = float(config.get("timeout_seconds", 120))
        self.extra_headers = config.get("headers") or {}
        self.response_type = config.get("response_type", "image_url")

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json", **self.extra_headers}
        if self.api_key_env:
            key = os.getenv(self.api_key_env, "")
            if key:
                headers.setdefault("Authorization", f"Bearer {key}")
        return headers

    def build_payload(self, model: str, request: GenerationRequest) -> dict[str, Any]:
        payload = {
            "model": model,
            "prompt": request.prompt,
            "width": request.width,
            "height": request.height,
            "metadata": request.metadata,
        }
        if request.seed is not None:
            payload["seed"] = request.seed
        if request.reference_images:
            payload["reference_images"] = request.reference_images
        if request.duration_seconds:
            payload["duration_seconds"] = request.duration_seconds
        return payload

    def generate(self, model: str, request: GenerationRequest, output_dir: Path) -> GenerationResult:
        if not self.base_url:
            raise ValueError(f"provider {self.name} missing base_url")
        started = time.time()
        url = f"{self.base_url}{self.endpoint}"
        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(url, json=self.build_payload(model, request), headers=self._headers())
            response.raise_for_status()
            data = response.json()

            output_dir.mkdir(parents=True, exist_ok=True)
            if self.response_type == "image_url":
                image_url = data.get("image_url") or data.get("url")
                if not image_url:
                    raise ValueError(f"provider {self.name} response missing image_url")
                image = client.get(image_url)
                image.raise_for_status()
                suffix = ".png"
                if "." in image_url.rsplit("/", 1)[-1]:
                    suffix = "." + image_url.rsplit(".", 1)[-1].split("?")[0]
                path = output_dir / f"{self.name}_{model}_{int(started)}.{suffix.lstrip('.')}"
                path.write_bytes(image.content)
            elif self.response_type == "text":
                text = data.get("text") or data.get("content") or ""
                path = output_dir / f"{self.name}_{model}_{int(started)}.json"
                path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            else:
                path = output_dir / f"{self.name}_{model}_{int(started)}.json"
                path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

        latency_ms = int((time.time() - started) * 1000)
        return GenerationResult(
            provider=self.name,
            model=model,
            task=request.task,
            output_path=str(path),
            cost=0.0,
            latency_ms=latency_ms,
            metadata={"response": data if isinstance(data, dict) else {}},
        )
