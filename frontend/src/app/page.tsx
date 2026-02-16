"use client";

import { useState, useCallback, useEffect } from "react";
import SearchFilters from "@/components/SearchFilters";
import CreatorCard from "@/components/CreatorCard";
import CreatorTable from "@/components/CreatorTable";
import { searchCreators, addCreatorToCampaign, listCampaigns, getDatabase } from "@/lib/api";
import type { Creator, SearchParams, Campaign } from "@/lib/api";

export default function Home() {
  const [creators, setCreators] = useState<Creator[]>([]);
  const [total, setTotal] = useState(0);
  const [dbTotal, setDbTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [view, setView] = useState<"cards" | "table">("cards");
  const [searched, setSearched] = useState(false);

  // Campaign modal state
  const [showCampaignModal, setShowCampaignModal] = useState(false);
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [selectedCreator, setSelectedCreator] = useState<Creator | null>(null);

  // Fetch DB total on mount
  useEffect(() => {
    getDatabase({ page_size: 1 })
      .then((data) => setDbTotal(data.db_total))
      .catch(() => {});
  }, []);

  const handleSearch = useCallback(async (params: SearchParams) => {
    setLoading(true);
    setError(null);
    try {
      const data = await searchCreators(params);
      setCreators(data.creators);
      setTotal(data.total);
      setDbTotal(data.db_total);
      setSearched(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Search failed");
    } finally {
      setLoading(false);
    }
  }, []);

  const handleAddToCampaign = useCallback(async (creator: Creator) => {
    setSelectedCreator(creator);
    try {
      const camps = await listCampaigns();
      setCampaigns(camps);
    } catch {
      setCampaigns([]);
    }
    setShowCampaignModal(true);
  }, []);

  const handleConfirmAdd = useCallback(
    async (campaignId: number) => {
      if (!selectedCreator?.id) return;
      try {
        await addCreatorToCampaign(campaignId, selectedCreator.id);
        setShowCampaignModal(false);
        setSelectedCreator(null);
      } catch (err) {
        alert(err instanceof Error ? err.message : "Failed to add creator");
      }
    },
    [selectedCreator]
  );

  return (
    <div className="flex gap-6">
      <aside className="w-72 flex-shrink-0">
        <SearchFilters onSearch={handleSearch} loading={loading} />

        {dbTotal > 0 && (
          <div className="mt-4 bg-indigo-50 border border-indigo-200 rounded-lg p-4 text-center">
            <p className="text-2xl font-bold text-indigo-700">{dbTotal}</p>
            <p className="text-xs text-indigo-500">creators in database</p>
          </div>
        )}
      </aside>

      <section className="flex-1">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h1 className="text-2xl font-bold">UGC Creator Search</h1>
            <p className="text-gray-500 text-sm">
              Find women creators aged 40-60 across social platforms
            </p>
          </div>
          {searched && (
            <div className="flex items-center gap-3">
              <span className="text-sm text-gray-500">{total} results</span>
              <div className="flex border border-gray-300 rounded-md overflow-hidden">
                <button
                  onClick={() => setView("cards")}
                  className={`px-3 py-1.5 text-sm ${
                    view === "cards"
                      ? "bg-indigo-600 text-white"
                      : "bg-white text-gray-600"
                  }`}
                >
                  Cards
                </button>
                <button
                  onClick={() => setView("table")}
                  className={`px-3 py-1.5 text-sm ${
                    view === "table"
                      ? "bg-indigo-600 text-white"
                      : "bg-white text-gray-600"
                  }`}
                >
                  Table
                </button>
              </div>
            </div>
          )}
        </div>

        {error && (
          <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-md mb-4">
            {error}
          </div>
        )}

        {!searched && !loading && (
          <div className="text-center py-20 text-gray-400">
            <p className="text-lg">Use the filters to search for creators</p>
          </div>
        )}

        {searched && creators.length === 0 && !loading && (
          <div className="text-center py-20 text-gray-400">
            <p className="text-lg">No creators found matching your criteria</p>
          </div>
        )}

        {view === "cards" ? (
          <div className="space-y-4">
            {creators.map((c, i) => (
              <CreatorCard
                key={c.external_id || i}
                creator={c}
                onAddToCampaign={handleAddToCampaign}
              />
            ))}
          </div>
        ) : (
          <CreatorTable
            creators={creators}
            onAddToCampaign={handleAddToCampaign}
          />
        )}
      </section>

      {showCampaignModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg shadow-xl p-6 w-96">
            <h3 className="text-lg font-semibold mb-4">
              Add to Campaign
            </h3>
            <p className="text-sm text-gray-500 mb-4">
              Add {selectedCreator?.name} to a campaign:
            </p>
            {campaigns.length === 0 ? (
              <p className="text-sm text-gray-400 mb-4">
                No campaigns yet. Create one on the Campaigns page.
              </p>
            ) : (
              <div className="space-y-2 mb-4 max-h-60 overflow-y-auto">
                {campaigns.map((camp) => (
                  <button
                    key={camp.id}
                    onClick={() => handleConfirmAdd(camp.id)}
                    className="w-full text-left px-4 py-2 rounded border border-gray-200 hover:bg-indigo-50 hover:border-indigo-300 text-sm"
                  >
                    {camp.name}
                  </button>
                ))}
              </div>
            )}
            <button
              onClick={() => setShowCampaignModal(false)}
              className="w-full text-sm text-gray-500 hover:text-gray-700 py-2"
            >
              Cancel
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
