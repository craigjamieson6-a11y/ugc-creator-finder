"use client";

import { useState, useCallback, useEffect, useMemo } from "react";
import SearchFilters from "@/components/SearchFilters";
import CreatorCard from "@/components/CreatorCard";
import CreatorTable from "@/components/CreatorTable";
import { searchCreators, addCreatorToCampaign, listCampaigns, getDatabase, resetSeenCreators } from "@/lib/api";
import type { Creator, SearchParams, Campaign } from "@/lib/api";

export default function Home() {
  const [creators, setCreators] = useState<Creator[]>([]);
  const [total, setTotal] = useState(0);
  const [dbTotal, setDbTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [loadingSeconds, setLoadingSeconds] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [view, setView] = useState<"cards" | "table">("cards");
  const [searched, setSearched] = useState(false);

  // Campaign modal state
  const [showCampaignModal, setShowCampaignModal] = useState(false);
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [selectedCreator, setSelectedCreator] = useState<Creator | null>(null);

  // Reset confirmation state
  const [showResetConfirm, setShowResetConfirm] = useState(false);

  // Fetch DB total on mount
  useEffect(() => {
    getDatabase({ page_size: 1 })
      .then((data) => setDbTotal(data.db_total))
      .catch(() => {});
  }, []);

  // Split creators by tier
  const { established, emerging } = useMemo(() => {
    const established: Creator[] = [];
    const emerging: Creator[] = [];
    for (const c of creators) {
      if (c.tier === "established") {
        established.push(c);
      } else {
        emerging.push(c);
      }
    }
    return { established, emerging };
  }, [creators]);

  const handleSearch = useCallback(async (params: SearchParams) => {
    setLoading(true);
    setLoadingSeconds(0);
    setError(null);
    const timer = setInterval(() => setLoadingSeconds((s) => s + 1), 1000);
    try {
      const data = await searchCreators(params);
      setCreators(data.creators);
      setTotal(data.total);
      setDbTotal(data.db_total);
      setSearched(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Search failed");
    } finally {
      clearInterval(timer);
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

  const handleResetSeen = useCallback(async () => {
    try {
      await resetSeenCreators();
      setShowResetConfirm(false);
    } catch (err) {
      alert(err instanceof Error ? err.message : "Failed to reset");
    }
  }, []);

  const renderCreatorSection = (sectionCreators: Creator[], title: string, badgeColor: string) => {
    if (sectionCreators.length === 0) return null;

    return (
      <div className="mb-8">
        <div className="flex items-center gap-2 mb-3">
          <h2 className="text-lg font-semibold text-gray-800">{title}</h2>
          <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${badgeColor}`}>
            {sectionCreators.length}
          </span>
        </div>
        {view === "cards" ? (
          <div className="space-y-4">
            {sectionCreators.map((c, i) => (
              <CreatorCard
                key={c.external_id || i}
                creator={c}
                onAddToCampaign={handleAddToCampaign}
              />
            ))}
          </div>
        ) : (
          <CreatorTable
            creators={sectionCreators}
            onAddToCampaign={handleAddToCampaign}
          />
        )}
      </div>
    );
  };

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

        <button
          onClick={() => setShowResetConfirm(true)}
          className="mt-3 w-full text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg py-2 hover:bg-red-100"
        >
          Reset Seen Creators
        </button>
      </aside>

      <section className="flex-1">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h1 className="text-2xl font-bold">UGC Creator Search</h1>
            <p className="text-gray-500 text-sm">
              Find creators across social platforms
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

        {loading && (
          <div className="text-center py-20">
            <div className="inline-block animate-spin rounded-full h-8 w-8 border-4 border-indigo-200 border-t-indigo-600 mb-4"></div>
            <p className="text-lg text-gray-600">Searching creators...</p>
            <p className="text-sm text-gray-400 mt-1">{loadingSeconds}s elapsed — this can take 15-30 seconds</p>
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

        {searched && creators.length > 0 && (
          <>
            {renderCreatorSection(established, "Established Creators", "bg-green-100 text-green-800")}
            {renderCreatorSection(emerging, "Emerging Creators", "bg-blue-100 text-blue-800")}
          </>
        )}
      </section>

      {/* Campaign Modal */}
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

      {/* Reset Seen Confirmation Modal */}
      {showResetConfirm && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg shadow-xl p-6 w-96">
            <h3 className="text-lg font-semibold mb-2">
              Reset Seen Creators?
            </h3>
            <p className="text-sm text-gray-500 mb-4">
              This will clear the de-duplication history. Previously seen creators
              will appear again in future searches.
            </p>
            <div className="flex gap-3">
              <button
                onClick={handleResetSeen}
                className="flex-1 bg-red-600 text-white py-2 rounded-md hover:bg-red-700 text-sm font-medium"
              >
                Reset
              </button>
              <button
                onClick={() => setShowResetConfirm(false)}
                className="flex-1 bg-gray-100 text-gray-700 py-2 rounded-md hover:bg-gray-200 text-sm"
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
