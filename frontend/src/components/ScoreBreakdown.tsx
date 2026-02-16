"use client";

interface Props {
  engagement: number;
  quality: number;
  relevance: number;
  overall: number;
}

function Bar({ label, score, color }: { label: string; score: number; color: string }) {
  return (
    <div className="space-y-1">
      <div className="flex justify-between text-sm">
        <span className="text-gray-600">{label}</span>
        <span className="font-medium">{Math.round(score)}/100</span>
      </div>
      <div className="w-full bg-gray-200 rounded-full h-2.5">
        <div
          className={`h-2.5 rounded-full ${color}`}
          style={{ width: `${Math.min(100, score)}%` }}
        />
      </div>
    </div>
  );
}

export default function ScoreBreakdown({ engagement, quality, relevance, overall }: Props) {
  return (
    <div className="bg-white rounded-lg shadow p-6 space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-semibold">Score Breakdown</h3>
        <div className="text-3xl font-bold text-indigo-600">{Math.round(overall)}</div>
      </div>
      <Bar label="Engagement (40%)" score={engagement} color="bg-blue-500" />
      <Bar label="Quality (30%)" score={quality} color="bg-green-500" />
      <Bar label="Relevance (30%)" score={relevance} color="bg-purple-500" />
    </div>
  );
}
