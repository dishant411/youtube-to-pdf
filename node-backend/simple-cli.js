#!/usr/bin/env node

const { buildPipelineOptions, loadTranscriptInput, parseArgs } = require("./src/cli-utils");
const { runSimplePipeline } = require("./src/simple-pipeline");

async function main() {
  const { inputPath, options } = parseArgs(process.argv.slice(2));
  const transcriptInput = await loadTranscriptInput(inputPath);
  const result = await runSimplePipeline(transcriptInput, buildPipelineOptions(options));
  process.stdout.write(`${JSON.stringify(result, null, 2)}\n`);
}

main().catch((error) => {
  process.stderr.write(`${error.stack || error.message}\n`);
  process.exit(1);
});
