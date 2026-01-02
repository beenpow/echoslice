export async function postReview(params: {
    clipId: number;
    score: number; // 1~5
}) {
    const res = await fetch(`${import.meta.env.VITE_API_BASE_URL}/reviews`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(params),
      });

      if (!res.ok) {
        const text = await res.text();
        throw new Error(text || "Failed to post review");
      }

      return res.json();
}