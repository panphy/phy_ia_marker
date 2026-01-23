import re
from typing import Iterable

PROMPT_QA_MARKER = "# Prompt QA resolution"
PROMPT_QA_RULES = [
    {
        "name": "visual_analysis_citation_separation",
        "requires": [
            "Visual analysis summary",
            "Visual summary + tables/graphs inventory",
        ],
        "guidance": (
            "- Evidence citations must come only from the IA text or coverage report.\n"
            "- If you reference visual analysis, label it as a **visual analysis hint (uncited)** and keep it"
            " separate from IA/coverage evidence.\n"
            "- Do not treat visual-analysis-only content as verified evidence."
        ),
    }
]


def apply_prompt_qa(prompt: str) -> str:
    if PROMPT_QA_MARKER in prompt:
        return prompt
    qa_notes: list[str] = []
    for rule in PROMPT_QA_RULES:
        if all(requirement in prompt for requirement in rule["requires"]):
            qa_notes.append(rule["guidance"])
    if not qa_notes:
        return prompt
    qa_block = "\n".join(
        [PROMPT_QA_MARKER, "Resolve any internal contradictions with the guidance below:"]
        + qa_notes
    )
    return f"{prompt}\n\n{qa_block}"


def split_pages(raw_text: str) -> list[tuple[int, str]]:
    parts = re.split(r"--- Page (\d+) ---", raw_text)
    pages: list[tuple[int, str]] = []
    for index in range(1, len(parts), 2):
        page_number = int(parts[index])
        page_body = parts[index + 1].strip()
        pages.append((page_number, f"--- Page {page_number} ---\n{page_body}"))
    return pages


def _chunk_text(text: str, max_chars: int) -> list[str]:
    if max_chars <= 0:
        return [text]
    return [text[start : start + max_chars] for start in range(0, len(text), max_chars)]


def _chunk_oversized_page(page_number: int, page_text: str, target_chars: int) -> list[dict[str, object]]:
    lines = page_text.splitlines()
    header = lines[0] if lines else f"--- Page {page_number} ---"
    body = "\n".join(lines[1:]).strip()
    chunk_size = max(1, target_chars - len(header) - 1)
    body_chunks = _chunk_text(body, chunk_size)
    if not body_chunks:
        body_chunks = [""]
    return [
        {
            "start_page": page_number,
            "end_page": page_number,
            "text": f"{header}\n{chunk}".rstrip(),
        }
        for chunk in body_chunks
    ]


def chunk_pages(raw_text: str, target_chars: int) -> list[dict[str, object]]:
    pages = split_pages(raw_text)
    if not pages:
        return [{"start_page": None, "end_page": None, "text": raw_text}]

    chunks: list[dict[str, object]] = []
    current_pages: list[tuple[int, str]] = []
    current_len = 0

    for page_number, page_text in pages:
        page_len = len(page_text)
        if page_len > target_chars:
            if current_pages:
                start_page = current_pages[0][0]
                end_page = current_pages[-1][0]
                chunks.append(
                    {
                        "start_page": start_page,
                        "end_page": end_page,
                        "text": "\n\n".join(text for _, text in current_pages),
                    }
                )
                current_pages = []
                current_len = 0
            chunks.extend(_chunk_oversized_page(page_number, page_text, target_chars))
            continue

        if current_pages and current_len + page_len > target_chars:
            start_page = current_pages[0][0]
            end_page = current_pages[-1][0]
            chunks.append(
                {
                    "start_page": start_page,
                    "end_page": end_page,
                    "text": "\n\n".join(text for _, text in current_pages),
                }
            )
            current_pages = []
            current_len = 0

        current_pages.append((page_number, page_text))
        current_len += page_len

    if current_pages:
        start_page = current_pages[0][0]
        end_page = current_pages[-1][0]
        chunks.append(
            {
                "start_page": start_page,
                "end_page": end_page,
                "text": "\n\n".join(text for _, text in current_pages),
            }
        )

    return chunks


def report_has_expected_citations(report: str, used_digest: bool) -> bool:
    if not report.strip():
        return True
    patterns = [
        r"---\s*Page\s+\d+\s*---",
        r"\bPage\s+\d+",
    ]
    if used_digest:
        patterns.extend([r"\bPages?\s+\d", r"\bCHUNK\s+\d", r"\bChunk\s+\d"])
    return any(re.search(pattern, report) for pattern in patterns)


def sample_evenly(items: Iterable[object], limit: int) -> list[object]:
    items_list = list(items)
    if limit <= 0 or not items_list:
        return []
    if len(items_list) <= limit:
        return items_list
    if limit == 1:
        return [items_list[len(items_list) // 2]]
    step = (len(items_list) - 1) / (limit - 1)
    indices = [round(i * step) for i in range(limit)]
    unique_indices = []
    seen = set()
    for index in indices:
        if index not in seen:
            unique_indices.append(index)
            seen.add(index)
    while len(unique_indices) < limit:
        for index in range(len(items_list)):
            if index not in seen:
                unique_indices.append(index)
                seen.add(index)
            if len(unique_indices) == limit:
                break
    return [items_list[index] for index in unique_indices]
