'use client';

import dynamic from 'next/dynamic';
import { Dialog, DialogContent, DialogTitle } from '@/components/ui/dialog';
import type { GeoJsonFeatureCollection } from '@/lib/mcap/types';

const MapView = dynamic(() => import('./MapView'), { ssr: false });

interface Props {
    open: boolean;
    logId: number | null;
    geoJsonData: GeoJsonFeatureCollection | null;
    onClose: () => void;
}

export function MapModal({ open, logId, geoJsonData, onClose }: Props) {
    return (
        <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
            {geoJsonData && (
                <DialogContent className="max-w-6xl w-full h-[90vh] flex flex-col p-0">
                    <div
                        className="flex items-center px-4 py-3 border-b"
                        style={{ borderColor: 'rgba(42,38,34,0.18)', background: 'rgba(255,255,255,0.3)' }}
                    >
                        <DialogTitle className="font-serif text-base" style={{ color: 'var(--charcoal)' }}>
                            Map View — Log ID {logId}
                        </DialogTitle>
                    </div>
                    <div className="flex-1 relative">
                        <MapView geoJsonData={geoJsonData} />
                    </div>
                </DialogContent>
            )}
        </Dialog>
    );
}
