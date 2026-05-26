const fs = require("fs/promises");
const path = require("path");

const { ensureDir, sha256 } = require("./files");

class FileCache {
  constructor(cacheDir) {
    this.cacheDir = cacheDir;
  }

  async get(keyParts) {
    const key = sha256(JSON.stringify(keyParts));
    const filePath = path.join(this.cacheDir, `${key}.txt`);

    try {
      return await fs.readFile(filePath, "utf8");
    } catch (error) {
      return null;
    }
  }

  async set(keyParts, value) {
    const key = sha256(JSON.stringify(keyParts));
    const filePath = path.join(this.cacheDir, `${key}.txt`);
    await ensureDir(this.cacheDir);
    await fs.writeFile(filePath, value, "utf8");
  }
}

module.exports = {
  FileCache,
};
