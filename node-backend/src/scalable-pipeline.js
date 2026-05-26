const path = require("path");

const { FileCache } = require("./cache");
const { DEFAULT_CACHE_DIR, resolveOutputDir } = require("./config");
const { slugify, uniqueFilePath } = require("./files");
const { createOpenAIClient, requestTextResponse } = require("./openai-client");
const { writeSummaryPdf } = require("./pdf-renderer");
const { renderPromptFile } = require("./prompt-loader");
const {
  buildCompactBlocks,
  chunkBlocks,
  chunkTextItems,
  cleanTranscriptSegments,
  estimateTokenCount,
  normalizeTranscriptInput,
} = require("./transcript-utils");

async function mapWithConcurrency(items, limit, iteratee) {
  const results = new Array(items.length);
  let index = 0;

  async function worker() {
    while (index < items.length) {
      const currentIndex = index;
      index += 1;
      results[currentIndex] = await iteratee(items[currentIndex], currentIndex);
    }
  }

  const workers = Array.from({ length: Math.max(1, Math.min(limit, items.length)) }, () => worker());
  await Promise.all(workers);
  return results;
}

async function summarizeWithPrompt(client, cache, promptFile, variables, options) {
  const prompt = await renderPromptFile(promptFile, variables);
  const cacheKey = {
    maxOutputTokens: options.maxOutputTokens,
    model: options.model,
    prompt,
  };

  if (cache) {
    const cached = await cache.get(cacheKey);
    if (cached) {
      return cached;
    }
  }

  const response = await requestTextResponse(client, {
    input: prompt,
    maxOutputTokens: options.maxOutputTokens,
    model: options.model,
    retries: options.retries,
  });

  if (cache) {
    await cache.set(cacheKey, response.text);
  }

  return response.text;
}

async function reduceChunkSummaries(client, cache, items, metadata, options) {
  let currentItems = items.slice();
  let pass = 0;

  while (currentItems.length > 1 || estimateTokenCount(currentItems.join("\n\n")) > options.finalInputTokenBudget) {
    pass += 1;
    const grouped = chunkTextItems(
      currentItems.map((item, index) => `## Reduced Chunk ${index + 1}\n${item}`),
      options.reductionChunkChars,
    );

    currentItems = await mapWithConcurrency(grouped, options.chunkConcurrency, async (groupText) =>
      summarizeWithPrompt(
        client,
        cache,
        "reduce-summary.md",
        {
          sourceUrl: metadata.sourceUrl || "unknown",
          transcriptText: groupText,
          videoTitle: metadata.title,
        },
        {
          maxOutputTokens: options.reductionMaxOutputTokens,
          model: options.model,
          retries: options.retries,
        },
      ),
    );

    if (pass > 8) {
      throw new Error("Reduction did not converge within 8 passes.");
    }
  }

  return currentItems.join("\n\n");
}

async function runScalablePipeline(transcriptResult, options = {}) {
  const normalized = normalizeTranscriptInput(transcriptResult);
  const cleanedSegments = cleanTranscriptSegments(normalized.segments, {
    dedupeAdjacent: options.dedupeAdjacent !== false,
    dropLowSignal: options.dropLowSignal !== false,
  });

  if (!cleanedSegments.length) {
    throw new Error("Transcript cleaning removed all transcript content.");
  }

  const blocks = buildCompactBlocks(cleanedSegments, {
    maxBlockChars: options.maxBlockChars || 900,
    pauseThresholdSeconds: options.pauseThresholdSeconds || 8,
    preserveTimestamps: options.preserveTimestamps !== false,
    timestampIntervalSeconds: options.timestampIntervalSeconds || 240,
  });

  const chunks = chunkBlocks(blocks, options.maxChunkChars || 6000);
  const client = createOpenAIClient();
  const model = options.model || process.env.OPENAI_MODEL || "gpt-5.4-nano";
  const cache =
    options.enableCache === false ? null : new FileCache(options.cacheDir || DEFAULT_CACHE_DIR);

  const chunkSummaries = await mapWithConcurrency(
    chunks,
    options.chunkConcurrency || 2,
    async (chunk, index) =>
      summarizeWithPrompt(
        client,
        cache,
        "chunk-summary.md",
        {
          chunkCount: chunks.length,
          chunkIndex: index + 1,
          sourceUrl: normalized.sourceUrl || "unknown",
          transcriptText: chunk.text,
          videoTitle: normalized.title,
        },
        {
          maxOutputTokens: options.chunkSummaryMaxOutputTokens || 260,
          model,
          retries: options.retries || 4,
        },
      ),
  );

  const reducedInput = await reduceChunkSummaries(
    client,
    cache,
    chunkSummaries,
    normalized,
    {
      chunkConcurrency: options.chunkConcurrency || 2,
      finalInputTokenBudget: options.finalInputTokenBudget || 2500,
      model,
      reductionChunkChars: options.reductionChunkChars || 7000,
      reductionMaxOutputTokens: options.reductionMaxOutputTokens || 500,
      retries: options.retries || 4,
    },
  );

  const finalText = await summarizeWithPrompt(
    client,
    cache,
    "reduce-summary.md",
    {
      sourceUrl: normalized.sourceUrl || "unknown",
      transcriptText: reducedInput,
      videoTitle: normalized.title,
    },
    {
      maxOutputTokens: options.finalSummaryMaxOutputTokens || 700,
      model,
      retries: options.retries || 4,
    },
  );

  const outputDir = resolveOutputDir(options.outputDir);
  const stem = slugify(normalized.title);
  const outputPath = await uniqueFilePath(outputDir, stem, "pdf");

  await writeSummaryPdf(outputPath, {
    generatedAt: new Date().toISOString(),
    model,
    sourceUrl: normalized.sourceUrl,
    summaryText: finalText,
    title: normalized.title,
  });

  return {
    chunks: chunks.length,
    cleanedSegmentCount: cleanedSegments.length,
    estimatedInputTokens: estimateTokenCount(blocks.map((block) => block.text).join(" ")),
    model,
    outputPath: path.resolve(outputPath),
    summaryText: finalText,
    title: normalized.title,
  };
}

module.exports = {
  runScalablePipeline,
};
