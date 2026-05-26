const fs = require("fs/promises");
const path = require("path");

function parseArgs(argv) {
  const args = {
    inputPath: null,
    options: {},
  };

  for (let index = 0; index < argv.length; index += 1) {
    const token = argv[index];
    if (!token.startsWith("--") && !args.inputPath) {
      args.inputPath = token;
      continue;
    }

    if (!token.startsWith("--")) {
      throw new Error(`Unexpected argument: ${token}`);
    }

    const key = token.slice(2);
    const next = argv[index + 1];

    if (next && !next.startsWith("--")) {
      args.options[key] = next;
      index += 1;
    } else {
      args.options[key] = true;
    }
  }

  if (!args.inputPath) {
    throw new Error("Usage: node <script> <transcript.json> [--output-dir <dir>] [--model <model>]");
  }

  return args;
}

async function loadTranscriptInput(inputPath) {
  const absolutePath = path.resolve(inputPath);
  const raw = await fs.readFile(absolutePath, "utf8");
  return JSON.parse(raw);
}

function coerceNumber(value, fallback) {
  if (value === undefined || value === null) {
    return fallback;
  }
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : fallback;
}

function buildPipelineOptions(cliOptions) {
  return {
    cacheDir: cliOptions["cache-dir"],
    chunkConcurrency: coerceNumber(cliOptions["chunk-concurrency"], undefined),
    finalInputTokenBudget: coerceNumber(cliOptions["final-input-token-budget"], undefined),
    finalSummaryMaxOutputTokens: coerceNumber(
      cliOptions["final-summary-max-output-tokens"],
      undefined,
    ),
    maxBlockChars: coerceNumber(cliOptions["max-block-chars"], undefined),
    maxChunkChars: coerceNumber(cliOptions["max-chunk-chars"], undefined),
    model: cliOptions.model,
    outputDir: cliOptions["output-dir"],
    pauseThresholdSeconds: coerceNumber(cliOptions["pause-threshold-seconds"], undefined),
    preserveTimestamps: cliOptions["no-timestamps"] ? false : undefined,
    retries: coerceNumber(cliOptions.retries, undefined),
    timestampIntervalSeconds: coerceNumber(
      cliOptions["timestamp-interval-seconds"],
      undefined,
    ),
  };
}

module.exports = {
  buildPipelineOptions,
  loadTranscriptInput,
  parseArgs,
};
