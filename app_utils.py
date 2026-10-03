import base64
import json
import re
import threading
import time
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Iterable


@dataclass(frozen=True)
class AssessmentType:
    """One kind of student work, with its criteria, rubric and prompt files."""

    key: str
    label: str
    short_name: str
    criteria: tuple[tuple[str, int], ...]
    rubric_file: str
    prompt_files: tuple[str, str, str]  # primary marker, evidence auditor, Chief Moderator
    evidence_terms: tuple[tuple[str, str], ...]
    pipeline: str
    rubric_note: str
    # Shown wherever marks are reported when the app marks fewer criteria than the official model.
    marking_notice: str = ""

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(name for name, _ in self.criteria)

    @property
    def total(self) -> int:
        return sum(maximum for _, maximum in self.criteria)

    def maximum(self, criterion: str) -> int:
        return dict(self.criteria)[criterion]

    @property
    def count_word(self) -> str:
        return {4: "four", 5: "five"}.get(len(self.criteria), str(len(self.criteria)))


IA = AssessmentType(
    key="ia",
    label="Internal assessment (IA)",
    short_name="IA",
    criteria=(
        ("Research design", 6),
        ("Data analysis", 6),
        ("Conclusion", 6),
        ("Evaluation", 6),
    ),
    rubric_file="ib_phy_ia_criteria.md",
    prompt_files=("examiner1_prompt.md", "examiner2_prompt.md", "moderator_prompt.md"),
    evidence_terms=(
        ("Research design", r"research question|independent variable|dependent variable|control variable|apparatus|method(?:ology)?|procedure|repeat|range|interval"),
        ("Data analysis", r"raw data|processed data|uncertaint|error bar|gradient|slope|graph|fit|regress|calculation|significant figure"),
        ("Conclusion", r"conclusion|result|hypothesis|theor|accepted value|agreement|discrepan|percentage difference"),
        ("Evaluation", r"evaluation|limitation|weakness|improvement|systematic error|random error|reliab|validity"),
    ),
    pipeline="evidence_audit_v1",
    rubric_note="Physics guide, first assessment 2025 · verified for 2026",
)

EE = AssessmentType(
    key="ee",
    label="Extended essay (EE)",
    short_name="EE",
    criteria=(
        ("Framework for the essay", 6),
        ("Knowledge and understanding", 6),
        ("Analysis and line of argument", 6),
        ("Discussion and evaluation", 8),
    ),
    rubric_file="ib_phy_ee_criteria.md",
    prompt_files=("ee_primary_prompt.md", "ee_audit_prompt.md", "ee_moderator_prompt.md"),
    evidence_terms=(
        ("Framework for the essay", r"research question|method(?:ology)?|approach|experiment|simulation|primary data|secondary data|database|structure|scope|introduction"),
        ("Knowledge and understanding", r"theor|law|principle|equation|model|concept|background|literature|source|reference|bibliograph"),
        ("Analysis and line of argument", r"analys|data|graph|calculat|uncertaint|gradient|fit|trend|result|argument|therefore|suggests"),
        ("Discussion and evaluation", r"discuss|conclusion|significan|implication|limitation|strength|weakness|evaluat|reliab|validity|further research"),
    ),
    pipeline="ee_evidence_audit_v2",
    rubric_note="Extended essay guide, first assessment 2027 · descriptors paraphrased, verify",
    marking_notice=(
        "Criterion E (Reflection, 4 marks) is not marked, because the Reflection and Progress Form "
        "is usually unavailable. Marks cover criteria A–D only and are out of 26, not the official 30."
    ),
)

ASSESSMENT_TYPES = {assessment.key: assessment for assessment in (IA, EE)}

# The IA names are kept for callers that predate the EE option.
CRITERION_NAMES = IA.names
EVIDENCE_TERMS = dict(IA.evidence_terms)

INJECTION_DIRECTIVE_PATTERNS = {
    "instruction_override": (
        r"\b(?:ignore|disregard|forget|override)\s+"
        r"(?:(?:all|any|previous|prior|earlier|original|above|the|these|your|of)\s+){0,8}"
        r"(?:instructions?|prompts?|rules?|rubric|criteria)\b"
    ),
    "mark_command": (
        r"\b(?:give|award|assign|set|score|mark|grade)\b[^\n.!?]{0,80}"
        r"\b(?:full|maximum|perfect|top)\s+(?:marks?|score|points?)\b"
    ),
    "perfect_score_command": (
        r"\b(?:give|award|assign|set|score|mark|grade)\b[^\n.!?]{0,80}"
        r"\b(?:24\s*/\s*24|26\s*/\s*26|30\s*/\s*30|4\s*/\s*4|6\s*/\s*6|8\s*/\s*8)\b"
    ),
    "role_spoofing": (
        r"\b(?:you are now|act as|assume the role of)\s+(?:the\s+)?"
        r"(?:system|developer|examiner|marker|moderator|grader|assistant)\b"
    ),
    "prompt_reference": r"\b(?:system prompt|developer message|jailbreak)\b",
}


def scan_injection_phrases(text: str, page_number: int | None = None) -> list[dict[str, object]]:
    """Find likely instructions addressed to the marker, without treating IA text as authority."""
    page_markers = list(re.finditer(r"--- Page (\d+) ---", text)) if page_number is None else []
    matches: list[dict[str, object]] = []
    for kind, pattern in INJECTION_DIRECTIVE_PATTERNS.items():
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            preceding = [marker for marker in page_markers if marker.start() <= match.start()]
            page = page_number if page_number is not None else (
                int(preceding[-1].group(1)) if preceding else None
            )
            matches.append(
                {"kind": kind, "start": match.start(), "end": match.end(), "page_number": page}
            )
    return sorted(matches, key=lambda item: int(item["start"]))


def redact_injection_spans(text: str, matches: list[dict[str, object]]) -> str:
    """Remove each suspect line, including instructions after the matched phrase."""
    spans: list[tuple[int, int]] = []
    for match in matches:
        start = text.rfind("\n", 0, int(match["start"])) + 1
        end = text.find("\n", int(match["end"]))
        spans.append((start, len(text) if end < 0 else end))
    merged: list[list[int]] = []
    for start, end in sorted(set(spans)):
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    for start, end in reversed(merged):
        text = text[:start] + "[Potential instruction directed at marker removed]" + text[end:]
    return text


def require_human_review(report: str, reason: str) -> str:
    """Apply a deterministic review flag to a model report after validation."""
    review_line = f"- **Human review recommended:** yes — {reason}"
    pattern = r"(?im)^-\s*" + _label("Human review recommended") + r"(?:yes|no)\b[^\n]*"
    if re.search(pattern, report):
        return re.sub(pattern, lambda _: review_line, report, count=1)
    return f"## Mandatory human review\n{review_line}\n\n{report}"

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


def report_has_expected_citations(
    report: str, used_digest: bool, assessment: AssessmentType = IA
) -> bool:
    """Require an evidence location for each criterion decision."""
    if not report.strip():
        return False
    for criterion in assessment.names:
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


def _heading_mark(report: str, criterion: str, maximum: int) -> int | None:
    """Read "### Criterion — X/max"; a mark above the maximum counts as missing."""
    match = re.search(
        rf"^###\s+{re.escape(criterion)}\s*(?:[—-]|\().*?(?<!\d)(\d)\s*/\s*{maximum}\b",
        report,
        flags=re.IGNORECASE | re.MULTILINE,
    )
    if match and int(match.group(1)) <= maximum:
        return int(match.group(1))
    return None


def _cell_mark(cell: str, maximum: int) -> int | None:
    match = re.fullmatch(rf"\s*\**(\d)(?:\s*/\s*{maximum})?\**\s*", cell)
    if match and int(match.group(1)) <= maximum:
        return int(match.group(1))
    return None


def report_validation_issues(
    report: str, used_digest: bool, assessment: AssessmentType = IA
) -> list[str]:
    """Return problems that prevent a report from being treated as complete."""
    if not report.strip():
        return ["The model returned an empty report."]
    scores = extract_report_scores(report, assessment)
    missing = [name for name in assessment.names if name not in scores]
    issues = []
    if missing:
        issues.append("Missing criterion marks: " + ", ".join(missing) + ".")
    for criterion, maximum in assessment.criteria:
        heading = _heading_mark(report, criterion, maximum)
        row = re.search(
            rf"^\|\s*\**{re.escape(criterion)}\**\s*\|(?P<cells>[^\n]+)$",
            report,
            flags=re.IGNORECASE | re.MULTILINE,
        )
        if heading is not None and row:
            cells = row.group("cells").split("|")
            if len(cells) >= 3:
                final = _cell_mark(cells[2], maximum)
                if final is not None and heading != final:
                    issues.append(f"{criterion} heading and final table mark disagree.")
    if len(scores) == len(assessment.criteria):
        mark_sum = sum(scores.values())
        for stated in report_stated_totals(report, assessment.total):
            if stated != mark_sum:
                issues.append(
                    f"The stated total {stated}/{assessment.total} does not match the criterion marks "
                    f"({mark_sum}/{assessment.total})."
                )
                break
    if not report_has_expected_citations(report, used_digest, assessment):
        issues.append("Each criterion needs a page or digest citation.")
    return issues


def report_stated_totals(report: str, maximum_total: int = IA.total) -> list[int]:
    """Return totals written in a report's summary line and marks table, if present."""
    totals = []
    line = re.search(
        rf"\*{{0,2}}Total:\*{{0,2}}\s*\*{{0,2}}(\d{{1,2}})\s*/\s*{maximum_total}\b", report, re.IGNORECASE
    )
    if line:
        totals.append(int(line.group(1)))
    row = re.search(r"^\|\s*\**Total\**\s*\|(?P<cells>[^\n]+)$", report, re.IGNORECASE | re.MULTILINE)
    if row:
        values = []
        for cell in row.group("cells").split("|"):
            value = re.fullmatch(rf"\s*\**(\d{{1,2}})(?:\s*/\s*{maximum_total})?\**\s*", cell)
            if value:
                values.append(int(value.group(1)))
        if len(values) > 1 and values[-1] == maximum_total:
            values = values[:-1]  # drop the Maximum column
        if values:
            # Moderator tables list primary, audit and final totals in that order.
            totals.append(values[2] if len(values) >= 3 else values[0])
    return totals


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


def _label(label: str) -> str:
    """Regex for a report label, with the colon inside or outside Markdown bold."""
    return rf"\*{{0,2}}{re.escape(label)}(?::\*{{0,2}}|\*{{0,2}}\s*:)\s*\*{{0,2}}\s*"


def audit_requests_review(report: str) -> bool:
    """An absent or ambiguous audit verdict is treated as needing moderation."""
    verdict = re.search(_label("Escalation required") + r"(yes|no)\b", report, re.IGNORECASE)
    return verdict is None or verdict.group(1).lower() == "yes"


HUMAN_REVIEW_PATTERN = re.compile(
    _label("Human review recommended") + r"(yes|no)\b\**[\s—–:-]*([^\n]*)",
    flags=re.IGNORECASE,
)


def report_requests_human_review(report: str) -> bool:
    """An absent or ambiguous human-review verdict is treated as a request for review."""
    verdict = HUMAN_REVIEW_PATTERN.search(report)
    return verdict is None or verdict.group(1).lower() == "yes"


def human_review_reason(report: str) -> str:
    verdict = HUMAN_REVIEW_PATTERN.search(report)
    return verdict.group(2).strip().rstrip(".") if verdict else ""


def primary_requests_human_review(report: str) -> bool:
    return report_requests_human_review(report)


def _criterion_section(report: str, criterion: str) -> str | None:
    match = re.search(
        rf"^###\s+{re.escape(criterion)}\b[^\n]*\n(?P<body>.*?)(?=^#{{2,3}}\s|\Z)",
        report,
        flags=re.IGNORECASE | re.MULTILINE | re.DOTALL,
    )
    return match.group("body") if match else None


def _mark_out_of(maximum: int) -> str:
    return rf"(?<![\d.])(\d)\s*(?:/|out of)\s*{maximum}\b"


def _labelled_mark(section: str, label: str, maximum: int = 6) -> int | None:
    """Read the mark on a labelled line, e.g. "Keep 4/6" or "Raise from 4/6 to 5/6".

    A mark after "to"/"→" is the recommendation; otherwise the first mark on the line is.
    """
    line = re.search(_label(label) + r"(?P<rest>[^\n]*)", section, flags=re.IGNORECASE)
    if not line:
        return None
    rest = line.group("rest")
    mark = _mark_out_of(maximum)
    found = re.search(r"(?:\bto\b|→|->)\s*\**\s*" + mark, rest, flags=re.IGNORECASE)
    if not found:
        found = re.search(mark, rest, flags=re.IGNORECASE)
    if found and int(found.group(1)) <= maximum:
        return int(found.group(1))
    return None


def audit_mark_issues(
    primary_report: str, audit_report: str, assessment: AssessmentType = IA
) -> list[str]:
    """Check that the audit heading, its recommendation and its quoted primary mark agree."""
    primary = extract_report_scores(primary_report, assessment)
    audited = extract_report_scores(audit_report, assessment)
    issues = []
    for criterion, maximum in assessment.criteria:
        section = _criterion_section(audit_report, criterion)
        if section is None:
            continue
        recommendation = _labelled_mark(section, "Audited mark recommendation", maximum)
        heading = audited.get(criterion)
        if recommendation is None:
            issues.append(f"{criterion}: the audit gave no clear mark recommendation")
        elif heading is not None and recommendation != heading:
            issues.append(
                f"{criterion}: audit heading {heading}/{maximum} but recommendation {recommendation}/{maximum}"
            )
        quoted_primary = _labelled_mark(section, "Primary mark", maximum)
        if quoted_primary is not None and criterion in primary and quoted_primary != primary[criterion]:
            issues.append(
                f"{criterion}: the audit quoted the primary mark as {quoted_primary}/{maximum}, "
                f"but the primary marker awarded {primary[criterion]}/{maximum}"
            )
    return issues


QUOTE_PATTERN = re.compile(r"[“\"]([^”\"\n]{12,400})[”\"]")
MIN_VERIFIABLE_PAGE_CHARS = 200


def _normalize_for_match(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def _fuzzy_contains(needle: str, haystack: str, threshold: float = 0.85) -> bool:
    needle_tokens = needle.split()
    haystack_tokens = haystack.split()
    width = len(needle_tokens)
    starts = {token for token in needle_tokens[:3]}
    for index, token in enumerate(haystack_tokens):
        if token not in starts:
            continue
        window = haystack_tokens[max(0, index - 2): index + width + 2]
        matcher = SequenceMatcher(None, needle_tokens, window, autojunk=False)
        matched = sum(block.size for block in matcher.get_matching_blocks())
        if matched / width >= threshold:
            return True
    return False


def unverified_quotes(
    report: str,
    page_texts: dict[int, str],
    reference_text: str = "",
) -> list[dict[str, object]]:
    """Find quoted excerpts that do not appear in the extracted text of the cited pages.

    Quotes of rubric or prompt wording, or of earlier reports, are ignored (pass them as
    reference_text). Pages with too little extracted text to check, such as image-only
    pages, are skipped rather than flagged.
    """
    reference = _normalize_for_match(reference_text)
    findings: list[dict[str, object]] = []
    seen: set[str] = set()
    for line in report.splitlines():
        cited = sorted(page for page in report_cited_pages(line) if page in page_texts)
        if not cited:
            continue
        if sum(len(page_texts[page]) for page in cited) < MIN_VERIFIABLE_PAGE_CHARS:
            continue
        window = sorted({near for page in cited for near in (page - 1, page, page + 1)} & set(page_texts))
        haystack = _normalize_for_match(" ".join(page_texts[page] for page in window))
        for match in QUOTE_PATTERN.finditer(line):
            quote = match.group(1).strip()
            fragments = [
                _normalize_for_match(part) for part in re.split(r"\.\.\.|…|\[\.\.\.\]", quote)
            ]
            fragments = [part for part in fragments if len(part.split()) >= 4]
            if not fragments or quote in seen:
                continue
            if all(part in reference for part in fragments):
                continue
            if all(part in haystack or _fuzzy_contains(part, haystack) for part in fragments):
                continue
            seen.add(quote)
            findings.append({"quote": quote, "pages": cited})
    return findings


def moderation_reasons(
    primary_report: str,
    audit_report: str,
    coverage_warnings: list[str],
    visual_error: bool,
    visuals_without_source_images: bool,
    injection_review_required: bool = False,
    *,
    summary_used: bool = False,
    unverified_quote_reasons: Iterable[str] = (),
    assessment: AssessmentType = IA,
) -> list[str]:
    primary = extract_report_scores(primary_report, assessment)
    audited = extract_report_scores(audit_report, assessment)
    reasons = [
        f"{criterion}: primary {primary[criterion]}/{maximum}, audit {audited[criterion]}/{maximum}"
        for criterion, maximum in assessment.criteria
        if criterion in primary and criterion in audited and primary[criterion] != audited[criterion]
    ]
    expected = len(assessment.criteria)
    if len(primary) != expected or len(audited) != expected:
        reasons.append("A report is missing one or more criterion marks")
    reasons.extend(audit_mark_issues(primary_report, audit_report, assessment))
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
    if injection_review_required:
        reasons.append("Possible marker-directed instructions or unscreened visuals require teacher review")
    if summary_used:
        reasons.append(
            f"The {assessment.short_name} was summarised before marking, so the audit could not check the full text"
        )
    reasons.extend(unverified_quote_reasons)
    return reasons


def _audit_overstated_claims(audit_report: str, criterion: str) -> str:
    """Return the auditor's overstated-claims note for a criterion, unless it found none."""
    section = _criterion_section(audit_report, criterion) or ""
    match = re.search(
        r"^-\s*\*{0,2}Unsupported or overstated claims:\*{0,2}\s*(?P<body>.*?)(?=^-\s|\Z)",
        section,
        flags=re.IGNORECASE | re.MULTILINE | re.DOTALL,
    )
    if not match:
        return ""
    note = " ".join(match.group("body").split())
    if not note or re.match(r"[\"“]?none\b", note, re.IGNORECASE):
        return ""
    return note


def build_agreed_decision(
    primary_report: str, audit_report: str, assessment: AssessmentType = IA
) -> str:
    """Finalize only exact agreement after the evidence audit passes."""
    if moderation_reasons(primary_report, audit_report, [], False, False, assessment=assessment):
        raise ValueError("A moderated decision is required.")
    scores = extract_report_scores(primary_report, assessment)
    sections = []
    for criterion in assessment.names:
        match = re.search(
            rf"^###\s+{re.escape(criterion)}\b[^\n]*\n.*?(?=^#{2,3}\s|\Z)",
            primary_report,
            flags=re.IGNORECASE | re.MULTILINE | re.DOTALL,
        )
        if not match:
            raise ValueError(f"Missing {criterion} evidence section.")
        section = match.group(0).strip()
        audit_note = _audit_overstated_claims(audit_report, criterion)
        if audit_note:
            section += f"\n- **Audit note:** {audit_note}"
        sections.append(section)
    total = sum(scores.values())
    return (
        "## Final decision\n"
        f"- **Total:** {total}/{assessment.total}\n"
        f"- **Human review recommended:** no — the evidence audit confirmed all {assessment.count_word} marks and no extraction warning was detected.\n"
        "- **Decision route:** primary marks confirmed by evidence audit; no chief moderation was needed.\n\n"
        "## Criterion decisions\n\n"
        + "\n\n".join(sections)
        + f"\n\nReview the cited pages in the original {assessment.short_name} before using this recommendation."
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


def build_candidate_evidence_ledger(
    raw_text: str, per_criterion_limit: int = 8, assessment: AssessmentType = IA
) -> str:
    """Quote likely relevant student lines with source pages; make no inference or mark."""
    lines = [
        f"Candidate evidence excerpts from the student's {assessment.short_name} "
        "(untrusted; verify against the full page):"
    ]
    pages = split_pages(raw_text)
    for criterion, terms in assessment.evidence_terms:
        excerpts = []
        for page_number, page_text in pages:
            for line in page_text.splitlines()[1:]:
                excerpt = " ".join(line.split())
                if len(excerpt) < 12 or not re.search(terms, excerpt, flags=re.IGNORECASE):
                    continue
                excerpts.append(f"- Page {page_number}: {excerpt[:240]}")
        lines.append(f"## {criterion}")
        lines.extend(sample_evenly(excerpts, per_criterion_limit) or [f"- No keyword-matched excerpt found; inspect the full {assessment.short_name}."])
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
    assessment: AssessmentType = IA,
) -> dict[str, object]:
    """Export marks and run metadata without the student's work or report text."""
    return {
        "case_id": case_id,
        "assessment": assessment.key,
        "pipeline": assessment.pipeline,
        "model": model,
        "primary_marks": extract_report_scores(primary_report, assessment),
        "audit_marks": extract_report_scores(audit_report, assessment),
        "marks": extract_report_scores(final_report, assessment),
        "decision_mode": decision_mode,
        "escalation_reasons": escalation_reasons,
        "review_recommended": report_requests_human_review(final_report),
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


def extract_report_scores(report: str, assessment: AssessmentType = IA) -> dict[str, int]:
    """Extract final/awarded criterion marks from a generated Markdown report."""
    scores: dict[str, int] = {}
    for criterion, maximum in assessment.criteria:
        heading_mark = _heading_mark(report, criterion, maximum)
        if heading_mark is not None:
            scores[criterion] = heading_mark
            continue

        table_pattern = re.compile(
            rf"^\|\s*\**{re.escape(criterion)}\**\s*\|(?P<cells>.+)$",
            flags=re.IGNORECASE | re.MULTILINE,
        )
        table_match = table_pattern.search(report)
        if table_match:
            marks = []
            for cell in table_match.group("cells").split("|"):
                mark = _cell_mark(cell, maximum)
                if mark is not None:
                    marks.append(mark)
            if marks:
                # Moderator tables place the final mark after both examiner marks.
                scores[criterion] = marks[2] if len(marks) >= 3 else marks[0]
    return scores


SUGGESTIONS_PROMPT_FILE = "suggestions_prompt.md"
SUGGESTIONS_HEADING = "## Suggestions for improvement"


def suggestions_validation_issues(
    report: str, used_digest: bool, assessment: AssessmentType = IA
) -> list[str]:
    """Check the student-facing suggestions: one cited section per marked criterion, no marks."""
    if not report.strip():
        return ["The model returned no suggestions."]
    issues = []
    if not re.search(rf"^{re.escape(SUGGESTIONS_HEADING)}\s*$", report, flags=re.IGNORECASE | re.MULTILINE):
        issues.append(f"The suggestions need the heading '{SUGGESTIONS_HEADING}'.")
    missing = [name for name in assessment.names if _criterion_section(report, name) is None]
    if missing:
        issues.append("Missing suggestion sections: " + ", ".join(missing) + ".")
    elif not report_has_expected_citations(report, used_digest, assessment):
        issues.append("Each suggestion section needs a page or digest citation.")
    if any(_heading_mark(report, name, maximum) is not None for name, maximum in assessment.criteria):
        issues.append("Suggestions for the student must not state criterion marks.")
    return issues


EXAMINER_NOTES_PROMPT_FILE = "examiner_notes_prompt.md"
# Appended to the suggestions prompt only when annotated PDFs are requested.
STUDENT_NOTES_PROMPT_FILE = "student_notes_prompt.md"
MARGIN_NOTES_HEADING = "## Margin notes"
MAX_MARGIN_NOTES = 40
# A note for the student must not reveal marks, markbands or grades.
STUDENT_NOTE_MARK_PATTERN = re.compile(
    r"\b\d+\s*/\s*(?:4|6|8|24|26|30)\b|\bmark ?bands?\b|\bmarks?\b|\bgrades?\b", re.IGNORECASE
)


def split_margin_notes(
    report: str,
    page_count: int,
    assessment: AssessmentType = IA,
    *,
    for_student: bool = False,
) -> tuple[str, list[dict[str, object]], list[str]]:
    """Separate a report's "## Margin notes" JSON from its Markdown body.

    Returns the body, the usable notes ({page, quote, note, label}) and warnings about notes
    that were dropped. Invalid or missing JSON gives no notes rather than an error, because
    margin notes are an aid and never affect marks.
    """
    match = re.search(rf"^{re.escape(MARGIN_NOTES_HEADING)}\s*$", report, flags=re.IGNORECASE | re.MULTILINE)
    if not match:
        return report.strip(), [], ["No margin notes were returned."]
    body = report[: match.start()].strip()
    section = report[match.end():]
    fenced = re.search(r"```(?:json)?\s*(.*?)```", section, flags=re.DOTALL)
    raw = fenced.group(1) if fenced else section[section.find("["): section.rfind("]") + 1]
    try:
        items = json.loads(raw)
    except ValueError:
        return body, [], ["The margin notes could not be read."]
    if not isinstance(items, list):
        return body, [], ["The margin notes could not be read."]
    notes: list[dict[str, object]] = []
    dropped = {"page": 0, "marks": 0, "format": 0}
    for item in items:
        if not isinstance(item, dict):
            dropped["format"] += 1
            continue
        page, quote, note = item.get("page"), item.get("quote") or "", item.get("note")
        if type(page) is not int or not isinstance(quote, str) or not isinstance(note, str) or not note.strip():
            dropped["format"] += 1
            continue
        if not 1 <= page <= page_count:
            dropped["page"] += 1
            continue
        if for_student and STUDENT_NOTE_MARK_PATTERN.search(note):
            dropped["marks"] += 1
            continue
        label = item.get("criterion")
        notes.append(
            {
                "page": page,
                "quote": " ".join(quote.split())[:300],
                "note": " ".join(note.split())[:400],
                "label": label if label in assessment.names else "General",
            }
        )
    warnings = []
    if dropped["page"]:
        warnings.append(f"{dropped['page']} margin note(s) cited pages outside this PDF and were dropped.")
    if dropped["marks"]:
        warnings.append(f"{dropped['marks']} student margin note(s) mentioned marks and were dropped.")
    if dropped["format"]:
        warnings.append(f"{dropped['format']} margin note(s) were incomplete and were dropped.")
    if len(notes) > MAX_MARGIN_NOTES:
        warnings.append(f"Only the first {MAX_MARGIN_NOTES} margin notes are used.")
        notes = notes[:MAX_MARGIN_NOTES]
    return body, notes, warnings


def build_examiner_cover(
    assessment: AssessmentType,
    final_report: str,
    status_message: str,
) -> str:
    """First pages of the examiner's annotated PDF: marks, status, and the full final decision."""
    scores = extract_report_scores(final_report, assessment)
    lines = [f"# Examiner copy: IB DP Physics {assessment.short_name}"]
    if assessment.marking_notice:
        lines.append(f"> **Note:** {assessment.marking_notice}")
    lines += ["", "| Criterion | Mark | Maximum |", "|---|---:|---:|"]
    for criterion, maximum in assessment.criteria:
        mark = scores.get(criterion)
        lines.append(f"| {criterion} | {'—' if mark is None else mark} | {maximum} |")
    total = sum(scores.values()) if len(scores) == len(assessment.criteria) else "—"
    lines.append(f"| **Total** | **{total}** | **{assessment.total}** |")
    if status_message:
        lines += ["", status_message.replace("  \n", "\n\n")]
    lines += [
        "",
        "Numbered margin notes on the following pages show the evidence behind these marks. "
        "Notes marked “page note” could not be matched to the page's text; check them against the page.",
        "",
        "---",
        "",
        final_report.strip(),
    ]
    return "\n".join(lines)


def build_suggestions_document(report: str, assessment: AssessmentType = IA) -> str:
    """The separately downloadable, student-facing suggestions."""
    return (
        f"# IB DP Physics {assessment.short_name}: suggestions for improvement\n\n"
        "These suggestions are based on the draft you submitted. Page numbers refer to that PDF.\n\n"
        + report.strip()
        + "\n"
    )


def build_combined_report(
    examiner1_report: str,
    examiner2_report: str,
    moderator_report: str,
    assessment: AssessmentType = IA,
    suggestions_report: str = "",
) -> str:
    """Create a single downloadable Markdown bundle from completed reports."""
    sections = [f"# IB DP Physics {assessment.short_name} assessment bundle"]
    if assessment.marking_notice:
        sections[0] += f"\n\n> **Note:** {assessment.marking_notice}"
    for title, report in (
        ("Primary mark — Experimentalist" if assessment is IA else "Primary mark", examiner1_report),
        ("Evidence audit", examiner2_report),
        ("Final decision", moderator_report),
        ("Suggestions for improvement (for the student)", suggestions_report),
    ):
        if report.strip():
            sections.extend([f"## {title}", report.strip()])
    return "\n\n---\n\n".join(sections) + "\n"
