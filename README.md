# Udyam Express — a small business goes digital in one sitting

**Airtel SYNC 2026 · Digital / Enterprise Track A · Project Udyam Digital**
_The case uses a fictional operator, Accel Telecom, and its B2B arm Accel Business. All data is synthetic._

A phone-first journey where a small-business owner **chats (or speaks) in their language → gets one transparent monthly bill → finishes KYC in 2 minutes → tracks installation**, with no sales visit. Leads the bot can't close go to partners with a summary and a win-back score.

| Deliverable | Where |
|---|---|
| Working prototype (code) | this repo — run it in one command (below) |
| Demo video (≤ 3 min) | `submission/` (link in the deck) |
| Business case (7 slides, Airtel SYNC template) | [`submission/UdyamExpress_Submission.pptx`](submission/UdyamExpress_Submission.pptx) · PDF alongside |
| Solution architecture | [`submission/UdyamExpress_Architecture.pdf`](submission/UdyamExpress_Architecture.pdf) |
| 1-page privacy & security note | [`submission/UdyamExpress_Privacy_Note.pdf`](submission/UdyamExpress_Privacy_Note.pdf) |

## What it does (the four required modules + all three stretch goals)

| Module | What the owner / staff gets |
|---|---|
| **Advisor** | Chat or voice in English, Hindi, Hinglish offline; Marathi, Tamil, Telugu, Bengali, Gujarati, Kannada via Gemini. Understands a whole business in one message ("dental clinic in Pune, 8 staff, need CCTV and backup internet"), a GSTIN or Udyam number (auto-fills from the registry), worded counts ("me and my brother"), removals ("no security"), explicit product asks (toll-free, SD-WAN, fleet…). Hands off tier-3 towns, very large sites and custom needs to a person. |
| **Quote & checkout** | Essential / Recommended / Complete on **one monthly line**; add-ons toggle and re-price live; 12 vs 24 months (setup fee waived on 24); blocked products shown with the rule and the fix ("register for GST to unlock WhatsApp"). |
| **Smart KYC** | Per-purpose consent first → OCR on our own server (Tesseract) with auto-deskew, blur detection, GSTIN look-alike correction + checksum → GST & Udyam registry checks, name/address/date consistency → **4 verdicts**: verified · needs action · manual review · rejected, each with a plain-language fix. |
| **Tracker** | Six stages, an ETA per product from `typical_install_days`, WhatsApp-style updates — no need to call. |
| **Back office** (stretch) | Advisor hand-offs with chat summary, live orders, and a **win-back queue** of the 4,632 dropped leads ranked by propensity × recoverability, with a next-best action. |
| **Propensity score** (stretch) | Logistic regression trained Apr–May, tested on June: **AUC 0.72**, top-10% leads activate at **16.5% vs 7.5%** (2.2×). Language deliberately excluded for fairness. |
| **Voice** (stretch) | Browser speech input in 9 Indian locales. |

**Design rule — the AI talks, the rules engine decides.** Products, eligibility (city tier, min staff/sites, GST), dependencies and prices come only from `product_catalogue.csv`. The LLM only extracts facts and rephrases; any number in its output that isn't in our text is discarded.

## Evidence

| Check | Result |
|---|---|
| Automated tests | `pytest` — 27 pass (rules, KYC, advisor, end-to-end API) |
| Every one of the 5,000 lead profiles | 3 tiers each, **0 rule violations** |
| Historic sales that broke catalogue rules | **48 of 368** activations — all blocked by our engine |
| KYC specimens K01–K12 | **12 / 12** match our answer key (K01 rejected, K07 manual review, K04/K05/K06/K11 needs action, 6 verified) |
| Advisor on 268 unseen public scenarios written by other teams | **75 %** pass (rule-based mode, no LLM) — `tests/bench_public.py` |

## Run it

```bash
docker build -t udyam . && docker run -p 8000:8000 udyam        # open http://localhost:8000
```
Without Docker (Python 3.11+, `tesseract-ocr` installed):
```bash
pip install -r requirements.txt
uvicorn app.main:app --port 8000
pytest -q
```
Optional: `export GEMINI_API_KEY=...` (free Google AI Studio key) for 6 more languages and free-form understanding. Without it everything still works offline.

## Repository
```
app/core.py         catalogue rules engine, pricing, GSTIN checksum, mock registries
app/recommender.py  profile → 3 rule-checked tiers with plain-language reasons
app/nlu.py          English / Hindi / Hinglish understanding, PII redaction
app/advisor.py      conversation, hand-offs, multilingual templates
app/llm.py          optional Gemini layer with guardrails
app/kyc.py          OCR → extraction → registry & consistency checks → verdict
app/backoffice.py   orders/tracker, propensity model, funnel, impact replay
app/main.py         FastAPI + static web app
static/             mobile-first web UI (owner app + back office)
data/               the case dataset (synthetic)
tests/              pytest suite + public-scenario benchmark
submission/         deck, architecture, privacy note
```
