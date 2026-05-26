const fs = require("fs/promises");
const path = require("path");

const { marked } = require("marked");
const puppeteer = require("puppeteer");

function escapeHtml(value) {
  return String(value || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function buildDocumentHtml({
  generatedAt,
  model,
  sourceUrl,
  summaryText,
  title,
}) {
  const renderedSummary = marked.parse(String(summaryText || ""), {
    gfm: true,
  });

  const metadataRows = [
    sourceUrl
      ? `<div><span class="meta-label">Source</span><span class="meta-value">${escapeHtml(sourceUrl)}</span></div>`
      : "",
    `<div><span class="meta-label">Generated</span><span class="meta-value">${escapeHtml(generatedAt)}</span></div>`,
    `<div><span class="meta-label">Model</span><span class="meta-value">${escapeHtml(model)}</span></div>`,
  ]
    .filter(Boolean)
    .join("");

  return `<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <title>${escapeHtml(title)}</title>
    <style>
      @page {
        size: Letter;
        margin: 0.72in;
      }

      :root {
        color-scheme: light;
        --body: #1f2937;
        --muted: #667085;
        --heading: #101828;
        --border: #e4e7ec;
        --accent: #175cd3;
        --quote-bg: #f8fafc;
        --quote-border: #cbd5e1;
      }

      * {
        box-sizing: border-box;
      }

      html {
        -webkit-print-color-adjust: exact;
      }

      body {
        margin: 0;
        color: var(--body);
        font-family: "Helvetica Neue", Helvetica, Arial, sans-serif;
        font-size: 11pt;
        line-height: 1.65;
        text-rendering: optimizeLegibility;
      }

      .page {
        max-width: 7.1in;
        margin: 0 auto;
      }

      header {
        margin-bottom: 28px;
        padding-bottom: 18px;
        border-bottom: 1px solid var(--border);
      }

      h1.document-title {
        margin: 0 0 10px;
        color: var(--heading);
        font-size: 22pt;
        line-height: 1.18;
        letter-spacing: -0.02em;
      }

      .meta {
        display: grid;
        gap: 6px;
        font-size: 9pt;
        color: var(--muted);
      }

      .meta div {
        display: flex;
        gap: 8px;
        align-items: baseline;
        min-width: 0;
      }

      .meta-label {
        min-width: 64px;
        font-weight: 700;
        color: var(--heading);
      }

      .meta-value {
        overflow-wrap: anywhere;
      }

      main > :first-child {
        margin-top: 0;
      }

      h1, h2, h3 {
        color: var(--heading);
        page-break-after: avoid;
      }

      h1 {
        margin: 28px 0 12px;
        font-size: 18pt;
        line-height: 1.25;
      }

      h2 {
        margin: 22px 0 10px;
        font-size: 14pt;
        line-height: 1.3;
      }

      h3 {
        margin: 18px 0 8px;
        font-size: 12pt;
        line-height: 1.35;
      }

      p {
        margin: 0 0 12px;
      }

      ul, ol {
        margin: 0 0 14px;
        padding-left: 24px;
      }

      li {
        margin: 0 0 6px;
        padding-left: 4px;
      }

      li > ul,
      li > ol {
        margin-top: 6px;
        margin-bottom: 6px;
      }

      strong {
        color: var(--heading);
        font-weight: 700;
      }

      em {
        font-style: italic;
      }

      blockquote {
        margin: 16px 0;
        padding: 10px 14px;
        border-left: 3px solid var(--quote-border);
        background: var(--quote-bg);
        color: #344054;
      }

      blockquote > :last-child {
        margin-bottom: 0;
      }

      code {
        font-family: "SFMono-Regular", Menlo, Consolas, monospace;
        font-size: 0.92em;
        padding: 0.12em 0.35em;
        border-radius: 4px;
        background: #f5f7fa;
      }

      pre {
        margin: 16px 0;
        padding: 14px 16px;
        overflow-x: auto;
        border: 1px solid var(--border);
        border-radius: 8px;
        background: #f8fafc;
      }

      pre code {
        padding: 0;
        background: transparent;
      }

      hr {
        margin: 24px 0;
        border: 0;
        border-top: 1px solid var(--border);
      }

      a {
        color: var(--accent);
        text-decoration: none;
      }

      table {
        width: 100%;
        margin: 16px 0;
        border-collapse: collapse;
        font-size: 10pt;
      }

      th, td {
        padding: 8px 10px;
        border: 1px solid var(--border);
        vertical-align: top;
      }

      th {
        background: #f8fafc;
        color: var(--heading);
        text-align: left;
      }
    </style>
  </head>
  <body>
    <div class="page">
      <header>
        <h1 class="document-title">${escapeHtml(title)}</h1>
        <div class="meta">${metadataRows}</div>
      </header>
      <main>${renderedSummary}</main>
    </div>
  </body>
</html>`;
}

async function writeSummaryPdf(
  outputPath,
  {
    generatedAt,
    model,
    sourceUrl,
    summaryText,
    title,
  },
) {
  await fs.mkdir(path.dirname(outputPath), { recursive: true });

  const browser = await puppeteer.launch({
    headless: true,
    args: ["--no-sandbox", "--disable-setuid-sandbox"],
  });

  try {
    const page = await browser.newPage();
    await page.setContent(
      buildDocumentHtml({
        generatedAt,
        model,
        sourceUrl,
        summaryText,
        title,
      }),
      { waitUntil: "networkidle0" },
    );
    await page.pdf({
      path: outputPath,
      format: "Letter",
      margin: {
        top: "0.72in",
        right: "0.72in",
        bottom: "0.72in",
        left: "0.72in",
      },
      printBackground: true,
    });
  } finally {
    await browser.close();
  }
}

module.exports = {
  writeSummaryPdf,
};
