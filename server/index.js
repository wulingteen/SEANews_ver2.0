import dotenv from 'dotenv';
import express from 'express';
import OpenAI from 'openai';
import { SYSTEM_PROMPT, buildDocContextPrompt } from './prompt_config.js';

// Always prefer .env values even if shell has an existing OPENAI_API_KEY
dotenv.config({ override: true });

const app = express();
const port = process.env.PORT || 8787;

app.use((req, res, next) => {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
  res.setHeader('Access-Control-Allow-Methods', 'GET,POST,OPTIONS');
  if (req.method === 'OPTIONS') {
    res.sendStatus(200);
    return;
  }
  next();
});

app.use(express.json({ limit: '4mb' }));


const buildDocContext = (documents = []) => {
  if (!documents.length) {
    return '文件清單: 無。';
  }

  const lines = documents.map((doc, index) => {
    const safeTags = Array.isArray(doc.tags) ? doc.tags.join('、') : '無';
    const content = typeof doc.content === 'string' && doc.content.trim()
      ? doc.content.trim().slice(0, 2000)
      : '未提供';

    return [
      `${index + 1}. 名稱: ${doc.name || '未命名'}`,
      `   類型: ${doc.type || '-'}`,
      `   頁數: ${doc.pages || '-'}`,
      `   標籤: ${safeTags}`,
      `   內容摘要: ${content}`,
    ].join('\n');
  });

  return `文件清單:\n${lines.join('\n')}`;
};

app.get('/api/health', (_req, res) => {
  res.json({ ok: true });
});

app.post('/api/artifacts', async (req, res) => {
  if (!process.env.OPENAI_API_KEY) {
    res.status(400).json({ error: 'Missing OPENAI_API_KEY' });
    return;
  }

  try {
    const { messages = [], documents = [] } = req.body || {};

    const trimmedMessages = Array.isArray(messages)
      ? messages
          .filter((item) => item && typeof item.content === 'string')
          .slice(-8)
          .map((item) => ({
            role: item.role === 'assistant' ? 'assistant' : 'user',
            content: item.content,
          }))
      : [];

    const docContext = buildDocContext(documents);

    const client = new OpenAI({ apiKey: process.env.OPENAI_API_KEY });
    const response = await client.chat.completions.create({
      model: process.env.OPENAI_MODEL || 'gpt-4o-mini',
      temperature: 0.2,
      response_format: { type: 'json_object' },
      messages: [
        { role: 'system', content: SYSTEM_PROMPT },
        ...trimmedMessages,
        {
          role: 'user',
          content: buildDocContextPrompt(docContext),
        },
      ],
    });

    const content = response.choices?.[0]?.message?.content || '{}';
    const json = JSON.parse(content);

    res.json(json);
  } catch (error) {
    res.status(500).json({
      error: 'LLM request failed',
      detail: error instanceof Error ? error.message : 'Unknown error',
    });
  }
});

app.listen(port, () => {
  console.log(`API server listening on http://localhost:${port}`);
});
