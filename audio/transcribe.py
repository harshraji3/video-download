import whisper


def transcribe(file_path: str) -> dict:
    model = whisper.load_model("base")
    result = model.transcribe(file_path, fp16=False)

    segments = []
    for seg in result["segments"]:
        segments.append({
            "start": round(seg["start"], 2),
            "end": round(seg["end"], 2),
            "text": seg["text"].strip(),
        })

    return {
        "content": result["text"].strip(),
        "segments": segments,
        "language": result.get("language", "unknown"),
    }
