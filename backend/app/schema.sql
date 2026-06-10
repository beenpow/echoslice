-- app/schema.sql
-- EchoSlice MVP schema (single-user, no auth)

CREATE TABLE IF NOT EXISTS clips (
  id SERIAL PRIMARY KEY,
  video_id TEXT NOT NULL,
  start_sec REAL NOT NULL,
  end_sec REAL NOT NULL,
  title TEXT,
  talk_slug TEXT,
  source TEXT NOT NULL DEFAULT 'unknown',
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS reviews (
  id SERIAL PRIMARY KEY,
  clip_id INTEGER NOT NULL,
  score INTEGER NOT NULL CHECK (score BETWEEN 1 AND 5),
  reviewed_at TEXT NOT NULL,
  next_review_at TEXT NOT NULL,
  FOREIGN KEY (clip_id) REFERENCES clips(id)
);

CREATE TABLE IF NOT EXISTS today_queue (
  day TEXT NOT NULL,
  position INTEGER NOT NULL,
  clip_id INTEGER NOT NULL,
  kind TEXT NOT NULL CHECK (kind IN ('review','new')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (day, position),
  FOREIGN KEY (clip_id) REFERENCES clips(id)
);

CREATE TABLE IF NOT EXISTS gemini_calls (
  id SERIAL PRIMARY KEY,
  reason TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_gemini_calls_created_at ON gemini_calls(created_at);
CREATE INDEX IF NOT EXISTS idx_today_queue_day ON today_queue(day);
CREATE INDEX IF NOT EXISTS idx_reviews_next_review_at ON reviews(next_review_at);
CREATE INDEX IF NOT EXISTS idx_reviews_clip_id ON reviews(clip_id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_clips_video_time ON clips(video_id, start_sec, end_sec);

CREATE TABLE IF NOT EXISTS bad_slugs (
  slug TEXT PRIMARY KEY,
  reason TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_bad_slugs_created_at ON bad_slugs(created_at);

CREATE TABLE IF NOT EXISTS timeslicer_state (
  key TEXT PRIMARY KEY,
  state_json TEXT NOT NULL,
  updated_at TEXT NOT NULL
)
