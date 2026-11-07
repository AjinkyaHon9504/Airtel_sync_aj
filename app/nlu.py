"""Deterministic understanding of English, Hindi (Devanagari) and Hinglish messages.

Extracts profile facts, needs, removals and intents. The optional LLM only fills gaps.
"""
from __future__ import annotations

import re

from .core import GSTIN_RE, city_tiers

DEV = re.compile(r"[ऀ-ॿ]")
HINGLISH_WORDS = re.compile(r"\b(hai|hain|mein|mera|meri|mere|hamara|hamari|hamare|chahiye|nahi|nahin|log|ladke|kitna|kya|aur|bhi|wala|wali|dukaan|dukan|karna|kar|ek|sirf|bas|abhi|accha|haan|ji)\b", re.I)

# ----------------------------------------------------------- business types -> segment
BUSINESS = [
    # (regex, canonical type, segment)
    (r"kirana|grocery|general store|किराना|किराणा|परचून", "Kirana store", "micro"),
    (r"bakery|bake house|बेकरी", "Bakery", "micro"),
    (r"salon|parlou?r|barber|सैलून|पार्लर", "Salon", "micro"),
    (r"pharmacy|chemist|medical (shop|store)|medicals|दवा|फार्मेसी|मेडिकल", "Pharmacy", "micro"),
    (r"stationery|स्टेशनरी", "Stationery shop", "micro"),
    (r"optician|optical|चश्मे", "Optician", "micro"),
    (r"hardware|हार्डवेयर", "Hardware store", "micro"),
    (r"boutique|tailor|बुटीक|दर्जी", "Boutique", "micro"),
    (r"sweet|mithai|मिठाई|halwai", "Sweet shop", "micro"),
    (r"mobile (repair|shop)|phone repair|मोबाइल", "Mobile repair shop", "micro"),
    (r"\bcafe\b|café|tea stall|chai|कैफे", "Cafe", "micro"),
    (r"\bshop\b|\bstore\b|dukaan|dukan|दुकान|retail", "Retail shop", "micro"),
    (r"dental|dentist|डेंटल|दंत", "Dental clinic", "prof"),
    (r"diagnostic|pathology|\blab\b|लैब", "Diagnostic lab", "prof"),
    (r"physio|फिजियो", "Physiotherapy clinic", "prof"),
    (r"clinic|doctor|hospital|nursing home|क्लिनिक|अस्पताल|डॉक्टर|दवाखाना", "Clinic", "prof"),
    (r"real estate|property|realty|प्रॉपर्टी", "Real estate agency", "prof"),
    (r"law|lawyer|advocate|legal|वकील", "Law office", "prof"),
    (r"coaching|tuition|institute|classes|कोचिंग|ट्यूशन", "Coaching centre", "prof"),
    (r"\bca\b|chartered accountant|accountant|tax consult|सीए", "CA firm", "prof"),
    (r"architect", "Architecture studio", "prof"),
    (r"travel|tours|ट्रैवल", "Travel agency", "prof"),
    (r"insurance|बीमा", "Insurance agency", "prof"),
    (r"\boffice\b|consult|agency|studio|ऑफिस", "Office", "prof"),
    (r"restaurant|dhaba|hotel|eatery|रेस्टोरेंट|होटल|ढाबा", "Restaurant", "micro"),
    (r"\bgym\b|fitness|जिम", "Gym", "micro"),
    (r"pre-?school|play ?school|school", "Pre-school", "prof"),
    (r"auto.?parts|automobile parts", "Auto-parts unit", "mfg"),
    (r"textile|loom|garment (unit|factory)|कपड़ा|टेक्सटाइल", "Textile unit", "mfg"),
    (r"plastic|moulding|molding", "Plastic moulding unit", "mfg"),
    (r"packaging", "Packaging unit", "mfg"),
    (r"food processing|masala|papad|namkeen", "Food processing unit", "mfg"),
    (r"furniture|carpentry|wood", "Furniture workshop", "mfg"),
    (r"printing|press", "Printing press", "mfg"),
    (r"factory|manufactur|workshop|plant\b|फैक्ट्री|कारखाना|मैन्युफैक्चरिंग|we make|unit\b", "Manufacturing unit", "mfg"),
]
CHAIN_RE = re.compile(r"\bchain\b|\bgroup\b|branches|outlets|चेन|ब्रांच|शाखा", re.I)

# ----------------------------------------------------------- numbers
WORDNUM = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
    "ten": 10, "eleven": 11, "twelve": 12, "fifteen": 15, "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50,
    "a couple": 2, "couple": 2, "single": 1, "a": 1, "an": 1,
    "ek": 1, "do": 2, "teen": 3, "char": 4, "chaar": 4, "paanch": 5, "panch": 5, "chhe": 6, "che": 6, "saat": 7,
    "aath": 8, "nau": 9, "das": 10, "barah": 12, "pandrah": 15, "bees": 20, "tees": 30, "pachas": 50,
    "एक": 1, "दो": 2, "तीन": 3, "चार": 4, "पांच": 5, "पाँच": 5, "छह": 6, "छः": 6, "सात": 7, "आठ": 8, "नौ": 9, "दस": 10,
    "बारह": 12, "पंद्रह": 15, "बीस": 20, "तीस": 30, "पचास": 50,
}
DEV_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")
NUM = r"(\d{1,5}|" + "|".join(sorted(map(re.escape, [k for k in WORDNUM if k not in ("a", "an")]), key=len, reverse=True)) + r")"
STAFF_W = r"(staff|people|persons|employees|employee|workers|worker|members|log|logon|ladke|bande|karmachari|teachers|doctors|nurses|lawyers|associates|engineers|stylists|chairs? and staff|लोग|कर्मचारी|स्टाफ|आदमी|जण|मजदूर|टीचर)"
SITE_W = r"(outlets?|branch(?:es)?|stores?|shops?|sites?|locations?|clinics?|centres?|centers?|hotels?|gyms?|restaurants?|plants?|offices?|factories|units?|cafes?|salons?|labs?|bakeries|pharmacies|schools?|ब्रांच|शाखा|दुकानें|दुकान|जगह|आउटलेट|स्टोर|होटल|जिम|क्लिनिक)"


def _n(tok: str) -> int | None:
    tok = tok.strip().lower().translate(DEV_DIGITS)
    if tok.isdigit():
        return int(tok)
    return WORDNUM.get(tok)


def parse_employees(t: str) -> int | None:
    tl = t.lower().translate(DEV_DIGITS)
    if re.search(r"\b(just me|only me|myself only|me alone|i work alone|akela|akele|sirf main|bas main|फक्त मी|सिर्फ मैं|अकेला|अकेले|मैं अकेला)\b", tl):
        return 1
    if re.search(r"\b(me and my (wife|husband|brother|sister|son|daughter|father|partner|friend|helper)|my (wife|husband|brother|partner) and (me|i)|husband.wife|two of us|both of us|hum dono|हम दोनों|मैं और मेरा|मैं और मेरी)\b", tl):
        return 2
    m = re.search(r"\b" + NUM + r"\s+of\s+us\b", tl)
    if m:
        return _n(m.group(1))
    m = re.search(r"\bwe are\s+" + NUM + r"\b|\bwe're\s+" + NUM + r"\b|\bhum\s+" + NUM + r"\s+(log|hain)|हम\s+" + NUM + r"\s+(लोग|हैं)", tl)
    if m:
        v = next(g for g in m.groups() if g and _n(g) is not None)
        return _n(v)
    m = re.search(r"(?<![\w-])(-?\d{1,7}|" + NUM[1:-1] + r")\s*\+?\s*(?:full[- ]time\s+|part[- ]time\s+)?" + STAFF_W, tl)
    if m:
        v = _n(m.group(1).lstrip("-")) if not m.group(1).startswith("-") else None
        return v if v and v > 0 else None
    m = re.search(STAFF_W + r"\s*(?:of|:|=|-|is|are|hai|hain|हैं|है)?\s*" + NUM + r"\b", tl)
    if m and not re.search(r"(staff|people)\s+" + NUM + r"\s+" + SITE_W, tl):
        return _n(m.group(2))
    return None


def parse_sites(t: str) -> int | None:
    tl = t.lower().translate(DEV_DIGITS)
    if re.search(r"\b(one|single|ek hi|only one|just one|1)\s+(location|site|branch|place|jagah|outlet|shop|store|clinic|office)\b|एक ही (जगह|दुकान|ब्रांच)|ek hi jagah|ek hi branch|ek hi (dukan|dukaan|shop|office|clinic)|एक ही", tl):
        return 1
    m = re.search(r"(?:across|in|with|have|run|own|of)?\s*" + NUM + r"\s+(?:[a-z\u0900-\u097F]+\s+)?" + SITE_W, tl)
    if m:
        v = _n(m.group(1))
        if v:
            return v
    return None


# ----------------------------------------------------------- needs / removals
NEEDS = [
    ("internet", r"\binternet\b|\bnet chahiye|\bnet\b for|इंटरनेट|connectivity|wi-?fi for (the )?(shop|office|clinic)"),
    ("failover", r"backup (internet|line|connection|net)|failover|internet (goes|keeps) (down|dropping)|net (jata|chala jata|band)|never stops?|always on|uptime|बैकअप इंटरनेट|नेट चला जाता|net down|dual internet|stay up|stays up|keep running"),
    ("cloud_backup", r"(data|file|files|pc|computer|cloud) backup|backup (of|for) (data|files|client|pc)|backup (karna|chahiye)|back ?up my|client files|\bbackup\b(?! internet| line| connection| net)|डेटा बैकअप"),
    ("payments", r"billing|bill software|\bpos\b|upi|paytm|qr|payment|card machine|invoice|inventory|stock|hisab|बिलिंग|पेमेंट|यूपीआई|बिल"),
    ("whatsapp", r"whats ?app|व्हाट्सएप|व्हाट्सऐप|catalogue"),
    ("sms", r"\bsms\b|text messages|एसएमएस|मैसेज भेज"),
    ("email", r"e-?mail|gmail|outlook|office suite|ईमेल"),
    ("cctv", r"cctv|camera|cameras|surveillance|कैमरा|सीसीटीवी"),
    ("security", r"antivirus|virus|ransomware|cyber ?security|endpoint|data security|secure (my|our) (pc|data|devices)|hack|सुरक्षा|साइबर|\bsecurity\b"),
    ("firewall", r"firewall|फ़ायरवॉल"),
    ("guest_wifi", r"guest wi-?fi|wi-?fi for (customers|guests|patients|students)|customer wi-?fi|free wi-?fi|\bwi-?fi\b|wifi|वाईफाई|वाई-फाई"),
    ("website", r"website|web ?site|domain|online presence|वेबसाइट"),
    ("static_ip", r"static ip|fixed ip|public ip"),
    ("telephony", r"ivr|call recording|cloud telephony|\bsip\b|phone lines|landline|telephony|call cent"),
    ("tollfree", r"toll ?free|1800|टोल फ्री"),
    ("sdwan", r"sd-?wan|central(ly)? (manage|control)|central control|centrally|manage all (branches|sites|stores|outlets)|all branches from one|one dashboard for"),
    ("iot", r"machine monitoring|machines?|iot|sensor|looms?|energy (use|monitor)|मशीन"),
    ("fleet", r"fleet|trucks?|vehicles?|gps|tracker for|delivery bikes|गाड़ि|गाड़ी|ट्रक|vehicle location"),
    ("sim_plus", r"150 ?gb|roaming|priority care"),
    ("sim", r"\bsims?\b|mobile (plan|line|connection|number)s?|postpaid|सिम|मोबाइल प्लान|phone connection"),
    ("leased_line", r"leased line|dedicated (line|internet|bandwidth)|\bsla\b|1:1 internet|लीज़्ड"),
    ("gigabit", r"\b1 ?g(bps)?\b|gigabit|1000 ?mbps|fastest"),
    ("fast_internet", r"300 ?mbps|fast internet|high.?speed|tez internet|faster internet"),
    ("5g", r"\b5g\b|airfiber|air fiber|wireless broadband|fwa"),
    ("fibre", r"\bfib(re|er)\b|broadband|wired internet|फाइबर|ब्रॉडबैंड"),
]
NEG = r"(no|not|don'?t|do not|without|remove|drop|skip|exclude|nahi|nahin|mat|na|नहीं|बिना|हटा)"
PRODUCT_WORDS = {
    "security": "P20", "antivirus": "P20", "camera": "P23", "cameras": "P23", "cctv": "P23", "email": "P16",
    "backup": "P17", "whatsapp": "P15", "sms": "P14", "website": "P18", "wifi": "P22", "wi-fi": "P22",
    "sim": "P07", "sims": "P07", "billing": "P19", "pos": "P19", "firewall": "P21", "static ip": "P11",
    "failover": "P09", "कैमरा": "P23", "सिक्योरिटी": "P20",
}


def parse_needs(t: str) -> list[str]:
    tl = t.lower()
    found = []
    for name, rx in NEEDS:
        for m in re.finditer(rx, tl):
            pre = tl[max(0, m.start() - 18):m.start()]
            post = tl[m.end():m.end() + 14]
            if re.search(NEG + r"\W+(\w+\W+)?$", pre) or re.search(r"^\W*(nahi|nahin|नहीं|mat)\b", post):
                continue
            if name in ("fibre", "5g") and re.search(r"(have|already|using|use|current|existing|home|abhi|hai)\W+(\w+\W+){0,2}$", pre):
                continue
            if name == "guest_wifi" and re.search(r"home wi-?fi|wifi (at home|hai)|have wi-?fi|use wi-?fi", tl):
                continue
            found.append(name)
            break
    if "sim_plus" in found and "sim" in found:
        found.remove("sim")
    if "failover" in found and "cloud_backup" in found and not re.search(r"data|file|pc|computer|cloud", tl):
        found.remove("cloud_backup")
    return found


def parse_removals(t: str) -> list[str]:
    tl = t.lower()
    out = []
    for w, pid in PRODUCT_WORDS.items():
        if re.search(re.escape(w) + r"\W+yet\b", tl) or re.search(re.escape(w) + r"\W+(\w+\W+){0,3}(but|par|lekin)\W+(\w+\W+){0,2}(want|need|chahiye)", tl):
            continue
        if re.search(NEG + r"\W+(\w+\W+){0,2}" + re.escape(w) + r"\b", tl) or re.search(re.escape(w) + r"\W+(\w+\W+){0,1}(nahi|nahin|नहीं|not needed|not required|mat)\b", tl):
            out.append(pid)
    return sorted(set(out))


def parse_qty(t: str) -> dict:
    tl = t.lower().translate(DEV_DIGITS)
    out = {}
    for rx, pid in [(r"cameras?|cctv", "P23"), (r"trucks?|vehicles?|bikes?|गाड़ि\S*|गाड़ी\S*", "P25"), (r"sims?|mobile lines?", "P07"),
                    (r"machines?|looms?", "P24"), (r"counters?|billing counters?", "P19"), (r"email (users|ids|accounts)", "P16")]:
        m = re.search(NUM + r"\s+(?:\w+\s+)?(?:" + rx + r")\b", tl)
        if m and _n(m.group(1)):
            out[pid] = _n(m.group(1))
    return out


# ----------------------------------------------------------- city / tier
HI_CITIES = {"दिल्ली": "Delhi", "मुंबई": "Mumbai", "पुणे": "Pune", "पटना": "Patna", "लखनऊ": "Lucknow",
             "जयपुर": "Jaipur", "इंदौर": "Indore", "भोपाल": "Bhopal", "नाशिक": "Nashik", "नासिक": "Nashik",
             "सूरत": "Surat", "बेंगलुरु": "Bengaluru", "बैंगलोर": "Bengaluru", "हैदराबाद": "Hyderabad",
             "चेन्नई": "Chennai", "कोलकाता": "Kolkata", "अहमदाबाद": "Ahmedabad", "नागपुर": "Nagpur",
             "कोच्चि": "Kochi", "लुधियाना": "Ludhiana", "वडोदरा": "Vadodara", "कोयंबटूर": "Coimbatore",
             "मैसूर": "Mysuru", "विशाखापत्तनम": "Visakhapatnam", "नोएडा": "Noida", "गुड़गांव": "Gurugram"}
ALIASES = {"bangalore": "bengaluru", "bombay": "mumbai", "new delhi": "delhi", "vizag": "visakhapatnam",
           "mysore": "mysuru", "cochin": "kochi", "calcutta": "kolkata", "madras": "chennai", "baroda": "vadodara",
           "poona": "pune", "gurgaon": "gurugram"}
RURAL = re.compile(r"\b(village|gaon|gaanv|gram|kasba|tehsil|taluka|rural|small town|outside the cities|chhota shehar)\b|गाँव|गांव|कस्बा|देहात", re.I)
NOT_CITY = {"the", "a", "my", "our", "one", "two", "three", "india", "hindi", "english", "night", "morning", "evening",
            "market", "main", "this", "that", "future", "cash", "person", "total", "front", "store", "shop", "office",
            "clinic", "it", "tier", "year", "month", "town", "city", "area", "short", "time", "bulk", "stock"}


def parse_city(t: str) -> tuple[str | None, int | None, bool]:
    """returns (city, tier, unserved_place_mentioned)"""
    tl = t.lower()
    for hi, en in HI_CITIES.items():
        if hi in t:
            return en, city_tiers().get(en.lower()), False
    for a, c in ALIASES.items():
        if re.search(r"\b" + a + r"\b", tl):
            tl = tl.replace(a, c)
    tiers = city_tiers()
    for c in sorted(tiers, key=len, reverse=True):
        if re.search(r"\b" + re.escape(c) + r"\b", tl):
            return c.title() if c != "navi mumbai" else "Navi Mumbai", tiers[c], False
    if RURAL.search(t):
        return None, 3, True
    m = re.search(r"\b(?:in|at|from|near)\s+([A-Z][a-z]{3,})\b|\b([A-Z][a-z]{3,})\s+(?:mein|me|mai|में|मध्ये)\b", t)
    if m:
        name = (m.group(1) or m.group(2))
        if name.lower() not in NOT_CITY and not re.match(r"(Hindi|English|Tamil|Telugu|Marathi|Bengali|Gujarati|Kannada|Punjabi|Malayalam)$", name):
            return name, 3, True
    m = re.search(r"([ऀ-ॿ]{3,})\s+(?:में|मध्ये)", t)
    if m and m.group(1) not in ("मेरी", "मेरा", "हमारी", "दुकान", "शहर", "बिज़नेस", "यहाँ", "ऑफिस", "क्लिनिक"):
        return m.group(1), 3, True
    return None, None, False


def parse_gst(t: str) -> tuple[str | None, bool | None]:
    up = t.upper()
    m = re.search(r"\b[0-9]{2}[A-Z0-9]{10}[0-9A-Z]Z[0-9A-Z]\b", up)
    if m and GSTIN_RE.match(m.group(0)) or (m and len(m.group(0)) == 15):
        return m.group(0), True
    tl = t.lower()
    if re.search(r"(gst|gstin|जीएसटी)\W+(\w+\W+){0,2}(cancel|suspend|band|रद्द)|(cancelled|suspended) (gst|gstin)", tl):
        return None, False
    if re.search(r"(no|not|without|don'?t have|nahi|nahin|not yet|unregistered)\W+(\w+\W+){0,2}(gst|gstin|जीएसटी)|(gst|gstin|जीएसटी)\W+(\w+\W+){0,2}(nahi|nahin|नहीं|no\b|not registered|not yet|nhi)|गैर.?जीएसटी|^\s*no\s*\.?\s*$|^\s*nahi\s*$|^\s*नहीं\s*$", tl):
        return None, False
    if re.search(r"(gst|gstin|जीएसटी)\W+(\w+\W+){0,2}(yes|hai|है|registered|active|number hai|we have)|(have|has|with|got)\W+(\w+\W+){0,1}(gst|gstin)|gst registered|registered (under|for) gst|(yes|haan),? (we have )?gst", tl):
        return None, True
    return None, None


UDYAM_FIND = re.compile(r"UDYAM-?\s*[A-Z]{2}-?\s*\d{2}-?\s*\d{7}", re.I)


def parse_udyam(t: str) -> str | None:
    m = UDYAM_FIND.search(t)
    if not m:
        return None
    s = re.sub(r"[\s-]", "", m.group(0).upper())
    return f"{s[:5]}-{s[5:7]}-{s[7:9]}-{s[9:]}"


def parse_spend(t: str) -> int | None:
    m = re.search(r"(?:₹|rs\.?|inr|rupees?)\s*([\d,]{3,7})|([\d,]{3,7})\s*(?:₹|rs\.?|rupees?|रुपये|/month|a month|per month|mahina|महीना)", t.lower())
    if m:
        v = int((m.group(1) or m.group(2)).replace(",", ""))
        return v if 50 <= v <= 500000 else None
    return None


def parse_current(t: str) -> tuple[str | None, bool]:
    tl = t.lower()
    if re.search(r"hotspot|हॉटस्पॉट|phone ka net|mobile data", tl):
        return "Mobile hotspot", False
    if re.search(r"(no|without|koi nahi|nahi hai) internet|internet (nahi|नहीं)|इंटरनेट नहीं", tl):
        return "None", False
    if re.search(r"leased line", tl) and re.search(r"(have|already|existing|current|using)", tl):
        return "Leased line", True
    if re.search(r"(have|already|existing|current|using|use|on)\W+(\w+\W+){0,2}(broadband|fibre|fiber|internet|wifi|wi-fi)", tl) and re.search(r"only|just|bas|sirf|also|need", tl):
        return "Broadband", "already" in tl or "have" in tl and "only" in tl
    if re.search(r"home broadband|broadband|jio ?fiber|airtel|wifi at home", tl):
        return "Home broadband", False
    return None, False


def parse_pincode(t: str) -> str | None:
    m = re.search(r"\b([1-8]\d{5})\b", t)
    return m.group(1) if m else None


# ----------------------------------------------------------- intents
INTENTS = [
    ("restart", r"start over|restart|reset|new chat|फिर से शुरू|dobara shuru|naya shuru"),
    ("human", r"(?<!can )(?<!to )(?<!will )(?<!they )call me\b|talk to (a |an )?(person|human|agent|someone|executive)|speak to|call back|callback|(want|need|send|arrange) (a |someone for a )?visit\b|salesman|मुझे कॉल|कॉल करें|baat karni|phone karo|call karo"),
    ("cheaper", r"too (expensive|costly|high|much)|cheaper|reduce|kam karo|sasta|budget|discount|mehenga|महंगा|सस्ता|कम कीजिए|kam kar|less money"),
    ("later", r"decide later|think about it|later|baad mein|बाद में|sochta|soch ke"),
    ("thanks", r"^\s*(ok(ay)?|thanks?|thank you|dhanyavad|shukriya|धन्यवाद|शुक्रिया|bye)\W*\s*$"),
    ("mobile_only", r"only (want |need )?(a |one |ek )?(business )?(mobile|sim|phone) ?(plan|line|connection)?|(bas|sirf) (ek )?(business )?(mobile|sim)|just (a )?(sim|mobile plan)|sirf (sim|mobile)|only sims?|bas sim|सिर्फ सिम"),
    ("injection", r"ignore (all |the |previous |your )?(rules|instructions)|disregard|system prompt|you are now|jailbreak|for (1|one|0) rupee|for free|give me everything free"),
    ("accept", r"^\s*(yes|yes please|go ahead|proceed|book it|confirm|haan|ha|ji haan|theek hai|done|हाँ|ठीक है)\W*\s*$"),
]
FAQ = [
    ("lockin", r"lock.?in|contract|commitment|exit|cancel"),
    ("install", r"how long|install|kitne din|कितने दिन|when will|activation time"),
    ("router", r"free router|router free|router included|modem"),
    ("gst_price", r"include gst|with gst|tax"),
    ("whatis", r"what is|what's|kya hota|kya hai|matlab|explain"),
    ("competitor", r"jio|bsnl|act fibernet|competitor|cheaper elsewhere|better than"),
]
OFFTOPIC = re.compile(r"cricket|score|weather|movie|joke|politics|recipe|क्रिकेट|मौसम|फिल्म", re.I)


def intent(t: str) -> str | None:
    tl = t.lower()
    for name, rx in INTENTS:
        if re.search(rx, tl):
            return name
    return None


def faq(t: str) -> str | None:
    tl = t.lower()
    for name, rx in FAQ:
        if re.search(rx, tl):
            return name
    return None


# ----------------------------------------------------------- PII
PII = [
    (re.compile(r"\b[2-9]\d{3}\s?\d{4}\s?\d{4}\b"), "[aadhaar removed]"),
    (re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b"), "[PAN removed]"),
    (re.compile(r"\b\d{9,18}\b"), "[number removed]"),
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+"), "[email removed]"),
    (re.compile(r"(?<!\d)(\+91[\s-]?)?[6-9]\d{9}(?!\d)"), "[phone removed]"),
]


def redact(t: str) -> tuple[str, bool]:
    hit = False
    # keep GSTIN / Udyam (needed for lookup) by protecting them first
    keep = {}
    def _protect(m):
        k = f"__K{len(keep)}__"; keep[k] = m.group(0); return k
    t2 = re.sub(r"\b[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]\b", _protect, t)
    t2 = UDYAM_FIND.sub(_protect, t2)
    t2 = re.sub(r"\b[1-8]\d{5}\b", _protect, t2)  # pincode
    for rx, rep in PII:
        t2, n = rx.subn(rep, t2)
        hit = hit or n > 0
    for k, v in keep.items():
        t2 = t2.replace(k, v)
    return t2, hit


def detect_lang(t: str) -> str:
    if DEV.search(t):
        return "hi"
    if len(HINGLISH_WORDS.findall(t)) >= 1 and not re.search(r"\b(the|and|is|we|our|my|need|want)\b", t.lower()):
        return "hinglish"
    if len(HINGLISH_WORDS.findall(t)) >= 2:
        return "hinglish"
    return "en"
