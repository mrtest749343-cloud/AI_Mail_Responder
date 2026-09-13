# answer_adapter.py - Fills placeholders in a selected template and optionally
#                   rephrases it via a lightweight AI API.
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# Starts deterministic (regex-based placeholder extraction & filling). If the
# user has provided an API key in data.json an optional LLM polish step is
# available but the code degrades gracefully if the call fails.

import re
import json
from utils import load_data, save_data


# ---------------------------------------------------------------------------
# Placeholder extraction & data pulling from the email body
# ---------------------------------------------------------------------------

def _find_placeholders(template):
    """Find all {placeholder} patterns in a template string.

    Uses a regex to locate every occurrence of curly-brace placeholders.
    Returns a set of placeholder names (without braces).

    Args:
        template (str): The template text that may contain placeholders.

    Returns:
        set[str]: Unique placeholder names, e.g. {"name", "order_number"}.
    """
    return set(re.findall(r"\{([^}]+)\}", template))


def _extract_sender_name(from_header):
    """Try to extract a sender's name from the "From" header.

    Handles formats like "John Doe" <john@example.com> or just the address.

    Args:
        from_header (str): The raw "From" header value.

    Returns:
        str: The extracted name, or "there" as a default.
    """
    m = re.match(r'"([^"]+)"', from_header)
    if m:
        return m.group(1)
    return "there"


def _extract_order_number(body):
    """Try to find an order number in the email body.

    Looks for common patterns like "Order #12345", "Order Number: ABC-678",
    or "order 98765". Returns the matched string or None.

    Args:
        body (str): The plain‑text body of the incoming email.

    Returns:
        str|None: The detected order number, or None if not found.
    """
    patterns = [
        r"order\s*#?\s*([A-Za-z0-9\-]+)",
        r"order[^A-Za-z]*number[^:]*[: ]?\s*([A-Za-z0-9\-]+)",
        r"\b#([0-9]{4,})\b",
    ]
    for pat in patterns:
        m = re.search(pat, body, re.IGNORECASE)
        if m:
            return m.group(1).strip()
    return None


def _extract_product_name(body):
    """Try to detect a product name from the email body.

    Looks for patterns like "product XYZ", "item: Z", etc. This is a simple
    heuristic; most of the time the placeholder will simply get a generic
    substitute.

    Args:
        body (str): The plain‑text body of the incoming email.

    Returns:
        str|None: Detected product name or None.
    """
    m = re.search(r"product\s+([A-Za-z0-9\-]+)", body, re.IGNORECASE)
    if m:
        return m.group(1)
    return None


# ---------------------------------------------------------------------------
# Core adaptation function
# ---------------------------------------------------------------------------

def adapt_template(template_dict, email_body, sender_name=None):
    """Adapt a selected template by filling placeholders with data from the
    email.

    1. Finds all ``{placeholders}`` in the template.
    2. For each placeholder, attempts to extract data from ``email_body``
       using dedicated heuristics (sender name, order number, product name).
    3. If a placeholder cannot be filled, replaces it with a generic phrase.
    4. (Optional) If an OpenAI/API key is configured in ``data.json``, send
       the filled template to the LLM for a final rephrase polish.
    5. Returns the fully adapted, ready‑to‑send reply body.

    The AI enhancement step is defensive: if the API call raises any exception
    (network error, quota exceeded, etc.) the function returns the manually
    filled template unchanged.

    Args:
        template_dict (dict): Template dict from ``answer_matcher``, must have
            a ``template`` key containing the raw template string.
        email_body (str): The plain‑text body of the incoming email.
        sender_name (str|None): The "From" header value; used to extract the
            sender's display name.

    Returns:
        str: The adapted reply body with all placeholders filled (and optionally
             rephrased). Returns the template unchanged if filling yields an
             empty string.
    """
    template_text = template_dict.get("template", "")
    if not template_text:
        return ""

    # 1. Find placeholders
    placeholders = _find_placeholders(template_text)

    # 2. Extract data from the email body
    data_map = {}

    # Sender name
    if sender_name:
        data_map["name"] = _extract_sender_name(sender_name)
    else:
        data_map["name"] = "there"

    # Order number
    order_num = _extract_order_number(email_body)
    if order_num:
        data_map["order_number"] = order_num
    else:
        # If no order number found, use a generic phrase per spec
        data_map["order_number"] = "your recent request"

    # Product name (optional heuristic)
    product = _extract_product_name(email_body)
    if product:
        data_map["product"] = product

    # 3. Fill placeholders
    filled = template_text
    for ph in placeholders:
        replacement = data_map.get(ph, "your recent request")
        # Replace all occurrences of {placeholder}
        filled = filled.replace("{" + ph + "}", replacement)

    # 4. Optional AI enhancement
    # Check if an API key is configured
    data = load_data()
    api_key = data.get("api_key", "")
    if api_key and api_key.strip():
        try:
            filled = _ai_rephrase(filled, api_key)
        except Exception:
            # On any failure fall back to the manually filled template
            pass

    return filled


def _ai_rephrase(reply_body, api_key):
    """Send the filled reply to an LLM for a professional polish.

    Currently supports OpenAI's Chat Completions API. The system prompt asks
    the model to rephrase while keeping all facts exactly as provided.

    Args:
        reply_body (str): The filled reply body (placeholders already resolved).
        api_key (str): The API key for the chosen LLM service.

    Returns:
        str: The rephrased reply body. If the API call fails for any reason,
             the original ``reply_body`` is returned unchanged.

    Note:
        This function currently uses OpenAI. To support other providers replace
        the request payload accordingly. The function raises any exception so
        the caller can catch it and fall back gracefully.
    """
    # Lazy import to keep import times fast if openai is not installed
    try:
        import openai  # type: ignore
    except Exception:
        # openai not installed – skip AI step
        return reply_body

    openai.api_key = api_key

    system_prompt = (
        "Rephrase the following professional email reply to sound natural and "
        "courteous, while keeping all facts exactly as provided. Do not invent "
        "new data, only improve flow and tone."
    )

    user_prompt = f"Reply body:\n{reply_body}\n\nRephrased reply:"

    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.7,
            max_tokens=500,
        )
        rephrased = response.choices[0].message.content.strip()
        if rephrased:
            return rephrased
    except Exception:
        pass

    return reply_body