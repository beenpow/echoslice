import './App.css'
import YoutubeClipPlayer from './components/YoutubeClipPlayer'
import { useState } from "react";
import RatingButtons from './components/RatingButtons';
import { postReview } from './api/reviews';

function App() {
    const clipId = 1;

    const [completedClipIds, setCompletedClipId] = useState<number[]>([]);
    const [submitting, setSubmitting] = useState(false);

    const isCompleted = completedClipIds.includes(clipId);

    const handleRate = async (score: number) => {
        try {
            setSubmitting(true);
            await postReview({ clipId, score });
            setCompletedClipId((prev) =>
                prev.includes(clipId) ? prev : [...prev, clipId]
            );
        } catch (e) {
            alert("Failed to save review");
            console.error(e);
        } finally {
            setSubmitting(false);
        }
    };

    return (
        <div>
          <h1>EchoSlice</h1>
    
          <YoutubeClipPlayer
            videoId="Ks-_Mh1QhMc"
            startSec={110}
            endSec={140}
          />
    
          <div style={{ marginTop: 16 }}>
            {isCompleted ? (
              <div>Completed</div>
            ) : (
              <>
                <div>Rate this clip</div>
                <RatingButtons
                  disabled={submitting}
                  onSelect={handleRate}
                />
              </>
            )}
          </div>
        </div>
      );
    }
    
export default App;