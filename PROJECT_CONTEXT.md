# NEXORA — Complete Project Context

> **Purpose of this file:** Single source of truth so any future Devin session (or human reader) can instantly understand the entire Nexora project. If you're a Devin session reading this for the first time, READ THIS WHOLE FILE before doing anything.

---

## 1. Project Identity

| | |
|---|---|
| **Project name** | Nexora |
| **Owner** | Kareem Elsayed (karemali11@gmail.com) |
| **Brand tagline** | "Smart Finds. Better Life." |
| **Logo** | https://f.top4top.io/p_3776hn9nu1.png |
| **Live URL** | https://nexora-shop-us.netlify.app |
| **Hosting** | Netlify (manual zip drop; not connected to git) |
| **Repo location (Devin VM)** | `/home/ubuntu/nexora/` |
| **Git repo** | NOT a git repo — local files only |

---

## 2. What is Nexora?

**Today (v2.x):** Static affiliate site showing 28 Amazon products with prices, ratings, reviews, and discounts.

**Tomorrow (v3 — being built now):** **AI-powered viral product discovery platform** — premium, brand-driven, NOT an Amazon clone. Compliant with Amazon Associates TOS (no static prices/ratings/reviews).

See `REBUILD_PLAN_v3.md` for the full 10-phase roadmap.

---

## 3. Major Pivots / Decisions

### Pivot 1 (May 2026): Pause Pinterest, Rebuild Everything
User explicitly stopped Pinterest marketing automation work and pivoted to full Nexora rebuild.

**Quote from user:**
> "لا انا قصدي ان مرحله التسويق هنوقفها دلوقتي وهنعمل اعاده هيكله للمشروع وللموقع"
> (No — I mean we're stopping the marketing phase now, we're rebuilding the project and the website.)

### Pivot 2: Credential-based OAuth (NOT Pinterest API)
User wants email/password Pinterest login via Make.com — NOT official Pinterest API tokens.

### Pivot 3: Backend CSV modifications, NOT Make.com formulas
User rejected Make.com switch() formula approach for board mapping after validation errors.
Quote: **"افضل شئ خد الملف انت عدل عليه كامل و اكنتبهولي بالتعديل"** (Better to edit the file completely and send it back)

---

## 4. File Structure

```
/home/ubuntu/nexora/
├── PROJECT_CONTEXT.md                    ← THIS FILE (read first)
├── REBUILD_PLAN_v3.md                    ← Full 10-phase rebuild plan
├── ANALYSIS_AND_PLAN.md                  ← v2 analysis (historical)
├── README.md                             ← v2.1 documentation
├── CHANGELOG_v2.1.md … v2.6.md           ← v2.x changelogs
├── REDEPLOY_GUIDE.md, DEPLOY_NETLIFY_GUIDE.md  ← deployment docs
├── requirements.txt                       ← Python deps
│
├── nexora_market_intelligence_v2.py       ← Scraper (Amazon trends)
├── nexora_market_intelligence_v1_original.py  ← OLD v1 (backup)
│
├── site_builder/
│   └── nexora_site_builder.py            ← Generates static HTML from products.js (~1408 lines)
│
├── website/                              ← OUTPUT directory (deployed to Netlify)
│   ├── index.html                        ← Homepage
│   ├── products.js                       ← Product data (28 products)
│   ├── site.css, pages.css               ← Styles
│   ├── sitemap.xml, robots.txt           ← SEO
│   ├── google0e18519c81a40ea2.html       ← Google Search Console
│   ├── about.html, contact.html, contact-success.html
│   ├── privacy.html, terms.html, disclosure.html
│   ├── product/                          ← 28 product pages (NOT compliant — has prices/ratings)
│   │   └── *.html (28 files)
│   └── category/                         ← 4 category pages
│       ├── tech.html, home.html, beauty.html, pet.html
│
└── pinterest/                            ← Pinterest automation (paused)
    ├── nexora_pinterest_v2.py            ← Pin image generator
    ├── build_make_sheet.py               ← Builds CSV for Make.com
    ├── PINTEREST_AUTOMATION_GUIDE.md
    ├── PINTEREST_2_ACCOUNTS_GUIDE.md
    ├── output_v2/
    │   ├── make_sheet.csv                ← 28 pins ready for Google Sheets (with board_id)
    │   ├── upload/                       ← Generated pin images
    │   └── bulk_create_csv/              ← Pinterest bulk upload format
    └── make_blueprints/
        └── blueprint_pinterest_auto_poster.json  ← Make.com blueprint (incompatible)
```

---

## 5. Credentials & API Keys

### Already configured (in source files):

| Service | Where stored | Notes |
|---|---|---|
| **ImgBB API key** | `pinterest/build_make_sheet.py` line 290 (hardcoded) + env var `IMGBB_API_KEY` | Value: `9c5a54329d929ce98cde36976412fb23`. Used for hosting pin images. 28 images already uploaded. |
| **Amazon Associate tag** | Embedded in product URLs in `products.js` | `kareemelsay0a-20` (US) |

### Need to be requested from user (for v3 rebuild):

| Service | Purpose | Notes |
|---|---|---|
| **Gemini API key** | All AI content generation (Phase 2) | Get at https://aistudio.google.com/apikey. User has not yet provided. |
| **OneSignal app ID** | Push notifications (Phase 7, optional) | https://onesignal.com |
| **Plausible/GA4** | Analytics (Phase 8, optional) | |

### Pinterest accounts (paused but worth knowing):

| Account | Name | Boards |
|---|---|---|
| Account 1 (Morning) | nexora-shop | "Smart Tech Finds" (ID: 1088182397404596892), "Home & Kitchen Inspiration" (ID: 1088182397404596893) |
| Account 2 (Night) | nexora | "Pet Parents Picks" (ID: 1118229851168463032), "Beauty & Self-Care" (ID: 1118229851168463030) |

### Google Sheets (for Pinterest, paused):

- **Sheet ID:** `1WQSBdMSX42iu9ypqSVvb0hjUnY8GeToCcMegWWjYb50`
- **Sheet name:** `make_sheet`
- **Connected via:** User's Google OAuth in Make.com

### Make.com:

- **Scenario URL:** https://us2.make.com/2225427/scenarios/4979425/edit
- **Status:** PAUSED (per user pivot — will resume after rebuild)

---

## 6. Phase Status (as of 2026-05-05)

### Completed (v2.x):
- ✅ Market intelligence scraper (Phase 1-3)
- ✅ Static site generator (Phase 4)
- ✅ 28 product pages built and live
- ✅ Legal pages (privacy, terms, disclosure)
- ✅ Sitemap, robots.txt
- ✅ Pinterest pin generator (v2.1)
- ✅ 28 pin images uploaded to ImgBB
- ✅ Make.com scenario built (6 modules + 2 filters)

### In progress (Phase 7B — PAUSED for v3 rebuild):
- ⏸ Pinterest automation testing (was blocked on board_id mapping)

### Pending (v3 rebuild — 10 phases):
See `REBUILD_PLAN_v3.md` for full details.

| Phase | Title | Blockers |
|---|---|---|
| 1 | Cleanup & Amazon Compliance | None — can start immediately |
| 9 | Legal, Trust & Cookie System | Pair with Phase 1 |
| 2 | AI Content Engine | Needs Gemini API key |
| 3 | SEO & Google Optimization | None |
| 4 | Viral Brand Experience | None |
| 6 | Conversion Optimization | None |
| 5 | Social & Traffic Automation (resume Pinterest) | None |
| 7 | Audience Building | OneSignal optional |
| 8 | Analytics & Data | None |
| 10 | Future-Ready Architecture | Done last as refactor |

---

## 7. Critical Compliance Issues (Phase 1 MUST fix)

Current site has **forbidden content per Amazon Associates TOS:**

- ❌ Static prices: `$2.29`, `$14.99`, `$17.77`
- ❌ Static ratings: `4.4 stars`, `★★★★½`
- ❌ Static review counts: `(55,820 reviews)`, `(74,952 reviews)`
- ❌ Discounts: `83% off`, `29%`
- ❌ Social proof: `5K+ bought in past month`
- ❌ Copied Amazon descriptions (identical to titles)
- ❌ Copied Amazon titles (verbatim with keyword stuffing)
- ❌ `schema.org/Product` with `aggregateRating` and `offers.price`

**ALL of these must be removed in Phase 1.**

---

## 8. User Communication Style

### Language
- **Egyptian Arabic + technical English**
- User speaks Arabic colloquially: "تمام كمل" (ok continue), "ابعتلي screenshot" (send me screenshot)
- Technical terms in English: API, connection, module, route, board, filter

### Workflow Preference (CRITICAL!)
**One step at a time.** User explicitly stated:
> "تقولي خطه تسكت وقولي لمه تخلص قولي كمل"
> (Tell me one step, be silent, confirm when done, then continue)

**Do NOT:**
- Provide multi-step checklists in one message
- Combine steps
- Move on without explicit user confirmation

**DO:**
- Send one concise instruction
- Wait for "تمام" / "خلصت" / "كمل" / screenshot
- Then provide next step

### Screenshots
User often sends screenshots of:
- Make.com canvas
- Google Sheets
- Browser windows
- Errors

Always inspect them carefully before responding.

### Decision-making
User prefers backend code modifications over UI formula tricks. He rejected:
- Make.com `switch()` formula approach
- Manual board ID mapping in UI

He preferred:
- Adding `board_id` column directly to CSV
- Pre-built JSON files over UI work
- Python scripts for data transformations

---

## 9. Known Errors & Workarounds (Historical)

### Error 1: Pinterest API rejects board names
- Pinterest API requires numeric board IDs (regex `^\d+$`)
- Solution: Added `board_id` column to CSV with numeric IDs
- Status: Fix applied, but unverified due to Pinterest pause

### Error 2: CSV multi-line description fields broke Google Sheets import
- Description fields contain literal newlines (not RFC 4180 escaped)
- Caused row fragmentation during import
- Solution (planned): Regenerate CSV with proper csv.writer quoting
- Status: Pending (deprioritized — Pinterest paused)

### Error 3: Make.com blueprint JSON incompatible
- Pre-built JSON had module names that didn't match current Make.com platform
- Solution: Built scenario manually from scratch via UI

### Error 4: User typed `python3` on Windows
- Windows uses `python` command, not `python3`
- Documented in PINTEREST_SETUP_GUIDE.md

### Error 5: ImgBB key was placeholder text
- User typed `set IMGBB_API_KEY=your_actual_key_here` literally with placeholder
- Solution: Hardcoded key in `build_make_sheet.py` line 290 with env var fallback

---

## 10. How to Resume Work in a New Session

If you're a new Devin session reading this file:

### Step 1: Confirm context
Send to user:
> "I've loaded your Nexora project context from PROJECT_CONTEXT.md and REBUILD_PLAN_v3.md. We're at the start of v3 rebuild (Phase 1 — Cleanup). Should I continue from there, or do you want to update something first?"

### Step 2: Identify current phase
- Check `REBUILD_PLAN_v3.md` for the 10-phase roadmap
- Check this file's "Phase Status" section for what's done
- Ask user explicitly: "Which phase are we on?"

### Step 3: Follow user's working style
- One step at a time
- Arabic + English
- Wait for confirmation
- Use screenshots

### Step 4: Critical credentials check
- Is Gemini API key available? If not, ask user.
- ImgBB key: hardcoded in `pinterest/build_make_sheet.py` line 290.

### Step 5: Don't recreate work
- 28 product pages already built (in `website/product/`)
- 28 pin images already uploaded to ImgBB
- Pinterest CSV already prepared
- Make.com scenario already configured (paused)

---

## 11. Quick Bootstrap Prompt (for new sessions)

If the user opens a new Devin session, they can paste this prompt:

```
أنا كاريم. أكمل مشروع Nexora اللي شغال عليه.

اقرأ الملفات دي بالترتيب:
1. /home/ubuntu/nexora/PROJECT_CONTEXT.md  (السياق الكامل)
2. /home/ubuntu/nexora/REBUILD_PLAN_v3.md  (خطة الـ rebuild)

بعد ما تخلص القراية، قوللي على آخر مرحلة وصلنا فيها وايه اللي محتاج نكمله.

تذكير مهم:
- بكلمك بالعربي + إنجليزي
- خطوة وحدة في كل رسالة، ساكت، ولما أقولك "كمل" تكمل
- لو محتاج Gemini API key أو حاجة، اطلبها مرة واحدة
- متعدش حاجة موجودة من جديد (مثلاً متعملش رفع صور تاني، الـ 28 صورة موجودين علي ImgBB)
```

---

## 12. Last Updated

- **Date:** May 5, 2026 (last conversation)
- **By:** Devin session `f6b628630a2c44c9b0c6cb438f350960`
- **Status:** Plan approved by user, awaiting Gemini API key + deploy approach approval before Phase 1 starts.

---

## 13. Contact

If you (Devin or human reader) have any doubts, ASK THE USER. Do not assume. The user is at `karemali11@gmail.com` and prefers Arabic communication.
