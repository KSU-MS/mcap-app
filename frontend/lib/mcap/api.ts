import type {
    McapLog,
    PaginatedResponse,
    LogFilters,
    DownloadFormat,
    GeoJsonFeatureCollection,
} from './types';

const configuredApiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL?.trim();

export const API_BASE_URL = (configuredApiBaseUrl && configuredApiBaseUrl.length > 0
    ? configuredApiBaseUrl
    : '/api'
).replace(/\/+$/, '');

function withApiBase(path?: string): string | undefined {
    if (!path) return undefined;
    if (path.startsWith('http://') || path.startsWith('https://')) return path;
    if (path.startsWith('/')) return `${API_BASE_URL}${path}`;
    return `${API_BASE_URL}/${path}`;
}

function normalizeLog(log: McapLog): McapLog {
    return {
        ...log,
        map_preview_uri: withApiBase(log.map_preview_uri),
    };
}

function getCookie(name: string): string | null {
    if (typeof document === 'undefined') return null;
    const prefix = `${name}=`;
    const parts = document.cookie.split(';');
    for (const rawPart of parts) {
        const part = rawPart.trim();
        if (part.startsWith(prefix)) {
            return decodeURIComponent(part.slice(prefix.length));
        }
    }
    return null;
}

let csrfPrimed = false;

async function ensureCsrfCookie(): Promise<void> {
    if (csrfPrimed && getCookie('csrftoken')) return;
    const response = await fetch(`${API_BASE_URL}/auth/csrf/`, {
        method: 'GET',
        credentials: 'include',
    });
    if (response.ok) csrfPrimed = true;
}

interface ApiFetchOptions extends RequestInit {
    skipCsrf?: boolean;
}

async function apiFetch(url: string, options: ApiFetchOptions = {}): Promise<Response> {
    const method = (options.method ?? 'GET').toUpperCase();
    const isUnsafe = !['GET', 'HEAD', 'OPTIONS', 'TRACE'].includes(method);

    if (isUnsafe && !options.skipCsrf) {
        await ensureCsrfCookie();
    }

    const headers = new Headers(options.headers ?? {});
    if (isUnsafe && !options.skipCsrf) {
        const csrfToken = getCookie('csrftoken');
        if (csrfToken) headers.set('X-CSRFToken', csrfToken);
    }

    return fetch(url, {
        ...options,
        headers,
        credentials: 'include',
    });
}

async function getErrorMessage(response: Response, fallback: string): Promise<string> {
    try {
        const data = await response.json();
        return data.detail ?? data.error ?? data.message ?? fallback;
    } catch {
        return fallback;
    }
}

export interface AuthUser {
    id: number;
    username: string;
    email: string;
    is_staff: boolean;
    is_superuser: boolean;
    workspace_ids?: number[];
    default_workspace_id?: number | null;
}

export async function fetchCurrentUser(): Promise<AuthUser> {
    const res = await apiFetch(`${API_BASE_URL}/auth/me/`);
    if (!res.ok) {
        throw new Error(await getErrorMessage(res, `Failed to fetch current user: ${res.statusText}`));
    }
    return res.json();
}

export async function loginWithPassword(username: string, password: string): Promise<AuthUser> {
    await ensureCsrfCookie();
    const csrfToken = getCookie('csrftoken');
    const headers: HeadersInit = { 'Content-Type': 'application/json' };
    if (csrfToken) {
        headers['X-CSRFToken'] = csrfToken;
    }
    const res = await apiFetch(`${API_BASE_URL}/auth/login/`, {
        method: 'POST',
        headers,
        body: JSON.stringify({ username, password }),
        skipCsrf: true,
    });
    if (!res.ok) {
        throw new Error(await getErrorMessage(res, `Login failed: ${res.statusText}`));
    }
    return res.json();
}

export async function logoutSession(): Promise<void> {
    const res = await apiFetch(`${API_BASE_URL}/auth/logout/`, { method: 'POST' });
    if (!res.ok && res.status !== 401 && res.status !== 403) {
        throw new Error(await getErrorMessage(res, `Logout failed: ${res.statusText}`));
    }
}

/** Fetch a paginated + filtered list of logs */
export async function fetchLogs(filters: LogFilters): Promise<{ logs: McapLog[]; total: number }> {
    const params = new URLSearchParams();
    params.set('page', String(filters.page ?? 1));
    if (filters.search?.trim()) params.set('search', filters.search.trim());
    if (filters.start_date?.trim()) params.set('start_date', filters.start_date.trim());
    if (filters.end_date?.trim()) params.set('end_date', filters.end_date.trim());
    if (filters.car?.trim()) params.set('car', filters.car.trim());
    if (filters.event_type?.trim()) params.set('event_type', filters.event_type.trim());
    if (filters.driver?.trim()) params.set('driver', filters.driver.trim());
    if (filters.location?.trim()) params.set('location', filters.location.trim());
    if (filters.channel?.trim()) params.set('channel', filters.channel.trim());
    if (filters.tag?.trim()) params.set('tag', filters.tag.trim());

    const res = await apiFetch(`${API_BASE_URL}/mcap-logs/?${params.toString()}`);
    if (!res.ok) throw new Error(await getErrorMessage(res, `Failed to fetch logs: ${res.statusText}`));
    const data = await res.json();

    if (Array.isArray(data)) return { logs: data.map(normalizeLog), total: data.length };
    const paginated = data as PaginatedResponse<McapLog>;
    return { logs: (paginated.results ?? []).map(normalizeLog), total: paginated.count ?? 0 };
}

/** Fetch a single log by ID */
export async function fetchLog(id: number): Promise<McapLog> {
    const res = await apiFetch(`${API_BASE_URL}/mcap-logs/${id}/`);
    if (!res.ok) throw new Error(await getErrorMessage(res, `Failed to fetch log ${id}: ${res.statusText}`));
    return normalizeLog(await res.json());
}

/** Fetch GeoJSON for a log */
export async function fetchGeoJson(id: number): Promise<GeoJsonFeatureCollection> {
    const res = await apiFetch(`${API_BASE_URL}/mcap-logs/${id}/geojson`);
    if (!res.ok) throw new Error(await getErrorMessage(res, `Failed to fetch GeoJSON: ${res.statusText}`));
    return await res.json();
}

/** PATCH or PUT a log */
export async function updateLog(
    id: number,
    body: Partial<Pick<McapLog, 'cars' | 'drivers' | 'event_types' | 'locations' | 'notes' | 'tags'>>,
    method: 'PATCH' | 'PUT' = 'PATCH',
): Promise<McapLog> {
    const res = await apiFetch(`${API_BASE_URL}/mcap-logs/${id}/`, {
        method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
    });
    if (!res.ok) {
        throw new Error(await getErrorMessage(res, `Update failed: ${res.statusText}`));
    }
    return res.json();
}

/** DELETE a single log */
export async function deleteLog(id: number): Promise<void> {
    const res = await apiFetch(`${API_BASE_URL}/mcap-logs/${id}/`, { method: 'DELETE' });
    if (!res.ok) {
        throw new Error(await getErrorMessage(res, `Delete failed: ${res.statusText}`));
    }
}

/** DELETE multiple logs in parallel */
export async function deleteLogs(ids: number[]): Promise<void> {
    const results = await Promise.allSettled(ids.map((id) => deleteLog(id)));
    const failed = results.filter((r) => r.status === 'rejected');
    if (failed.length > 0) {
        throw new Error(`${failed.length} deletion(s) failed`);
    }
}

/** Upload one or more .mcap files; returns created log IDs */
export async function uploadFiles(files: File[]): Promise<number[]> {
    const formData = new FormData();
    for (const f of files) formData.append('files', f);
    const res = await apiFetch(`${API_BASE_URL}/mcap-logs/batch-upload/`, {
        method: 'POST',
        body: formData,
    });
    if (!res.ok) {
        throw new Error(await getErrorMessage(res, `Upload failed: ${res.statusText}`));
    }
    const payload = (await res.json().catch(() => null)) as { results?: Array<{ id?: number }> } | null;
    if (!payload?.results) return [];
    return payload.results
        .map((result) => result.id)
        .filter((id): id is number => typeof id === 'number');
}

/** Download MCAP file for a single log */
export async function downloadLog(id: number): Promise<void> {
    const res = await apiFetch(`${API_BASE_URL}/mcap-logs/${id}/download`);
    if (!res.ok) throw new Error(await getErrorMessage(res, `Download failed: ${res.statusText}`));
    const contentDisposition = res.headers.get('Content-Disposition');
    let filename = `mcap-log-${id}.mcap`;
    if (contentDisposition) {
        const m = contentDisposition.match(/filename="?(.+)"?/i);
        if (m) filename = m[1];
    }
    const blob = await res.blob();
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    window.URL.revokeObjectURL(url);
    document.body.removeChild(a);
}

/** Bulk download logs as a ZIP */
export async function bulkDownload(ids: number[], format: DownloadFormat, resampleHz?: number): Promise<void> {
    const payload: { ids: number[]; format: DownloadFormat; resample_hz?: number } = { ids, format };
    if (format !== 'mcap' && typeof resampleHz === 'number') {
        payload.resample_hz = resampleHz;
    }

    const res = await apiFetch(`${API_BASE_URL}/mcap-logs/download/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
    });
    if (!res.ok) {
        throw new Error(await getErrorMessage(res, `Failed to download: ${res.statusText}`));
    }
    const blob = await res.blob();
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `mcap_logs_${format}.zip`;
    document.body.appendChild(a);
    a.click();
    window.URL.revokeObjectURL(url);
    document.body.removeChild(a);
}

/** Fetch distinct lookup lists for filter dropdowns */
export async function fetchLookups(): Promise<{
    cars: string[];
    drivers: string[];
    eventTypes: string[];
    locations: string[];
    tags: string[];
    channels: string[];
}> {
    const normalize = (values: unknown): string[] => {
        if (!Array.isArray(values)) return [];
        const seen = new Set<string>();
        const out: string[] = [];
        for (const v of values) {
            if (typeof v !== 'string') continue;
            const item = v.trim();
            if (!item) continue;
            const key = item.toLowerCase();
            if (seen.has(key)) continue;
            seen.add(key);
            out.push(item);
        }
        return out;
    };

    try {
        const [carRes, driverRes, eventRes, locationRes, tagRes, channelRes] = await Promise.all([
            apiFetch(`${API_BASE_URL}/mcap-logs/car-names/`),
            apiFetch(`${API_BASE_URL}/mcap-logs/driver-names/`),
            apiFetch(`${API_BASE_URL}/mcap-logs/event-type-names/`),
            apiFetch(`${API_BASE_URL}/mcap-logs/location-names/`),
            apiFetch(`${API_BASE_URL}/mcap-logs/tag-names/`),
            apiFetch(`${API_BASE_URL}/mcap-logs/channel-names/`),
        ]);

        return {
            cars: carRes.ok ? normalize(await carRes.json()) : [],
            drivers: driverRes.ok ? normalize(await driverRes.json()) : [],
            eventTypes: eventRes.ok ? normalize(await eventRes.json()) : [],
            locations: locationRes.ok ? normalize(await locationRes.json()) : [],
            tags: tagRes.ok ? normalize(await tagRes.json()) : [],
            channels: channelRes.ok ? normalize(await channelRes.json()) : [],
        };
    } catch {
        return { cars: [], drivers: [], eventTypes: [], locations: [], tags: [], channels: [] };
    }
}

/** Check if the backend is reachable with current session */
export async function checkDbStatus(): Promise<boolean> {
    try {
        const res = await apiFetch(`${API_BASE_URL}/mcap-logs/?page=1`);
        return res.ok;
    } catch {
        return false;
    }
}
