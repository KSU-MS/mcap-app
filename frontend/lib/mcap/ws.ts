import { API_BASE_URL } from './api';

export type WorkspaceSocketState = 'connecting' | 'connected' | 'reconnecting' | 'disconnected';

export interface WorkspaceSocketMessage {
    event_type?: string;
    workspace_id?: number;
    entity_type?: string;
    entity_id?: number;
    status?: unknown;
    progress_percent?: number;
    updated_at?: string;
    meta?: Record<string, unknown>;
}

export function getWorkspaceSocketUrl(workspaceId: number): string {
    const apiUrl = new URL(API_BASE_URL, typeof window !== 'undefined' ? window.location.origin : 'http://localhost');
    const wsProtocol = apiUrl.protocol === 'https:' ? 'wss:' : 'ws:';
    return `${wsProtocol}//${apiUrl.host}/ws/workspaces/${workspaceId}/jobs/`;
}
