'use client';

import { useEffect, useMemo } from 'react';
import { GeoJSON, MapContainer, TileLayer, useMap } from 'react-leaflet';
import L, { type LatLngExpression, type Layer } from 'leaflet';
import type { GeoJsonFeature, GeoJsonFeatureCollection } from '@/lib/mcap/types';

type LeafletGeoJsonInput = Parameters<typeof L.geoJSON>[0];
type GeoJsonLayerData = React.ComponentProps<typeof GeoJSON>['data'];

interface MapViewProps {
    geoJsonData: GeoJsonFeatureCollection;
}

function FitBounds({ geoJsonData }: MapViewProps) {
    const map = useMap();

    useEffect(() => {
        try {
            const layer = L.geoJSON(geoJsonData as LeafletGeoJsonInput);
            const bounds = layer.getBounds();
            if (bounds.isValid()) {
                map.fitBounds(bounds, { padding: [20, 20] });
            }
        } catch {
            // ignore invalid geometry payloads
        }
    }, [geoJsonData, map]);

    return null;
}

function getCenter(geoJsonData: GeoJsonFeatureCollection): LatLngExpression {
    const firstFeature = geoJsonData.features?.[0];
    const geometry = firstFeature?.geometry;
    const coordinates = geometry?.coordinates;

    if (geometry?.type === 'Point' && Array.isArray(coordinates) && coordinates.length >= 2) {
        const [lng, lat] = coordinates;
        if (typeof lat === 'number' && typeof lng === 'number') return [lat, lng];
    }

    if (geometry?.type === 'LineString' && Array.isArray(coordinates) && coordinates.length > 0) {
        const firstPoint = coordinates[0];
        if (Array.isArray(firstPoint) && firstPoint.length >= 2) {
            const [lng, lat] = firstPoint;
            if (typeof lat === 'number' && typeof lng === 'number') return [lat, lng];
        }
    }

    return [0, 0];
}

export default function MapView({ geoJsonData }: MapViewProps) {
    const center = useMemo(() => getCenter(geoJsonData), [geoJsonData]);

    const geoJsonStyle = { color: '#C38822', weight: 3, opacity: 0.85, fillOpacity: 0.15 };

    const pointToLayer = (_feature: GeoJsonFeature | undefined, latlng: L.LatLng) => (
        L.circleMarker(latlng, { radius: 6, fillColor: '#C38822', color: '#fff', weight: 2, opacity: 1, fillOpacity: 0.9 })
    );

    const onEachFeature = (feature: GeoJsonFeature, layer: Layer) => {
        if (!feature.properties) return;

        const html = Object.entries(feature.properties)
            .map(([key, value]) => `<strong>${key}:</strong> ${String(value)}`)
            .join('<br>');

        if (html) {
            layer.bindPopup(html);
        }
    };

    return (
        <MapContainer center={center} zoom={13} style={{ height: '100%', width: '100%', zIndex: 0 }} scrollWheelZoom>
            <TileLayer
                attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
                url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
            />
            <GeoJSON
                data={geoJsonData as GeoJsonLayerData}
                style={geoJsonStyle}
                pointToLayer={pointToLayer}
                onEachFeature={onEachFeature}
            />
            <FitBounds geoJsonData={geoJsonData} />
        </MapContainer>
    );
}
