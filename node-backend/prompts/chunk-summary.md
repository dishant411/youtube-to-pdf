You are compressing one chunk of a YouTube transcript before final executive summarization.

Return Markdown only.
Keep only the highest-value information.
Do not repeat boilerplate or hedge.

Use this structure:
## Chunk {{chunkIndex}} of {{chunkCount}}
1 sentence gist.
- 3 to 5 bullets with facts, claims, decisions, or recommendations.
- Include at most 2 timestamps if they materially help.

Video title: {{videoTitle}}
Source URL: {{sourceUrl}}

Transcript chunk:
{{transcriptText}}
