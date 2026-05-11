---
name: transcript-timestamp-lyric-extractor
description: Extract timestamp and lyric pairs from YouTube transcript-style HTML using specific div/span tags.
---

# Skill: Timestamp + Lyric Extraction from Transcript HTML

## Purpose
Extract only:
1. The timestamp text inside:
   `<div aria-hidden="true" class="ytwTranscriptSegmentViewModelTimestamp">...</div>`
2. The lyric text inside:
   `<span class="ytAttributedStringHost ytAttributedStringLinkInheritColor" role="text" style="">...</span>`

Return each result as one pair in source order.

## Expected Input
- An HTML file that contains repeated transcript segments with:
  - timestamp div
  - accessibility label div (optional to keep in pattern)
  - lyric span

Example file path:
- `resources/speed_of_sound.html`

## Extraction Rules
1. Preserve original ordering from the HTML.
2. Match each timestamp with the next corresponding lyric span in the same segment block.
3. Normalize lyric whitespace to single spaces.
4. Trim leading/trailing whitespace in both fields.
5. Output format:
   - `timestamp<TAB>lyric`

## PowerShell Command (Reference Implementation)
```powershell
$content = Get-Content -Raw 'resources/speed_of_sound.html'
$pattern = '<div aria-hidden="true" class="ytwTranscriptSegmentViewModelTimestamp">(.*?)</div>\s*<div class="ytwTranscriptSegmentViewModelTimestampA11yLabel">.*?</div>\s*<span class="ytAttributedStringHost ytAttributedStringLinkInheritColor" role="text" style="">(.*?)</span>'

[regex]::Matches($content, $pattern, [System.Text.RegularExpressions.RegexOptions]::Singleline) |
ForEach-Object {
  $ts = $_.Groups[1].Value.Trim()
  $ly = ($_.Groups[2].Value -replace '\s+', ' ').Trim()
  "$ts`t$ly"
}
```

## Validation Checklist
- The match count equals the number of expected transcript lines.
- First and last pairs look correct.
- No HTML tags remain in extracted lyric output.
- No extra spaces/newlines remain inside lyrics.

## Notes
- This skill is intentionally strict to the current tag/class attributes.
- If the source HTML changes classes or structure, update the regex accordingly.
