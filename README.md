# My WE usage → Telegram

سكربت بايثون بيدخل على [My WE](https://my.te.eg/echannel/#/login) بحسابك، يجيب **Current Balance** وكل الباقات اللي في صفحة **Usage**، ويبعتلك رسالة على تليجرام **لما أي باقة توصل 25% / 50% / 75% استهلاك، ولما يفضل 10%**. بيشتغل على GitHub Actions كل 3 ساعات.

## الإعداد

### 1) بوت تليجرام
1. افتح [@BotFather](https://t.me/BotFather) → `/newbot` → خد الـ **Bot Token**.
2. ابعت أي رسالة للبوت بتاعك.
3. افتح `https://api.telegram.org/bot<TOKEN>/getUpdates` وخد قيمة `chat.id` ← ده الـ **Chat ID**.

### 2) GitHub Secrets
في الريبو: **Settings → Secrets and variables → Actions → New repository secret** وضيف:

| الاسم | القيمة |
|---|---|
| `MYWE_SERVICE_NUMBER` | الرقم اللي بتسجل بيه في My WE |
| `MYWE_PASSWORD` | باسورد My WE |
| `TELEGRAM_BOT_TOKEN` | توكن البوت |
| `TELEGRAM_CHAT_ID` | الـ Chat ID |

> لو الرقم أرضي (02…) الموقع بيطلب **Service Type** — السكربت بيختار **Internet** تلقائياً.

### 3) التشغيل
- تلقائي كل 3 ساعات.
- يدوي: **Actions → My WE usage alerts → Run workflow** (علّم على *Send a full usage report now* لو عاوز تقرير كامل فوراً).

> يُفضّل الريبو يكون **Private**.

## التجربة على جهازك
```powershell
python -m pip install -r requirements-dev.txt
python -m playwright install chromium
copy .env.example .env   # واملا القيم
python usage_monitor.py --headed --dump --dry-run   # بيفتح المتصفح ويطبع الرسالة بدل ما يبعتها
python usage_monitor.py --report                     # يبعت تقرير فعلي على تليجرام
python -m pytest -q
```
مع `--dump` بيتحفظ نص الصفحات وصور وردود الـ API في فولدر `debug/` (مش بيترفع على git).

## إزاي التنبيهات بتشتغل
- لكل باقة بيتحسب `المستخدم ÷ الإجمالي`.
- كل حد (25/50/75/90) بيتبعت **مرة واحدة بس**، والحالة بتتحفظ في `state.json`.
- لو الباقة اتجددت (الاستهلاك نزل) الحالة بتترست والتنبيهات تبدأ من الأول.
- لو حصل خطأ (باسورد غلط / الموقع اتغير) بتوصلك رسالة خطأ **مرة واحدة**.
