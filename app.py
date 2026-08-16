import os
import smtplib
import time

from flask import (
    Flask,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_from_directory,
    url_for,
)
from werkzeug.utils import secure_filename

import config
import mailer
import search
import store

DEFAULT_SUBJECT = "Partnership opportunity for {{businessName}}"
DEFAULT_TEMPLATE = """<p>Hi {{ownerName}},</p>
<p>I came across {{businessName}} and thought our product catalog (attached) could be
a good fit for your customers.</p>
<p>Happy to chat on WhatsApp: {{whatsappNumber}}</p>
<p style="font-size:12px;color:#888">
  <a href="{{unsubscribeUrl}}">Unsubscribe</a>
</p>
"""

app = Flask(__name__)
app.secret_key = config.SECRET_KEY
app.config["MAX_CONTENT_LENGTH"] = 25 * 1024 * 1024

store.init_storage()
os.makedirs(config.UPLOAD_FOLDER, exist_ok=True)


def catalog_path():
    filename = store.get_setting("catalog_filename")
    if not filename:
        return None
    path = os.path.join(config.UPLOAD_FOLDER, filename)
    return path if os.path.exists(path) else None


@app.route("/")
def index():
    return render_template(
        "index.html",
        leads=store.list_leads(),
        stats=store.stats(),
        catalog_filename=store.get_setting("catalog_filename"),
        subject=store.get_setting("email_subject", DEFAULT_SUBJECT),
        template=store.get_setting("email_template", DEFAULT_TEMPLATE),
        search_connected=config.search_api_configured(),
        search_account=config.masked(config.SERPAPI_KEY) or "not configured",
        search_engine=config.SEARCH_ENGINE,
        smtp_connected=config.smtp_configured(),
        smtp_account=config.SMTP_EMAIL or "not configured",
        send_delay=config.SEND_DELAY,
    )


@app.post("/search")
def run_search():
    keywords = request.form.get("keywords", "").strip()
    countries = search.split_list(request.form.get("countries", ""))
    seed_urls = search.split_list(request.form.get("seed_urls", ""))
    try:
        limit = int(request.form.get("limit") or 10)
    except ValueError:
        limit = 10

    if not keywords and not seed_urls:
        flash("Enter search keywords or at least one seed URL.", "error")
        return redirect(url_for("index"))

    try:
        leads = search.find_leads(keywords, countries, limit, seed_urls)
    except search.SearchError as exc:
        flash(f"Search failed: {exc}", "error")
        return redirect(url_for("index"))

    if not leads:
        flash(
            "Search returned no results. Try different keywords or countries.", "error"
        )
        return redirect(url_for("index"))

    added = sum(1 for lead in leads if store.add_lead(lead))
    flash(
        f"Found {len(leads)} results, saved {added} new leads "
        f"({len(leads) - added} duplicates skipped).",
        "success",
    )
    return redirect(url_for("index"))


@app.post("/upload-catalog")
def upload_catalog():
    file = request.files.get("catalog")
    if not file or not file.filename:
        flash("Choose a PDF file to upload.", "error")
        return redirect(url_for("index"))
    if not file.filename.lower().endswith(".pdf"):
        flash("Only PDF catalogs are supported.", "error")
        return redirect(url_for("index"))

    filename = secure_filename(file.filename)
    file.save(os.path.join(config.UPLOAD_FOLDER, filename))
    store.set_setting("catalog_filename", filename)
    flash(f"Uploaded catalog {filename}.", "success")
    return redirect(url_for("index"))


@app.get("/uploads/<path:filename>")
def uploaded_file(filename):
    return send_from_directory(config.UPLOAD_FOLDER, filename)


@app.post("/email-template")
def save_template():
    store.set_setting("email_subject", request.form.get("subject", ""))
    store.set_setting("email_template", request.form.get("template", ""))
    flash("Email template saved.", "success")
    return redirect(url_for("index"))


def _send_to_leads(leads, subject, template):
    sent, failed, errors = 0, 0, []
    try:
        server = mailer.open_connection()
    except (mailer.MailError, OSError, smtplib.SMTPException) as exc:
        app.logger.warning("SMTP connection failed: %s", exc)
        for _ in leads:
            store.increment_counter("emails_failed")
        return 0, len(leads), [str(exc)]

    try:
        for position, lead in enumerate(leads):
            try:
                mailer.send_lead(server, lead, subject, template, catalog_path())
            except Exception as exc:  # noqa: BLE001 - one failure must not stop the run
                failed += 1
                message = f"{lead.get('email') or lead.get('id')}: {exc}"
                errors.append(message)
                app.logger.warning("Send failed for %s", message)
                store.increment_counter("emails_failed")
            else:
                sent += 1
                store.mark_contacted(int(lead["id"]))
                store.increment_counter("emails_sent")
            if position < len(leads) - 1 and config.SEND_DELAY > 0:
                time.sleep(config.SEND_DELAY)
    finally:
        server.quit()
    return sent, failed, errors


@app.post("/send-bulk")
def send_bulk():
    subject = request.form.get("subject") or store.get_setting(
        "email_subject", DEFAULT_SUBJECT
    )
    template = request.form.get("template") or store.get_setting(
        "email_template", DEFAULT_TEMPLATE
    )
    store.set_setting("email_subject", subject)
    store.set_setting("email_template", template)

    leads = [lead for lead in store.list_leads() if lead["email"]]
    if not leads:
        flash("No leads with an email address to send to.", "error")
        return redirect(url_for("index"))

    sent, failed, errors = _send_to_leads(leads, subject, template)
    message = f"Bulk send finished: {sent} sent, {failed} failed."
    if errors:
        message += " First error: " + errors[0]
    flash(message, "success" if failed == 0 else "error")
    return redirect(url_for("index"))


@app.post("/leads/<int:lead_id>/send")
def send_one(lead_id):
    lead = store.get_lead(lead_id)
    if not lead:
        return jsonify({"ok": False, "error": "Lead not found"}), 404

    subject = store.get_setting("email_subject", DEFAULT_SUBJECT)
    template = store.get_setting("email_template", DEFAULT_TEMPLATE)
    sent, _failed, errors = _send_to_leads([lead], subject, template)
    if sent:
        return jsonify({"ok": True, "contacted": True})
    return jsonify({"ok": False, "error": errors[0] if errors else "Send failed"}), 502


@app.post("/leads/<int:lead_id>/delete")
def delete_one(lead_id):
    if store.delete_lead(lead_id):
        return jsonify({"ok": True})
    return jsonify({"ok": False, "error": "Lead not found"}), 404


@app.errorhandler(413)
def too_large(_error):
    flash("That file is too large (25 MB max).", "error")
    return redirect(url_for("index"))


@app.errorhandler(Exception)
def unhandled_error(error):
    app.logger.exception("Unhandled error", exc_info=error)
    flash(f"Something went wrong: {error}", "error")
    return redirect(url_for("index"))


@app.get("/unsubscribe")
def unsubscribe():
    return render_template("unsubscribe.html", email=request.args.get("email", ""))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), debug=True)
