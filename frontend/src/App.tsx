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

  const loadToday = async (keepSelectedId?: number) => {
    const data = await fetchToday();

    setClips(data.clips);
    setCompletedClipId(data.completedClipIds ?? []);

    const nextSelected =
      (keepSelectedId != null && data.clips.find((c) => c.id === keepSelectedId)) ||
      data.clips[0] ||
      null;

    setSelectedClip(nextSelected);
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

    try {
      setRerollingPos(pos);
      await rerollTodayOne(pos);
      await loadToday(selectedClip?.id);
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
  
    // reroll 가능 조건: new 이면서 아직 완료되지 않음
    const canReroll = c.kind === "new" && !completed;
    const isBusy = rerollingPos === c.position;
  
    return (
      <div
        key={c.id}
        style={{
          display: "flex",
          alignItems: "center",
          gap: 8,
        }}
      >
        {/* 왼쪽: 클립 선택 버튼 */}
        <button
          onClick={() => setSelectedClip(c)}
          style={{
            flex: 1,
            textAlign: "left",
            padding: 10,
            borderRadius: 10,
            border: selected ? "2px solid #2563eb" : "1px solid #ccc",
            cursor: "pointer",
            opacity: completed ? 0.5 : 1,
            background: selected ? "#f3f3f3" : "white",
            color: "#111",
          }}
        >
          <div style={{ fontWeight: 600 }}>
            {completed ? "✅ " : ""}
            {c.title?.trim() ? c.title : `Clip #${c.id}`}
          </div>
          <div style={{ fontSize: 12, color: "#444" }}>
            {c.startSec}s - {c.endSec}s
          </div>
        </button>
  
        {/* 오른쪽: reroll 아이콘 (자리 고정: 항상 렌더) */}
        {c.kind === "new" && (
          <button
            onClick={() => {
              if (!canReroll || isBusy) return;
              handleRerollOne(c.position);
            }}
            disabled={!canReroll || isBusy}
            title={completed ? "Already completed" : "Reroll this clip"}
            style={{
              width: 24,
              height: 24,
              padding: 0,
              border: "none",
              background: "transparent",
              fontSize: 16,
              lineHeight: "24px",
              flexShrink: 0,
  
              cursor: !canReroll || isBusy ? "default" : "pointer",
              opacity: completed ? 0.25 : isBusy ? 0.35 : 0.6,
            }}
            onMouseEnter={(e) => {
              if (!canReroll || isBusy) return;
              e.currentTarget.style.opacity = "1";
            }}
            onMouseLeave={(e) => {
              if (!canReroll || isBusy) return;
              e.currentTarget.style.opacity = "0.6";
            }}
          >
            🔁
          </button>
        )}
      </div>
    );
  };
  

  // ✅ early return은 모든 hook/state/함수 선언 이후에만!
  if (loading) return <div style={{ padding: 16 }}>Loading...</div>;
  if (error) return <div style={{ padding: 16 }}>Error: {error}</div>;
  if (clips.length === 0) return <div style={{ padding: 16 }}>No clips today</div>;

  return (
    <div style={{ padding: 16 }}>
      <h1>EchoSlice</h1>

      <div style={{ display: "flex", gap: 16 }}>
        <div style={{ width: 320 }}>
          <h3>Today</h3>

          <div style={{ marginTop: 12 }}>
            <div style={{ fontWeight: 700, marginBottom: 8 }}>Review</div>
            {reviewClips.length === 0 ? (
              <div style={{ fontSize: 12, color: "#666" }}>No reviews today</div>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                {reviewClips.map(renderClipRow)}
              </div>
            )}
          </div>

          <div style={{ marginTop: 16 }}>
            <div style={{ fontWeight: 700, marginBottom: 8 }}>New</div>
            {newClips.length === 0 ? (
              <div style={{ fontSize: 12, color: "#666" }}>No new clips</div>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                {newClips.map(renderClipRow)}
              </div>
            )}
          </div>
        </div>

        <div style={{ flex: 1 }}>
          {selectedClip && (
            <>
              <YoutubeClipPlayer
                videoId={selectedClip.videoId}
                startSec={selectedClip.startSec}
                endSec={selectedClip.endSec}
              />

              <div style={{ marginTop: 16 }}>
                {isSelectedCompleted ? (
                  <div>Completed</div>
                ) : (
                  <>
                    <div style={{ marginBottom: 8 }}>Rate this clip</div>
                    <RatingButtons disabled={submitting} onSelect={handleRate} />
                  </>
                )}
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

export default App;
