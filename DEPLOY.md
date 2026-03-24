# 🚀 GitHub → Railway Deploy Qo'llanmasi

## 📁 Loyiha fayllari
```
videobot/
├── bot.py
├── downloader.py
├── config.py
├── requirements.txt
├── Procfile
├── railway.toml
├── nixpacks.toml
├── .env.example
├── .gitignore
└── README.md
```

---

## 1️⃣ GitHub ga yuklash

### GitHub account yo'q bo'lsa:
👉 https://github.com → Sign up

### Repository yaratish:
1. GitHub → **New repository**
2. Nom: `video-downloader-bot` (yoki xohlagan nom)
3. **Private** ✅ (tokenni yashirish uchun)
4. **Create repository**

### Fayllarni yuklash:
```bash
# Papkangizga kiring
cd videobot

# Git boshlash
git init
git add .
git commit -m "Initial commit: video downloader bot"

# GitHub bilan bog'lash (github.com dagi URL ni ko'chiring)
git remote add origin https://github.com/USERNAME/video-downloader-bot.git
git branch -M main
git push -u origin main
```

> ⚠️ `.env` fayli `.gitignore` da — GitHub ga chiqmaydi (xavfsiz)

---

## 2️⃣ Railway ga deploy

### Railway account:
👉 https://railway.app → **Login with GitHub**

### Yangi project:
1. **New Project** tugmasini bosing
2. **Deploy from GitHub repo** tanlang
3. `video-downloader-bot` ni tanlang
4. **Deploy Now** bosing

---

## 3️⃣ Environment Variables qo'shish

Railway dashboard → loyihangiz → **Variables** tab:

| Key | Value (misol) |
|-----|--------------|
| `BOT_TOKEN` | `1234567890:ABCdefGHI...` |
| `CHANNEL_ID` | `@sizning_kanal` |
| `CHANNEL_LINK` | `https://t.me/sizning_kanal` |
| `CHANNEL_NAME` | `Mening Kanalim` |

**Qo'shish usuli:**
1. Variables → **New Variable**
2. Key va Value kiriting
3. **Add** bosing
4. Bot avtomatik qayta ishga tushadi ✅

---

## 4️⃣ Deploy tekshirish

- Railway dashboard → **Deployments** tab
- Yashil ✅ = muvaffaqiyatli
- **View Logs** → bot xabarlarini ko'rish

```
✅ Bot ishga tushdi
```

---

## 🔄 Kodni yangilash

```bash
# O'zgarish qilib, GitHub ga push qiling:
git add .
git commit -m "Yangilanish"
git push
```
Railway avtomatik qayta deploy qiladi! 🎉

---

## ⚠️ Muhim eslatmalar

- Railway **bepul plan**: oyiga 5$ kredit (taxminan 500 soat)
- Bot **worker** sifatida ishlaydi (HTTP server emas)
- `downloads/` papkasi vaqtinchalik — Railway restart da tozalanadi (bu normal)
- Loglarni Railway dashboard dan ko'rish mumkin
