from dotenv import load_dotenv
load_dotenv()

import sys, os, json, re, subprocess, csv
from pathlib import Path
from datetime import datetime

NA = "N/A"


# =============================================================================
# FOLDER MAP
# =============================================================================

FOLDER_MAP = {
    "Tumor Board / MDT Cases":            "CLINICAL_DECISION/Tumor_Board_MDT",
    "Treatment Planning":                 "CLINICAL_DECISION/Treatment_Planning",
    "Clinical Trial Results":             "CLINICAL_DECISION/Clinical_Trial_Results",
    "Precision Oncology / Biomarkers":    "PRECISION_MEDICINE/Precision_Oncology",
    "Diagnostic and Staging":            "PRECISION_MEDICINE/Diagnostic_Staging",
    "Patient Counseling / Communication": "PATIENT_CARE/Patient_Counseling",
    "Adverse Event Management":           "PATIENT_CARE/Adverse_Event_Management",
    "Survivorship and Palliative Care":   "PATIENT_CARE/Survivorship_Palliative",
    "Conference Updates / FDA Approvals": "KNOWLEDGE_UPDATES/Conference_Updates_FDA",
    "Regulatory / Guidelines":           "KNOWLEDGE_UPDATES/Regulatory_Guidelines",
    "Uncategorized":                      "_Uncategorized",
}

# =============================================================================
# RULE-BASED DICTIONARIES
# =============================================================================

DRUG_DICT = {
    "keytruda":   "pembrolizumab",       "opdivo":     "nivolumab",
    "yervoy":     "ipilimumab",          "tecentriq":  "atezolizumab",
    "imfinzi":    "durvalumab",          "bavencio":   "avelumab",
    "libtayo":    "cemiplimab",          "jemperli":   "dostarlimab",
    "tagrisso":   "osimertinib",         "iressa":     "gefitinib",
    "tarceva":    "erlotinib",           "gilotrif":   "afatinib",
    "vizimpro":   "dacomitinib",
    "lumakras":   "sotorasib",           "krazati":    "adagrasib",
    "herceptin":  "trastuzumab",         "enhertu":    "trastuzumab deruxtecan",
    "kadcyla":    "T-DM1",               "perjeta":    "pertuzumab",
    "tykerb":     "lapatinib",           "nerlynx":    "neratinib",
    "tukysa":     "tucatinib",
    "ibrance":    "palbociclib",         "kisqali":    "ribociclib",
    "verzenio":   "abemaciclib",
    "lynparza":   "olaparib",            "rubraca":    "rucaparib",
    "zejula":     "niraparib",           "talzenna":   "talazoparib",
    "avastin":    "bevacizumab",         "cyramza":    "ramucirumab",
    "cabometyx":  "cabozantinib",        "nexavar":    "sorafenib",
    "sutent":     "sunitinib",           "votrient":   "pazopanib",
    "inlyta":     "axitinib",            "lenvima":    "lenvatinib",
    "welireg":    "belzutifan",
    "revlimid":   "lenalidomide",        "velcade":    "bortezomib",
    "kyprolis":   "carfilzomib",         "ninlaro":    "ixazomib",
    "darzalex":   "daratumumab",         "sarclisa":   "isatuximab",
    "pomalyst":   "pomalidomide",
    "rituxan":    "rituximab",           "gazyva":     "obinutuzumab",
    "imbruvica":  "ibrutinib",           "calquence":  "acalabrutinib",
    "brukinsa":   "zanubrutinib",        "venclexta":  "venetoclax",
    "kymriah":    "tisagenlecleucel",    "yescarta":   "axicabtagene ciloleucel",
    "tecartus":   "brexucabtagene autoleucel",
    "abecma":     "idecabtagene vicleucel",
    "carvykti":   "ciltacabtagene autoleucel",
    "taxol":      "paclitaxel",          "abraxane":   "nab-paclitaxel",
    "taxotere":   "docetaxel",           "xeloda":     "capecitabine",
    "gemzar":     "gemcitabine",         "platinol":   "cisplatin",
    "paraplatin": "carboplatin",         "eloxatin":   "oxaliplatin",
    "gleevec":    "imatinib",            "sprycel":    "dasatinib",
    "tasigna":    "nilotinib",           "bosulif":    "bosutinib",
    "iclusig":    "ponatinib",
    "zelboraf":   "vemurafenib",         "tafinlar":   "dabrafenib",
    "cotellic":   "cobimetinib",         "mekinist":   "trametinib",
    "braftovi":   "encorafenib",         "mektovi":    "binimetinib",
    "xtandi":     "enzalutamide",        "zytiga":     "abiraterone",
    "erleada":    "apalutamide",         "nubeqa":     "darolutamide",
    "vitrakvi":   "larotrectinib",       "rozlytrek":  "entrectinib",
    "retevmo":    "selpercatinib",       "gavreto":    "pralsetinib",
    "tepmetko":   "tepotinib",           "tabrecta":   "capmatinib",
    "rybrevant":  "amivantamab",         "exkivity":   "mobocertinib",
}

CANCER_KW = {
    "nsclc": "NSCLC",                    "non-small cell lung": "NSCLC",
    "lung adenocarcinoma": "NSCLC",      "lung squamous": "NSCLC",
    "lung cancer": "NSCLC",
    "small cell lung": "SCLC",           "sclc": "SCLC",
    "breast cancer": "Breast cancer",    "breast carcinoma": "Breast cancer",
    "tnbc": "TNBC",                      "triple negative": "TNBC",
    "her2-positive breast": "HER2+ breast",
    "colorectal cancer": "Colorectal cancer", "crc": "Colorectal cancer",
    "colon cancer": "Colorectal cancer", "rectal cancer": "Colorectal cancer",
    "gastric cancer": "Gastric cancer",  "stomach cancer": "Gastric cancer",
    "gastroesophageal": "Gastric cancer",
    "hepatocellular": "HCC",             "hcc": "HCC", "liver cancer": "HCC",
    "pancreatic cancer": "Pancreatic cancer", "pdac": "Pancreatic cancer",
    "cholangiocarcinoma": "Biliary cancer",
    "ovarian cancer": "Ovarian cancer",  "ovarian carcinoma": "Ovarian cancer",
    "endometrial cancer": "Endometrial cancer",
    "cervical cancer": "Cervical cancer",
    "prostate cancer": "Prostate cancer", "mcrpc": "mCRPC", "crpc": "mCRPC",
    "bladder cancer": "Bladder cancer",  "urothelial": "Urothelial cancer",
    "renal cell": "RCC",                 "rcc": "RCC", "kidney cancer": "RCC",
    "melanoma": "Melanoma",              "glioblastoma": "GBM", "gbm": "GBM",
    "mesothelioma": "Mesothelioma",      "thyroid cancer": "Thyroid cancer",
    "acute myeloid": "AML",              "aml": "AML",
    "chronic lymphocytic": "CLL",        "cll": "CLL",
    "chronic myeloid": "CML",            "cml": "CML",
    "myelodysplastic": "MDS",            "mds": "MDS",
    "multiple myeloma": "Multiple myeloma", "myeloma": "Multiple myeloma",
    "dlbcl": "DLBCL",                    "diffuse large b": "DLBCL",
    "hodgkin": "Hodgkin lymphoma",       "follicular lymphoma": "Follicular lymphoma",
    "mantle cell": "Mantle cell lymphoma",
    "head and neck": "Head and neck cancer", "hnscc": "HNSCC",
    "esophageal": "Esophageal cancer",   "sarcoma": "Sarcoma",
    "gist": "GIST",                      "neuroendocrine": "Neuroendocrine tumor",
}

BIOMARKER_KW = {
    "egfr exon 19": "EGFR exon 19 deletion", "egfr exon 21": "EGFR L858R",
    "egfr mutation": "EGFR mutation",    "egfr-mutant": "EGFR mutation",
    "egfr": "EGFR",
    "pd-l1 tps": "PD-L1 TPS",           "pd-l1": "PD-L1",
    "tmb-high": "TMB-H",                 "tmb high": "TMB-H",
    "msi-h": "MSI-H",                    "microsatellite instability": "MSI-H",
    "her2 3+": "HER2 3+",               "her2-positive": "HER2-positive", "her2": "HER2",
    "alk-positive": "ALK rearrangement", "alk": "ALK",
    "ros1": "ROS1 fusion",               "kras g12c": "KRAS G12C", "kras": "KRAS",
    "braf v600e": "BRAF V600E",          "braf": "BRAF",
    "ntrk fusion": "NTRK fusion",        "ntrk": "NTRK",
    "ret fusion": "RET fusion",          "ret": "RET",
    "met exon 14": "MET exon 14 skipping",
    "brca1": "BRCA1", "brca2": "BRCA2", "brca": "BRCA1/2",
    "hrd": "HRD",     "fgfr": "FGFR",   "pten": "PTEN loss",
    "cd19": "CD19",   "bcma": "BCMA",   "cd38": "CD38",
}

MODALITY_KW = {
    "immunotherapy": "Immunotherapy",    "checkpoint inhibitor": "Immunotherapy",
    "targeted therapy": "Targeted therapy",
    "tyrosine kinase inhibitor": "Targeted therapy",
    "chemotherapy": "Chemotherapy",      "car-t": "CAR-T therapy",
    "bispecific antibody": "Bispecific antibody",
    "antibody-drug conjugate": "ADC",
    "radiation therapy": "Radiation",    "radiotherapy": "Radiation",
    "stereotactic": "Stereotactic radiation",
    "surgery": "Surgery",                "surgical resection": "Surgery",
    "stem cell transplant": "Stem cell transplant",
    "parp inhibitor": "PARP inhibitor",  "cdk4/6 inhibitor": "CDK4/6 inhibitor",
}

ENDPOINT_KW = [
    "overall survival", "progression-free survival", "pfs",
    "objective response rate", "orr", "complete response",
    "disease-free survival", "dfs", "pathologic complete response",
    "minimal residual disease", "mrd", "hazard ratio",
]

NCT_PATTERN   = re.compile(r'NCT\d{8}', re.IGNORECASE)
TRIAL_PATTERN = re.compile(
    r'\b(KEYNOTE|CheckMate|IMpower|MONARCH|DESTINY|ADAURA|CROWN|FLAURA|ALEX'
    r'|POLO|PAOLA|PROfound|ARIEL|SOLO|TOPAZ|HIMALAYA|EMERALD|MONALEESA'
    r'|BOLERO|SOLAR|PALOMA|AURORA|ASPIRE|CANDOR|MAIA|POLLUX|CASTOR|GRIFFIN'
    r'|KarMMa|CARTITUDE|MURANO|CLL14|ASCEND|ELEVATE|SEQUOIA|ALPINE'
    r'|MAGNOLIA|SYMPATICO|NATALEE|monarchE|EMBER|INAVO|TROPiCS'
    r'|LAURA|PACIFIC|MARIPOSA|PAPILLON|POSEIDON|RELATIVITY|BREAK'
    r'|CLEOPATRA|APHINITY|KATHERINE|OlympiAD|OlympiA|TALAPRO)-?\w*\b',
    re.IGNORECASE
)

ONCOLOGY_KW = [
    "tumor board", "case", "expert", "panel", "roundtable", "Q&A",
    "treatment", "therapy", "clinical", "precision", "immunotherapy",
    "chemotherapy", "targeted", "trial", "grand rounds", "symposium",
    "practice", "management", "efficacy", "biomarker", "webinar",
]


# =============================================================================
# TRANSCRIPT SETUP
# =============================================================================

YT_TRANSCRIPT_OK = False
try:
    from youtube_transcript_api import YouTubeTranscriptApi as _YTApi
    YT_TRANSCRIPT_OK = True
except ImportError:
    print("ℹ️  youtube-transcript-api not installed  →  pip install youtube-transcript-api")


# =============================================================================
# BLOB STORAGE SETUP
# =============================================================================

BLOB_OK = False
BLOB_CONTAINER = None
try:
    from azure.storage.blob import BlobServiceClient
    from azure.core.exceptions import ResourceExistsError
    _conn_str = os.environ.get("AZURE_STORAGE_CONNECTION_STRING", "")
    if _conn_str:
        _client = BlobServiceClient.from_connection_string(_conn_str)
        _container = os.environ.get("AZURE_STORAGE_CONTAINER", "media-files")
        BLOB_CONTAINER = _client.get_container_client(_container)
        try:
            BLOB_CONTAINER.create_container()
        except ResourceExistsError:
            pass
        BLOB_OK = True
    else:
        print("ℹ️  AZURE_STORAGE_CONNECTION_STRING not set  →  videos stored locally")
except ImportError:
    print("ℹ️  azure-storage-blob not installed  →  pip install azure-storage-blob")


# =============================================================================
# CATEGORY GUIDE (for folder mapping and rule-based classification)
# =============================================================================

CATEGORY_GUIDE = """CONTENT CATEGORIES — pick exactly one:
  "Tumor Board / MDT Cases"            → Real patient cases, MDT meetings, grand rounds with case presentations
  "Treatment Planning"                 → Treatment decision-making, algorithms, first/second/third line selection
  "Clinical Trial Results"             → Phase 2/3 trial data, survival curves, hazard ratios, named trials
  "Precision Oncology / Biomarkers"    → NGS, genomic profiling, biomarker testing, molecular therapy selection
  "Diagnostic and Staging"             → Imaging workup, biopsy, pathology, staging systems
  "Patient Counseling / Communication" → Shared decision making, communicating with patients, informed consent
  "Adverse Event Management"           → Managing toxicities, immune-related AEs, dose modifications
  "Survivorship and Palliative Care"   → Quality of life, survivorship programmes, palliative/supportive care
  "Conference Updates / FDA Approvals" → ASCO/ESMO/ASH highlights, FDA approval announcements
  "Regulatory / Guidelines"            → NCCN/ESMO guideline reviews, standard of care updates
  "Uncategorized"                      → Use ONLY if none of the above clearly fits"""


# =============================================================================
# RULE-BASED EXTRACTION — always runs
# =============================================================================

def _match(text, kw_dict):
    found = []
    for kw, val in kw_dict.items():
        if kw in text and val not in found:
            found.append(val)
    return found


def rule_extract(title, description, transcript=""):
    text     = (title + " " + description + " " + transcript).lower()
    text_raw = title + " " + description + " " + transcript

    cancers    = _match(text, CANCER_KW)
    biomarkers = _match(text, BIOMARKER_KW)
    modalities = _match(text, MODALITY_KW)
    ncts       = list(set(NCT_PATTERN.findall(text_raw)))
    trials     = list(set(TRIAL_PATTERN.findall(text_raw)))

    brands, generics = [], []
    for brand, generic in DRUG_DICT.items():
        if brand in text:
            b = brand.title()
            if b not in brands:         brands.append(b)
            if generic not in generics: generics.append(generic)

    endpoints = []
    for ep in ENDPOINT_KW:
        if ep in text:
            label = ep.upper() if len(ep) <= 4 else ep.title()
            if label not in endpoints: endpoints.append(label)

    cat = "Uncategorized"
    if any(k in text for k in ["tumor board", "mdt", "multidisciplinary", "grand round"]):
        cat = "Tumor Board / MDT Cases"
    elif any(k in text for k in ["precision oncology", "genomic profiling", "biomarker-driven", "ngs panel"]):
        cat = "Precision Oncology / Biomarkers"
    elif any(k in text for k in ["phase 3", "phase iii", "randomized trial", "rct", "survival data"]):
        cat = "Clinical Trial Results"
    elif any(k in text for k in ["asco 20", "esmo 20", "ash 20", "fda approv"]):
        cat = "Conference Updates / FDA Approvals"
    elif any(k in text for k in ["adverse event", "immune-related", "toxicity management"]):
        cat = "Adverse Event Management"
    elif any(k in text for k in ["palliative", "survivorship", "quality of life", "hospice"]):
        cat = "Survivorship and Palliative Care"
    elif any(k in text for k in ["patient communication", "shared decision", "counseling"]):
        cat = "Patient Counseling / Communication"
    elif any(k in text for k in ["staging", "diagnostic workup", "biopsy"]):
        cat = "Diagnostic and Staging"
    elif any(k in text for k in ["nccn guideline", "esmo guideline", "regulatory"]):
        cat = "Regulatory / Guidelines"
    elif any(k in text for k in ["first-line", "treatment approach", "management of"]):
        cat = "Treatment Planning"
    elif trials or ncts:
        cat = "Clinical Trial Results"

    return {
        "cancer_indications":  cancers,    "disease_subtypes":   [],
        "treatment_modality":  modalities, "drug_brand_names":   brands,
        "drug_generic_names":  generics,   "drug_classes":       [],
        "drug_combinations":   [],         "speakers":           [],
        "trial_names":         trials,     "nct_numbers":        ncts,
        "trial_phase":         NA,         "key_endpoints":      endpoints,
        "biomarker_context":   biomarkers, "content_format":     cat,
    }


# =============================================================================
# SUMMARY FROM FIELDS
# Builds a readable summary from extracted clinical fields.
# Never returns N/A — always produces something useful.
# =============================================================================

def summary_from_fields(g, title, uploader):
    """Build a 2-sentence summary from extracted fields. Zero API cost."""
    cancer   = join_list(g.get("cancer_indications", []))
    drugs    = join_list(g.get("drug_brand_names",   []) or g.get("drug_generic_names", []))
    trials   = join_list(g.get("trial_names",        []))
    speakers = g.get("speakers", [])
    category = g.get("content_format", "Uncategorized")

    who   = speakers[0]["name"] if speakers else uploader
    topic = cancer if cancer != NA else title[:70]

    s1 = f"{who} discusses {topic} in this clinical education session."

    if drugs != NA and trials != NA:
        s2 = f"Key content covers {drugs}, with reference to data from {trials}."
    elif drugs != NA:
        s2 = f"Key content covers treatment with {drugs} and related clinical considerations."
    elif trials != NA:
        s2 = f"Data from {trials} is reviewed, covering efficacy and safety outcomes."
    elif category != "Uncategorized":
        s2 = f"The session focuses on {category.lower()} considerations for practicing oncologists."
    else:
        s2 = "Clinical management approaches and treatment decision-making are discussed."

    return f"{s1} {s2}"


# =============================================================================
# MAIN EXTRACTION
# =============================================================================

def extract_all(title, description, transcript=""):
    g = rule_extract(title, description, transcript)
    g["video_summary"]   = summary_from_fields(g, title, "oncology expert")
    g["_summary_source"] = "template"
    g["_engine"]         = "rule-based"
    return g


# =============================================================================
# CONFIDENCE SCORE
# =============================================================================

def confidence_score(g):
    score = 0.0
    if g.get("cancer_indications"):                                     score += 0.25
    if g.get("content_format", "Uncategorized") != "Uncategorized":     score += 0.15
    if g.get("drug_brand_names") or g.get("drug_generic_names"):        score += 0.15
    if g.get("biomarker_context"):                                       score += 0.10
    if g.get("treatment_modality"):                                      score += 0.10
    if g.get("trial_names") or g.get("nct_numbers"):                    score += 0.10
    if g.get("speakers"):                                                score += 0.10
    if g.get("key_endpoints"):                                           score += 0.05
    return round(score, 2)

def confidence_label(s):
    if s >= 0.70: return "✅ good"
    if s >= 0.50: return "⚠️  marginal"
    if s >= 0.30: return "⚠️  review"
    return "❌ poor"


# =============================================================================
# HELPERS
# =============================================================================

ROOT   = Path("oncology-video-library")
VIDEOS = ROOT / "videos"
DESCS  = ROOT / "descriptions"
DB     = ROOT / "library_database.csv"

MAX_WARN_MIN  = 180
MAX_AUDIO_MIN = 240
MAX_SKIP_MB   = 4000


def join_list(lst):
    return " | ".join(str(x) for x in lst) if lst else NA

def get_transcript(video_id, max_chars=4000):
    if not YT_TRANSCRIPT_OK: return ""
    try:
        data = _YTApi.get_transcript(video_id, languages=["en", "en-US", "en-GB"])
        return " ".join(t["text"] for t in data)[:max_chars]
    except Exception:
        return ""

def make_file_id(uploader, video_id, title=""):
    SKIP = {
        "a","an","the","in","on","at","to","of","for","and","or","but",
        "with","from","by","as","is","are","was","were","be","been",
        "how","what","why","when","where","this","that","we","our",
    }
    chan = re.sub(r'^@', '', uploader)
    chan = re.sub(r'[^a-zA-Z0-9]', '_', chan)
    chan = re.sub(r'_+', '_', chan).strip('_')[:20]
    if title:
        words = re.sub(r'[^a-zA-Z0-9\s]', '', title).split()
        words = [w for w in words if w.lower() not in SKIP and len(w) > 1]
        slug  = '_'.join(words[:4])[:35]
    else:
        slug = ""
    return f"{chan}_{slug}_{video_id}" if slug else f"{chan}_{video_id}"

def est_mb(dur_s):
    return (dur_s / 60) * 4.5 if dur_s else 0

def upload_to_blob(local_path, blob_name):
    if not BLOB_OK:
        return None
    try:
        blob_client = BLOB_CONTAINER.get_blob_client(blob_name)
        with open(local_path, "rb") as data:
            blob_client.upload_blob(data, overwrite=True)
        return blob_client.url
    except Exception as e:
        print(f"   ⚠️  Blob upload failed: {e}")
        return None


# =============================================================================
# SETUP
# =============================================================================

def setup():
    ROOT.mkdir(exist_ok=True)
    DESCS.mkdir(exist_ok=True)
    for sub in FOLDER_MAP.values():
        (VIDEOS / sub).mkdir(parents=True, exist_ok=True)

    if not DB.exists():
        with open(DB, "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow([
                "file_id", "video_id",
                "source_platform", "publication_date", "duration_min", "video_language",
                "video_summary",
                "cancer_indications", "disease_subtypes",
                "treatment_modality", "drug_brand_names", "drug_generic_names",
                "drug_classes", "drug_combinations",
                "speaker_names", "speaker_affiliations",
                "trial_names", "nct_numbers", "trial_phase",
                "key_endpoints", "biomarker_context", "content_format",
                "title", "url",
                "video_file", "description_file", "added_date",
                "extraction_engine", "summary_source", "confidence_score",
            ])

    print(f"\n📁 Library: {ROOT.absolute()}")
    print(f"📝 Transcript: {'ready' if YT_TRANSCRIPT_OK else 'not installed'}")
    print(f"☁️  Blob: {'connected' if BLOB_OK else 'local only'}")
    print()


# =============================================================================
# PLAYLIST
# =============================================================================

def is_playlist(url):
    return "playlist?list=" in url or ("/@" in url and "/videos" in url)

def get_playlist_videos(url, limit=None):
    print("📋 Reading playlist...")
    cmd = ["yt-dlp", "--flat-playlist", "--print", "%(url)s\t%(title)s", "--no-warnings"]
    if limit: cmd += ["--playlist-end", str(limit)]
    cmd.append(url)
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    videos, skipped = [], 0
    for line in r.stdout.strip().split("\n"):
        if "\t" not in line: continue
        vu, title = line.split("\t", 1)
        if sum(1 for kw in ONCOLOGY_KW if kw in title.lower()) >= 2:
            videos.append({"url": vu.strip(), "title": title.strip()})
        else:
            skipped += 1
    print(f"   ✅ {len(videos)} passed filter  |  ⏭️  {skipped} skipped")
    return videos

def resolve_urls(raw_urls, limit=None):
    out = []
    for url in raw_urls:
        url = url.strip()
        if not url: continue
        if is_playlist(url): out.extend(get_playlist_videos(url, limit))
        else: out.append({"url": url, "title": ""})
    return out


# =============================================================================
# METADATA + DOWNLOAD
# =============================================================================

def get_meta(url):
    try:
        r = subprocess.run(
            ["yt-dlp", "--dump-json", "--no-warnings", url],
            capture_output=True, text=True, timeout=90,
        )
        if r.returncode != 0:
            print(f"   ❌ {r.stderr.strip()[:160]}")
            return None
        return json.loads(r.stdout)
    except Exception as e:
        print(f"   ❌ {e}")
        return None

def download_video(url, file_id, category, audio_only=False):
    sub     = FOLDER_MAP.get(category, "_Uncategorized")
    out_dir = VIDEOS / sub
    out_dir.mkdir(parents=True, exist_ok=True)
    template = str(out_dir / f"{file_id}.%(ext)s")
    if audio_only:
        cmd = ["yt-dlp", "-x", "--audio-format", "mp3",
               "-o", template, "--no-warnings", "--no-playlist", url]
        print("   📻 Audio only...")
    else:
        cmd = ["yt-dlp", "-f", "best[height<=720]/best",
               "-o", template, "--no-warnings", "--no-playlist",
               "--merge-output-format", "mp4", url]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
        if r.returncode == 0:
            for f in out_dir.glob(f"{file_id}*"):
                if f.suffix not in {".part", ".ytdl"}:
                    return str(f.relative_to(ROOT))
        else:
            print(f"   ⚠️  {r.stderr.strip()[:100]}")
    except subprocess.TimeoutExpired:
        print("   ⚠️  Timeout")
    except Exception as e:
        print(f"   ⚠️  {e}")
    return None


# =============================================================================
# PROCESS ONE VIDEO
# =============================================================================

def process(url, skip_download=False):
    print(f"\n{'─' * 65}")
    print(f"🔗 {url}")
    print(f"{'─' * 65}")

    print("📋 Fetching metadata...")
    meta = get_meta(url)
    if not meta:
        print("   ❌ Could not fetch metadata — skipping")
        return False

    video_id     = str(meta.get("id", f"unk_{int(datetime.now().timestamp())}"))
    title        = meta.get("title", "Untitled")
    description  = meta.get("description", "") or ""
    uploader     = meta.get("uploader", meta.get("channel", "Unknown"))
    upload_date  = meta.get("upload_date", NA)
    duration_s   = meta.get("duration") or 0
    duration_min = round(duration_s / 60, 1)
    language     = (
        meta.get("language") or
        (meta.get("subtitles", {}) and list(meta["subtitles"].keys())[0]) or NA
    )
    mb_est  = est_mb(duration_s)
    file_id = make_file_id(uploader, video_id, title)

    print(f"   Title:   {title[:75]}")
    print(f"   Channel: {uploader}  |  File ID: {file_id}")
    print(f"   Duration:{duration_min} min  |  Language: {language}")

    transcript = ""
    if YT_TRANSCRIPT_OK and ("youtube.com" in url or "youtu.be" in url):
        transcript = get_transcript(video_id)
        if transcript:
            print(f"   📝 Transcript: {len(transcript):,} chars")

    g = extract_all(title, description, transcript)

    summary        = g.get("video_summary", NA)
    summary_source = g.get("_summary_source", "template")
    category       = g.get("content_format", "Uncategorized")
    engine         = g.get("_engine", "rule-based")
    score          = confidence_score(g)
    label          = confidence_label(score)
    speakers       = g.get("speakers", [])
    spkr_names     = join_list([s.get("name", "")       for s in speakers if s.get("name")])
    spkr_affs      = join_list([s.get("affiliation", "") for s in speakers if s.get("affiliation")])

    bar = "█" * int(score * 10) + "░" * (10 - int(score * 10))
    print(f"\n   {label}  [{bar}]  {int(score * 100)}%  ({engine})")
    print(f"   Summary: {summary[:110]}")
    print(f"   Folder:  {FOLDER_MAP.get(category, '_Uncategorized')}")
    print(f"   Cancer:  {join_list(g.get('cancer_indications', []))}")
    print(f"   Drugs:   {join_list(g.get('drug_brand_names', []))}")
    print(f"   Trial:   {join_list(g.get('trial_names', []))}")
    print(f"   Speakers:{spkr_names}")

    # Save JSON
    desc_file = DESCS / f"{file_id}.json"
    with open(desc_file, "w", encoding="utf-8") as f:
        json.dump({
            "file_id":          file_id,
            "video_id":         video_id,
            "source_platform":  uploader,
            "publication_date": upload_date,
            "duration_minutes": duration_min,
            "video_language":   language,
            "video_summary":       summary,
            "cancer_indications":  g.get("cancer_indications",  []) or [NA],
            "disease_subtypes":    g.get("disease_subtypes",    []) or [NA],
            "treatment_modality":  g.get("treatment_modality",  []) or [NA],
            "drug_brand_names":    g.get("drug_brand_names",    []) or [NA],
            "drug_generic_names":  g.get("drug_generic_names",  []) or [NA],
            "drug_classes":        g.get("drug_classes",        []) or [NA],
            "drug_combinations":   g.get("drug_combinations",   []) or [NA],
            "speakers":            speakers or [{"name": NA, "affiliation": NA}],
            "trial_names":         g.get("trial_names",         []) or [NA],
            "nct_numbers":         g.get("nct_numbers",         []) or [NA],
            "trial_phase":         g.get("trial_phase",  NA) or NA,
            "key_endpoints":       g.get("key_endpoints",       []) or [NA],
            "biomarker_context":   g.get("biomarker_context",   []) or [NA],
            "content_format":      category,
            "title":               title,
            "url":                 url,
            "extraction_engine":   engine,
            "summary_source":      summary_source,
            "confidence_score":    score,
            "processed_date":      datetime.now().isoformat(timespec="seconds"),
        }, f, indent=2, ensure_ascii=False)
    print(f"\n💾 JSON → descriptions/{file_id}.json")
    json_blob_url = upload_to_blob(str(desc_file), f"descriptions/{file_id}.json")
    if json_blob_url:
        print(f"   📎 JSON → blob: {json_blob_url}")

    # Download
    video_file = NA
    if not skip_download:
        if mb_est > MAX_SKIP_MB:
            print(f"\n⛔ Estimated {mb_est:.0f} MB > {MAX_SKIP_MB} MB limit — skipping")
            video_file = "[skipped — too large]"
        elif duration_min > MAX_AUDIO_MIN or mb_est > 2000:
            video_file = download_video(url, file_id, category, audio_only=True) or "[failed]"
        else:
            msg = f"Long video ({duration_min} min) — " if duration_min > MAX_WARN_MIN else ""
            print(f"\n⬇️  {msg}Downloading (720p max)...")
            video_file = download_video(url, file_id, category) or "[failed]"
        if video_file and not video_file.startswith("["):
            local_path = ROOT / video_file
            blob_name = f"{video_file}"
            blob_url = upload_to_blob(str(local_path), blob_name)
            if blob_url:
                video_file = blob_url
                local_path.unlink(missing_ok=True)
                print(f"   ✅ Video → blob: {blob_url}")
            else:
                print(f"   ✅ Video → {video_file}")
    else:
        video_file = "[metadata only]"

    # CSV row
    with open(DB, "a", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow([
            file_id, video_id,
            uploader, upload_date, duration_min, language,
            summary,
            join_list(g.get("cancer_indications",  [])),
            join_list(g.get("disease_subtypes",    [])),
            join_list(g.get("treatment_modality",  [])),
            join_list(g.get("drug_brand_names",    [])),
            join_list(g.get("drug_generic_names",  [])),
            join_list(g.get("drug_classes",        [])),
            join_list(g.get("drug_combinations",   [])),
            spkr_names, spkr_affs,
            join_list(g.get("trial_names",         [])),
            join_list(g.get("nct_numbers",         [])),
            g.get("trial_phase", NA) or NA,
            join_list(g.get("key_endpoints",       [])),
            join_list(g.get("biomarker_context",   [])),
            category, title, url,
            video_file, desc_file.name,
            datetime.now().isoformat(timespec="seconds"),
            engine, summary_source, score,
        ])
    print(f"📊 CSV → library_database.csv")

    # Upload CSV to blob storage
    if BLOB_OK:
        csv_blob_url = upload_to_blob(str(DB), "_index/video_library.csv")
        if csv_blob_url:
            print(f"   📎 CSV → blob: {csv_blob_url}")

    print(f"\n✅ Done: {title[:60]}")
    return True


# =============================================================================
# CLI
# =============================================================================

def main():
    args  = sys.argv[1:]
    skip  = "--no-video" in args
    limit = None
    if "--limit" in args:
        i = args.index("--limit")
        try:
            limit = int(args[i + 1])
            args  = [a for a in args if a != "--limit" and a != str(limit)]
        except (IndexError, ValueError):
            pass
    urls = [a for a in args if a.startswith("http")]
    if not urls:
        print("Usage:")
        print("  python process.py <URL>")
        print("  python process.py --limit 3 <PLAYLIST_URL>")
        print("  python process.py --no-video <URL>")
        print("\nEnv:")
        print("  AZURE_STORAGE_CONNECTION_STRING  (for blob upload)")
        print("  AZURE_STORAGE_CONTAINER          (default: yt-media-files)")
        return
    setup()
    videos = resolve_urls(urls, limit)
    if not videos:
        print("❌ No videos found.")
        return
    print(f"🚀 Processing {len(videos)} video(s)\n")
    ok = sum(process(v["url"], skip) for v in videos)
    print(f"\n{'=' * 65}")
    print(f"🎉 Done: {ok} / {len(videos)} processed")
    print(f"📁 Library: {ROOT.absolute()}")
    print(f"{'=' * 65}")

if __name__ == "__main__":
    main()
