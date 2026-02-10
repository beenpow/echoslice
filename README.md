# EchoSlice

Short TED clips for speaking practice: loop a segment, rate it, and get spaced repetition so you actually stick with it.

**Live site:** [https://echoslicefront.vercel.app/](https://echoslicefront.vercel.app/)

Solo project. Stack: React + TypeScript (frontend), FastAPI (backend), YouTube IFrame API for segment playback.  
AI is used only for **picking and ranking** clips—no training, no fine-tuning. I pull candidate TED talks, send them to an LLM with simple criteria (good for shadowing, coherent idea, clear phrasing), and it returns a small ranked set. So the model is a decision layer: which segments to surface, not what to say or how to score pronunciation.

---

## What it does

1. **Clip playback** – Play a segment by start/end. Loop on/off, one-click replay.
2. **Clip library** – Save clips (URL + start/end), list and replay.
3. **Today / review** – Spaced repetition: clips due today, rate Hard/OK/Easy, next review date updates automatically.
4. **AI-backed discovery** – Candidate videos are filtered and ranked by an LLM (topic, difficulty, fit for speaking practice). I keep the scope small so the AI part stays predictable and debuggable.

---

## Stack

- Frontend: React, TypeScript, YouTube IFrame Player API (segment playback).
- Backend: FastAPI, SQLite. YouTube Data API v3 for search/metadata.
- AI: LLM for recommendation/ranking only (e.g. pick ~3 clips per talk, with short reasoning). No generative or grading use.

---

## Data model (draft)

**Clips**: id, video_id, title, start_sec, end_sec, topic, created_at  
**Review Items**: id, clip_id, due_date, interval_days, last_practiced_at, state (new / learning / review)  
**Practice Logs**: id, clip_id, practiced_at, result (hard / ok / easy)  
**Ratings**: id, clip_id, rating (1–5), created_at  

MVP is single-user; schema is set up so user_id can be added later without a big redesign.

---

## Backend API (minimum)

- `POST /clips` – create clip  
- `GET /clips` – list clips  
- `GET /clips/{id}` – clip detail  
- `POST /practice` – log practice + update review schedule  
- `GET /reviews/due` – today’s review list  
- `POST /ratings` – save 1–5 rating  
- `GET /discover/recommendations` – AI-backed video recommendations  

---

## YouTube segment playback (frontend)

IFrame API: `seekTo(start_sec)` then `playVideo()`. Poll `getCurrentTime()`; at end_sec, loop or pause depending on loop setting. Desktop web for now.

---

## How AI is used

No model training, fine-tuning, or pronunciation scoring. The LLM does **selection and ranking**: which videos and segments are good for speaking practice, with a one-line reason. It uses the criteria I define (e.g. coherent idea, good for shadowing) and can take past ratings into account. So it’s a decision layer—not a generator or an evaluator.

---

## Dev order

1. Frontend: YouTube segment playback component first.  
2. Clip CRUD (backend).  
3. Review / today logic.  
4. AI discovery last.  

---

## Principle

Build something I’ll actually use every day: short clips, real sentences, repetition, habit.
