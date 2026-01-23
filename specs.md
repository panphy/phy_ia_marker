# Agentic Coding Specs

## Project overview
- **Purpose**: Grading/assessment tooling for physics IA (see `app.py`, `criteria/`, `prompts/`).
- **Primary entrypoint**: `app.py` (likely the main CLI/server runner).
- **Supporting modules**: `pdf_utils.py` for PDF/text handling; `tests/` for validation.
- **Coverage goal**: Ensure the system can account for all PDF content (text + visuals) and explicitly flag any unread content to avoid unfair marking.

## Repository layout
- `app.py`: top-level application wiring, orchestration, and I/O.
- `pdf_utils.py`: PDF parsing utilities.
- `criteria/`: rubric criteria used in scoring.
- `prompts/`: LLM prompt templates and system instructions.
- `tests/`: automated tests.

## Agent workflow expectations
1. **Read project context first**
   - Start with `README.md` for intent and usage.
   - Scan `app.py` to understand the execution path and data flow.
   - Check `prompts/` and `criteria/` to ensure scoring behavior is consistent.
2. **Make changes small and local**
   - Prefer targeted edits and avoid wide refactors unless requested.
   - Keep logic close to existing orchestration in `app.py`.
3. **Preserve behavior and outputs**
   - Any user-facing output or scoring changes should be intentional and documented.
   - Maintain compatibility with existing prompt formats.

## Coding conventions
- Use clear, explicit names aligned with existing style.
- Keep functions focused and side effects contained.
- Avoid adding new dependencies unless necessary.

## Testing guidance
- Run unit tests when altering core logic:
  - `pytest -q`
- For prompt or rubric changes, add/adjust tests under `tests/`.

## Common tasks
- **Update scoring/rubrics**: edit files in `criteria/` and ensure they are referenced in `app.py`.
- **Update prompts**: edit files in `prompts/` and confirm `app.py` loads the correct templates.
- **Improve PDF parsing**: update `pdf_utils.py` and add tests that exercise extraction.
- **Improve visual coverage**: update extraction + prompts to cover photos/diagrams/graphs/tables and report any missing content.

## Pull request checklist
- Summarize changes with affected modules and rationale.
- Note any output or scoring changes.
- Include tests run and results.

## Safety and quality
- Be cautious with any changes that affect grading or evaluation outcomes.
- Avoid leaking secrets or hardcoding API keys.
- Keep prompts and criteria auditable and versioned.
