"""Orders + tracker, lead propensity model, and funnel analytics for the back office."""
from __future__ import annotations

import time
import uuid
from datetime import date, timedelta
from functools import lru_cache

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score

from .core import TODAY, leads

ORDERS: dict[str, dict] = {}
STAGES = ["Order placed", "KYC verified", "E-sign & payment", "Installation scheduled", "Installed", "Activated"]


def create_order(session: dict, quote: dict, kyc: dict | None, contact: dict) -> dict:
    oid = "AB" + uuid.uuid4().hex[:6].upper()
    start = TODAY
    lines = []
    for l in quote["lines"]:
        eta = start + timedelta(days=1 + l["install_days"])
        lines.append({"product_id": l["product_id"], "name": l["name"], "qty": l["qty"], "eta": eta.isoformat(),
                      "install_days": l["install_days"]})
    install = max([l["install_days"] for l in quote["lines"]] or [1])
    verified = bool(kyc) and kyc.get("verdict") == "verified"
    o = {"id": oid, "created": time.strftime("%Y-%m-%d %H:%M"), "business": session.get("business"),
         "contact": {"name": contact.get("name"), "phone_masked": _mask_phone(contact.get("phone"))},
         "monthly": quote["monthly"], "setup_payable": quote["setup_payable"], "contract_months": quote["contract_months"],
         "lines": lines, "kyc_verdict": (kyc or {}).get("verdict", "pending"),
         "stage": 2 if verified else 0, "eta": (start + timedelta(days=1 + install)).isoformat(),
         "events": [{"at": start.isoformat(), "text": "Order placed online"}] +
                   ([{"at": start.isoformat(), "text": "KYC verified instantly"}, {"at": start.isoformat(), "text": "Order e-signed, UPI AutoPay set up"}] if verified else []),
         "sla_risk": install >= 21}
    ORDERS[oid] = o
    return o


def _mask_phone(p):
    p = "".join(ch for ch in str(p or "") if ch.isdigit())
    return ("••••••" + p[-4:]) if len(p) >= 4 else ""


def advance(oid: str) -> dict:
    """Demo control: move the order to the next stage (as field ops would)."""
    o = ORDERS[oid]
    if o["stage"] < len(STAGES) - 1:
        o["stage"] += 1
        o["events"].append({"at": (TODAY + timedelta(days=o["stage"])).isoformat(), "text": STAGES[o["stage"]]})
    return o


def tracker(oid: str) -> dict | None:
    o = ORDERS.get(oid)
    if not o:
        return None
    return {**o, "stages": [{"name": s, "done": i <= o["stage"], "current": i == o["stage"]} for i, s in enumerate(STAGES)]}


# ------------------------------------------------------------------ propensity model
FEATS_CAT = ["lead_source", "segment", "current_internet"]


def _X(d: pd.DataFrame, cols=None) -> pd.DataFrame:
    X = pd.DataFrame({
        "tier1": (d.city_tier == 1).astype(int),
        "gstin": (d.has_gstin == "Y").astype(int),
        "udyam": (d.has_udyam == "Y").astype(int),
        "log_emp": np.log1p(d.employee_count),
        "sites": np.minimum(d.num_sites, 12),
        "log_spend": np.log1p(d.monthly_telecom_spend_inr.fillna(0)),
        "n_interest": d.products_of_interest.fillna("").str.count(";") + 1,
    })
    X = pd.concat([X, pd.get_dummies(d[FEATS_CAT].fillna("NA"), dtype=int)], axis=1)
    if cols is not None:
        X = X.reindex(columns=cols, fill_value=0)
    return X


@lru_cache
def model() -> dict:
    """Trained on Apr-May leads, tested on June (time split). Language deliberately excluded (fairness)."""
    d = leads().copy()
    d["y"] = (d.outcome == "Activated").astype(int)
    d["m"] = pd.to_datetime(d.created_date).dt.month
    tr, te = d[d.m < 6], d[d.m == 6]
    Xtr = _X(tr)
    clf = LogisticRegression(max_iter=2000, C=0.5).fit(Xtr, tr.y)
    p = clf.predict_proba(_X(te, Xtr.columns))[:, 1]
    auc = roc_auc_score(te.y, p)
    top = te.assign(p=p).sort_values("p", ascending=False)
    k = max(1, len(top) // 10)
    lift = top.head(k).y.mean() / te.y.mean()
    full = LogisticRegression(max_iter=2000, C=0.5).fit(_X(d), d.y)
    coefs = sorted(zip(_X(d).columns, full.coef_[0]), key=lambda x: -abs(x[1]))[:8]
    return {"clf": full, "cols": list(_X(d).columns), "auc": round(float(auc), 3), "top_decile_rate": round(float(top.head(k).y.mean()) * 100, 1),
            "base_rate": round(float(te.y.mean()) * 100, 1), "lift": round(float(lift), 2),
            "top_factors": [(c, round(float(v), 2)) for c, v in coefs]}


# how recoverable is each drop reason by the digital journey / a partner call (0..1)
RECOVERABLE = {
    "Owner had no time for a visit": 0.9, "Visit not scheduled by sales": 0.9, "Quote took too long to arrive": 0.85,
    "Quote too complex to understand": 0.85, "Unreachable after 3 attempts": 0.5, "Documents incomplete": 0.8,
    "Signatory not available": 0.8, "Installation delayed beyond 21 days": 0.6, "Price too high": 0.4,
    "Competitor offered cheaper plan": 0.3, "Decided to wait": 0.5, "Only wanted a mobile plan": 0.7,
    "Not interested on first call": 0.2, "Locked in with current provider": 0.2, "Wrong or invalid number": 0.05,
    "No fibre at location": 0.7, "Missing GST or Udyam document": 0.8, "Found paperwork too long": 0.9,
    "Authorised signatory not available": 0.85, "Document details did not match": 0.6, "Site not feasible for fibre": 0.8,
    "Customer cancelled before install": 0.4, "First payment failed": 0.7,
}
ACTION = {
    "Owner had no time for a visit": "Send WhatsApp advisor link — no visit needed",
    "Visit not scheduled by sales": "Send WhatsApp advisor link; partner books slot",
    "Quote took too long to arrive": "Send instant OneBill quote link",
    "Quote too complex to understand": "Send instant OneBill quote link",
    "Price too high": "Offer Essential bundle / 24-month setup waiver",
    "Unreachable after 3 attempts": "WhatsApp + missed-call callback",
    "Only wanted a mobile plan": "Offer mobile-only plan, cross-sell later",
    "Installation delayed beyond 21 days": "Offer 5G AirFiber (2-day install)",
    "No fibre at location": "Offer 5G AirFiber (2-day install)",
    "Site not feasible for fibre": "Offer 5G AirFiber (2-day install)",
    "Missing GST or Udyam document": "Send KYC link: Udyam/GST fetched from registry",
    "Found paperwork too long": "Send 2-minute Smart KYC link",
    "Authorised signatory not available": "Send remote e-sign link to signatory",
    "Document details did not match": "KYC specialist call with flagged fields",
    "First payment failed": "Resend UPI AutoPay link",
}


def winback(limit: int = 50, segment: str | None = None) -> dict:
    m = model()
    d = leads()
    dropped = d[d.outcome == "Dropped"].copy()
    if segment:
        dropped = dropped[dropped.segment == segment]
    dropped["score"] = m["clf"].predict_proba(_X(dropped, m["cols"]))[:, 1]
    dropped["recover"] = dropped.drop_reason.map(RECOVERABLE).fillna(0.3)
    dropped["winback"] = (dropped.score * dropped.recover)
    dropped["action"] = dropped.drop_reason.map(ACTION).fillna("Partner call with chat summary")
    top = dropped.sort_values("winback", ascending=False).head(limit)
    rows = [{"lead_id": r.lead_id, "business": r.business_name, "type": r.business_type, "segment": r.segment, "city": r.city,
             "source": r.lead_source, "drop_reason": r.drop_reason, "stage": r.stage_reached,
             "score": round(float(r.score) * 100, 1), "winback": round(float(r.winback) * 100, 1), "action": r.action,
             "contact": r.contact_name.split()[0] + " " + r.contact_name.split()[-1][0] + "."} for r in top.itertuples()]
    return {"model": {k: v for k, v in m.items() if k != "clf" and k != "cols"}, "leads": rows, "dropped_total": int(len(dropped))}


@lru_cache
def funnel() -> dict:
    d = leads()
    a = d[d.outcome == "Activated"]
    stages = ["Lead", "Contacted", "Needs assessed", "Quote accepted", "KYC complete", "Activated"]
    order = {s: i for i, s in enumerate(stages)}
    reach = [int((d.stage_reached.map(order) >= i).sum()) for i in range(len(stages))]
    seg = d.groupby("segment").agg(leads=("lead_id", "size"), act=("outcome", lambda s: (s == "Activated").mean() * 100))
    seg["median_bundle"] = a.groupby("segment").monthly_bundle_value_inr.median()
    seg["churn"] = a.groupby("segment").churned_within_6_months.apply(lambda s: (s == "Y").mean() * 100)
    seg["cac_per_activation"] = d.groupby("segment").acquisition_cost_inr.sum() / a.groupby("segment").size()
    src = d.groupby("lead_source").agg(leads=("lead_id", "size"), act=("outcome", lambda s: (s == "Activated").mean() * 100))
    src["cac_per_activation"] = d.groupby("lead_source").acquisition_cost_inr.sum() / a.groupby("lead_source").size()
    drops = d.drop_reason.value_counts()
    return {
        "stages": [{"stage": s, "leads": n} for s, n in zip(stages, reach)],
        "activation_rate": round(len(a) / len(d) * 100, 2),
        "days_to_activate": round(float(a.days_lead_to_activation.mean()), 1),
        "follow_up_calls": round(float(a.customer_follow_up_calls.mean()), 2),
        "cac": round(float(d.acquisition_cost_inr.sum() / len(a))),
        "churn_6m": round(float((a.churned_within_6_months == "Y").mean() * 100), 1),
        "segments": seg.round(1).reset_index().to_dict("records"),
        "sources": src.round(1).reset_index().to_dict("records"),
        "drop_reasons": [{"reason": r, "leads": int(n), "recoverable": RECOVERABLE.get(r, 0.3)} for r, n in drops.items()],
    }


# ------------------------------------------------------------------ impact replay
# Which drop reasons each feature removes, and the CONSERVATIVE share we assume it wins back.
FEATURE_FIX = {
    "Owner had no time for a visit": ("Self-serve advisor", 0.35), "Visit not scheduled by sales": ("Self-serve advisor", 0.35),
    "Quote took too long to arrive": ("Instant OneBill quote", 0.40), "Quote too complex to understand": ("Instant OneBill quote", 0.40),
    "Missing GST or Udyam document": ("Smart KYC", 0.40), "Found paperwork too long": ("Smart KYC", 0.40),
    "Authorised signatory not available": ("Remote e-sign", 0.40), "Document details did not match": ("Smart KYC", 0.25),
    "Installation delayed beyond 21 days": ("AirFiber fallback + tracker", 0.30), "Site not feasible for fibre": ("AirFiber fallback + tracker", 0.40),
    "Unreachable after 3 attempts": ("WhatsApp-first contact", 0.10), "Only wanted a mobile plan": ("Mobile-only path", 0.30),
    "First payment failed": ("UPI AutoPay", 0.40), "Price too high": ("Essential tier", 0.10),
}


@lru_cache
def impact() -> dict:
    d = leads()
    stages = ["Lead", "Contacted", "Needs assessed", "Quote accepted", "KYC complete", "Activated"]
    idx = {s: i for i, s in enumerate(stages)}
    reached = [int((d.stage_reached.map(idx) >= i).sum()) for i in range(len(stages))]
    # P(activate | reached stage i+1): downstream conversion after the leak is fixed
    p_after = {i: reached[-1] / reached[min(i + 1, 5)] for i in range(5)}
    drop = d[d.outcome == "Dropped"]
    gained, by_feature = 0.0, {}
    for r in drop.itertuples():
        f = FEATURE_FIX.get(r.drop_reason)
        if not f:
            continue
        g = f[1] * p_after[idx[r.stage_reached]]
        gained += g
        by_feature[f[0]] = by_feature.get(f[0], 0) + g
    base = len(d[d.outcome == "Activated"])
    new = base + gained
    a = d[d.outcome == "Activated"]
    cost_now = float(d.acquisition_cost_inr.sum())
    # cost: self-served leads (web, WhatsApp, inbound, referral) need ~60% less field effort; +Rs 40/lead platform cost
    self_src = d.lead_source.isin(["Website form", "WhatsApp campaign", "Inbound call", "Referral"])
    cost_new = cost_now - 0.6 * float(d[self_src].acquisition_cost_inr.sum()) * 0.5 + 40 * len(d)
    med = float(a.monthly_bundle_value_inr.median())
    return {
        "activations_now": base, "activations_new": round(new), "gain": round(gained),
        "rate_now": round(base / len(d) * 100, 2), "rate_new": round(new / len(d) * 100, 1),
        "cac_now": round(cost_now / base), "cac_new": round(cost_new / new),
        "by_feature": {k: round(v) for k, v in sorted(by_feature.items(), key=lambda x: -x[1])},
        "arr_cr": round(gained * 4 * med * 12 / 1e7, 1), "median_bundle": med,
    }
