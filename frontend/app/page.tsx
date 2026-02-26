'use client';

import { useState, useEffect, useCallback } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { Suspense } from 'react';
import 'leaflet/dist/leaflet.css';

import { UploadCard } from '@/components/mcap/UploadCard';
import { LogsFilters } from '@/components/mcap/LogsFilters';
import { LogsToolbar } from '@/components/mcap/LogsToolbar';
import { LogsTable } from '@/components/mcap/LogsTable';
import { ViewModal } from '@/components/mcap/modals/ViewModal';
import { EditModal } from '@/components/mcap/modals/EditModal';
import { DeleteConfirmModal } from '@/components/mcap/modals/DeleteConfirmModal';
import { DownloadModal } from '@/components/mcap/modals/DownloadModal';
import { MapModal } from '@/components/mcap/modals/MapModal';

import {
  fetchLogs, fetchLog, fetchGeoJson, fetchLookups,
  updateLog, deleteLogs, bulkDownload, checkDbStatus,
} from '@/lib/mcap/api';
import type { McapLog, DownloadFormat, GeoJsonFeatureCollection, ResampleRateHz } from '@/lib/mcap/types';

const PAGE_SIZE = 10;

// ──────────────────────────────────────────────────────────────
// The actual page content (needs Suspense for useSearchParams)
// ──────────────────────────────────────────────────────────────
function McapDashboard() {
  const router = useRouter();
  const params = useSearchParams();

  // ── Derived filter values from URL ──
  const currentPage = parseInt(params.get('page') ?? '1', 10);
  const filters = {
    search: params.get('search') ?? '',
    start_date: params.get('start_date') ?? '',
    end_date: params.get('end_date') ?? '',
    car: params.get('car') ?? '',
    event_type: params.get('event_type') ?? '',
    driver: params.get('driver') ?? '',
    location: params.get('location') ?? '',
    channel: params.get('channel') ?? '',
    tag: params.get('tag') ?? '',
    page: currentPage,
  };

  // ── Server data ──
  const [logs, setLogs] = useState<McapLog[]>([]);
  const [totalCount, setTotalCount] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // ── Lookups ──
  const [lookups, setLookups] = useState({
    cars: [] as string[], drivers: [] as string[],
    eventTypes: [] as string[], locations: [] as string[],
    tags: [] as string[], channels: [] as string[],
  });

  // ── DB indicator ──
  const [dbStatus, setDbStatus] = useState<'checking' | 'connected' | 'disconnected'>('checking');
  const [mounted, setMounted] = useState(false);
  useEffect(() => { setMounted(true); }, []);

  // ── Selection ──
  const [selectedIds, setSelectedIds] = useState<number[]>([]);
  const [processingIds, setProcessingIds] = useState<number[]>([]);

  // ── Modals ──
  const [viewLog, setViewLog] = useState<McapLog | null>(null);
  const [viewOpen, setViewOpen] = useState(false);
  const [viewLoading, setViewLoading] = useState(false);

  const [editLog, setEditLog] = useState<McapLog | null>(null);
  const [editOpen, setEditOpen] = useState(false);
  const [saving, setSaving] = useState(false);

  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deleteIds, setDeleteIds] = useState<number[]>([]);
  const [deleting, setDeleting] = useState(false);

  const [downloadOpen, setDownloadOpen] = useState(false);
  const [downloadFormat, setDownloadFormat] = useState<DownloadFormat>('mcap');
  const [downloadResampleHz, setDownloadResampleHz] = useState<ResampleRateHz>(20);
  const [downloading, setDownloading] = useState(false);
  const [downloadError, setDownloadError] = useState<string | null>(null);

  const [mapOpen, setMapOpen] = useState(false);
  const [mapLogId, setMapLogId] = useState<number | null>(null);
  const [geoJsonData, setGeoJsonData] = useState<GeoJsonFeatureCollection | null>(null);

  const [toastMsg, setToastMsg] = useState<string | null>(null);

  // ── Toast helper ──
  const showToast = useCallback((msg: string) => {
    setToastMsg(msg);
    setTimeout(() => setToastMsg(null), 4000);
  }, []);

  // ── Chime ──
  const playChime = () => {
    try {
      const AudioContextClass = window.AudioContext
        ?? (window as Window & { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
      if (!AudioContextClass) return;
      const ctx = new AudioContextClass();
      const tone = (freq: number, start: number, dur: number) => {
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.connect(gain); gain.connect(ctx.destination);
        osc.frequency.value = freq; osc.type = 'sine';
        gain.gain.setValueAtTime(0.14, start);
        gain.gain.exponentialRampToValueAtTime(0.01, start + dur);
        osc.start(start); osc.stop(start + dur);
      };
      tone(523.25, 0, 0.12); tone(659.25, 0.14, 0.2);
    } catch { }
  };

  // ── Load logs whenever URL params change ──
  const loadLogs = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const { logs: data, total } = await fetchLogs(filters);
      setLogs(data);
      setTotalCount(total);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load logs');
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [params.toString()]);

  useEffect(() => { loadLogs(); }, [loadLogs]);

  // ── Load lookups + DB status on mount ──
  useEffect(() => {
    fetchLookups().then(setLookups);
  }, []);

  useEffect(() => {
    const run = async () => {
      const ok = await checkDbStatus();
      setDbStatus(ok ? 'connected' : 'disconnected');
    };
    run();
    const interval = setInterval(run, 15_000);
    return () => clearInterval(interval);
  }, []);

  // ── Poll processing IDs ──
  useEffect(() => {
    if (!processingIds.length) return;
    let cancelled = false;
    const interval = setInterval(async () => {
      const results = await Promise.all(
        processingIds.map(async (id) => {
          try {
            const log = await fetchLog(id);
            return { id, log };
          } catch { return { id, log: null }; }
        }),
      );
      if (cancelled) return;
      setLogs((prev) => {
        const byId = new Map(results.filter((r) => r.log).map((r) => [r.id, r.log!]));
        return prev.map((l) => byId.has(l.id) ? { ...l, ...byId.get(l.id) } : l);
      });
      const isTerminal = (s?: string) => {
        const v = s?.toLowerCase();
        return v === 'completed' || v === 'success' || v?.startsWith('error');
      };
      setProcessingIds((prev) =>
        prev.filter((id) => {
          const found = results.find((r) => r.id === id)?.log;
          return !found || !(isTerminal(found.recovery_status) && isTerminal(found.parse_status));
        }),
      );
    }, 2500);
    return () => { cancelled = true; clearInterval(interval); };
  }, [processingIds]);

  // ── Page navigation via URL ──
  const goToPage = (page: number) => {
    const next = new URLSearchParams(params.toString());
    next.set('page', String(Math.max(1, Math.min(page, totalPages))));
    setSelectedIds([]);
    router.push(`?${next.toString()}`, { scroll: false });
  };

  const totalPages = Math.max(1, Math.ceil(totalCount / PAGE_SIZE));

  // ── Selection ──
  const toggleSelect = (id: number) =>
    setSelectedIds((prev) => prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]);
  const toggleAll = () => {
    const allIds = logs.map((l) => l.id);
    const all = allIds.every((id) => selectedIds.includes(id)) && allIds.length > 0;
    setSelectedIds(all ? selectedIds.filter((id) => !allIds.includes(id)) : [...new Set([...selectedIds, ...allIds])]);
  };

  // ── View ──
  const openView = async (id: number) => {
    setViewOpen(true);
    setViewLoading(true);
    try {
      const log = await fetchLog(id);
      setViewLog(log);
    } finally {
      setViewLoading(false);
    }
  };

  // ── Edit ──
  const openEdit = async (id: number) => {
    const log = await fetchLog(id);
    setEditLog(log);
    setEditOpen(true);
  };

  const handleSave = async (form: {
    cars: string[]; drivers: string[]; event_types: string[];
    locations: string[]; notes: string; tags: string[];
  }) => {
    if (!editLog) return;
    setSaving(true);
    try {
      await updateLog(editLog.id, form);
      setEditOpen(false);
      setEditLog(null);
      showToast('Log updated');
      loadLogs();
      fetchLookups().then(setLookups);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Save failed');
    } finally {
      setSaving(false);
    }
  };

  // ── Delete (selection-driven) ──
  const openDelete = () => {
    if (!selectedIds.length) return;
    setDeleteIds([...selectedIds]);
    setDeleteOpen(true);
  };

  const handleDelete = async () => {
    setDeleting(true);
    try {
      await deleteLogs(deleteIds);
      setDeleteOpen(false);
      setSelectedIds([]);
      showToast(`Deleted ${deleteIds.length} log${deleteIds.length !== 1 ? 's' : ''}`);
      loadLogs();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Delete failed');
    } finally {
      setDeleting(false);
    }
  };

  // ── Download ──
  const openDownload = () => {
    if (!selectedIds.length) return;
    setDownloadError(null);
    setDownloadOpen(true);
  };

  const handleDownload = async () => {
    setDownloading(true);
    setDownloadError(null);
    try {
      await bulkDownload(selectedIds, downloadFormat, downloadResampleHz);
      setDownloadOpen(false);
      playChime();
      showToast('Download complete!');
    } catch (err) {
      setDownloadError(err instanceof Error ? err.message : 'Download failed');
    } finally {
      setDownloading(false);
    }
  };

  // ── Map ──
  const openMap = async (id: number) => {
    try {
      const data = await fetchGeoJson(id);
      setGeoJsonData(data);
      setMapLogId(id);
      setMapOpen(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load map');
    }
  };

  // ══════════════════════════════
  //  RENDER
  // ══════════════════════════════
  return (
    <div className="min-h-screen py-8 px-4 sm:px-8">
      {/* DB status indicator — only render after mount to avoid hydration mismatch */}
      {mounted && (
        <div
          className="fixed top-4 right-4 z-50 flex items-center gap-1.5 text-xs rounded-full px-2.5 py-1"
          style={{
            background: 'rgba(232,224,212,0.92)',
            border: '1px solid rgba(42,38,34,0.2)',
            color: 'var(--sienna)',
            backdropFilter: 'blur(4px)',
          }}
          title={`Database: ${dbStatus}`}
        >
          <span
            className={`block h-2 w-2 rounded-full ${dbStatus === 'connected' ? 'bg-green-500' :
              dbStatus === 'disconnected' ? 'bg-red-500' : 'bg-amber-400'
              }`}
          />
          {dbStatus}
        </div>
      )}

      {/* Toast */}
      {mounted && toastMsg && (
        <div
          className="fixed bottom-6 right-6 z-50 flex items-center gap-2 rounded-lg px-4 py-3 text-sm font-medium shadow-lg"
          role="status"
          style={{
            background: 'var(--parchment)',
            border: '1px solid rgba(46,107,62,0.3)',
            color: 'var(--success)',
            boxShadow: '0 4px 20px rgba(42,38,34,0.2)',
          }}
        >
          <span className="inline-flex h-2 w-2 rounded-full bg-green-500" />
          {toastMsg}
        </div>
      )}

      <div className="max-w-7xl mx-auto">
        {/* Header */}
        <div className="mb-7">
          <h1 className="font-serif text-4xl" style={{ color: 'var(--charcoal)', fontWeight: 900, letterSpacing: '-0.03em' }}>
            MCAP{' '}
            <span style={{ color: 'var(--ochre)' }}>Log Manager</span>
          </h1>
          <p className="text-sm mt-1" style={{ color: 'var(--sienna)' }}>
            Upload, browse, and annotate MCAP telemetry logs.
          </p>
        </div>

        {/* Error banner */}
        {error && (
          <div
            className="mb-5 rounded-lg px-4 py-3 text-sm flex items-start gap-2"
            style={{ background: 'rgba(179,58,46,0.08)', color: 'var(--danger)', border: '1px solid rgba(179,58,46,0.24)' }}
          >
            <span className="mr-1 mt-0.5 shrink-0">⚠</span>
            <span>{error}</span>
            <button className="ml-auto text-xs opacity-60 hover:opacity-100" onClick={() => setError(null)}>✕</button>
          </div>
        )}

        {/* Upload */}
        <UploadCard
          processingCount={processingIds.length}
          onUploaded={(ids) => {
            setProcessingIds((p) => [...new Set([...p, ...ids])]);
            loadLogs();
          }}
        />

        {/* Logs card */}
        <div className="skeuo-card">
          <div className="skeuo-card-header">
            <LogsToolbar
              selectedCount={selectedIds.length}
              totalCount={totalCount}
              loading={loading}
              onDownload={openDownload}
              onDelete={openDelete}
              onRefresh={loadLogs}
            />
            <LogsFilters lookups={lookups} />
          </div>

          <div className="skeuo-card-content">
            <LogsTable
              logs={logs}
              selectedIds={selectedIds}
              processingIds={processingIds}
              currentPage={currentPage}
              totalPages={totalPages}
              loading={loading}
              onToggleAll={toggleAll}
              onToggle={toggleSelect}
              onView={openView}
              onEdit={openEdit}
              onViewMap={openMap}
              onPageChange={goToPage}
            />
          </div>
        </div>
      </div>

      {/* Modals */}
      <ViewModal
        log={viewLog}
        open={viewOpen}
        loading={viewLoading}
        onClose={() => { setViewOpen(false); setViewLog(null); }}
        onViewMap={(id) => { setViewOpen(false); openMap(id); }}
      />
      <EditModal
        log={editLog}
        open={editOpen}
        saving={saving}
        lookups={lookups}
        onClose={() => { setEditOpen(false); setEditLog(null); }}
        onSave={handleSave}
      />
      <DeleteConfirmModal
        ids={deleteIds}
        open={deleteOpen}
        deleting={deleting}
        onClose={() => setDeleteOpen(false)}
        onConfirm={handleDelete}
      />
      <DownloadModal
        open={downloadOpen}
        selectedCount={selectedIds.length}
        format={downloadFormat}
        resampleHz={downloadResampleHz}
        downloading={downloading}
        error={downloadError}
        onFormatChange={setDownloadFormat}
        onResampleChange={setDownloadResampleHz}
        onClose={() => setDownloadOpen(false)}
        onDownload={handleDownload}
      />
      <MapModal
        open={mapOpen}
        logId={mapLogId}
        geoJsonData={geoJsonData}
        onClose={() => { setMapOpen(false); setGeoJsonData(null); }}
      />
    </div>
  );
}

// ──────────────────────────────────────────────────────────────
// Default export wraps in Suspense (required for useSearchParams)
// ──────────────────────────────────────────────────────────────
export default function Home() {
  return (
    <Suspense fallback={
      <div className="min-h-screen flex items-center justify-center">
        <p className="text-sm" style={{ color: 'var(--sienna)' }}>Loading…</p>
      </div>
    }>
      <McapDashboard />
    </Suspense>
  );
}
