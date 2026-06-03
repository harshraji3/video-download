import os
import json
import re
from google import genai

_client: genai.Client | None = None


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(api_key=os.environ["GOOGLE_API_KEY"])
    return _client


def generate_answer(query: str, evidence_blocks: list[dict]) -> dict:
    context_parts = []
    for i, block in enumerate(evidence_blocks):
        source_type = block["source_type"]
        lines = [f"--- SOURCE {i + 1} ---"]

        if source_type == "webpage":
            lines.append(f"Type: Web Article")
            lines.append(f"Title: {block.get('document_title', 'N/A')}")
            lines.append(f"URL: {block.get('document_url', 'N/A')}")
        elif source_type == "audio":
            lines.append(f"Type: Audio Transcript")
            lines.append(f"Title: {block.get('audio_title', 'N/A')}")
            if block.get("speaker"):
                lines.append(f"Speaker: {block['speaker']}")
            lines.append(f"Timestamp: {block.get('start_time', '?')}s - {block.get('end_time', '?')}s")

        lines.append(f"Relevant Excerpt: {block['content']}")

        ctx_sents = block.get("context_window", [])
        if ctx_sents:
            lines.append("Surrounding Context:")
            for s in ctx_sents:
                ts = ""
                if s.get("start_time") is not None:
                    ts = f" [{s['start_time']}s - {s['end_time']}s]"
                lines.append(f"  - {s['content']}{ts}")

        context_parts.append("\n".join(lines))

    context_str = "\n\n".join(context_parts)

    prompt = f"""You are an evidence-based answer generator. Answer the user's question using ONLY the provided sources below. If the evidence is insufficient, say so.

For EVERY claim in your answer, cite the exact source number (Source 1, Source 2, etc.) and include the precise location (URL for web articles, timestamp range for audio).

IMPORTANT: start_time and end_time must be numbers (e.g., 0.0, 14.64), NOT strings. Do NOT include "s" or "seconds" suffix.

Return ONLY a JSON object with this exact structure (no markdown, no code fences):
{{
  "answer": "concise answer synthesized from the evidence",
  "insufficient_evidence": false,
  "citations": [
    {{
      "source_number": 1,
      "source_type": "webpage",
      "source_title": "...",
      "url": null,
      "speaker": null,
      "start_time": null,
      "end_time": null,
      "supporting_text": "exact excerpt from the source"
    }}
  ]
}}

If no source answers the question, set "insufficient_evidence" to true and explain what's missing in "answer".

CONTEXT:
{context_str}

USER QUESTION: {query}"""

    response = _get_client().models.generate_content(
        model="models/gemma-4-31b-it",
        contents=prompt,
        config={
            "response_mime_type": "application/json",
        },
    )

    raw = response.text.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)

    result = json.loads(raw)

    for c in result.get("citations", []):
        for key in ("start_time", "end_time"):
            val = c.get(key)
            if isinstance(val, str):
                val = re.sub(r"[^\d.\-]", "", val)
                try:
                    c[key] = float(val) if val else None
                except ValueError:
                    c[key] = None

    return result
