"""Validated assessment records and concise, source-anchored feedback.

Matching an excerpt proves its location, not the truth of a model's interpretation.
The evidence auditor and human calibration remain necessary.
"""
import json
import re
from copy import deepcopy

from app_utils import CRITERION_NAMES, split_pages

ANNOTATION_WORD_LIMIT = 40
MAX_ANNOTATIONS_PER_CRITERION = 3
KINDS = ('credit', 'limitation', 'advice', 'check')

RECORD_INSTRUCTIONS = '''
# Output contract (replaces the Markdown output format above)
Return a single JSON object, no fences. Do not produce totals or Markdown tables.
Use exactly this shape:
{"review_required": false, "review_reasons": [], "escalation_required": false,
 "visual_checks": [],
 "criteria": [{"name": "Research design", "mark": 4,
 "best_fit": "Rubric-linked best-fit explanation, at most 60 words",
 "within_band": "Why this mark within the band, at most 35 words",
 "why_not_higher": "Decisive reason, at most 35 words; at 6 say Maximum mark achieved.",
 "evidence_ids": [1],
 "annotations": [{"kind": "credit", "page": 1,
 "quote": "Exact short contiguous excerpt from supplied original page text",
 "visual_id": "", "observation": "One precise observation",
 "consequence": "Brief criterion consequence", "action": "One clear action, or empty for credit"}]}]}
For EACH directly supplied visual include a visual_checks entry with visual_id,
status (readable, unreadable, or not_needed), and a reason of at most 20 words.
Use unreadable if the relevant detail cannot be read; this always requires human review.
not_needed means inspected and irrelevant to the marking decision, never assumed decorative.
Include exactly the four rubric criteria, in rubric order. Marks are integers 0 through 6.
Annotations: at most THREE per criterion; do not pad. observation + consequence + action
must total at most 40 words. Quote at most 20 words and at least 8 characters, excluding page markers.
Kinds: credit (supports credit), limitation (affects mark), advice (optional enrichment,
NOT a reason to withhold marks), check (teacher must verify uncertain or missing evidence).
Each annotation must reference a PDF page. For text, copy an exact excerpt from ORIGINAL
PAGE TEXT, never from the navigation digest. For a visual use its exact supplied visual_id,
leave quote empty, and cite its page. Never invent coordinates or quote graph text from memory.
For a check only, quote and visual_id may both be empty; give a specific location to inspect.
Use one-based evidence_ids to link all criterion reasoning to its supporting annotations.
Any check means review_required=true with a specific unresolved source check in review_reasons.
Do not convert a source gap into a student weakness. Mark-limiting claims require verified
source evidence; where it cannot be verified, give a provisional best-fit mark and a check.
An annotation's quote must actually support the observation, not just share a keyword.
The auditor must verify every annotation and reasoning claim, including missed strengths;
return corrected, self-contained feedback, not copied unsupported claims. Set escalation_required
for any changed mark, changed material claim, or unresolved issue. The moderator must reconcile
claims in best_fit using sources, and preserve unresolved checks. At 6/6 use
"Maximum mark achieved." and offer enrichment only if useful; do not invent a shortcoming.
Do not force three improvements. Do not write model confidence percentages.
'''


def normalized(text: str) -> str:
    return ' '.join(text.split())


def parse_record(raw: str, source_text: str, source_images: list, page_count: int) -> dict:
    """Fail closed on malformed marks, long comments and unsupported source locations."""
    try:
        record = json.loads(raw)
    except (ValueError, TypeError) as exc:
        raise ValueError('Assessment must be a JSON object.') from exc
    if not isinstance(record, dict):
        raise ValueError('Assessment must be a JSON object.')
    for field in ('review_required', 'escalation_required'):
        if type(record.get(field)) is not bool:
            raise ValueError(f'{field} must be a Boolean.')
    reasons = record.get('review_reasons')
    if not isinstance(reasons, list) or any(not isinstance(x, str) or not x.strip() for x in reasons):
        raise ValueError('Review reasons must be nonempty strings.')
    if record['review_required'] and not reasons:
        raise ValueError('Human review needs a specific reason.')
    pages = {number: normalized(text.split('\n', 1)[-1]) for number, text in split_pages(source_text)}
    images = {visual_id(image): image.page_number for image in source_images}
    checks = record.get('visual_checks', [])
    if not isinstance(checks, list) or any(not isinstance(c, dict) for c in checks):
        raise ValueError('Visual checks must be a list.')
    if any(not isinstance(c.get('visual_id'), str) for c in checks):
        raise ValueError('Visual IDs must be strings.')
    if len(checks) != len(images) or {c.get('visual_id') for c in checks} != set(images):
        raise ValueError('Every supplied visual needs exactly one readability check.')
    for check in checks:
        if check.get('status') not in ('readable', 'unreadable', 'not_needed'):
            raise ValueError('Invalid visual readability status.')
        if not isinstance(check.get('reason'), str) or not 1 <= len(check['reason'].split()) <= 20:
            raise ValueError('A visual check needs a concise reason of 1–20 words.')
        if check['status'] == 'unreadable':
            reasons.append(f"{check['visual_id']}: {check['reason']}")
    record['visual_checks'] = checks
    visual_status = {c['visual_id']: c['status'] for c in checks}
    criteria = record.get('criteria')
    if not isinstance(criteria, list) or len(criteria) != 4 or any(not isinstance(c, dict) for c in criteria):
        raise ValueError('Exactly four criterion records are required.')
    if [c.get('name') for c in criteria] != list(CRITERION_NAMES):
        raise ValueError('Criterion names or order are invalid.')
    for criterion in criteria:
        mark = criterion.get('mark')
        if type(mark) is not int or not 0 <= mark <= 6:
            raise ValueError('Marks must be integers from 0 to 6.')
        for field, limit in (('best_fit', 60), ('within_band', 35), ('why_not_higher', 35)):
            value = criterion.get(field)
            if not isinstance(value, str) or not value.strip() or len(value.split()) > limit:
                raise ValueError(f'{criterion["name"]}: {field} must contain 1–{limit} words.')
        criterion['band'] = '0' if mark == 0 else ('1–2' if mark <= 2 else '3–4' if mark <= 4 else '5–6')
        if mark == 6:
            criterion['why_not_higher'] = 'Maximum mark achieved.'
        annotations = criterion.get('annotations')
        if not isinstance(annotations, list) or not 1 <= len(annotations) <= MAX_ANNOTATIONS_PER_CRITERION:
            raise ValueError('Each criterion needs 1–3 concise source annotations.')
        ids = criterion.get('evidence_ids')
        if not isinstance(ids, list) or not ids or any(type(i) is not int or not 1 <= i <= len(annotations) for i in ids):
            raise ValueError('Criterion reasoning needs valid annotation references.')
        for a in annotations:
            if not isinstance(a, dict) or a.get('kind') not in KINDS:
                raise ValueError('Unknown annotation kind.')
            page = a.get('page')
            if type(page) is not int or not 1 <= page <= page_count:
                raise ValueError('Annotation page is outside the PDF.')
            for field in ('quote', 'visual_id', 'observation', 'consequence', 'action'):
                if not isinstance(a.get(field), str):
                    raise ValueError(f'Annotation {field} must be text.')
            if not a['observation'].strip() or not a['consequence'].strip():
                raise ValueError('Annotations need an observation and criterion consequence.')
            if a['kind'] != 'credit' and not a['action'].strip():
                raise ValueError('Limitations, advice and checks need a clear next action.')
            if len(annotation_comment(a).split()) > ANNOTATION_WORD_LIMIT:
                raise ValueError('Annotation exceeds the 40-word limit; shorten it, do not truncate.')
            quote = normalized(a['quote'])
            if len(quote.split()) > 20:
                raise ValueError('Quote exceeds 20 words.')
            if quote and (len(quote) < 8 or quote not in pages.get(page, '')):
                raise ValueError(f'Annotation quote not found in supplied original Page {page}.')
            if a['visual_id'] and images.get(a['visual_id']) != page:
                raise ValueError('Annotation visual was not supplied on the cited page.')
            if a['kind'] != 'check' and a['visual_id'] and visual_status[a['visual_id']] != 'readable':
                raise ValueError('An unreadable or irrelevant visual cannot support a material claim.')
            if a['kind'] != 'check' and not (quote or a['visual_id']):
                raise ValueError('Material annotations require an exact quote or supplied visual.')
            if a['kind'] == 'check':
                record['review_required'] = True
                reason = f'Page {page}: {a["observation"]}'
                if reason not in reasons:
                    reasons.append(reason)
        if all(a['kind'] in ('advice', 'check') for a in annotations):
            record['review_required'] = True
            reasons.append(f'{criterion["name"]}: insufficient verified evidence for the mark.')
    if reasons:
        record['review_required'] = True
    record['total'] = sum(c['mark'] for c in criteria)
    record['schema_version'] = 2
    return record


def visual_id(image) -> str:
    return f'p{image.page_number}:{image.name}'


def annotation_comment(annotation: dict) -> str:
    return ' '.join(annotation[key].strip() for key in ('observation', 'consequence', 'action') if annotation[key].strip())


def enforce_review(record: dict, reasons: list[str]) -> dict:
    record = deepcopy(record)
    record['review_reasons'] = list(dict.fromkeys(record['review_reasons'] + reasons))
    record['review_required'] = record['review_required'] or bool(record['review_reasons'])
    return record


def safe_markdown(text: str) -> str:
    # Model/student text is displayed as text, not active links, HTML or headings.
    return re.sub(r'([\\`*_{}\[\]<>()#!|])', r'\\\1', normalized(text))


def render_record(record: dict, stage: str) -> str:
    review = record['review_required']
    title = 'Provisional decision' if review and stage == 'Final decision' else stage
    lines = [f'## {title}', f'- **Total:** {sum(c["mark"] for c in record["criteria"])}/24',
             f'- **Human review recommended:** {"yes" if review else "no"} — ' +
             (safe_markdown('; '.join(record['review_reasons'])) if review else 'Review cited sources before using the marks.')]
    if stage == 'Evidence audit':
        lines.append(f'- **Escalation required:** {"yes" if record["escalation_required"] or review else "no"}')
    for c in record['criteria']:
        cited = sorted({c['annotations'][i - 1]['page'] for i in c['evidence_ids']})
        refs = ', '.join(f'Page {p}' for p in cited)
        lines += ['', f'### {c["name"]} — {c["mark"]}/6',
                  f'- **Best-fit decision:** Band {c["band"]}. {safe_markdown(c["best_fit"])} ({refs})',
                  f'- **Within-band decision:** {safe_markdown(c["within_band"])} ({refs})',
                  f'- **Why not higher:** {safe_markdown(c["why_not_higher"])} ({refs})']
        for a in c['annotations']:
            quote = f' “{safe_markdown(a["quote"])}” —' if a['quote'] else ''
            lines.append(f'- **{a["kind"].title()} · Page {a["page"]}:**{quote} {safe_markdown(annotation_comment(a))}')
    return '\n'.join(lines)


def missing_visuals(visuals: list, images: list) -> list:
    supplied = {visual_id(image) for image in images}
    # A rendered vector visual is the complete page, including embedded images.
    full_pages = {v.page_number for v in visuals if v.kind == 'vector' and visual_id(v) in supplied}
    full_pages.update(image.page_number for image in images if getattr(image, 'covers_page', False))
    return [v for v in visuals if v.page_number not in full_pages and visual_id(v) not in supplied]


def rank_visuals(visuals: list) -> list:
    """Prefer data and calculation evidence; captions are hints, never proof."""
    def priority(v):
        caption = ' '.join(v.captions).lower()
        score = 0
        if re.search(r'table|graph|plot|uncertaint|regress|fit|calculation|data', caption):
            score += 4
        if re.search(r'apparatus|setup|set-up|circuit|diagram', caption):
            score += 2
        if v.kind == 'vector':
            score += 1
        return (-score, v.page_number, v.name)
    return sorted(visuals, key=priority)


def original_page_selection(raw_text: str, requested: list[int], budget: int = 150_000) -> tuple[str, list[int]]:
    """Whole original pages only; omitted pages remain explicit review gaps."""
    pages = dict(split_pages(raw_text))
    if any(type(p) is not int or p not in pages for p in requested):
        raise ValueError('Requested source page is outside the PDF.')
    ordered = list(dict.fromkeys(requested))
    selected, size = [], 0
    for number in ordered:
        page = pages[number]
        if size + len(page) > budget:
            continue
        selected.append(number)
        size += len(page)
    return '\n\n'.join(pages[p] for p in selected), sorted(set(pages) - set(selected))
