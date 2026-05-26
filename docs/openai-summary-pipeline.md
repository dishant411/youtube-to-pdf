# OpenAI Summary Pipeline

## Cheapest practical architecture

The cost floor is reached by keeping OpenAI limited to one job: generating a concise executive summary from compact plain text. The backend should do everything else locally.

Flow:

1. Fetch transcript from YouTube on the backend.
2. Normalize transcript segments into `{ text, start, duration }`.
3. Remove empty lines, duplicate adjacent captions, and low-signal noise such as `[Music]`.
4. Merge nearby segments into short paragraph blocks.
5. Keep timestamps sparsely, for example every 3 to 4 minutes, instead of on every caption line.
6. Send only the cleaned transcript text plus the video title to OpenAI.
7. Receive Markdown or plain text summary.
8. Render that summary to PDF locally with backend code.
9. Save the PDF into `~/Documents/youtube-to-pdf/` by default.

Why this is cheap:

- No PDF bytes go to OpenAI.
- No HTML or Markdown-to-PDF generation is outsourced.
- Transcript cleanup shrinks token volume before the API call.
- Timestamps are sparse instead of attached to every segment.
- Long transcripts are chunked and reduced hierarchically instead of forcing one oversized request.

## Simple version

Use [`node-backend/src/simple-pipeline.js`](/Users/dishantpatel/Documents/Projects/youtubeToPdf/node-backend/src/simple-pipeline.js) when you want the lowest implementation complexity.

Behavior:

- Cleans and compacts transcript text.
- Uses one OpenAI call for short transcripts.
- For long transcripts, summarizes chunks sequentially and then performs one final reduction call.
- Writes the final summary PDF locally.

Good fit:

- Single-worker backend jobs
- Low throughput
- Minimal moving parts

## Scalable version

Use [`node-backend/src/scalable-pipeline.js`](/Users/dishantpatel/Documents/Projects/youtubeToPdf/node-backend/src/scalable-pipeline.js) when you expect longer videos or repeated processing.

Behavior:

- Performs the same cleanup and timestamp thinning.
- Summarizes transcript chunks with bounded concurrency.
- Recursively reduces chunk summaries until the final prompt stays compact.
- Caches chunk summaries locally to avoid paying again for identical chunk work.

Good fit:

- Longer videos
- Batch processing
- Re-runs on the same transcript set

## Transcript minimization rules

Implemented in [`node-backend/src/transcript-utils.js`](/Users/dishantpatel/Documents/Projects/youtubeToPdf/node-backend/src/transcript-utils.js):

- Collapse whitespace.
- Drop empty captions.
- Drop adjacent duplicate captions.
- Drop common noise markers such as `[Music]`.
- Drop tiny filler-only segments such as `um` or `okay`.
- Merge adjacent segments into larger blocks to reduce prompt overhead.
- Preserve timestamps only at a configurable interval.

Example compact transcript block:

```text
[00:00:00] In this video I will show a cheaper summarization pipeline.

The transcript is cleaned before any API call.

[00:03:00] Chunk summaries are combined into one executive summary.
```

## Prompt editing

Prompt templates are plain files:

- [`node-backend/prompts/executive-summary.md`](/Users/dishantpatel/Documents/Projects/youtubeToPdf/node-backend/prompts/executive-summary.md)
- [`node-backend/prompts/chunk-summary.md`](/Users/dishantpatel/Documents/Projects/youtubeToPdf/node-backend/prompts/chunk-summary.md)
- [`node-backend/prompts/reduce-summary.md`](/Users/dishantpatel/Documents/Projects/youtubeToPdf/node-backend/prompts/reduce-summary.md)

Edit those files directly when you want to change summary instructions without touching code.

## Usage

Install Node dependencies:

```bash
npm install
```

Set the backend API key:

```bash
export OPENAI_API_KEY=your_key_here
```

Optional overrides:

```bash
export OPENAI_MODEL=gpt-5.4-nano
export YOUTUBE_TO_PDF_OUTPUT_DIR="$HOME/Documents/youtube-to-pdf"
```

Run the simple pipeline:

```bash
npm run summarize:simple -- examples/transcript-input.example.json
```

Run the scalable pipeline:

```bash
npm run summarize:scalable -- examples/transcript-input.example.json --chunk-concurrency 2
```

## Input contract

The pipeline accepts JSON shaped like:

```json
{
  "title": "Video title",
  "url": "https://www.youtube.com/watch?v=...",
  "transcript": [
    { "text": "caption text", "start": 0, "duration": 4.2 }
  ]
}
```

Fallback fields are also accepted:

- `videoTitle`
- `videoUrl`
- `canonicalUrl`
- `segments`
- `entries`
- `items`
- `captions`
- `transcriptText`

## Cost controls already built in

- Backend-only `OPENAI_API_KEY`
- Local PDF generation only
- Sparse timestamp retention
- Plain text prompt payloads
- Retry handling for temporary API failures
- Chunking for long transcripts
- Optional local cache in `.cache/openai-summary/`
