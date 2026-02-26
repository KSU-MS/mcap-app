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

    const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        const files = Array.from(e.target.files ?? []);
        const mcap = files.filter((f) => f.name.toLowerCase().endsWith('.mcap'));
        if (mcap.length !== files.length) {
            setError('Some files were ignored — only .mcap files are accepted.');
        } else {
            setError(null);
        }
        setSelectedFiles(mcap);
        e.currentTarget.value = '';
    };

    const handleUpload = async () => {
        if (!selectedFiles.length) return;
        setUploading(true);
        setError(null);
        try {
            const ids = await uploadFiles(selectedFiles);
            setSelectedFiles([]);
            onUploaded(ids);
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Upload failed');
        } finally {
            setUploading(false);
        }
    };

    const totalMB = (selectedFiles.reduce((a, f) => a + f.size, 0) / 1024 / 1024).toFixed(2);

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
                            <p>
                                <strong>{selectedFiles.length}</strong> file{selectedFiles.length !== 1 ? 's' : ''} ·{' '}
                                {totalMB} MB
                            </p>
                            <div className="mt-1 space-y-0.5 max-h-20 overflow-y-auto">
                                {selectedFiles.slice(0, 6).map((f, i) => (
                                    <div key={i} className="flex justify-between gap-2 text-xs">
                                        <span className="truncate" style={{ color: 'var(--charcoal)' }}>{f.name}</span>
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
                                {selectedFiles.length > 6 && (
                                    <p className="text-xs" style={{ color: 'var(--sienna)' }}>
                                        +{selectedFiles.length - 6} more
                                    </p>
                                )}
                            </div>
                            <button
                                type="button"
                                className="text-xs mt-1 hover:opacity-70"
                                style={{ color: 'var(--sienna)' }}
                                onClick={() => setSelectedFiles([])}
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
