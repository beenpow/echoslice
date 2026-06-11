import { useEffect, useRef, useState } from 'react';
import { fetchClipTranscript, type TranscriptSegment } from '../api/transcript';

declare global {
    interface Window {
        YT: any;
        onYouTubeIframeAPIReady: () => void;
    }
}

type Props = {
    clipId: number;
    videoId: string;
    startSec: number;
    endSec: number;
};

export default function YoutubeClipPlayer({ clipId, videoId, startSec, endSec }: Props) {
    const containerRef = useRef<HTMLDivElement>(null);
    const playBtnRef = useRef<HTMLButtonElement>(null);
    const playerRef = useRef<any>(null);
    const [isPlaying, setIsPlaying] = useState(false);
    const [isLooping, setIsLooping] = useState(true);
    const [isCCOn, setIsCCOn] = useState(true);

    const [isReady, setIsReady] = useState(false);
    const [loopCount, setLoopCount] = useState(0);
    const pendingCueRef = useRef<{ videoId: string } | null>(null);
    const loopTriggeredRef = useRef(false);

    const [segments, setSegments] = useState<TranscriptSegment[]>([]);
    const [activeIndex, setActiveIndex] = useState(-1);
    const segmentRefs = useRef<(HTMLDivElement | null)[]>([]);

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
                if (loopTriggeredRef.current) return;
                loopTriggeredRef.current = true;

                setLoopCount((prev) => prev + 1);
                if (isLooping) {
                    player.seekTo(startSec, true);
                    player.playVideo();
                } else {
                    player.pauseVideo();
                    setIsPlaying(false);
                }
            } else {
                loopTriggeredRef.current = false;
            }

            setActiveIndex((prev) => {
                const idx = segments.findIndex(
                    (s) => current >= s.start && current < s.end
                );
                return idx === prev ? prev : idx;
            });
        }, 200);
        return () => {
            window.clearInterval(intervalId);
        };
    }, [isPlaying, endSec, isLooping, startSec, segments]);

    useEffect(() => {
        let cancelled = false;
        setSegments([]);
        setActiveIndex(-1);

        fetchClipTranscript(clipId)
            .then((segs) => {
                if (!cancelled) setSegments(segs);
            })
            .catch(() => {
                if (!cancelled) setSegments([]);
            });

        return () => {
            cancelled = true;
        };
    }, [clipId]);

    useEffect(() => {
        if (activeIndex < 0) return;
        const el = segmentRefs.current[activeIndex];
        const box = el?.parentElement;
        if (!el || !box) return;

        const elRect = el.getBoundingClientRect();
        const boxRect = box.getBoundingClientRect();
        const elOffsetInBox = elRect.top - boxRect.top + box.scrollTop;

        const target = elOffsetInBox - box.clientHeight / 2 + el.offsetHeight / 2;
        box.scrollTo({
            top: Math.max(0, target),
            behavior: "smooth",
        });
    }, [activeIndex]);

    useEffect(() => {
        const player = playerRef.current;
        if (!player) return;

        if (!isReady) {
            pendingCueRef.current = { videoId };
            return;
        }
        player.cueVideoById(videoId);
        setIsPlaying(false);
        setLoopCount(0);
        loopTriggeredRef.current = false;
    }, [videoId, isReady]);

    useEffect(() => {
        const loadAndCreate = () => {
            if (!window.YT || !containerRef.current) return;

            if (!playerRef.current) {
                playerRef.current = new window.YT.Player(containerRef.current, {
                    height: "100%",
                    width: "100%",
                    videoId,
                    playerVars: {
                        controls: 1,
                        cc_load_policy: 1,
                        cc_lang_pref: "en",
                    },
                    events: {
                        onReady: () => {
                            setIsReady(true);

                            const pending = pendingCueRef.current;
                            if (pending && playerRef.current) {
                                playerRef.current.cueVideoById(pending.videoId);
                                pendingCueRef.current = null;
                            }
                        },
                    },
                });
            }
        };

        if (window.YT) {
            loadAndCreate();
            return;
        }
        const existing = document.querySelector('script[src="https://www.youtube.com/iframe_api"]');
        if (!existing) {
            const tag = document.createElement("script");
            tag.src = "https://www.youtube.com/iframe_api";
            document.body.appendChild(tag);
        }

        window.onYouTubeIframeAPIReady = () => {
            loadAndCreate();
        };
    }, [videoId]);

    return (
        <div className="player-wrapper">
            <div className="player-aspect">
                <div
                    ref={containerRef}
                    className="player-embed"
                    aria-label="YouTube clip player"
                />
            </div>
            <div className="player-controls">
                <button
                    ref={playBtnRef}
                    type="button"
                    className="player-ctrl-btn primary"
                    onClick={handlePlayFromStart}
                >
                    ▶ Play
                </button>
                <button type="button" className="player-ctrl-btn" onClick={handlePause}>
                    Pause
                </button>
                <button
                    type="button"
                    className={`player-ctrl-btn toggle ${isLooping ? "on" : ""}`}
                    onClick={() => setIsLooping((prev) => !prev)}
                    title="Loop clip"
                >
                    Loop {isLooping ? "ON" : "OFF"}
                </button>
                <button
                    type="button"
                    className={`player-ctrl-btn toggle ${isCCOn ? "on" : ""}`}
                    onClick={() => setIsCCOn((prev) => !prev)}
                    title="Subtitles"
                >
                    CC {isCCOn ? "ON" : "OFF"}
                </button>
                <span className="player-loop-count" title="Loop count">
                    🔁 {loopCount}
                </span>
                <span className="player-time">
                    {startSec}s – {endSec}s
                </span>
            </div>
            {segments.length > 0 && (
                <div className="transcript-box">
                    {segments.map((seg, i) => (
                        <div
                            key={i}
                            ref={(el) => { segmentRefs.current[i] = el; }}
                            className={`transcript-line ${i === activeIndex ? "active" : ""}`}
                        >
                            {seg.text}
                        </div>
                    ))}
                </div>
            )}
        </div>
    );
}
