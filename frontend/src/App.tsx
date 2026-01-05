import './App.css'
import { useEffect, useState } from "react";
import YoutubeClipPlayer from './components/YoutubeClipPlayer'
import RatingButtons from './components/RatingButtons';
import { postReview } from './api/reviews';
import { fetchToday } from "./api/today";
import type { Clip } from "./api/today";

function App() {
    const [clips, setClips] = useState<Clip[]>([]);
    const [selectedClip, setSelectedClip] = useState<Clip | null>(null);
    const [completedClipIds, setCompletedClipId] = useState<number[]>([]);

    const [loading, setLoading] = useState(true);
    const [submitting, setSubmitting] = useState(false);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        const run = async() => {
            try {
                setLoading(true);
                const data = await fetchToday();
                setClips(data.clips);
                setCompletedClipId(data.completedClipIds ?? []);

                if (data.clips.length > 0) {
                    setSelectedClip(data.clips[0]);
                }
            } catch (e) {
                const msg = e instanceof Error ? e.message : String(e);
                setError(msg);
            } finally {
                setLoading(false);
            }
        };
        run();
    }, []);

    const isSelectedCompleted = selectedClip ? completedClipIds.includes(selectedClip.id) : false;

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

    if (loading) return <div style = {{ padding: 16 }}>Loading...</div>;
    if (error) return <div style={{ padding: 16 }}>Error: {error}</div>;
    if (clips.length == 0) return <div style = {{ padding: 16 }}>No clips today</div>;

    return (
        <div style={{ padding: 16 }}>
          <h1>EchoSlice</h1>
    
          <div style={{ display: "flex", gap: 16 }}>
            {/* 왼쪽: 오늘 클립 리스트 */}
            <div style={{ width: 320 }}>
              <h3>Today</h3>
    
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                {clips.map((c) => {
                  const completed = completedClipIds.includes(c.id);
                  const selected = selectedClip?.id === c.id;
    
                  return (
                    <button
                      key={c.id}
                      onClick={() => setSelectedClip(c)}
                      style={{
                        textAlign: "left",
                        padding: 10,
                        borderRadius: 10,
                        border: "1px solid #ccc",
                        cursor: "pointer",
                        opacity: completed ? 0.5 : 1,
                        background: selected ? "#f3f3f3" : "white",
                        color: "#111",
                      }}
                    >
                      <div style={{ fontWeight: 600 }}>
                        {completed ? "✅ " : ""}
                        {c.title ? c.title : `Clip #${c.id}`}
                      </div>
                      <div style={{ fontSize: 12 }}>
                        {c.startSec}s - {c.endSec}s
                      </div>
                    </button>
                  );
                })}
              </div>
            </div>
    
            {/* 오른쪽: 플레이어 + 평점 */}
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
                        <RatingButtons
                          disabled={submitting}
                          onSelect={handleRate}
                        />
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