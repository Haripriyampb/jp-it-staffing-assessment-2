# Lead Report

Flask app for finding business leads via SerpAPI and emailing them a product
catalog over Gmail SMTP.

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in SEARCH_API_KEY, SMTP_EMAIL, SMTP_PASSWORD
python app.py          # http://localhost:5000
```

## Configuration

| Variable | Purpose |
| --- | --- |
| `SEARCH_API_KEY` | SerpAPI key |
| `SEARCH_ENGINE` | `google_maps` (default), `google_local` or `google` |
| `SEARCH_ENRICH_WEBSITES` | fetch each result's site to scrape email/phone/owner |
| `SMTP_HOST` / `SMTP_PORT` | defaults to Gmail (`smtp.gmail.com:587`, STARTTLS) |
| `SMTP_EMAIL` / `SMTP_PASSWORD` | Gmail address and App Password |
| `SEND_DELAY` | seconds between sends in a bulk run |
| `WHATSAPP_NUMBER` | value for the `{{whatsappNumber}}` merge tag |
| `UNSUBSCRIBE_BASE_URL` | base for the `{{unsubscribeUrl}}` merge tag |

## How search works

`search.find_leads` queries SerpAPI once per country. `google_maps` /
`google_local` results come back in `local_results` (business name, phone,
website); plain `google` results come back in `organic_results` (title, link,
snippet). SerpAPI does not return email addresses, so when
`SEARCH_ENRICH_WEBSITES` is on each lead's website plus its `/contact`,
`/contact-us`, `/about` and `/about-us` pages are fetched and scanned for a
`mailto:` link, an email pattern, a phone number and an "Owner/Founder/CEO: Name"
pattern. Seed URLs skip the SerpAPI call and go straight to enrichment.

Lead score (0-100): 20 base, +40 email, +15 phone, +10 owner name, +10 website,
+5 business name.

## Storage

SQLite at `data/leads.db` (`DATABASE_PATH` overrides). Leads are deduplicated on
a non-empty email address. Counters for emails sent/failed and the saved email
subject/template/catalog filename live in the same database, so all state
survives restarts.

## Email sending

`mailer.py` opens one SMTP connection per run (`starttls` + `login`), builds a
`MIMEMultipart` per lead with the rendered HTML body and the uploaded catalog
PDF attached, and sleeps `SEND_DELAY` seconds between sends. Merge tags:
`{{ownerName}}`, `{{businessName}}`, `{{whatsappNumber}}`, `{{unsubscribeUrl}}`.
A failed send increments the Failed counter and does not abort the rest of the
run.
