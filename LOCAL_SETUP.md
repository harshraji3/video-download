# 🎬 Running the Complete Pipeline Locally

## Overview
You now have a **full-stack solution** that:
- **Backend (Python/FastAPI)**: Downloads videos, extracts metadata, uploads to Azure, updates CSV
- **Frontend (React)**: Communicates with the local backend instead of Azure Functions
- **CORS enabled**: Browser can communicate with localhost backend
- **CSV Updates**: Automatic indexing after each video process

---

## Prerequisites

1. **Python 3.8+** installed
2. **Node.js & npm** installed
3. **yt-dlp** system binary:
   ```powershell
   # Windows - Install via pip (comes with ffmpeg support)
   pip install yt-dlp
   ```
   OR download from: https://github.com/yt-dlp/yt-dlp/releases

4. **Azure Storage Connection String** in `.env` file:
   ```env
   AZURE_STORAGE_CONNECTION_STRING=DefaultEndpointsProtocol=https;AccountName=...
   AZURE_STORAGE_CONTAINER=media-files
   ```

---

## Step 1: Set Up Backend

### 1.1 Install Python Dependencies
```powershell
cd d:\Downloads\process_pycopy
pip install -r requirements.txt
```

### 1.2 Create `.env` file (if not exists)
```powershell
# In the root directory
echo "AZURE_STORAGE_CONNECTION_STRING=your_connection_string" > .env
echo "AZURE_STORAGE_CONTAINER=media-files" >> .env
```

### 1.3 Start the FastAPI Backend
```powershell
python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

✅ Backend is now running at `http://localhost:8000`

**Check health:**
```
curl http://localhost:8000/health
```

Expected response:
```json
{"status": "ok", "blob": "media-files"}
```

---

## Step 2: Set Up Frontend

### 2.1 Install React Dependencies
```powershell
# In a NEW terminal window
cd d:\Downloads\process_pycopy\clinsearch
npm install
```

### 2.2 Start React Dev Server
```powershell
npm start
```

✅ Frontend opens at `http://localhost:3000`

---

## Step 3: Test the Complete Pipeline

### 3.1 Via UI
1. Open browser: `http://localhost:3000`
2. Click "Process video" tab
3. Paste a YouTube URL (e.g., `https://www.youtube.com/watch?v=dQw4w9WgXcQ`)
4. Click "Process"
5. Watch the status:
   - ✅ Downloads video
   - ✅ Extracts metadata
   - ✅ Uploads to Azure Blob
   - ✅ Updates CSV index
   - ✅ Shows results with confidence score

### 3.2 Via CLI (alternative)
```powershell
python process.py "https://www.youtube.com/watch?v=..."
```

### 3.3 Check Results

**View the Video Library tab:**
- Click "Video library" tab in frontend
- See all processed videos with searchable index
- Click "Refresh" to reload from Azure

**Download CSV from Azure:**
```powershell
# List blob contents (requires Azure CLI)
az storage blob list --container-name media-files --account-name your_account_name

# Download CSV
az storage blob download --container-name media-files --name _index/video_library.csv --file video_library.csv
```

---

## What Changed

### Backend (`main.py`)
✅ **CORS Middleware Added** → Browser can now call localhost  
✅ **CSV Update Endpoint** → `/update-csv` for indexing videos  
✅ **Full Processing** → Download + metadata_only=false now works  

### Frontend (`ClinSearch.jsx`)
✅ **API URL Changed** → Points to `http://localhost:8000` instead of Azure  
✅ **Real Processing** → `metadata_only: false` downloads actual videos  
✅ **CSV Auto-Update** → Calls `/update-csv` after processing  
✅ **Error Display** → Shows helpful messages if backend is down  
✅ **Status Messages** → "Downloading video · uploading to Azure…"  

---

## Troubleshooting

### Issue: "Cannot find yt-dlp"
**Solution:** Install via pip
```powershell
pip install yt-dlp
```

### Issue: "AZURE_STORAGE_CONNECTION_STRING not set"
**Solution:** Create `.env` file with your Azure connection string
```powershell
# Get from Azure Portal → Storage Account → Access Keys
```

### Issue: "API error 500" or "Connection refused"
**Solution:** 
1. Check backend is running on port 8000:
   ```powershell
   curl http://localhost:8000/health
   ```
2. If not running, restart FastAPI:
   ```powershell
   python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
   ```

### Issue: Video download fails with "yt-dlp: command not found"
**Solution:** Ensure yt-dlp is in PATH:
```powershell
# Check if installed
python -m yt_dlp --version

# If not, install
pip install yt-dlp --upgrade
```

### Issue: Frontend shows "Make sure backend is running on http://localhost:8000"
**Solution:**
1. Start backend first (terminal 1)
2. Start frontend second (terminal 2)
3. Both must be running simultaneously
4. Check CORS: Backend should show middleware initialization

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│  React Frontend (localhost:3000)                        │
│  - Input: YouTube URL                                   │
│  - POST /process → Download & extract                   │
│  - POST /update-csv → Index video                       │
│  - GET /videos → Show library                           │
└────────────────┬────────────────────────────────────────┘
                 │ CORS enabled
                 ↓
┌─────────────────────────────────────────────────────────┐
│  FastAPI Backend (localhost:8000)                       │
│  ✅ CORS Middleware                                     │
│  ✅ /process endpoint (download + upload)               │
│  ✅ /update-csv endpoint (maintain index)               │
│  ✅ /videos endpoint (list all)                         │
│  ✅ /health endpoint (check status)                     │
└────────────────┬────────────────────────────────────────┘
                 │ Uses yt-dlp + youtube-transcript-api
                 ├─ Downloads video locally
                 ├─ Extracts transcript
                 └─ Uploads to Azure Blob Storage
                 ↓
┌─────────────────────────────────────────────────────────┐
│  Azure Blob Storage                                      │
│  📁 /metadata/{file_id}.json                            │
│  📁 /videos/{category}/{file_id}.mp4                    │
│  📁 /_index/video_library.csv                           │
│  📁 /_index/library_database.json                       │
└─────────────────────────────────────────────────────────┘
```

---

## Production Deployment

When deploying to production:

### 1. Update Frontend Config
```javascript
// In ClinSearch.jsx line 2:
// Change from:
// const FUNCTION_BASE_URL = "http://localhost:8000";
// To:
const FUNCTION_BASE_URL = "https://your-production-domain.com";
```

### 2. Restrict CORS
```python
# In main.py, change from:
# allow_origins=["*"]
# To:
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://your-frontend-domain.com"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

### 3. Use Environment Variables
```python
import os
ALLOWED_ORIGINS = os.environ.get("ALLOWED_ORIGINS", "http://localhost:3000").split(",")
```

---

## Next Steps

✅ **Test locally** with sample videos  
✅ **Verify CSV** is updating in Azure Blob  
✅ **Check logs** for any extraction issues  
✅ **Deploy backend** to Azure Functions or App Service  
✅ **Deploy frontend** to Azure Static Web Apps or Vercel  

---

## Questions?

Check the logs in both terminals for debugging:
- **Backend errors**: Terminal 1 (uvicorn)
- **Frontend errors**: Browser DevTools Console
- **Processing logs**: Check `process.py` output
