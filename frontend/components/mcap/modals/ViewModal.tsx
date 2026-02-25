'use client';

import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import type { McapLog } from '@/lib/mcap/types';

interface Props {
    log: McapLog | null;
    open: boolean;
    loading: boolean;
    onClose: () => void;
    onViewMap: (id: number) => void;
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

export function ViewModal({ log, open, loading, onClose, onViewMap }: Props) {
    return (
        <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
            {log && (
                <DialogContent className="max-w-3xl max-h-[90vh] overflow-y-auto">
                    <DialogHeader>
                        <DialogTitle className="font-serif text-lg" style={{ color: 'var(--charcoal)' }}>
                            Log Details — ID {log.id}
                        </DialogTitle>
                    </DialogHeader>

                    {loading ? (
                        <div className="py-8 text-center text-sm" style={{ color: 'var(--sienna)' }}>
                            Loading…
                        </div>
                    ) : (
                        <div className="space-y-5">
                            {/* Core fields grid */}
                            <div className="grid grid-cols-2 gap-x-6 gap-y-3">
                                {[
                                    ['Recovery Status', log.recovery_status],
                                    ['Parse Status', log.parse_status],
                                    ['Captured At', log.captured_at ? new Date(log.captured_at).toLocaleString() : undefined],
                                    ['Duration', log.duration_seconds ? `${log.duration_seconds.toFixed(1)}s` : undefined],
                                    ['Channel Count', log.channel_count],
                                    ['Car(s)', normalizeList(log.cars).join(', ')],
                                    ['Driver(s)', normalizeList(log.drivers).join(', ')],
                                    ['Event Type(s)', normalizeList(log.event_types).join(', ')],
                                    ['Location(s)', normalizeList(log.locations).join(', ')],
                                    ['Created At', log.created_at ? new Date(log.created_at).toLocaleString() : undefined],
                                    ['Updated At', log.updated_at ? new Date(log.updated_at).toLocaleString() : undefined],
                                ].map(([label, value]) => (
                                    <div key={String(label)}>
                                        <p className="text-xs font-semibold uppercase tracking-wide mb-0.5" style={{ color: 'var(--sienna)' }}>
                                            {label}
                                        </p>
                                        {/* Status fields get a badge */}
                                        {(label === 'Recovery Status' || label === 'Parse Status') && value ? (
                                            <span className={statusBadgeClass(String(value))}>{String(value)}</span>
                                        ) : (
                                            <p className="text-sm" style={{ color: 'var(--charcoal)' }}>{String(value ?? '—')}</p>
                                        )}
                                    </div>
                                ))}
                            </div>

                            {/* Channels list */}
                            {log.channels && log.channels.length > 0 && (
                                <div
                                    className="rounded-lg border overflow-hidden"
                                    style={{ borderColor: 'rgba(42,38,34,0.18)', background: 'var(--off-white)' }}
                                >
                                    <div
                                        className="flex justify-between items-center px-4 py-2 border-b"
                                        style={{ borderColor: 'rgba(42,38,34,0.12)', background: 'rgba(255,255,255,0.4)' }}
                                    >
                                        <span className="text-sm font-semibold" style={{ color: 'var(--charcoal)' }}>Channels</span>
                                        <span className="text-xs" style={{ color: 'var(--sienna)' }}>
                                            Count: {log.channel_count ?? log.channels.length}
                                        </span>
                                    </div>
                                    <div className="max-h-52 overflow-y-auto">
                                        <table className="w-full border-collapse">
                                            <tbody>
                                                {log.channels.map((ch, i) => (
                                                    <tr
                                                        key={i}
                                                        className="border-b"
                                                        style={{ borderColor: 'rgba(42,38,34,0.06)' }}
                                                    >
                                                        <td className="py-1.5 px-4 text-xs w-10" style={{ color: 'var(--sienna)' }}>{i + 1}</td>
                                                        <td className="py-1.5 px-4 text-xs font-mono" style={{ color: 'var(--charcoal)' }}>{ch}</td>
                                                    </tr>
                                                ))}
                                            </tbody>
                                        </table>
                                    </div>
                                </div>
                            )}

                            {/* Notes */}
                            {log.notes && (
                                <div>
                                    <p className="text-xs font-semibold uppercase tracking-wide mb-1" style={{ color: 'var(--sienna)' }}>Notes</p>
                                    <p className="text-sm" style={{ color: 'var(--charcoal)' }}>{log.notes}</p>
                                </div>
                            )}

                            {/* View on Map */}
                            <button
                                className="skeuo-btn-ghost w-full justify-center"
                                onClick={() => onViewMap(log.id)}
                            >
                                View on Map
                            </button>
                        </div>
                    )}
                </DialogContent>
            )}
        </Dialog>
    );
}
