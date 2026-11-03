"""Resume text extraction and structured parsing."""

from __future__ import annotations

import io
from typing import Any

from app.ai.llm import LLM, untrusted

MAX_TEXT_CHARS = 30000

RESUME_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "email": {"type": "string"},
        "phone": {"type": "string"},
        "headline": {"type": "string", "description": "one-line professional title"},
        "summary": {"type": "string", "description": "2-3 sentence summary"},
        "years_experience": {"type": "number"},
        "locations": {"type": "array", "items": {"type": "string"}},
        "skills": {"type": "array", "items": {"type": "string"}},
        "experience": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "company": {"type": "string"},
                    "title": {"type": "string"},
                    "start": {"type": "string"},
                    "end": {"type": "string"},
                    "highlights": {"type": "array", "items": {"type": "string"}},
                },
            },
        },
        "education": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "institution": {"type": "string"},
                    "degree": {"type": "string"},
                    "year": {"type": "string"},
                },
            },
        },
        "links": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["skills", "experience"],
}


def extract_text(data: bytes, content_type: str, filename: str) -> str:
    name = filename.lower()
    if content_type == "application/pdf" or name.endswith(".pdf"):
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(data))
        text = "\n".join((page.extract_text() or "") for page in reader.pages)
    elif name.endswith(".docx") or content_type.endswith("wordprocessingml.document"):
        from docx import Document

        doc = Document(io.BytesIO(data))
        parts = [p.text for p in doc.paragraphs]
        for table in doc.tables:
            for row in table.rows:
                parts.append(" | ".join(c.text for c in row.cells))
        text = "\n".join(parts)
    else:
        text = data.decode("utf-8", errors="replace")
    return _clean(text)[:MAX_TEXT_CHARS]


def _clean(text: str) -> str:
    lines = [line.strip() for line in text.replace("\r", "").split("\n")]
    out: list[str] = []
    blank = 0
    for line in lines:
        if not line:
            blank += 1
            if blank <= 1:
                out.append("")
            continue
        blank = 0
        out.append(line)
    return "\n".join(out).strip()


async def parse_structured(llm: LLM, text: str) -> dict[str, Any]:
    system = (
        "You extract structured data from resumes. Copy facts exactly as written; never invent "
        "employers, dates, degrees or skills that are not in the text. Leave unknown fields empty."
    )
    prompt = "Extract this resume into the schema.\n\n" + untrusted(text, "resume")
    data = await llm.json(system=system, prompt=prompt, schema=RESUME_SCHEMA, max_tokens=2000)
    data["skills"] = dedupe_skills(data.get("skills", []))
    return data


def dedupe_skills(raw: object) -> list[str]:
    """Trim, drop blanks, de-duplicate case-insensitively (first spelling wins), keep order."""
    seen: set[str] = set()
    out: list[str] = []
    for s in raw if isinstance(raw, list) else []:
        if not isinstance(s, str) or not s.strip():
            continue
        key = s.strip().lower()
        if key not in seen:
            seen.add(key)
            out.append(s.strip()[:80])
    return out
