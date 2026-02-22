'use client';

import { memo, useCallback } from 'react';
import { Eye, Pencil } from 'lucide-react';
import type { McapLog } from '@/lib/mcap/types';

interface Props {
    logs: McapLog[];
    selectedIds: number[];
    processingIds: number[];
    currentPage: number;
    totalPages: number;
    totalCount: number;
    pageSize: number;
    loading: boolean;
    onToggleAll: () => void;
    onToggle: (id: number) => void;
    onView: (id: number) => void;
    onEdit: (id: number) => void;
    onPageChange: (page: number) => void;
}

function normalizeList(v: unknown): string[] {
    if (!Array.isArray(v)) return [];
    return v.filter((x): x is string => typeof x === 'string' && x.trim() !== '');
}

function statusBadgeClass(status: string) {
    const s = status.toLowerCase();
    if (s === 'completed' || s === 'success') return 'badge-success';
    if (s === 'pending') return 'badge-pending';
    if (s.startsWith('error')) return 'badge-error';
    return 'badge-info';
}

const LogRow = memo(function LogRow({
    log,
    selected,
    processing,
    onToggle,
    onView,
    onEdit,
}: {
    log: McapLog;
    selected: boolean;
    processing: boolean;
    onToggle: () => void;
    onView: () => void;
    onEdit: () => void;
}) {
    return (
        <tr className={selected ? 'selected-row' : ''}>
            {/* Checkbox */}
            <td className="py-2 px-3 w-9">
                <input
                    type="checkbox"
                    className="skeuo-checkbox"
                    checked={selected}
                    onChange={onToggle}
                    aria-label={`Select log ${log.id}`}
                />
            </td>

            {/* ID */}
            <td style={{ color: 'var(--charcoal)' }} className="font-mono text-xs font-medium">{log.id}</td>

            {/* Date */}
            <td className="text-xs" style={{ color: 'var(--charcoal-mid)' }}>
                {log.captured_at ? new Date(log.captured_at).toLocaleDateString() : '—'}
            </td>

            {/* Time */}
            <td className="text-xs" style={{ color: 'var(--charcoal-mid)' }}>
                {log.captured_at ? new Date(log.captured_at).toLocaleTimeString() : '—'}
            </td>

            {/* Duration */}
            <td className="text-xs" style={{ color: 'var(--charcoal-mid)' }}>
                {log.duration_seconds ? `${log.duration_seconds.toFixed(1)}s` : '—'}
            </td>

            {/* Channels */}
            <td className="text-xs" style={{ color: 'var(--charcoal-mid)' }}>
                {log.channel_count ?? '—'}
            </td>

            {/* Status */}
            <td>
                <div className="flex flex-col gap-1">
                    {log.recovery_status && (
                        <span className={statusBadgeClass(log.recovery_status)}>
                            Rec: {log.recovery_status}
                        </span>
                    )}
                    {log.parse_status && (
                        <span className={statusBadgeClass(log.parse_status)}>
                            Parse: {log.parse_status}
                        </span>
                    )}
                    {processing && (
                        <span className="badge-pending flex items-center gap-1">
                            <span className="inline-block h-2.5 w-2.5 rounded-full border-2 border-current border-t-transparent animate-spin" />
                            Processing
                        </span>
                    )}
                </div>
            </td>

            {/* Car */}
            <td className="text-xs" style={{ color: 'var(--charcoal-mid)' }}>
                {normalizeList(log.cars).join(', ') || '—'}
            </td>

            {/* Driver */}
            <td className="text-xs" style={{ color: 'var(--charcoal-mid)' }}>
                {normalizeList(log.drivers).join(', ') || '—'}
            </td>

            {/* Event */}
            <td className="text-xs" style={{ color: 'var(--charcoal-mid)' }}>
                {normalizeList(log.event_types).join(', ') || '—'}
            </td>

            {/* Tags */}
            <td className="max-w-[160px]">
                {log.tags && log.tags.length > 0 ? (
                    <span className="flex flex-wrap gap-1">
                        {log.tags.map((t) => (
                            <span key={t} className="tag-pill">{t}</span>
                        ))}
                    </span>
                ) : '—'}
            </td>

            {/* Actions */}
            <td>
                <div className="flex items-center gap-1.5">
                    <button
                        className="skeuo-icon-btn"
                        title="View details"
                        onClick={onView}
                    >
                        <Eye className="h-3.5 w-3.5" />
                    </button>
                    <button
                        className="skeuo-icon-btn"
                        title="Edit log"
                        onClick={onEdit}
                    >
                        <Pencil className="h-3.5 w-3.5" />
                    </button>
                </div>
            </td>
        </tr>
    );
});

export function LogsTable({
    logs,
    selectedIds,
    processingIds,
    currentPage,
    totalPages,
    totalCount,
    pageSize,
    loading,
    onToggleAll,
    onToggle,
    onView,
    onEdit,
    onPageChange,
}: Props) {
    const allSelected = logs.length > 0 && logs.every((l) => selectedIds.includes(l.id));

    if (loading && logs.length === 0) {
        return (
            <div className="py-12 text-center text-sm" style={{ color: 'var(--sienna)' }}>
                Loading logs…
            </div>
        );
    }

    if (!loading && logs.length === 0) {
        return (
            <div className="py-12 text-center text-sm" style={{ color: 'var(--sienna)' }}>
                No logs found. Upload a .mcap file to get started.
            </div>
        );
    }

    return (
        <>
            <div className="overflow-x-auto">
                <table className="table-skeuo">
                    <thead>
                        <tr>
                            <th className="py-2 px-3 w-9">
                                <input
                                    type="checkbox"
                                    className="skeuo-checkbox"
                                    checked={allSelected}
                                    onChange={onToggleAll}
                                    aria-label="Select all"
                                />
                            </th>
                            <th>ID</th>
                            <th>Date</th>
                            <th>Time</th>
                            <th>Duration</th>
                            <th>Ch.</th>
                            <th>Status</th>
                            <th>Car</th>
                            <th>Driver</th>
                            <th>Event</th>
                            <th>Tags</th>
                            <th>Actions</th>
                        </tr>
                    </thead>
                    <tbody>
                        {logs.map((log) => (
                            <LogRow
                                key={log.id}
                                log={log}
                                selected={selectedIds.includes(log.id)}
                                processing={processingIds.includes(log.id)}
                                onToggle={() => onToggle(log.id)}
                                onView={() => onView(log.id)}
                                onEdit={() => onEdit(log.id)}
                            />
                        ))}
                    </tbody>
                </table>
            </div>

            {/* Pagination */}
            <div className="mt-4 flex flex-col sm:flex-row items-center justify-between gap-3">
                <p className="text-xs" style={{ color: 'var(--sienna)' }}>
                    Page <strong style={{ color: 'var(--charcoal)' }}>{currentPage}</strong> of{' '}
                    <strong style={{ color: 'var(--charcoal)' }}>{totalPages}</strong>
                </p>
                <div className="flex items-center gap-1 flex-wrap">
                    <button
                        className="pagination-btn"
                        disabled={currentPage <= 1 || loading}
                        onClick={() => onPageChange(currentPage - 1)}
                    >
                        Prev
                    </button>

                    {buildPages(currentPage, totalPages).map((p, i) =>
                        p === 'dots' ? (
                            <span key={`d-${i}`} className="px-2 text-xs" style={{ color: 'var(--sienna)' }}>…</span>
                        ) : (
                            <button
                                key={p}
                                className={`pagination-btn${p === currentPage ? ' active' : ''}`}
                                disabled={loading}
                                onClick={() => onPageChange(p as number)}
                            >
                                {p}
                            </button>
                        ),
                    )}

                    <button
                        className="pagination-btn"
                        disabled={currentPage >= totalPages || loading}
                        onClick={() => onPageChange(currentPage + 1)}
                    >
                        Next
                    </button>
                </div>
            </div>
        </>
    );
}

function buildPages(current: number, total: number): (number | 'dots')[] {
    if (total <= 7) return Array.from({ length: total }, (_, i) => i + 1);
    const pages: (number | 'dots')[] = [];
    const start = Math.max(2, current - 2);
    const end = Math.min(total - 1, current + 2);
    pages.push(1);
    if (start > 2) pages.push('dots');
    for (let p = start; p <= end; p++) pages.push(p);
    if (end < total - 1) pages.push('dots');
    pages.push(total);
    return pages;
}
