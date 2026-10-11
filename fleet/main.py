import json
import logging
import os
import sqlite3
import uuid
from contextlib import asynccontextmanager
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from fastapi import Body, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

from fleet import auth
from fleet.db import ROOT, audit, collection, connect, encode, metadata, migrate, now
from fleet.importer import commit, stage


@asynccontextmanager
async def lifespan(app):
    migrate()
    yield


app = FastAPI(title="Cars · soukromá evidence", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=os.environ.get("FLEET_ALLOWED_HOSTS", "localhost,127.0.0.1,[::1],testserver").split(","))


@app.exception_handler(Exception)
async def server_error(request: Request, exc: Exception):
    reference = uuid.uuid4().hex[:12]
    # Log no request body, password, session cookie, or imported data.
    logging.getLogger("fleet").error("Server error id=%s method=%s path=%s type=%s",
                                   reference, request.method, request.url.path, type(exc).__name__)
    return JSONResponse({"detail": "Při zpracování požadavku nastala chyba serveru. Zkontrolujte Terminál Codespaces.", "request_id": reference},
                        status_code=500, headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff", "Referrer-Policy": "no-referrer"})


@app.middleware("http")
async def privacy(request: Request, call_next):
    path = request.url.path
    public = path in {"/api/health", "/api/auth/status", "/api/auth/login", "/api/auth/setup"}
    if path.startswith("/api/"):
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            origin = request.headers.get("origin")
            if origin and urlsplit(origin).netloc != request.headers.get("host"):
                return JSONResponse({"detail": "Požadavek z jiného webu není povolen."}, status_code=403)
            if request.headers.get("sec-fetch-site") == "cross-site":
                return JSONResponse({"detail": "Požadavek z jiného webu není povolen."}, status_code=403)
            if "application/json" not in request.headers.get("content-type", ""):
                return JSONResponse({"detail": "Použijte JSON."}, status_code=415)
            if int(request.headers.get("content-length", "0")) > 5_000_000:
                return JSONResponse({"detail": "Soubor je příliš velký."}, status_code=413)
        if not public and not auth.authenticated(request.cookies.get("fleet_session")):
            return JSONResponse({"detail": "Přihlaste se pro přístup k soukromým datům."}, status_code=401)
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Content-Security-Policy"] = "default-src 'self'; style-src 'self'; script-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
    return response


class Password(BaseModel):
    password: str = Field(min_length=1, max_length=256)


class IssueUpdate(BaseModel):
    assigned_to: str | None = Field(default=None, max_length=150)
    close: bool = False
    evidence_type: str | None = None
    evidence_title: str | None = Field(default=None, max_length=300)
    evidence_url: str | None = Field(default=None, max_length=1000)
    evidence_date: date | None = None
    closure_note: str | None = Field(default=None, max_length=2000)


class Reading(BaseModel):
    km: str = Field(max_length=20)
    date: date
    evidence: str = Field(min_length=5, max_length=1000)


def user_session(token):
    response = JSONResponse({"ok": True})
    response.set_cookie("fleet_session", token, httponly=True, samesite="strict", secure=os.environ.get("FLEET_SECURE_COOKIES") == "1", max_age=43200)
    return response


@app.get("/api/health")
def health():
    with connect() as con:
        con.execute("SELECT 1").fetchone()
    return {"status": "ok"}


@app.get("/api/auth/status")
def auth_status(request: Request):
    return {"configured": auth.configured(), "authenticated": auth.authenticated(request.cookies.get("fleet_session"))}


@app.post("/api/auth/setup")
def setup_password(body: Password, request: Request):
    # First-admin enrollment is only allowed from the local machine.
    # Remote deployments must initialize an administrator locally before exposure.
    if request.client and request.client.host not in {"127.0.0.1", "::1", "testclient"}:
        raise HTTPException(403, "První heslo nastavte místně před vzdáleným nasazením.")
    try:
        auth.create_user(body.password)
    except sqlite3.IntegrityError:
        raise HTTPException(409, "Heslo již bylo nastaveno. Přihlaste se.")
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    token, _ = auth.login(body.password, request.client.host if request.client else "local")
    return user_session(token)


@app.post("/api/auth/login")
def login(body: Password, request: Request):
    token, limited = auth.login(body.password, request.client.host if request.client else "local")
    if limited:
        raise HTTPException(429, "Příliš mnoho pokusů. Zkuste to za 15 minut.")
    if token is None:
        raise HTTPException(401, "Nesprávné heslo.")
    return user_session(token)


@app.post("/api/auth/logout")
def logout(request: Request):
    with connect() as con, con:
        con.execute("DELETE FROM sessions WHERE token_hash=?", (auth.token_hash(request.cookies.get("fleet_session", "")),))
    response = JSONResponse({"ok": True})
    response.delete_cookie("fleet_session")
    return response


def required_evidence(issue):
    topic = issue["topic"].lower()
    if issue["priority"] == "P0":
        return "insurer_confirmation"
    if "stk" in topic or "tk" == topic:
        return "inspection_certificate"
    if "vin" in topic or "rz" in topic or "registr" in topic:
        return "registration_record"
    if "vlastn" in topic or "prodej" in topic or "titul" in topic:
        return "ownership_title"
    return "supporting_document"


def issues(con):
    updates = {r["issue_id"]: dict(r) for r in con.execute("SELECT * FROM issue_updates")}
    result = []
    for issue in collection(con, "issues"):
        issue["required_evidence"] = required_evidence(issue)
        update = updates.get(issue["issue_id"])
        if update:
            issue.update(update)
        result.append(issue)
    return sorted(result, key=lambda i: (i["state"] == "Uzavřeno", i["priority"], i["deadline"] or "9999", i["issue_id"]))


def with_readings(con, vehicle):
    candidates = [x for x in collection(con, "odometer_readings") if x["asset_id"] == vehicle["asset_id"] and x.get("date")]
    candidates += [{**dict(r), "km": float(r["km"]), "verification": "Ruční doložený odečet", "source_id": None, "location": r["evidence"]}
                   for r in con.execute("SELECT * FROM manual_readings WHERE asset_id=?", (vehicle["asset_id"],))]
    if candidates:
        vehicle["last_reading"] = max(candidates, key=lambda x: x["date"])
    return vehicle


@app.get("/api/dashboard")
def dashboard():
    with connect() as con:
        vehicles = [with_readings(con, x) for x in collection(con, "vehicles")]
        tasks = issues(con)
        meta = metadata(con)
        return {"vehicles": vehicles, "issues": tasks, "metadata": meta,
                "premium_lines": collection(con, "premium_lines"), "sources": collection(con, "sources"),
                "counts": {"vehicles": len(vehicles), "candidates": sum(v["asset_state"] == "Kandidát aktuálního majetku" for v in vehicles),
                           "open_issues": sum(i["state"] != "Uzavřeno" for i in tasks), "p0": sum(i["priority"] == "P0" and i["state"] != "Uzavřeno" for i in tasks)},
                "today": datetime.now(ZoneInfo("Europe/Paris")).date().isoformat()}


@app.get("/api/vehicles/{asset_id}")
def detail(asset_id: str):
    with connect() as con:
        row = con.execute("SELECT payload FROM vehicles WHERE asset_id=?", (asset_id,)).fetchone()
        if row is None:
            raise HTTPException(404, "Vozidlo nenalezeno.")
        vehicle = with_readings(con, json.loads(row[0]))
        related = {name: [x for x in collection(con, name) if x.get("asset_id") == asset_id]
                   for name in ("insurance", "operations", "acquisitions", "premium_lines", "odometer_readings", "rides", "source_observations")}
        related["issues"] = [x for x in issues(con) if x.get("asset_id") == asset_id]
        related["manual_readings"] = [dict(r) for r in con.execute("SELECT * FROM manual_readings WHERE asset_id=? ORDER BY date DESC", (asset_id,))]
        refs = set(vehicle.get("source_ids", []))
        for rows in related.values():
            for x in rows:
                refs.update(x.get("source_ids", []))
                if x.get("source_id"):
                    refs.add(x["source_id"])
        return {"vehicle": vehicle, **related, "sources": [x for x in collection(con, "sources") if x["source_id"] in refs]}


@app.post("/api/vehicles/{asset_id}/readings")
def add_reading(asset_id: str, body: Reading):
    try:
        km = Decimal(body.km)
        if not km.is_finite() or km < 0 or km > 10000000:
            raise InvalidOperation
    except InvalidOperation:
        raise HTTPException(422, "Zadejte platný nezáporný počet kilometrů.")
    if body.date > datetime.now(ZoneInfo("Europe/Paris")).date():
        raise HTTPException(422, "Odečet nemůže být z budoucnosti.")
    with connect() as con, con:
        if not con.execute("SELECT 1 FROM vehicles WHERE asset_id=?", (asset_id,)).fetchone():
            raise HTTPException(404, "Vozidlo nenalezeno.")
        reading_id = str(uuid.uuid4())
        con.execute("INSERT INTO manual_readings VALUES(?,?,?,?,?,?)", (reading_id, asset_id, str(km), body.date.isoformat(), body.evidence, now()))
        audit(con, "reading_added", asset_id, body.model_dump(mode="json"))
    return {"id": reading_id, "ok": True}


@app.patch("/api/issues/{issue_id}")
def update_issue(issue_id: str, body: IssueUpdate):
    with connect() as con, con:
        issue = next((i for i in issues(con) if i["issue_id"] == issue_id), None)
        if issue is None:
            raise HTTPException(404, "Úkol nenalezen.")
        if body.close:
            evidence_ok = body.evidence_type == issue["required_evidence"] and all((body.evidence_title and body.evidence_title.strip(), body.evidence_url, body.evidence_date, body.closure_note and body.closure_note.strip()))
            if not evidence_ok or urlsplit(body.evidence_url or "").scheme != "https":
                raise HTTPException(422, "K uzavření doplňte požadovaný druh dokladu, jeho název, HTTPS odkaz, datum a zdůvodnění.")
            if body.evidence_date > datetime.now(ZoneInfo("Europe/Paris")).date():
                raise HTTPException(422, "Datum důkazu nemůže být z budoucnosti.")
        old = con.execute("SELECT * FROM issue_updates WHERE issue_id=?", (issue_id,)).fetchone()
        if not body.close and old:
            con.execute("UPDATE issue_updates SET assigned_to=? WHERE issue_id=?", (body.assigned_to, issue_id))
        else:
            con.execute("INSERT INTO issue_updates VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(issue_id) DO UPDATE SET assigned_to=excluded.assigned_to,state=excluded.state,evidence_type=excluded.evidence_type,evidence_title=excluded.evidence_title,evidence_url=excluded.evidence_url,evidence_date=excluded.evidence_date,closure_note=excluded.closure_note,closed_at=excluded.closed_at",
                        (issue_id, body.assigned_to, "Uzavřeno" if body.close else "Otevřeno", body.evidence_type, body.evidence_title,
                         body.evidence_url, body.evidence_date.isoformat() if body.evidence_date else None, body.closure_note, now() if body.close else None))
        audit(con, "issue_closed_with_manual_evidence" if body.close else "issue_assigned", issue_id, body.model_dump(mode="json"))
    return {"ok": True}


@app.post("/api/imports/preview")
def preview(payload: dict = Body(...)):
    try:
        return stage(payload)
    except (ValueError, KeyError, TypeError) as exc:
        raise HTTPException(422, str(exc))


@app.post("/api/imports/{import_id}/commit")
def import_commit(import_id: str):
    try:
        return commit(import_id)
    except ValueError as exc:
        raise HTTPException(422, str(exc))


@app.get("/api/export")
def export():
    with connect() as con:
        return {"exported_at": now(), "metadata": metadata(con),
                **{name: collection(con, name) for name in ("vehicles", "sources", "insurance", "premium_lines", "acquisitions", "operations", "odometer_readings", "rides", "source_observations")},
                "issues": issues(con), "manual_readings": [dict(r) for r in con.execute("SELECT * FROM manual_readings")],
                "audit_log": [dict(r) for r in con.execute("SELECT * FROM audit_log ORDER BY id")]}


@app.get("/api/connectors")
def connectors():
    return [{"name": "Google Drive a Gmail", "state": "disabled", "reason": "Přístup k originálním dokladům vyžaduje autorizaci účtu. Odkazy ve zdrojích můžete otevřít ručně."},
            {"name": "Registr silničních vozidel", "state": "disabled", "reason": "Živá kontrola nebyla provedena. Doplňte aktuální výpis nebo příslušné přístupové oprávnění."},
            {"name": "Tržní ocenění", "state": "disabled", "reason": "Cenové řady nejsou k dispozici. Pro automatický odhad je nutný povolený zdroj a licence."}]


app.mount("/static", StaticFiles(directory=ROOT / "web"), name="static")


@app.get("/")
def index():
    return FileResponse(ROOT / "web/index.html")
