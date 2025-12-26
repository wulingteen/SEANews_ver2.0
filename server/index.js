import dotenv from 'dotenv';
import express from 'express';
import OpenAI from 'openai';

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

const systemPrompt = `你是企業金融 RM 的授信報告助理。你的任務是根據對話與文件清單，產出三個 artifacts：摘要、翻譯、授信報告草稿。

輸出規則：
1) 回傳內容必須是嚴格 JSON，不要額外說明或 Markdown code fence。
2) summary.output 與 memo.output 使用繁體中文；translation.output 與 translation.clauses[].translated 使用英文。
3) summary.risks[].level 必須是 High、Medium、Low。
4) routing[].status 必須是 running、queued、done。
5) 若文件內容不足，請明確註記「內容不足，需補充」。
6) 請控制每個陣列 3-6 個項目，避免過長。

JSON 格式：
{
  "assistant": { "content": "...", "bullets": ["...", "..."] },
  "summary": {
    "output": "...",
    "borrower": { "name": "...", "description": "...", "rating": "..." },
    "metrics": [{ "label": "...", "value": "...", "delta": "..." }],
    "risks": [{ "label": "...", "level": "High" }]
  },
  "translation": {
    "output": "...",
    "clauses": [{ "section": "...", "source": "...", "translated": "..." }]
  },
  "memo": {
    "output": "...",
    "sections": [{ "title": "...", "detail": "..." }],
    "recommendation": "...",
    "conditions": "..."
  },
  "routing": [{ "label": "...", "status": "queued", "eta": "..." }]
}`;

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
        { role: 'system', content: systemPrompt },
        ...trimmedMessages,
        {
          role: 'user',
          content: `以下是最新文件清單與可用內容，請依照對話需求產出 artifacts。\n\n${docContext}`,
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
