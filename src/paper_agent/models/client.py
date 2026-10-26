"""Small OpenAI Responses client. No papers or profiles are loaded here."""

import json
import os
import time
import tomllib
from datetime import datetime, timezone
from pathlib import Path
from paper_agent.paths import project_root


ROOT = project_root()
SMOKE_PROMPT = "请仅回复：连接成功。"


class ModelError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def load_settings(config=None):
    path = Path(config) if config else ROOT / "config" / "model.toml"
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        raise ModelError("invalid_model_config", f"Cannot read model configuration: {path.name}.") from None
    if set(data) - {"model", "reasoning_effort", "max_output_tokens", "timeout_seconds"}:
        raise ModelError("invalid_model_config", "Unknown model settings. Keep credentials only in config/.env.local.")
    if not isinstance(data.get("model"), str) or not data["model"].strip():
        raise ModelError("invalid_model_config", "Model name must be a nonempty string.")
    if data.get("reasoning_effort") not in ("low", "medium", "high"):
        raise ModelError("invalid_model_config", "Choose reasoning_effort low, medium or high.")
    if type(data.get("max_output_tokens")) is not int or not 1 <= data["max_output_tokens"] <= 16384:
        raise ModelError("invalid_model_config", "max_output_tokens must be between 1 and 16384.")
    if type(data.get("timeout_seconds")) not in (int, float) or not 0 < data["timeout_seconds"] <= 300:
        raise ModelError("invalid_model_config", "timeout_seconds must be between 0 and 300.")
    return data


def load_api_key(env_file=None):
    try:
        from dotenv import dotenv_values
    except ImportError:
        raise ModelError("dependency_missing", "Install the models extra in the project environment.") from None
    path = Path(env_file) if env_file else ROOT / "config" / ".env.local"
    # Project key wins over a possibly unrelated shell key. Never echo either.
    values = dotenv_values(path, encoding="utf-8-sig", interpolate=False) if path.exists() else {}
    key = (values.get("OPENAI_API_KEY") or os.environ.get("OPENAI_API_KEY", "")).strip()
    if not key or key in ("YOUR_API_KEY", "your_api_key_here"):
        raise ModelError("missing_api_key", "Fill OPENAI_API_KEY in config/.env.local, then retry.")
    return key


def _append_usage(record, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(record, ensure_ascii=False) + "\n")


def generate_text(prompt, instructions, *, config=None, env_file=None, usage_path=None, json_schema=None, tools=None):
    settings = load_settings(config)
    key = load_api_key(env_file)
    if not ((isinstance(prompt, str) and prompt.strip()) or (tools is not None and isinstance(prompt, list) and prompt)):
        raise ModelError("invalid_input", "Prompt must be nonempty text.")
    try:
        from openai import OpenAI, APIError, APIConnectionError, APIStatusError, APITimeoutError
    except ImportError:
        raise ModelError("dependency_missing", "Install the models extra in the project environment.") from None
    started = time.monotonic()
    record = {"created_at": datetime.now(timezone.utc).isoformat(), "model_requested": settings["model"]}
    try:
        # Ignore ambient OPENAI_BASE_URL so a key cannot accidentally go to another provider.
        with OpenAI(api_key=key, base_url="https://api.openai.com/v1",
                    timeout=settings["timeout_seconds"], max_retries=0) as client:
            output_options = {}
            if tools is not None:
                output_options.update(tools=tools, parallel_tool_calls=False, include=["reasoning.encrypted_content"])
            if json_schema is not None:
                output_options["text"] = {"format": {"type": "json_schema", "name": "structured_result",
                                                     "strict": True, "schema": json_schema}}
            response = client.responses.create(
                model=settings["model"], instructions=instructions, input=prompt,
                reasoning={"effort": settings["reasoning_effort"]},
                max_output_tokens=settings["max_output_tokens"], store=False, **output_options,
            )
        usage = response.usage.model_dump() if response.usage else None
        record.update(response_id=response.id, model_returned=response.model,
                      status=response.status, usage=usage)
        text = response.output_text or ""
        result = {"text": text, "model": response.model, "status": response.status,
                  "response_id": response.id, "usage": usage}
        if tools is not None:
            result["output"] = [item.model_dump(mode="json", exclude_none=True) for item in response.output]
        if response.status != "completed":
            result["warning"] = "Response is incomplete; inspect output limits or provider status before retrying."
        elif not text.strip() and not any(item.get("type") == "function_call" for item in result.get("output", [])):
            result["warning"] = "No text returned; the model may have refused or produced no visible answer."
    except APITimeoutError:
        record.update(status="error", error_code="timeout")
        raise ModelError("timeout", "Request timed out. No automatic retry; provider processing or charges may still have occurred.") from None
    except APIConnectionError:
        record.update(status="error", error_code="connection_error")
        raise ModelError("connection_error", "Cannot reach the OpenAI API. Check local network settings; request was not automatically retried.") from None
    except APIStatusError as exc:
        code = {401: "authentication_failed", 403: "access_denied", 404: "model_or_endpoint_not_found",
                429: "rate_or_quota_limit"}.get(exc.status_code, "api_error")
        record.update(status="error", error_code=code, http_status=exc.status_code)
        raise ModelError(code, f"OpenAI returned HTTP {exc.status_code}. Check key, model access, billing or usage limits in the dashboard.") from None
    except APIError:
        record.update(status="error", error_code="sdk_error")
        raise ModelError("sdk_error", "OpenAI SDK could not complete or validate the response. No automatic retry.") from None
    finally:
        record["elapsed_seconds"] = round(time.monotonic() - started, 3)
        try:
            _append_usage(record, usage_path or ROOT / "data" / "logs" / "model-usage.jsonl")
        except OSError:
            # Do not mask a potentially billed successful call and invite a retry.
            if "result" in locals():
                result["usage_log_warning"] = "Call finished, but the local usage log could not be written. Do not repeat merely to restore logging."
    return result


def smoke_test(**kwargs):
    return generate_text(SMOKE_PROMPT, "这是 API 连通性测试。不要调用工具，只输出要求的短句。", **kwargs)
