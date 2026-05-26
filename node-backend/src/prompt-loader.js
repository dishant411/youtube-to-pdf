const fs = require("fs/promises");
const path = require("path");

const { PROMPTS_DIR } = require("./config");

async function loadPromptTemplate(fileName) {
  const promptPath = path.join(PROMPTS_DIR, fileName);
  return fs.readFile(promptPath, "utf8");
}

function renderTemplate(template, variables) {
  return template.replace(/\{\{(\w+)\}\}/g, (_, key) => {
    const value = variables[key];
    return value === undefined || value === null ? "" : String(value);
  });
}

async function renderPromptFile(fileName, variables) {
  const template = await loadPromptTemplate(fileName);
  return renderTemplate(template, variables);
}

module.exports = {
  loadPromptTemplate,
  renderPromptFile,
  renderTemplate,
};
