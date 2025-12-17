# Deployment Guide for Railway / Render / Heroku

## 📝 Summary of Changes Made for Production

### ✅ Changes Already Applied to `app.py`

1. **✅ Port Configuration** - Now uses `PORT` environment variable
2. **✅ Host Binding** - Changed from `127.0.0.1` to `0.0.0.0`
3. **✅ Debug Mode** - Automatically OFF in production
4. **✅ CORS** - Uses `FRONTEND_URL` environment variable
5. **✅ Environment Detection** - Uses `FLASK_ENV` variable

### ❌ NO Endpoint URL Changes Needed!

**All your endpoint URLs stay exactly the same:**

- `/img-compress`
- `/video-upscale`
- `/pdf-to-word`
- etc.

---

## 🚀 Deploy to Railway

### Step 1: Install Railway CLI (Optional)

```powershell
npm install -g @railway/cli
railway login
```

### Step 2: Create Railway Project

1. Go to [railway.app](https://railway.app/)
2. Click "New Project"
3. Select "Deploy from GitHub repo" or "Empty Project"

### Step 3: Connect Your Repository

**Option A: Via GitHub**

1. Connect your GitHub account
2. Select the repository
3. Railway will auto-detect Python app

**Option B: Via Railway CLI**

```powershell
cd "c:\Users\HARSHIL\Documents\Python LLM\upscale-fullstack\backend"
railway init
railway up
```

### Step 4: Set Environment Variables

In Railway Dashboard → Variables:

```bash
# Required Variables
PORT=5000                          # Railway sets this automatically
FLASK_ENV=production              # Enable production mode

# Optional Variables
FRONTEND_URL=https://your-frontend-domain.com    # Your Angular app URL
MAX_CONTENT_LENGTH=524288000      # 500MB in bytes
```

### Step 5: Create `Procfile` (if needed)

Railway usually auto-detects, but you can create:

**Path**: `c:\Users\HARSHIL\Documents\Python LLM\upscale-fullstack\backend\Procfile`

```
web: python app.py
```

### Step 6: Verify `requirements.txt`

Make sure all dependencies are listed in `requirements.txt`:

```
Flask>=2.3.0
flask-cors>=4.0.0
Pillow>=10.0.0
yt-dlp>=2023.0.0
moviepy>=1.0.3
PyPDF2>=3.0.0
python-docx>=0.8.11
rembg>=2.0.0
pillow-heif>=0.13.0
```

### Step 7: Deploy!

Railway will automatically:

- ✅ Detect Python
- ✅ Install from `requirements.txt`
- ✅ Run `python app.py`
- ✅ Assign a PORT
- ✅ Give you a public URL

---

## 🌐 Deploy to Render

### Step 1: Create New Web Service

1. Go to [render.com](https://render.com/)
2. Click "New +" → "Web Service"
3. Connect your repository

### Step 2: Configure Service

```yaml
Name: upscale-backend
Environment: Python 3
Branch: main
Build Command: pip install -r requirements.txt
Start Command: python app.py
```

### Step 3: Set Environment Variables

In Render Dashboard → Environment:

```bash
FLASK_ENV=production
FRONTEND_URL=https://your-frontend-domain.com
PORT=10000    # Render automatically sets this
```

### Step 4: Advanced Settings

- **Health Check Path**: `/health`
- **Auto-Deploy**: Yes
- **Instance Type**: Free or Starter

---

## 🔧 Deploy to Heroku

### Step 1: Install Heroku CLI

```powershell
# Download from heroku.com/cli
```

### Step 2: Create Heroku App

```powershell
cd "c:\Users\HARSHIL\Documents\Python LLM\upscale-fullstack\backend"
heroku login
heroku create your-app-name
```

### Step 3: Create `Procfile`

**Path**: `c:\Users\HARSHIL\Documents\Python LLM\upscale-fullstack\backend\Procfile`

```
web: python app.py
```

### Step 4: Set Environment Variables

```powershell
heroku config:set FLASK_ENV=production
heroku config:set FRONTEND_URL=https://your-frontend-domain.com
```

### Step 5: Deploy

```powershell
git add .
git commit -m "Deploy to Heroku"
git push heroku main
```

---

## 🔐 Environment Variables Reference

### Required on All Platforms

| Variable    | Default       | Production Value | Purpose          |
| ----------- | ------------- | ---------------- | ---------------- |
| `PORT`      | `5000`        | Set by platform  | Server port      |
| `FLASK_ENV` | `development` | `production`     | Environment mode |

### Optional but Recommended

| Variable             | Default     | Production Value       | Purpose                 |
| -------------------- | ----------- | ---------------------- | ----------------------- |
| `FRONTEND_URL`       | `*`         | `https://your-app.com` | CORS origin             |
| `MAX_CONTENT_LENGTH` | `524288000` | Custom                 | Max upload size (bytes) |

---

## 📱 Update Your Frontend

### Angular Environment Files

**For Development** (`src/environments/environment.ts`):

```typescript
export const environment = {
  production: false,
  apiUrl: "http://localhost:5000", // Local backend
};
```

**For Production** (`src/environments/environment.prod.ts`):

```typescript
export const environment = {
  production: true,
  apiUrl: "https://your-railway-app.railway.app", // Railway backend URL
  // Or: 'https://your-app.onrender.com'  // Render backend URL
  // Or: 'https://your-app.herokuapp.com'  // Heroku backend URL
};
```

### Update API Calls

In your Angular services:

```typescript
import { environment } from '../environments/environment';

// Example
uploadImage(file: File) {
  return this.http.post(`${environment.apiUrl}/img-compress`, formData);
}
```

---

## ✅ Testing Your Deployment

### Test Health Endpoint

```bash
# Replace with your actual deployed URL
curl https://your-app.railway.app/health
```

Expected response:

```json
{
  "status": "healthy",
  "service": "upscale-backend"
}
```

### Test API Index

```bash
curl https://your-app.railway.app/
```

Expected response:

```json
{
  "status": "ok",
  "message": "Upscale Fullstack Backend API",
  "version": "2.0",
  "endpoints": { ... }
}
```

### Test Actual Endpoint

```bash
curl -X POST https://your-app.railway.app/img-compress \
  -F "file=@test-image.jpg" \
  -F "quality=85"
```

---

## 🐛 Common Issues & Solutions

### Issue 1: "Application Error" or Won't Start

**Solution**: Check logs in platform dashboard

```powershell
# Railway
railway logs

# Heroku
heroku logs --tail
```

**Common causes**:

- Missing dependencies in `requirements.txt`
- Python version mismatch
- Port binding issue (make sure using `0.0.0.0`)

### Issue 2: CORS Errors

**Solution**: Set `FRONTEND_URL` environment variable correctly

```bash
FRONTEND_URL=https://your-angular-app.vercel.app
```

### Issue 3: 502 Bad Gateway

**Solution**:

- Check if app is actually running
- Verify `PORT` environment variable is being used
- Ensure health check endpoint works

### Issue 4: File Upload Fails

**Solution**: Some platforms have upload limits

- Railway: 100MB default
- Render: 100MB default
- Heroku: 30 seconds timeout on free tier

Consider upgrading or using smaller files for testing.

---

## 📊 Platform Comparison

| Feature       | Railway      | Render           | Heroku         |
| ------------- | ------------ | ---------------- | -------------- |
| Free Tier     | ✅ $5 credit | ✅ 750 hrs/month | ✅ Limited     |
| Auto Deploy   | ✅           | ✅               | ✅             |
| Custom Domain | ✅           | ✅               | ✅             |
| Sleep on Idle | ❌           | ✅ (free tier)   | ✅ (free tier) |
| Build Time    | Fast         | Medium           | Slow           |
| Ease of Use   | ⭐⭐⭐⭐⭐   | ⭐⭐⭐⭐         | ⭐⭐⭐         |

**Recommendation**: **Railway** for easiest deployment and best free tier.

---

## 🎯 Quick Start Checklist

- [x] ✅ `app.py` updated for production (already done!)
- [ ] Push code to GitHub repository
- [ ] Create account on Railway/Render/Heroku
- [ ] Create new project/service
- [ ] Set environment variables (`FLASK_ENV=production`, `FRONTEND_URL`)
- [ ] Deploy and get public URL
- [ ] Test `/health` endpoint
- [ ] Test actual endpoints
- [ ] Update Angular frontend with production API URL
- [ ] Deploy Angular frontend
- [ ] Test full application flow

---

## 🚀 Summary

### ✅ What Changed in Code

1. **`app.py`** - Now production-ready:
   - Uses `PORT` from environment
   - Binds to `0.0.0.0` (required for Railway/Render)
   - Auto-detects production mode
   - Uses `FRONTEND_URL` for CORS

### ❌ What DIDN'T Change

1. **Endpoint URLs** - All stay the same!
   - `/img-compress` is still `/img-compress`
   - `/video-upscale` is still `/video-upscale`
   - No need to change anything in frontend API calls

### 🎯 Next Steps

1. **Push to GitHub** (if not already)
2. **Choose platform** (Railway recommended)
3. **Deploy** (one-click or CLI)
4. **Set environment variables**
5. **Get deployed URL**
6. **Update Angular frontend** with new API URL
7. **Test everything**

**Your backend is now ready for production hosting!** 🚀
