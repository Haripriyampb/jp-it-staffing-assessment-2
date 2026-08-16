"""Lead discovery via SerpAPI plus optional website enrichment.

The parsing layer is deliberately defensive: SerpAPI returns different result
containers per engine (``local_results`` for ``google_maps`` / ``google_local``,
``organic_results`` for ``google``), so each engine has its own normaliser and
everything funnels into the same lead dict.
"""

import re
from collections.abc import Iterable
from typing import Any
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

import config

SERPAPI_ENDPOINT = "https://serpapi.com/search.json"
REQUEST_TIMEOUT = 20
ENRICH_TIMEOUT = 10

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PHONE_RE = re.compile(r"\+?\d[\d\s().-]{7,}\d")
OWNER_RE = re.compile(
    r"(?:owner|founder|ceo|proprietor|managing director|director)\s*[:\-–]?\s*"
    r"([A-Z][a-zA-Z.'-]+(?:\s+[A-Z][a-zA-Z.'-]+){0,2})",
    re.IGNORECASE,
)

GENERIC_EMAIL_PREFIXES = ("noreply", "no-reply", "donotreply", "postmaster", "abuse")
SKIP_EMAIL_DOMAINS = ("sentry.io", "wixpress.com", "example.com", "godaddy.com")

COUNTRY_CODES = {
    "usa": "us",
    "united states": "us",
    "us": "us",
    "uk": "uk",
    "united kingdom": "uk",
    "england": "uk",
    "india": "in",
    "canada": "ca",
    "australia": "au",
    "germany": "de",
    "france": "fr",
    "spain": "es",
    "italy": "it",
    "netherlands": "nl",
    "uae": "ae",
    "united arab emirates": "ae",
    "singapore": "sg",
    "japan": "jp",
    "brazil": "br",
    "mexico": "mx",
    "south africa": "za",
    "new zealand": "nz",
}


class SearchError(RuntimeError):
    pass


def country_code(country: str) -> str | None:
    return COUNTRY_CODES.get(country.strip().lower())


def split_list(raw: str) -> list[str]:
    return [item.strip() for item in (raw or "").split(",") if item.strip()]


def _serpapi_call(params: dict[str, Any]) -> dict[str, Any]:
    if not config.SEARCH_API_KEY:
        raise SearchError("SEARCH_API_KEY is not configured")
    params = {**params, "api_key": config.SEARCH_API_KEY}
    response = requests.get(SERPAPI_ENDPOINT, params=params, timeout=REQUEST_TIMEOUT)
    if response.status_code != 200:
        raise SearchError(
            f"SerpAPI returned HTTP {response.status_code}: {response.text[:200]}"
        )
    payload = response.json()
    if payload.get("error"):
        raise SearchError(str(payload["error"]))
    return payload


def _normalise_local_result(result: dict[str, Any], country: str) -> dict[str, Any]:
    return {
        "business_name": result.get("title", ""),
        "owner_name": "",
        "email": "",
        "phone": result.get("phone", ""),
        "country": country,
        "source": "google_maps",
        "website": result.get("website", "") or result.get("link", ""),
    }


def _normalise_organic_result(result: dict[str, Any], country: str) -> dict[str, Any]:
    snippet = result.get("snippet", "") or ""
    email_match = EMAIL_RE.search(snippet)
    phone_match = PHONE_RE.search(snippet)
    return {
        "business_name": result.get("title", ""),
        "owner_name": "",
        "email": email_match.group(0) if email_match else "",
        "phone": phone_match.group(0).strip() if phone_match else "",
        "country": country,
        "source": "business_website",
        "website": result.get("link", ""),
    }


def _search_country(keywords: str, country: str, limit: int) -> list[dict[str, Any]]:
    engine = config.SEARCH_ENGINE
    params: dict[str, Any] = {"engine": engine, "num": min(limit, 20)}
    code = country_code(country)

    if engine in ("google_maps", "google_local"):
        params["q"] = f"{keywords} {country}".strip()
        params["type"] = "search"
    else:
        params["q"] = f"{keywords} {country}".strip()
        if code:
            params["gl"] = code

    payload = _serpapi_call(params)
    results = payload.get("local_results") or payload.get("organic_results") or []
    if isinstance(results, dict):
        results = results.get("places", [])

    leads = []
    for result in results[:limit]:
        if "local_results" in payload:
            leads.append(_normalise_local_result(result, country))
        else:
            leads.append(_normalise_organic_result(result, country))
    return leads


def _homepage_urls(website: str) -> Iterable[str]:
    parsed = urlparse(website)
    if not parsed.scheme:
        website = f"https://{website}"
    yield website
    for path in ("contact", "contact-us", "about", "about-us"):
        yield urljoin(website.rstrip("/") + "/", path)


def _usable_email(email: str) -> bool:
    local, _, domain = email.lower().partition("@")
    if local.startswith(GENERIC_EMAIL_PREFIXES):
        return False
    if any(domain.endswith(skip) for skip in SKIP_EMAIL_DOMAINS):
        return False
    return not domain.endswith((".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"))


def enrich_from_website(lead: dict[str, Any]) -> dict[str, Any]:
    """Fetch the lead's website and pull out email / phone / owner name."""
    website = lead.get("website") or ""
    if not website:
        return lead

    for url in _homepage_urls(website):
        try:
            response = requests.get(
                url,
                timeout=ENRICH_TIMEOUT,
                headers={"User-Agent": "Mozilla/5.0 (compatible; LeadReport/1.0)"},
            )
        except requests.RequestException:
            continue
        if response.status_code != 200 or "text/html" not in response.headers.get(
            "Content-Type", ""
        ):
            continue

        soup = BeautifulSoup(response.text, "html.parser")
        text = soup.get_text(" ", strip=True)

        if not lead.get("email"):
            candidates = [
                anchor["href"].split("mailto:", 1)[1].split("?")[0]
                for anchor in soup.select('a[href^="mailto:"]')
                if "mailto:" in anchor.get("href", "")
            ]
            candidates.extend(EMAIL_RE.findall(text))
            for candidate in candidates:
                if _usable_email(candidate):
                    lead["email"] = candidate
                    lead["source"] = "business_website"
                    break

        if not lead.get("phone"):
            phone_match = PHONE_RE.search(text)
            if phone_match:
                lead["phone"] = phone_match.group(0).strip()

        if not lead.get("owner_name"):
            owner_match = OWNER_RE.search(text)
            if owner_match:
                lead["owner_name"] = owner_match.group(1).strip()

        if lead.get("email"):
            break

    return lead


def score_lead(lead: dict[str, Any]) -> int:
    score = 20
    if lead.get("email"):
        score += 40
    if lead.get("phone"):
        score += 15
    if lead.get("owner_name"):
        score += 10
    if lead.get("website"):
        score += 10
    if lead.get("business_name"):
        score += 5
    return min(score, 100)


def find_leads(
    keywords: str,
    countries: list[str],
    limit: int,
    seed_urls: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Return up to ``limit`` normalised, scored leads across all countries."""
    leads: list[dict[str, Any]] = []
    seen_websites = set()

    for url in seed_urls or []:
        lead = {
            "business_name": urlparse(
                url if "//" in url else f"https://{url}"
            ).netloc.replace("www.", ""),
            "owner_name": "",
            "email": "",
            "phone": "",
            "country": countries[0] if countries else "",
            "source": "seed_url",
            "website": url,
        }
        leads.append(lead)
        seen_websites.add(url)

    per_country = max(1, limit // max(1, len(countries) or 1))
    for country in countries or [""]:
        if len(leads) >= limit:
            break
        for lead in _search_country(keywords, country, per_country):
            website = lead.get("website")
            if website and website in seen_websites:
                continue
            if website:
                seen_websites.add(website)
            leads.append(lead)
            if len(leads) >= limit:
                break

    enriched = []
    for lead in leads[:limit]:
        if config.SEARCH_ENRICH_WEBSITES:
            lead = enrich_from_website(lead)
        lead["score"] = score_lead(lead)
        enriched.append(lead)
    return enriched
