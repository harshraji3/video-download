import nltk
import httpx
from bs4 import BeautifulSoup
from nltk.tokenize import sent_tokenize
from documents.db import get_db
from documents.indexer import index_document

nltk.download("punkt_tab", quiet=True)


def extract_paragraphs(html: str) -> tuple[str | None, list[dict]]:
    soup = BeautifulSoup(html, "lxml")

    for tag in soup(["script", "style", "nav", "header", "footer", "aside"]):
        tag.decompose()

    title_tag = soup.find("title")
    title = title_tag.get_text(strip=True) if title_tag else None

    paragraphs: list[dict] = []
    current_heading: str | None = None

    for el in soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6", "p"]):
        text = el.get_text(strip=True)
        if not text:
            continue
        if el.name != "p":
            current_heading = text
        else:
            paragraphs.append({"content": text, "heading": current_heading})
            current_heading = None

    if not paragraphs:
        text = soup.get_text(separator="\n", strip=True)
        for block in text.split("\n\n"):
            block = block.strip()
            if len(block) > 50:
                paragraphs.append({"content": block, "heading": None})

    return title, paragraphs


def split_sentences(paragraphs: list[dict]) -> list[list[dict]]:
    result = []
    for p in paragraphs:
        sentences = sent_tokenize(p["content"])
        result.append([
            {"content": s.strip(), "paragraph_idx": i}
            for i, s in enumerate(sentences) if s.strip()
        ])
    return result


def ingest_web_article(url: str) -> dict:
    resp = httpx.get(url, follow_redirects=True, timeout=30)
    resp.raise_for_status()

    html = resp.text
    title, paragraphs = extract_paragraphs(html)

    update_fields = {"url": url, "raw_html": html}
    if title:
        update_fields["title"] = title

    doc = (
        get_db()
        .table("documents")
        .insert(update_fields)
        .execute()
    )

    if not doc.data:
        raise RuntimeError("Failed to insert document")

    doc_row = doc.data[0]
    doc_id = doc_row["id"]

    para_rows = [
        {
            "document_id": doc_id,
            "idx": i,
            "content": p["content"],
            "heading": p["heading"],
        }
        for i, p in enumerate(paragraphs)
    ]

    sentence_count = 0
    if para_rows:
        inserted = get_db().table("paragraphs").insert(para_rows).execute()
        inserted_paras = inserted.data

        sentences_by_para = split_sentences(paragraphs)

        all_sentences = []
        doc_idx = 0
        for para_row, sent_list in zip(inserted_paras, sentences_by_para):
            for s in sent_list:
                all_sentences.append({
                    "paragraph_id": para_row["id"],
                    "document_id": doc_id,
                    "doc_idx": doc_idx,
                    "idx": s["paragraph_idx"],
                    "content": s["content"],
                })
                doc_idx += 1
                sentence_count += 1

        if all_sentences:
            get_db().table("sentences").insert(all_sentences).execute()

    doc_row["paragraph_count"] = len(para_rows)
    doc_row["sentence_count"] = sentence_count

    chunk_count = index_document(doc_id)
    doc_row["chunk_count"] = chunk_count

    return doc_row
