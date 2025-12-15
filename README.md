# EchoSlice – Development Planning Notes

## Tech Stack (Fixed)
- **Frontend**: React + TypeScript
- **Backend**: FastAPI (Python)
- **AI**: Pre-trained LLM (selection / ranking only)
- **Video**: YouTube IFrame Player API
- **Data Source**: YouTube Data API v3

---

## 1. MVP Scope (Do Not Expand)

To avoid scope creep, the MVP is limited to **4 core features** only.

1. **Clip Playback**
   - Play only a specific YouTube segment (start/end)
   - Loop on/off toggle
   - One-click replay for speaking practice

2. **Clip Storage & Library**
   - Add Clip: YouTube URL + start/end
   - Save clips
   - View and replay saved clips in Library

3. **Today / Review (Spaced Repetition)**
   - Show clips due for today
   - Mark result: Hard / OK / Easy
   - Update next review date automatically

4. **AI Discovery (Minimal)**
   - Recommend 3 candidate videos based on topic/difficulty
   - No automatic sentence extraction in MVP

---

## 2. Data Model (Initial)

### Clips
- `id`
- `video_id`
- `title`
- `start_sec`
- `end_sec`
- `topic`
- `created_at`

### Review Items
- `id`
- `clip_id`
- `due_date`
- `interval_days`
- `last_practiced_at`
- `state` (new / learning / review)

### Practice Logs
- `id`
- `clip_id`
- `practiced_at`
- `result` (hard / ok / easy)

### Ratings
- `id`
- `clip_id`
- `rating` (1–5)
- `created_at`

> MVP starts as **single-user**.  
> `user_id` can be added later without schema redesign.

---

## 3. Backend API Endpoints (Minimum)

- `POST /clips` – create clip
- `GET /clips` – list clips
- `GET /clips/{id}` – get clip detail
- `POST /practice` – log practice + update review schedule
- `GET /reviews/due` – get today’s review list
- `POST /ratings` – save 1–5 rating
- `GET /discover/recommendations` – AI video recommendations

---

## 4. YouTube Playback Strategy (Frontend Core)

- Use **YouTube IFrame Player API**
- On Play:
  - `seekTo(start_sec)`
  - `playVideo()`
- Poll `getCurrentTime()`
  - If `>= end_sec`:
    - Loop ON → `seekTo(start_sec)`
    - Loop OFF → `pauseVideo()`

> Desktop web only (no mobile autoplay concerns).

---

## 5. YouTube Data API Usage (Backend)

- Use `search.list` to retrieve candidate videos
  - Keywords: `TED`, `TED talk`, topic keywords
  - Filters: medium duration, captions preferred
- Use `videos.list` to enrich metadata
  - duration
  - title / description
- Pass candidates to LLM for ranking

---

## 6. AI Usage Philosophy

- ❌ No model training or fine-tuning
- ❌ No pronunciation scoring
- ✅ LLM used only for **selection & ranking**

### AI Responsibilities
- Rank candidate videos for speaking practice
- Explain selection briefly (1 line)
- Use user preferences + past ratings as feedback

> AI acts as a **decision layer**, not a generator or evaluator.

---

## 7. Development Order (Critical)

1. **Frontend only**
   - Implement YouTube segment playback component
2. Backend CRUD for clips
3. Review / Today logic
4. AI Discovery (last)

---

## 8. First Task (Start Here)

Implement a reusable React component:

**Inputs**
- `videoId`
- `startSec`
- `endSec`

**Controls**
- Play
- Pause
- Loop on/off

> Once this works, the project is already 50% done.

---

## Project Principle

> Build a tool I actually use every day.  
> Short clips, real sentences, repetition, and habit.
