import base64
import re
import threading
import time
from typing import Iterable


CRITERION_NAMES = (
    "Research design",
    "Data analysis",
    "Conclusion",
    "Evaluation",
)

EVIDENCE_TERMS = {
    "Research design": r"research question|independent variable|dependent variable|control variable|apparatus|method(?:ology)?|procedure|repeat|range|interval",
    "Data analysis": r"raw data|processed data|uncertaint|error bar|gradient|slope|graph|fit|regress|calculation|significant figure",
    "Conclusion": r"conclusion|result|hypothesis|theor|accepted value|agreement|discrepan|percentage difference",
    "Evaluation": r"evaluation|limitation|weakness|improvement|systematic error|random error|reliab|validity",
}

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


def _has_source_citation(text: str, used_digest: bool) -> bool:
    patterns = [r"\bPages?\s+\d+", r"---\s*Page\s+\d+\s*---"]
    if used_digest:
        patterns.append(r"\bCHUNK\s+\d+")
    return any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in patterns)


def report_has_expected_citations(report: str, used_digest: bool) -> bool:
    """Require an evidence location for each of the four criterion decisions."""
    if not report.strip():
        return False
    for criterion in CRITERION_NAMES:
        heading = re.search(
            rf"^###\s+{re.escape(criterion)}\b[^\n]*\n(?P<body>.*?)(?=^#{2,3}\s|\Z)",
            report,
            flags=re.IGNORECASE | re.MULTILINE | re.DOTALL,
        )
        if heading:
            evidence = heading.group("body")
        else:
            row = re.search(
                rf"^\|\s*\**{re.escape(criterion)}\**\s*\|(?P<body>[^\n]+)$",
                report,
                flags=re.IGNORECASE | re.MULTILINE,
            )
            if not row:
                return False
            evidence = row.group("body")
        if not _has_source_citation(evidence, used_digest):
            return False
    return True


def report_validation_issues(report: str, used_digest: bool) -> list[str]:
    """Return problems that prevent a report from being treated as complete."""
    if not report.strip():
        return ["The model returned an empty report."]
    missing = [name for name in CRITERION_NAMES if name not in extract_report_scores(report)]
    issues = []
    if missing:
        issues.append("Missing criterion marks: " + ", ".join(missing) + ".")
    for criterion in CRITERION_NAMES:
        heading = re.search(
            rf"^###\s+{re.escape(criterion)}\s*(?:[—-]|\().*?(?<!\d)([0-6])\s*/\s*6\b",
            report,
            flags=re.IGNORECASE | re.MULTILINE,
        )
        row = re.search(
            rf"^\|\s*\**{re.escape(criterion)}\**\s*\|(?P<cells>[^\n]+)$",
            report,
            flags=re.IGNORECASE | re.MULTILINE,
        )
        if heading and row:
            cells = row.group("cells").split("|")
            if len(cells) >= 3:
                final = re.fullmatch(r"\s*\**([0-6])(?:\s*/\s*6)?\**\s*", cells[2])
                if final and int(heading.group(1)) != int(final.group(1)):
                    issues.append(f"{criterion} heading and final table mark disagree.")
    if not report_has_expected_citations(report, used_digest):
        issues.append("Each criterion needs a page or digest citation.")
    return issues


def report_cited_pages(report: str) -> set[int]:
    """Collect explicit page references for source-range validation."""
    pages: set[int] = set()
    for match in re.finditer(r"\bPages?\s+(\d+)(?:\s*[-–—]\s*(\d+))?", report, re.IGNORECASE):
        start = int(match.group(1))
        end = int(match.group(2)) if match.group(2) else start
        pages.update(range(start, min(end, start + 1000) + 1))
    return pages


def report_page_issues(report: str, page_count: int) -> list[str]:
    invalid = sorted(page for page in report_cited_pages(report) if page < 1 or page > page_count)
    return [f"Citations refer to pages outside this PDF: {', '.join(map(str, invalid))}."] if invalid else []


def audit_requests_review(report: str) -> bool:
    """An absent or ambiguous audit verdict is treated as needing moderation."""
    verdict = re.search(r"\*{0,2}Escalation required:\*{0,2}\s*(yes|no)\b", report, re.IGNORECASE)
    return verdict is None or verdict.group(1).lower() == "yes"


def primary_requests_human_review(report: str) -> bool:
    verdict = re.search(
        r"\*{0,2}Human review recommended:\*{0,2}\s*(yes|no)\b",
        report,
        flags=re.IGNORECASE,
    )
    return verdict is None or verdict.group(1).lower() == "yes"


def moderation_reasons(
    primary_report: str,
    audit_report: str,
    coverage_warnings: list[str],
    visual_error: bool,
    visuals_without_source_images: bool,
) -> list[str]:
    primary = extract_report_scores(primary_report)
    audited = extract_report_scores(audit_report)
    reasons = [
        f"{criterion}: primary {primary[criterion]}/6, audit {audited[criterion]}/6"
        for criterion in CRITERION_NAMES
        if criterion in primary and criterion in audited and primary[criterion] != audited[criterion]
    ]
    if len(primary) != 4 or len(audited) != 4:
        reasons.append("A report is missing one or more criterion marks")
    if primary_requests_human_review(primary_report):
        reasons.append("The primary marker requested human review or gave no clear verdict")
    if audit_requests_review(audit_report):
        reasons.append("The evidence auditor requested review or gave no clear verdict")
    if coverage_warnings:
        reasons.append("PDF extraction has evidence-quality warnings")
    if visual_error:
        reasons.append("Visual analysis failed")
    if visuals_without_source_images:
        reasons.append("A relevant original visual was not supplied to the marking calls")
    return reasons


def build_agreed_decision(primary_report: str, audit_report: str) -> str:
    """Finalize only exact agreement after the evidence audit passes."""
    if moderation_reasons(primary_report, audit_report, [], False, False):
        raise ValueError("A moderated decision is required.")
    scores = extract_report_scores(primary_report)
    sections = []
    for criterion in CRITERION_NAMES:
        match = re.search(
            rf"^###\s+{re.escape(criterion)}\b[^\n]*\n.*?(?=^#{2,3}\s|\Z)",
            primary_report,
            flags=re.IGNORECASE | re.MULTILINE | re.DOTALL,
        )
        if not match:
            raise ValueError(f"Missing {criterion} evidence section.")
        sections.append(match.group(0).strip())
    total = sum(scores.values())
    return (
        "## Final decision\n"
        f"- **Total:** {total}/24\n"
        "- **Human review recommended:** no — the evidence audit confirmed all four marks and no extraction warning was detected.\n"
        "- **Decision route:** primary marks confirmed by evidence audit; no chief moderation was needed.\n\n"
        "## Criterion decisions\n\n"
        + "\n\n".join(sections)
        + "\n\nReview the cited pages in the original IA before using this recommendation."
    )


def build_page_evidence_index(
    diagnostics: Iterable[object], visuals: Iterable[object], source_images: Iterable[object]
) -> str:
    """Create a deterministic page map; the full IA remains the source for claims."""
    visual_pages: dict[int, int] = {}
    for visual in visuals:
        page = int(getattr(visual, "page_number"))
        visual_pages[page] = visual_pages.get(page, 0) + 1
    supplied_pages = {int(getattr(image, "page_number")) for image in source_images}
    lines = [
        "Page evidence index (navigation and extraction status; not a substitute for the original IA):"
    ]
    for diag in diagnostics:
        page = int(getattr(diag, "page_number"))
        sources = []
        if getattr(diag, "has_text"):
            sources.append("selectable text")
        if getattr(diag, "used_ocr"):
            sources.append("OCR")
        if not sources:
            sources.append("no readable text")
        visual_count = visual_pages.get(page, 0)
        supplied = "yes" if page in supplied_pages else "no"
        lines.append(
            f"- Page {page}: {', '.join(sources)}; {visual_count} detected visuals; "
            f"at least one source image from page supplied: {supplied}."
        )
    return "\n".join(lines)


def build_candidate_evidence_ledger(raw_text: str, per_criterion_limit: int = 8) -> str:
    """Quote likely relevant IA lines with source pages; make no inference or mark."""
    lines = [
        "Candidate evidence excerpts from the student's IA (untrusted; verify against the full page):"
    ]
    pages = split_pages(raw_text)
    for criterion, terms in EVIDENCE_TERMS.items():
        excerpts = []
        for page_number, page_text in pages:
            for line in page_text.splitlines()[1:]:
                excerpt = " ".join(line.split())
                if len(excerpt) < 12 or not re.search(terms, excerpt, flags=re.IGNORECASE):
                    continue
                excerpts.append(f"- Page {page_number}: {excerpt[:240]}")
        lines.append(f"## {criterion}")
        lines.extend(sample_evenly(excerpts, per_criterion_limit) or ["- No keyword-matched excerpt found; inspect the full IA."])
    return "\n".join(lines)


def build_evaluation_record(
    case_id: str,
    model: str,
    primary_report: str,
    audit_report: str,
    final_report: str,
    decision_mode: str,
    escalation_reasons: list[str],
    usage_log: list[dict[str, object]],
) -> dict[str, object]:
    """Export marks and run metadata without the student's IA or report text."""
    review = re.search(
        r"\*{0,2}Human review recommended:\*{0,2}\s*(yes|no)\b",
        final_report,
        flags=re.IGNORECASE,
    )
    return {
        "case_id": case_id,
        "pipeline": "evidence_audit_v1",
        "model": model,
        "primary_marks": extract_report_scores(primary_report),
        "audit_marks": extract_report_scores(audit_report),
        "marks": extract_report_scores(final_report),
        "decision_mode": decision_mode,
        "escalation_reasons": escalation_reasons,
        "review_recommended": review is None or review.group(1).lower() == "yes",
        "api_input_tokens": sum(int(entry.get("input_tokens") or 0) for entry in usage_log),
        "api_output_tokens": sum(int(entry.get("output_tokens") or 0) for entry in usage_log),
        "api_seconds": round(sum(float(entry.get("seconds") or 0) for entry in usage_log), 2),
    }


def build_model_input(user_input: str, source_images: Iterable[object]) -> str | list[dict]:
    """Attach original PDF visuals with explicit source-page labels."""
    images = list(source_images)
    if not images:
        return user_input
    content = [{"type": "input_text", "text": user_input}]
    for image in images:
        page = int(getattr(image, "page_number"))
        data = bytes(getattr(image, "png_data"))
        content.append({"type": "input_text", "text": f"Original PDF visual from Page {page}."})
        content.append(
            {
                "type": "input_image",
                "image_url": "data:image/png;base64," + base64.b64encode(data).decode("ascii"),
                "detail": "high",
            }
        )
    return [{"role": "user", "content": content}]


class LoginThrottle:
    """One shared, process-wide login cooldown across browser sessions."""

    def __init__(self, max_attempts: int, window_seconds: int) -> None:
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self._failures: list[float] = []
        self._lock = threading.Lock()

    def try_password(self, supplied: str, expected: str, now: float | None = None) -> tuple[bool, int]:
        from hmac import compare_digest

        current = time.time() if now is None else now
        with self._lock:
            self._failures = [
                timestamp for timestamp in self._failures
                if current - timestamp < self.window_seconds
            ]
            if len(self._failures) >= self.max_attempts:
                remaining = max(1, int(self.window_seconds - (current - self._failures[0])) + 1)
                return False, remaining
            if compare_digest(supplied, expected):
                return True, 0
            self._failures.append(current)
            remaining = self.window_seconds if len(self._failures) >= self.max_attempts else 0
            return False, remaining

    def cooldown_remaining(self, now: float | None = None) -> int:
        current = time.time() if now is None else now
        with self._lock:
            self._failures = [
                timestamp for timestamp in self._failures
                if current - timestamp < self.window_seconds
            ]
            if len(self._failures) < self.max_attempts:
                return 0
            return max(1, int(self.window_seconds - (current - self._failures[0])) + 1)


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


def extract_report_scores(report: str) -> dict[str, int]:
    """Extract final/awarded criterion marks from a generated Markdown report."""
    scores: dict[str, int] = {}
    for criterion in CRITERION_NAMES:
        heading_pattern = re.compile(
            rf"^###\s+{re.escape(criterion)}\s*(?:[—-]|\().*?(?<!\d)([0-6])\s*/\s*6\b",
            flags=re.IGNORECASE | re.MULTILINE,
        )
        heading_match = heading_pattern.search(report)
        if heading_match:
            scores[criterion] = int(heading_match.group(1))
            continue

        table_pattern = re.compile(
            rf"^\|\s*\**{re.escape(criterion)}\**\s*\|(?P<cells>.+)$",
            flags=re.IGNORECASE | re.MULTILINE,
        )
        table_match = table_pattern.search(report)
        if table_match:
            marks = []
            for cell in table_match.group("cells").split("|"):
                mark = re.fullmatch(r"\s*\**([0-6])(?:\s*/\s*6)?\**\s*", cell)
                if mark:
                    marks.append(int(mark.group(1)))
            if marks:
                # Moderator tables place the final mark after both examiner marks.
                scores[criterion] = marks[2] if len(marks) >= 3 else marks[0]
    return scores


def build_combined_report(
    examiner1_report: str,
    examiner2_report: str,
    moderator_report: str,
) -> str:
    """Create a single downloadable Markdown bundle from completed reports."""
    sections = ["# IB DP Physics IA assessment bundle"]
    for title, report in (
        ("Primary mark — Experimentalist", examiner1_report),
        ("Evidence audit", examiner2_report),
        ("Final decision", moderator_report),
    ):
        if report.strip():
            sections.extend([f"## {title}", report.strip()])
    return "\n\n---\n\n".join(sections) + "\n"
