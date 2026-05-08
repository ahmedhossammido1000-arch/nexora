# NEXORA v3 — Complete Rebuild Plan

**Goal:** Transform Nexora from Amazon-clone into AI-powered viral product discovery platform.

**Compliance target:** Amazon Associates safe — NO static prices, ratings, reviews, or copied content.

---

## 1. Current State Analysis

### What we have:
| Component | File | Status |
|---|---|---|
| Scraper | `nexora_market_intelligence_v2.py` | ✅ Works — 28 products |
| Site Builder | `site_builder/nexora_site_builder.py` | ⚠ Generates non-compliant HTML |
| Website (live) | `website/` (28 product pages) | ❌ Has prices, ratings, reviews |
| Pinterest Generator | `pinterest/nexora_pinterest_v2.py` | ✅ Works |
| Pinterest Automation | Make.com scenario | ⏸ Paused per user request |
| Legal pages | privacy.html, terms.html, disclosure.html | ✅ Mostly compliant |
| Deployment | Netlify (`nexora-shop-us.netlify.app`) | ✅ Live |

### What MUST be removed (Phase 1):
From `products.js` and ALL rendered pages:
- ❌ `price`, `listPrice`, `discount` fields
- ❌ `rating`, `reviewCount`
- ❌ `socialProof` ("5K+ bought in past month")
- ❌ Copied Amazon descriptions (currently identical to title)
- ❌ Copied Amazon titles (verbatim with all the keyword stuffing)
- ❌ `aggregateRating` and `offers.price` from schema.org JSON-LD
- ❌ Star displays, "(55,820 reviews)", "$2.29", "83% off"

---

## 2. New Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  Amazon Link Input (manual/auto-list)                       │
│    └─> extract: name, image, category, asin only            │
│        (NO prices, ratings, reviews, descriptions)          │
└──────────────────┬──────────────────────────────────────────┘
                   ▼
┌─────────────────────────────────────────────────────────────┐
│  AI Content Engine (NEW)                                    │
│  - ai_engine.py                                             │
│  - Gemini API: viral title, hook, benefits, SEO, captions   │
│  - Pollinations API: AI hero + lifestyle images             │
│  - Nexora Score: virality + usefulness + value              │
└──────────────────┬──────────────────────────────────────────┘
                   ▼
┌─────────────────────────────────────────────────────────────┐
│  Site Builder v3 (REWRITTEN)                                │
│  - site_builder_v3.py                                       │
│  - Generates: index, category, product, blog, finds-feed    │
│  - Compliant schema.org (no aggregateRating, no offers.price)│
└──────────────────┬──────────────────────────────────────────┘
                   ▼
┌─────────────────────────────────────────────────────────────┐
│  Static Site (REDESIGNED)                                   │
│  - Homepage with Nexora Finds feed (TikTok-style)           │
│  - Trending Right Now section                               │
│  - Blog/Discover section                                    │
│  - Premium dark UI, sticky CTAs, exit popups                │
│  - Cookie consent, push notifications, email collection     │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. New File Structure

```
nexora/
├── data/
│   ├── products.json              ← clean source data (no prices/ratings)
│   ├── ai_cache.json              ← Gemini outputs cached (cost saving)
│   └── ai_images/                 ← Generated AI images (uploaded to ImgBB)
├── ai_engine/
│   ├── __init__.py
│   ├── gemini_client.py           ← Gemini API wrapper
│   ├── pollinations_client.py     ← Pollinations AI image gen
│   ├── content_generator.py       ← orchestrates: title→hook→benefits→SEO
│   └── nexora_score.py            ← virality/usefulness/value scoring
├── site_builder_v3/
│   ├── __init__.py
│   ├── builder.py                 ← main orchestrator
│   ├── templates/
│   │   ├── base.html              ← shared head/header/footer/cookies
│   │   ├── index.html             ← Nexora Finds + Trending
│   │   ├── product.html           ← redesigned product page
│   │   ├── category.html          ← category pages
│   │   ├── blog.html              ← blog listing
│   │   ├── blog_post.html         ← blog post template
│   │   └── finds.html             ← TikTok-style scrolling feed
│   ├── seo.py                     ← schema, sitemap, robots, OG
│   └── components.py              ← cards, badges, CTAs, popups
├── website/                       ← OUTPUT (built site, deployed to Netlify)
│   ├── index.html
│   ├── finds.html                 ← NEW — TikTok-style feed
│   ├── blog/                      ← NEW — blog/discover section
│   ├── category/
│   ├── product/
│   ├── assets/
│   │   ├── site.css
│   │   ├── app.js                 ← cookie consent, sticky CTA, exit popup
│   │   └── analytics.js           ← CTR tracking, click events
│   └── (legal pages, sitemap, robots)
├── pinterest/                     ← unchanged (paused)
└── REBUILD_PLAN_v3.md             ← this file
```

---

## 4. Phase-by-Phase Roadmap

### Phase 1 — Cleanup & Amazon Compliance ⚡ FIRST
**Output:** Compliant product pages with viral content (NO prices/ratings/reviews).
- Strip products.js of forbidden fields
- Rewrite product page template
- Add new CTAs: "Check Today's Deal", "View on Amazon", "See Why It's Trending", "Check Availability"
- Update schema.org to remove `aggregateRating`, `offers.price`
- Add disclosure to footer + every product page

### Phase 2 — AI Content Engine
**Output:** All product content auto-generated by AI, not copied from Amazon.
- Build `ai_engine/gemini_client.py` (REQUIRES: Gemini API key from user)
- Build `ai_engine/pollinations_client.py` (no key needed)
- For each product, generate:
  - Viral title (e.g., "This $? Gadget Solves a Daily Frustration")
  - Emotional hook paragraph
  - 3–5 product benefits (bullet list)
  - SEO meta title + description
  - Pinterest title + description
  - TikTok caption
  - Instagram caption
- Generate AI hero image + 2–3 lifestyle images per product

### Phase 3 — SEO & Google Optimization
**Output:** Every page indexable, schema-rich, fast.
- Dynamic SEO per page (unique title, meta, keywords, OG tags, Twitter cards)
- Schema.org: Product (without offers/aggregateRating), BreadcrumbList, ItemList, Article (for blog)
- Sitemap.xml + robots.txt + canonical URLs
- Image lazy loading, compressed assets, mobile-first CSS
- **Blog/Discover section**: 5–10 AI-assisted articles like "Top 5 Viral Kitchen Gadgets"

### Phase 4 — Viral Brand Experience
**Output:** Premium, social-driven UX that retains visitors.
- **Nexora Finds**: Vertical TikTok-style scrolling feed (mobile + desktop)
- **Trending Right Now**: Section showing most-viewed products (tracked via JS)
- **Nexora Score**: Display 3 sub-scores per product (Virality / Usefulness / Value)
- **Related products**: 3-card grid on every product page
- Premium dark UI consistency (already partly there)

### Phase 5 — Social & Traffic Automation
**Output:** Multi-platform content per product.
- Captions for TikTok, Instagram, Pinterest auto-generated (Phase 2 covers gen)
- Vertical Pinterest images (already exist via pinterest generator)
- Make.com schema kept intact for resume after rebuild

### Phase 6 — Conversion Optimization
**Output:** Higher CTR to Amazon affiliate links.
- Sticky CTA button on product pages (visible while scrolling)
- Psychological CTA phrases rotating: "People love this", "Trending on TikTok", etc.
- Exit-intent popup: "🔥 Don't miss today's viral finds."

### Phase 7 — Audience Building
**Output:** Captured emails + push subscribers.
- Email collection popup ("Get weekly viral product finds 🚀")
- Email storage: localStorage + Netlify Forms (no backend)
- Push notifications: OneSignal integration (REQUIRES: OneSignal app ID)

### Phase 8 — Analytics & Data
**Output:** Visibility into what works.
- Lightweight analytics.js: track CTR, page views, scroll depth, button clicks
- Store events in Netlify Functions or localStorage→batch send
- Simple admin dashboard at `/admin/dashboard.html` (password-protected)
- OR integrate: Plausible / Umami / Google Analytics 4

### Phase 9 — Legal, Trust & Cookie System
**Output:** GDPR + Amazon TOS compliance.
- Cookie consent popup (Accept/Learn More) → localStorage
- Update Privacy Policy with cookie + AI disclosure
- Cookie Policy page (NEW)
- Affiliate Disclosure page (already exists, needs update)
- Terms & Conditions (already exists)
- Footer disclosure on every product page

### Phase 10 — Future-Ready Architecture
**Output:** Codebase ready for next features without rewrites.
- Modular component system (cards, sections, popups all reusable)
- Data layer abstraction (products.json → easy to swap to DB later)
- Wishlist hooks (localStorage now, easy to migrate to user accounts)
- Comparison engine stub (compare 2 products side-by-side)
- Personalized feed structure (based on click history in localStorage)

---

## 5. Required Credentials

| Service | Purpose | Action |
|---|---|---|
| **Gemini API key** | All AI content generation | Get at https://aistudio.google.com/apikey |
| Pollinations | AI image generation | NO key needed (free) |
| ImgBB (existing) | Host AI-generated images | ✅ already have key |
| OneSignal | Push notifications | Sign up at https://onesignal.com (Phase 7) |
| Plausible/GA4 | Analytics | Optional (Phase 8) |

---

## 6. Execution Order (Recommended)

| Order | Phase | Why first |
|---|---|---|
| 1 | Phase 1 | Critical: Amazon TOS compliance — must remove forbidden content ASAP |
| 2 | Phase 9 | Pair with Phase 1 (cookie consent + legal updates) |
| 3 | Phase 2 | AI Engine — core of new value proposition |
| 4 | Phase 3 | SEO — drives organic traffic |
| 5 | Phase 4 | Brand UX — converts visitors |
| 6 | Phase 6 | Conversion — converts to Amazon clicks |
| 7 | Phase 5 | Social automation (also resume Pinterest here) |
| 8 | Phase 7 | Audience capture |
| 9 | Phase 8 | Analytics (last because needs traffic to validate) |
| 10 | Phase 10 | Future-ready (refactor pass after all features built) |

---

## 7. Deliverables per Phase

Each phase ships:
1. ✅ Working code (committed to repo)
2. ✅ Updated `website/` folder (rebuilt)
3. ✅ Redeploy to Netlify (`nexora-shop-us.netlify.app`)
4. ✅ Brief CHANGELOG entry
5. ✅ User confirmation before next phase

---

## 8. Estimated Scope

This is a multi-day project. Conservative estimate:
- Phase 1+9: 2-3 hours
- Phase 2: 4-6 hours (depends on AI generation speed for 28 products)
- Phase 3: 2-3 hours
- Phase 4: 4-6 hours (Nexora Finds feed is the big one)
- Phase 5: 1-2 hours (mostly already done)
- Phase 6: 2-3 hours
- Phase 7: 2-3 hours
- Phase 8: 2-4 hours
- Phase 10: 2-3 hours (refactor + cleanup)

**Total: ~22-35 hours of focused work.**

---

## 9. Next Action

**Awaiting from user:**
1. Gemini API key (at https://aistudio.google.com/apikey)
2. Confirmation: deploy approach (A: side branch + atomic swap, B: incremental updates)

**Once received, I will:**
1. Save credential securely
2. Start Phase 1 immediately
3. After Phase 1 completes → redeploy → ask for confirmation → move to Phase 2
