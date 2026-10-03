Finally, add margin notes that will be printed beside the student's draft. Give 6–15 notes, each
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
