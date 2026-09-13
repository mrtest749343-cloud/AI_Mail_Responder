# app.py - Main Flask Application
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# Routes, sessions, and HTML rendering for the AI Email Responder.
# Follows PEP8, uses Werkzeug for password hashing, Flask sessions for auth.

import os
import json
import hmac
from datetime import datetime
from flask import Flask, render_template, redirect, url_for, request, session, jsonify
from utils import (
    load_data,
    save_data,
    verify_login,
    login_required,
    is_locked_out,
    register_failed_login,
    reset_login_attempts,
)

# Load trigger token from data.json (set at init) for the /trigger_poll endpoint
DATA = load_data()
TRIGGER_TOKEN = DATA.get("trigger_token", "change-this-dev-token")

# ---------------------------------------------------------------------------
# App configuration
# ---------------------------------------------------------------------------
def create_app():
    app = Flask(__name__)
    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-change-me")
    app.config["DATA_PATH"] = os.path.join(app.root_path, "data", "data.json")

    # Session cookie hardening: not readable from JS, not sent cross-site,
    # and HTTPS-only once deployed (set SESSION_COOKIE_SECURE=false locally
    # over plain http, e.g. via an env var, if needed for local testing).
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["SESSION_COOKIE_SECURE"] = os.getenv("SESSION_COOKIE_SECURE", "true").lower() == "true"
    app.config["PERMANENT_SESSION_LIFETIME"] = 60 * 60 * 8  # 8h

    @app.after_request
    def set_security_headers(response):
        """Attach baseline security headers to every response.

        These reduce common attack surface (clickjacking, MIME sniffing,
        referrer leakage) at near-zero cost, which fits the "lightweight"
        constraint of the project.
        """
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "same-origin"
        return response

    # -----------------------------------------------------------------------
    # Public routes (no login required)
    # -----------------------------------------------------------------------

    @app.route("/")
    def welcome():
        return render_template("welcome.html")

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "POST":
            ip = request.remote_addr or "unknown"
            if is_locked_out(ip):
                return render_template(
                    "login.html",
                    error="Trop de tentatives. Réessayez dans quelques minutes.",
                )
            username = request.form.get("username", "").strip()
            password = request.form.get("password", "").strip()
            if verify_login(username, password):
                reset_login_attempts(ip)
                session.clear()
                session["user_id"] = username
                return redirect(url_for("dashboard"))
            register_failed_login(ip)
            return render_template("login.html", error="Identifiant ou mot de passe invalide")
        return render_template("login.html", error=None)

    @app.route("/logout")
    def logout():
        session.clear()
        return redirect(url_for("login"))

    # -----------------------------------------------------------------------
    # Authenticated routes (session required)
    # -----------------------------------------------------------------------

    @app.route("/dashboard")
    @login_required
    def dashboard():
        return render_template("dashboard.html")

    # -----------------------------------------------------------------------
    # REST API endpoints
    # -----------------------------------------------------------------------

    @app.route("/api/login", methods=["POST"])
    def api_login():
        ip = request.remote_addr or "unknown"
        if is_locked_out(ip):
            return jsonify({"success": False, "error": "Too many attempts, try again later"}), 429
        data = request.get_json(silent=True)
        if not data:
            data = request.form.to_dict()
        if not data:
            return jsonify({"error": "No data provided"}), 400
        username = str(data.get("username", "")).strip()
        password = str(data.get("password", "")).strip()
        if verify_login(username, password):
            reset_login_attempts(ip)
            session.clear()
            session["user_id"] = username
            return jsonify({"success": True})
        register_failed_login(ip)
        return jsonify({"success": False, "error": "Invalid credentials"}), 401

    @app.route("/api/mails", methods=["GET"])
    @login_required
    def api_mails():
        from email_processor import fetch_unread
        mails = fetch_unread(limit=20)
        return jsonify(mails)

    @app.route("/api/answers", methods=["GET"])
    @login_required
    def api_answers():
        data = load_data()
        return jsonify(data.get("answers", []))

    @app.route("/api/answers", methods=["POST"])
    @login_required
    def api_answers_add():
        data = request.get_json(silent=True)
        if not data:
            data = request.form.to_dict()
        if not data:
            return jsonify({"error": "No data"}), 400
        existing = load_data()
        answers = existing.get("answers", [])
        new_id = max([a.get("id", 0) for a in answers], default=0) + 1
        new_answer = {
            "id": new_id,
            "keywords": data.get("keywords", []),
            "template": data.get("template", ""),
        }
        if isinstance(new_answer["keywords"], str):
            new_answer["keywords"] = [item.strip() for item in new_answer["keywords"].split(",") if item.strip()]
        answers.append(new_answer)
        existing["answers"] = answers
        save_data(existing)
        return jsonify({"success": True, "answer": new_answer})

    @app.route("/api/answers/<int:answer_id>", methods=["PUT"])
    @login_required
    def api_answers_update(answer_id):
        data = request.get_json(silent=True)
        if not data:
            data = request.form.to_dict()
        if not data:
            return jsonify({"error": "No data"}), 400
        existing = load_data()
        answers = existing.get("answers", [])
        for a in answers:
            if a["id"] == answer_id:
                a["keywords"] = data.get("keywords", a["keywords"])
                a["template"] = data.get("template", a["template"])
                if isinstance(a["keywords"], str):
                    a["keywords"] = [item.strip() for item in a["keywords"].split(",") if item.strip()]
                break
        existing["answers"] = answers
        save_data(existing)
        return jsonify({"success": True})

    @app.route("/api/answers/<int:answer_id>", methods=["DELETE"])
    @login_required
    def api_answers_delete(answer_id):
        existing = load_data()
        answers = existing.get("answers", [])
        answers = [a for a in answers if a["id"] != answer_id]
        existing["answers"] = answers
        save_data(existing)
        return jsonify({"success": True})

    @app.route("/api/process", methods=["POST"])
    @login_required
    def api_process():
        from email_processor import process_inbox
        result = process_inbox()
        return jsonify(result)

    # -----------------------------------------------------------------------
    # Trigger poll - public but token-protected (for cron jobs)
    # -----------------------------------------------------------------------

    @app.route("/trigger_poll")
    def trigger_poll():
        token = request.args.get("token", "")
        # Constant-time comparison to avoid leaking the token via timing.
        if not hmac.compare_digest(token, TRIGGER_TOKEN):
            return jsonify({"error": "Invalid token"}), 403
        from email_processor import process_inbox
        result = process_inbox()
        return jsonify(result)

    return app


app = create_app()

# ---------------------------------------------------------------------------
# Entry point when running directly
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)