export type Clip = {
    id: number;
    videoId: string;
    startSec: number;
    endSec: number;
    title?: string;
    kind: "new" | "review";
};

export type TodayResponse = {
    day: string;
    clips: Clip[];
    completedClipIds?: number[];
};

export async function fetchToday(): Promise<TodayResponse> {
    const base = import.meta.env.VITE_API_BASE_URL;

    const res = await fetch(`${base}/today`);
    if (!res.ok) {
        const text = await res.text();
        throw new Error(text || "Failed to fetch /today");
    }
    return res.json();
}