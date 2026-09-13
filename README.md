# AI Email Responder

A lightweight Flask-based email response automation project that reads unread emails, chooses the best matching answer template, adapts the message to the specific email, and sends a professional reply through an SMTP account.

The project includes a password-protected dashboard for reviewing incoming mail and maintaining the answer base stored in a local JSON file.

## Overview

This project is designed as a small, self-contained email automation workflow:

1. A scheduled request or manual trigger calls the Flask app.
2. The backend connects to an IMAP inbox and fetches unread messages.
3. An answer matcher scores available templates against the incoming email text.
4. A dedicated adapter step fills or personalizes the selected template.
5. The final reply is sent through SMTP.
6. Users manage templates and monitor activity through the dashboard.

## Features

- Password-protected Flask dashboard
- Login and session management using Flask sessions and Werkzeug password hashing
- JSON-backed answer storage and user configuration
- Email inbox polling via IMAP
- Template matching through a keyword scoring strategy
- Placeholder adaptation and optional text refinement flow
- Template CRUD endpoints for adding, updating, and deleting answer definitions
- Lightweight static HTML, CSS, and JavaScript frontend

## Project Structure

```text
project-root/
├── app.py                 # Flask routes, sessions, and API endpoints
├── email_processor.py     # IMAP/SMTP email fetch and send logic
├── answer_matcher.py      # Keyword-based answer template selection
├── answer_adapter.py      # Template adaptation and placeholder handling
├── utils.py               # JSON helpers, password verification, and auth guard
├── init_db.py             # Creates the initial data.json configuration
├── requirements.txt       # Python dependencies
├── vercel.json            # Vercel routing configuration
├── data/
│   └── data.json          # JSON data source for user account and answer templates
├── static/
│   ├── css/
│   └── js/
└── templates/
    ├── base.html
    ├── login.html
    ├── welcome.html
    └── dashboard.html
```

## Local Setup

1. Create and activate a Python virtual environment:

```bash
python -m venv venv
source venv/bin/activate   # Linux/macOS
venv\Scripts\activate     # Windows
```

2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Create the local configuration data file:

```bash
python init_db.py
```

This bootstrap step writes the initial JSON structure and stores the admin password as a salted hash instead of plain text.

4. Configure your environment variables in a local environment file or hosting environment:

- `SECRET_KEY`
- `IMAP_*` server settings
- `SMTP_*` server settings
- `TRIGGER_TOKEN`

5. Run the Flask app locally:

```bash
flask run
```

## Security Notes

- Passwords are not stored in plaintext. The project follows the recommended pattern of hashing the password before saving it in the JSON configuration file.
- The trigger endpoint uses a secret token, compared in constant time, and should not be exposed publicly without it.
- Login attempts are rate-limited per IP (5 failures → 5 minute lockout) to slow down credential stuffing.
- Session cookies are `HttpOnly`, `SameSite=Lax`, and `Secure` in production, with a secure secret key.
- Baseline security headers (`X-Frame-Options`, `X-Content-Type-Options`, `Referrer-Policy`) are set on every response.

See [`Documentation.md`](./Documentation.md) for the full project map, local setup, Vercel deployment steps, and additional protection options (WAF, 2FA, CAPTCHA).

## API Flow

The application exposes the following main request paths:

- `/` – public landing page
- `/login` – login page
- `/dashboard` – protected dashboard page
- `/api/login` – authentication endpoint
- `/api/mails` – fetch unread messages
- `/api/answers` – template read/write endpoint
- `/api/process` – process mailbox
- `/trigger_poll` – token-protected processing endpoint

## Deployment

The repository includes a Vercel configuration file for a serverless deployment pattern. A cron or external scheduler can call the protected trigger route on a fixed interval to process emails automatically.

## License

This project is intended for local automation use and can be adapted for your own environment and email workflow.
