"use client";

import { useState } from "react";
import type { SearchParams } from "@/lib/api";

const PLATFORMS = ["instagram", "tiktok", "youtube", "facebook", "pinterest", "twitter", "all"];
const NICHES = [
  "beauty",
  "health",
  "lifestyle",
  "food",
  "fitness",
  "fashion",
  "travel",
  "parenting",
  "home",
  "crafts",
  "wellness",
  "education",
];
const SORT_OPTIONS = [
  { value: "overall_score", label: "Overall Score" },
  { value: "engagement_score", label: "Engagement" },
  { value: "follower_count", label: "Followers" },
  { value: "quality_score", label: "Quality" },
  { value: "relevance_score", label: "Relevance" },
];

interface Props {
  onSearch: (params: SearchParams) => void;
  loading: boolean;
}

export default function SearchFilters({ onSearch, loading }: Props) {
  const [platform, setPlatform] = useState("instagram");
  const [niche, setNiche] = useState("");
  const [minFollowers, setMinFollowers] = useState(1000);
  const [minEngagement, setMinEngagement] = useState(0);
  const [sortBy, setSortBy] = useState("overall_score");

  const handleSearch = (deepSearch = false) => {
    onSearch({
      platform,
      niche: niche || undefined,
      min_followers: minFollowers,
      min_engagement: minEngagement,
      sort_by: sortBy,
      gender: "female",
      age_min: 40,
      age_max: 60,
      page_size: 100,
      deep_search: deepSearch || undefined,
    });
  };

  return (
    <div className="bg-white rounded-lg shadow p-6 space-y-4">
      <h2 className="text-lg font-semibold">Search Filters</h2>

      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">
          Platform
        </label>
        <div className="flex flex-wrap gap-2">
          {PLATFORMS.map((p) => (
            <button
              key={p}
              onClick={() => setPlatform(p)}
              className={`px-3 py-1.5 rounded-full text-sm capitalize ${
                platform === p
                  ? "bg-indigo-600 text-white"
                  : "bg-gray-100 text-gray-700 hover:bg-gray-200"
              }`}
            >
              {p === "all" ? "All Platforms" : p === "twitter" ? "Twitter/X" : p}
            </button>
          ))}
        </div>
      </div>

      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">
          Niche
        </label>
        <select
          value={niche}
          onChange={(e) => setNiche(e.target.value)}
          className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm"
        >
          <option value="">All niches</option>
          {NICHES.map((n) => (
            <option key={n} value={n}>
              {n.charAt(0).toUpperCase() + n.slice(1)}
            </option>
          ))}
        </select>
      </div>

      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">
          Min Followers: {minFollowers.toLocaleString()}
        </label>
        <input
          type="range"
          min={1000}
          max={500000}
          step={1000}
          value={minFollowers}
          onChange={(e) => setMinFollowers(Number(e.target.value))}
          className="w-full"
        />
      </div>

      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">
          Min Engagement Rate: {minEngagement}%
        </label>
        <input
          type="range"
          min={0}
          max={10}
          step={0.5}
          value={minEngagement}
          onChange={(e) => setMinEngagement(Number(e.target.value))}
          className="w-full"
        />
      </div>

      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">
          Sort By
        </label>
        <select
          value={sortBy}
          onChange={(e) => setSortBy(e.target.value)}
          className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm"
        >
          {SORT_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
      </div>

      <button
        onClick={() => handleSearch(false)}
        disabled={loading}
        className="w-full bg-indigo-600 text-white py-2.5 rounded-md hover:bg-indigo-700 disabled:opacity-50 font-medium"
      >
        {loading ? "Searching..." : "Search Creators"}
      </button>

      <button
        onClick={() => handleSearch(true)}
        disabled={loading}
        className="w-full bg-orange-500 text-white py-2.5 rounded-md hover:bg-orange-600 disabled:opacity-50 font-medium text-sm"
      >
        {loading ? "Deep Searching..." : "Deep Search (Max Volume)"}
      </button>
      <p className="text-xs text-gray-400 text-center -mt-2">
        Runs all queries with pagination for maximum results
      </p>
    </div>
  );
}
