"use client";

import type { Creator } from "@/lib/api";

interface Props {
  creators: Creator[];
  onAddToCampaign?: (creator: Creator) => void;
}

export default function CreatorTable({ creators, onAddToCampaign }: Props) {
  return (
    <div className="overflow-x-auto">
      <table className="min-w-full bg-white rounded-lg shadow">
        <thead>
          <tr className="border-b border-gray-200 text-left text-sm font-medium text-gray-500">
            <th className="px-4 py-3">Creator</th>
            <th className="px-4 py-3">Platform</th>
            <th className="px-4 py-3">Followers</th>
            <th className="px-4 py-3">Engagement</th>
            <th className="px-4 py-3">Age Range</th>
            <th className="px-4 py-3">Overall</th>
            <th className="px-4 py-3">Eng.</th>
            <th className="px-4 py-3">Qual.</th>
            <th className="px-4 py-3">Rel.</th>
            <th className="px-4 py-3"></th>
          </tr>
        </thead>
        <tbody>
          {creators.map((c, i) => (
            <tr
              key={c.external_id || i}
              className="border-b border-gray-100 hover:bg-gray-50 text-sm"
            >
              <td className="px-4 py-3">
                <div className="flex items-center gap-3">
                  <img
                    src={c.avatar_url || "/placeholder-avatar.png"}
                    alt={c.name}
                    className="w-8 h-8 rounded-full object-cover bg-gray-200"
                  />
                  <div>
                    <div className="font-medium text-gray-900">{c.name}</div>
                    <div className="text-gray-500 text-xs">@{c.handle}</div>
                  </div>
                </div>
              </td>
              <td className="px-4 py-3 capitalize">{c.platform}</td>
              <td className="px-4 py-3">
                {(c.follower_count / 1000).toFixed(1)}K
              </td>
              <td className="px-4 py-3">{c.engagement_rate}%</td>
              <td className="px-4 py-3">{c.estimated_age_range || "—"}</td>
              <td className="px-4 py-3 font-bold text-indigo-600">
                {Math.round(c.overall_score)}
              </td>
              <td className="px-4 py-3">{Math.round(c.engagement_score)}</td>
              <td className="px-4 py-3">{Math.round(c.quality_score)}</td>
              <td className="px-4 py-3">{Math.round(c.relevance_score)}</td>
              <td className="px-4 py-3">
                <div className="flex gap-2">
                  {c.id && (
                    <a
                      href={`/creators/${c.id}`}
                      className="text-indigo-600 hover:text-indigo-800 text-xs"
                    >
                      View
                    </a>
                  )}
                  {onAddToCampaign && c.id && (
                    <button
                      onClick={() => onAddToCampaign(c)}
                      className="text-indigo-600 hover:text-indigo-800 text-xs"
                    >
                      +Camp
                    </button>
                  )}
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
