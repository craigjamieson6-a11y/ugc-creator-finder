"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import ScoreBreakdown from "@/components/ScoreBreakdown";
import { getCreator } from "@/lib/api";
import type { Creator } from "@/lib/api";

export default function CreatorDetailPage() {
  const params = useParams();
  const id = Number(params.id);
  const [creator, setCreator] = useState<Creator | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!id) return;
    setLoading(true);
    getCreator(id)
      .then(setCreator)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, [id]);

  if (loading)
    return <div className="text-center py-20 text-gray-400">Loading...</div>;
  if (error)
    return (
      <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-md">
        {error}
      </div>
    );
  if (!creator)
    return (
      <div className="text-center py-20 text-gray-400">Creator not found</div>
    );

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <a href="/" className="text-sm text-indigo-600 hover:text-indigo-800">
        &larr; Back to Search
      </a>

      <div className="bg-white rounded-lg shadow p-6">
        <div className="flex items-start gap-6">
          <img
            src={creator.avatar_url || "/placeholder-avatar.png"}
            alt={creator.name}
            className="w-24 h-24 rounded-full object-cover bg-gray-200"
          />
          <div className="flex-1">
            <h1 className="text-2xl font-bold">{creator.name}</h1>
            <p className="text-gray-500">
              @{creator.handle} &middot;{" "}
              <span className="capitalize">{creator.platform}</span>
            </p>
            <p className="text-gray-600 mt-2">{creator.bio}</p>

            <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mt-4">
              <div>
                <div className="text-sm text-gray-500">Followers</div>
                <div className="text-lg font-semibold">
                  {(creator.follower_count / 1000).toFixed(1)}K
                </div>
              </div>
              <div>
                <div className="text-sm text-gray-500">Engagement</div>
                <div className="text-lg font-semibold">
                  {creator.engagement_rate}%
                </div>
              </div>
              <div>
                <div className="text-sm text-gray-500">Age Range</div>
                <div className="text-lg font-semibold">
                  {creator.estimated_age_range || "Unknown"}
                </div>
              </div>
              <div>
                <div className="text-sm text-gray-500">Gender</div>
                <div className="text-lg font-semibold capitalize">
                  {creator.gender || "Unknown"}
                </div>
              </div>
            </div>

            {creator.niche_tags && creator.niche_tags.length > 0 && (
              <div className="flex flex-wrap gap-2 mt-3">
                {creator.niche_tags.map((tag) => (
                  <span
                    key={tag}
                    className="bg-indigo-50 text-indigo-700 px-2 py-0.5 rounded text-xs"
                  >
                    {tag}
                  </span>
                ))}
              </div>
            )}

            {creator.profile_url && (
              <a
                href={creator.profile_url}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-block mt-3 text-sm text-indigo-600 hover:text-indigo-800"
              >
                View Profile &rarr;
              </a>
            )}
          </div>
        </div>
      </div>

      <ScoreBreakdown
        engagement={creator.engagement_score}
        quality={creator.quality_score}
        relevance={creator.relevance_score}
        overall={creator.overall_score}
      />

      <div className="bg-white rounded-lg shadow p-6">
        <h3 className="text-lg font-semibold mb-4">Additional Metrics</h3>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
          <div>
            <div className="text-sm text-gray-500">Avg Likes</div>
            <div className="text-lg font-semibold">
              {creator.avg_likes?.toLocaleString() || "—"}
            </div>
          </div>
          <div>
            <div className="text-sm text-gray-500">Avg Comments</div>
            <div className="text-lg font-semibold">
              {creator.avg_comments?.toLocaleString() || "—"}
            </div>
          </div>
          <div>
            <div className="text-sm text-gray-500">Avg Views</div>
            <div className="text-lg font-semibold">
              {creator.avg_views?.toLocaleString() || "—"}
            </div>
          </div>
          <div>
            <div className="text-sm text-gray-500">Total Posts</div>
            <div className="text-lg font-semibold">
              {creator.post_count?.toLocaleString() || "—"}
            </div>
          </div>
        </div>
        <div className="mt-3 text-xs text-gray-400">
          Demographic confidence: {creator.demographic_confidence}
        </div>
      </div>
    </div>
  );
}
