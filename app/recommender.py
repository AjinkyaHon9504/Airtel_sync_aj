"""Profile -> three bundle tiers (Essential / Recommended / Complete), all rule-checked."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

from .core import BASE_LINKS, Ctx, bundle_violations, catalogue, ineligible_reason, price_lines

# need keyword -> product
NEED_PRODUCT = {
    "payments": "P19", "whatsapp": "P15", "sms": "P14", "email": "P16", "cloud_backup": "P17",
    "failover": "P09", "cctv": "P23", "security": "P20", "firewall": "P21", "guest_wifi": "P22",
    "website": "P18", "static_ip": "P11", "telephony": "P12", "tollfree": "P13", "sdwan": "P10",
    "iot": "P24", "fleet": "P25", "sim": "P07", "sim_plus": "P08", "leased_line": "P05",
    "fibre": "P01", "fast_internet": "P02", "gigabit": "P03", "5g": "P04",
}
LINK_NEEDS = {"leased_line", "fibre", "fast_internet", "gigabit", "5g"}

# What a typical business in each segment gets beyond what it asked for.
SEG_DEFAULTS = {
    "micro": {"recommended": ["sim", "payments"], "complete": ["cctv", "guest_wifi", "whatsapp", "website"]},
    "prof": {"recommended": ["sim_plus", "email", "security", "cloud_backup"], "complete": ["failover", "website", "static_ip", "telephony"]},
    "multi": {"recommended": ["sim_plus", "payments", "failover", "cctv"], "complete": ["sdwan", "guest_wifi", "whatsapp", "firewall"]},
    "mfg": {"recommended": ["sim_plus", "email", "security"], "complete": ["cctv", "iot", "firewall", "failover", "cloud_backup"]},
}


@dataclass
class Profile:
    business_type: str | None = None
    segment: str | None = None
    city: str | None = None
    city_tier: int | None = None
    employees: int | None = None
    sites: int | None = None
    has_gst: bool | None = None
    gstin: str | None = None
    gstin_status: str | None = None
    legal_name: str | None = None
    fibre: bool = True
    pincode: str | None = None
    current_internet: str | None = None
    monthly_spend: int | None = None
    needs: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)   # product ids the owner declined
    qty_override: dict = field(default_factory=dict)    # product id -> qty the owner stated
    has_internet_already: bool = False
    assumed: list[str] = field(default_factory=list)

    def ctx(self) -> Ctx:
        return Ctx(city_tier=self.city_tier or 1, employees=self.employees or 1, sites=self.sites or 1,
                   gstin_ok=bool(self.has_gst) and self.gstin_status in (None, "Active"), fibre=self.fibre)

    def to_dict(self) -> dict:
        return asdict(self)


def _qty(pid: str, p: Profile) -> int:
    e, s = p.employees or 1, p.sites or 1
    if pid in p.qty_override:
        return int(p.qty_override[pid])
    if pid in ("P01", "P02", "P03", "P04", "P05", "P06", "P09", "P10", "P21", "P22"):
        return s
    if pid in ("P07", "P08"):
        return max(1, min(e, s * 2 if p.segment in ("micro", "multi") else max(1, round(e * 0.35))))
    if pid in ("P16", "P20"):
        if p.segment == "mfg":
            return max(2, round(e * 0.3))  # office staff, not every machine operator
        if p.segment == "multi":
            return min(e, 2 * s + 2)
        return max(1, e) if p.segment != "micro" else min(e, 3)
    if pid == "P23":
        return {"micro": 2, "prof": 2, "multi": 4, "mfg": 6}.get(p.segment or "micro", 2) * s
    if pid == "P19":
        return s
    if pid == "P12":
        return max(1, min(4, e // 5))
    if pid in ("P24", "P25"):
        return 5
    return 1


def _base_link(p: Profile) -> str:
    ctx = p.ctx()
    wanted = [NEED_PRODUCT[n] for n in p.needs if n in LINK_NEEDS]
    if "failover" in p.needs and "5g" in p.needs and not p.fibre is False:
        wanted = [w for w in wanted if w != "P04"]
    for pid in wanted:  # honour an explicit request if allowed (leased line steps down 100 -> 20 if needed)
        if pid == "P05" and (p.employees or 0) >= 25 and ctx.gstin_ok:
            pid = "P06"
        if not ineligible_reason(pid, ctx):
            return pid
        if pid in ("P06", "P05") and not ineligible_reason("P05", ctx):
            return "P05"
    if not ctx.fibre:
        return "P04"
    seg, e = p.segment, p.employees or 1
    if seg == "mfg":
        for pid in (["P06"] if e >= 25 and "iot" not in p.needs else []) + ["P05", "P02"]:
            if pid == "P06" and e < 60:
                continue
            if not ineligible_reason(pid, ctx):
                return pid
    if seg in ("prof", "multi") or e >= 6:
        return "P02"
    return "P01"


def build_tier(p: Profile, extra_needs: list[str]) -> tuple[dict, list[dict]]:
    ctx = p.ctx()
    lines: dict[str, int] = {}
    blocked: list[dict] = []
    base = _base_link(p)
    want = [NEED_PRODUCT[n] for n in p.needs if n in NEED_PRODUCT and n not in LINK_NEEDS] + [NEED_PRODUCT[n] for n in extra_needs]
    if not p.has_internet_already or any(catalogue().loc[x].needs_one_of for x in want):
        lines[base] = _qty(base, p)
    for pid in want:
        if pid in lines or pid in p.removed:
            continue
        reason = ineligible_reason(pid, ctx)
        if reason:
            if pid in [NEED_PRODUCT.get(n) for n in p.needs]:
                blocked.append({"product_id": pid, "name": catalogue().loc[pid].product_name, "reason": reason})
            continue
        need = catalogue().loc[pid].needs_one_of
        if need and not any(n in lines for n in need):
            alt = next((n for n in need if not ineligible_reason(n, ctx)), None)
            if not alt:
                blocked.append({"product_id": pid, "name": catalogue().loc[pid].product_name,
                                "reason": f"needs a fibre or leased-line connection, not available here"})
                continue
            lines[alt] = _qty(alt, p)
        if pid == "P08" and "P07" in lines:
            continue
        if pid == "P07" and "P08" in lines:
            continue
        lines[pid] = _qty(pid, p)
    # Firewall can't sit on 5G AirFiber etc.: drop anything whose dependency isn't met
    for pid in list(lines):
        need = catalogue().loc[pid].needs_one_of
        if need and not any(n in lines for n in need):
            del lines[pid]
    assert not bundle_violations(lines, ctx), bundle_violations(lines, ctx)
    return lines, blocked


def recommend(p: Profile, term_months: int = 12) -> dict:
    seg = p.segment or "micro"
    d = SEG_DEFAULTS[seg]
    removed_needs = {n for n, pid in NEED_PRODUCT.items() if pid in p.removed}
    rec_extra = [n for n in d["recommended"] if n not in removed_needs]
    comp_extra = rec_extra + [n for n in d["complete"] if n not in removed_needs]
    tiers = {}
    blocked_all: dict[str, dict] = {}
    for name, extra in (("essential", []), ("recommended", rec_extra), ("complete", comp_extra)):
        lines, blocked = build_tier(p, extra)
        q = price_lines(lines, term_months)
        q["why"] = explain(p, lines)
        tiers[name] = q
        for b in blocked:
            blocked_all[b["product_id"]] = b
    # de-duplicate identical tiers
    seen, order = set(), []
    for name in ("essential", "recommended", "complete"):
        key = tuple(sorted((l["product_id"], l["qty"]) for l in tiers[name]["lines"]))
        if key in seen:
            del tiers[name]
        else:
            seen.add(key)
            order.append(name)
    default = "recommended" if "recommended" in tiers else order[0]
    if seg == "micro" and (p.monthly_spend or 0) and (p.monthly_spend or 0) < 1500:
        default = "essential"  # price-sensitive: lead with the lean bundle
    return {"tiers": tiers, "default_tier": default, "blocked": list(blocked_all.values()),
            "fixes": fixes_for(list(blocked_all.values()), p)}


def fixes_for(blocked: list[dict], p: Profile) -> list[str]:
    out = []
    if any("GST" in b["reason"] for b in blocked):
        out.append("Register for GST (or share your active GSTIN) to unlock WhatsApp, SMS and other GST-only services.")
    if any("staff" in b["reason"] for b in blocked):
        out.append("Some services are for bigger teams; we picked the closest option that fits your size.")
    return out


WHY = {
    "P01": "100 Mbps fibre is plenty for UPI, billing and a few devices",
    "P02": "300 Mbps fibre keeps everyone online at once, with a static IP option",
    "P03": "1 Gbps with priority support for heavy cloud and video use",
    "P04": "5G AirFiber is plug-and-play and installs in about 2 days where fibre isn't available",
    "P05": "a dedicated 20 Mbps line with 99.5% uptime SLA for operations that can't stop",
    "P06": "a dedicated 100 Mbps line with 99.9% SLA for a large plant",
    "P07": "business SIMs with 50 GB and unlimited calls",
    "P08": "business SIMs with 150 GB, roaming and priority care",
    "P09": "automatic 4G/5G backup so billing never stops when the main line drops",
    "P10": "manage every branch's internet from one screen",
    "P11": "a fixed IP for CCTV, servers or remote access",
    "P12": "business phone lines with IVR and call recording",
    "P13": "a 1800 number customers can call free",
    "P14": "10,000 SMS a month for alerts and offers",
    "P15": "a verified WhatsApp channel with your catalogue",
    "P16": "email on your own domain, documents and video meetings for each person",
    "P17": "automatic backup of PCs and phones, 1 TB",
    "P18": "a website with your own domain",
    "P19": "GST-ready billing, stock and UPI/card payments on a tablet",
    "P20": "antivirus and ransomware protection on every device",
    "P21": "a managed firewall watched by Accel's security team",
    "P22": "separate Wi-Fi for customers, safely away from your billing devices",
    "P23": "HD cameras you can watch on your phone, 30 days cloud recording",
    "P24": "sensors that track machine uptime and power use",
    "P25": "live GPS tracking for each vehicle",
}


def explain(p: Profile, lines: dict) -> list[str]:
    return [f"{catalogue().loc[pid].product_name}: {WHY[pid]}" for pid in lines]
