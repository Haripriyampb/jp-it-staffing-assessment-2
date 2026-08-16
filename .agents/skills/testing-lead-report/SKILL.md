---
name: testing-lead-report
description: How to run and end-to-end test the Lead Report Flask app locally (server startup, state reset, SerpAPI-less search, safe real email sends, and delivery verification).
---

# Testing the Lead Report Flask app

## Running the app

```bash
cd /home/ubuntu/repos/lead-report
(setsid nohup .venv/bin/python app.py > /tmp/leadreport.log 2>&1 < /dev/null &)
sleep 5 && curl -s -o /dev/null -w "%{http_code}\n" http://localhost:5000/
```

Gotchas:
- Wrap the launch in `( ... &)` (or use `setsid`). A bare `nohup ... &` inside the exec tool can die with the shell.
- Do **not** run `pkill -f "app.py"` — the pattern matches the wrapping `bash -c` command itself and kills your own shell. Use a narrower pattern such as `pkill -f "lead-report/.venv/bin/python"`, and run the restart in a *separate* call from the kill.
- Flask debug mode is on, so there are two `python app.py` processes (reloader + child).

## Resetting state before a clean test run

All state lives in flat files; back them up and reset:

```bash
cd /home/ubuntu/repos/lead-report
cp -r data /tmp/data-backup-$(date +%s)
printf 'id,business_name,owner_name,email,phone,country,source,website,score,contacted,created_at\n' > data/leads.csv
printf '{\n  "catalog_filename": "",\n  "email_subject": "",\n  "email_template": "",\n  "emails_sent": 0,\n  "emails_failed": 0\n}\n' > data/settings.json
rm -f uploads/*.pdf
```

`data/leads.csv` holds leads, `data/settings.json` holds the catalog filename, subject/template and the
`emails_sent` / `emails_failed` counters. Dashboard "Total Leads" / "Contacted" are derived from the CSV.

## Search without a SerpAPI key

`SERPAPI_KEY` may be empty. In that case:
- A keyword search flashes `Search failed: SERPAPI_KEY is not set in .env` (302 redirect, not a 500) — this is the expected graceful path.
- Seed-URL-only search skips SerpAPI entirely (`search.find_leads` only calls the API when `keywords` is truthy) and scrapes email/phone/owner from the page. `https://www.iana.org` is a reliable fixture: yields `iana.org / iana@iana.org / +1-424-254-5300 / score 90`.
- **Known trap:** the "Search keywords" input in `templates/index.html` has the HTML `required` attribute, so the browser blocks submitting with keywords blank and the seed-URL-only path is unreachable through the UI. Workaround for testing: type a single space in keywords (satisfies `required`, and the server does `keywords.strip()` so SerpAPI is still skipped). If this is fixed, the `required` attribute will have been removed.

## Safe real email sends

`.env` contains live Gmail SMTP creds. Before clicking any Send / Send Bulk Email button, delete every lead
whose address is not the account owner's own address, then add a single self-addressed lead:

```bash
.venv/bin/python -c "import store; store.add_lead({'business_name':'Hari Test Co','owner_name':'Hari','email':'<SMTP_EMAIL>','phone':'+91 90000 00000','country':'India','source':'manual_test','score':100})"
```

Note the seed-URL scraping flow produces third-party addresses (e.g. `iana@iana.org`) — always delete those first.

## Verifying delivery

The UI only proves the request succeeded. Confirm the message actually left by reading the Gmail Sent folder over IMAP with the same credentials:

```bash
.venv/bin/python -c "
import imaplib, email, os
from dotenv import load_dotenv; load_dotenv()
M = imaplib.IMAP4_SSL('imap.gmail.com'); M.login(os.getenv('SMTP_EMAIL'), os.getenv('SMTP_PASSWORD'))
M.select('\"[Gmail]/Sent Mail\"')
ids = M.search(None, 'ALL')[1][0].split()[-3:]
for i in reversed(ids):
    m = email.message_from_bytes(M.fetch(i, '(RFC822)')[1][0][1])
    print(m['Date'], m['To'], m['Subject'], [p.get_filename() for p in m.walk() if p.get_filename()])
M.logout()"
```

Put a unique marker string (e.g. `TESTRUN-<date>`) in the HTML template before sending so the sent message is unambiguously from your run.

## Log noise

`app.py` registers a catch-all `@app.errorhandler(Exception)`. Every `GET /favicon.ico` therefore logs a full
`werkzeug.exceptions.NotFound` traceback and 302-redirects to `/`. When grepping `/tmp/leadreport.log` for
regressions, filter these out and look for genuine `" 500 "` responses instead of raw `Traceback` counts.

## Devin Secrets Needed

- `SMTP_EMAIL`, `SMTP_PASSWORD` — Gmail address + app password, already in `.env`; needed for send and IMAP verification.
- `SERPAPI_KEY` — optional; without it the keyword search cannot be tested beyond its graceful error path.
