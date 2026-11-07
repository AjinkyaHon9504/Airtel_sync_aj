"""Udyam Express API + static web app.  Run:  uvicorn app.main:app --port 8000"""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import advisor, backoffice, kyc, llm
from .core import catalogue, lookup_gstin, lookup_udyam, mask

app = FastAPI(title="Udyam Express", version="1.0")
STATIC = Path(__file__).resolve().parent.parent / "static"
CONSENTS: list[dict] = []   # append-only, hash-chained consent ledger
KYC_RESULTS: dict[str, dict] = {}
NOTICE_VERSION = "2026-07-v1"
PURPOSES = {
    "kyc": "Verify your business identity (GST, Udyam, signatory, address) to activate services — required by telecom rules",
    "registry": "Look up your GSTIN/Udyam in government registries",
    "contact": "Contact you about this order and installation",
    "marketing": "Send offers for other Accel Business services (optional)",
}


class Start(BaseModel):
    lang: str = "en"
    channel: str = "web"


class Msg(BaseModel):
    session_id: str
    text: str


class Select(BaseModel):
    session_id: str
    tier: str | None = None
    toggles: dict[str, bool] | None = None
    term: int | None = None


class Consent(BaseModel):
    session_id: str
    purposes: list[str]


class OrderIn(BaseModel):
    session_id: str
    name: str = ""
    phone: str = ""


@app.get("/api/health")
def health():
    return {"ok": True, "llm": llm.enabled(), "llm_stats": llm.STATS, "products": len(catalogue())}


@app.post("/api/advisor/start")
def adv_start(b: Start):
    return advisor.start(b.lang, b.channel)


@app.post("/api/advisor/message")
def adv_msg(b: Msg):
    if b.session_id not in advisor.SESSIONS:
        raise HTTPException(404, "session not found")
    return advisor.handle(b.session_id, b.text[:1000])


@app.post("/api/advisor/select")
def adv_select(b: Select):
    if b.session_id not in advisor.SESSIONS or not advisor.SESSIONS[b.session_id]["rec"]:
        raise HTTPException(404, "no quote yet")
    return advisor.select(b.session_id, b.tier, b.toggles, b.term)


@app.get("/api/catalogue")
def cat():
    c = catalogue().reset_index()
    return c.drop(columns=["tiers", "needs_one_of", "segments"]).to_dict("records")


@app.get("/api/registry/gstin/{g}")
def gst(g: str):
    r = lookup_gstin(g)
    if r.get("found"):  # minimise: status + names only, identifiers masked
        return {"found": True, "gstin": mask(r["gstin"], 5), "trade_name": r["trade_name"], "status": r["status"], "state": r["state"]}
    return r


@app.get("/api/registry/udyam/{u}")
def udy(u: str):
    r = lookup_udyam(u)
    if r.get("found"):
        return {"found": True, "enterprise_name": r["enterprise_name"], "enterprise_type": r["enterprise_type"], "city": r["city"]}
    return r


@app.get("/api/kyc/notice")
def notice():
    return {"version": NOTICE_VERSION, "purposes": PURPOSES, "retention_days": 30,
            "controller": "Accel Business (fictional)", "grievance": "privacy@accel.example"}


@app.post("/api/kyc/consent")
def consent(b: Consent):
    if "kyc" not in b.purposes:
        raise HTTPException(400, "KYC consent is required to verify documents")
    prev = CONSENTS[-1]["hash"] if CONSENTS else "GENESIS"
    rec = {"session_id": b.session_id, "purposes": sorted(set(b.purposes) & set(PURPOSES)), "notice": NOTICE_VERSION,
           "at": time.strftime("%Y-%m-%dT%H:%M:%S"), "prev": prev}
    rec["hash"] = hashlib.sha256(json.dumps(rec, sort_keys=True).encode()).hexdigest()
    CONSENTS.append(rec)
    return {"ok": True, "receipt": rec["hash"][:16], "purposes": rec["purposes"]}


@app.post("/api/kyc/withdraw")
def withdraw(b: Consent):
    KYC_RESULTS.pop(b.session_id, None)
    prev = CONSENTS[-1]["hash"] if CONSENTS else "GENESIS"
    rec = {"session_id": b.session_id, "purposes": [], "withdrawn": True, "at": time.strftime("%Y-%m-%dT%H:%M:%S"), "prev": prev}
    rec["hash"] = hashlib.sha256(json.dumps(rec, sort_keys=True).encode()).hexdigest()
    CONSENTS.append(rec)
    return {"ok": True, "erased": True}


def _has_consent(sid: str) -> bool:
    for c in reversed(CONSENTS):
        if c["session_id"] == sid:
            return "kyc" in c["purposes"]
    return False


@app.post("/api/kyc/verify")
async def kyc_verify(session_id: str = Form(...), gst_certificate: UploadFile | None = File(None),
                     udyam_certificate: UploadFile | None = File(None), signatory_id: UploadFile | None = File(None),
                     address_proof: UploadFile | None = File(None)):
    if not _has_consent(session_id):
        raise HTTPException(403, "consent required before upload")
    docs = {}
    for name, f in [("gst_certificate", gst_certificate), ("udyam_certificate", udyam_certificate),
                    ("signatory_id", signatory_id), ("address_proof", address_proof)]:
        if f is not None:
            data = await f.read()
            if len(data) > 8 * 1024 * 1024:
                raise HTTPException(413, f"{name} larger than 8 MB")
            docs[name] = data
    s = advisor.SESSIONS.get(session_id)
    r = kyc.verify(docs, declared_gstin=(s["profile"].gstin if s else None))
    KYC_RESULTS[session_id] = r
    return r


@app.post("/api/kyc/specimen/{applicant}")
def kyc_specimen(applicant: str, session_id: str = "demo"):
    """Demo: run the real pipeline on the specimen documents K01-K12."""
    if applicant.upper() not in {f"K{i:02d}" for i in range(1, 13)}:
        raise HTTPException(404)
    r = kyc.verify(kyc.specimen(applicant.upper()))
    KYC_RESULTS[session_id] = r
    return r


@app.post("/api/orders")
def order(b: OrderIn):
    s = advisor.SESSIONS.get(b.session_id)
    if not s or not s["rec"]:
        raise HTTPException(400, "no quote")
    q = s["rec"]["tiers"][s["tier"]]
    o = backoffice.create_order({"business": s["profile"].legal_name or s["profile"].business_type}, q,
                                KYC_RESULTS.get(b.session_id), {"name": b.name, "phone": b.phone})
    return backoffice.tracker(o["id"])


@app.get("/api/orders/{oid}")
def track(oid: str):
    t = backoffice.tracker(oid.upper())
    if not t:
        raise HTTPException(404, "order not found")
    return t


@app.post("/api/orders/{oid}/advance")
def advance(oid: str):
    backoffice.advance(oid.upper())
    return backoffice.tracker(oid.upper())


@app.get("/api/backoffice/leads")
def bo_leads(segment: str | None = None):
    return {"advisor_handoffs": list(reversed(advisor.LEADS)), **backoffice.winback(40, segment)}


@app.get("/api/backoffice/funnel")
def bo_funnel():
    return backoffice.funnel()


@app.get("/api/backoffice/orders")
def bo_orders():
    return [backoffice.tracker(o) for o in backoffice.ORDERS]


app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")
