"""Conversational advisor: asks a few questions, recommends a rule-checked bundle, explains why.

State lives in memory per session (prototype). Every recommendation comes from recommender.py.
"""
from __future__ import annotations

import time
import uuid

from . import llm, nlu
from .core import catalogue, lookup_gstin, lookup_udyam
from .recommender import NEED_PRODUCT, Profile, recommend

SESSIONS: dict[str, dict] = {}
LEADS: list[dict] = []  # leads the advisor could not close -> back office / partners

T = {
    "en": {
        "hello": "Namaste! I'm Udyam Express, Accel Business's setup assistant. Tell me about your business — what you do, where, and how many people work there. (Tip: share your GSTIN and I'll fill in the details for you.)",
        "ask_business": "What kind of business is it, and in which city?",
        "ask_city": "Which city is the business in?",
        "ask_size": "Got it — a {btype} in {city}. How many people work there, and how many locations do you have?",
        "ask_needs": "What do you need most? e.g. internet, UPI billing, WhatsApp for customers, CCTV, email, backup internet. Also: do you have a GST registration (yes / no / your GSTIN)?",
        "assumed": "(I've assumed {what} — tell me if that's wrong.)",
        "rec": "Here's what I recommend for your {btype}: **{tier}** at **₹{monthly:,}/month** + GST — everything on one bill and one support number. You can switch add-ons on or off in the quote.",
        "blocked": "Not included: {items}.",
        "gst_found": "Found you in the GST registry: **{name}**, {city}. Status: **{status}**.",
        "gst_bad": "GST registry says this GSTIN is **{status}**, so GST-only services (WhatsApp, SMS, telephony, leased lines) can't be added until it's active.",
        "gst_invalid": "That GSTIN doesn't look right ({reason}). You can carry on without it.",
        "udyam_found": "Found your Udyam registration: **{name}** ({type}), {city}.",
        "handoff": "This needs a quick check by our team ({reason}). I've passed your details and our chat summary to an Accel Business advisor — they'll call you within 1 working day, so you won't have to repeat anything.",
        "tier3": "Accel Business services are currently sold in tier 1 and tier 2 cities, so I can't book it online for {city}.",
        "cheaper": "Understood — here's the lean option: **Essential** at **₹{monthly:,}/month** + GST. A 24-month contract also waives the setup fee.",
        "pii": "Please don't share ID or account numbers in chat — I've removed it. We'll collect KYC documents securely in the next step.",
        "offtopic": "I can only help with Accel Business internet, mobile, cloud, security and CCTV for your business. What does your business need?",
        "injection": "I can't change prices or rules — every price comes from the Accel catalogue. Happy to find the best-value bundle for you though!",
        "thanks": "You're welcome! Your quote is saved — come back any time.",
        "later": "No problem — I've saved your quote. Want a reminder on WhatsApp?",
        "mobile_only": "Sure — just mobile lines: **{n} × Business Postpaid 299** at **₹{monthly:,}/month** + GST.",
        "confused": "Sorry, I didn't quite get that. Tell me what your business does and where — e.g. \"Dental clinic in Pune, 8 staff, 1 clinic\".",
        "updated": "Updated. **{tier}** is now **₹{monthly:,}/month** + GST.",
        "accept": "Great! Next: a quick consent and KYC step — it takes about 2 minutes.",
        "restart": "Fresh start! Tell me about your business.",
    },
    "hi": {
        "hello": "नमस्ते! मैं Udyam Express हूँ, Accel Business का सेटअप सहायक। अपने बिज़नेस के बारे में बताइए — क्या करते हैं, कहाँ, और कितने लोग काम करते हैं। (GSTIN बताएँगे तो मैं बाकी जानकारी खुद भर दूँगा।)",
        "ask_business": "आपका बिज़नेस किस तरह का है और किस शहर में है?",
        "ask_city": "बिज़नेस किस शहर में है?",
        "ask_size": "समझ गया — {city} में {btype}। वहाँ कितने लोग काम करते हैं और कितनी जगह/ब्रांच हैं?",
        "ask_needs": "आपको सबसे ज़्यादा क्या चाहिए? जैसे इंटरनेट, UPI बिलिंग, ग्राहकों के लिए WhatsApp, CCTV, ईमेल, बैकअप इंटरनेट। और क्या GST रजिस्ट्रेशन है (हाँ / नहीं / GSTIN)?",
        "assumed": "(मैंने {what} मान लिया है — गलत हो तो बताइए।)",
        "rec": "आपके {btype} के लिए मेरा सुझाव: **{tier}** — **₹{monthly:,}/महीना** + GST, सब कुछ एक बिल और एक सपोर्ट नंबर पर। कोटेशन में ऐड-ऑन चालू/बंद कर सकते हैं।",
        "blocked": "शामिल नहीं: {items}।",
        "gst_found": "GST रजिस्ट्री में मिला: **{name}**, {city}। स्थिति: **{status}**।",
        "gst_bad": "GST रजिस्ट्री के अनुसार यह GSTIN **{status}** है, इसलिए GST वाली सेवाएँ (WhatsApp, SMS आदि) अभी नहीं जुड़ सकतीं।",
        "gst_invalid": "यह GSTIN सही नहीं लग रहा ({reason})। आप इसके बिना भी आगे बढ़ सकते हैं।",
        "udyam_found": "आपका Udyam रजिस्ट्रेशन मिला: **{name}** ({type}), {city}।",
        "handoff": "इसके लिए हमारी टीम को एक बार देखना होगा ({reason})। मैंने आपकी जानकारी और बातचीत का सार Accel Business सलाहकार को भेज दिया है — वे 1 कार्यदिवस में कॉल करेंगे, आपको कुछ दोहराना नहीं पड़ेगा।",
        "tier3": "Accel Business सेवाएँ अभी टियर 1 और टियर 2 शहरों में मिलती हैं, इसलिए {city} के लिए ऑनलाइन बुकिंग नहीं हो सकती।",
        "cheaper": "ठीक है — सबसे किफ़ायती विकल्प: **Essential** — **₹{monthly:,}/महीना** + GST। 24 महीने के कॉन्ट्रैक्ट पर सेटअप फीस माफ़।",
        "pii": "कृपया चैट में ID या खाता नंबर न भेजें — मैंने उसे हटा दिया है। KYC दस्तावेज़ अगले चरण में सुरक्षित तरीके से लिए जाएँगे।",
        "offtopic": "मैं केवल आपके बिज़नेस के लिए Accel Business इंटरनेट, मोबाइल, क्लाउड, सुरक्षा और CCTV में मदद कर सकता हूँ। आपको क्या चाहिए?",
        "injection": "मैं कीमतें या नियम नहीं बदल सकता — हर कीमत Accel कैटलॉग से आती है। पर आपके लिए सबसे किफ़ायती बंडल ज़रूर ढूँढ सकता हूँ!",
        "thanks": "धन्यवाद! आपका कोटेशन सेव है — कभी भी वापस आइए।",
        "later": "कोई बात नहीं — कोटेशन सेव कर दिया है। WhatsApp पर याद दिलाऊँ?",
        "mobile_only": "ज़रूर — सिर्फ़ मोबाइल लाइनें: **{n} × Business Postpaid 299** — **₹{monthly:,}/महीना** + GST।",
        "confused": "माफ़ कीजिए, मैं समझ नहीं पाया। बताइए आपका बिज़नेस क्या है और कहाँ है — जैसे \"पुणे में डेंटल क्लिनिक, 8 लोग, 1 क्लिनिक\"।",
        "updated": "अपडेट हो गया। **{tier}** अब **₹{monthly:,}/महीना** + GST है।",
        "accept": "बढ़िया! अगला कदम: सहमति और KYC — लगभग 2 मिनट।",
        "restart": "नई शुरुआत! अपने बिज़नेस के बारे में बताइए।",
    },
    "hinglish": {
        "hello": "Namaste! Main Udyam Express hoon, Accel Business ka setup assistant. Apne business ke baare mein bataiye — kya karte hain, kahan, aur kitne log kaam karte hain.",
        "ask_business": "Aapka business kis type ka hai aur kis shehar mein hai?",
        "ask_city": "Business kis shehar mein hai?",
        "ask_size": "Samajh gaya — {city} mein {btype}. Kitne log kaam karte hain aur kitni jagah/branch hain?",
        "ask_needs": "Aapko sabse zyada kya chahiye? Jaise internet, UPI billing, WhatsApp, CCTV, email, backup internet. Aur GST registration hai? (haan / nahi / GSTIN)",
        "assumed": "(Maine {what} maan liya hai — galat ho toh bataiye.)",
        "rec": "Aapke {btype} ke liye mera sujhav: **{tier}** — **₹{monthly:,}/mahina** + GST, sab kuch ek bill aur ek support number par. Quote mein add-ons on/off kar sakte hain.",
        "blocked": "Shamil nahi: {items}.",
        "gst_found": "GST registry mein mila: **{name}**, {city}. Status: **{status}**.",
        "gst_bad": "GST registry ke hisaab se yeh GSTIN **{status}** hai, isliye GST wali services (WhatsApp, SMS) abhi nahi jud sakti.",
        "gst_invalid": "Yeh GSTIN sahi nahi lag raha ({reason}). Aap iske bina bhi aage badh sakte hain.",
        "udyam_found": "Aapka Udyam registration mila: **{name}** ({type}), {city}.",
        "handoff": "Iske liye hamari team ko ek baar dekhna hoga ({reason}). Maine aapki details aur chat summary Accel Business advisor ko bhej di hai — woh 1 working day mein call karenge.",
        "tier3": "Accel Business services abhi tier 1 aur tier 2 shehron mein milti hain, isliye {city} ke liye online booking nahi ho sakti.",
        "cheaper": "Theek hai — sabse kifayati option: **Essential** — **₹{monthly:,}/mahina** + GST. 24 mahine ke contract par setup fee maaf.",
        "pii": "Please chat mein ID ya account number na bhejein — maine hata diya hai. KYC documents agle step mein safely liye jayenge.",
        "offtopic": "Main sirf aapke business ke liye Accel Business internet, mobile, cloud, security aur CCTV mein madad kar sakta hoon. Aapko kya chahiye?",
        "injection": "Main prices ya rules nahi badal sakta — har price Accel catalogue se aati hai. Par sabse kifayati bundle zaroor dhoondh sakta hoon!",
        "thanks": "Shukriya! Aapka quote save hai.",
        "later": "Koi baat nahi — quote save kar diya hai.",
        "mobile_only": "Zaroor — sirf mobile lines: **{n} × Business Postpaid 299** — **₹{monthly:,}/mahina** + GST.",
        "confused": "Maaf kijiye, samajh nahi paya. Bataiye business kya hai aur kahan — jaise \"Pune mein dental clinic, 8 log, 1 clinic\".",
        "updated": "Update ho gaya. **{tier}** ab **₹{monthly:,}/mahina** + GST hai.",
        "accept": "Badhiya! Agla step: consent aur KYC — lagbhag 2 minute.",
        "restart": "Nayi shuruaat! Apne business ke baare mein bataiye.",
    },
}
TIER_NAMES = {"essential": "Essential", "recommended": "Recommended", "complete": "Complete"}
DEFAULT_SIZE = {"micro": 2, "prof": 5, "multi": 20, "mfg": 20}


def _t(s: dict, key: str, **kw) -> str:
    lang = s["lang"] if s["lang"] in T else "en"
    text = T[lang][key].format(**kw)
    if s["lang"] not in T:  # other Indian languages via Gemini, guarded
        text = llm.phrase(text, s["lang"]) or text
    return text


def start(lang: str = "en", channel: str = "web") -> dict:
    sid = uuid.uuid4().hex[:12]
    s = {"id": sid, "lang": lang, "lang_locked": lang not in ("en",), "channel": channel, "profile": Profile(),
         "asked": [], "confused": 0, "history": [], "rec": None, "tier": None, "lead": None, "created": time.time(),
         "done": False}
    SESSIONS[sid] = s
    msg = _t(s, "hello")
    s["history"].append(("bot", msg))
    return _resp(s, [msg])


def _resp(s: dict, replies: list[str], **extra) -> dict:
    return {"session_id": s["id"], "replies": replies, "profile": s["profile"].to_dict(), "lang": s["lang"],
            "recommendation": s["rec"], "selected_tier": s["tier"], "lead_id": (s["lead"] or {}).get("id"),
            "llm": llm.enabled(), **extra}


def _handoff(s: dict, reason: str, replies: list[str]) -> dict:
    p = s["profile"]
    if not s["lead"]:
        s["lead"] = {"id": "LD" + uuid.uuid4().hex[:6].upper(), "session_id": s["id"], "reason": reason,
                     "summary": summary(s), "profile": p.to_dict(), "created": time.strftime("%Y-%m-%d %H:%M"),
                     "status": "open", "channel": s["channel"]}
        LEADS.append(s["lead"])
    replies.append(_t(s, "handoff", reason=reason))
    s["done"] = True
    return _resp(s, replies, handoff=True)


def summary(s: dict) -> str:
    p = s["profile"]
    bits = [p.business_type or "business", f"in {p.city}" if p.city else "", f"{p.employees} staff" if p.employees else "",
            f"{p.sites} sites" if p.sites else "", "GST: " + ({True: "yes", False: "no"}.get(p.has_gst, "unknown")),
            "needs: " + ", ".join(p.needs) if p.needs else ""]
    return ", ".join(b for b in bits if b)


def _apply(s: dict, text: str, replies: list[str]) -> bool:
    """Apply every fact found in the message. Returns True if anything new was learned."""
    p: Profile = s["profile"]
    before = repr(p.to_dict())
    tl = text.lower()
    bare = re.fullmatch(r"\s*(\d{1,6})(?:\s*[,/&and]+\s*(\d{1,4}))?\s*", text.translate(nlu.DEV_DIGITS))
    if bare:
        a, b = int(bare.group(1)), bare.group(2)
        if not p.employees:
            p.employees = a
            if b:
                p.sites = int(b)
        elif not p.sites:
            p.sites = a
        return True
    last = s["asked"][-1] if s["asked"] else None
    if last in ("needs", "gst") and re.fullmatch(r"\s*(yes|y|haan|ha|han|ji|हाँ|हां|yes we have|registered)\W*", tl):
        p.has_gst = True
        return True
    # registrations first: they can fill several fields
    g, has = nlu.parse_gst(text)
    if g:
        r = lookup_gstin(g)
        if r.get("found"):
            p.gstin, p.gstin_status, p.legal_name = g, r["status"], r["legal_name"]
            p.has_gst = r["status"] == "Active"
            city = r["address"].split(",")[-2].strip() if "," in r["address"] else None
            if not p.city and city:
                c, tier, _ = nlu.parse_city(city)
                p.city, p.city_tier = c or city, tier or p.city_tier
            _fill_from_leads(p, g)
            replies.append(_t(s, "gst_found", name=r["trade_name"], city=p.city or r["state"], status=r["status"]))
            if r["status"] != "Active":
                replies.append(_t(s, "gst_bad", status=r["status"]))
        else:
            p.has_gst = False
            replies.append(_t(s, "gst_invalid", reason=r["reason"]))
    elif has is not None:
        p.has_gst = has
    u = nlu.parse_udyam(text)
    if u:
        r = lookup_udyam(u)
        if r.get("found"):
            if not p.city:
                c, tier, _ = nlu.parse_city(r["city"])
                p.city, p.city_tier = c or r["city"], tier
            if not p.business_type:
                _set_business(p, r["nic_description"])
            replies.append(_t(s, "udyam_found", name=r["enterprise_name"], type=r["enterprise_type"], city=r["city"]))
    if not p.business_type:
        _set_business(p, text)
    c, tier, unserved = nlu.parse_city(text)
    if c or unserved:
        p.city, p.city_tier = c or p.city, tier
    e = nlu.parse_employees(text)
    if e:
        p.employees = e
    st = nlu.parse_sites(text)
    if st:
        p.sites = st
        if st > 1 and p.segment == "micro" or st > 1 and p.segment == "prof" and st >= 3:
            p.segment = "multi"
    elif e and not p.sites and s["asked"] and s["asked"][-1] == "size" and not nlu.parse_sites(text):
        pass
    for n in nlu.parse_needs(text):
        if n not in p.needs:
            p.needs.append(n)
    for pid in nlu.parse_removals(text):
        if pid not in p.removed:
            p.removed.append(pid)
        p.needs = [n for n in p.needs if NEED_PRODUCT.get(n) != pid]
    q = nlu.parse_qty(text)
    for pid, n in q.items():
        p.qty_override[pid] = n
        need = next((k for k, v in NEED_PRODUCT.items() if v == pid), None)
        if need and need not in p.needs and pid not in p.removed:
            p.needs.append(need)
    sp = nlu.parse_spend(text)
    if sp:
        p.monthly_spend = sp
    cur, already = nlu.parse_current(text)
    if cur:
        p.current_internet = cur
        p.has_internet_already = already
    pin = nlu.parse_pincode(text)
    if pin:
        p.pincode = pin
        p.fibre = fibre_feasible(pin)
    if re.search(r"no fib(re|er)|fib(re|er) (not available|nahi|doesn'?t reach)|फाइबर नहीं", tl):
        p.fibre = False
    # LLM fills only what the rules missed (any language)
    if llm.enabled() and (s["lang"] not in ("en",) or not (p.business_type and p.employees)):
        x = llm.extract(text, {k: v for k, v in p.to_dict().items() if v not in (None, [], {}, False)})
        if x.get("business_type") and not p.business_type:
            _set_business(p, x["business_type"]) or setattr(p, "business_type", x["business_type"])
            if not p.segment and x.get("segment"):
                p.segment = x["segment"]
        if x.get("city") and not p.city:
            c, tier, unserved = nlu.parse_city(x["city"])
            p.city, p.city_tier = c or x["city"], tier if (c or unserved) else 3
        for k in ("employees", "sites"):
            if x.get(k) and not getattr(p, k):
                setattr(p, k, x[k])
        if "has_gst" in x and p.has_gst is None:
            p.has_gst = x["has_gst"]
        for n in x.get("needs", []):
            if n not in p.needs and NEED_PRODUCT.get(n) not in p.removed:
                p.needs.append(n)
        for n in x.get("removed_needs", []):
            pid = NEED_PRODUCT.get(n)
            if pid and pid not in p.removed:
                p.removed.append(pid)
    if p.segment != "multi" and (p.sites or 1) > 1 and p.segment in ("micro",):
        p.segment = "multi"
    return repr(p.to_dict()) != before


import re  # noqa: E402


def _set_business(p: Profile, text: str) -> bool:
    for rx, name, seg in nlu.BUSINESS:
        if re.search(rx, text, re.I):
            p.business_type = name
            p.segment = seg
            if nlu.CHAIN_RE.search(text) and seg in ("micro", "prof"):
                p.segment = "multi"
                p.business_type = name + " chain"
            return True
    return False


def _fill_from_leads(p: Profile, gstin: str) -> None:
    from .core import leads
    d = leads()
    row = d[d.gstin == gstin]
    if len(row):
        r = row.iloc[0]
        p.business_type = p.business_type or r.business_type
        p.segment = p.segment or {"Micro retail & services": "micro", "Professional offices": "prof",
                                  "Small multi-site businesses": "multi", "Small manufacturers": "mfg"}[r.segment]
        p.employees = p.employees or int(r.employee_count)
        p.sites = p.sites or int(r.num_sites)
        if not p.city:
            p.city, p.city_tier = r.city, int(r.city_tier)


NO_FIBRE_PINCODES = {"390001", "400008", "411045", "560100", "302020"}


def fibre_feasible(pin: str) -> bool:
    """Mock serviceability: a few demo pincodes have no fibre yet."""
    return pin not in NO_FIBRE_PINCODES


def _recommend(s: dict, replies: list[str], key: str = "rec") -> dict:
    p: Profile = s["profile"]
    assumed = []
    if not p.segment:
        p.segment = "micro"
    if not p.employees:
        p.employees = DEFAULT_SIZE[p.segment]
        assumed.append(f"{p.employees} people")
    if not p.sites:
        p.sites = 1
        assumed.append("1 location")
    if p.city_tier is None:
        p.city_tier = 1
    p.assumed = assumed
    s["rec"] = recommend(p)
    tier = s["rec"]["default_tier"] if key == "rec" or s["tier"] not in s["rec"]["tiers"] else s["tier"]
    s["tier"] = tier
    q = s["rec"]["tiers"][tier]
    if assumed:
        replies.append(_t(s, "assumed", what=" and ".join(assumed)))
    replies.append(_t(s, key, btype=(p.business_type or "business").lower(), tier=TIER_NAMES[tier], monthly=q["monthly"]))
    if s["rec"]["blocked"]:
        items = "; ".join(b["reason"] for b in s["rec"]["blocked"])
        replies.append(_t(s, "blocked", items=items) + (" " + " ".join(s["rec"]["fixes"]) if s["lang"] == "en" else ""))
    return _resp(s, replies, quote_ready=True)


FACTS_FAQ = {
    "lockin": lambda: "Minimum contract per product (months): " + "; ".join(f"{r.product_name}: {r.min_contract_months}" for _, r in catalogue().iterrows()) + ". Mobile lines (Business Postpaid) have a 1-month minimum.",
    "install": lambda: "Typical installation days: " + "; ".join(f"{r.product_name}: {r.typical_install_days} days" for _, r in catalogue().iterrows()),
    "router": lambda: "The catalogue lists the fibre plans as broadband service; setup fees are listed per product. I can't promise a free router beyond what the catalogue states.",
    "gst_price": lambda: "Catalogue prices are monthly and exclude 18% GST; the quote shows GST separately.",
    "competitor": lambda: "Accel Business puts internet, mobile, cloud, security and CCTV on one bill with one support number, with prices from its catalogue.",
}
FAQ_EN = {
    "router": "I can't promise a free router — the quote shows exactly what's included and any setup fee from the catalogue.",
    "gst_price": "Prices shown are per month and exclude 18% GST; the quote shows GST separately.",
    "competitor": "We put internet, mobile, cloud, security and CCTV on one bill with one support number, so there's one place to call. Prices come straight from the Accel catalogue.",
}


def _faq(s: dict, kind: str, text: str) -> str | None:
    if kind == "whatis":
        for pid, r in catalogue().iterrows():
            if any(w in text.lower() for w in [r.product_name.lower(), *[k for k, v in nlu.PRODUCT_WORDS.items() if v == pid]]):
                return f"**{r.product_name}** — {r.description}. ₹{r.price_min_inr_per_month:,}–{r.price_max_inr_per_month:,} {r.unit}/month."
        return None
    if kind in ("lockin", "install") and s["rec"]:
        q = s["rec"]["tiers"][s["tier"]]
        if kind == "lockin":
            return f"Your bundle has a **{q['contract_months']}-month** minimum contract (longest product minimum). Mobile lines alone are month-to-month."
        return "Installation: " + ", ".join(f"{l['name']} ~{l['install_days']} days" for l in q["lines"]) + f". Everything is live in about **{q['install_days']} days**, and you can follow each step in the tracker."
    if kind == "lockin":
        return "Each product has a minimum contract in the catalogue — fibre plans 12 months, 5G AirFiber 6 months, mobile lines 1 month. Your quote shows the exact term."
    if kind == "install":
        return "Typical installation: 5G AirFiber ~2 days, fibre ~5 days, leased line 21–30 days. The tracker shows a date for each product."
    ans = llm.answer(text, FACTS_FAQ[kind](), s["lang"]) if kind in FACTS_FAQ else None
    return ans or FAQ_EN.get(kind)


def handle(sid: str, text: str) -> dict:
    s = SESSIONS.get(sid) or SESSIONS[start()["session_id"]]
    replies: list[str] = []
    clean, had_pii = nlu.redact(text)
    s["history"].append(("user", re.sub(r"\b([0-9]{2})[A-Z0-9]{10}([0-9A-Z]Z[0-9A-Z])\b", r"\1••••••••••\2", clean.upper()) if nlu.parse_gst(clean)[0] else clean))
    if had_pii and not nlu.parse_gst(text)[0]:
        replies.append(_t(s, "pii"))
    # language follows the owner
    lang = nlu.detect_lang(text)
    if lang == "hi" or (lang == "hinglish" and s["lang"] == "en") or (lang == "en" and s["lang"] in ("hi", "hinglish") and len(text.split()) > 3 and not nlu.DEV.search(text) and nlu.detect_lang(text) == "en"):
        s["lang"] = lang
    p: Profile = s["profile"]
    it = nlu.intent(clean)
    if it == "restart":
        SESSIONS[sid] = None
        new = start(s["lang"])
        s2 = SESSIONS[new["session_id"]]
        SESSIONS[sid] = s2
        s2["id"] = sid
        SESSIONS.pop(new["session_id"], None)
        return _resp(s2, [_t(s2, "restart")])
    if it == "injection":
        replies.append(_t(s, "injection"))
        learned = _apply(s, re.sub(nlu.INTENTS[6][1], "", clean, flags=re.I), replies)
        return _resp(s, replies) if not learned else _continue(s, replies)
    if nlu.OFFTOPIC.search(clean) and not p.business_type:
        replies.append(_t(s, "offtopic"))
        return _resp(s, replies)
    if it == "human":
        _apply(s, clean, replies)
        return _handoff(s, "you asked for a call", replies)
    if it == "thanks" and not s["rec"]:
        replies.append(_t(s, "thanks"))
        return _resp(s, replies)
    if it == "mobile_only":
        _apply(s, clean, replies)
        n = p.qty_override.get("P07") or 1
        from .core import price_lines
        q = price_lines({"P07": n})
        s["rec"] = {"tiers": {"essential": {**q, "why": ["Business Postpaid 299: 50 GB, unlimited calls"]}}, "default_tier": "essential", "blocked": [], "fixes": []}
        s["tier"] = "essential"
        replies.append(_t(s, "mobile_only", n=n, monthly=q["monthly"]))
        return _resp(s, replies, quote_ready=True, mobile_only=True)
    if s["rec"]:
        if it == "cheaper":
            _apply(s, clean, replies)
            s["rec"] = recommend(p)
            s["tier"] = "essential"
            replies.append(_t(s, "cheaper", monthly=s["rec"]["tiers"]["essential"]["monthly"]))
            return _resp(s, replies, quote_ready=True)
        if it == "later":
            _handoff_lead_only(s, "decided later")
            replies.append(_t(s, "later"))
            return _resp(s, replies)
        if it in ("accept",):
            replies.append(_t(s, "accept"))
            return _resp(s, replies, quote_ready=True, go_kyc=True)
        if it == "thanks":
            replies.append(_t(s, "thanks"))
            return _resp(s, replies)
    kind = nlu.faq(clean)
    learned = _apply(s, clean, replies)
    if kind and not learned:
        a = _faq(s, kind, clean)
        if a:
            replies.append(a)
            return _resp(s, replies, quote_ready=bool(s["rec"]))
    if s["rec"] and learned:
        return _check_handoff(s, replies) or _recommend(s, replies, key="updated")
    if not learned and not replies:
        s["confused"] += 1
        if s["confused"] >= 2:
            return _handoff(s, "we couldn't work out your needs in chat", replies)
        replies.append(_t(s, "confused"))
        return _resp(s, replies)
    return _continue(s, replies)


def _handoff_lead_only(s, reason):
    if not s["lead"]:
        s["lead"] = {"id": "LD" + uuid.uuid4().hex[:6].upper(), "session_id": s["id"], "reason": reason, "summary": summary(s),
                     "profile": s["profile"].to_dict(), "created": time.strftime("%Y-%m-%d %H:%M"), "status": "nurture", "channel": s["channel"]}
        LEADS.append(s["lead"])


def _check_handoff(s: dict, replies: list[str]) -> dict | None:
    p: Profile = s["profile"]
    if p.city_tier == 3:
        replies.append(_t(s, "tier3", city=p.city or "your town"))
        return _handoff(s, "outside our online service area", replies)
    if (p.sites or 0) > 10 or (p.employees or 0) > 500:
        return _handoff(s, "large multi-site setup needs a site survey", replies)
    if any(v > 100 for v in p.qty_override.values()):
        return _handoff(s, "a large order needs a custom quote", replies)
    if p.segment == "mfg" and re.search(r"erp|custom|automation|scada|survey", " ".join(t for w, t in s["history"] if w == "user"), re.I):
        return _handoff(s, "custom factory requirements need an engineer", replies)
    if p.employees is not None and p.employees <= 0:
        p.employees = None
    return None


def _continue(s: dict, replies: list[str]) -> dict:
    p: Profile = s["profile"]
    h = _check_handoff(s, replies)
    if h:
        return h
    # ask for what's missing, at most once per slot
    if not p.business_type and "business" not in s["asked"]:
        s["asked"].append("business")
        replies.append(_t(s, "ask_business" if not p.city else "ask_business"))
        return _resp(s, replies)
    if not p.city and s["asked"].count("city") < 2 and p.city_tier != 3:
        s["asked"].append("city")
        replies.append(_t(s, "ask_city"))
        return _resp(s, replies)
    if (not p.employees or (p.segment == "multi" and not p.sites)) and "size" not in s["asked"] and not p.gstin:
        s["asked"].append("size")
        replies.append(_t(s, "ask_size", btype=(p.business_type or "business").lower(), city=p.city or "—"))
        return _resp(s, replies)
    if not p.needs and p.has_gst is None and "needs" not in s["asked"]:
        s["asked"].append("needs")
        replies.append(_t(s, "ask_needs"))
        return _resp(s, replies)
    if p.has_gst is None and any(n in NEED_PRODUCT and catalogue().loc[NEED_PRODUCT[n]].requires_gstin == "Y" for n in p.needs) and "gst" not in s["asked"]:
        s["asked"].append("gst")
        replies.append({"en": "Do you have an active GST registration? (yes / no / your GSTIN) — some services need it.",
                        "hi": "क्या आपका GST रजिस्ट्रेशन चालू है? (हाँ / नहीं / GSTIN) — कुछ सेवाओं के लिए ज़रूरी है।",
                        "hinglish": "Kya aapka GST registration active hai? (haan / nahi / GSTIN) — kuch services ke liye zaroori hai."}.get(s["lang"], "Do you have an active GST registration? (yes / no / GSTIN)"))
        return _resp(s, replies)
    if not p.business_type:
        return _handoff(s, "we couldn't work out your business type", replies)
    return _recommend(s, replies)


def select(sid: str, tier: str | None = None, toggles: dict | None = None, term: int | None = None) -> dict:
    s = SESSIONS[sid]
    p: Profile = s["profile"]
    if toggles:
        for pid, on in toggles.items():
            if on:
                if pid in p.removed:
                    p.removed.remove(pid)
                need = next((k for k, v in NEED_PRODUCT.items() if v == pid), None)
                if need and need not in p.needs:
                    p.needs.append(need)
            else:
                if pid not in p.removed:
                    p.removed.append(pid)
                p.needs = [n for n in p.needs if NEED_PRODUCT.get(n) != pid]
        s["rec"] = recommend(p, term or 12)
    if term:
        s["rec"] = recommend(p, term)
    if tier and tier in s["rec"]["tiers"]:
        s["tier"] = tier
    elif s["tier"] not in s["rec"]["tiers"]:
        s["tier"] = s["rec"]["default_tier"]
    return _resp(s, [], quote_ready=True)
