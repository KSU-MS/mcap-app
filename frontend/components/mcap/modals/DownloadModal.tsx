'use client';

import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from '@/components/ui/dialog';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Label } from '@/components/ui/label';
import type { DownloadFormat, ResampleRateHz } from '@/lib/mcap/types';

const RESAMPLE_RATES: ResampleRateHz[] = [10, 20, 50, 100];

interface Props {
    open: boolean;
    selectedCount: number;
    format: DownloadFormat;
    resampleHz: ResampleRateHz;
    downloading: boolean;
    error: string | null;
    onFormatChange: (f: DownloadFormat) => void;
    onResampleChange: (hz: ResampleRateHz) => void;
    onClose: () => void;
    onDownload: () => void;
}

export function DownloadModal({
    open, selectedCount, format, resampleHz, downloading, error,
    onFormatChange, onResampleChange, onClose, onDownload,
}: Props) {
    const showResampleSelector = format !== 'mcap';

    return (
        <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
            <DialogContent className="max-w-sm">
                <DialogHeader>
                    <DialogTitle className="font-serif text-lg" style={{ color: 'var(--charcoal)' }}>
                        Download
                    </DialogTitle>
                    <DialogDescription style={{ color: 'var(--sienna)' }}>
                        {selectedCount} log{selectedCount !== 1 ? 's' : ''} selected
                    </DialogDescription>
                </DialogHeader>

                <div className="space-y-3">
                    <div>
                        <Label className="text-xs font-semibold uppercase tracking-wide mb-1 block" style={{ color: 'var(--sienna)' }}>
                            Format
                        </Label>
                        <Select value={format} onValueChange={(v) => onFormatChange(v as DownloadFormat)}>
                            <SelectTrigger className="w-full" style={{ background: 'var(--off-white)' }}>
                                <SelectValue placeholder="Select format" />
                            </SelectTrigger>
                            <SelectContent style={{ background: 'var(--off-white)' }}>
                                <SelectItem value="mcap">MCAP (original)</SelectItem>
                                <SelectItem value="csv_omni">CSV (omni)</SelectItem>
                                <SelectItem value="csv_tvn">CSV (tvn)</SelectItem>
                                <SelectItem value="ld">LD (i2) (not yet)</SelectItem>
                            </SelectContent>
                        </Select>
                    </div>

                    {showResampleSelector && (
                        <div>
                            <Label className="text-xs font-semibold uppercase tracking-wide mb-1 block" style={{ color: 'var(--sienna)' }}>
                                Resample rate
                            </Label>
                            <Select
                                value={String(resampleHz)}
                                onValueChange={(v) => onResampleChange(Number(v) as ResampleRateHz)}
                                disabled={downloading}
                            >
                                <SelectTrigger className="w-full" style={{ background: 'var(--off-white)' }}>
                                    <SelectValue placeholder="Select rate" />
                                </SelectTrigger>
                                <SelectContent style={{ background: 'var(--off-white)' }}>
                                    {RESAMPLE_RATES.map((rate) => (
                                        <SelectItem key={rate} value={String(rate)}>{rate} Hz</SelectItem>
                                    ))}
                                </SelectContent>
                            </Select>
                            <p className="mt-1 text-xs" style={{ color: 'var(--sienna)' }}>
                                Higher rates are smoother but produce larger files.
                            </p>
                        </div>
                    )}

                    {error && <p className="text-sm" style={{ color: 'var(--danger)' }}>{error}</p>}

                    {downloading && (
                        <div
                            className="flex items-center gap-2 rounded-md px-3 py-2.5 text-sm"
                            style={{ background: 'var(--warning-bg)', color: 'var(--warning-text)', border: '1px solid rgba(122,90,26,0.25)' }}
                        >
                            <span className="inline-block h-3.5 w-3.5 rounded-full border-2 border-current border-t-transparent animate-spin" />
                            {format === 'mcap'
                                ? 'Preparing ZIP…'
                                : `Converting to ${format.replace('csv_', '').toUpperCase()} at ${resampleHz}Hz and zipping…`}
                        </div>
                    )}
                </div>

                <DialogFooter className="gap-2 mt-2">
                    <button className="skeuo-btn-ghost" onClick={onClose} disabled={downloading}>Cancel</button>
                    <button className="skeuo-btn-primary" onClick={onDownload} disabled={downloading}>
                        {downloading ? 'Preparing…' : 'Download'}
                    </button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}
