import services

_META_KEYS = [
    "summary", "topics", "keywords", "speaker_count", "speaker_names",
    "drug_names", "cancer_types", "biomarkers", "company_name",
]


def transcribe_audio(data: bytes, filename: str) -> dict:
    audio_url, permanent_url, container, blob_name, conn_str = services.upload_bytes_to_blob(data, filename)
    _, op_url = services.start_analysis(
        audio_url,
        services._get_env("AZURE_CONTENT_UNDERSTANDING_ANALYZER_ID_AUDIO"),
    )
    result = services.wait_for_analysis(op_url)
    parsed = _parse_result(result)
    parsed["blob_url"] = audio_url
    services.set_blob_metadata(conn_str, container, blob_name, parsed, _META_KEYS)
    return parsed


def _parse_result(result: dict) -> dict:
    contents = result.get("contents", [])
    if not contents:
        raise RuntimeError("CU analysis returned no contents")

    content = contents[0]
    phrases = content.get("transcriptPhrases", [])
    fields = content.get("fields", {})

    segments = [
        {
            "start": round(p["startTimeMs"] / 1000.0, 2),
            "end": round(p["endTimeMs"] / 1000.0, 2),
            "text": p["text"].strip(),
            "speaker": p.get("speaker", ""),
            "confidence": round(p.get("confidence", 0), 4),
        }
        for p in phrases
    ]

    full_text = " ".join(s["text"] for s in segments)
    language = phrases[0].get("locale", "en-US") if phrases else "en-US"
    duration = content.get("endTimeMs", 0) / 1000.0

    def _f(key: str) -> str:
        v = fields.get(key, {})
        return v.get("valueString", "") if isinstance(v, dict) else ""

    return {
        "content": full_text,
        "segments": segments,
        "language": language,
        "speaker_count": int(_f("speaker_count")) if _f("speaker_count") else 0,
        "speaker_names": services.parse_csv(_f("speaker_names")),
        "keywords": services.parse_csv(_f("keywords")),
        "duration": duration,
        "summary": _f("summary"),
        "topics": _f("topics"),
        "drug_names": services.parse_csv(_f("drug_name")),
        "cancer_types": services.parse_csv(_f("cancer")),
        "biomarkers": services.parse_csv(_f("biomaker_name")),
        "company_name": _f("company_name") or None,
    }
