-- app/schema.sql
-- EchoSlice MVP schema (single-user, no auth)

CREATE TABLE IF NOT EXISTS clips (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  video_id TEXT NOT NULL,
  start_sec INTEGER NOT NULL,
  end_sec INTEGER NOT NULL,
  title TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS reviews (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  clip_id INTEGER NOT NULL,
  score INTEGER NOT NULL CHECK (score BETWEEN 1 AND 5),
  reviewed_at TEXT NOT NULL DEFAULT (datetime('now')),
  next_review_at TEXT NOT NULL,
  FOREIGN KEY (clip_id) REFERENCES clips(id)
);

CREATE INDEX IF NOT EXISTS idx_reviews_next_review_at ON reviews(next_review_at);
CREATE INDEX IF NOT EXISTS idx_reviews_clip_id ON reviews(clip_id);
