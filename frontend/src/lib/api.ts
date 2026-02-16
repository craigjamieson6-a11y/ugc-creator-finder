const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export interface Creator {
  id?: number;
  external_id: string;
  name: string;
  platform: string;
  handle: string;
  profile_url: string;
  avatar_url: string;
  follower_count: number;
  following_count?: number;
  engagement_rate: number;
  avg_likes?: number;
  avg_comments?: number;
  avg_views?: number;
  post_count?: number;
  bio: string;
  niche_tags: string[];
  estimated_age_range: string | null;
  gender: string | null;
  demographic_confidence: string;
  audience_demographics?: Record<string, unknown>;
  overall_score: number;
  engagement_score: number;
  quality_score: number;
  relevance_score: number;
  tier: string;
  country: string | null;
  last_updated?: string;
}

export interface Campaign {
  id: number;
  name: string;
  filters_json: Record<string, unknown>;
  created_at: string;
  creator_count?: number;
  creators?: Array<Creator & { notes: string; added_at: string }>;
}

export interface SearchParams {
  platform?: string;
  niche?: string;
  min_followers?: number;
  max_followers?: number;
  min_engagement?: number;
  gender?: string;
  age_min?: number;
  age_max?: number;
  country?: string;
  sort_by?: string;
  page?: number;
  page_size?: number;
  deep_search?: boolean;
}

export interface SearchResult {
  creators: Creator[];
  total: number;
  db_total: number;
  page: number;
}

async function fetchApi(path: string, options?: RequestInit) {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    throw new Error(`API error: ${res.status} ${res.statusText}`);
  }
  return res.json();
}

export async function searchCreators(
  params: SearchParams
): Promise<SearchResult> {
  const query = new URLSearchParams();
  Object.entries(params).forEach(([key, val]) => {
    if (val !== undefined && val !== null && val !== "") {
      query.set(key, String(val));
    }
  });
  return fetchApi(`/api/creators/search?${query.toString()}`);
}

export async function getDatabase(
  params: { gender?: string; sort_by?: string; page?: number; page_size?: number } = {}
): Promise<SearchResult> {
  const query = new URLSearchParams();
  Object.entries(params).forEach(([key, val]) => {
    if (val !== undefined && val !== null && val !== "") {
      query.set(key, String(val));
    }
  });
  return fetchApi(`/api/creators/database?${query.toString()}`);
}

export async function getCreator(id: number): Promise<Creator> {
  return fetchApi(`/api/creators/${id}`);
}

export async function resetSeenCreators(): Promise<{ status: string; message: string }> {
  return fetchApi("/api/creators/reset-seen", { method: "POST" });
}

export async function listCampaigns(): Promise<Campaign[]> {
  return fetchApi("/api/campaigns");
}

export async function getCampaign(id: number): Promise<Campaign> {
  return fetchApi(`/api/campaigns/${id}`);
}

export async function createCampaign(
  name: string,
  filters: Record<string, unknown> = {}
): Promise<Campaign> {
  return fetchApi("/api/campaigns", {
    method: "POST",
    body: JSON.stringify({ name, filters_json: filters }),
  });
}

export async function addCreatorToCampaign(
  campaignId: number,
  creatorId: number,
  notes: string = ""
): Promise<void> {
  await fetchApi(`/api/campaigns/${campaignId}/creators`, {
    method: "POST",
    body: JSON.stringify({ creator_id: creatorId, notes }),
  });
}

export async function removeCreatorFromCampaign(
  campaignId: number,
  creatorId: number
): Promise<void> {
  await fetchApi(`/api/campaigns/${campaignId}/creators/${creatorId}`, {
    method: "DELETE",
  });
}

export function getExportUrl(campaignId: number): string {
  return `${API_BASE}/api/campaigns/${campaignId}/export`;
}
