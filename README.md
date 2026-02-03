# EchoSlice

Dev planning notes.

## Stack

- React + TypeScript (frontend)
- FastAPI (backend)
- YouTube IFrame Player API for segment playback
- YouTube Data API v3 for search and metadata
- LLM only for recommendation/ranking (no training or fine-tuning)

---

## MVP scope

Sticking to these four. Everything else later.

1. **Clip playback** – Play a segment of a YouTube video by start/end. Loop on/off, one-click replay for speaking practice.
2. **Clip storage & library** – Save clips (URL + start/end), list and replay them.
3. **Today / review (spaced repetition)** – Show clips due today, mark Hard/OK/Easy, auto-update next review date.
4. **AI discovery (minimal)** – Recommend ~3 candidate videos by topic/difficulty. No automatic sentence extraction in MVP.

---

## Data model (draft)

**Clips**: id, video_id, title, start_sec, end_sec, topic, created_at  
**Review Items**: id, clip_id, due_date, interval_days, last_practiced_at, state (new / learning / review)  
**Practice Logs**: id, clip_id, practiced_at, result (hard / ok / easy)  
**Ratings**: id, clip_id, rating (1–5), created_at  

MVP is single-user. Adding user_id later won’t require a schema redesign.

---

## Backend API (minimum)

- `POST /clips` – create clip
- `GET /clips` – list clips
- `GET /clips/{id}` – clip detail
- `POST /practice` – log practice + update review schedule
- `GET /reviews/due` – today’s review list
- `POST /ratings` – save 1–5 rating
- `GET /discover/recommendations` – AI video recommendations

---

## YouTube segment playback (frontend)

Use YouTube IFrame Player API. On play: `seekTo(start_sec)` then `playVideo()`.  
Poll `getCurrentTime()`; when it hits end_sec: if loop is on, `seekTo(start_sec)` again; if off, `pauseVideo()`.  
Desktop web only for now (skipping mobile autoplay issues).

---

## YouTube Data API (backend)

- `search.list`: TED, TED talk + topic keywords for candidates. Prefer medium length and captions.
- `videos.list`: enrich with duration, title, description.
- Send candidates to LLM for ranking.

---

## How we use AI

No model training, fine-tuning, or pronunciation scoring.  
LLM does **selection and ranking** only: pick videos good for speaking practice, one-line explanation, use preferences and past ratings.  
So it’s a decision layer, not a generator or evaluator.

---

## Dev order

1. Frontend only: YouTube segment playback component first.
2. Clip CRUD (backend).
3. Review / today logic.
4. AI discovery last.

---

## First task

One reusable React component:

- **Inputs**: videoId, startSec, endSec  
- **Controls**: play, pause, loop on/off  

Get that working and we’re halfway there.

---

## Principle

Build something I’ll actually use every day. Short clips, real sentences, repetition, habit.
