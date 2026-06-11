export type TranscriptSegment = {
    start: number;
    end: number;
    text: string;
};

export async function fetchClipTranscript(clipId: number): Promise<TranscriptSegment[]> {
    const base = import.meta.env.VITE_API_BASE_URL;

    const res = await fetch(`${base}/clips/${clipId}/transcript`);
    if (!res.ok) {
        const text = await res.text();
        throw new Error(text || "Failed to fetch transcript");
    }
    const data = await res.json();
    return data.segments ?? [];
}
