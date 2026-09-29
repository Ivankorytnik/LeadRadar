from __future__ import annotations

import asyncio
import base64
import csv
import difflib
import hashlib
import hmac
import html
import io
import json
import os
import re
import secrets
import smtplib
import ssl
import time
import uuid
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urljoin, urlparse
from xml.etree import ElementTree as ET

import httpx
from bs4 import BeautifulSoup
from fastapi import BackgroundTasks, Cookie, Depends, FastAPI, Header, HTTPException, Request, Response
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from openpyxl import Workbook
from pydantic import BaseModel, Field
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, create_engine, func, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, sessionmaker

# -----------------------------
# Settings
# -----------------------------

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

APP_NAME = os.getenv("APP_NAME", "LeadRadar AI")
APP_SECRET = os.getenv("APP_SECRET", "dev-secret-change-me")
BASE_URL = os.getenv("BASE_URL", "http://localhost:8000").rstrip("/")
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DATA_DIR / 'leadradar.db'}")
DEMO_MODE = os.getenv("DEMO_MODE", "1") == "1"

YANDEX_API_KEY = os.getenv("YANDEX_API_KEY", "")
YANDEX_FOLDER_ID = os.getenv("YANDEX_FOLDER_ID", "")
SERPAPI_KEY = os.getenv("SERPAPI_KEY", "")
SERPAPI_ENDPOINT = os.getenv("SERPAPI_ENDPOINT", "https://serpapi.com/search.json")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5.6-luna")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_WEBHOOK_SECRET = os.getenv("TELEGRAM_WEBHOOK_SECRET", "change-me")
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "").strip().lower()

SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM = os.getenv("SMTP_FROM", SMTP_USER)
SMTP_STARTTLS = os.getenv("SMTP_STARTTLS", "true").lower() == "true"

# -----------------------------
# DB
# -----------------------------

class Base(DeclarativeBase):
    pass


class Organization(Base):
    __tablename__ = "organizations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    site_url: Mapped[str] = mapped_column(String(500))
    api_key: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    telegram_link_code: Mapped[str] = mapped_column(String(30), unique=True, index=True)
    telegram_chat_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    email_recipients: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(300))
    name: Mapped[str] = mapped_column(String(255), default="")
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class SearchProfile(Base):
    __tablename__ = "search_profiles"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    products: Mapped[str] = mapped_column(Text, default="[]")
    services: Mapped[str] = mapped_column(Text, default="[]")
    keywords: Mapped[str] = mapped_column(Text, default="[]")
    minus_words: Mapped[str] = mapped_column(Text, default="[]")
    regions: Mapped[str] = mapped_column(Text, default="[]")
    customer_types: Mapped[str] = mapped_column(Text, default='["B2B","B2G"]')
    min_score: Mapped[int] = mapped_column(Integer, default=60)
    min_budget: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    schedule_hours: Mapped[int] = mapped_column(Integer, default=6)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_run_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    next_run_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class SearchRun(Base):
    __tablename__ = "search_runs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    search_profile_id: Mapped[int] = mapped_column(ForeignKey("search_profiles.id"), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(40), default="running")
    queries_count: Mapped[int] = mapped_column(Integer, default=0)
    raw_results_count: Mapped[int] = mapped_column(Integer, default=0)
    created_count: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class Opportunity(Base):
    __tablename__ = "opportunities"
    __table_args__ = (UniqueConstraint("organization_id", "dedupe_hash", name="uq_org_dedupe"),)
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    search_profile_id: Mapped[int] = mapped_column(ForeignKey("search_profiles.id"), index=True)
    type: Mapped[str] = mapped_column(String(50), default="lead")
    title: Mapped[str] = mapped_column(String(1000))
    description: Mapped[str] = mapped_column(Text, default="")
    source: Mapped[str] = mapped_column(String(100), default="web")
    source_id: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    source_url: Mapped[str] = mapped_column(Text)
    customer_name: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    customer_inn: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    region: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    address: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    publication_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    deadline: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    amount: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    currency: Mapped[str] = mapped_column(String(10), default="RUB")
    actuality_status: Mapped[str] = mapped_column(String(30), default="Unknown")
    pipeline_status: Mapped[str] = mapped_column(String(50), default="Новая")
    relevance_score: Mapped[int] = mapped_column(Integer, default=0)
    ai_summary: Mapped[str] = mapped_column(Text, default="")
    relevance_reasons: Mapped[str] = mapped_column(Text, default="[]")
    contact_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    contact_phone: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    contact_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    dedupe_hash: Mapped[str] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class Integration(Base):
    __tablename__ = "integrations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    type: Mapped[str] = mapped_column(String(40), default="webhook")
    name: Mapped[str] = mapped_column(String(255), default="Partner CRM")
    endpoint_url: Mapped[str] = mapped_column(Text, default="")
    secret: Mapped[str] = mapped_column(String(300), default="")
    api_key: Mapped[str] = mapped_column(String(500), default="")
    min_relevance_score: Mapped[int] = mapped_column(Integer, default=60)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class DeliveryJob(Base):
    __tablename__ = "delivery_jobs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    opportunity_id: Mapped[str] = mapped_column(ForeignKey("opportunities.id"), index=True)
    channel: Mapped[str] = mapped_column(String(40))
    integration_id: Mapped[Optional[int]] = mapped_column(ForeignKey("integrations.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="pending")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    delivered_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class DeliveryAttempt(Base):
    __tablename__ = "delivery_attempts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    delivery_job_id: Mapped[int] = mapped_column(ForeignKey("delivery_jobs.id"), index=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    opportunity_id: Mapped[str] = mapped_column(ForeignKey("opportunities.id"), index=True)
    channel: Mapped[str] = mapped_column(String(40))
    attempt: Mapped[int] = mapped_column(Integer)
    http_code: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    finished_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    status: Mapped[str] = mapped_column(String(30))
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
Base.metadata.create_all(engine)

# -----------------------------
# Helpers
# -----------------------------

STATUSES = ["Новая", "Просмотрена", "В работе", "Подготовка КП", "КП отправлено", "Переговоры", "Победа", "Проиграна", "Не подходит"]
RETRY_DELAYS = [0, 60, 300, 900, 3600, 21600]


def utcnow() -> datetime:
    return datetime.utcnow()


def json_list(value: str | list[str] | None) -> list[str]:
    if isinstance(value, list):
        return value
    if not value:
        return []
    try:
        data = json.loads(value)
        return [str(x).strip() for x in data if str(x).strip()]
    except Exception:
        return [x.strip() for x in value.split(",") if x.strip()]


def dumps_list(value: list[str]) -> str:
    return json.dumps([x.strip() for x in value if x.strip()], ensure_ascii=False)


def clean_url(url: str) -> str:
    url = url.strip()
    if not re.match(r"^https?://", url, re.I):
        url = "https://" + url
    return url.rstrip("/")


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 180_000).hex()
    return f"pbkdf2_sha256${salt}${digest}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, salt, digest = stored.split("$", 2)
        actual = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 180_000).hex()
        return hmac.compare_digest(actual, digest)
    except Exception:
        return False


def sign_session(user_id: int) -> str:
    expires = int(time.time()) + 60 * 60 * 24 * 14
    payload = f"{user_id}:{expires}"
    sig = hmac.new(APP_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return base64.urlsafe_b64encode(f"{payload}:{sig}".encode()).decode()


def parse_session(token: str | None) -> Optional[int]:
    if not token:
        return None
    try:
        raw = base64.urlsafe_b64decode(token.encode()).decode()
        user_id_s, expires_s, sig = raw.split(":", 2)
        payload = f"{user_id_s}:{expires_s}"
        expected = hmac.new(APP_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected) or int(expires_s) < int(time.time()):
            return None
        return int(user_id_s)
    except Exception:
        return None


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def current_user(
    db: Session = Depends(get_db),
    leadradar_session: Optional[str] = Cookie(default=None),
    x_api_key: Optional[str] = Header(default=None, alias="X-API-Key"),
) -> User:
    if x_api_key:
        org = db.scalar(select(Organization).where(Organization.api_key == x_api_key))
        if not org:
            raise HTTPException(401, "Invalid API key")
        user = db.scalar(select(User).where(User.organization_id == org.id).order_by(User.id.asc()))
        if not user:
            raise HTTPException(401, "Organization has no user")
        return user
    uid = parse_session(leadradar_session)
    if not uid:
        raise HTTPException(401, "Not authenticated")
    user = db.get(User, uid)
    if not user:
        raise HTTPException(401, "Not authenticated")
    return user


def user_org(db: Session, user: User) -> Organization:
    org = db.get(Organization, user.organization_id)
    if not org:
        raise HTTPException(404, "Organization not found")
    return org


def opportunity_to_dict(o: Opportunity) -> dict[str, Any]:
    return {
        "id": o.id,
        "type": o.type,
        "title": o.title,
        "description": o.description,
        "source": o.source,
        "source_id": o.source_id,
        "source_url": o.source_url,
        "customer_name": o.customer_name,
        "customer_inn": o.customer_inn,
        "region": o.region,
        "address": o.address,
        "publication_date": o.publication_date.isoformat() if o.publication_date else None,
        "deadline": o.deadline.isoformat() if o.deadline else None,
        "amount": o.amount,
        "currency": o.currency,
        "actuality_status": o.actuality_status,
        "status": o.pipeline_status,
        "relevance_score": o.relevance_score,
        "ai_summary": o.ai_summary,
        "relevance_reasons": json_list(o.relevance_reasons),
        "contact_name": o.contact_name,
        "contact_phone": o.contact_phone,
        "contact_email": o.contact_email,
        "created_at": o.created_at.isoformat(),
        "updated_at": o.updated_at.isoformat(),
    }


def profile_to_dict(p: SearchProfile) -> dict[str, Any]:
    return {
        "id": p.id,
        "name": p.name,
        "products": json_list(p.products),
        "services": json_list(p.services),
        "keywords": json_list(p.keywords),
        "minus_words": json_list(p.minus_words),
        "regions": json_list(p.regions),
        "customer_types": json_list(p.customer_types),
        "min_score": p.min_score,
        "min_budget": p.min_budget,
        "schedule_hours": p.schedule_hours,
        "is_active": p.is_active,
        "last_run_at": p.last_run_at.isoformat() if p.last_run_at else None,
        "next_run_at": p.next_run_at.isoformat() if p.next_run_at else None,
    }


# -----------------------------
# Site analysis
# -----------------------------

STOP_WORDS = {
    "для", "или", "это", "как", "что", "при", "его", "она", "они", "мы", "вы", "вас", "наш", "ваш", "сайт", "главная",
    "компания", "компании", "услуги", "товары", "контакты", "подробнее", "заказать", "купить", "цена", "цены", "россия",
    "the", "and", "with", "from", "your", "our", "are", "for", "this", "that", "home", "contact", "about"
}


async def fetch_text(url: str, max_chars: int = 80_000) -> tuple[str, str, str]:
    headers = {"User-Agent": "Mozilla/5.0 LeadRadarBot/1.0 (+https://example.invalid/bot)"}
    async with httpx.AsyncClient(timeout=15, follow_redirects=True, headers=headers) as client:
        r = await client.get(url)
        r.raise_for_status()
        content_type = r.headers.get("content-type", "")
        if "html" not in content_type and "text" not in content_type:
            return r.text[:max_chars], str(r.url), content_type
        soup = BeautifulSoup(r.text, "lxml")
        for tag in soup(["script", "style", "noscript", "svg"]):
            tag.decompose()
        text = " ".join(soup.stripped_strings)
        return text[:max_chars], str(r.url), content_type


async def analyze_site(url: str) -> dict[str, Any]:
    url = clean_url(url)
    pages = [url]
    combined = ""
    title = urlparse(url).netloc
    try:
        async with httpx.AsyncClient(timeout=12, follow_redirects=True, headers={"User-Agent": "Mozilla/5.0 LeadRadarBot/1.0"}) as client:
            r = await client.get(url)
            r.raise_for_status()
            soup = BeautifulSoup(r.text, "lxml")
            title = (soup.title.string.strip() if soup.title and soup.title.string else title)[:200]
            combined += " ".join(soup.stripped_strings)[:50_000]
            links: list[str] = []
            for a in soup.find_all("a", href=True):
                href = urljoin(str(r.url), a["href"])
                label = (a.get_text(" ", strip=True) + " " + href).lower()
                if urlparse(href).netloc == urlparse(str(r.url)).netloc and any(k in label for k in ["услуг", "каталог", "product", "service", "about", "о-комп", "контакт"]):
                    if href not in links:
                        links.append(href)
            for href in links[:4]:
                try:
                    rr = await client.get(href)
                    if rr.status_code < 400 and "html" in rr.headers.get("content-type", ""):
                        ss = BeautifulSoup(rr.text, "lxml")
                        for tag in ss(["script", "style", "noscript"]):
                            tag.decompose()
                        combined += " " + " ".join(ss.stripped_strings)[:20_000]
                        pages.append(href)
                except Exception:
                    pass
    except Exception as e:
        raise HTTPException(400, f"Не удалось прочитать сайт: {e}")

    words = re.findall(r"[A-Za-zА-Яа-яЁё0-9][A-Za-zА-Яа-яЁё0-9+.-]{2,}", combined.lower())
    counts: dict[str, int] = {}
    for w in words:
        if w in STOP_WORDS or w.isdigit() or len(w) > 40:
            continue
        counts[w] = counts.get(w, 0) + 1
    keywords = [w for w, c in sorted(counts.items(), key=lambda x: x[1], reverse=True) if c >= 2][:18]

    regions = []
    known_regions = ["москва", "московская область", "санкт-петербург", "ленинградская область", "россия", "казань", "екатеринбург", "новосибирск", "краснодар"]
    low = combined.lower()
    for region in known_regions:
        if region in low:
            regions.append(region.title())
    if not regions:
        regions = ["Россия"]

    # Optional AI refinement: only if explicitly configured.
    ai_data = None
    if OPENAI_API_KEY:
        prompt = (
            "Проанализируй сайт компании по тексту. Верни ТОЛЬКО JSON с полями: "
            "products (array), services (array), keywords (array), minus_words (array), customer_types (array), summary (string). "
            "Не выдумывай факты. Текст сайта:\n" + combined[:20_000]
        )
        try:
            async with httpx.AsyncClient(timeout=45) as client:
                rr = await client.post(
                    "https://api.openai.com/v1/responses",
                    headers={"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"},
                    json={"model": OPENAI_MODEL, "input": prompt, "store": False},
                )
                rr.raise_for_status()
                data = rr.json()
                texts = []
                for item in data.get("output", []):
                    for content in item.get("content", []):
                        if content.get("type") == "output_text":
                            texts.append(content.get("text", ""))
                raw = "\n".join(texts).strip()
                raw = re.sub(r"^```(?:json)?|```$", "", raw, flags=re.I | re.M).strip()
                ai_data = json.loads(raw)
        except Exception:
            ai_data = None

    products = []
    services = []
    if ai_data:
        products = [str(x) for x in ai_data.get("products", [])][:15]
        services = [str(x) for x in ai_data.get("services", [])][:15]
        keywords = [str(x) for x in ai_data.get("keywords", [])][:25] or keywords
    else:
        # Generic MVP fallback: frequent multi-purpose business terms become search keywords.
        products = keywords[:6]
        services = keywords[6:12]

    return {
        "site_url": url,
        "title": title,
        "pages_analyzed": pages,
        "products": products,
        "services": services,
        "keywords": keywords,
        "minus_words": ["вакансия", "работа", "резюме", "обучение"],
        "regions": regions,
        "customer_types": (ai_data or {}).get("customer_types", ["B2B", "B2G"]),
        "summary": (ai_data or {}).get("summary", f"Автоматический профиль по сайту {title}"),
    }


# -----------------------------
# Search connectors
# -----------------------------

def build_queries(profile: SearchProfile) -> list[str]:
    terms = json_list(profile.services) + json_list(profile.products) + json_list(profile.keywords)
    terms = list(dict.fromkeys([x for x in terms if len(x) >= 3]))[:8]
    regions = json_list(profile.regions)[:2] or [""]
    patterns = ["требуется {term}", "ищем подрядчика {term}", "закупка {term}", "тендер {term}", "запрос КП {term}"]
    queries = []
    for term in terms[:5]:
        for pattern in patterns[:3]:
            q = pattern.format(term=term)
            if regions[0]:
                q += " " + regions[0]
            queries.append(q)
        queries.append(f"site:zakupki.gov.ru {term} {regions[0]}".strip())
    return list(dict.fromkeys(queries))[:16]


async def yandex_search(query: str) -> list[dict[str, Any]]:
    if not (YANDEX_API_KEY and YANDEX_FOLDER_ID):
        return []
    body = {
        "query": {"searchType": "SEARCH_TYPE_RU", "queryText": query, "familyMode": "FAMILY_MODE_MODERATE"},
        "groupSpec": {"groupMode": "GROUP_MODE_FLAT", "groupsOnPage": "10", "docsInGroup": "1"},
        "folderId": YANDEX_FOLDER_ID,
        "responseFormat": "FORMAT_XML",
    }
    async with httpx.AsyncClient(timeout=25) as client:
        r = await client.post(
            "https://searchapi.api.cloud.yandex.net/v2/web/search",
            headers={"Authorization": f"Api-Key {YANDEX_API_KEY}", "Content-Type": "application/json"},
            json=body,
        )
        r.raise_for_status()
        raw = base64.b64decode(r.json()["rawData"])
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        return []
    results = []
    for doc in root.findall(".//doc"):
        def txt(path: str) -> str:
            el = doc.find(path)
            return "" if el is None else "".join(el.itertext()).strip()
        url = txt("url") or txt("saved-copy-url")
        title = txt("title") or url
        passages = " ".join("".join(p.itertext()).strip() for p in doc.findall(".//passage"))
        if url:
            results.append({"title": title, "url": url, "snippet": passages, "source": "Yandex Search API"})
    return results


async def serpapi_search(query: str) -> list[dict[str, Any]]:
    if not SERPAPI_KEY:
        return []
    params = {"api_key": SERPAPI_KEY, "engine": "google", "q": query, "hl": "ru", "gl": "ru", "num": 10}
    async with httpx.AsyncClient(timeout=25) as client:
        r = await client.get(SERPAPI_ENDPOINT, params=params)
        r.raise_for_status()
        data = r.json()
    out = []
    for item in data.get("organic_results", []):
        if item.get("link"):
            out.append({"title": item.get("title") or item["link"], "url": item["link"], "snippet": item.get("snippet", ""), "source": "SERP API"})
    return out


def demo_search(profile: SearchProfile) -> list[dict[str, Any]]:
    terms = json_list(profile.services) + json_list(profile.products) + json_list(profile.keywords)
    term = terms[0] if terms else "корпоративные услуги"
    region = (json_list(profile.regions) or ["Москва"])[0]
    today = utcnow().date().isoformat()
    return [
        {
            "title": f"Запрос коммерческого предложения: {term}",
            "url": f"https://demo.leadradar.local/opportunity/{profile.id}/1",
            "snippet": f"Организация ищет поставщика/подрядчика по направлению {term}. Регион: {region}. Срок подачи предложений 7 дней.",
            "source": "DEMO",
            "demo": True,
        },
        {
            "title": f"Тендер на {term}",
            "url": f"https://demo.leadradar.local/opportunity/{profile.id}/2",
            "snippet": f"Закупка по направлению {term}. {region}. Начальная цена 2 500 000 руб. Опубликовано {today}.",
            "source": "DEMO",
            "demo": True,
        },
    ]


def infer_amount(text: str) -> Optional[float]:
    patterns = [
        r"(?:цена|сумма|бюджет|нмцк)[^\d]{0,20}([\d\s]{4,15})(?:[,.]\d+)?\s*(?:₽|руб|р\b)",
        r"([\d\s]{4,15})\s*(?:₽|руб(?:лей|ля)?\b)",
    ]
    low = text.lower().replace("\xa0", " ")
    for p in patterns:
        m = re.search(p, low, re.I)
        if m:
            try:
                return float(re.sub(r"\s", "", m.group(1)))
            except Exception:
                pass
    return None


def infer_deadline(text: str) -> Optional[datetime]:
    # dd.mm.yyyy or dd-mm-yyyy
    for m in re.finditer(r"\b(0?[1-9]|[12]\d|3[01])[./-](0?[1-9]|1[0-2])[./-](20\d{2})\b", text):
        try:
            d = datetime(int(m.group(3)), int(m.group(2)), int(m.group(1)))
            if d >= utcnow() - timedelta(days=1):
                return d
        except Exception:
            pass
    return None


def infer_contacts(text: str) -> tuple[Optional[str], Optional[str]]:
    email_match = re.search(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", text, re.I)
    phone_match = re.search(r"(?:\+7|8)[\s()-]*\d{3}[\s()-]*\d{3}[\s-]*\d{2}[\s-]*\d{2}", text)
    return (phone_match.group(0) if phone_match else None, email_match.group(0) if email_match else None)


async def enrich_result(result: dict[str, Any]) -> dict[str, Any]:
    if result.get("demo"):
        return result
    url = result.get("url", "")
    if not url:
        return result
    try:
        text, final_url, _ = await fetch_text(url, max_chars=30_000)
        result["url"] = final_url
        result["page_text"] = text
    except Exception:
        result["page_text"] = ""
    return result


def score_result(profile: SearchProfile, result: dict[str, Any]) -> tuple[int, list[str], str, str]:
    text = (result.get("title", "") + " " + result.get("snippet", "") + " " + result.get("page_text", "")).lower()
    terms = json_list(profile.services) + json_list(profile.products) + json_list(profile.keywords)
    minus = json_list(profile.minus_words)
    regions = json_list(profile.regions)

    score = 0
    reasons: list[str] = []
    matched_terms = [t for t in terms if t.lower() in text]
    if matched_terms:
        score += min(40, 16 + len(matched_terms) * 6)
        reasons.append("совпадает продукт/услуга: " + ", ".join(matched_terms[:3]))
    if regions and any(r.lower() in text for r in regions):
        score += 15
        reasons.append("подходящая география")
    if any(x in text for x in ["тендер", "закуп", "требуется", "ищем", "поставщик", "подрядчик", "запрос коммерческого", "запрос кп"]):
        score += 20
        reasons.append("обнаружен явный сигнал коммерческого спроса")
    if any(m.lower() in text for m in minus):
        score -= 35
        reasons.append("есть минус-слово")
    amount = infer_amount(text)
    if amount is not None:
        if profile.min_budget is None or amount >= profile.min_budget:
            score += 10
            reasons.append("бюджет соответствует фильтру")
        else:
            score -= 15
            reasons.append("бюджет ниже минимального")
    deadline = infer_deadline(text)
    actuality = "Unknown"
    closed_markers = ["прием заявок заверш", "приём заявок заверш", "закупка завершена", "тендер завершен", "тендер завершён", "объявление закрыто", "неактуально"]
    if any(marker in text for marker in closed_markers):
        actuality = "Closed"
        score -= 40
        reasons.append("источник содержит признак завершенной заявки")
    elif deadline:
        if deadline < utcnow():
            actuality = "Closed"
            score -= 40
        elif deadline <= utcnow() + timedelta(days=2):
            actuality = "Expiring"
            score += 5
            reasons.append("срок подачи скоро заканчивается")
        else:
            actuality = "Active"
            score += 10
            reasons.append("заявка выглядит активной")
    else:
        page_reachable = bool(result.get("page_text"))
        actuality = "Active" if (result.get("demo") or page_reachable) else "Unknown"
        if actuality == "Active":
            score += 10
            reasons.append("страница источника доступна при повторной проверке")

    score = max(0, min(100, score))
    typ = "tender" if any(x in text for x in ["тендер", "закуп", "44-фз", "223-фз", "zakupki.gov.ru"]) else "lead"
    return score, reasons, actuality, typ


async def ai_summary_if_enabled(title: str, description: str, reasons: list[str]) -> str:
    fallback = f"{title}. " + ("; ".join(reasons[:3]) if reasons else "Требуется ручная проверка релевантности.")
    if not OPENAI_API_KEY:
        return fallback[:1200]
    prompt = (
        "Кратко, до 3 предложений, суммируй коммерческую возможность для B2B-менеджера. "
        "Не выдумывай данные. Укажи, почему стоит открыть источник.\n"
        f"Заголовок: {title}\nТекст: {description[:6000]}\nПричины: {', '.join(reasons)}"
    )
    try:
        async with httpx.AsyncClient(timeout=35) as client:
            r = await client.post(
                "https://api.openai.com/v1/responses",
                headers={"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"},
                json={"model": OPENAI_MODEL, "input": prompt, "store": False},
            )
            r.raise_for_status()
            data = r.json()
            texts = []
            for item in data.get("output", []):
                for content in item.get("content", []):
                    if content.get("type") == "output_text":
                        texts.append(content.get("text", ""))
            return "\n".join(texts).strip()[:1200] or fallback[:1200]
    except Exception:
        return fallback[:1200]


# -----------------------------
# Delivery
# -----------------------------

def webhook_payload(o: Opportunity) -> dict[str, Any]:
    return {
        "event": "opportunity.created",
        "id": o.id,
        "external_id": o.id,
        "type": o.type,
        "title": o.title,
        "description": o.description,
        "relevance_score": o.relevance_score,
        "customer": {"name": o.customer_name, "inn": o.customer_inn},
        "location": {"region": o.region, "address": o.address},
        "amount": {"value": o.amount, "currency": o.currency} if o.amount is not None else None,
        "publication_date": o.publication_date.isoformat() if o.publication_date else None,
        "deadline": o.deadline.isoformat() if o.deadline else None,
        "source": {"name": o.source, "url": o.source_url},
        "contacts": {"name": o.contact_name, "phone": o.contact_phone, "email": o.contact_email},
        "ai_summary": o.ai_summary,
        "status": o.pipeline_status,
        "created_at": o.created_at.isoformat(),
    }


def enqueue_delivery_jobs(db: Session, org: Organization, o: Opportunity) -> None:
    now = utcnow()
    channels: list[tuple[str, Optional[int]]] = []
    if org.email_recipients.strip():
        channels.append(("email", None))
    if org.telegram_chat_id and TELEGRAM_BOT_TOKEN:
        channels.append(("telegram", None))
    integrations = db.scalars(select(Integration).where(Integration.organization_id == org.id, Integration.is_active == True)).all()
    for integ in integrations:
        if o.relevance_score >= integ.min_relevance_score and integ.endpoint_url:
            channels.append(("webhook", integ.id))
    for channel, integration_id in channels:
        exists = db.scalar(select(DeliveryJob).where(
            DeliveryJob.opportunity_id == o.id,
            DeliveryJob.channel == channel,
            DeliveryJob.integration_id == integration_id,
        ))
        if not exists:
            db.add(DeliveryJob(
                organization_id=org.id,
                opportunity_id=o.id,
                channel=channel,
                integration_id=integration_id,
                status="pending",
                attempts=0,
                next_attempt_at=now,
            ))
    db.commit()


def send_email_sync(org: Organization, o: Opportunity) -> tuple[bool, Optional[int], str]:
    if not SMTP_HOST or not SMTP_FROM:
        return False, None, "SMTP not configured"
    recipients = [x.strip() for x in re.split(r"[,;\n]", org.email_recipients) if x.strip()]
    if not recipients:
        return False, None, "No recipients"
    msg = EmailMessage()
    msg["From"] = SMTP_FROM
    msg["To"] = ", ".join(recipients)
    msg["Subject"] = f"Новая возможность: {o.title[:80]} | {o.relevance_score}%"
    lines = [
        f"{o.title}",
        f"Релевантность: {o.relevance_score}%",
        f"Тип: {o.type}",
        f"Регион: {o.region or '-'}",
        f"Бюджет: {o.amount:,.0f} {o.currency}" if o.amount is not None else "Бюджет: не указан",
        f"Срок: {o.deadline.date().isoformat() if o.deadline else '-'}",
        "",
        o.ai_summary or o.description[:1200],
        "",
        f"Источник: {o.source_url}",
        f"Карточка: {BASE_URL}/#opportunity={o.id}",
    ]
    msg.set_content("\n".join(lines))
    try:
        if SMTP_STARTTLS:
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20) as server:
                server.ehlo()
                server.starttls(context=ssl.create_default_context())
                if SMTP_USER:
                    server.login(SMTP_USER, SMTP_PASSWORD)
                server.send_message(msg)
        else:
            with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=20, context=ssl.create_default_context()) as server:
                if SMTP_USER:
                    server.login(SMTP_USER, SMTP_PASSWORD)
                server.send_message(msg)
        return True, 250, ""
    except Exception as e:
        return False, None, str(e)


async def send_telegram(org: Organization, o: Opportunity) -> tuple[bool, Optional[int], str]:
    if not TELEGRAM_BOT_TOKEN or not org.telegram_chat_id:
        return False, None, "Telegram not configured"
    text = (
        f"<b>Новая возможность</b>\n\n"
        f"<b>{html.escape(o.title[:500])}</b>\n"
        f"📍 {html.escape(o.region or 'Регион не указан')}\n"
        f"💰 {(f'{o.amount:,.0f} {o.currency}' if o.amount is not None else 'Бюджет не указан')}\n"
        f"⭐ {o.relevance_score}%\n"
        f"⏱ {(o.deadline.date().isoformat() if o.deadline else 'Срок не указан')}\n\n"
        f"{html.escape((o.ai_summary or o.description)[:1200])}"
    )
    keyboard = {
        "inline_keyboard": [
            [{"text": "Открыть источник", "url": o.source_url}],
            [
                {"text": "В работу", "callback_data": f"status:{o.id}:В работе"},
                {"text": "Не подходит", "callback_data": f"status:{o.id}:Не подходит"},
            ],
        ]
    }
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.post(
                f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                json={"chat_id": org.telegram_chat_id, "text": text, "parse_mode": "HTML", "reply_markup": keyboard, "disable_web_page_preview": True},
            )
            ok = 200 <= r.status_code < 300 and r.json().get("ok") is True
            return ok, r.status_code, "" if ok else r.text[:500]
    except Exception as e:
        return False, None, str(e)


async def send_webhook(integ: Integration, o: Opportunity) -> tuple[bool, Optional[int], str]:
    payload = webhook_payload(o)
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
    signature = hmac.new(integ.secret.encode(), raw, hashlib.sha256).hexdigest() if integ.secret else ""
    headers = {
        "Content-Type": "application/json",
        "X-LeadRadar-Event": "opportunity.created",
        "X-LeadRadar-Id": o.id,
        "X-LeadRadar-Timestamp": str(int(time.time())),
        "X-LeadRadar-Signature": signature,
    }
    if integ.api_key:
        headers["Authorization"] = f"Bearer {integ.api_key}"
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(integ.endpoint_url, content=raw, headers=headers)
            ok = 200 <= r.status_code < 300
            return ok, r.status_code, "" if ok else r.text[:800]
    except Exception as e:
        return False, None, str(e)


async def process_delivery_job(job_id: int) -> None:
    with SessionLocal() as db:
        job = db.get(DeliveryJob, job_id)
        if not job or job.status in {"delivered", "failed", "disabled", "processing"}:
            return
        o = db.get(Opportunity, job.opportunity_id)
        org = db.get(Organization, job.organization_id)
        if not o or not org:
            return
        job.status = "processing"
        job.attempts += 1
        db.commit()
        attempt_no = job.attempts
        channel = job.channel
        integ = db.get(Integration, job.integration_id) if job.integration_id else None

    ok = False
    code = None
    error = ""
    if channel == "email":
        ok, code, error = await asyncio.to_thread(send_email_sync, org, o)
    elif channel == "telegram":
        ok, code, error = await send_telegram(org, o)
    elif channel == "webhook" and integ:
        ok, code, error = await send_webhook(integ, o)
    else:
        error = "Unsupported or missing integration"

    with SessionLocal() as db:
        job = db.get(DeliveryJob, job_id)
        if not job:
            return
        db.add(DeliveryAttempt(
            delivery_job_id=job.id,
            organization_id=job.organization_id,
            opportunity_id=job.opportunity_id,
            channel=job.channel,
            attempt=attempt_no,
            http_code=code,
            status="delivered" if ok else "failed",
            error=error or None,
        ))
        if ok:
            job.status = "delivered"
            job.delivered_at = utcnow()
            job.last_error = None
        else:
            job.last_error = error[:2000]
            if attempt_no >= len(RETRY_DELAYS):
                job.status = "failed"
            else:
                job.status = "retrying"
                job.next_attempt_at = utcnow() + timedelta(seconds=RETRY_DELAYS[attempt_no])
        db.commit()


async def delivery_worker_tick() -> None:
    with SessionLocal() as db:
        jobs = db.scalars(select(DeliveryJob).where(
            DeliveryJob.status.in_(["pending", "retrying"]),
            DeliveryJob.next_attempt_at <= utcnow(),
        ).order_by(DeliveryJob.id.asc()).limit(20)).all()
        ids = [j.id for j in jobs]
    for jid in ids:
        await process_delivery_job(jid)


# -----------------------------
# Search pipeline
# -----------------------------

async def run_profile_search(profile_id: int) -> dict[str, Any]:
    with SessionLocal() as db:
        profile = db.get(SearchProfile, profile_id)
        if not profile:
            return {"error": "profile not found"}
        org = db.get(Organization, profile.organization_id)
        run = SearchRun(organization_id=profile.organization_id, search_profile_id=profile.id)
        db.add(run)
        db.commit()
        db.refresh(run)
        run_id = run.id
        queries = build_queries(profile)
        run.queries_count = len(queries)
        db.commit()

    raw_results: list[dict[str, Any]] = []
    try:
        if YANDEX_API_KEY and YANDEX_FOLDER_ID:
            for q in queries:
                try:
                    raw_results.extend(await yandex_search(q))
                except Exception:
                    pass
        if SERPAPI_KEY:
            for q in queries[:8]:
                try:
                    raw_results.extend(await serpapi_search(q))
                except Exception:
                    pass
        if not raw_results and DEMO_MODE:
            with SessionLocal() as db:
                p = db.get(SearchProfile, profile_id)
                raw_results = demo_search(p)

        # Fast URL/title dedupe before expensive crawling.
        uniq: dict[str, dict[str, Any]] = {}
        for r in raw_results:
            key = hashlib.sha256((r.get("url", "") + "|" + r.get("title", "")).lower().encode()).hexdigest()
            uniq[key] = r
        raw_results = list(uniq.values())[:80]

        created = 0
        for r in raw_results:
            r = await enrich_result(r)
            with SessionLocal() as db:
                profile = db.get(SearchProfile, profile_id)
                org = db.get(Organization, profile.organization_id)
                score, reasons, actuality, typ = score_result(profile, r)
                if score < profile.min_score or actuality in {"Closed", "Cancelled"}:
                    continue
                source_url = r.get("url", "")
                canonical = re.sub(r"[?#].*$", "", source_url).rstrip("/").lower()
                dedupe_hash = hashlib.sha256((canonical + "|" + re.sub(r"\s+", " ", r.get("title", "").lower())).encode()).hexdigest()
                existing = db.scalar(select(Opportunity).where(
                    Opportunity.organization_id == profile.organization_id,
                    Opportunity.dedupe_hash == dedupe_hash,
                ))
                if existing:
                    existing.last_seen_at = utcnow()
                    db.commit()
                    continue
                # Near-duplicate guard for mirrors / tracking URLs with the same commercial request.
                normalized_title = re.sub(r"[^a-zа-яё0-9]+", " ", r.get("title", "").lower()).strip()
                recent = db.scalars(select(Opportunity).where(
                    Opportunity.organization_id == profile.organization_id
                ).order_by(Opportunity.created_at.desc()).limit(100)).all()
                is_near_duplicate = False
                for prev in recent:
                    prev_title = re.sub(r"[^a-zа-яё0-9]+", " ", prev.title.lower()).strip()
                    if normalized_title and prev_title and difflib.SequenceMatcher(None, normalized_title, prev_title).ratio() >= 0.94:
                        prev.last_seen_at = utcnow()
                        is_near_duplicate = True
                        break
                if is_near_duplicate:
                    db.commit()
                    continue
                text = (r.get("snippet", "") + " " + r.get("page_text", ""))[:30_000]
                amount = infer_amount(text)
                deadline = infer_deadline(text)
                phone, email_addr = infer_contacts(text)
                summary = await ai_summary_if_enabled(r.get("title", ""), text, reasons)
                region = None
                for rg in json_list(profile.regions):
                    if rg.lower() in text.lower():
                        region = rg
                        break
                if not region and json_list(profile.regions):
                    region = json_list(profile.regions)[0] if r.get("demo") else None
                opp = Opportunity(
                    id="opp_" + uuid.uuid4().hex[:16],
                    organization_id=profile.organization_id,
                    search_profile_id=profile.id,
                    type=typ,
                    title=r.get("title", "Без названия")[:1000],
                    description=(r.get("snippet", "") or text[:4000])[:20_000],
                    source=r.get("source", "web")[:100],
                    source_id=source_url[:500],
                    source_url=source_url,
                    region=region,
                    deadline=deadline,
                    amount=amount,
                    actuality_status=actuality,
                    relevance_score=score,
                    ai_summary=summary,
                    relevance_reasons=dumps_list(reasons),
                    contact_phone=phone,
                    contact_email=email_addr,
                    dedupe_hash=dedupe_hash,
                )
                db.add(opp)
                db.commit()
                db.refresh(opp)
                enqueue_delivery_jobs(db, org, opp)
                created += 1

        with SessionLocal() as db:
            run = db.get(SearchRun, run_id)
            profile = db.get(SearchProfile, profile_id)
            run.raw_results_count = len(raw_results)
            run.created_count = created
            run.status = "completed"
            run.finished_at = utcnow()
            profile.last_run_at = utcnow()
            profile.next_run_at = utcnow() + timedelta(hours=max(1, profile.schedule_hours))
            db.commit()
        await delivery_worker_tick()
        return {"run_id": run_id, "raw_results": len(raw_results), "created": created}
    except Exception as e:
        with SessionLocal() as db:
            run = db.get(SearchRun, run_id)
            if run:
                run.status = "failed"
                run.error = str(e)[:3000]
                run.finished_at = utcnow()
                db.commit()
        return {"run_id": run_id, "error": str(e)}


async def scheduler_tick() -> None:
    with SessionLocal() as db:
        profiles = db.scalars(select(SearchProfile).where(SearchProfile.is_active == True)).all()
        due = []
        now = utcnow()
        for p in profiles:
            if p.next_run_at is None or p.next_run_at <= now:
                due.append(p.id)
                # reserve next slot now to avoid concurrent duplicate runs
                p.next_run_at = now + timedelta(hours=max(1, p.schedule_hours))
        db.commit()
    for pid in due[:10]:
        asyncio.create_task(run_profile_search(pid))


# -----------------------------
# Schemas
# -----------------------------

class RegisterIn(BaseModel):
    organization_name: str = Field(min_length=2, max_length=255)
    site_url: str
    name: str = ""
    email: str
    password: str = Field(min_length=6)


class LoginIn(BaseModel):
    email: str
    password: str


class ProfileIn(BaseModel):
    name: str
    products: list[str] = []
    services: list[str] = []
    keywords: list[str] = []
    minus_words: list[str] = []
    regions: list[str] = []
    customer_types: list[str] = ["B2B", "B2G"]
    min_score: int = 60
    min_budget: Optional[float] = None
    schedule_hours: int = 6
    is_active: bool = True


class StatusIn(BaseModel):
    status: str


class SettingsIn(BaseModel):
    email_recipients: str = ""


class IntegrationIn(BaseModel):
    name: str = "Partner CRM"
    endpoint_url: str
    secret: str = ""
    api_key: str = ""
    min_relevance_score: int = 60
    is_active: bool = True


# -----------------------------
# App
# -----------------------------

app = FastAPI(title=APP_NAME, version="0.1.0")
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "app" / "static")), name="static")
worker_tasks: list[asyncio.Task] = []


async def periodic_loop(fn, seconds: int):
    while True:
        try:
            await fn()
        except asyncio.CancelledError:
            raise
        except Exception:
            pass
        await asyncio.sleep(seconds)


@app.on_event("startup")
async def on_startup():
    worker_tasks.append(asyncio.create_task(periodic_loop(scheduler_tick, 60)))
    worker_tasks.append(asyncio.create_task(periodic_loop(delivery_worker_tick, 20)))


@app.on_event("shutdown")
async def on_shutdown():
    for task in worker_tasks:
        task.cancel()
    if worker_tasks:
        await asyncio.gather(*worker_tasks, return_exceptions=True)


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "app": APP_NAME,
        "demo_mode": DEMO_MODE,
        "live_search": bool(YANDEX_API_KEY and YANDEX_FOLDER_ID) or bool(SERPAPI_KEY),
        "telegram": bool(TELEGRAM_BOT_TOKEN),
        "smtp": bool(SMTP_HOST and SMTP_FROM),
    }


@app.get("/", response_class=HTMLResponse)
async def index():
    return FileResponse(BASE_DIR / "app" / "static" / "index.html")


@app.post("/api/auth/register")
async def register(data: RegisterIn, background: BackgroundTasks, response: Response, db: Session = Depends(get_db)):
    email = data.email.strip().lower()
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(409, "Email already registered")
    org = Organization(
        name=data.organization_name.strip(),
        site_url=clean_url(data.site_url),
        api_key="lr_" + secrets.token_urlsafe(32),
        telegram_link_code=secrets.token_hex(4).upper(),
        email_recipients=email,
    )
    db.add(org)
    db.commit()
    db.refresh(org)
    user = User(
        organization_id=org.id,
        email=email,
        name=data.name.strip(),
        password_hash=hash_password(data.password),
        is_admin=bool(ADMIN_EMAIL and email == ADMIN_EMAIL),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    response.set_cookie("leadradar_session", sign_session(user.id), httponly=True, samesite="lax", secure=BASE_URL.startswith("https://"), max_age=60 * 60 * 24 * 14)

    # Analyze immediately enough to create a useful profile, without blocking future UI actions.
    try:
        analysis = await analyze_site(org.site_url)
        profile = SearchProfile(
            organization_id=org.id,
            name="Основной профиль",
            products=dumps_list(analysis["products"]),
            services=dumps_list(analysis["services"]),
            keywords=dumps_list(analysis["keywords"]),
            minus_words=dumps_list(analysis["minus_words"]),
            regions=dumps_list(analysis["regions"]),
            customer_types=dumps_list(analysis["customer_types"]),
            min_score=60,
            schedule_hours=6,
            next_run_at=utcnow(),
        )
        db.add(profile)
        db.commit()
    except Exception:
        profile = SearchProfile(
            organization_id=org.id,
            name="Основной профиль",
            keywords=dumps_list([urlparse(org.site_url).netloc]),
            minus_words=dumps_list(["вакансия", "работа", "резюме"]),
            regions=dumps_list(["Россия"]),
            min_score=60,
            schedule_hours=6,
            next_run_at=utcnow(),
        )
        db.add(profile)
        db.commit()
    return {"ok": True}


@app.post("/api/auth/login")
def login(data: LoginIn, response: Response, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == data.email.strip().lower()))
    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(401, "Invalid email or password")
    response.set_cookie("leadradar_session", sign_session(user.id), httponly=True, samesite="lax", secure=BASE_URL.startswith("https://"), max_age=60 * 60 * 24 * 14)
    return {"ok": True}


@app.post("/api/auth/logout")
def logout(response: Response):
    response.delete_cookie("leadradar_session")
    return {"ok": True}


@app.get("/api/me")
def me(user: User = Depends(current_user), db: Session = Depends(get_db)):
    org = user_org(db, user)
    return {
        "user": {"id": user.id, "email": user.email, "name": user.name, "is_admin": user.is_admin},
        "organization": {
            "id": org.id,
            "name": org.name,
            "site_url": org.site_url,
            "email_recipients": org.email_recipients,
            "api_key": org.api_key,
            "telegram_link_code": org.telegram_link_code,
            "telegram_connected": bool(org.telegram_chat_id),
        },
        "system": {
            "demo_mode": DEMO_MODE,
            "live_search": bool(YANDEX_API_KEY and YANDEX_FOLDER_ID) or bool(SERPAPI_KEY),
            "telegram_configured": bool(TELEGRAM_BOT_TOKEN),
            "smtp_configured": bool(SMTP_HOST and SMTP_FROM),
            "openai_configured": bool(OPENAI_API_KEY),
        },
    }


@app.post("/api/analyze-site")
async def analyze_site_endpoint(user: User = Depends(current_user), db: Session = Depends(get_db)):
    org = user_org(db, user)
    return await analyze_site(org.site_url)


@app.post("/api/rebuild-main-profile")
async def rebuild_main_profile(user: User = Depends(current_user), db: Session = Depends(get_db)):
    org = user_org(db, user)
    analysis = await analyze_site(org.site_url)
    p = db.scalar(select(SearchProfile).where(SearchProfile.organization_id == org.id).order_by(SearchProfile.id.asc()))
    if not p:
        p = SearchProfile(organization_id=org.id, name="Основной профиль")
        db.add(p)
    p.products = dumps_list(analysis["products"])
    p.services = dumps_list(analysis["services"])
    p.keywords = dumps_list(analysis["keywords"])
    p.minus_words = dumps_list(analysis["minus_words"])
    p.regions = dumps_list(analysis["regions"])
    p.customer_types = dumps_list(analysis["customer_types"])
    p.next_run_at = utcnow()
    db.commit()
    db.refresh(p)
    return {"analysis": analysis, "profile": profile_to_dict(p)}


@app.get("/api/v1/search-profiles")
def list_profiles(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(SearchProfile).where(SearchProfile.organization_id == user.organization_id).order_by(SearchProfile.id.asc())).all()
    return [profile_to_dict(x) for x in rows]


@app.post("/api/v1/search-profiles")
def create_profile(data: ProfileIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = SearchProfile(
        organization_id=user.organization_id,
        name=data.name,
        products=dumps_list(data.products),
        services=dumps_list(data.services),
        keywords=dumps_list(data.keywords),
        minus_words=dumps_list(data.minus_words),
        regions=dumps_list(data.regions),
        customer_types=dumps_list(data.customer_types),
        min_score=max(0, min(100, data.min_score)),
        min_budget=data.min_budget,
        schedule_hours=max(1, data.schedule_hours),
        is_active=data.is_active,
        next_run_at=utcnow(),
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return profile_to_dict(p)


@app.put("/api/v1/search-profiles/{profile_id}")
def update_profile(profile_id: int, data: ProfileIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = db.scalar(select(SearchProfile).where(SearchProfile.id == profile_id, SearchProfile.organization_id == user.organization_id))
    if not p:
        raise HTTPException(404, "Profile not found")
    p.name = data.name
    p.products = dumps_list(data.products)
    p.services = dumps_list(data.services)
    p.keywords = dumps_list(data.keywords)
    p.minus_words = dumps_list(data.minus_words)
    p.regions = dumps_list(data.regions)
    p.customer_types = dumps_list(data.customer_types)
    p.min_score = max(0, min(100, data.min_score))
    p.min_budget = data.min_budget
    p.schedule_hours = max(1, data.schedule_hours)
    p.is_active = data.is_active
    if p.next_run_at is None:
        p.next_run_at = utcnow()
    db.commit()
    return profile_to_dict(p)


@app.post("/api/v1/search-profiles/{profile_id}/run")
async def run_profile(profile_id: int, background: BackgroundTasks, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = db.scalar(select(SearchProfile).where(SearchProfile.id == profile_id, SearchProfile.organization_id == user.organization_id))
    if not p:
        raise HTTPException(404, "Profile not found")
    background.add_task(run_profile_search, profile_id)
    return {"accepted": True, "profile_id": profile_id}


@app.get("/api/v1/opportunities")
def list_opportunities(
    min_score: int = 0,
    status: Optional[str] = None,
    limit: int = 200,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    q = select(Opportunity).where(Opportunity.organization_id == user.organization_id, Opportunity.relevance_score >= min_score)
    if status:
        q = q.where(Opportunity.pipeline_status == status)
    q = q.order_by(Opportunity.created_at.desc()).limit(min(max(limit, 1), 500))
    return [opportunity_to_dict(x) for x in db.scalars(q).all()]


@app.get("/api/v1/opportunities/{opportunity_id}")
def get_opportunity(opportunity_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    o = db.scalar(select(Opportunity).where(Opportunity.id == opportunity_id, Opportunity.organization_id == user.organization_id))
    if not o:
        raise HTTPException(404, "Opportunity not found")
    return opportunity_to_dict(o)


@app.post("/api/v1/opportunities/{opportunity_id}/status")
def update_status(opportunity_id: str, data: StatusIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if data.status not in STATUSES:
        raise HTTPException(400, "Unknown status")
    o = db.scalar(select(Opportunity).where(Opportunity.id == opportunity_id, Opportunity.organization_id == user.organization_id))
    if not o:
        raise HTTPException(404, "Opportunity not found")
    o.pipeline_status = data.status
    o.updated_at = utcnow()
    db.commit()
    return opportunity_to_dict(o)


@app.get("/api/v1/analytics")
def analytics(user: User = Depends(current_user), db: Session = Depends(get_db)):
    org_id = user.organization_id
    today = utcnow() - timedelta(hours=24)
    found_24h = db.scalar(select(func.count()).select_from(Opportunity).where(Opportunity.organization_id == org_id, Opportunity.created_at >= today)) or 0
    total = db.scalar(select(func.count()).select_from(Opportunity).where(Opportunity.organization_id == org_id)) or 0
    in_work = db.scalar(select(func.count()).select_from(Opportunity).where(Opportunity.organization_id == org_id, Opportunity.pipeline_status == "В работе")) or 0
    sum_amount = db.scalar(select(func.coalesce(func.sum(Opportunity.amount), 0)).where(Opportunity.organization_id == org_id)) or 0
    delivered = db.scalar(select(func.count()).select_from(DeliveryJob).where(DeliveryJob.organization_id == org_id, DeliveryJob.status == "delivered")) or 0
    failed = db.scalar(select(func.count()).select_from(DeliveryJob).where(DeliveryJob.organization_id == org_id, DeliveryJob.status == "failed")) or 0
    return {"found_24h": found_24h, "total": total, "in_work": in_work, "sum_amount": sum_amount, "delivered": delivered, "delivery_failed": failed}


@app.get("/api/v1/deliveries")
def deliveries(user: User = Depends(current_user), db: Session = Depends(get_db)):
    jobs = db.scalars(select(DeliveryJob).where(DeliveryJob.organization_id == user.organization_id).order_by(DeliveryJob.id.desc()).limit(200)).all()
    return [{
        "id": j.id,
        "opportunity_id": j.opportunity_id,
        "channel": j.channel,
        "status": j.status,
        "attempts": j.attempts,
        "last_error": j.last_error,
        "next_attempt_at": j.next_attempt_at.isoformat() if j.next_attempt_at else None,
        "delivered_at": j.delivered_at.isoformat() if j.delivered_at else None,
        "created_at": j.created_at.isoformat(),
    } for j in jobs]


@app.get("/api/v1/search-runs")
def search_runs(user: User = Depends(current_user), db: Session = Depends(get_db)):
    runs = db.scalars(select(SearchRun).where(SearchRun.organization_id == user.organization_id).order_by(SearchRun.id.desc()).limit(100)).all()
    return [{
        "id": r.id,
        "profile_id": r.search_profile_id,
        "status": r.status,
        "queries_count": r.queries_count,
        "raw_results_count": r.raw_results_count,
        "created_count": r.created_count,
        "error": r.error,
        "started_at": r.started_at.isoformat(),
        "finished_at": r.finished_at.isoformat() if r.finished_at else None,
    } for r in runs]


@app.get("/api/v1/sources")
def sources(user: User = Depends(current_user)):
    return [
        {"name": "Yandex Search API", "status": "connected" if (YANDEX_API_KEY and YANDEX_FOLDER_ID) else "not_configured"},
        {"name": "SERP API", "status": "connected" if SERPAPI_KEY else "not_configured"},
        {"name": "EIS discovery via web search", "status": "connected" if (YANDEX_API_KEY and YANDEX_FOLDER_ID) else "demo" if DEMO_MODE else "not_configured"},
    ]


@app.put("/api/settings")
def update_settings(data: SettingsIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    org = user_org(db, user)
    org.email_recipients = data.email_recipients.strip()
    db.commit()
    return {"ok": True}


@app.get("/api/v1/integrations")
def list_integrations(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(Integration).where(Integration.organization_id == user.organization_id).order_by(Integration.id.desc())).all()
    return [{"id": x.id, "name": x.name, "type": x.type, "endpoint_url": x.endpoint_url, "min_relevance_score": x.min_relevance_score, "is_active": x.is_active} for x in rows]


@app.post("/api/v1/integrations")
def create_integration(data: IntegrationIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    integ = Integration(
        organization_id=user.organization_id,
        name=data.name,
        endpoint_url=data.endpoint_url,
        secret=data.secret,
        api_key=data.api_key,
        min_relevance_score=max(0, min(100, data.min_relevance_score)),
        is_active=data.is_active,
    )
    db.add(integ)
    db.commit()
    db.refresh(integ)
    return {"id": integ.id, "ok": True}


@app.post("/api/v1/integrations/{integration_id}/test")
async def test_integration(integration_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    integ = db.scalar(select(Integration).where(Integration.id == integration_id, Integration.organization_id == user.organization_id))
    if not integ:
        raise HTTPException(404, "Integration not found")
    sample = db.scalar(select(Opportunity).where(Opportunity.organization_id == user.organization_id).order_by(Opportunity.created_at.desc()))
    if not sample:
        raise HTTPException(400, "Сначала создайте хотя бы одну Opportunity")
    ok, code, err = await send_webhook(integ, sample)
    return {"ok": ok, "http_code": code, "error": err}


@app.get("/api/v1/export.xlsx")
def export_xlsx(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(Opportunity).where(Opportunity.organization_id == user.organization_id).order_by(Opportunity.created_at.desc())).all()
    wb = Workbook()
    ws = wb.active
    ws.title = "Opportunities"
    headers = ["ID", "Тип", "Название", "Источник", "URL", "Регион", "Бюджет", "Валюта", "Срок", "Актуальность", "Релевантность", "Статус", "AI summary", "Создано"]
    ws.append(headers)
    for o in rows:
        ws.append([o.id, o.type, o.title, o.source, o.source_url, o.region, o.amount, o.currency, o.deadline.isoformat() if o.deadline else None, o.actuality_status, o.relevance_score, o.pipeline_status, o.ai_summary, o.created_at.isoformat()])
    stream = io.BytesIO()
    wb.save(stream)
    stream.seek(0)
    return StreamingResponse(stream, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={"Content-Disposition": "attachment; filename=leadradar-opportunities.xlsx"})


@app.post("/api/telegram/webhook/{secret}")
async def telegram_webhook(secret: str, request: Request, db: Session = Depends(get_db)):
    if secret != TELEGRAM_WEBHOOK_SECRET:
        raise HTTPException(403, "Forbidden")
    data = await request.json()
    message = data.get("message") or {}
    text = (message.get("text") or "").strip()
    chat_id = str((message.get("chat") or {}).get("id") or "")
    if text.startswith("/start") and chat_id:
        parts = text.split(maxsplit=1)
        if len(parts) == 2:
            code = parts[1].strip().upper()
            org = db.scalar(select(Organization).where(Organization.telegram_link_code == code))
            if org:
                org.telegram_chat_id = chat_id
                db.commit()
                await telegram_simple(chat_id, f"LeadRadar AI подключён к компании «{org.name}».")
                return {"ok": True}
        await telegram_simple(chat_id, "Пришлите /start КОД_ПРИВЯЗКИ из личного кабинета LeadRadar AI.")
        return {"ok": True}

    callback = data.get("callback_query") or {}
    if callback:
        cb_data = callback.get("data", "")
        cb_id = callback.get("id")
        if cb_data.startswith("status:"):
            _, opp_id, status = cb_data.split(":", 2)
            o = db.get(Opportunity, opp_id)
            if o and str((callback.get("message") or {}).get("chat", {}).get("id")) == (db.get(Organization, o.organization_id).telegram_chat_id or "") and status in STATUSES:
                o.pipeline_status = status
                o.updated_at = utcnow()
                db.commit()
                await telegram_answer_callback(cb_id, f"Статус: {status}")
                return {"ok": True}
        await telegram_answer_callback(cb_id, "Не удалось изменить статус")
    return {"ok": True}


async def telegram_simple(chat_id: str, text: str):
    if not TELEGRAM_BOT_TOKEN:
        return
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            await client.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage", json={"chat_id": chat_id, "text": text})
    except Exception:
        pass


async def telegram_answer_callback(callback_query_id: str, text: str):
    if not TELEGRAM_BOT_TOKEN or not callback_query_id:
        return
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            await client.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/answerCallbackQuery", json={"callback_query_id": callback_query_id, "text": text})
    except Exception:
        pass


@app.get("/api/admin/overview")
def admin_overview(user: User = Depends(current_user), db: Session = Depends(get_db)):
    if not user.is_admin:
        raise HTTPException(403, "Admin only")
    return {
        "organizations": db.scalar(select(func.count()).select_from(Organization)) or 0,
        "users": db.scalar(select(func.count()).select_from(User)) or 0,
        "profiles": db.scalar(select(func.count()).select_from(SearchProfile)) or 0,
        "opportunities": db.scalar(select(func.count()).select_from(Opportunity)) or 0,
        "delivery_failed": db.scalar(select(func.count()).select_from(DeliveryJob).where(DeliveryJob.status == "failed")) or 0,
    }
