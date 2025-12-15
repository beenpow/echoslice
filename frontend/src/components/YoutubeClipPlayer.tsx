import { useEffect, useRef, useState } from 'react';

type Props = {
    videoId: string;
    startSec: number;
    endSec : number;
};

export default function YoutubeClipPlayer({ videoId, startSec, endSec }: Props) {
    // (1) ref for the DOM
    const containerRef = useRef<HTMLDivElement>(null);

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