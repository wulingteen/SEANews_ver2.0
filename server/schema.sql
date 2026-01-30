-- server/schema.sql

CREATE TABLE IF NOT EXISTS news_records (
    id TEXT PRIMARY KEY,
    name TEXT,
    content TEXT,
    country TEXT,
    publish_date TEXT,
    url TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    types TEXT, -- Original 'type' field
    source TEXT,
    message TEXT,
    status TEXT,
    preview TEXT,
    tags TEXT, -- JSON array
    pages INTEGER
);

CREATE INDEX IF NOT EXISTS idx_country ON news_records(country);
CREATE INDEX IF NOT EXISTS idx_types ON news_records(types);
CREATE INDEX IF NOT EXISTS idx_created_at ON news_records(created_at);
