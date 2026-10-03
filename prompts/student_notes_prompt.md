Finally, add margin notes that will be printed beside the student's draft. Give up to three notes per criterion, each
tied to a specific place a suggestion above refers to:
- `note`: one action in at most 25 words, starting with a verb, with no marks or markbands.
- `quote`: copied exactly, character for character, from the extracted text of that page:
  4–15 consecutive words, on one line where possible, with no ellipsis. Use an empty string for a
  note about a whole page or a visual with no quotable text.
- `criterion`: one of {criterion_list}, or "General".

## Margin notes
```json
[
  {{"page": 4, "quote": "exact words from page 4", "criterion": "...", "note": "Add ..."}}
]
```

Keep each comment to at most 40 words, with at most 20 words of source quotation.
Return at most three notes per criterion; do not pad. Use one observation and one clear action.
