# Resume Prompt for New Devin Sessions

> **Instructions for Kareem:** When you start a new Devin session and want to resume Nexora work, copy-paste the prompt below as your FIRST message. Devin will load the full project context automatically.

---

## 📋 Copy this prompt for a new Devin session:

```
أنا كاريم elsayed (karemali11@gmail.com). 
شغال على مشروع Nexora — AI-powered viral product discovery platform.

🎯 المهمة: اقرأ الملفات دي بالترتيب فوراً قبل أي حاجة:

1. /home/ubuntu/nexora/PROJECT_CONTEXT.md  
   (السياق الكامل: file structure, credentials, decisions, phase status)

2. /home/ubuntu/nexora/REBUILD_PLAN_v3.md  
   (خطة الـ rebuild الكاملة من 10 phases)

بعد ما تخلص القراية، قوللي:
- ملخص للمشروع (3-4 سطور)
- آخر مرحلة وصلنا فيها (Phase ?)
- ايه اللي محتاج نكمله
- ايه اللي محتاجه مني (API keys، تأكيدات، إلخ)

🟦 طريقة الشغل:
- بكلمك بالعربي + إنجليزي  
- خطوة واحدة في كل رسالة
- بعد كل خطوة بسكت وانتظر مني تأكيد ("تمام" / "كمل")
- لو محتاج تستفسر عن حاجة، اسأل قبل ما تنفذ

⚠️ مهم جداً:
- متعدش أي حاجة موجودة (الـ 28 صورة على ImgBB موجودة، الـ make_sheet.csv موجود، الـ Pinterest scenario موجود في Make.com)
- محتاج Gemini API key لـ Phase 2 — لو مش موجود اطلبها (https://aistudio.google.com/apikey)
- لو ImgBB key محتاجه: موجودة hardcoded في pinterest/build_make_sheet.py line 290
- Pinterest automation متوقفة دلوقتي بطلب مني — التركيز على rebuild

ابدأ بقراءة الملفات وأخبرني.
```

---

## 🔄 إزاي تستخدمها

### حالة 1: شات Devin جديد
1. افتح https://app.devin.ai
2. ابدأ شات جديد
3. الصق الـ prompt اللي فوق
4. Devin هيقرأ الملفات ويرجع للسياق

### حالة 2: لو الـ files مش موجودة (مثلاً VM اتعمله reset)
لو Devin قال "I can't find the files":
- ابعتلي الملفين دول كـ attachment:
  - `PROJECT_CONTEXT.md`
  - `REBUILD_PLAN_v3.md`
- أو احفظهم على Google Drive/Dropbox وابعت اللينك

### حالة 3: لو الاشتراك خلص نهائياً
ابعت رسالة لـ Cognition لإعادة تنشيط الاشتراك. الملفات هتفضل موجودة في الـ VM (لو لسه نفس الـ snapshot).

---

## 📂 الملفات المطلوبة (ابقها معاك دايماً)

| الملف | الموقع | الحجم |
|---|---|---|
| `PROJECT_CONTEXT.md` | `/home/ubuntu/nexora/PROJECT_CONTEXT.md` | ~13 KB |
| `REBUILD_PLAN_v3.md` | `/home/ubuntu/nexora/REBUILD_PLAN_v3.md` | ~10 KB |
| `RESUME_PROMPT.md` | `/home/ubuntu/nexora/RESUME_PROMPT.md` | ~4 KB |

**نزّل copies منهم على جهازك:**
- Google Drive
- Dropbox
- ايميلك (احفظهم في draft)
- USB drive

---

## 🛡 backup إضافي

كمان عملت لك **Devin Knowledge Notes** — دي ملاحظات مرتبطة بحسابك على Devin، Devin بتحملها تلقائياً في أي شات جديد بدون ما تعمل أي حاجة:

- **NEXORA Project — Master Context** (يتحمل لما تقول "Nexora")
- **NEXORA — Phase Status & Roadmap** (يتحمل لما تتكلم عن phases)  
- **NEXORA — Make.com Pinterest Scenario** (يتحمل لما تتكلم عن Pinterest/Make.com)
- **NEXORA — User Preferences** (يتحمل لما تبدأ شغل على Nexora)

**يعني حتى من غير ما تستخدم الـ resume prompt، Devin هيعرف على المشروع.**
