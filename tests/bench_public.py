"""Benchmark our advisor on other teams' PUBLIC scenario files (used only as unseen test inputs).

Usage: python tests/bench_public.py /path/to/AgileSeagull_AirtelSync /path/to/adityamalik24_udyam-digital
Not part of CI (the files aren't ours and aren't committed).
"""
import json, re, sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import advisor  # noqa: E402
from app.core import catalogue  # noqa: E402

GST_PIDS = set(catalogue()[catalogue().requires_gstin == "Y"].index)


def run(msgs, lang="en"):
    s = advisor.start(lang)
    sid = s["session_id"]; last = s
    hist = []
    for m in msgs:
        last = advisor.handle(sid, m)
        hist += last["replies"]
    sess = advisor.SESSIONS[sid]
    rec = sess["rec"] or {"tiers": {}}
    q = rec["tiers"].get(sess["tier"]) if sess["tier"] else None
    lines = {l["product_id"]: l["qty"] for l in (q or {"lines": []})["lines"]}
    allids = {l["product_id"] for t in rec["tiers"].values() for l in t["lines"]}
    return dict(p=sess["profile"], lines=lines, all=allids, has_rec=bool(rec["tiers"]), last=" ".join(last["replies"]),
                hist=" ".join(hist), lead=bool(sess["lead"]), sess=sess)


def agile(root):
    res = []
    for sc in yaml.safe_load(open(f"{root}/services/api/evals/advisor_scenarios.yaml")):
        e = sc.get("expect", {}); r = run(sc["messages"], sc.get("lang", "en")); f = []
        if "segment" in e and r["p"].segment != e["segment"]: f.append(f"segment {r['p'].segment}≠{e['segment']}")
        f += [f"missing {x}" for x in e.get("include", []) if x not in r["lines"]]
        f += [f"has {x}" for x in e.get("exclude", []) if x in r["lines"]]
        if "first" in e and e["first"] not in r["lines"]: f.append(f"first {e['first']} absent")
        f += [f"qty {k}={r['lines'].get(k)}≠{v}" for k, v in (e.get("qty") or {}).items() if r["lines"].get(k) != v]
        f += [f"{x} offered" for x in e.get("excluded", []) if x in r["all"]]
        if e.get("no_gst_products") and (r["all"] & GST_PIDS): f.append(f"GST products {sorted(r['all'] & GST_PIDS)}")
        if e.get("handoff") and not r["lead"]: f.append("no handoff")
        res.append((sc["id"], f, r))
    return res


def aditya(root, fn):
    res = []
    for sc in yaml.safe_load(open(f"{root}/tests/{fn}")):
        r = run(sc["turns"]); f = []
        f += [f"missing {x}" for x in sc.get("has", []) + sc.get("items", []) if x not in r["lines"]]
        f += [f"has {x}" for x in sc.get("lacks", []) if x in r["lines"]]
        f += [f"qty {k}={r['lines'].get(k)}≠{v}" for k, v in (sc.get("qty") or {}).items() if r["lines"].get(k) != v]
        if sc.get("no_rec") and r["has_rec"]: f.append("recommended though shouldn't")
        if sc.get("handoff") and not r["lead"]: f.append("no handoff")
        if "reply_lacks" in sc and re.search(sc["reply_lacks"], r["last"]): f.append("echo in reply")
        if "history_lacks" in sc and sc["history_lacks"] in json.dumps([h for h in r["sess"]["history"]], ensure_ascii=False): f.append("PII stored")
        pr = sc.get("profile") or {}
        if "employees" in pr and r["p"].employees != pr["employees"]: f.append(f"employees {r['p'].employees}≠{pr['employees']}")
        if "locations" in pr and r["p"].sites != pr["locations"]: f.append(f"sites {r['p'].sites}≠{pr['locations']}")
        res.append((f"{fn.split('.')[0]}:{sc.get('id')} {sc.get('name','')}", f, r))
    return res


if __name__ == "__main__":
    a, b = sys.argv[1], sys.argv[2]
    sets = {"agile": agile(a)}
    for fn in ["advisor_unseen.yaml", "advisor_dev.yaml", "advisor_scenarios.yaml", "advisor_teammate.yaml"]:
        sets[fn] = aditya(b, fn)
    verbose = "-v" in sys.argv
    tot = ok = 0
    for k, res in sets.items():
        n = sum(not f for _, f, _ in res); tot += len(res); ok += n
        print(f"===== {k}: {n}/{len(res)}")
        if verbose:
            for sid, f, r in res:
                if f: print(f"  ✗ {sid}: {'; '.join(f)} | {r['lines']} | {r['last'][:100]}")
    print(f"TOTAL {ok}/{tot} = {100*ok/tot:.0f}%")
