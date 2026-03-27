import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const promptPath = path.join(__dirname, 'prompts.json');
const prompts = JSON.parse(fs.readFileSync(promptPath, 'utf-8'));

export const SYSTEM_PROMPT = prompts.SYSTEM_PROMPT;

export const buildDocContextPrompt = (docContext) => (
  prompts.DOC_CONTEXT_PROMPT_TEMPLATE.replace('{docContext}', docContext)
);
