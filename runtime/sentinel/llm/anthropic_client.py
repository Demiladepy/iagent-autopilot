import json
import logging
import time
from typing import Any

from pydantic import ValidationError

from sentinel.config import Settings
from sentinel.schemas import ProposalOutput

logger = logging.getLogger(__name__)

MODEL = "claude-sonnet-4-5"
HAIKU_MODEL = "claude-haiku-4-5"

STRATEGY_PARSE_SYSTEM = """You parse natural-language trading strategies into structured limits. Output ONLY JSON matching:
{
  "text": "<the user's original text, cleaned up>",
  "max_notional_usd": number,
  "max_leverage": number,
  "max_daily_loss_usd": number,
  "allowed_markets": ["BTC", "ETH", "INJ", ...]
}

Be conservative on defaults: if unspecified, max_notional=50, max_leverage=2, max_daily_loss=25, allowed_markets=["BTC","ETH","INJ"]."""


class AnthropicCallResult:
    def __init__(
        self,
        *,
        parsed: ProposalOutput,
        latency_ms: float,
        input_tokens: int,
        output_tokens: int,
        raw_text: str,
    ) -> None:
        self.parsed = parsed
        self.latency_ms = latency_ms
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.raw_text = raw_text


async def generate_proposal(
    settings: Settings,
    system: str,
    user: str,
    *,
    retry_hint: str | None = None,
) -> AnthropicCallResult:
    """Call Claude with JSON schema output; validate as ProposalOutput."""
    if not settings.anthropic_api_key:
        return _stub_proposal_result(user)

    import anthropic

    messages: list[dict[str, str]] = [{"role": "user", "content": user}]
    if retry_hint:
        messages.append({"role": "user", "content": retry_hint})

    schema = ProposalOutput.model_json_schema()
    # Anthropic strict JSON schema requires additionalProperties: false on objects
    schema.setdefault("additionalProperties", False)

    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    started = time.perf_counter()
    try:
        message = await client.messages.create(
            model=MODEL,
            max_tokens=1024,
            temperature=0.3,
            system=system,
            messages=messages,
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "proposal",
                    "strict": True,
                    "schema": schema,
                },
            },
        )
    except Exception as exc:
        logger.warning("Anthropic proposal call failed: %s", exc)
        return _stub_proposal_result(user, error=str(exc))

    latency_ms = (time.perf_counter() - started) * 1000
    blocks = [b.text for b in message.content if hasattr(b, "text")]
    raw_text = "\n".join(blocks)
    usage = getattr(message, "usage", None)
    input_tokens = int(getattr(usage, "input_tokens", 0) or 0)
    output_tokens = int(getattr(usage, "output_tokens", 0) or 0)

    parsed = _parse_proposal_output(raw_text)
    logger.info(
        "Analyst Claude call latency_ms=%.1f input_tokens=%d output_tokens=%d",
        latency_ms,
        input_tokens,
        output_tokens,
    )
    return AnthropicCallResult(
        parsed=parsed,
        latency_ms=latency_ms,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        raw_text=raw_text,
    )


def _parse_proposal_output(raw: str) -> ProposalOutput:
    text = raw.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1] if len(lines) > 2 else lines)
    start = text.find("{")
    end = text.rfind("}") + 1
    if start >= 0 and end > start:
        text = text[start:end]
    data = json.loads(text)
    return ProposalOutput.model_validate(data)


def _stub_proposal_result(user: str, error: str | None = None) -> AnthropicCallResult:
    parsed = ProposalOutput(
        action="none",
        market=None,
        side=None,
        notional_usd=None,
        leverage=None,
        reasoning=(
            f"[anthropic stub] No API key configured. Event not analyzed."
            + (f" Error: {error}" if error else "")
        ),
        confidence=0.0,
        expected_hold_hours=None,
        invalidation=None,
    )
    return AnthropicCallResult(
        parsed=parsed,
        latency_ms=0.0,
        input_tokens=0,
        output_tokens=0,
        raw_text=parsed.model_dump_json(),
    )


async def complete(
    settings: Settings,
    system: str,
    user: str,
    max_tokens: int = 1024,
) -> str:
    if not settings.anthropic_api_key:
        return _stub_response("anthropic", user)
    try:
        import anthropic

        client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        message = await client.messages.create(
            model=MODEL,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        blocks = [b.text for b in message.content if hasattr(b, "text")]
        return "\n".join(blocks)
    except Exception as exc:
        logger.warning("Anthropic call failed: %s", exc)
        return _stub_response("anthropic", user, error=str(exc))


async def parse_strategy_text(settings: Settings, user_text: str) -> dict[str, Any]:
    """Parse natural-language strategy into structured limits (Claude Haiku)."""
    defaults = {
        "text": user_text.strip(),
        "max_notional_usd": 50.0,
        "max_leverage": 2.0,
        "max_daily_loss_usd": 25.0,
        "allowed_markets": ["BTC", "ETH", "INJ"],
    }
    if not settings.anthropic_api_key:
        return {**defaults, "parsed": False, "note": "anthropic_api_key missing — defaults applied"}

    import anthropic

    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    try:
        message = await client.messages.create(
            model=HAIKU_MODEL,
            max_tokens=512,
            temperature=0.0,
            system=STRATEGY_PARSE_SYSTEM,
            messages=[{"role": "user", "content": user_text}],
            response_format={"type": "json_object"},
        )
        blocks = [b.text for b in message.content if hasattr(b, "text")]
        raw = "\n".join(blocks)
        data = json.loads(raw)
        return {
            "text": data.get("text", defaults["text"]),
            "max_notional_usd": float(data.get("max_notional_usd", defaults["max_notional_usd"])),
            "max_leverage": float(data.get("max_leverage", defaults["max_leverage"])),
            "max_daily_loss_usd": float(
                data.get("max_daily_loss_usd", defaults["max_daily_loss_usd"])
            ),
            "allowed_markets": list(
                data.get("allowed_markets", defaults["allowed_markets"])
            ),
            "parsed": True,
        }
    except Exception as exc:
        logger.warning("Strategy parse failed: %s", exc)
        return {**defaults, "parsed": False, "error": str(exc)}


class AuditExplanationResult:
    def __init__(
        self,
        *,
        summary: str,
        flags: list[str],
        latency_ms: float,
        input_tokens: int,
        output_tokens: int,
        raw_text: str,
    ) -> None:
        self.summary = summary
        self.flags = flags
        self.latency_ms = latency_ms
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.raw_text = raw_text


async def explain_execution(
    settings: Settings,
    system: str,
    user: str,
    *,
    on_text_delta: Any = None,
    temperature: float = 0.5,
) -> AuditExplanationResult:
    """Stream Claude audit narrative; optional async callback per text delta."""
    if not settings.anthropic_api_key:
        stub = _stub_audit_text(user)
        if on_text_delta:
            await on_text_delta(stub)
        summary, flags = _split_summary_and_flags(stub)
        return AuditExplanationResult(
            summary=summary,
            flags=flags,
            latency_ms=0.0,
            input_tokens=0,
            output_tokens=0,
            raw_text=stub,
        )

    import anthropic

    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    started = time.perf_counter()
    accumulated = ""
    input_tokens = 0
    output_tokens = 0

    try:
        async with client.messages.stream(
            model=MODEL,
            max_tokens=1024,
            temperature=temperature,
            system=system,
            messages=[{"role": "user", "content": user}],
        ) as stream:
            async for event in stream:
                if event.type == "content_block_delta":
                    delta = getattr(event.delta, "text", "") or ""
                    if delta:
                        accumulated += delta
                        if on_text_delta:
                            await on_text_delta(accumulated)
                elif event.type == "message_stop":
                    final = await stream.get_final_message()
                    usage = getattr(final, "usage", None)
                    input_tokens = int(getattr(usage, "input_tokens", 0) or 0)
                    output_tokens = int(getattr(usage, "output_tokens", 0) or 0)
    except Exception as exc:
        logger.warning("Anthropic audit stream failed: %s", exc)
        accumulated = _stub_audit_text(user, error=str(exc))
        if on_text_delta:
            await on_text_delta(accumulated)

    latency_ms = (time.perf_counter() - started) * 1000
    summary, flags = _split_summary_and_flags(accumulated)
    logger.info(
        "Auditor Claude call latency_ms=%.1f input_tokens=%d output_tokens=%d",
        latency_ms,
        input_tokens,
        output_tokens,
    )
    return AuditExplanationResult(
        summary=summary,
        flags=flags,
        latency_ms=latency_ms,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        raw_text=accumulated,
    )


def _stub_audit_text(user: str, error: str | None = None) -> str:
    msg = (
        "No Anthropic API key configured; audit unavailable. "
        "Configure ANTHROPIC_API_KEY to enable post-trade explanations."
    )
    if error:
        msg += f" ({error})"
    return f"{msg}\n{{\"flags\": []}}"


def _split_summary_and_flags(raw: str) -> tuple[str, list[str]]:
    lines = raw.strip().split("\n")
    flags: list[str] = []
    json_line: str | None = None

    for line in reversed(lines):
        stripped = line.strip()
        if stripped.startswith("{") and "flags" in stripped:
            json_line = stripped
            break

    if json_line:
        try:
            parsed = json.loads(json_line)
            raw_flags = parsed.get("flags", [])
            if isinstance(raw_flags, list):
                flags = [str(f) for f in raw_flags]
        except json.JSONDecodeError:
            pass
        cut = raw.rfind(json_line)
        summary = raw[:cut].strip() if cut >= 0 else raw.strip()
    else:
        summary = raw.strip()
        start = summary.find("{")
        end = summary.rfind("}") + 1
        if start >= 0 and end > start and "flags" in summary[start:end]:
            try:
                parsed = json.loads(summary[start:end])
                flags = list(parsed.get("flags", []))
                summary = (summary[:start] + summary[end:]).strip()
            except json.JSONDecodeError:
                pass

    return summary or raw.strip(), flags


def _stub_response(provider: str, user: str, error: str | None = None) -> str:
    payload = {
        "action": "none",
        "confidence": 0.4,
        "rationale": f"[{provider} stub] No API key configured.",
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
