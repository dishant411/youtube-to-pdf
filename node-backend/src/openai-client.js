const OpenAI = require("openai");

const { getRequiredApiKey } = require("./config");

function createOpenAIClient() {
  return new OpenAI({ apiKey: getRequiredApiKey() });
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function isRetriable(error) {
  const status = error && (error.status || error.statusCode);
  return [408, 409, 429, 500, 502, 503, 504].includes(status);
}

async function withRetry(task, { retries = 4, baseDelayMs = 800 } = {}) {
  let attempt = 0;

  while (true) {
    try {
      return await task();
    } catch (error) {
      attempt += 1;
      if (attempt > retries || !isRetriable(error)) {
        throw error;
      }

      const jitter = Math.floor(Math.random() * 250);
      const delayMs = baseDelayMs * (2 ** (attempt - 1)) + jitter;
      await sleep(delayMs);
    }
  }
}

function extractResponseText(response) {
  if (response && typeof response.output_text === "string" && response.output_text.trim()) {
    return response.output_text.trim();
  }

  const parts = [];
  for (const item of response.output || []) {
    for (const content of item.content || []) {
      if (typeof content.text === "string" && content.text.trim()) {
        parts.push(content.text.trim());
      } else if (typeof content.value === "string" && content.value.trim()) {
        parts.push(content.value.trim());
      }
    }
  }

  if (!parts.length) {
    throw new Error("OpenAI response did not contain text output.");
  }

  return parts.join("\n\n").trim();
}

async function requestTextResponse(
  client,
  {
    input,
    maxOutputTokens = 900,
    model = process.env.OPENAI_MODEL || "gpt-5.4-nano",
    retries = 4,
  },
) {
  const response = await withRetry(
    () =>
      client.responses.create({
        input,
        max_output_tokens: maxOutputTokens,
        model,
      }),
    { retries },
  );

  return {
    model: response.model || model,
    raw: response,
    text: extractResponseText(response),
  };
}

module.exports = {
  createOpenAIClient,
  requestTextResponse,
  withRetry,
};
