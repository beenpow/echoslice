import { useEffect, useRef, useState } from 'react';

declare global {
    interface Window {
        YT: any;
        onYoutubeIframeAPIReady: () => void;
    }
}

type Props = {
    videoId: string;
    startSec: number;
    endSec : number;
};

export default function YoutubeClipPlayer({ videoId, startSec, endSec }: Props) {
    const containerRef = useRef<HTMLDivElement>(null);

    useEffect(() => {
        // 1) Skip if YT is already loaded
        if (window.YT) {
            console.log("Youtube IFrame API alread loaded");
            return;
        }
        // 2) add script tag
        const tag = document.createElement("script");
        tag.src = "https://www.youtube.com/iframe_api";
        document.body.appendChild(tag);

        // 3. Load done callback
        window.onYoutubeIframeAPIReady = () => {
            console.log("Youtube IFrame API ready");
        };
    }, []);

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

            <div>VideoId: {videoId}</div>
            <div>
                start: {startSec}s, end: {endSec}s
            </div>
        </div>
    );
}