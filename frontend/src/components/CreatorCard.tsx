"use client";

import type { Creator } from "@/lib/api";

interface Props {
  creator: Creator;
  onAddToCampaign?: (creator: Creator) => void;
}

function ScoreBadge({ score, label }: { score: number; label: string }) {
  const color =
    score >= 70
      ? "text-green-700 bg-green-50"
      : score >= 40
      ? "text-yellow-700 bg-yellow-50"
      : "text-red-700 bg-red-50";

  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${color}`}>
      {label}: {score}
    </span>
  );
}

export default function CreatorCard({ creator, onAddToCampaign }: Props) {
  return (
    <div className="bg-white rounded-lg shadow hover:shadow-md transition-shadow p-4">
      <div className="flex items-start gap-4">
        <img
          src={creator.avatar_url || "/placeholder-avatar.png"}
          alt={creator.name}
          className="w-14 h-14 rounded-full object-cover bg-gray-200"
        />
        <div className="flex-1 min-w-0">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="font-semibold text-gray-900 truncate">
                {creator.name}
              </h3>
              <p className="text-sm text-gray-500">
                @{creator.handle} &middot;{" "}
                <span className="capitalize">{creator.platform}</span>
              </p>
            </div>
            <div className="text-right">
              <div className="text-2xl font-bold text-indigo-600">
                {Math.round(creator.overall_score)}
              </div>
              <div className="text-xs text-gray-500">Score</div>
            </div>
          </div>

          <p className="text-sm text-gray-600 mt-2 line-clamp-2">
            {creator.bio}
          </p>

          <div className="flex items-center gap-4 mt-3 text-sm text-gray-600">
            <span>{(creator.follower_count / 1000).toFixed(1)}K followers</span>
            <span>{creator.engagement_rate}% engagement</span>
            {creator.estimated_age_range && (
              <span>Age: {creator.estimated_age_range}</span>
            )}
          </div>

          <div className="flex flex-wrap gap-1.5 mt-2">
            <ScoreBadge score={creator.engagement_score} label="Eng" />
            <ScoreBadge score={creator.quality_score} label="Qual" />
            <ScoreBadge score={creator.relevance_score} label="Rel" />
          </div>

          <div className="flex items-center gap-2 mt-3">
            {creator.id && (
              <a
                href={`/creators/${creator.id}`}
                className="text-sm text-indigo-600 hover:text-indigo-800"
              >
                View Details
              </a>
            )}
            {creator.profile_url && (
              <a
                href={creator.profile_url}
                target="_blank"
                rel="noopener noreferrer"
                className="text-sm text-gray-500 hover:text-gray-700"
              >
                Profile
              </a>
            )}
            {onAddToCampaign && creator.id && (
              <button
                onClick={() => onAddToCampaign(creator)}
                className="ml-auto text-sm bg-indigo-50 text-indigo-600 px-3 py-1 rounded hover:bg-indigo-100"
              >
                + Campaign
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
