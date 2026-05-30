import json
import logging
import time
from typing import Any

from sentinel.config import Settings

logger = logging.getLogger(__name__)

MODEL = "llama-3.3-70b-versatile"
RISK_SANITY_MAX_TOKENS = 48
RISK_SANITY_TIMEOUT_SEC = 0.85


async def complete(
    settings: Settings,
    system: str,
    user: str,
    max_tokens: int = 512,
) -> str:
    if not settings.groq_api_key:
        return _stub_response("groq", user)
    try:
        from groq import AsyncGroq

        client = AsyncGroq(api_key=settings.groq_api_key)
        response = await client.chat.completions.create(
            model=MODEL,
            max_tokens=max_tokens,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        return response.choices[0].message.content or ""
    except Exception as exc:
        logger.warning("Groq call failed: %s", exc)
        return _stub_response("groq", user, error=str(exc))


async def risk_sanity_check(
    settings: Settings,
    system: str,
    user: str,
) -> tuple[bool, str, float]:
    """
    Stream Groq response; abort early when APPROVE is detected.
    Returns (approved, reason, latency_ms).
    """
    if not settings.groq_api_key:
        return True, "groq_skipped_no_api_key", 0.0

    from groq import AsyncGroq

    client = AsyncGroq(api_key=settings.groq_api_key)
    started = time.perf_counter()
    buffer = ""

    try:
        stream = await client.chat.completions.create(
            model=MODEL,
            max_tokens=RISK_SANITY_MAX_TOKENS,
            temperature=0.1,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            stream=True,
        )
        async for chunk in stream:
            if time.perf_counter() - started > RISK_SANITY_TIMEOUT_SEC:
                logger.warning("Risk Groq sanity check timed out — default APPROVE")
                return True, "groq_timeout_default_approve", (time.perf_counter() - started) * 1000

            delta = chunk.choices[0].delta.content or ""
            if not delta:
                continue
            buffer += delta
            upper = buffer.upper().lstrip()

            if upper.startswith("APPROVE"):
                latency_ms = (time.perf_counter() - started) * 1000
                logger.info("Risk Groq early APPROVE latency_ms=%.1f", latency_ms)
                return True, "groq_approve", latency_ms

            if "REJECT:" in upper or upper.startswith("REJECT"):
                reason = _parse_reject_reason(buffer)
                latency_ms = (time.perf_counter() - started) * 1000
                logger.info("Risk Groq REJECT latency_ms=%.1f reason=%s", latency_ms, reason[:80])
                return False, reason, latency_ms

    except Exception as exc:
        logger.warning("Risk Groq stream failed: %s — default APPROVE", exc)
        return True, f"groq_error_default_approve: {exc}", (time.perf_counter() - started) * 1000

    latency_ms = (time.perf_counter() - started) * 1000
    approved = _interpret_final_buffer(buffer)
    reason = "groq_approve" if approved else _parse_reject_reason(buffer)
    return approved, reason, latency_ms


def _parse_reject_reason(text: str) -> str:
    upper = text.upper()
    if "REJECT:" in upper:
        idx = upper.index("REJECT:")
        return text[idx + len("REJECT:") :].strip().split("\n")[0][:300]
    if upper.strip().startswith("REJECT"):
        return text.strip()[6:].lstrip(": ").split("\n")[0][:300]
    return text.strip()[:300] or "groq_reject"


def _interpret_final_buffer(buffer: str) -> bool:
    upper = buffer.upper().strip()
    if not upper:
        return True
    if upper.startswith("APPROVE"):
        return True
    if "REJECT" in upper:
        return False
    return True


async def describe_event(settings: Settings, event: dict[str, Any]) -> str:
    """One-sentence dashboard description for a detected market event."""
    system = (
        "You are the Watcher for iAgent Autopilot. "
        "Write exactly one concise sentence describing this market event for a trading dashboard. "
        "No JSON, no bullet points."
    )
    user = f"Event:\n{json.dumps(event, indent=2, default=str)}"
    raw = await complete(settings, system, user, max_tokens=80)
    text = raw.strip()
    if text.startswith("{") or "[groq stub]" in text:
        raise ValueError("invalid groq response")
    return text.split("\n")[0].strip()


async def watch_signal(settings: Settings, event: dict[str, Any]) -> dict[str, Any]:
    system = (
        "You are the Watcher agent. Flag notable market events. "
        "Respond with JSON: {alert, severity, summary}."
    )
    user = f"Market event:\n{json.dumps(event, indent=2)}"
    raw = await complete(settings, system, user)
    return _parse_json_or_default(
        raw,
        {"alert": False, "severity": "info", "summary": raw[:300]},
    )


def _stub_response(provider: str, user: str, error: str | None = None) -> str:
    payload = {
        "alert": False,
        "severity": "info",
        "summary": f"[{provider} stub] No API key configured.",
        "error": error,
        "input_preview": user[:200],
    }
    return json.dumps(payload)


def _parse_json_or_default(raw: str, default: dict[str, Any]) -> dict[str, Any]:
    text = raw.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1] if len(lines) > 2 else lines)
    try:
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            return json.loads(text[start:end])
        return json.loads(text)
    except json.JSONDecodeError:
        return default
