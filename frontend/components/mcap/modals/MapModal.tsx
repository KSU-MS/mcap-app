'use client';

import dynamic from 'next/dynamic';
import { Dialog, DialogContent, DialogTitle } from '@/components/ui/dialog';

// Full-screen map (no SSR)
const MapComponent = dynamic(
    () => {
        return Promise.resolve().then(() => {
            const React = require('react');
            const L = require('leaflet');
            const { MapContainer, TileLayer, GeoJSON, useMap } = require('react-leaflet');

            if (typeof window !== 'undefined') {
                delete (L.Icon.Default.prototype as any)._getIconUrl;
                L.Icon.Default.mergeOptions({
                    iconRetinaUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.7.1/images/marker-icon-2x.png',
                    iconUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.7.1/images/marker-icon.png',
                    shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.7.1/images/marker-shadow.png',
                });
            }

            const FitBounds = ({ geoJsonData }: { geoJsonData: any }) => {
                const map = useMap();
                React.useEffect(() => {
                    if (geoJsonData && map) {
                        try {
                            const layer = L.geoJSON(geoJsonData as any);
                            const bounds = layer.getBounds();
                            if (bounds.isValid()) map.fitBounds(bounds, { padding: [20, 20] });
                        } catch { }
                    }
                }, [geoJsonData, map]);
                return null;
            };

            return ({ geoJsonData }: { geoJsonData: any }) => {
                const [mounted, setMounted] = React.useState(false);
                React.useEffect(() => { setMounted(true); }, []);

                const geoJsonStyle = { color: '#C38822', weight: 3, opacity: 0.85, fillOpacity: 0.15 };
                const pointToLayer = (feature: any, latlng: L.LatLng) =>
                    L.circleMarker(latlng, { radius: 6, fillColor: '#C38822', color: '#fff', weight: 2, opacity: 1, fillOpacity: 0.9 });

                const onEachFeature = (feature: any, layer: L.Layer) => {
                    if (feature.properties) {
                        const html = Object.keys(feature.properties)
                            .map((k) => `<strong>${k}:</strong> ${feature.properties[k]}`)
                            .join('<br>');
                        layer.bindPopup(html);
                    }
                };

                let center: [number, number] = [0, 0];
                if (geoJsonData?.features?.[0]?.geometry?.coordinates) {
                    const coords = geoJsonData.features[0].geometry.coordinates;
                    if (geoJsonData.features[0].geometry.type === 'Point') center = [coords[1], coords[0]];
                    else if (geoJsonData.features[0].geometry.type === 'LineString' && coords.length > 0)
                        center = [coords[0][1], coords[0][0]];
                }

                if (!mounted) return <div className="w-full h-full flex items-center justify-center text-sm" style={{ color: 'var(--sienna)' }}>Loading map…</div>;

                return (
                    <MapContainer center={center} zoom={13} style={{ height: '100%', width: '100%', zIndex: 0 }} scrollWheelZoom key={`map-${mounted}`}>
                        <TileLayer attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>' url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />
                        {geoJsonData && <GeoJSON data={geoJsonData} style={geoJsonStyle} pointToLayer={pointToLayer} onEachFeature={onEachFeature} />}
                        <FitBounds geoJsonData={geoJsonData} />
                    </MapContainer>
                );
            };
        });
    },
    { ssr: false },
);

interface Props {
    open: boolean;
    logId: number | null;
    geoJsonData: any;
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
                        <MapComponent geoJsonData={geoJsonData} />
                    </div>
                </DialogContent>
            )}
        </Dialog>
    );
}
