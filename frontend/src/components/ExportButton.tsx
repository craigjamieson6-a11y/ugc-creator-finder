"use client";

import { getExportUrl } from "@/lib/api";

interface Props {
  campaignId: number;
  campaignName: string;
}

export default function ExportButton({ campaignId, campaignName }: Props) {
  return (
    <a
      href={getExportUrl(campaignId)}
      download={`campaign_${campaignName.replace(/\s+/g, "_")}.csv`}
      className="inline-flex items-center gap-2 bg-white border border-gray-300 text-gray-700 px-4 py-2 rounded-md hover:bg-gray-50 text-sm font-medium"
    >
      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
      </svg>
      Export CSV
    </a>
  );
}
