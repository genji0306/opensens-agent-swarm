/**
 * SVG arc gauge showing agent budget utilization.
 *
 * Renders a 270° arc that fills proportionally to spent/budget.
 * Color transitions: green (0-60%), yellow (60-85%), red (85%+).
 */

interface BudgetGaugeProps {
  agentName: string;
  spentCents: number;
  budgetCents: number;
  size?: number;
}

function getGaugeColor(pct: number): string {
  if (pct >= 85) return "#ef4444";
  if (pct >= 60) return "#eab308";
  return "#22c55e";
}

export function BudgetGauge({
  agentName,
  spentCents,
  budgetCents,
  size = 48,
}: BudgetGaugeProps) {
  const pct = budgetCents > 0 ? Math.min(100, (spentCents / budgetCents) * 100) : 0;
  const color = getGaugeColor(pct);

  const cx = size / 2;
  const cy = size / 2;
  const r = (size - 6) / 2;
  const circumference = 2 * Math.PI * r;
  const arcLength = circumference * 0.75; // 270°
  const filled = arcLength * (pct / 100);

  const formatDollars = (cents: number) =>
    cents >= 100 ? `$${(cents / 100).toFixed(0)}` : `${cents}¢`;

  return (
    <div className="flex flex-col items-center gap-0.5">
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
        {/* Background arc */}
        <circle
          cx={cx}
          cy={cy}
          r={r}
          fill="none"
          stroke="currentColor"
          className="text-gray-200 dark:text-gray-700"
          strokeWidth={3}
          strokeDasharray={`${arcLength} ${circumference}`}
          strokeDashoffset={0}
          strokeLinecap="round"
          transform={`rotate(135 ${cx} ${cy})`}
        />
        {/* Filled arc */}
        <circle
          cx={cx}
          cy={cy}
          r={r}
          fill="none"
          stroke={color}
          strokeWidth={3}
          strokeDasharray={`${filled} ${circumference}`}
          strokeDashoffset={0}
          strokeLinecap="round"
          transform={`rotate(135 ${cx} ${cy})`}
        />
        {/* Center text */}
        <text
          x={cx}
          y={cy + 1}
          textAnchor="middle"
          dominantBaseline="central"
          className="fill-gray-700 dark:fill-gray-300"
          fontSize={size * 0.22}
          fontWeight={700}
        >
          {Math.round(pct)}%
        </text>
      </svg>
      <span
        className="max-w-[56px] truncate text-center text-[10px] leading-tight text-gray-500 dark:text-gray-400"
        title={`${agentName}: ${formatDollars(spentCents)} / ${formatDollars(budgetCents)}`}
      >
        {agentName}
      </span>
    </div>
  );
}
