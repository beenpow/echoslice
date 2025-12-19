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
    const playBtnRef = useRef<HTMLButtonElement>(null);
    const playerRef = useRef<any>(null);
    const [isPlaying, setIsPlaying] = useState(false);
    const [isLooping, setIsLooping] = useState(true);
    const [isCCOn, setIsCCOn] = useState(true);

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
        const onKeyDown = (e: KeyboardEvent) => {
            const target = e.target as HTMLElement | null;
            const tag = target?.tagName?.toLowerCase();
            const isTyping = 
                tag == "input" || tag == "textarea" || (target as any)?.isContentEditable;
            
            if (isTyping) return;
            if (e.code == "Space") {
                e.preventDefault();
                handlePlayFromStart();
            }
        };
        window.addEventListener("keydown", onKeyDown);
        return () => window.removeEventListener("keydown", onKeyDown);

    }, [startSec, videoId, endSec]);

    useEffect(() => {
        const player = playerRef.current;
        if (!player) return;
        if (isCCOn) {
            player.loadModule("captions");
            player.setOption("captions", "track", {
                languageCode: "en",
            });
        } else {
            player.unloadModule("captions");
        }
    }, [isCCOn]);
    useEffect(() => {
        if (!isPlaying) return;

        const intervalId = window.setInterval(() => {
            const player = playerRef.current;
            if (!player || !player.getCurrentTime) return;

            const current = player.getCurrentTime();
            if (current >= endSec) {
                if (isLooping) {
                    player.seekTo(startSec, true);
                    player.playVideo();
                } else {
                    player.pauseVideo();
                    setIsPlaying(false);
                }
            }
        }, 200);
        return () => {
            window.clearInterval(intervalId);
        };
    }, [isPlaying, endSec, isLooping, startSec]);

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
                        cc_load_policy: 1,
                        cc_lang_pref: "en",
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
                    width: 1000,
                    height: 800,
                    background: "#222",
                }}
            />
            <div style={{ marginTop: 8 }}>
                <button ref={playBtnRef} onClick={handlePlayFromStart}>Play from startSec</button>
                <button onClick={handlePause} style = {{ marginLeft: 8}}>
                    Pause
                </button>
                <button onClick={() => setIsLooping((prev) => !prev)}>
                    Loop: {isLooping ? "ON" : "OFF"}
                </button>
                <button onClick={() => setIsCCOn((prev) => !prev)}>
                    CC: {isCCOn ? "ON" : "OFF"}
                </button>                
            </div>

            <div>VideoId: {videoId}</div>
            <div>
                start: {startSec}s, end: {endSec}s
            </div>
        </div>
    );
}