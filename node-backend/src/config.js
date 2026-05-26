const os = require("os");
const path = require("path");

const PROJECT_ROOT = path.resolve(__dirname, "..", "..");
const PROMPTS_DIR = path.join(PROJECT_ROOT, "node-backend", "prompts");
const DEFAULT_OUTPUT_DIR = path.join(os.homedir(), "Documents", "youtube-to-pdf");
const DEFAULT_CACHE_DIR = path.join(PROJECT_ROOT, ".cache", "openai-summary");

function resolveOutputDir(explicitOutputDir) {
  return path.resolve(
    explicitOutputDir || process.env.YOUTUBE_TO_PDF_OUTPUT_DIR || DEFAULT_OUTPUT_DIR,
  );
}

function getRequiredApiKey() {
  const apiKey = process.env.OPENAI_API_KEY;
  if (!apiKey) {
    throw new Error("OPENAI_API_KEY is required in the backend environment.");
  }
  return apiKey;
}

module.exports = {
  DEFAULT_CACHE_DIR,
  DEFAULT_OUTPUT_DIR,
  PROJECT_ROOT,
  PROMPTS_DIR,
  getRequiredApiKey,
  resolveOutputDir,
};
