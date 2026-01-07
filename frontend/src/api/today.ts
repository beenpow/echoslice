export type Clip = {
    position: number;
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

export async function rerollTodayOne(position: number): Promise<void> {
    const base = import.meta.env.VITE_API_BASE_URL;

    const res = await fetch(`${base}/clips/today/reroll_one`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ position }),
      });

    if (!res.ok) {
        const text = await res.text();
        throw new Error(text || "Failed to reroll one slot");
    }
}