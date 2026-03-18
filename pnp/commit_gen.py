"""
AI-powered git commit message generator via OpenRouter.

Environment:
    OPENROUTER_API_KEY  — required
"""

from typing import Optional
import subprocess
import logging
import os

import requests
import json


MODELS = [
    "qwen/qwen3-coder:free",
    "qwen/qwen3-next-80b-a3b-instruct:free",
    "arcee-ai/trinity-large-preview:free",
    "liquid/lfm-2.5-1.2b-thinking:free",
    "liquid/lfm-2.5-1.2b-instruct:free",
    "openrouter/hunter-alpha",
    "openrouter/healer-alpha",
    "nvidia/nemotron-3-super-120b-a12b:free",
    "nvidia/nemotron-3-nano-30b-a3b:free",
    "stepfun/step-3.5-flash:free",
]

API_BASE_URL    = f"https://openrouter.ai/api/v1"
API_KEY_ENV     = "OPENROUTER_API_KEY"
MAX_DIFF_CHARS  = 100000
MAX_TOKENS      = 10000
TEMPERATURE     = 0.2
TIMEOUT_SECONDS = 15

SYSTEM_PROMPT = (
    "You are a git commit message generator. You write "
    "commit messages in the style of a senior engineer: "
    "technical, dense, imperative mood, zero filler.\n"
    "\n"
    "Output ONLY the commit message — no explanation, no "
    "markdown, no code fences."
)

USER_PROMPT = (
    "Generate a git commit message for the diff below.\n"
    "\n"
    "Follow this exact format:\n"
    "  type(scope): headline\n"
    "  <blank line>\n"
    "  Section header:\n"
    "    - Bullet point\n"
    "    - Bullet point\n"
    "  <blank line>\n"
    "  Section header:\n"
    "    - Bullet point\n\n"

    "RULES:\n"
    "- Output ONLY the commit message. No explanation, no markdown, no code fences.\n"
    "- Subject line: type(scope): headline — always include scope, 72 chars max.\n"
    "- There MUST be a blank line between the subject and the body.\n"
    "- Scope: derive from the primary subsystem, module, or directory changed. Never omit it.\n"
    "- Headline: punchy, captures the dominant theme — not a list of everything changed.\n"
    "- Body: group related changes under plain-text section headers followed by a colon.\n"
    "- Each section header is a noun phrase describing the concern (e.g. 'Core changes:', 'Test coverage:').\n"
    "- Bullets are tight and technical. Use past tense for additions ('Added X'), imperative for directives.\n"
    "- Split into multiple sections when changes span distinct concerns (e.g. new feature vs. integration wiring vs. tests).\n"
    "- Housekeeping: ANY minor/incidental change (formatting, imports, whitespace, comments, indentation, blank lines) anywhere in the diff must be collapsed into ONE bullet: 'Minor formatting and import cleanup.' Never enumerate them individually, and never let them appear in substantive sections — move them to a Housekeeping section at the end.\n"
    "- Only include a body if there are multiple logical groups. Single-concern diffs: subject line only.\n"
    "- Do NOT pad. Do NOT summarize what is already obvious from the subject.\n"
    "- Valid types: feat, fix, refactor, chore, docs, test, style, perf\n\n"

    "EXAMPLE OUTPUT:\n"
    "feat(resolver): expand autopilot remediation coverage\n"
    "\n"
    "Core resolver expansion:\n"
    "  - Added classification and handler paths for line-ending normalization and large-file rejection\n"
    "  - Added protected-branch and detached HEAD resolution paths\n"
    "\n"
    "Policy changes:\n"
    "  - Wired create_gitattributes and renormalize_line_endings remediation actions\n"
    "  - Destructive paths remain policy-gated and disabled in auto-fix\n"
    "\n"
    "Housekeeping:\n"
    "  - Minor formatting and import cleanup\n"
    "\n"
    "WRONG — do NOT produce output like this:\n"
    "feat(pnp): add things\n"
    "\n"
    "Core changes:\n"
    "  - Added feature X\n"
    "  - Added feature Y\n"
    "  - Minor formatting and import cleanup\n"
    "\n"
    "Wrong because: (1) housekeeping bullet is inside a substantive section instead of its own Housekeeping section, "
    "(2) all changes collapsed into one generic section instead of split by concern.\n\n"
    "Diff:\n\n"
)

logger = logging.getLogger(__name__)

def _trim_diff(diff: str) -> str:
    """
    Truncate diff to MAX_DIFF_CHARS.
    Appends a notice so the model knows the diff was cut.
    """
    if len(diff) <= MAX_DIFF_CHARS: return diff
    return diff[:MAX_DIFF_CHARS] \
         + "\n\n[diff truncated for length]"


def _get_api_key() -> Optional[str]:
    key = os.environ.get(API_KEY_ENV)
    if not key:
        logger.error(
            "Missing API key. Set the %s environment variable.", API_KEY_ENV
        )
    return key


def _call_openrouter(diff: str) -> Optional[str]:
    """
    Call OpenRouter via httpx and return the raw response
    text. Reasoning is disabled — llm will just burn all
    tokens over-thinking.

    Returns None on any failure — caller decides how to
    handle.
    """
    api_key = _get_api_key()
    if not api_key: return None
    
    status = 0
    for model in MODELS:
        midx    = MODELS.index(model) + 1
        content = None
        try:
            response = requests.post(
                url=f"{API_BASE_URL}/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "pnp-tool",
                    "X-Title": "pnp-commit-generator",
                },
                data=json.dumps({
                    "model": model,
                    "messages": [
                        {
                            "role": "system",
                            "content": SYSTEM_PROMPT
                        },
                        {
                            "role": "user",
                            "content": USER_PROMPT + diff},
                    ],
                    "max_tokens": MAX_TOKENS,
                    "temperature": TEMPERATURE,
                    "reasoning": {"enabled": False},
                }),
                timeout=TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            message = response.json()["choices"][0]["message"]
            content = message.get("content")
            if not content:
                finish = response.json()["choices"][0].get("finish_reason", "unknown")
                logger.warning("OpenRouter returned empty content (finish_reason=%s). Reasoning was: %s", finish, message.get("reasoning", "")[:120])
                return None

            return content.strip()
    
        except requests.exceptions.Timeout:
            logger.warning("OpenRouter request timed out after %ss.", TIMEOUT_SECONDS)
        except requests.exceptions.HTTPError as e:
            status = e.response.status_code if e.response is not None else "?"
            logger.warning("OpenRouter HTTP error %s: %s", status, e)
            if status == 429:
                logger.warning("Rate limit hit — free tier is 20 RPM / 200 RPD.")
        except requests.exceptions.RequestException as e:
            logger.warning("OpenRouter connection failed: %s", e)
        except (KeyError, IndexError) as e:
            logger.warning("Unexpected OpenRouter response shape: %s", e)
    
        finally:
            if content: return content
            print(f"Model ({midx}/{len(MODELS)}): {model}\n")
            if status == 429: continue


def generate_commit_message(diff: str) -> Optional[str]:
    """
    Generate a conventional commit message from a git diff
    string.

    Args:
        diff: Raw output of `git diff --cached` or similar.

    Returns:
        A commit message string, or None if generation failed.
        Callers should fall back to a manual message on None.
    """
    if not diff or not diff.strip():
        logger.warning("Empty diff — nothing to generate a message from.")
        return None

    trimmed = _trim_diff(diff)
    message = _call_openrouter(trimmed)

    if message:
        # Sanitize: strip surrounding quotes some models add
        #           despite instructions
        message = message.strip('"').strip("'").strip()
        logger.debug("Generated commit message: %s", message)

    return message or None
