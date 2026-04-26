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
  createExportJob, downloadExportJob, fetchActiveExportJobs, fetchCurrentUser, logoutSession,
} from '@/lib/mcap/api';
import type { McapLog, DownloadFormat, ExportJob, GeoJsonFeatureCollection, ResampleRateHz } from '@/lib/mcap/types';

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
  const [authReady, setAuthReady] = useState(false);
  useEffect(() => { setMounted(true); }, []);

  useEffect(() => {
    const checkAuth = async () => {
      try {
        await fetchCurrentUser();
        setAuthReady(true);
      } catch {
        router.replace('/login');
      }
    };
    void checkAuth();
  }, [router]);

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
  const [exportJobs, setExportJobs] = useState<ExportJob[]>([]);

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
  const playChime = useCallback(() => {
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
  }, []);

  // ── Load logs whenever URL params change ──
  const sortExportJobs = useCallback((jobs: ExportJob[]) => {
    const sorted = [...jobs].sort((a, b) => {
      const aTime = new Date(a.updated_at ?? a.created_at ?? 0).getTime();
      const bTime = new Date(b.updated_at ?? b.created_at ?? 0).getTime();
      return bTime - aTime;
    });
    return sorted.slice(0, 10);
  }, []);

  const loadLogs = useCallback(async () => {
    if (!authReady) return;
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
  }, [params.toString(), authReady]);

  useEffect(() => { loadLogs(); }, [loadLogs]);

  // ── Load lookups + DB status on mount ──
  useEffect(() => {
    if (!authReady) return;
    fetchLookups().then(setLookups);
  }, [authReady]);

  useEffect(() => {
    if (!authReady) return;
    fetchActiveExportJobs()
      .then((jobs) => setExportJobs(sortExportJobs(jobs)))
      .catch(() => {
        // Export jobs panel is optional; ignore load errors here.
      });
  }, [authReady, sortExportJobs]);

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
      if (downloadFormat === 'mcap') {
        await bulkDownload(selectedIds, downloadFormat, downloadResampleHz);
        setDownloadOpen(false);
        playChime();
        showToast('Download complete!');
        return;
      }

      const job = await createExportJob(selectedIds, downloadFormat, downloadResampleHz);
      setExportJobs((prev) => {
        const existing = prev.find((item) => item.id === job.id);
        if (existing) {
          return sortExportJobs(prev.map((item) => (item.id === job.id ? { ...item, ...job } : item)));
        }
        return sortExportJobs([job, ...prev]);
      });
      setDownloadOpen(false);
      showToast(`Export job #${job.id} started (${downloadFormat.toUpperCase()})`);
    } catch (err) {
      setDownloadError(err instanceof Error ? err.message : 'Download failed');
    } finally {
      setDownloading(false);
    }
  };

  const handleExportDownload = async (jobId: number) => {
    try {
      await downloadExportJob(jobId);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to download export bundle');
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

  if (!authReady) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <p className="text-sm" style={{ color: 'var(--sienna)' }}>Checking session…</p>
      </div>
    );
  }

  // ══════════════════════════════
  //  RENDER
  // ══════════════════════════════
  return (
    <div className="min-h-screen py-8 px-4 sm:px-8">
      {/* DB status indicator — only render after mount to avoid hydration mismatch */}
      {mounted && (
        <div className="mx-auto mb-3 flex max-w-7xl justify-center">
          <div className="flex flex-wrap items-center justify-center gap-2">
          <div
            className="flex items-center gap-1.5 text-xs rounded-full px-2.5 py-1"
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
          </div>
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
        <div className="mb-7 flex items-start justify-between gap-3">
          <div>
          <h1 className="font-serif text-4xl" style={{ color: 'var(--charcoal)', fontWeight: 900, letterSpacing: '-0.03em' }}>
            MCAP{' '}
            <span style={{ color: 'var(--ochre)' }}>Log Manager</span>
          </h1>
          <p className="text-sm mt-1" style={{ color: 'var(--sienna)' }}>
            Upload, browse, and annotate MCAP telemetry logs.
          </p>
          </div>
          <button
            className="skeuo-btn-ghost"
            onClick={async () => {
              try {
                await logoutSession();
              } finally {
                router.replace('/login');
              }
            }}
          >
            Sign out
          </button>
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

        {exportJobs.length > 0 && (
          <div className="skeuo-card mb-6">
            <div className="skeuo-card-header">
              <h2 className="font-serif font-semibold text-base" style={{ color: 'var(--charcoal)' }}>
                Recent Exports
              </h2>
            </div>
            <div className="skeuo-card-content space-y-2">
              {exportJobs.map((job) => {
                const totalItems = job.total_items ?? job.requested_ids?.length ?? 0;
                const completedItems = job.completed_items ?? 0;
                const failedItems = job.failed_items ?? 0;
                const doneItems = completedItems + failedItems;
                const progress = typeof job.progress_percent === 'number'
                  ? Math.max(0, Math.min(100, Math.round(job.progress_percent)))
                  : totalItems > 0
                    ? Math.max(0, Math.min(100, Math.round((doneItems / totalItems) * 100)))
                    : (job.status === 'completed' || job.status === 'completed_with_errors' ? 100 : 0);
                const formatLabel = job.format.toUpperCase();
                const ready = job.status === 'completed' || job.status === 'completed_with_errors';
                const statusTone = ready
                  ? { background: 'rgba(46,107,62,0.12)', color: 'var(--success)', border: '1px solid rgba(46,107,62,0.25)' }
                  : job.status === 'failed'
                    ? { background: 'rgba(179,58,46,0.1)', color: 'var(--danger)', border: '1px solid rgba(179,58,46,0.25)' }
                    : { background: 'rgba(195,136,34,0.12)', color: 'var(--warning-text)', border: '1px solid rgba(122,90,26,0.25)' };

                return (
                  <div
                    key={job.id}
                    className="rounded-md px-3 py-2.5"
                    style={{ background: 'rgba(42,38,34,0.04)', border: '1px solid rgba(42,38,34,0.12)' }}
                  >
                    <div className="flex flex-wrap items-center gap-2 justify-between">
                      <div className="min-w-0">
                        <p className="text-sm font-semibold" style={{ color: 'var(--charcoal)' }}>
                          Export #{job.id} · {formatLabel} · {job.resample_hz}Hz
                        </p>
                        <p className="text-xs" style={{ color: 'var(--sienna)' }}>
                          {totalItems > 0
                            ? `${doneItems}/${totalItems} items processed`
                            : 'Waiting for item stats...'}
                        </p>
                      </div>
                      <div className="flex items-center gap-2">
                        <span className="inline-flex items-center rounded-full px-2 py-0.5 text-xs font-semibold" style={statusTone}>
                          {job.status.replaceAll('_', ' ')}
                        </span>
                        {ready && (
                          <button
                            className="skeuo-btn-primary"
                            onClick={() => handleExportDownload(job.id)}
                          >
                            Download ZIP
                          </button>
                        )}
                      </div>
                    </div>
                    <div className="mt-2 h-1.5 w-full rounded-full" style={{ background: 'rgba(42,38,34,0.12)' }}>
                      <div
                        className="h-full rounded-full transition-all"
                        style={{
                          width: `${progress}%`,
                          background: ready ? 'var(--success)' : 'var(--ochre)',
                        }}
                      />
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}

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
