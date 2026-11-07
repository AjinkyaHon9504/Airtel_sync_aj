"""Smart KYC: OCR on our own server -> field extraction -> registry & consistency checks -> verdict.

Verdicts
  verified       all checks pass (notes may be attached)
  needs_action   owner can fix it now (re-upload, clearer photo, newer bill, missing document)
  manual_review  possible tampering / mismatch: a person checks before activation
  rejected       cannot proceed (GSTIN cancelled or suspended)
Images are processed in memory and never written to disk by this module.
"""
from __future__ import annotations

import re
from datetime import date

import cv2
import numpy as np
import pytesseract

from .core import DATA, TODAY, gstin_checksum, gstin_registry, gstin_valid, lookup_udyam, mask, udyam_registry

DOCS = {
    "gst_certificate": "GST certificate",
    "udyam_certificate": "Udyam certificate",
    "signatory_id": "Authorised signatory ID",
    "address_proof": "Address proof (utility bill)",
}
REQUIRED = ["gst_certificate", "udyam_certificate", "signatory_id", "address_proof"]
ADDRESS_MAX_AGE = 90
BLUR_MIN = 60.0


# ---------------------------------------------------------------- image -> text
def _deskew(gray: np.ndarray) -> tuple[np.ndarray, float]:
    small = cv2.resize(gray, None, fx=0.35, fy=0.35)
    inv = 255 - cv2.threshold(small, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
    best, best_a = -1.0, 0.0
    h, w = inv.shape
    for a in np.arange(-10, 10.5, 0.5):
        m = cv2.getRotationMatrix2D((w / 2, h / 2), a, 1)
        rot = cv2.warpAffine(inv, m, (w, h))
        score = float(np.var(rot.sum(axis=1)))
        if score > best:
            best, best_a = score, a
    if abs(best_a) < 0.75:
        return gray, 0.0
    H, W = gray.shape
    m = cv2.getRotationMatrix2D((W / 2, H / 2), best_a, 1)
    return cv2.warpAffine(gray, m, (W, H), borderValue=255), float(best_a)


def read_image(data: bytes) -> dict:
    arr = np.frombuffer(data, np.uint8)
    gray = cv2.imdecode(arr, cv2.IMREAD_GRAYSCALE)
    if gray is None:
        return {"ok": False, "error": "not an image", "text": "", "blur": 0, "skew": 0}
    blur = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    fixed, skew = _deskew(gray)
    text = pytesseract.image_to_string(fixed, config="--psm 6")
    return {"ok": True, "text": text, "blur": round(blur, 1), "skew": skew}


# ---------------------------------------------------------------- text -> fields
def _after(label: str, text: str) -> str | None:
    m = re.search(label + r"[\s:.|]*([^\n]+)", text, re.I)
    return m.group(1).strip(" :|.") if m else None


LETTER_POS = {2, 3, 4, 5, 6, 11, 13}
DIGIT_POS = {0, 1, 7, 8, 9, 10}
TO_DIGIT = str.maketrans("OIlSBZ", "011582")
TO_LETTER = str.maketrans("0158", "OISB")


def normalise_gstin(raw: str | None) -> tuple[str | None, bool]:
    """Fix common OCR confusions (O/0, I/1) by position. Returns (gstin, corrected?)."""
    if not raw:
        return None, False
    s = re.sub(r"[^A-Z0-9]", "", raw.upper())
    if len(s) != 15:
        return (s or None), False
    out = []
    for i, ch in enumerate(s):
        if i in DIGIT_POS:
            ch = ch.translate(TO_DIGIT)
        elif i in LETTER_POS:
            ch = ch.translate(TO_LETTER)
        out.append(ch)
    g = "".join(out)
    if not gstin_valid(g) and g[12] == "O":
        g = g[:12] + "0" + g[13:]
    if not gstin_valid(g) and g[14] in "O0":  # check digit can be either
        alt = g[:14] + ("0" if g[14] == "O" else "O")
        if gstin_valid(alt):
            g = alt
    if not gstin_valid(g):
        # one OCR look-alike swap that yields a valid GSTIN which exists in the registry
        reg = gstin_registry().index
        for i, ch in enumerate(g):
            for alt_ch in LOOKALIKE.get(ch, ""):
                cand = g[:i] + alt_ch + g[i + 1:]
                if gstin_valid(cand) and cand in reg:
                    return cand, True
    return g, g != s


LOOKALIKE = {"I": "TJL1", "T": "I", "J": "I", "L": "I", "1": "I", "O": "0DQ", "0": "OD", "D": "O0", "Q": "O",
             "S": "5", "5": "S", "B": "8", "8": "B", "Z": "2", "2": "Z", "G": "6", "6": "G", "U": "V", "V": "U"}


def extract(doc: str, text: str) -> dict:
    t = text.replace("|", " ")
    f: dict = {}
    if doc == "gst_certificate":
        m = re.search(r"GSTIN\s*[:.]?\s*([0-9OIlSBZ][0-9A-Z]{14})", t, re.I)
        f["gstin_raw"] = m.group(1) if m else None
        f["gstin"], f["gstin_ocr_corrected"] = normalise_gstin(f["gstin_raw"])
        f["legal_name"] = _after(r"Legal name", t)
        f["trade_name"] = _after(r"Trade name", t)
        f["constitution"] = _after(r"Constitution", t)
        addr = re.search(r"Address of principal\s*(.+?)\n\s*place of business\s*(.*?)\n", t, re.I | re.S)
        f["address"] = re.sub(r"\s+", " ", (addr.group(1) + " " + addr.group(2)) if addr else "").replace(" -", "").strip() or None
        f["liability_date"] = _date(_after(r"Date of liability", t))
    elif doc == "udyam_certificate":
        m = re.search(r"UDYAM\s*-?\s*[A-Z]{2}\s*-?\s*\d{2}\s*-?\s*\d{7}", t, re.I)
        f["udyam_number"] = re.sub(r"\s+", "", m.group(0)).upper() if m else None
        f["enterprise_name"] = _after(r"Enterprise name", t)
        f["city"] = _after(r"\bCity", t)
        f["state"] = _after(r"\bState", t)
    elif doc == "address_proof":
        f["billed_to"] = _after(r"Billed to", t)
        addr = re.search(r"Supply address\s*(.+?)(?:\n\s*Bill date|\nBill)", t, re.I | re.S)
        f["address"] = re.sub(r"\s+", " ", addr.group(1)).strip() if addr else None
        f["bill_date"] = _date(_after(r"Bill date", t))
    elif doc == "signatory_id":
        lines = [l.strip() for l in t.splitlines() if l.strip()]
        def nxt(label):
            for i, l in enumerate(lines):
                if re.fullmatch(label, l, re.I) and i + 1 < len(lines):
                    return lines[i + 1]
            return _after(label, t)
        f["name"] = nxt(r"Name")
        f["designation"] = nxt(r"Designation")
        f["business"] = nxt(r"For business")
        f["id_no"] = nxt(r"ID no\.?")
        f["valid_till"] = _date(nxt(r"Valid till"))
    return f


def _date(s: str | None) -> date | None:
    if not s:
        return None
    m = re.search(r"(20\d\d)-(\d\d)-(\d\d)", s)
    try:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3))) if m else None
    except ValueError:
        return None


# ---------------------------------------------------------------- comparison helpers
def _norm(s: str | None) -> str:
    s = (s or "").lower()
    s = re.sub(r"\b(pvt|private|ltd|limited|llp|m/s|the)\b", " ", s)
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def similar(a: str | None, b: str | None) -> float:
    A, B = set(_norm(a).split()), set(_norm(b).split())
    if not A or not B:
        return 0.0
    return len(A & B) / len(A | B)


def _prop(legal: str | None) -> tuple[str | None, str | None]:
    m = re.match(r"\s*(.+?)\s*\(Prop\.?\s*(.+?)\)", legal or "")
    return (m.group(1), m.group(2)) if m else (None, None)


# ---------------------------------------------------------------- verification
def verify(docs: dict[str, bytes], declared_gstin: str | None = None, declared_udyam: str | None = None) -> dict:
    checks: list[dict] = []
    reads: dict[str, dict] = {}

    def add(code, status, doc, title, detail, fix=None, severity=None):
        sev = severity or {"pass": "ok", "warn": "note", "fail": "needs_action"}[status]
        checks.append({"code": code, "status": status, "doc": doc, "title": title, "detail": detail, "fix": fix, "severity": sev})

    for d in REQUIRED:
        if d not in docs:
            add(f"present.{d}", "fail", d, f"{DOCS[d]} missing", f"No {DOCS[d].lower()} was uploaded.",
                f"Upload your {DOCS[d].lower()}" + (" — or we can fetch it from the Udyam registry with your consent." if d == "udyam_certificate" else "."))
            continue
        r = read_image(docs[d])
        r["fields"] = extract(d, r["text"]) if r["ok"] else {}
        reads[d] = r
        if not r["ok"]:
            add(f"quality.{d}", "fail", d, f"{DOCS[d]} unreadable", "The file isn't an image we can read.", "Upload a JPG or PNG photo/scan.")
        elif r["blur"] < BLUR_MIN or len(r["text"].strip()) < 30:
            add(f"quality.{d}", "fail", d, f"{DOCS[d]} too blurry to read", f"Sharpness score {r['blur']} (need ≥ {BLUR_MIN}). We don't guess fields from a blurry image.",
                "Retake the photo in good light, or fetch the certificate from DigiLocker.")
            r["fields"] = {}
        elif r["skew"]:
            add(f"quality.{d}", "warn", d, f"{DOCS[d]} was tilted", f"Straightened automatically by {abs(r['skew']):.1f}°.")

    gst = reads.get("gst_certificate", {}).get("fields", {})
    udy = reads.get("udyam_certificate", {}).get("fields", {})
    bill = reads.get("address_proof", {}).get("fields", {})
    sid = reads.get("signatory_id", {}).get("fields", {})
    reg = None

    # ---- GST
    if gst:
        g = gst.get("gstin")
        if gst.get("gstin_ocr_corrected") and g and gstin_valid(g):
            add("gstin.ocr", "warn", "gst_certificate", "GSTIN read corrected", "OCR confused similar characters (O/0); corrected using the GSTIN format rules.")
        if not g:
            add("gstin.read", "fail", "gst_certificate", "GSTIN not readable", "We couldn't read a GSTIN on the certificate.", "Upload a clearer copy or type your GSTIN.")
        elif not gstin_valid(g):
            near = _nearest_gstin(g, gst.get("trade_name") or gst.get("legal_name"))
            add("gstin.checksum", "fail", "gst_certificate", "GSTIN check digit doesn't match",
                f"{mask(g, 5)} fails the GSTIN checksum, so at least one character is wrong on the certificate.",
                ("The registry has " + mask(near, 5) + " for this business — upload the correct certificate or confirm the number.") if near else "Upload the original certificate from the GST portal.")
            if near:
                reg = gstin_registry().loc[near]
        else:
            if declared_gstin and declared_gstin.upper() != g:
                add("gstin.declared", "fail", "gst_certificate", "GSTIN differs from the one you gave", "The certificate shows a different GSTIN.", "Check the GSTIN on your order.")
            if g in gstin_registry().index:
                reg = gstin_registry().loc[g]
                if reg.status != "Active":
                    add("gstin.status", "fail", "gst_certificate", f"GSTIN is {reg.status}", f"The GST registry lists this GSTIN as {reg.status}. Services that need GST can't be activated.",
                        "Restore your GST registration, then restart KYC.", severity="rejected")
                else:
                    add("gstin.status", "pass", "gst_certificate", "GSTIN active in registry", f"{mask(g, 5)} is Active.")
            else:
                add("gstin.registry", "fail", "gst_certificate", "GSTIN not in registry", "We couldn't find this GSTIN in the GST registry.", "Check the certificate.", severity="manual_review")
        if reg is not None:
            ln, tn = gst.get("legal_name"), gst.get("trade_name")
            prop, prop_biz = _prop(ln)
            if prop_biz and tn and similar(prop_biz, tn) < 0.6:
                add("gst.name_conflict", "fail", "gst_certificate", "Business name on certificate looks edited",
                    f"The legal name says '{prop_biz}' but the trade name and other documents say '{tn}'.",
                    "A person will check this with you before activation.", severity="manual_review")
            elif similar(ln, reg.legal_name) < 0.6:
                add("gst.legal_name", "fail", "gst_certificate", "Legal name differs from the registry",
                    "The legal name printed on the certificate doesn't match the GST registry.", "A person will check this with you.", severity="manual_review")
            else:
                add("gst.legal_name", "pass", "gst_certificate", "Name matches GST registry", "Legal and trade name match.")
            if gst.get("address") and similar(gst["address"], reg.principal_place_of_business) < 0.5:
                add("gst.address", "warn", "gst_certificate", "Address differs slightly from registry", "We'll confirm the installation address with you.")

    # ---- Udyam
    if "udyam_certificate" in reads and reads["udyam_certificate"].get("fields") is not None and "udyam_certificate" in docs and reads["udyam_certificate"]["ok"] and reads["udyam_certificate"]["blur"] >= BLUR_MIN:
        u = udy.get("udyam_number")
        if not u:
            add("udyam.number", "fail", "udyam_certificate", "Udyam number missing on certificate", "The registration number field is blank.", "Upload the complete Udyam certificate (download it again from udyamregistration.gov.in).")
        else:
            r = lookup_udyam(u)
            if not r.get("found"):
                add("udyam.registry", "fail", "udyam_certificate", "Udyam number not in registry", r.get("reason", ""), "Check the certificate.", severity="manual_review")
            else:
                biz = (reg.trade_name if reg is not None else None) or gst.get("trade_name")
                if biz and similar(r["enterprise_name"], biz) < 0.6:
                    add("udyam.name", "fail", "udyam_certificate", "Udyam name differs from GST", f"Udyam says '{r['enterprise_name']}'.", "A person will check this.", severity="manual_review")
                else:
                    add("udyam.registry", "pass", "udyam_certificate", "Udyam verified", f"{r['enterprise_name']} · {r['enterprise_type']} · {r['city']}")

    # ---- address proof
    if bill:
        bd = bill.get("bill_date")
        if not bd:
            add("address.date", "fail", "address_proof", "Bill date not readable", "We couldn't read the bill date.", "Upload a clearer bill.")
        else:
            age = (TODAY - bd).days
            if age > ADDRESS_MAX_AGE:
                add("address.date", "fail", "address_proof", f"Bill is {age} days old", f"Dated {bd.isoformat()}; address proof must be from the last {ADDRESS_MAX_AGE} days.",
                    f"Upload a bill dated on or after {date.fromordinal(TODAY.toordinal() - ADDRESS_MAX_AGE).isoformat()}.")
            else:
                add("address.date", "pass", "address_proof", "Bill is recent", f"{age} days old.")
        names = [x for x in [gst.get("trade_name"), gst.get("legal_name"), reg.trade_name if reg is not None else None, udy.get("enterprise_name")] if x]
        if bill.get("billed_to") and names and max(similar(bill["billed_to"], n) for n in names) < 0.6:
            add("address.name", "fail", "address_proof", "Bill is in another name", f"Billed to '{bill['billed_to']}'.", "Upload a bill in the business or owner's name, or a rent agreement.", severity="manual_review")

    # ---- signatory
    if sid:
        vt = sid.get("valid_till")
        if vt and vt < TODAY:
            add("signatory.expired", "fail", "signatory_id", "Signatory ID has expired", f"Expired on {vt.isoformat()}.", "Upload a valid ID.")
        biz = gst.get("trade_name") or (reg.trade_name if reg is not None else None)
        if biz and sid.get("business") and similar(sid["business"], biz) < 0.6:
            add("signatory.business", "fail", "signatory_id", "ID is for a different business", f"ID says '{sid['business']}'.", "Upload the right signatory ID.", severity="manual_review")
        prop, _ = _prop(gst.get("legal_name"))
        if prop and sid.get("name") and similar(prop, sid["name"]) < 0.5:
            add("signatory.authority", "warn", "signatory_id", "Signatory isn't the proprietor",
                f"{sid['name']} ({sid.get('designation') or 'staff'}) isn't the proprietor named on the GST certificate.",
                f"We'll send {prop} a link to e-sign the order (or upload an authorisation letter).")
        elif sid.get("name"):
            add("signatory.ok", "pass", "signatory_id", "Signatory ID valid", f"{sid['name']} · valid till {vt.isoformat() if vt else '—'}")

    sev = [c["severity"] for c in checks]
    verdict = ("rejected" if "rejected" in sev else "manual_review" if "manual_review" in sev
               else "needs_action" if "needs_action" in sev else "verified")
    return {"verdict": verdict, "checks": checks,
            "fields": {d: _safe_fields(r.get("fields", {})) for d, r in reads.items()},
            "quality": {d: {"blur": r["blur"], "skew": r["skew"]} for d, r in reads.items()}}


def _nearest_gstin(g: str, name: str | None) -> str | None:
    reg = gstin_registry()
    cands = [x for x in reg.index if x[:2] == g[:2] and sum(a != b for a, b in zip(x, g)) <= 2]
    if name:
        cands = [x for x in cands if similar(reg.loc[x].trade_name, name) >= 0.6] or cands
    return cands[0] if len(cands) >= 1 else None


def _safe_fields(f: dict) -> dict:
    """Mask identifiers before anything leaves the server."""
    out = {}
    for k, v in f.items():
        if isinstance(v, date):
            v = v.isoformat()
        if k in ("gstin", "gstin_raw"):
            v = mask(v, 5)
        if k in ("udyam_number",):
            v = mask(v, 4)
        if k in ("id_no",):
            v = mask(v, 3)
        out[k] = v
    return out


def specimen(applicant: str) -> dict[str, bytes]:
    d = DATA / "kyc_documents"
    out = {}
    for doc in REQUIRED:
        p = d / f"{applicant}_{doc}.png"
        if p.exists():
            out[doc] = p.read_bytes()
    return out
