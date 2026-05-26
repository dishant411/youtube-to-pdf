const crypto = require("crypto");
const fs = require("fs/promises");
const path = require("path");

function slugify(value, maxLength = 80) {
  const normalized = String(value || "")
    .normalize("NFKD")
    .replace(/[^\x00-\x7F]/g, "")
    .toLowerCase()
    .replace(/[\/\\]/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/\s+/g, "-")
    .replace(/[^a-z0-9-]/g, "")
    .replace(/-{2,}/g, "-")
    .replace(/^-+|-+$/g, "");

  if (!normalized) {
    return "video-summary";
  }

  return normalized.slice(0, maxLength).replace(/-+$/g, "") || "video-summary";
}

async function ensureDir(dirPath) {
  await fs.mkdir(dirPath, { recursive: true });
}

async function uniqueFilePath(dirPath, stem, extension) {
  await ensureDir(dirPath);
  let attempt = 1;

  while (true) {
    const fileName = attempt === 1 ? `${stem}.${extension}` : `${stem}-${attempt}.${extension}`;
    const candidate = path.join(dirPath, fileName);

    try {
      await fs.access(candidate);
      attempt += 1;
    } catch (error) {
      return candidate;
    }
  }
}

function sha256(value) {
  return crypto.createHash("sha256").update(value).digest("hex");
}

module.exports = {
  ensureDir,
  sha256,
  slugify,
  uniqueFilePath,
};
