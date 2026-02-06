# SEA News Smoke Checklist (<= 10 minutes)

## 1. Environment and startup (2 min)
- Run `python3 server/validate_env.py` and confirm `Validation passed`.
- Start backend and frontend:
  - `npm run dev:api`
  - `npm run dev -- --host 127.0.0.1 --port 5176 --strictPort`
- Open `http://127.0.0.1:5176`.

## 2. Auth flows (2 min)
- Login with account/password and confirm app shell loads.
- If Google OAuth is configured, test Google sign-in once.
- Refresh browser and confirm session is still valid.

## 3. Search UX defaults (2 min)
- Ensure `新搜尋覆蓋舊結果` is enabled (default).
- Send a news-search prompt without date range.
- Confirm old news/research documents are replaced (not stacked).

## 4. Result limit and recency (2 min)
- Set `結果上限` to a small number (e.g. `5`) and search again.
- Confirm output follows the cap intent and focuses on recent period.
- Change `預設期間` (e.g. `14` days) and repeat once.

## 5. User data isolation (2 min)
- Login as user A, generate or edit news/tags.
- Logout and login as user B.
- Confirm user B only sees its own news/tags set (or migrated legacy once), then switch back to user A and verify isolation.
