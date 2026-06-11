import "./App.css";
import { useEffect, useState } from "react";
import YoutubeClipPlayer from "./components/YoutubeClipPlayer";
import RatingButtons from "./components/RatingButtons";
import { postReview } from "./api/reviews";
import { fetchToday, rerollTodayOne } from "./api/today";
import type { Clip } from "./api/today";

function App() {
  const [clips, setClips] = useState<Clip[]>([]);
  const [selectedClip, setSelectedClip] = useState<Clip | null>(null);
  const [completedClipIds, setCompletedClipId] = useState<number[]>([]);

  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [rerollingPos, setRerollingPos] = useState<number | null>(null);

  const loadToday = async (opts?: {keepSelectedId?: number; preferPosition?: number}) => {
    const data = await fetchToday();
    const list = data.clips ?? [];

    setClips(data.clips);
    setCompletedClipId(data.completedClipIds ?? []);

    const byPos =
        opts?.preferPosition != null
            ? list.find((c) => c.position === opts.preferPosition) ?? null
            : null;

    const byId =
        opts?.keepSelectedId != null
            ? list.find((c) => c.id === opts.keepSelectedId) ?? null
            : null;

    setSelectedClip(byPos ?? byId ?? list[0] ?? null);
  };

  useEffect(() => {
    const run = async () => {
      try {
        setError(null);
        setLoading(true);
        await loadToday();
      } catch (e) {
        const msg = e instanceof Error ? e.message : String(e);
        setError(msg);
        setClips([]);
        setSelectedClip(null);
        setCompletedClipId([]);
      } finally {
        setLoading(false);
      }
    };
    run();
  }, []);

  const isSelectedCompleted = selectedClip
    ? completedClipIds.includes(selectedClip.id)
    : false;

  const handleRate = async (score: number) => {
    if (!selectedClip) return;

    try {
      setSubmitting(true);
      await postReview({ clipId: selectedClip.id, score });
      setCompletedClipId((prev) =>
        prev.includes(selectedClip.id) ? prev : [...prev, selectedClip.id]
      );
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      alert(msg);
      console.error(e);
    } finally {
      setSubmitting(false);
    }
  };

  const handleRerollOne = async (pos: number) => {
    if (rerollingPos != null) return;

    const wasViewingThisSlot = selectedClip?.position === pos;

    try {
      setRerollingPos(pos);
      await rerollTodayOne(pos);

      await loadToday({
        preferPosition: wasViewingThisSlot ? pos : undefined,
        keepSelectedId: selectedClip?.id,
      });
    } catch (e) {
      alert(e instanceof Error ? e.message : "Reroll failed");
    } finally {
      setRerollingPos(null);
    }
  };

  const reviewClips = clips.filter((c) => c.kind === "review");
  const newClips = clips.filter((c) => c.kind === "new");

  const renderClipRow = (c: Clip) => {
    const completed = completedClipIds.includes(c.id);
    const selected = selectedClip?.id === c.id;
    const canReroll = c.kind === "new" && !completed;
    const isBusy = rerollingPos === c.position;

    return (
      <div key={c.id} className="clip-card-wrapper">
        <button
          type="button"
          className={`clip-card ${selected ? "selected" : ""} ${completed ? "completed" : ""}`}
          onClick={() => setSelectedClip(c)}
        >
          <div className="clip-card-content">
            <p className="clip-card-title">
              {completed ? "✓ " : ""}
              {c.title?.trim() ? c.title : `Clip #${c.id}`}
            </p>
            <p className="clip-card-meta">
              <span className={`clip-badge ${c.kind}`}>{c.kind}</span>
              {c.startSec}s – {c.endSec}s
            </p>
          </div>
        </button>
        {c.kind === "new" && (
          <button
            type="button"
            className="clip-reroll-btn"
            onClick={() => {
              if (!canReroll || isBusy) return;
              handleRerollOne(c.position);
            }}
            disabled={!canReroll || isBusy}
            title={completed ? "Already completed" : "Reroll this clip"}
            aria-label="Reroll clip"
          >
            {isBusy ? "…" : "↻"}
          </button>
        )}
      </div>
    );
  };

  if (loading) {
    return (
      <div className="app">
        <div className="loading-state">
          <div className="loading-spinner" aria-hidden />
          <span>Loading today’s clips…</span>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="app">
        <header className="app-header">
          <h1 className="app-title">EchoSlice</h1>
        </header>
        <div className="error-state" role="alert">
          {error}
        </div>
      </div>
    );
  }

  if (clips.length === 0) {
    return (
      <div className="app">
        <header className="app-header">
          <h1 className="app-title">EchoSlice</h1>
        </header>
        <div className="empty-state">No clips today</div>
      </div>
    );
  }

  return (
    <div className="app">
      <header className="app-header">
        <h1 className="app-title">EchoSlice</h1>
      </header>

      <div className="app-body">
        <aside className="sidebar">
          <div className="sidebar-section">
            <h2 className="sidebar-section-title">Review</h2>
            {reviewClips.length === 0 ? (
              <p className="sidebar-empty">No reviews today</p>
            ) : (
              <div className="clip-list">
                {reviewClips.map(renderClipRow)}
              </div>
            )}
          </div>
          <div className="sidebar-section">
            <h2 className="sidebar-section-title">New</h2>
            {newClips.length === 0 ? (
              <p className="sidebar-empty">No new clips</p>
            ) : (
              <div className="clip-list">
                {newClips.map(renderClipRow)}
              </div>
            )}
          </div>
        </aside>

        <main className="main-content">
          {selectedClip && (
            <>
              <YoutubeClipPlayer
                clipId={selectedClip.id}
                videoId={selectedClip.videoId}
                startSec={selectedClip.startSec}
                endSec={selectedClip.endSec}
              />

              <div style={{ marginTop: 20 }}>
                {isSelectedCompleted ? (
                  <p className="completed-label">Completed</p>
                ) : (
                  <>
                    <p className="rating-label">Rate this clip</p>
                    <RatingButtons disabled={submitting} onSelect={handleRate} />
                  </>
                )}
              </div>
            </>
          )}
        </main>
      </div>
    </div>
  );
}

export default App;
