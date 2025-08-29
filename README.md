<!-- Hero -->
<h1 align="center">🎂 HBD_NUNU</h1>
<p align="center">
  <i>A tiny, delightful birthday website to celebrate, share photos, and leave warm messages.</i>
</p>

---

## ✨ What’s inside

- **Main Page**
  - 🎥 *Video letter from FAKER* (AI-generated with Applio & Wav2Lip)
  - 🪖 Photo **slideshow**
  - 💌 Birthday owner’s personal **message**
  - 📝 **Guestbook** (anonymous posts allowed)
- **Letter Page**
  - 💌 A personal letter from the developer to the birthday owner
- **Countdowns**
  - ⏳ **Birthday**: Days / Hours / Minutes / Seconds
  - 🎖 **Discharge**: Years / Months / Days + progress bar

---

## 🔐 Birthday Owner perks

Login with a password to unlock owner-only features:

- 💬 Edit your personal birthday message  
- 📸 Manage photos  
  - Upload
  - Delete selected
  - **Reset** to original set
- 🗑 Remove guestbook entries  
- 💌 Open the **private letter** page

> The public cannot see the Letter page and cannot delete messages/photos.

---

## 🚀 Quick Start

### 1) Clone
```bash
git clone https://github.com/bettyshin1213/hbd_public.git
cd hbd_public
```

### 2) Run Locally
For Windows,
```bash
run_local.bat
```
For macOS/Linux,
```bash
sh run_local.sh
```

---

## 🛠 Tech Stack

- **Backend**: Flask (Python), SQLAlchemy  
- **Frontend**: Jinja2, HTML/CSS/JS, Swiper.js  
- **DB**: PostgreSQL (NCP VM)
- **Server**: Nginx (HTTPS) + Gunicorn (WSGI)  
- **Infra**: Naver Cloud Platform (VPC, NAT Gateway, Route Tables, VM Instances)  
- **Container**: Docker (App Server runtime)  
- **AI Media**: Applio (Voice Conversion) + Wav2Lip (lip-sync video for Faker message) with L4 GPU

---

## 👩‍💻 Architecture Diagram

<img width="847" height="765" alt="image" src="https://github.com/user-attachments/assets/07cbaadd-19b1-4a62-8569-745ca80295be" />
