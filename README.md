# Instagram Auto Comment Bot

Monorepo sederhana dengan frontend Next.js dan backend FastAPI.

## Struktur Proyek

```text
instagram-bot-app/
├── frontend/    # Next.js + TypeScript
└── backend/     # FastAPI + Python
```

## Menjalankan Secara Lokal

### 1. Konfigurasi environment

Salin template environment:

```bash
cd instagram-bot-app
cp backend/.env.example backend/.env
cp frontend/.env.local.example frontend/.env.local
```

Sesuaikan nilainya jika diperlukan. Jangan commit file `.env` atau `.env.local`.
Frontend menggunakan `BACKEND_API_URL` pada proxy Next.js untuk meneruskan request ke FastAPI.

### 2. Menjalankan backend

Pastikan Redis sedang berjalan di `localhost:6379`, lalu buka terminal pertama:

```bash
cd instagram-bot-app/backend
source .venv/bin/activate
uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

Backend tersedia di `http://localhost:8000`.
Health check: `http://localhost:8000/health`.

Buka terminal kedua untuk menjalankan Celery Worker:

```bash
cd instagram-bot-app/backend
source .venv/bin/activate
celery -A celery_app.celery_app worker --loglevel=info
```

### 3. Menguji API

Dokumentasi interaktif tersedia di `http://localhost:8000/docs`.

Untuk mengirim job:

```bash
curl -X POST http://localhost:8000/api/start-job \
	-H "Content-Type: application/json" \
	-d '{"username":"demo_user","target":"example_post","comment_count":3}'
```

Gunakan `task_id` dari respons untuk memeriksa status:

```bash
curl http://localhost:8000/api/job-status/TASK_ID
```

## Deployment Production

Arsitektur yang direkomendasikan:

```text
Browser -> Vercel (Next.js + /api proxy)
		      |
		      v
	      Render Web Service (FastAPI)
		      |
		      v
		Upstash Redis <-> Render Worker (Celery + Playwright)
```

Vercel menangani frontend dan proxy API singkat. FastAPI dan Celery worker
berjalan sebagai service terpisah karena proses Playwright tidak cocok dengan
batas waktu serverless Vercel.

### Push ke GitHub

```bash
cd instagram-bot-app
git init
git add .
git commit -m "Prepare production deployment"
git branch -M main
git remote add origin https://github.com/USERNAME/REPOSITORY.git
git push -u origin main
```

Jangan commit `backend/.env`, API key, session cookie, atau file state.

### Deploy frontend ke Vercel

1. Buka `https://vercel.com/new` dan pilih repository GitHub.
2. Gunakan root repository sebagai project root agar `vercel.json` digunakan.
3. Pilih framework preset **Next.js**.
4. Tambahkan environment variable production:

```env
BACKEND_API_URL=https://instagram-bot-api.onrender.com
```

`NEXT_PUBLIC_API_URL` tidak diperlukan oleh UI saat ini. Jangan menaruh
`DEEPSEEK_API_KEY`, `REDIS_URL`, atau password di variable `NEXT_PUBLIC_*`.

Jika memilih **Root Directory = frontend** di Vercel, pindahkan konfigurasi ke
`frontend/vercel.json` atau gunakan konfigurasi Next.js default, bukan keduanya.

### Deploy API dan worker ke Render

1. Buka Render Dashboard, pilih **New > Blueprint**.
2. Hubungkan repository GitHub ini.
3. Render membaca `render.yaml` dan membuat service API serta worker.
4. Isi `REDIS_URL`, `DEEPSEEK_API_KEY`, dan `FRONTEND_URL` saat diminta.
5. Salin URL API Render ke `BACKEND_API_URL` di Vercel.
6. Isi `FRONTEND_URL` dengan URL Vercel, misalnya
	`https://instagram-bot-app.vercel.app`.

Konfigurasi manual worker:

```text
Root Directory: backend
Build Command: pip install -r requirements.txt && playwright install chromium
Start Command: celery -A celery_app.celery_app worker --loglevel=info --pool=solo
```

Konfigurasi manual API:

```text
Root Directory: backend
Build Command: pip install -r requirements.txt && playwright install chromium
Start Command: uvicorn main:app --host 0.0.0.0 --port $PORT
Health Check Path: /health
```

Jika image Linux membutuhkan dependency browser sistem, gunakan
`playwright install --with-deps chromium`.

### Deploy worker ke Heroku

Repository sudah berisi `Procfile` dan `runtime.txt` Python 3.11.4.

```bash
heroku login
heroku create instagram-bot-worker
heroku config:set PIP_REQUIREMENTS_FILE=backend/requirements.txt
heroku config:set REDIS_URL='rediss://default:PASSWORD@YOUR-UPSTASH-ENDPOINT:6379'
heroku config:set DEEPSEEK_API_KEY='YOUR_DEEPSEEK_KEY'
git push heroku main
heroku ps:scale worker=1
heroku logs --tail --dyno worker
```

Worker akan menjalankan:

```text
worker: cd backend && celery -A celery_app.celery_app worker --loglevel=info --pool=solo
```

Gunakan Render atau Heroku untuk worker, bukan keduanya sekaligus.

### Environment variables

Buat Redis di Upstash, lalu salin connection string TLS yang biasanya berbentuk
`rediss://default:PASSWORD@HOST:6379`.

Vercel:

```env
BACKEND_API_URL=https://instagram-bot-api.onrender.com
```

Render API dan worker:

```env
REDIS_URL=rediss://default:PASSWORD@HOST:6379
DEEPSEEK_API_KEY=your_deepseek_key
CREDENTIAL_ENCRYPTION_KEY=generate_a_fernet_key
DEEPSEEK_BASE_URL=https://api.deepseek.com/v1
DEEPSEEK_MODEL=deepseek-chat
COMMENT_STATE_DIR=/tmp/comment-state
RATE_LIMIT_PER_IP_PER_DAY=10
COMMENT_CACHE_TTL_SECONDS=3600
PLAYWRIGHT_TIMEOUT_MS=10000
PLAYWRIGHT_NAVIGATION_TIMEOUT_MS=30000
CELERY_CONCURRENCY=1
LOG_LEVEL=INFO
```

Tambahkan hanya ke API service:

```env
FRONTEND_URL=https://instagram-bot-app.vercel.app
```

`NEXT_PUBLIC_API_URL` bersifat opsional dan tidak digunakan oleh proxy saat ini.

Generate `CREDENTIAL_ENCRYPTION_KEY` sekali, lalu simpan secret yang sama di API
dan worker. Key ini mengenkripsi password sebelum masuk antrean Celery. Jangan
rotate key tanpa migration karena ciphertext task lama tidak akan bisa didekripsi.

```bash
cd instagram-bot-app/backend
source .venv/bin/activate
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

### Testing production

```bash
curl --fail https://instagram-bot-api.onrender.com/health
```

Buka URL Vercel, isi form, lalu kirim job. Respons harus memiliki `task_id`.

```bash
curl https://instagram-bot-api.onrender.com/api/job-status/TASK_ID
```

Validasi berurutan:

1. Halaman Vercel tampil tanpa error.
2. `POST /api/start-job` mengembalikan `submitted`.
3. Log worker menunjukkan task diterima dan selesai.
4. Endpoint status mengembalikan `SUCCESS` dan ringkasan hasil.
5. Verifikasi postingan target secara manual setelah job selesai.

### Monitoring dan keamanan

- Vercel: **Project > Deployments > pilih deployment > Runtime Logs**.
- Render: buka service API atau worker, lalu tab **Logs**.
- Heroku: jalankan `heroku logs --tail --dyno worker`.
- Tambahkan Sentry untuk error tracking FastAPI dan worker jika DSN production
	sudah tersedia.
- Logtail dapat dipakai bila retention log bawaan tidak cukup.

Jangan log password, `DEEPSEEK_API_KEY`, atau isi request credential.

Checklist keamanan:

- Jangan expose `DEEPSEEK_API_KEY` melalui frontend atau `NEXT_PUBLIC_*`.
- Jangan menyimpan password di log, analytics, atau client-side storage.
- Password dienkripsi (Fernet) sebelum masuk antrean Celery dan hanya dipakai
	untuk login sesi tersebut di worker; tidak pernah disimpan ke disk.
- Tambahkan autentikasi pengguna dan rate limiting pada `/api/start-job`.
- Pertahankan validasi Pydantic dan batasi concurrency worker serta jumlah post.
- Rotate credential yang pernah tertulis di source code atau chat.

## Final Launch Checklist

- [ ] Jalankan smoke test `/health` dan `/docs`.
- [ ] Uji validasi input dan rate limit HTTP 422/429.
- [ ] Uji happy path dengan satu target yang diizinkan dan credential valid.
- [ ] Uji session expired, target hilang, target tanpa post, throttle, dan DeepSeek error.
- [ ] Set semua secret di Vercel, Render, atau Heroku; jangan commit `.env`.
- [ ] Periksa UI di desktop dan mobile.
- [ ] Pastikan log Vercel/API/worker bersih dari credential.
- [ ] Pastikan worker aktif dan Redis Upstash reachable.
- [ ] Verifikasi hasil komentar secara manual dan hormati rate limit Instagram.
- [ ] Baca disclaimer di halaman utama dan `/about` sebelum membuka akses publik.

## Lisensi

Proyek ini dirilis di bawah [MIT License](LICENSE). Pastikan penggunaan tetap
mematuhi Terms of Use Instagram, kebijakan DeepSeek, dan hukum setempat.

## Berbagi Proyek

Promosikan hanya setelah security review dan abuse controls aktif. Contoh pesan:

```text
Saya baru merilis Instagram Auto Comment Bot, sebuah workspace untuk membuat
dan memantau job komentar berbasis Next.js, FastAPI, Celery, Redis, dan Playwright.

Demo: https://your-app.vercel.app
Repository: https://github.com/USERNAME/REPOSITORY

Gunakan secara bertanggung jawab, patuhi kebijakan Instagram, dan jangan pernah
membagikan API key atau session cookie.
```

### 4. Menjalankan frontend

Buka terminal baru:

```bash
cd instagram-bot-app/frontend
npm run dev
```

Frontend tersedia di `http://localhost:3000`.

## Instalasi Ulang

Frontend:

```bash
cd instagram-bot-app/frontend
npm install
```

Backend:

```bash
cd instagram-bot-app/backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

## Instagram Worker Configuration

Isi `backend/.env` dengan `DEEPSEEK_API_KEY` dan `CREDENTIAL_ENCRYPTION_KEY`
sebelum menjalankan task. Worker melakukan login otomatis ke Instagram dengan
username dan password dari request, mengambil cookie `sessionid`, lalu menjalankan
bot dalam sesi tersebut. Password tidak disimpan; hanya dienkripsi saat transit
ke worker dan dipakai untuk login sekali jalan.
Jangan commit file `.env`, password, atau API key.

Task menyimpan URL posting yang sudah diproses di `.comment-state/commented_state_<username>.json`.

Contoh mengirim job:

```bash
curl -X POST http://localhost:8000/api/start-job \
	-H "Content-Type: application/json" \
	-d '{"username":"akun_login","password":"PASSWORD_AKUN","target":"akun_target","comment_count":2}'
```

Respons berisi `task_id`. Periksa hasilnya dengan:

```bash
curl http://localhost:8000/api/job-status/TASK_ID
```

## Langkah 6: E2E Testing dan Troubleshooting

### Checklist manual E2E

1. Pastikan Redis Upstash reachable, API FastAPI sehat, dan tepat satu worker aktif.
2. Buka URL Vercel dan pastikan halaman form tampil.
3. Isi username Instagram, password, username target, dan `comment_count` 1-10.
4. Klik **Kirim job**. UI harus menampilkan task ID dan status `submitted`.
5. Pastikan API mengembalikan `POST /api/start-job` dengan HTTP 200.
6. Pastikan worker log menampilkan task diterima dan state `PROCESSING`.
7. Pastikan Playwright tidak diarahkan ke halaman login.
8. Pastikan profil target dan postingan ditemukan.
9. Pastikan worker hanya mengirim komentar yang masih kurang dari target count.
10. Pastikan status berubah menjadi `SUCCESS` dan ringkasan menampilkan komentar
	terkirim serta postingan diproses.
11. Periksa satu postingan target secara manual.
12. Jalankan ulang job yang sama dan pastikan state mencegah komentar duplikat.

### Skenario uji

| ID | Kondisi | Hasil yang diharapkan |
| --- | --- | --- |
| E2E-01 | Credential valid, target memiliki post | Task `SUCCESS`, jumlah komentar sesuai kebutuhan |
| E2E-02 | Session ID expired | Task `FAILURE` dengan pesan session invalid; tidak retry tanpa batas |
| E2E-03 | Target tidak ditemukan | Task `FAILURE` dengan pesan target tidak ditemukan |
| E2E-04 | Target tidak punya post | `SUCCESS` dengan `posts_processed: 0`, tidak ada komentar |
| E2E-05 | Instagram throttle/rate limit | State `RETRY`, retry sekitar 5 menit, maksimum 3 kali |
| E2E-06 | DeepSeek 429/5xx/timeout | State `RETRY`, lalu error jelas setelah batas retry |
| E2E-07 | Backend mati | UI menampilkan error proxy/backend dan tidak membuat task palsu |
| E2E-08 | comment count 0 atau 11 | API mengembalikan HTTP 422 |

Jalankan smoke test API tanpa mengirim job nyata:

```bash
curl --fail "$BACKEND_URL/health"
curl "$BACKEND_URL/docs"
```

### Melihat log

Vercel:

```bash
npx vercel logs YOUR_VERCEL_PROJECT_URL --prod
```

Atau buka **Vercel Dashboard > Project > Deployments > Runtime Logs**.

Render: buka service API atau worker, lalu pilih tab **Logs**. Dengan Render CLI:

```bash
render logs --service instagram-bot-worker
```

Heroku:

```bash
heroku logs --tail --dyno worker --app instagram-bot-worker
```

Log worker menggunakan JSON, sehingga field `level`, `logger`, `message`, dan
`timestamp` dapat dikirim ke Logtail atau Datadog. Jangan mencatat password atau
API key.

### Debugging Celery dan Redis

Periksa worker dan task terdaftar:

```bash
celery -A celery_app.celery_app inspect ping
celery -A celery_app.celery_app inspect active
celery -A celery_app.celery_app inspect registered
```

Periksa queue Redis Upstash. Gunakan `rediss://` dan jangan menaruh URL di shell
history jika terminal dibagikan:

```bash
redis-cli -u "$REDIS_URL" PING
redis-cli -u "$REDIS_URL" LLEN celery
redis-cli -u "$REDIS_URL" LRANGE celery 0 5
```

State komentar lokal worker:

```bash
cat backend/.comment-state/commented_state_USERNAME.json
```

Pada Render filesystem worker bersifat ephemeral. Gunakan database/object storage
untuk state durable sebelum mengandalkan riwayat lintas deploy.

### Retry dan timeout

Task retryable (throttle Instagram, DeepSeek 429/5xx, atau timeout jaringan)
akan dijadwalkan ulang dengan jeda 300 detik dan maksimum tiga percobaan. Error
permanen seperti session expired atau target tidak ditemukan langsung menjadi
hasil `error`.

Konfigurasi penting:

```env
PLAYWRIGHT_TIMEOUT_MS=10000
PLAYWRIGHT_NAVIGATION_TIMEOUT_MS=30000
CELERY_CONCURRENCY=1
```

Jangan menaikkan concurrency tanpa menguji rate limit Instagram. Satu browser
per task mengonsumsi CPU/RAM besar; prefetch `1` mencegah satu worker mengambil
banyak task sebelum task sebelumnya selesai.

### Optimasi performa

- Gunakan `domcontentloaded`, bukan menunggu semua asset gambar selesai.
- Batasi `MAX_POSTS_PER_JOB` dan hindari scroll tanpa batas.
- Pertahankan satu browser/context per task dan selalu tutup browser pada `finally`.
- Cache hasil caption hanya bila tidak membuat data Instagram stale.
- Pisahkan antrean task berat dari task ringan jika volume meningkat.
- Scale worker secara bertahap, sambil memantau CPU, memory, Redis latency, dan
	response rate Instagram.

### Fitur lanjutan

- Simpan task dan hasil di database agar dashboard riwayat tidak bergantung pada
	Celery result backend.
- Tambahkan webhook/email/Telegram setelah task sukses atau gagal.
- Tambahkan autentikasi user dan rate limit, misalnya maksimal lima job per hari.
- Simpan kredensial (atau session yang valid) terenkripsi di secret manager dan
	jangan kirim ulang password ke browser setelah job dibuat.

### Masalah umum

**Status selalu `PENDING`:** pastikan `REDIS_URL` API dan worker identik, worker
aktif, dan `celery -A celery_app.celery_app inspect ping` menjawab `pong`.

**Status `RETRY`:** baca pesan JSON worker. Tunggu 300 detik untuk retry pertama;
jangan mengirim job duplikat selama retry masih terjadwal.

**Login gagal / session invalid:** periksa pesan error task (password salah,
akun tidak ditemukan, atau challenge/2FA). Password salah tidak di-retry otomatis;
challenge memerlukan tindakan manual di akun Instagram.

**Tidak ada postingan:** periksa target publik, status login, selector Instagram,
dan `MAX_POSTS_PER_JOB`. Jalankan satu target uji yang memiliki post publik.

**Browser gagal di Render:** pastikan build command menjalankan
`playwright install chromium`; gunakan `--with-deps` bila image membutuhkan
system packages.

**DeepSeek error:** periksa `DEEPSEEK_API_KEY`, `DEEPSEEK_BASE_URL`, quota, dan
status code API. Task 429/5xx/timeout akan retry; error lain menjadi fallback atau
error permanen sesuai responsnya.

### Live login assist (CAPTCHA manual)

Saat Instagram memblokir login otomatis dengan CAPTCHA/checkpoint, panel **Live
Login Assist** dapat menampilkan browser secara langsung di halaman web. Klik pada
gambar panel akan dikirim ke browser sehingga pengguna bisa menyelesaikan CAPTCHA
secara manual. Setelah login sukses, cookie `sessionid` dikirim ke `/api/start-job`
dan worker Celery menjalankan bot memakai sesi tersebut.

Alur baru pada tombol **Kirim job**:

1. Jika checkbox *tampilkan layar login manual* aktif, backend membuka browser
   login interaktif (`POST /api/live-login/start`).
2. Frame direfresh tiap ~450 ms; status dipolling tiap ~1,2 detik.
3. Setelah status `success`, job dikirim otomatis dengan `session_id`.

Kontrol tambahan: tombol **Ketik** untuk menulis teks ke elemen yang sedang
fokus (mis. jawaban challenge teks) dan tombol **Enter**.

Variabel opsional untuk pengembangan:

```env
# false = browser muncul (default, cocok lokal). true = headless (untuk CI).
LIVE_LOGIN_HEADLESS=false
```

Catatan: fitur ini berjalan di proses FastAPI dan paling cocok untuk development
lokal. Pada Render (tanpa display dan IP datacenter), menyelesaikan CAPTCHA manual
umumnya tidak berhasil; untuk production gunakan `sessionid` yang diambil dari
browser normal.