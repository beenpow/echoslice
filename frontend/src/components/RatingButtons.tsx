type Props = {
  disabled?: boolean;
  onSelect: (score: number) => void;
};

const LABELS: Record<number, string> = {
  1: "Skip",
  2: "Meh",
  3: "OK",
  4: "Good",
  5: "Great",
};

export default function RatingButtons({ disabled, onSelect }: Props) {
  const scores = [1, 2, 3, 4, 5] as const;

  return (
    <div className="rating-buttons">
      {scores.map((s) => (
        <button
          key={s}
          type="button"
          className="rating-btn"
          disabled={disabled}
          onClick={() => onSelect(s)}
          title={LABELS[s]}
          aria-label={`Rate ${s}: ${LABELS[s]}`}
        >
          <span className="rating-btn-score">{s}</span>
          <span className="rating-btn-label">{LABELS[s]}</span>
        </button>
      ))}
    </div>
  );
}
