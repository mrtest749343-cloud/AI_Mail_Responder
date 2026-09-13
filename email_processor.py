# email_processor.py - Handles IMAP fetch, SMTP send, and inbox processing.
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# Uses only Python standard library (imaplib, smtplib, email) plus regex.
# All external calls are wrapped in try/except with timeouts for robustness.

import os
import imaplib
import smtplib
import email
import email.header
import re
import socket
from datetime import datetime
from answer_matcher import get_best_template
from answer_adapter import adapt_template


# ---------------------------------------------------------------------------
# Configuration (read from environment)
# ---------------------------------------------------------------------------
IMAP_SERVER = os.getenv("IMAP_SERVER", "imap.gmail.com")
IMAP_USER = os.getenv("IMAP_USER", "")
IMAP_PASS = os.getenv("IMAP_PASS", "")

SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASS = os.getenv("SMTP_PASS", "")

socket.setdefaulttimeout(30)  # 30-second timeout for all socket operations


# ---------------------------------------------------------------------------
# IMAP helpers
# ---------------------------------------------------------------------------

def connect_imap():
    """Establish an IMAP over SSL connection and select the INBOX.

    Returns:
        imaplib.IMAP4_SSL: A connected IMAP instance positioned on INBOX.

    Raises:
        imaplib.IMAP4.error: If login or mailbox selection fails.
    """
    imap = imaplib.IMAP4_SSL(IMAP_SERVER)
    imap.login(IMAP_USER, IMAP_PASS)
    imap.select("INBOX")
    return imap


def fetch_unread(limit=20):
    """Fetch the most recent unread emails from the IMAP inbox.

    The function remains local-safe by failing closed: if the IMAP settings
    are not available, it returns an empty list instead of crashing. That
    makes the API usable on Vercel/serverless hosts where network credentials
    are provided through environment variables only.

    Args:
        limit (int): Maximum number of unread emails to return. Default 20.

    Returns:
        list[dict]: Each dict has keys: ``uid``, ``from_addr``, ``subject``,
                    ``date``, ``body`` (plain‑text snippet), and ``msg_id``.
    """
    if not IMAP_USER or not IMAP_PASS:
        print("IMAP credentials are not configured; fetch_unread returns an empty mailbox.")
        return []

    try:
        imap = connect_imap()
    except Exception as e:
        # Log and return empty list so the caller isn't crashed by auth errors
        print(f"IMAP connection error: {e}")
        return []

    # Search for UNSEEN emails
    status, messages = imap.search(None, "UNSEEN")
    if status != "OK" or not messages[0]:
        imap.logout()
        return []

    uids = messages[0].split()[:limit]

    results = []
    for uid in uids:
        uid = uid.decode() if isinstance(uid, bytes) else uid
        try:
            status, data = imap.fetch(uid, "(RFC822)")
            if status != "OK":
                continue
            raw_email = data[0][1]
            msg = email.message_from_bytes(raw_email)

            # Extract basic headers
            subject = _decode_header(msg["Subject"])
            frm = _decode_header(msg["From"])
            msg_id = msg.get("Message-ID", "")
            date_val = msg["Date"]

            # Extract plain‑text body
            body = _get_body(msg)

            results.append({
                "uid": uid,
                "from_addr": frm,
                "subject": subject,
                "date": date_val,
                "body": body,
                "msg_id": msg_id,
            })
        except Exception as e:
            print(f"Error fetching UID {uid}: {e}")
            continue

    imap.logout()
    # Sort by date descending (newest first)
    results.sort(key=lambda m: m.get("date", ""), reverse=True)
    return results


def _decode_header(header_value):
    """Decode an email header string to plain text.

    Args:
        header_value: The raw header value (may be bytes or str).

    Returns:
        str: The decoded, plain‑text header.
    """
    if not header_value:
        return ""
    try:
        decoded = email.header.decode_header(header_value)
        parts = []
        for piece, encoding in decoded:
            if isinstance(piece, bytes):
                if encoding:
                    parts.append(piece.decode(encoding, errors="replace"))
                else:
                    parts.append(piece.decode("utf-8", errors="replace"))
            else:
                parts.append(piece)
        return "".join(parts)
    except Exception:
        return str(header_value)


def _get_body(msg):
    """Extract the plain‑text body from an email message.

    Prefers ``text/plain`` parts. If only ``text/html`` is present, strips
    HTML tags with a regex to produce a best‑effort plain‑text snippet.

    Args:
        msg: An ``email.message_message`` object (parsed RFC822 email).

    Returns:
        str: The plain‑text body, or empty string if none found.
    """
    # Try text/plain first
    for part in msg.walk():
        content_type = part.get_content_type()
        if content_type == "text/plain":
            try:
                payload = part.get_payload(decode=True)
                if payload:
                    return payload.decode("utf-8", errors="replace").strip()
            except Exception:
                return ""
    # Fallback: if only HTML, strip tags
    for part in msg.walk():
        content_type = part.get_content_type()
        if content_type == "text/html":
            try:
                payload = part.get_payload(decode=True)
                if payload:
                    html = payload.decode("utf-8", errors="replace")
                    # Very simple tag stripping
                    text = re.sub(r"<[^>]+>", " ", html)
                    return re.sub(r"\s+", " ", text).strip()
            except Exception:
                return ""
    return ""


# ---------------------------------------------------------------------------
# SMTP helpers
# ---------------------------------------------------------------------------

def connect_smtp():
    """Create an SMTP connection with STARTTLS and log in.

    Returns:
        smtplib.SMTP: A connected and logged-in SMTP instance.

    Raises:
        smtplib.SMTPException: If connection or login fails.
    """
    if not SMTP_USER or not SMTP_PASS:
        raise RuntimeError("SMTP credentials are not configured.")

    if SMTP_PORT == 465:
        # Direct SSL
        smtp = smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT)
    else:
        smtp = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        smtp.starttls()
    smtp.login(SMTP_USER, SMTP_PASS)
    return smtp


def send_reply(to_addr, original_subject, reply_body, in_reply_to_uid, msg_id):
    """Send a reply email that is properly threaded to the original message.

    If SMTP credentials are not configured, the function fails safely and
    returns ``False``. On Vercel or other serverless runtimes, this avoids
    an unhandled internal error when the SMTP glue is not available.

    Args:
        to_addr (str): The recipient email address (the original sender).
        original_subject (str): The subject line of the original email
            (may be modified to add "Re:" if not already present).
        reply_body (str): The full body of the reply email.
        in_reply_to_uid (str): The IMAP UID of the original email (not directly
            used in the message but included for API consistency).
        msg_id (str): The ``Message-ID`` of the original email, used for
            ``References`` and ``In-Reply-To`` headers.

    Returns:
        bool: ``True`` if the email was sent successfully, ``False`` otherwise.
    """
    if not SMTP_USER or not SMTP_PASS:
        print("SMTP credentials are not configured; SMTP reply disabled.")
        return False

    try:
        smtp = connect_smtp()

        # Build the message - if subject already has Re:, keep it; otherwise prepend
        subject = original_subject.strip()
        if not subject.lower().startswith("re:"):
            subject = f"Re: {subject}"

        msg = f"""From: {SMTP_USER}
To: {to_addr}
Subject: {subject}
In-Reply-To: {msg_id}
References: {msg_id}

{reply_body}
"""

        smtp.sendmail(SMTP_USER, to_addr, msg)
        smtp.quit()
        return True
    except Exception as e:
        print(f"SMTP send error: {e}")
        return False


# ---------------------------------------------------------------------------
# Inbox processor - the main orchestrator
# ---------------------------------------------------------------------------

def process_inbox():
    """Main orchestrator: fetch unread, match templates, adapt, and reply.

    The flow for each unread email is:
      1. Call ``answer_matcher.get_best_template(body)`` to find the most
         relevant template based on keywords.
      2. If a template is found (or the fallback), call
         ``answer_adapter.adapt(template, body, sender_name)`` to fill
         placeholders and optionally rephrase via AI.
      3. If an adapted reply exists, send it via SMTP and mark the original
         as ``SEEN`` so it isn't reprocessed.
      4. Collect a summary report.

    Returns:
        dict: A summary with keys:
              - ``processed`` (int): number of emails examined.
              - ``replies_sent`` (int): number of replies actually sent.
              - ``details`` (list[str]): human‑readable notes per email.
    """
    mails = fetch_unread(limit=50)
    sent_count = 0
    details = []

    for mail in mails:
        body = mail.get("body", "")
        uid = mail.get("uid")
        frm = mail.get("from_addr", "")
        subject = mail.get("subject", "")
        msg_id = mail.get("msg_id", "")

        # 1. Match template
        template = get_best_template(body)

        # 2. Adapt template (fill placeholders, optional AI rephrase)
        if template:
            adapted = adapt_template(template, body, sender_name=frm)
        else:
            # No template matched – use a generic fallback
            adapted = adapt_template(
                {"id": 0, "template": "Thank you for your email. We will review and get back to you shortly."},
                body,
                sender_name=frm,
            )

        # 3. Send if we have a non‑empty reply
        if adapted and adapted.strip():
            # Extract the actual email address from the "From" header
            to_addr = _extract_email(frm)
            if send_reply(to_addr, subject, adapted, uid, msg_id):
                # Mark as seen so it won't be reprocessed
                try:
                    imap = connect_imap()
                    imap.store(uid, "+FLAGS", "\\Seen")
                    imap.logout()
                except Exception:
                    pass
                sent_count += 1
                details.append(f"Replied to UID {uid} ({frm})")
            else:
                details.append(f"Failed to send reply to UID {uid}")
        else:
            details.append(f"No reply generated for UID {uid}")

        # Mark as read even if we didn't send a reply (avoid reprocessing)
        try:
            imap = connect_imap()
            imap.store(uid, "+FLAGS", "\\Seen")
            imap.logout()
        except Exception:
            pass

    return {
        "processed": len(mails),
        "replies_sent": sent_count,
        "details": details,
    }


def _extract_email(from_header):
    """Extract the email address from a "From" header string.

    Handles formats like ``"John Doe" <john@example.com>`` or
    ``john@example.com`` alone.

    Args:
        from_header (str): The raw "From" header value.

    Returns:
        str: The parsed email address, or the whole string if parsing fails.
    """
    # Simple regex to grab an address enclosed in < >
    m = re.search(r"<([^>]+)>", from_header)
    if m:
        return m.group(1).strip()
    # Fallback: return the first token that looks like an email
    parts = from_header.split()
    for p in parts:
        if "@" in p:
            return p
    return from_header