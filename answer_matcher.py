# answer_matcher.py - Selects the best template based on keyword scoring.
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# Implements a weighted keyword matching system. Fast, deterministic, no
# external API calls required for the core matching logic.

import json
from utils import load_data


def get_best_template(email_body):
    """Select the best-matching answer template for the given email body.

    Iterates over all stored answer templates (stored in ``data.json``) and
    computes a keyword match score for each. The score is the count of
    ``keywords`` from the template that appear in ``email_body`` (case‑insensitive).

    If at least one template has a score > 0, the one with the highest score
    is returned. Ties are broken by selecting the first template with that score.
    If no template scores above 0, a configurable fallback template is returned.

    The fallback template is defined within this module and can be customised
    without altering the data file.

    Args:
        email_body (str): The plain‑text body of the incoming email.

    Returns:
        dict: A template dictionary with at least the keys ``id`` and ``template``.
              Example: ``{"id": 3, "template": "Your order {order_number} is ..."}``.
    """
    data = load_data()
    answers = data.get("answers", [])

    body_lower = email_body.lower()
    best_score = 0
    best_template = None

    for ans in answers:
        keywords = [k.strip().lower() for k in ans.get("keywords", [])]
        if not keywords:
            continue
        # Count how many keywords appear in the body
        score = sum(1 for k in keywords if k in body_lower)
        if score > best_score:
            best_score = score
            best_template = ans

    if best_template is not None and best_score > 0:
        return best_template

    # No matching template – return fallback
    return {"id": 0, "template": FALLBACK_TEMPLATE}


#: Default fallback template used when no keywords match.
FALLBACK_TEMPLATE = (
    "Thank you for your email. We will review your request and get back to you shortly."
)