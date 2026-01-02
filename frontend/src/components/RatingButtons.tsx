type Props = {
    disabled?: boolean;
    onSelect: (score: number) => void;
};

export default function RatingButtons({ disabled, onSelect }: Props) {
    const scores = [1, 2, 3, 4, 5];

    return (
        <div style={{ display: "flex", gap : 8}}>
            {scores.map((s) => (
                <button
                key={s}
                disabled={disabled}
                onClick={() => onSelect(s)}
                style={{
                    padding: "8px 10px",
                    borderRadius: 8,
                    border: "1px solid #ccc",
                    cursor: disabled ? "not-allowed" : "pointer",
                }}
                >
                    {s}
                </button>
            ))}
        </div>
    );
}