import { useEffect, useRef, useState } from 'react';

type Props = {
    videoId: string;
    startSec: number;
    endSec : number;
};

export default function YoutubeClipPlayer({ videoId, startSec, endSec }: Props) {
    return (
        <div>
            <h2>YoutubeClipPayer</h2>
            <div>VideoId: {videoId}</div>
            <div>
                start: {startSec}s, end: {endSec}s
            </div>
        </div>
    );
}