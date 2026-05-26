function estimateTokenCount(text) {
  return Math.ceil(String(text || "").length / 4);
}

function formatTimestamp(seconds) {
  const wholeSeconds = Math.max(0, Math.floor(Number(seconds) || 0));
  const hours = Math.floor(wholeSeconds / 3600);
  const minutes = Math.floor((wholeSeconds % 3600) / 60);
  const secs = wholeSeconds % 60;
  return [hours, minutes, secs].map((part) => String(part).padStart(2, "0")).join(":");
}

function cleanText(text) {
  return String(text || "")
    .replace(/\s+/g, " ")
    .replace(/\u00a0/g, " ")
    .trim();
}

function joinText(current, addition) {
  if (!current) {
    return addition;
  }
  if (!addition) {
    return current;
  }
  if (current.endsWith("-")) {
    return current + addition;
  }
  if (/^[,.;:!?)]/.test(addition)) {
    return current + addition;
  }
  return `${current} ${addition}`;
}

function pickFirstString(...values) {
  for (const value of values) {
    if (typeof value === "string" && value.trim()) {
      return value.trim();
    }
  }
  return "";
}

function pickFirstArray(...values) {
  for (const value of values) {
    if (Array.isArray(value)) {
      return value;
    }
  }
  return null;
}

function normalizeTranscriptInput(transcriptResult) {
  if (!transcriptResult || typeof transcriptResult !== "object") {
    throw new Error("Transcript input must be an object.");
  }

  const title = pickFirstString(
    transcriptResult.title,
    transcriptResult.videoTitle,
    transcriptResult.video && transcriptResult.video.title,
  );

  if (!title) {
    throw new Error("Transcript input must include a video title.");
  }

  const sourceUrl = pickFirstString(
    transcriptResult.url,
    transcriptResult.videoUrl,
    transcriptResult.canonicalUrl,
    transcriptResult.video && transcriptResult.video.url,
  );

  const rawSegments =
    pickFirstArray(
      transcriptResult.transcript,
      transcriptResult.segments,
      transcriptResult.entries,
      transcriptResult.items,
      transcriptResult.captions,
      transcriptResult.transcript && transcriptResult.transcript.segments,
    ) || [];

  let segments = rawSegments.map(normalizeSegment).filter(Boolean);

  if (!segments.length) {
    const rawText = pickFirstString(
      transcriptResult.transcriptText,
      transcriptResult.text,
      typeof transcriptResult.transcript === "string" ? transcriptResult.transcript : "",
    );

    if (!rawText) {
      throw new Error("Transcript input does not contain transcript segments or transcript text.");
    }

    segments = [{ text: cleanText(rawText), start: 0, duration: 0 }];
  }

  segments.sort((left, right) => left.start - right.start);

  return {
    sourceUrl,
    title,
    segments,
  };
}

function normalizeSegment(segment, index = 0) {
  if (typeof segment === "string") {
    const text = cleanText(segment);
    return text ? { text, start: index, duration: 0 } : null;
  }

  if (!segment || typeof segment !== "object") {
    return null;
  }

  const text = cleanText(segment.text || segment.snippet || segment.caption || "");
  if (!text) {
    return null;
  }

  const start = Number(
    segment.start ??
      segment.offset ??
      segment.startSeconds ??
      segment.start_time ??
      index,
  );
  const fallbackDuration =
    Number.isFinite(Number(segment.end)) && Number.isFinite(Number(segment.start))
      ? Number(segment.end) - Number(segment.start)
      : 0;
  const duration = Number(
    segment.duration ??
      segment.durationSeconds ??
      segment.length ??
      fallbackDuration,
  );

  return {
    text,
    start: Number.isFinite(start) ? start : index,
    duration: Number.isFinite(duration) ? duration : 0,
  };
}

const NOISE_PATTERNS = [
  /^\[(music|applause|laughter|silence|background music)\]$/i,
  /^\((music|applause|laughter|silence|background music)\)$/i,
];

const FILLER_ONLY_PATTERN =
  /^(uh|um|hmm|mm-hmm|mm|ah|er|you know|like|so|okay|ok|right|well)[.!?]*$/i;

function isLowSignalSegment(text) {
  if (!text) {
    return true;
  }
  if (NOISE_PATTERNS.some((pattern) => pattern.test(text))) {
    return true;
  }
  if (text.split(/\s+/).length <= 3 && FILLER_ONLY_PATTERN.test(text)) {
    return true;
  }
  return false;
}

function cleanTranscriptSegments(
  segments,
  {
    dropLowSignal = true,
    dedupeAdjacent = true,
  } = {},
) {
  const cleaned = [];
  let previousText = "";

  for (const segment of segments) {
    const text = cleanText(segment.text);
    if (!text) {
      continue;
    }
    if (dropLowSignal && isLowSignalSegment(text)) {
      continue;
    }
    if (dedupeAdjacent && text === previousText) {
      continue;
    }

    cleaned.push({
      duration: Math.max(0, Number(segment.duration) || 0),
      start: Math.max(0, Number(segment.start) || 0),
      text,
    });
    previousText = text;
  }

  return cleaned;
}

function buildCompactBlocks(
  segments,
  {
    maxBlockChars = 900,
    pauseThresholdSeconds = 8,
    timestampIntervalSeconds = 180,
    preserveTimestamps = true,
  } = {},
) {
  const blocks = [];
  let current = null;
  let previousEnd = null;
  let lastTimestampStart = Number.NEGATIVE_INFINITY;

  for (const segment of segments) {
    const end = segment.start + segment.duration;
    const pauseBreak =
      previousEnd !== null && segment.start - previousEnd >= pauseThresholdSeconds;
    const sizeBreak =
      current && current.text.length >= maxBlockChars;

    if (!current || pauseBreak || sizeBreak) {
      if (current && current.text) {
        blocks.push(current);
      }

      const shouldKeepTimestamp =
        preserveTimestamps &&
        (blocks.length === 0 ||
          segment.start - lastTimestampStart >= timestampIntervalSeconds);

      current = {
        start: segment.start,
        text: "",
        timestamp: shouldKeepTimestamp ? formatTimestamp(segment.start) : null,
      };

      if (shouldKeepTimestamp) {
        lastTimestampStart = segment.start;
      }
    }

    current.text = joinText(current.text, segment.text);
    previousEnd = end;
  }

  if (current && current.text) {
    blocks.push(current);
  }

  return blocks;
}

function blocksToCompactText(blocks) {
  return blocks
    .map((block) => (block.timestamp ? `[${block.timestamp}] ${block.text}` : block.text))
    .join("\n\n");
}

function chunkBlocks(blocks, maxChunkChars = 7000) {
  const chunks = [];
  let currentBlocks = [];
  let currentChars = 0;

  for (const block of blocks) {
    const blockText = block.timestamp ? `[${block.timestamp}] ${block.text}` : block.text;
    const projectedChars = currentChars === 0 ? blockText.length : currentChars + 2 + blockText.length;

    if (currentBlocks.length && projectedChars > maxChunkChars) {
      chunks.push({
        blocks: currentBlocks,
        estimatedTokens: estimateTokenCount(blocksToCompactText(currentBlocks)),
        text: blocksToCompactText(currentBlocks),
      });
      currentBlocks = [];
      currentChars = 0;
    }

    currentBlocks.push(block);
    currentChars = currentChars === 0 ? blockText.length : currentChars + 2 + blockText.length;
  }

  if (currentBlocks.length) {
    chunks.push({
      blocks: currentBlocks,
      estimatedTokens: estimateTokenCount(blocksToCompactText(currentBlocks)),
      text: blocksToCompactText(currentBlocks),
    });
  }

  return chunks;
}

function chunkTextItems(items, maxChunkChars = 7000) {
  const chunks = [];
  let current = [];
  let currentChars = 0;

  for (const item of items) {
    const value = String(item || "").trim();
    if (!value) {
      continue;
    }

    const projectedChars = currentChars === 0 ? value.length : currentChars + 2 + value.length;
    if (current.length && projectedChars > maxChunkChars) {
      chunks.push(current.join("\n\n"));
      current = [];
      currentChars = 0;
    }

    current.push(value);
    currentChars = currentChars === 0 ? value.length : currentChars + 2 + value.length;
  }

  if (current.length) {
    chunks.push(current.join("\n\n"));
  }

  return chunks;
}

module.exports = {
  blocksToCompactText,
  buildCompactBlocks,
  chunkBlocks,
  chunkTextItems,
  cleanTranscriptSegments,
  estimateTokenCount,
  formatTimestamp,
  normalizeTranscriptInput,
};
