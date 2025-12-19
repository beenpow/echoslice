import { useEffect, useRef, useState } from 'react';

declare global {
    interface Window {
        YT: any;
        onYouTubeIframeAPIReady: () => void;
    }
}

type Props = {
    videoId: string;
    startSec: number;
    endSec : number;
};

export default function YoutubeClipPlayer({ videoId, startSec, endSec }: Props) {
    const containerRef = useRef<HTMLDivElement>(null);
    const playerRef = useRef<any>(null);
    const [isPlaying, setIsPlaying] = useState(false);

    const handlePlayFromStart = () => {
        const player = playerRef.current;
        if (!player) return;

        player.seekTo(startSec, true);
        player.playVideo();
        setIsPlaying(true);
    };

    const handlePause = () => {
        const player = playerRef.current;
        if (!player) return;

        player.pauseVideo();
        setIsPlaying(false);
    };
    useEffect(() => {
        if (!isPlaying) return;

        const intervalId = window.setInterval(() => {
            const player = playerRef.current;
            if (!player || !player.getCurrentTime) return;

            const current = player.getCurrentTime();
            if (current >= endSec) {
                player.pauseVideo();
                setIsPlaying(false);
            }
        }, 200);
        return () => {
            window.clearInterval(intervalId);
        };
    }, [isPlaying, endSec]);

    useEffect(() => {
        const loadAndCreate = () => {
            if (!window.YT || !containerRef.current) return;

            if (!playerRef.current) {
                playerRef.current = new window.YT.Player(containerRef.current, {
                    height: "360",
                    width: "640",
                    videoId,
                    playerVars: {
                        controls: 1,
                    },
                    events: {
                        onReady: () => {
                            console.log("Player ready");
                        },
                    },
                });
            }
        };

        // 1) Skip if YT is already loaded
        if (window.YT) {
            loadAndCreate();
            return;
        }
        // 2) add script tag
        const existing = document.querySelector('script[src="https://www.youtube.com/iframe_api"]');
        if (!existing) {
          const tag = document.createElement("script");
          tag.src = "https://www.youtube.com/iframe_api";
          document.body.appendChild(tag);
        }
        
        // 3. Load done callback
        window.onYouTubeIframeAPIReady = () => {
            console.log("Youtube IFrame API ready");
            loadAndCreate();
        };
    }, [videoId]);

    return (
        <div>
            <h2>YoutubeClipPayer</h2>
            {/* Youtube Player position */}
            <div
                ref={containerRef}
                style={{
                    width: 640,
                    height: 360,
                    background: "#222",
                }}
            />
            <div style={{ marginTop: 8 }}>
                <button onClick={handlePlayFromStart}>Play from startSec</button>
                <button onClick={handlePause} style = {{ marginLeft: 8}}>
                    Pause
                </button>
            </div>

            <div>VideoId: {videoId}</div>
            <div>
                start: {startSec}s, end: {endSec}s
            </div>
        </div>
    );
}