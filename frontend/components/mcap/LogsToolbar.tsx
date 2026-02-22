'use client';

interface Props {
    selectedCount: number;
    totalCount: number;
    loading: boolean;
    onDownload: () => void;
    onDelete: () => void;
    onRefresh: () => void;
}

export function LogsToolbar({
    selectedCount, totalCount, loading, onDownload, onDelete, onRefresh,
}: Props) {
    return (
        <div className="flex justify-between items-center mb-4">
            <div className="flex items-center gap-3">
                <h2 className="font-serif font-semibold text-base" style={{ color: 'var(--charcoal)' }}>
                    MCAP Logs
                </h2>
                {selectedCount > 0 && (
                    <span
                        className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold"
                        style={{
                            background: 'rgba(195,136,34,0.12)',
                            color: 'var(--sienna)',
                            border: '1px solid rgba(195,136,34,0.3)',
                        }}
                    >
                        {selectedCount} selected
                    </span>
                )}
                <span className="text-xs" style={{ color: 'var(--sienna)' }}>
                    {totalCount} total
                </span>
            </div>

            <div className="flex gap-2 flex-wrap justify-end">
                {selectedCount > 0 && (
                    <>
                        <button
                            className="skeuo-btn-primary"
                            onClick={onDownload}
                            disabled={loading}
                        >
                            Download {selectedCount > 1 ? `${selectedCount} files` : 'file'}
                        </button>
                        <button
                            className="skeuo-btn-danger"
                            onClick={onDelete}
                            disabled={loading}
                        >
                            Delete {selectedCount > 1 ? `${selectedCount} logs` : 'log'}
                        </button>
                    </>
                )}
                <button
                    className="skeuo-btn-ghost"
                    onClick={onRefresh}
                    disabled={loading}
                >
                    {loading ? 'Refreshing…' : 'Refresh'}
                </button>
            </div>
        </div>
    );
}
