'use client';

import { useState, memo } from 'react';
import { Loader2 } from 'lucide-react';

interface MapCellProps {
    logId: number;
    mapPreviewUri?: string;
    mapDataAvailable?: boolean;
    onViewMap: (id: number) => void;
}

/**
 * A static CSS map thumbnail for every table row.
 * Clicking fetches GeoJSON and opens the full Leaflet MapModal.
 * No rough_point / coordinate parsing needed.
 */
export const MapCell = memo(function MapCell({ logId, mapPreviewUri, mapDataAvailable = true, onViewMap }: MapCellProps) {
    const [loading, setLoading] = useState(false);

    const handleClick = async () => {
        setLoading(true);
        try {
            await onViewMap(logId);
        } finally {
            setLoading(false);
        }
    };

    if (!mapDataAvailable) {
        return (
            <div
                style={{
                    width: 82,
                    height: 64,
                    borderRadius: '0.4rem',
                    overflow: 'hidden',
                    border: '1px solid rgba(42,38,34,0.2)',
                    background: 'rgba(42,38,34,0.04)',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    padding: '4px 6px',
                }}
                title="No map available"
                aria-label={`No map available for log ${logId}`}
            >
                <span style={{ fontSize: '0.62rem', lineHeight: 1.2, textAlign: 'center', color: 'var(--sienna)' }}>
                    No map available.
                </span>
            </div>
        );
    }

    return (
        <button
            type="button"
            onClick={handleClick}
            disabled={loading}
            title="View map"
            aria-label={`View map for log ${logId}`}
            style={{
                width: 82,
                height: 64,
                borderRadius: '0.4rem',
                overflow: 'hidden',
                border: '1px solid rgba(42,38,34,0.2)',
                background: 'var(--parchment)',
                cursor: loading ? 'wait' : 'pointer',
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'stretch',
                padding: 0,
                position: 'relative',
                transition: 'box-shadow .13s, transform .1s',
                boxShadow: '0 1px 3px rgba(42,38,34,0.1)',
                flexShrink: 0,
            }}
            onMouseEnter={(e) => {
                if (!loading) {
                    (e.currentTarget as HTMLElement).style.boxShadow = '0 3px 10px rgba(42,38,34,0.18)';
                    (e.currentTarget as HTMLElement).style.transform = 'translateY(-1px)';
                }
            }}
            onMouseLeave={(e) => {
                (e.currentTarget as HTMLElement).style.boxShadow = '0 1px 3px rgba(42,38,34,0.1)';
                (e.currentTarget as HTMLElement).style.transform = 'none';
            }}
        >
            {mapPreviewUri ? (
                <img
                    src={mapPreviewUri}
                    alt={`Map preview for log ${logId}`}
                    loading="lazy"
                    style={{
                        flex: 1,
                        width: '100%',
                        height: '100%',
                        objectFit: 'cover',
                        display: 'block',
                    }}
                />
            ) : (
                <div
                    style={{
                        flex: 1,
                        position: 'relative',
                        overflow: 'hidden',
                        backgroundImage: [
                            'linear-gradient(rgba(42,38,34,0.12) 1px, transparent 1px)',
                            'linear-gradient(90deg, rgba(42,38,34,0.12) 1px, transparent 1px)',
                            'linear-gradient(transparent 42%, rgba(195,136,34,0.35) 42%, rgba(195,136,34,0.35) 58%, transparent 58%)',
                            'linear-gradient(135deg, transparent 35%, rgba(195,136,34,0.22) 35%, rgba(195,136,34,0.22) 42%, transparent 42%)',
                        ].join(', '),
                        backgroundSize: '14px 14px, 14px 14px, 100% 100%, 100% 100%',
                    }}
                />
            )}

            {loading && (
                <div
                    style={{
                        position: 'absolute',
                        inset: 0,
                        background: 'rgba(255,255,255,0.55)',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                    }}
                >
                    <Loader2 className="animate-spin" style={{ width: 14, height: 14, color: 'var(--ochre-dark)' }} />
                </div>
            )}
        </button>
    );
});
