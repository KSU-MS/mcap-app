export interface McapLog {
    id: number;
    recovery_status?: string;
    parse_status?: string;
    captured_at?: string;
    duration_seconds?: number;
    channel_count?: number;
    channels?: string[];
    channels_summary?: string[];
    cars?: string[];
    drivers?: string[];
    event_types?: string[];
    locations?: string[];
    map_preview_uri?: string;
    map_data_available?: boolean;
    notes?: string;
    tags?: string[];
    created_at?: string;
    updated_at?: string;
}

export interface PaginatedResponse<T> {
    count: number;
    results: T[];
    next?: string | null;
    previous?: string | null;
}

export interface LogFilters {
    search?: string;
    start_date?: string;
    end_date?: string;
    car?: string;
    event_type?: string;
    driver?: string;
    location?: string;
    channel?: string;
    tag?: string;
    page?: number;
}

export type DownloadFormat = 'mcap' | 'csv_omni' | 'csv_tvn' | 'ld';
export type ResampleRateHz = 10 | 20 | 50 | 100;

export interface GeoJsonGeometry {
    type: string;
    coordinates?: unknown;
}

export interface GeoJsonFeature {
    type: string;
    geometry?: GeoJsonGeometry | null;
    properties?: Record<string, unknown>;
}

export interface GeoJsonFeatureCollection {
    type: string;
    features?: GeoJsonFeature[];
}
