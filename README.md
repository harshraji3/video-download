# Video Processing & Library Management System

A full-stack application for downloading YouTube videos, extracting metadata, and managing an oncology video library with searchable database.

## 📋 Project Overview

This system processes oncology educational videos from YouTube, extracts clinical metadata (cancer indications, drugs, biomarkers), and maintains a searchable CSV index stored in Azure Blob Storage.

**Tech Stack:**
- **Backend:** FastAPI (Python 3.14)
- **Frontend:** React 18 (JavaScript)
- **Cloud Storage:** Azure Blob Storage
- **Video Processing:** yt-dlp, youtube-transcript-api
- **Development:** localhost (8000 for backend, 3000 for frontend)

---

## 🚀 Quick Start

### Prerequisites
- Python 3.14+
- Node.js 16+
- Azure Storage Account (with connection string)
- YouTube URLs of videos to process

### Backend Setup

1. **Navigate to backend folder:**
   ```bash
   cd backend
   ```

2. **Create `.env` file** (copy from `.env.example`):
   ```
   AZURE_STORAGE_CONNECTION_STRING=DefaultEndpointsProtocol=https;AccountName=...;AccountKey=...;EndpointSuffix=core.windows.net
   AZURE_STORAGE_CONTAINER=your-container-name
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Run FastAPI server:**
   ```bash
   python main.py
   ```
   Server runs on `http://localhost:8000`

### Frontend Setup

1. **Navigate to frontend folder:**
   ```bash
   cd frontend/clinsearch
   ```

2. **Install dependencies:**
   ```bash
   npm install
   ```

3. **Start development server:**
   ```bash
   npm start
   ```
   Frontend runs on `http://localhost:3000`

---

## 📁 Project Structure

```
.
├── backend/
│   ├── main.py                 # FastAPI server
│   ├── api.py                  # Azure Functions version (legacy)
│   ├── process.py              # Core metadata extraction logic
│   ├── requirements.txt         # Python dependencies
│   ├── .env.example             # Environment template
│   ├── function_app.py
│   └── host.json
│
├── frontend/
│   └── clinsearch/
│       ├── src/
│       │   ├── App.js           # Main React component
│       │   ├── App.css
│       │   └── index.js
│       ├── public/
│       └── package.json
│
├── oncology-video-library/     # Video storage & index
│   ├── library_database.csv    # Master video index
│   ├── descriptions/           # Video metadata JSONs
│   └── videos/                 # Organized by category
│
└── README.md
```

---

## 🎯 Features

### Backend (`/backend/main.py`)
- **Video Processing**
  - Download videos from YouTube (up to 720p)
  - Extract transcripts using youtube-transcript-api
  - Support for multi-language transcripts

- **Metadata Extraction**
  - Cancer indications (e.g., "lung cancer", "breast cancer")
  - Drug names (generic & brand names)
  - Biomarker context (e.g., "PD-L1", "EGFR mutation")
  - Speaker information
  - Confidence scoring for extracted data

- **Cloud Integration**
  - Upload videos to Azure Blob Storage
  - Store metadata as JSON files
  - Maintain searchable CSV index (_index/video_library.csv)
  - Automatic CSV updates after each video

- **REST API Endpoints**
  - `POST /process` - Process new YouTube video
  - `POST /update-csv` - Update CSV index
  - `GET /videos` - List all processed videos
  - `GET /health` - Server health check

### Frontend (`/frontend/clinsearch/src/App.js`)
- **UI Components**
  - Video URL input form
  - Real-time processing feedback
  - Video library search & filter
  - Metadata display (category, drugs, speakers, etc.)
  - CSV download option

- **Features**
  - Process videos end-to-end (download → extract → upload)
  - View extracted metadata
  - Search library by title, drug, indication
  - Automatic CSV synchronization

---

## 🔄 Processing Workflow

1. **User enters YouTube URL** in React UI
2. **Frontend sends POST** to `http://localhost:8000/process`
3. **Backend**:
   - Downloads video with yt-dlp
   - Extracts transcript
   - Runs metadata extraction (cancer indications, drugs, biomarkers)
   - Calculates confidence scores
   - Uploads video to Azure Blob
   - Saves metadata as JSON to Azure
4. **Frontend receives response** with metadata
5. **Frontend calls** `http://localhost:8000/update-csv`
6. **Backend**:
   - Reads existing CSV from Azure
   - Adds new row with 14 columns
   - Writes back to Azure (_index/video_library.csv)
7. **CSV index updates automatically** for search functionality

---

## 🛠️ Environment Variables

Create `.env` file in `/backend` folder:

```env
# Azure Storage Configuration
AZURE_STORAGE_CONNECTION_STRING=<your-connection-string>
AZURE_STORAGE_CONTAINER=<your-container-name>
```

**Get Connection String:**
1. Go to Azure Portal → Storage Account
2. Settings → Access Keys
3. Copy the full connection string
4. Container: typically named `videos` or `library`

---

## 📊 CSV Index Schema

The system maintains a master CSV with these 14 columns:

| Column | Type | Example |
|--------|------|---------|
| file_id | string | `video_12345` |
| title | string | `Treatment Planning for Metastatic Lung Cancer` |
| url | string | `https://youtube.com/watch?v=...` |
| description | string | Short description |
| category | string | `CLINICAL_DECISION` |
| cancer_indications | string | `lung cancer, non-small cell carcinoma` |
| drug_generic_names | string | `pembrolizumab, cisplatin` |
| biomarker_context | string | `PD-L1, EGFR mutation` |
| speakers | string | `Dr. Jane Smith, Dr. John Doe` |
| confidence_score | float | `0.87` |
| confidence_label | string | `HIGH` |
| duration_minutes | float | `45.5` |
| processed_date | string | `2026-06-10` |
| metadata_url | string | `https://blob.../metadata_12345.json` |

---

## 🔍 Extraction Logic

**Confidence Scoring:**
- HIGH (≥0.85): Multiple keywords found in transcript
- MEDIUM (0.50-0.84): Some keywords found, partial matches
- LOW (<0.50): Few keywords, uncertain extraction

**Supported Patterns:**
- Cancer types: "lung cancer", "metastatic breast cancer", "NSCLC"
- Drugs: "pembrolizumab", "nivolumab", "chemotherapy agents"
- Biomarkers: "PD-L1", "EGFR", "BRAF V600E"
- See `backend/process.py` for complete keyword lists

---

## 🚀 API Examples

### Process a Video
```bash
curl -X POST "http://localhost:8000/process" \
  -H "Content-Type: application/json" \
  -d "{
    \"url\": \"https://www.youtube.com/watch?v=dQw4w9WgXcQ\",
    \"metadata_only\": false
  }"
```

**Response:**
```json
{
  "file_id": "video_abc123",
  "title": "Video Title",
  "metadata": {
    "cancer_indications": ["lung cancer"],
    "drugs": ["pembrolizumab"],
    "biomarkers": ["PD-L1"],
    "speakers": ["Dr. Smith"],
    "confidence_score": 0.88,
    "confidence_label": "HIGH"
  },
  "blob_url": "https://...blob.../video_abc123.mp4",
  "metadata_url": "https://...blob.../metadata_abc123.json"
}
```

### Update CSV
```bash
curl -X POST "http://localhost:8000/update-csv" \
  -H "Content-Type: application/json" \
  -d "{
    \"file_id\": \"video_abc123\",
    \"title\": \"Video Title\",
    \"url\": \"https://youtube.com/...\",
    \"category\": \"CLINICAL_DECISION\",
    \"cancer_indications\": \"lung cancer\",
    \"drug_generic_names\": \"pembrolizumab\",
    \"biomarker_context\": \"PD-L1\",
    \"speakers\": \"Dr. Smith\",
    \"confidence_score\": 0.88,
    \"confidence_label\": \"HIGH\",
    \"duration_minutes\": 45.5,
    \"processed_date\": \"2026-06-10\",
    \"metadata_url\": \"https://...blob.../metadata_abc123.json\"
  }"
```

---

## 🧪 Testing

### Backend Health Check
```bash
curl http://localhost:8000/health
```

### List Videos
```bash
curl http://localhost:8000/videos
```

### Frontend
- Open `http://localhost:3000` in browser
- Test video processing with sample YouTube URLs
- Check Video Library tab for CSV index display

---

## 📝 Common Issues

| Issue | Solution |
|-------|----------|
| `AZURE_STORAGE_CONNECTION_STRING not found` | Create `.env` file in backend folder |
| `Cannot connect to localhost:8000` | Ensure backend is running: `python main.py` |
| `CORS error in browser` | Backend has CORS enabled, try clearing browser cache |
| `CSV not updating` | Check Azure connection & permissions, verify CSV format |
| `Video download fails` | Check YouTube URL is valid, try different URL |

---

## 🔐 Security

- ✅ `.env` file excluded from git (in `.gitignore`)
- ✅ Azure credentials never committed to repository
- ✅ Use `.env.example` as template for new setup
- ✅ CORS middleware allows all origins (development only)

**For Production:**
- Restrict CORS origins
- Use managed identities instead of connection strings
- Enable video encryption
- Add authentication/authorization layer

---

## 📚 Dependencies

**Backend:**
```
fastapi
uvicorn
yt-dlp
youtube-transcript-api
azure-storage-blob
pydantic
python-multipart
```

**Frontend:**
```
react@18
react-dom@18
```

See `backend/requirements.txt` and `frontend/clinsearch/package.json` for full lists.

---

## 🤝 Contributing

1. Create a feature branch: `git checkout -b feature/new-feature`
2. Make changes and test locally
3. Commit with clear messages: `git commit -m "Add feature X"`
4. Push: `git push origin feature/new-feature`
5. Create Pull Request

---

## 📄 License

Internal project - i3 Digital Health

---

## 📞 Support

For issues or questions:
- Check this README first
- Review backend logs: `main.py` output
- Check browser console: F12 in frontend
- Contact senior developer

---

**Last Updated:** June 10, 2026  
**Version:** 1.0.0
