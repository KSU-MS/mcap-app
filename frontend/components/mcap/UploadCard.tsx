'use client';

import { useState } from 'react';
import { uploadFiles } from '@/lib/mcap/api';

interface Props {
    onUploaded: (ids: number[]) => void;
    processingCount: number;
}

export function UploadCard({ onUploaded, processingCount }: Props) {
    const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
    const [uploading, setUploading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [showAllSelected, setShowAllSelected] = useState(false);

    const formatFileSize = (bytes: number) => {
        if (bytes < 1024) return `${bytes} B`;
        const units = ['KB', 'MB', 'GB'];
        let value = bytes / 1024;
        let unitIndex = 0;
        while (value >= 1024 && unitIndex < units.length - 1) {
            value /= 1024;
            unitIndex += 1;
        }
        return `${value.toFixed(value >= 100 ? 0 : value >= 10 ? 1 : 2)} ${units[unitIndex]}`;
    };

    const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        const files = Array.from(e.target.files ?? []);
        const mcap = files.filter((f) => f.name.toLowerCase().endsWith('.mcap'));
        if (mcap.length !== files.length) {
            setError('Some files were ignored — only .mcap files are accepted.');
        } else {
            setError(null);
        }
        setSelectedFiles(mcap);
        setShowAllSelected(false);
        e.currentTarget.value = '';
    };

    const handleUpload = async () => {
        if (!selectedFiles.length) return;
        setUploading(true);
        setError(null);
        try {
            const ids = await uploadFiles(selectedFiles);
            setSelectedFiles([]);
            setShowAllSelected(false);
            onUploaded(ids);
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Upload failed');
        } finally {
            setUploading(false);
        }
    };

    const totalBytes = selectedFiles.reduce((a, f) => a + f.size, 0);
    const visibleCount = showAllSelected ? selectedFiles.length : Math.min(selectedFiles.length, 8);
    const visibleFiles = selectedFiles.slice(0, visibleCount);

    return (
        <div className="skeuo-card mb-6">
            <div className="skeuo-card-header">
                <h2 className="font-serif font-semibold text-base" style={{ color: 'var(--charcoal)' }}>
                    Upload MCAP Files
                </h2>
            </div>
            <div className="skeuo-card-content">
                <div className="flex flex-col sm:flex-row gap-4 items-start sm:items-center">
                    {/* File picker */}
                    <label className="cursor-pointer">
                        <input
                            type="file"
                            accept=".mcap"
                            multiple
                            onChange={handleFileChange}
                            className="hidden"
                            disabled={uploading}
                        />
                        <span className="skeuo-btn-ghost">Select MCAP Files</span>
                    </label>

                    {/* Selected file summary */}
                    {selectedFiles.length > 0 && (
                        <div className="flex-1 text-sm" style={{ color: 'var(--charcoal-mid)' }}>
                            <div
                                className="rounded-md px-3 py-2"
                                style={{ background: 'rgba(42,38,34,0.04)', border: '1px solid rgba(42,38,34,0.14)' }}
                            >
                                <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs">
                                    <span>
                                        <strong>{selectedFiles.length}</strong> file{selectedFiles.length !== 1 ? 's' : ''}
                                    </span>
                                    <span>total {formatFileSize(totalBytes)}</span>
                                    <span>avg {formatFileSize(Math.round(totalBytes / selectedFiles.length))}</span>
                                </div>

                                <div className="mt-2 max-h-36 overflow-y-auto space-y-1.5 pr-1">
                                    {visibleFiles.map((f, i) => (
                                        <div
                                            key={`${f.name}-${f.lastModified}-${i}`}
                                            className="flex items-center gap-2 rounded px-2 py-1.5 text-xs"
                                            style={{ background: 'rgba(232,224,212,0.72)', border: '1px solid rgba(42,38,34,0.09)' }}
                                        >
                                            <span className="block h-1.5 w-1.5 rounded-full bg-[var(--ochre)] shrink-0" />
                                            <span className="truncate" style={{ color: 'var(--charcoal)', flex: 1, minWidth: 0 }} title={f.name}>
                                                {f.name}
                                            </span>
                                            <span
                                                className="shrink-0"
                                                style={{ color: 'var(--sienna)', fontVariantNumeric: 'tabular-nums' }}
                                            >
                                                {formatFileSize(f.size)}
                                            </span>
                                            <button
                                                type="button"
                                                style={{ color: 'var(--sienna)' }}
                                                className="hover:opacity-70 shrink-0"
                                                onClick={() => setSelectedFiles((p) => p.filter((_, idx) => idx !== i))}
                                                disabled={uploading}
                                            >
                                                Remove
                                            </button>
                                        </div>
                                    ))}
                                </div>

                                {selectedFiles.length > visibleCount && (
                                    <button
                                        type="button"
                                        className="text-xs mt-2 hover:opacity-70"
                                        style={{ color: 'var(--sienna)' }}
                                        onClick={() => setShowAllSelected(true)}
                                        disabled={uploading}
                                    >
                                        Show {selectedFiles.length - visibleCount} more
                                    </button>
                                )}
                                {showAllSelected && selectedFiles.length > 8 && (
                                    <button
                                        type="button"
                                        className="text-xs mt-2 ml-3 hover:opacity-70"
                                        style={{ color: 'var(--sienna)' }}
                                        onClick={() => setShowAllSelected(false)}
                                        disabled={uploading}
                                    >
                                        Show less
                                    </button>
                                )}
                            </div>
                            <button
                                type="button"
                                className="text-xs mt-1 hover:opacity-70"
                                style={{ color: 'var(--sienna)' }}
                                onClick={() => {
                                    setSelectedFiles([]);
                                    setShowAllSelected(false);
                                }}
                                disabled={uploading}
                            >
                                Clear all
                            </button>
                        </div>
                    )}

                    <button
                        className="skeuo-btn-primary"
                        onClick={handleUpload}
                        disabled={selectedFiles.length === 0 || uploading}
                    >
                        {uploading ? 'Uploading…' : 'Upload'}
                    </button>
                </div>

                {processingCount > 0 && (
                    <div
                        className="mt-4 rounded-md px-4 py-2.5 text-sm flex items-center gap-2"
                        style={{ background: 'var(--warning-bg)', color: 'var(--warning-text)', border: '1px solid rgba(122,90,26,0.25)' }}
                    >
                        <span className="inline-block h-3.5 w-3.5 rounded-full border-2 border-current border-t-transparent animate-spin" />
                        Processing {processingCount} file{processingCount !== 1 ? 's' : ''}…
                    </div>
                )}

                {error && (
                    <div
                        className="mt-4 rounded-md px-4 py-2.5 text-sm"
                        style={{ background: 'rgba(179,58,46,0.08)', color: 'var(--danger)', border: '1px solid rgba(179,58,46,0.25)' }}
                    >
                        {error}
                    </div>
                )}
            </div>
        </div>
    );
}
