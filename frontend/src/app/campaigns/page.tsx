"use client";

import { useEffect, useState, useCallback } from "react";
import ExportButton from "@/components/ExportButton";
import {
  listCampaigns,
  getCampaign,
  createCampaign,
  removeCreatorFromCampaign,
} from "@/lib/api";
import type { Campaign } from "@/lib/api";

export default function CampaignsPage() {
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [selected, setSelected] = useState<Campaign | null>(null);
  const [loading, setLoading] = useState(true);
  const [newName, setNewName] = useState("");
  const [creating, setCreating] = useState(false);

  const loadCampaigns = useCallback(async () => {
    setLoading(true);
    try {
      const data = await listCampaigns();
      setCampaigns(data);
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadCampaigns();
  }, [loadCampaigns]);

  const handleCreate = async () => {
    if (!newName.trim()) return;
    setCreating(true);
    try {
      await createCampaign(newName.trim());
      setNewName("");
      await loadCampaigns();
    } catch {
      alert("Failed to create campaign");
    } finally {
      setCreating(false);
    }
  };

  const handleSelect = async (id: number) => {
    try {
      const data = await getCampaign(id);
      setSelected(data);
    } catch {
      alert("Failed to load campaign");
    }
  };

  const handleRemoveCreator = async (creatorId: number) => {
    if (!selected) return;
    try {
      await removeCreatorFromCampaign(selected.id, creatorId);
      const data = await getCampaign(selected.id);
      setSelected(data);
    } catch {
      alert("Failed to remove creator");
    }
  };

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Campaigns</h1>

      <div className="flex gap-3">
        <input
          type="text"
          value={newName}
          onChange={(e) => setNewName(e.target.value)}
          placeholder="New campaign name..."
          className="border border-gray-300 rounded-md px-4 py-2 text-sm flex-1 max-w-md"
          onKeyDown={(e) => e.key === "Enter" && handleCreate()}
        />
        <button
          onClick={handleCreate}
          disabled={creating || !newName.trim()}
          className="bg-indigo-600 text-white px-4 py-2 rounded-md text-sm hover:bg-indigo-700 disabled:opacity-50"
        >
          Create Campaign
        </button>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="space-y-2">
          <h2 className="text-sm font-medium text-gray-500 uppercase tracking-wide">
            Your Campaigns
          </h2>
          {loading && <p className="text-gray-400 text-sm">Loading...</p>}
          {!loading && campaigns.length === 0 && (
            <p className="text-gray-400 text-sm">No campaigns yet</p>
          )}
          {campaigns.map((camp) => (
            <button
              key={camp.id}
              onClick={() => handleSelect(camp.id)}
              className={`w-full text-left px-4 py-3 rounded-lg border text-sm ${
                selected?.id === camp.id
                  ? "border-indigo-500 bg-indigo-50"
                  : "border-gray-200 bg-white hover:bg-gray-50"
              }`}
            >
              <div className="font-medium">{camp.name}</div>
              <div className="text-xs text-gray-500">
                {camp.creator_count || 0} creators &middot;{" "}
                {new Date(camp.created_at).toLocaleDateString()}
              </div>
            </button>
          ))}
        </div>

        <div className="lg:col-span-2">
          {selected ? (
            <div className="bg-white rounded-lg shadow p-6">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-xl font-semibold">{selected.name}</h2>
                <ExportButton
                  campaignId={selected.id}
                  campaignName={selected.name}
                />
              </div>

              {selected.creators && selected.creators.length > 0 ? (
                <div className="space-y-3">
                  {selected.creators.map((c) => (
                    <div
                      key={c.id}
                      className="flex items-center justify-between border border-gray-100 rounded-lg p-3"
                    >
                      <div className="flex items-center gap-3">
                        <img
                          src={c.avatar_url || "/placeholder-avatar.png"}
                          alt={c.name}
                          className="w-10 h-10 rounded-full object-cover bg-gray-200"
                        />
                        <div>
                          <div className="font-medium text-sm">{c.name}</div>
                          <div className="text-xs text-gray-500">
                            @{c.handle} &middot; {c.platform} &middot;{" "}
                            {(c.follower_count / 1000).toFixed(1)}K &middot;
                            Score: {Math.round(c.overall_score)}
                          </div>
                        </div>
                      </div>
                      <button
                        onClick={() => c.id && handleRemoveCreator(c.id)}
                        className="text-red-500 hover:text-red-700 text-xs"
                      >
                        Remove
                      </button>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-gray-400 text-sm">
                  No creators in this campaign yet. Add creators from the search
                  page.
                </p>
              )}
            </div>
          ) : (
            <div className="text-center py-20 text-gray-400">
              Select a campaign to view details
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
