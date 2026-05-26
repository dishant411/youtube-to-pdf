const path = require("path");

const { resolveOutputDir } = require("./config");
const { slugify, uniqueFilePath } = require("./files");
const { createOpenAIClient, requestTextResponse } = require("./openai-client");
const { writeSummaryPdf } = require("./pdf-renderer");
const { renderPromptFile } = require("./prompt-loader");
const {
  buildCompactBlocks,
  chunkBlocks,
  cleanTranscriptSegments,
  estimateTokenCount,
  normalizeTranscriptInput,
} = require("./transcript-utils");

async function summarizeChunk(client, options) {
  const prompt = await renderPromptFile("chunk-summary.md", options);
  return requestTextResponse(client, {
    input: prompt,
    maxOutputTokens: options.maxOutputTokens || 280,
    model: options.model,
    retries: options.retries,
  });
}

async function summarizeFinal(client, options, promptFileName) {
  const prompt = await renderPromptFile(promptFileName, options);
  return requestTextResponse(client, {
    input: prompt,
    maxOutputTokens: options.maxOutputTokens || 700,
    model: options.model,
    retries: options.retries,
  });
}

async function runSimplePipeline(transcriptResult, options = {}) {
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
    timestampIntervalSeconds: options.timestampIntervalSeconds || 180,
  });

  const chunks = chunkBlocks(blocks, options.maxChunkChars || 7000);
  const client = createOpenAIClient();
  const model = options.model || process.env.OPENAI_MODEL || "gpt-5.4-nano";

  let finalInputText = chunks[0].text;
  let chunkSummaries = [];

  if (chunks.length > 1) {
    for (let index = 0; index < chunks.length; index += 1) {
      const result = await summarizeChunk(client, {
        chunkCount: chunks.length,
        chunkIndex: index + 1,
        maxOutputTokens: options.chunkSummaryMaxOutputTokens || 280,
        model,
        retries: options.retries || 4,
        sourceUrl: normalized.sourceUrl || "unknown",
        transcriptText: chunks[index].text,
        videoTitle: normalized.title,
      });
      chunkSummaries.push(result.text);
    }

    finalInputText = chunkSummaries
      .map((summary, index) => `## Chunk ${index + 1}\n${summary}`)
      .join("\n\n");
  }

  const finalResult = await summarizeFinal(
    client,
    {
      maxOutputTokens: options.finalSummaryMaxOutputTokens || 700,
      model,
      retries: options.retries || 4,
      sourceUrl: normalized.sourceUrl || "unknown",
      timestampGuidance:
        options.preserveTimestamps === false
          ? "No timestamps are included."
          : "Use timestamps only when they help the reader jump to a material moment.",
      transcriptText: finalInputText,
      videoTitle: normalized.title,
    },
    chunks.length > 1 ? "reduce-summary.md" : "executive-summary.md",
  );

  const outputDir = resolveOutputDir(options.outputDir);
  const stem = slugify(normalized.title);
  const outputPath = await uniqueFilePath(outputDir, stem, "pdf");

  await writeSummaryPdf(outputPath, {
    generatedAt: new Date().toISOString(),
    model: finalResult.model,
    sourceUrl: normalized.sourceUrl,
    summaryText: finalResult.text,
    title: normalized.title,
  });

  return {
    chunks: chunks.length,
    cleanedSegmentCount: cleanedSegments.length,
    estimatedInputTokens: estimateTokenCount(blocks.map((block) => block.text).join(" ")),
    model: finalResult.model,
    outputPath: path.resolve(outputPath),
    summaryText: finalResult.text,
    title: normalized.title,
  };
}

module.exports = {
  runSimplePipeline,
};
