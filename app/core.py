"""Catalogue rules engine, pricing and mock registries.

Design rule: every product, eligibility decision and rupee figure shown to the owner comes
from this module (i.e. from product_catalogue.csv). The language model never decides these.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from datetime import date
from functools import lru_cache
from pathlib import Path

import pandas as pd

DATA = Path(__file__).resolve().parent.parent / "data"
TODAY = date(2026, 7, 15)  # README: use 2026-07-15 as "today" for date checks
GST_RATE = 0.18

SEGMENTS = {
    "micro": "Micro retail & services",
    "prof": "Professional offices",
    "multi": "Small multi-site businesses",
    "mfg": "Small manufacturers",
}
SEG_CODE = {v: k for k, v in SEGMENTS.items()}
BASE_LINKS = ["P01", "P02", "P03", "P04", "P05", "P06"]


@lru_cache
def catalogue() -> pd.DataFrame:
    c = pd.read_csv(DATA / "product_catalogue.csv", dtype=str).fillna("")
    for col in ["price_min_inr_per_month", "price_max_inr_per_month", "one_time_setup_inr",
                "min_contract_months", "min_employees", "min_sites", "typical_install_days"]:
        c[col] = c[col].astype(int)
    c["tiers"] = c.available_city_tiers.str.split(";").apply(lambda xs: {int(x) for x in xs})
    c["needs_one_of"] = c.requires_one_of.apply(lambda s: [x for x in s.split("|") if x])
    c["segments"] = c.target_segments.str.split(";")
    # Price we quote: midpoint of the catalogue range, rounded to the rupee.
    c["price"] = ((c.price_min_inr_per_month + c.price_max_inr_per_month) / 2).round().astype(int)
    return c.set_index("product_id")


@lru_cache
def gstin_registry() -> pd.DataFrame:
    return pd.read_csv(DATA / "mock_gstin_registry.csv", dtype=str).set_index("gstin")


@lru_cache
def udyam_registry() -> pd.DataFrame:
    return pd.read_csv(DATA / "mock_udyam_registry.csv", dtype=str).set_index("udyam_number")


@lru_cache
def leads() -> pd.DataFrame:
    return pd.read_csv(DATA / "smb_leads.csv")


@lru_cache
def city_tiers() -> dict[str, int]:
    d = leads()
    m = {c.lower(): int(t) for c, t in d.groupby("city").city_tier.first().items()}
    # Other well-known tier 1 / tier 2 cities (outside the dataset) so we don't wrongly turn them away.
    for c in ["gurugram", "gurgaon", "noida", "navi mumbai", "thane", "ghaziabad", "faridabad", "secunderabad"]:
        m.setdefault(c, 1)
    for c in ["chandigarh", "kanpur", "agra", "varanasi", "amritsar", "jalandhar", "raipur", "ranchi",
              "bhubaneswar", "guwahati", "dehradun", "madurai", "trichy", "tiruchirappalli", "mangaluru",
              "mangalore", "hubli", "belagavi", "vijayawada", "warangal", "aurangabad", "rajkot", "jodhpur",
              "udaipur", "kota", "gwalior", "jabalpur", "allahabad", "prayagraj", "meerut", "thiruvananthapuram",
              "trivandrum", "kozhikode", "thrissur", "goa", "panaji", "salem", "tiruppur", "jamshedpur",
              "dhanbad", "siliguri", "durgapur", "asansol", "bareilly", "aligarh", "moradabad", "solapur",
              "kolhapur", "nellore", "guntur", "bikaner", "ajmer"]:
        m.setdefault(c, 2)
    return m


# ---------------------------------------------------------------- GSTIN / Udyam formats
_CS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
GSTIN_RE = re.compile(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")
UDYAM_RE = re.compile(r"^UDYAM-[A-Z]{2}-\d{2}-\d{7}$")


def gstin_checksum(first14: str) -> str:
    total = 0
    for i, ch in enumerate(first14):
        v = _CS.index(ch) * (2 if i % 2 else 1)
        total += v // 36 + v % 36
    return _CS[(36 - total % 36) % 36]


def gstin_valid(g: str) -> bool:
    g = (g or "").strip().upper()
    return bool(GSTIN_RE.match(g)) and gstin_checksum(g[:14]) == g[14]


def lookup_gstin(g: str) -> dict:
    g = (g or "").strip().upper()
    if not GSTIN_RE.match(g):
        return {"found": False, "valid_format": False, "reason": "GSTIN must be 15 characters (e.g. 27ABCXE1234F1Z5)."}
    if not gstin_valid(g):
        return {"found": False, "valid_format": True, "checksum_ok": False, "reason": "The GSTIN check digit doesn't match; there may be a typo."}
    reg = gstin_registry()
    if g not in reg.index:
        return {"found": False, "valid_format": True, "checksum_ok": True, "reason": "Not found in the GST registry."}
    r = reg.loc[g]
    return {"found": True, "gstin": g, "legal_name": r.legal_name, "trade_name": r.trade_name,
            "constitution": r.constitution, "address": r.principal_place_of_business, "state": r.state,
            "registration_date": r.registration_date, "status": r.status}


def lookup_udyam(u: str) -> dict:
    u = re.sub(r"\s+", "", (u or "").upper())
    if not UDYAM_RE.match(u):
        return {"found": False, "reason": "Udyam numbers look like UDYAM-MH-00-1234567."}
    reg = udyam_registry()
    if u not in reg.index:
        return {"found": False, "reason": "Not found in the Udyam registry."}
    r = reg.loc[u]
    return {"found": True, "udyam_number": u, **{k: r[k] for k in reg.columns}}


def mask(s: str | None, keep: int = 4) -> str:
    if not s:
        return ""
    s = str(s)
    return "•" * max(0, len(s) - keep) + s[-keep:]


# ---------------------------------------------------------------- eligibility
@dataclass
class Ctx:
    city_tier: int = 1
    employees: int = 1
    sites: int = 1
    gstin_ok: bool = False  # valid + active GSTIN
    fibre: bool = True      # fibre available at the pincode


def ineligible_reason(pid: str, ctx: Ctx) -> str | None:
    p = catalogue().loc[pid]
    if ctx.city_tier not in p.tiers:
        return f"{p.product_name} is only sold in tier {'/'.join(map(str, sorted(p.tiers)))} cities"
    if ctx.employees < p.min_employees:
        return f"{p.product_name} needs at least {p.min_employees} staff"
    if ctx.sites < p.min_sites:
        return f"{p.product_name} needs at least {p.min_sites} sites"
    if p.requires_gstin == "Y" and not ctx.gstin_ok:
        return f"{p.product_name} needs an active GST registration"
    if pid in ("P01", "P02", "P03") and not ctx.fibre:
        return "Fibre isn't available at this address yet"
    return None


def bundle_violations(lines: dict[str, int], ctx: Ctx) -> list[str]:
    out = []
    for pid in lines:
        r = ineligible_reason(pid, ctx)
        if r:
            out.append(r)
        need = catalogue().loc[pid].needs_one_of
        if need and not any(n in lines for n in need):
            out.append(f"{catalogue().loc[pid].product_name} needs one of {', '.join(need)} in the bundle")
    return out


# ---------------------------------------------------------------- quote
def price_lines(lines: dict[str, int], term_months: int = 12) -> dict:
    c = catalogue()
    rows, monthly, setup = [], 0, 0
    for pid, qty in lines.items():
        p = c.loc[pid]
        m = int(p.price) * qty
        s = int(p.one_time_setup_inr) * qty
        rows.append({"product_id": pid, "name": p.product_name, "category": p.category, "unit": p.unit,
                     "qty": qty, "unit_price": int(p.price), "monthly": m, "setup": s,
                     "min_contract": int(p.min_contract_months), "install_days": int(p.typical_install_days),
                     "description": p.description})
        monthly += m
        setup += s
    contract = max([r["min_contract"] for r in rows] + [term_months]) if rows else term_months
    # Offer: setup fee waived on contracts of 24 months or more (our commercial proposal).
    setup_waived = setup if contract >= 24 else 0
    gst = round(monthly * GST_RATE)
    return {"lines": rows, "monthly": monthly, "gst": gst, "monthly_incl_gst": monthly + gst,
            "setup": setup, "setup_waived": setup_waived, "setup_payable": setup - setup_waived,
            "contract_months": contract, "install_days": max([r["install_days"] for r in rows] or [0]),
            "first_bill": monthly + gst + setup - setup_waived}
