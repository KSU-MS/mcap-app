'use client';

import { useState, useEffect, useCallback } from 'react';
import dynamic from 'next/dynamic';
import 'leaflet/dist/leaflet.css';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Search, Download } from 'lucide-react';

// Map Preview Component - small preview for table rows
const MapPreview = dynamic(
  () => {
    return Promise.resolve().then(() => {
      const React = require('react');
      const L = require('leaflet');
      const { MapContainer, TileLayer, GeoJSON, useMap } = require('react-leaflet');

      // Fix for default marker icons in Next.js
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
              const geoJsonLayer = L.geoJSON(geoJsonData as any);
              const bounds = geoJsonLayer.getBounds();
              if (bounds.isValid()) {
                map.fitBounds(bounds, { padding: [5, 5] });
              }
            } catch (err) {
              // Silently fail for preview
            }
          }
        }, [geoJsonData, map]);
        return null;
      };

      return ({ logId, apiBaseUrl, onMapClick }: { logId: number; apiBaseUrl: string; onMapClick?: (logId: number) => void }) => {
      const [geoJsonData, setGeoJsonData] = React.useState(null as any);
      const [loading, setLoading] = React.useState(true);
      const [mounted, setMounted] = React.useState(false);
      const [containerReady, setContainerReady] = React.useState(false);

      React.useEffect(() => {
        // Use a small delay to ensure DOM is ready
        const timer = setTimeout(() => {
          setMounted(true);
        }, 100);
        return () => clearTimeout(timer);
      }, []);

      // Check if container is ready after mount
      React.useEffect(() => {
        if (mounted) {
          // Additional small delay to ensure container is in DOM
          const timer = setTimeout(() => {
            setContainerReady(true);
          }, 50);
          return () => clearTimeout(timer);
        }
      }, [mounted]);

      React.useEffect(() => {
        if (!mounted) return;
        
        let cancelled = false;
        const fetchGeoJson = async () => {
          try {
            const response = await fetch(`${apiBaseUrl}/mcap-logs/${logId}/geojson`);
            if (!response.ok) {
              throw new Error('Failed to fetch');
            }
            const data = await response.json();
            if (!cancelled) {
              setGeoJsonData(data);
            }
          } catch (err) {
            // Silently fail for preview
          } finally {
            if (!cancelled) {
              setLoading(false);
            }
          }
        };

        fetchGeoJson();
        return () => {
          cancelled = true;
        };
      }, [logId, apiBaseUrl, mounted]);

      const geoJsonStyle = {
        color: '#3388ff',
        weight: 2,
        opacity: 0.8,
        fillOpacity: 0.2,
      };

      const pointToLayer = (feature: any, latlng: L.LatLng) => {
        return L.circleMarker(latlng, {
          radius: 3,
          fillColor: '#3388ff',
          color: '#fff',
          weight: 1,
          opacity: 1,
          fillOpacity: 0.8,
        });
      };

      // Calculate center from GeoJSON if available
      let center: [number, number] = [0, 0];
      if (geoJsonData?.features?.[0]?.geometry?.coordinates) {
        const coords = geoJsonData.features[0].geometry.coordinates;
        if (geoJsonData.features[0].geometry.type === 'Point') {
          center = [coords[1], coords[0]];
        } else if (geoJsonData.features[0].geometry.type === 'LineString' && coords.length > 0) {
          center = [coords[0][1], coords[0][0]];
        }
      }

      if (!mounted) {
        return (
          <div className="w-full h-24 bg-gray-100 rounded flex items-center justify-center">
            <span className="text-xs text-gray-500">Loading...</span>
          </div>
        );
      }

      if (loading) {
        return (
          <div className="w-full h-24 bg-gray-100 rounded flex items-center justify-center">
            <span className="text-xs text-gray-500">Loading...</span>
          </div>
        );
      }

      if (!geoJsonData) {
        return (
          <div className="w-full h-24 bg-gray-100 rounded flex items-center justify-center">
            <span className="text-xs text-gray-500">No map data</span>
          </div>
        );
      }

      return (
        <div 
          className="w-full h-24 rounded overflow-hidden border border-gray-200 cursor-pointer hover:border-purple-500 transition-colors"
          onClick={() => onMapClick?.(logId)}
          title="Click to view full map"
        >
          {mounted && containerReady ? (
          <MapContainer
            center={center}
            zoom={13}
            style={{ height: '100%', width: '100%', zIndex: 0 }}
            scrollWheelZoom={false}
            zoomControl={false}
            dragging={false}
            doubleClickZoom={false}
            boxZoom={false}
            touchZoom={false}
              key={`map-${logId}-${mounted}`}
          >
            <TileLayer
              attribution=""
              url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
            />
            <GeoJSON
              data={geoJsonData}
              style={geoJsonStyle}
              pointToLayer={pointToLayer}
            />
            <FitBounds geoJsonData={geoJsonData} />
          </MapContainer>
          ) : (
            <div className="w-full h-full flex items-center justify-center">
              <span className="text-xs text-gray-500">Loading map...</span>
            </div>
          )}
        </div>
      );
      };
    });
  },
  { ssr: false }
);

// Map Component - dynamically imported to avoid SSR issues
const MapComponent = dynamic(
  () => {
    return Promise.resolve().then(() => {
      const React = require('react');
      const L = require('leaflet');
      const { MapContainer, TileLayer, GeoJSON, useMap } = require('react-leaflet');

      // Fix for default marker icons in Next.js
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
              const geoJsonLayer = L.geoJSON(geoJsonData as any);
              const bounds = geoJsonLayer.getBounds();
              if (bounds.isValid()) {
                map.fitBounds(bounds, { padding: [20, 20] });
              }
            } catch (err) {
              console.error('Error fitting bounds:', err);
            }
          }
        }, [geoJsonData, map]);
        return null;
      };

      return ({ geoJsonData }: { geoJsonData: any }) => {
        const [mounted, setMounted] = React.useState(false);

        React.useEffect(() => {
          setMounted(true);
        }, []);

        const geoJsonStyle = {
          color: '#3388ff',
          weight: 3,
          opacity: 0.8,
          fillOpacity: 0.2,
        };

        const pointToLayer = (feature: any, latlng: L.LatLng) => {
          return L.circleMarker(latlng, {
            radius: 6,
            fillColor: '#3388ff',
            color: '#fff',
            weight: 2,
            opacity: 1,
            fillOpacity: 0.8,
          });
        };

        const onEachFeature = (feature: any, layer: L.Layer) => {
          if (feature.properties) {
            const popupContent = Object.keys(feature.properties)
              .map((key) => `<strong>${key}:</strong> ${feature.properties[key]}`)
              .join('<br>');
            layer.bindPopup(popupContent);
          }
        };

        // Calculate center from GeoJSON if available
        let center: [number, number] = [0, 0];
        if (geoJsonData?.features?.[0]?.geometry?.coordinates) {
          const coords = geoJsonData.features[0].geometry.coordinates;
          if (geoJsonData.features[0].geometry.type === 'Point') {
            center = [coords[1], coords[0]];
          } else if (geoJsonData.features[0].geometry.type === 'LineString' && coords.length > 0) {
            center = [coords[0][1], coords[0][0]];
          }
        }

        if (!mounted) {
          return (
            <div className="w-full h-full flex items-center justify-center">
              <span className="text-zinc-500">Loading map...</span>
            </div>
          );
        }

        return (
          <div className="w-full h-full">
            <MapContainer
              center={center}
              zoom={13}
              style={{ height: '100%', width: '100%', zIndex: 0 }}
              scrollWheelZoom={true}
              key={`fullmap-${mounted}`}
            >
              <TileLayer
                attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
                url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
              />
              {geoJsonData && (
                <GeoJSON
                  data={geoJsonData}
                  style={geoJsonStyle}
                  pointToLayer={pointToLayer}
                  onEachFeature={onEachFeature}
                />
              )}
              <FitBounds geoJsonData={geoJsonData} />
            </MapContainer>
          </div>
        );
      };
    });
  },
  { ssr: false }
);

interface McapLog {
  id: number;
  recovery_status?: string;
  parse_status?: string;
  captured_at?: string;
  duration_seconds?: number;
  channel_count?: number;
  channels?: string[];
  channels_summary?: string[];
  rough_point?: string;
  car?: string | { id: number; name: string };
  driver?: string | { id: number; name: string };
  event_type?: string | { id: number; name: string };
  notes?: string;
  tags?: string[];
  created_at?: string;
  updated_at?: string;
}

const API_BASE_URL = 'http://127.0.0.1:8000';

export default function Home() {
  const [logs, setLogs] = useState<McapLog[]>([]);
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [processingLogIds, setProcessingLogIds] = useState<number[]>([]);
  const [totalCount, setTotalCount] = useState(0);
  const [currentPage, setCurrentPage] = useState(1);
  const pageSize = 10; // matches backend REST_FRAMEWORK['PAGE_SIZE']
  const [selectedLog, setSelectedLog] = useState<McapLog | null>(null);
  const [isViewModalOpen, setIsViewModalOpen] = useState(false);
  const [isEditModalOpen, setIsEditModalOpen] = useState(false);
  const [isDeleteModalOpen, setIsDeleteModalOpen] = useState(false);
  const [logToDelete, setLogToDelete] = useState<number | null>(null);
  const [editForm, setEditForm] = useState({
    car: '',
    driver: '',
    event_type: '',
    notes: '',
    tags: [] as string[],
  });
  const [editTagInput, setEditTagInput] = useState('');
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [loadingLog, setLoadingLog] = useState(false);
  const [isMapModalOpen, setIsMapModalOpen] = useState(false);
  const [geoJsonData, setGeoJsonData] = useState<any>(null);
  const [loadingGeoJson, setLoadingGeoJson] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [debouncedSearchQuery, setDebouncedSearchQuery] = useState('');
  const [downloading, setDownloading] = useState<number | null>(null);
  const [selectedLogIds, setSelectedLogIds] = useState<number[]>([]);
  const [isDownloadDialogOpen, setIsDownloadDialogOpen] = useState(false);
  const [downloadFormat, setDownloadFormat] = useState<'mcap' | 'csv_omni' | 'csv_tvn' | 'ld'>('mcap');
  const [bulkDownloading, setBulkDownloading] = useState(false);
  const [bulkDownloadError, setBulkDownloadError] = useState<string | null>(null);
  const [downloadCompleteMessage, setDownloadCompleteMessage] = useState<string | null>(null);
  const [cars, setCars] = useState<{ id: number; name: string }[]>([]);
  const [drivers, setDrivers] = useState<{ id: number; name: string }[]>([]);
  const [eventTypes, setEventTypes] = useState<{ id: number; name: string }[]>([]);
  const [loadingLookups, setLoadingLookups] = useState(false);
  // Filter state for list
  const [filterStartDate, setFilterStartDate] = useState('');
  const [filterEndDate, setFilterEndDate] = useState('');
  const [filterCarId, setFilterCarId] = useState('');
  const [filterEventTypeId, setFilterEventTypeId] = useState('');
  const [filterDriverId, setFilterDriverId] = useState('');
  const [filterLocationBbox, setFilterLocationBbox] = useState('');
  const [filterChannel, setFilterChannel] = useState('');
  const [filterTag, setFilterTag] = useState('');
  const [tagNames, setTagNames] = useState<string[]>([]);
  const [channelNames, setChannelNames] = useState<string[]>([]);
  const [dbStatus, setDbStatus] = useState<'checking' | 'connected' | 'disconnected'>('checking');

  // Play a short chime (Web Audio API) when download completes
  const playChime = () => {
    try {
      const ctx = new (window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext)();
      const playTone = (frequency: number, startTime: number, duration: number) => {
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.connect(gain);
        gain.connect(ctx.destination);
        osc.frequency.value = frequency;
        osc.type = 'sine';
        gain.gain.setValueAtTime(0.15, startTime);
        gain.gain.exponentialRampToValueAtTime(0.01, startTime + duration);
        osc.start(startTime);
        osc.stop(startTime + duration);
      };
      playTone(523.25, 0, 0.12);
      playTone(659.25, 0.14, 0.2);
    } catch {
      // ignore if AudioContext not supported or blocked
    }
  };

  // Fetch cars, drivers, and event types for dropdowns
  const fetchLookups = async () => {
    setLoadingLookups(true);
    try {
      // Fetch cars
      try {
        const carsResponse = await fetch(`${API_BASE_URL}/cars/`);
        if (carsResponse.ok) {
          const carsData = await carsResponse.json();
          // Handle paginated response (DRF returns {results: [...]}) or direct array
          const carsArray = Array.isArray(carsData) ? carsData : (carsData.results || []);
          setCars(carsArray);
        }
      } catch (err) {
        console.warn('Failed to fetch cars:', err);
      }

      // Fetch drivers
      try {
        const driversResponse = await fetch(`${API_BASE_URL}/drivers/`);
        if (driversResponse.ok) {
          const driversData = await driversResponse.json();
          // Handle paginated response (DRF returns {results: [...]}) or direct array
          const driversArray = Array.isArray(driversData) ? driversData : (driversData.results || []);
          setDrivers(driversArray);
        }
      } catch (err) {
        console.warn('Failed to fetch drivers:', err);
      }

      // Fetch event types
      try {
        const eventTypesResponse = await fetch(`${API_BASE_URL}/event-types/`);
        if (eventTypesResponse.ok) {
          const eventTypesData = await eventTypesResponse.json();
          const eventTypesArray = Array.isArray(eventTypesData) ? eventTypesData : (eventTypesData.results || []);
          setEventTypes(eventTypesArray);
        }
      } catch (err) {
        console.warn('Failed to fetch event types:', err);
      }

      // Fetch distinct tag names and channel names for filter dropdowns
      try {
        const [tagRes, channelRes] = await Promise.all([
          fetch(`${API_BASE_URL}/mcap-logs/tag-names/`),
          fetch(`${API_BASE_URL}/mcap-logs/channel-names/`),
        ]);
        if (tagRes.ok) {
          const names = await tagRes.json();
          setTagNames(Array.isArray(names) ? names : []);
        }
        if (channelRes.ok) {
          const names = await channelRes.json();
          setChannelNames(Array.isArray(names) ? names : []);
        }
      } catch (err) {
        console.warn('Failed to fetch tag/channel names:', err);
      }
    } catch (err) {
      console.error('Error fetching lookups:', err);
    } finally {
      setLoadingLookups(false);
    }
  };

  const checkDatabaseStatus = useCallback(async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/mcap-logs/?page=1`);
      if (!response.ok) {
        throw new Error(`Backend returned ${response.status}`);
      }
      setDbStatus('connected');
    } catch (err) {
      setDbStatus('disconnected');
      console.error('Database status check failed:', err);
    }
  }, []);

  // Fetch logs from the API (paginated; server-side search and filters)
  const fetchLogs = async (page: number = currentPage) => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams();
      params.set('page', String(page));
      if (debouncedSearchQuery.trim()) params.set('search', debouncedSearchQuery.trim());
      if (filterStartDate.trim()) params.set('start_date', filterStartDate.trim());
      if (filterEndDate.trim()) params.set('end_date', filterEndDate.trim());
      if (filterCarId.trim()) params.set('car_id', filterCarId.trim());
      if (filterEventTypeId.trim()) params.set('event_type_id', filterEventTypeId.trim());
      if (filterDriverId.trim()) params.set('driver_id', filterDriverId.trim());
      if (filterLocationBbox.trim()) params.set('location', filterLocationBbox.trim());
      if (filterChannel.trim()) params.set('channel', filterChannel.trim());
      if (filterTag.trim()) params.set('tag', filterTag.trim());

      const url = `${API_BASE_URL}/mcap-logs/?${params.toString()}`;
      const response = await fetch(url);
      if (!response.ok) {
        throw new Error(`Failed to fetch logs: ${response.statusText}`);
      }
      const data = await response.json();

      if (Array.isArray(data)) {
        setLogs(data);
        setTotalCount(data.length);
      } else if (data?.results) {
        setLogs(data.results);
        setTotalCount(typeof data.count === 'number' ? data.count : data.results.length);
      } else {
        setLogs([]);
        setTotalCount(0);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch logs');
      console.error('Error fetching logs:', err);
    } finally {
      setLoading(false);
    }
  };

  const clearFilters = () => {
    setFilterStartDate('');
    setFilterEndDate('');
    setFilterCarId('');
    setFilterEventTypeId('');
    setFilterDriverId('');
    setFilterLocationBbox('');
    setFilterChannel('');
    setFilterTag('');
    setCurrentPage(1);
  };

  const removeSelectedFileAtIndex = (index: number) => {
    setSelectedFiles((prev) => prev.filter((_, i) => i !== index));
  };

  const clearSelectedFiles = () => setSelectedFiles([]);

  // Upload file(s)
  const handleUpload = async () => {
    if (selectedFiles.length === 0) {
      setError('Please select one or more .mcap files first');
      return;
    }

    setUploading(true);
    setError(null);

    try {
      const formData = new FormData();
      for (const file of selectedFiles) {
        formData.append('files', file);
      }

      // Always use batch upload endpoint (works for 1+ files)
      const response = await fetch(`${API_BASE_URL}/mcap-logs/batch-upload/`, {
        method: 'POST',
        body: formData,
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(
          errorData.detail || errorData.message || `Upload failed: ${response.statusText}`
        );
      }

      // Capture created log IDs so we can show a simple processing indicator
      const payload = await response.json().catch(() => null);
      const createdIds: number[] =
        payload?.results?.map((r: any) => r?.id).filter((id: any) => typeof id === 'number') ?? [];

      if (createdIds.length > 0) {
        setProcessingLogIds((prev) => Array.from(new Set([...prev, ...createdIds])));
      }

      // Clear selection and refresh logs (newest logs are on page 1)
      setSelectedLogIds([]);
      setSelectedFiles([]);
      setCurrentPage(1);
      await fetchLogs(1);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to upload file');
      console.error('Error uploading file:', err);
    } finally {
      setUploading(false);
    }
  };

  // Handle file selection (multiple)
  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files ?? []);
    if (files.length === 0) return;

    const mcapFiles = files.filter((f) => f.name.toLowerCase().endsWith('.mcap'));
    if (mcapFiles.length !== files.length) {
      setError('Some files were ignored. Only .mcap files can be uploaded.');
    } else {
      setError(null);
    }

    setSelectedFiles(mcapFiles);

    // Allow selecting the same files again
    e.currentTarget.value = '';
  };

  // Fetch a specific log by ID
  const fetchLog = async (id: number) => {
    setLoadingLog(true);
    setError(null);
    try {
      const response = await fetch(`${API_BASE_URL}/mcap-logs/${id}/`);
      if (!response.ok) {
        throw new Error(`Failed to fetch log: ${response.statusText}`);
      }
      const data = await response.json();
      return data;
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch log');
      console.error('Error fetching log:', err);
      throw err;
    } finally {
      setLoadingLog(false);
    }
  };

  // View log details
  const handleViewLog = async (id: number) => {
    try {
      const log = await fetchLog(id);
      setSelectedLog(log);
      setIsViewModalOpen(true);
    } catch (err) {
      // Error already handled in fetchLog
    }
  };

  // Helper to extract name from car/driver/event_type (handles both object and string)
  const getName = (value: string | { id: number; name: string } | undefined): string => {
    if (!value) return 'N/A';
    if (typeof value === 'string') return value;
    if (typeof value === 'object' && 'name' in value) return value.name;
    return 'N/A';
  };

  // Helper to extract ID from car/driver/event_type (handles both object and string)
  const extractId = (value: any): string => {
    if (!value) return '';
    if (typeof value === 'object' && value.id) return value.id.toString();
    if (typeof value === 'string') {
      // If it's a string, try to find matching ID from lookups
      const carMatch = cars.find(c => c.name === value);
      if (carMatch) return carMatch.id.toString();
      const driverMatch = drivers.find(d => d.name === value);
      if (driverMatch) return driverMatch.id.toString();
      const eventMatch = eventTypes.find(e => e.name === value);
      if (eventMatch) return eventMatch.id.toString();
    }
    return '';
  };

  // Open edit modal
  const handleEditLog = async (id: number) => {
    try {
      const log = await fetchLog(id);
      setSelectedLog(log);
      
      // Extract IDs - wait a bit if lookups aren't ready yet
      let carId = extractId(log.car);
      let driverId = extractId(log.driver);
      let eventId = extractId(log.event_type);
      
      // If extraction failed and lookups aren't loaded, wait and try again
      if ((!carId || !driverId || !eventId) && loadingLookups) {
        // Wait for lookups to load
        await new Promise(resolve => setTimeout(resolve, 500));
        carId = extractId(log.car);
        driverId = extractId(log.driver);
        eventId = extractId(log.event_type);
      }
      
      setEditForm({
        car: carId,
        driver: driverId,
        event_type: eventId,
        notes: log.notes || '',
        tags: Array.isArray(log.tags) ? [...log.tags] : [],
      });
      setEditTagInput('');
      setIsEditModalOpen(true);
    } catch (err) {
      // Error already handled in fetchLog
    }
  };

  // Update log (PATCH or PUT)
  const handleUpdateLog = async (id: number, usePut = false) => {
    setSaving(true);
    setError(null);

    try {
      const method = usePut ? 'PUT' : 'PATCH';
      
      // Build request body - convert IDs to numbers for car, driver, event_type; include tags
      const body: any = {
        notes: editForm.notes || '',
        tags: editForm.tags && editForm.tags.length > 0 ? editForm.tags : [],
      };

      // Convert string IDs to numbers
      // The API expects car_id, driver_id, event_type_id (with _id suffix) for updates
      // For PATCH: only include fields that have values (don't send null)
      // For PUT: include all fields, even if null
      if (usePut) {
        // PUT requires all fields - send null if empty
        body.car_id = editForm.car && editForm.car.trim() !== '' ? Number(editForm.car) : null;
        body.driver_id = editForm.driver && editForm.driver.trim() !== '' ? Number(editForm.driver) : null;
        body.event_type_id = editForm.event_type && editForm.event_type.trim() !== '' ? Number(editForm.event_type) : null;
      } else {
        // PATCH: only include fields that have values
        if (editForm.car && editForm.car.trim() !== '') {
          const carId = Number(editForm.car);
          if (!isNaN(carId) && carId > 0) {
            body.car_id = carId;
          }
        }
        if (editForm.driver && editForm.driver.trim() !== '') {
          const driverId = Number(editForm.driver);
          if (!isNaN(driverId) && driverId > 0) {
            body.driver_id = driverId;
          }
        }
        if (editForm.event_type && editForm.event_type.trim() !== '') {
          const eventId = Number(editForm.event_type);
          if (!isNaN(eventId) && eventId > 0) {
            body.event_type_id = eventId;
          }
        }
      }

      console.log('=== UPDATE DEBUG ===');
      console.log('Log ID:', id);
      console.log('Method:', method);
      console.log('Edit form state:', editForm);
      console.log('Request body being sent:', body);
      console.log('Body JSON:', JSON.stringify(body));

      const response = await fetch(`${API_BASE_URL}/mcap-logs/${id}/`, {
        method,
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(body),
      });

      if (!response.ok) {
        let errorMessage = `Update failed: ${response.statusText}`;
        try {
          const errorData = await response.json();
          console.error('Update error response:', errorData); // Debug log
          // Handle different error response formats
          if (errorData.detail) {
            errorMessage = errorData.detail;
          } else if (errorData.message) {
            errorMessage = errorData.message;
          } else if (typeof errorData === 'object') {
            // Handle field-specific errors
            const fieldErrors = Object.entries(errorData)
              .map(([key, value]) => `${key}: ${Array.isArray(value) ? value.join(', ') : value}`)
              .join('; ');
            if (fieldErrors) {
              errorMessage = fieldErrors;
            }
          }
        } catch (parseError) {
          // If JSON parsing fails, use the status text
          console.error('Error parsing error response:', parseError);
        }
        throw new Error(errorMessage);
      }

      // Get the updated log data
      const updatedData = await response.json();
      console.log('Update successful, response:', updatedData); // Debug log
      console.log('Response car:', updatedData.car);
      console.log('Response driver:', updatedData.driver);
      console.log('Response event_type:', updatedData.event_type);
      
      // Check if the update actually worked
      if (updatedData.car === null && body.car !== undefined) {
        console.warn('⚠️ WARNING: Backend returned null for car despite sending:', body.car);
        console.warn('This suggests the backend serializer may not be processing the car field in PATCH requests.');
      }
      if (updatedData.driver === null && body.driver !== undefined) {
        console.warn('⚠️ WARNING: Backend returned null for driver despite sending:', body.driver);
      }
      if (updatedData.event_type === null && body.event_type !== undefined) {
        console.warn('⚠️ WARNING: Backend returned null for event_type despite sending:', body.event_type);
      }

      // Optimistically update the logs state with the response data
      setLogs((prevLogs) =>
        prevLogs.map((log) =>
          log.id === id
            ? {
                ...log,
                car: updatedData.car,
                driver: updatedData.driver,
                event_type: updatedData.event_type,
                notes: updatedData.notes ?? log.notes,
                tags: updatedData.tags ?? log.tags ?? [],
              }
            : log
        )
      );

      // Refresh tag names for filter dropdown in case a new tag was added
      try {
        const tagRes = await fetch(`${API_BASE_URL}/mcap-logs/tag-names/`);
        if (tagRes.ok) {
          const names = await tagRes.json();
          setTagNames(Array.isArray(names) ? names : []);
        }
      } catch {
        // ignore
      }

      setIsEditModalOpen(false);
      setSelectedLog(null);
      await fetchLogs(currentPage);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update log');
      console.error('Error updating log:', err);
    } finally {
      setSaving(false);
    }
  };

  // Delete log
  const handleDeleteLog = async (id: number) => {
    setDeleting(true);
    setError(null);

    try {
      const response = await fetch(`${API_BASE_URL}/mcap-logs/${id}/`, {
        method: 'DELETE',
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(
          errorData.detail || errorData.message || `Delete failed: ${response.statusText}`
        );
      }

      setIsDeleteModalOpen(false);
      setLogToDelete(null);
      await fetchLogs(currentPage);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete log');
      console.error('Error deleting log:', err);
    } finally {
      setDeleting(false);
    }
  };

  // Open delete confirmation
  const openDeleteConfirm = (id: number) => {
    setLogToDelete(id);
    setIsDeleteModalOpen(true);
  };

  // Fetch GeoJSON for a log
  const fetchGeoJson = async (id: number) => {
    setLoadingGeoJson(true);
    setError(null);
    try {
      const response = await fetch(`${API_BASE_URL}/mcap-logs/${id}/geojson`);
      if (!response.ok) {
        throw new Error(`Failed to fetch GeoJSON: ${response.statusText}`);
      }
      const data = await response.json();
      setGeoJsonData(data);
      setIsMapModalOpen(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch GeoJSON');
      console.error('Error fetching GeoJSON:', err);
    } finally {
      setLoadingGeoJson(false);
    }
  };

  // Download MCAP file
  const handleDownload = async (id: number) => {
    setDownloading(id);
    setError(null);
    try {
      const response = await fetch(`${API_BASE_URL}/mcap-logs/${id}/download`);
      if (!response.ok) {
        throw new Error(`Failed to download file: ${response.statusText}`);
      }
      
      // Get filename from Content-Disposition header or use default
      const contentDisposition = response.headers.get('Content-Disposition');
      let filename = `mcap-log-${id}.mcap`;
      if (contentDisposition) {
        const filenameMatch = contentDisposition.match(/filename="?(.+)"?/i);
        if (filenameMatch) {
          filename = filenameMatch[1];
        }
      }

      // Create blob and download
      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to download file');
      console.error('Error downloading file:', err);
    } finally {
      setDownloading(null);
    }
  };

  // Debounce search and fetch server-side results (search across ALL logs)
  useEffect(() => {
    const t = setTimeout(() => setDebouncedSearchQuery(searchQuery), 300);
    return () => clearTimeout(t);
  }, [searchQuery]);

  useEffect(() => {
    setSelectedLogIds([]);
    setCurrentPage(1);
    fetchLogs(1);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [debouncedSearchQuery, filterStartDate, filterEndDate, filterCarId, filterEventTypeId, filterDriverId, filterLocationBbox, filterChannel, filterTag]);

  const totalPages = Math.max(1, Math.ceil(totalCount / pageSize));

  const goToPage = (page: number) => {
    const nextPage = Math.min(Math.max(1, page), totalPages);
    setSelectedLogIds([]);
    setCurrentPage(nextPage);
    fetchLogs(nextPage);
  };

  const terminalStatus = (s?: string) => {
    if (!s) return false;
    const v = s.toLowerCase();
    return v === 'completed' || v === 'success' || v.startsWith('error');
  };

  // Poll for status updates while uploads are processing
  useEffect(() => {
    if (processingLogIds.length === 0) return;

    let cancelled = false;
    const interval = setInterval(async () => {
      try {
        const ids = processingLogIds.slice();
        if (ids.length === 0) return;

        const results = await Promise.all(
          ids.map(async (id) => {
            const res = await fetch(`${API_BASE_URL}/mcap-logs/${id}/`);
            if (!res.ok) return { id, log: null };
            const log = await res.json();
            return { id, log };
          })
        );

        if (cancelled) return;

        // Update visible rows in-place if they’re on the current page
        setLogs((prev) => {
          const byId = new Map(results.filter((r) => r.log).map((r) => [r.id, r.log]));
          return prev.map((l) => (byId.has(l.id) ? { ...l, ...byId.get(l.id) } : l));
        });

        // Remove finished IDs
        setProcessingLogIds((prev) =>
          prev.filter((id) => {
            const found = results.find((r) => r.id === id)?.log;
            if (!found) return true;
            return !(terminalStatus(found.recovery_status) && terminalStatus(found.parse_status));
          })
        );
      } catch (_) {
        // Keep polling; transient errors are fine
      }
    }, 2500);

    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [processingLogIds]);

  // Selection helpers
  const toggleSelectLog = (id: number) => {
    setSelectedLogIds((prev) =>
      prev.includes(id) ? prev.filter((logId) => logId !== id) : [...prev, id]
    );
  };

  const toggleSelectAll = () => {
    const allIds = logs.map((log) => log.id);
    const allSelected = allIds.every((id) => selectedLogIds.includes(id)) && allIds.length > 0;
    if (allSelected) {
      setSelectedLogIds((prev) => prev.filter((id) => !allIds.includes(id)));
    } else {
      setSelectedLogIds((prev) => Array.from(new Set([...prev, ...allIds])));
    }
  };

  const openDownloadDialog = () => {
    if (selectedLogIds.length === 0) {
      setError('Select at least one log to download');
      return;
    }
    setBulkDownloadError(null);
    setIsDownloadDialogOpen(true);
  };

  const handleBulkDownload = async () => {
    if (selectedLogIds.length === 0) {
      setBulkDownloadError('Select at least one log to download');
      return;
    }
    setBulkDownloading(true);
    setBulkDownloadError(null);
    try {
      const response = await fetch(`${API_BASE_URL}/mcap-logs/download/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ids: selectedLogIds, format: downloadFormat }),
      });

      if (!response.ok) {
        let message = `Failed to download files: ${response.statusText}`;
        try {
          const data = await response.json();
          message = data.error || message;
        } catch (_) {
          // ignore json errors
        }
        throw new Error(message);
      }

      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      const filename = `mcap_logs_${downloadFormat}.zip`;
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
      playChime();
      setDownloadCompleteMessage('Download complete!');
      setIsDownloadDialogOpen(false);
    } catch (err) {
      setBulkDownloadError(err instanceof Error ? err.message : 'Failed to download files');
      console.error('Error downloading files:', err);
    } finally {
      setBulkDownloading(false);
    }
  };

  // Fetch logs and lookups on component mount
  useEffect(() => {
    fetchLookups();
    fetchLogs(1);
  }, []);

  useEffect(() => {
    let cancelled = false;

    const runCheck = async () => {
      if (cancelled) return;
      await checkDatabaseStatus();
    };

    runCheck();
    const interval = setInterval(runCheck, 15000);

    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [checkDatabaseStatus]);

  // Auto-dismiss download complete toast after 4 seconds
  useEffect(() => {
    if (!downloadCompleteMessage) return;
    const t = setTimeout(() => setDownloadCompleteMessage(null), 4000);
    return () => clearTimeout(t);
  }, [downloadCompleteMessage]);

  return (
    <div className="min-h-screen bg-white py-8 px-4 sm:px-8">
      <div className="fixed top-4 right-4 z-50" title={`Database: ${dbStatus}`} aria-label={`Database status: ${dbStatus}`}>
        <span
          className={`block h-3 w-3 rounded-full ${
            dbStatus === 'connected'
              ? 'bg-green-500'
              : dbStatus === 'disconnected'
              ? 'bg-red-500'
              : 'bg-amber-400'
          }`}
        />
      </div>

      {/* Download complete toast */}
      {downloadCompleteMessage && (
        <div
          className="fixed bottom-6 right-6 z-50 flex items-center gap-2 rounded-lg border border-green-200 bg-green-50 px-4 py-3 text-sm font-medium text-green-900 shadow-lg animate-in fade-in slide-in-from-bottom-2 duration-300"
          role="status"
          aria-live="polite"
        >
          <span className="inline-flex h-2 w-2 rounded-full bg-green-500" />
          {downloadCompleteMessage}
        </div>
      )}

      <div className="max-w-7xl mx-auto">
        <h1 className="text-4xl font-bold text-gray-900 mb-8">
          MCAP Log Manager
        </h1>

        {/* Upload Section */}
        <Card className="mb-8 bg-white border border-gray-200 shadow-sm">
          <CardHeader>
            <CardTitle className="text-gray-900">Upload MCAP Files</CardTitle>
          </CardHeader>
          <CardContent>
          <div className="flex flex-col sm:flex-row gap-4 items-start sm:items-center">
              <label className="cursor-pointer">
              <input
                type="file"
                accept=".mcap"
                multiple
                onChange={handleFileChange}
                className="hidden"
                disabled={uploading}
              />
                <Button variant="outline" className="cursor-pointer border-gray-300 text-gray-700 hover:bg-gray-50" asChild>
              <span>Select MCAP Files</span>
                </Button>
            </label>

            {selectedFiles.length > 0 && (
              <div className="flex-1">
                <p className="text-sm text-gray-600">
                  Selected: <span className="font-medium text-gray-900">{selectedFiles.length}</span> file{selectedFiles.length === 1 ? '' : 's'}
                </p>
                <p className="text-xs text-gray-500">
                  Total size:{' '}
                  {(selectedFiles.reduce((acc, f) => acc + f.size, 0) / 1024 / 1024).toFixed(2)} MB
                </p>
                <div className="mt-2 space-y-1">
                  {selectedFiles.slice(0, 5).map((file, idx) => (
                    <div key={`${file.name}-${file.size}-${idx}`} className="flex items-center justify-between gap-2">
                      <span className="text-xs text-gray-700 truncate">{file.name}</span>
                      <button
                        type="button"
                        className="text-xs text-purple-700 hover:text-purple-900"
                        onClick={() => removeSelectedFileAtIndex(idx)}
                        disabled={uploading}
                      >
                        Remove
                      </button>
                    </div>
                  ))}
                  {selectedFiles.length > 5 && (
                    <div className="text-xs text-gray-500">
                      + {selectedFiles.length - 5} more…
                    </div>
                  )}
                </div>
                <div className="mt-2">
                  <button
                    type="button"
                    className="text-xs text-gray-600 hover:text-gray-900"
                    onClick={clearSelectedFiles}
                    disabled={uploading}
                  >
                    Clear selection
                  </button>
                </div>
              </div>
            )}

              <Button
              onClick={handleUpload}
              disabled={selectedFiles.length === 0 || uploading}
                className="bg-purple-600 hover:bg-purple-700 text-white"
            >
              {uploading ? 'Uploading...' : 'Upload'}
              </Button>
          </div>

          {processingLogIds.length > 0 && (
            <div className="mt-4 rounded-md border border-purple-200 bg-purple-50 px-4 py-3 text-sm text-purple-900">
              Processing {processingLogIds.length} file{processingLogIds.length === 1 ? '' : 's'}…
              <span className="ml-2 text-purple-700">(recovery/parse running)</span>
            </div>
          )}

          {error && (
              <div className="mt-4 p-4 bg-red-50 border border-red-200 rounded-lg">
              <p className="text-red-600">{error}</p>
            </div>
          )}
          </CardContent>
        </Card>

        {/* Logs Display Section */}
        <Card className="bg-white border border-gray-200 shadow-sm">
          <CardHeader>
              <div className="flex justify-between items-center mb-4">
              <div className="flex items-center gap-3">
                <CardTitle className="text-gray-900">MCAP Logs</CardTitle>
                {selectedLogIds.length > 0 && (
                  <span className="inline-flex items-center px-3 py-1 rounded-full text-sm font-medium bg-purple-100 text-purple-800 border border-purple-200">
                    {selectedLogIds.length} {selectedLogIds.length === 1 ? 'file' : 'files'} selected
                  </span>
                )}
              </div>
              <div className="flex gap-2">
                <Button
                  onClick={openDownloadDialog}
                  disabled={selectedLogIds.length === 0}
                  className="bg-purple-600 hover:bg-purple-700 text-white disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  Download Selected
                  {selectedLogIds.length > 0 && (
                    <span className="ml-2 inline-flex items-center justify-center w-5 h-5 rounded-full bg-purple-500 text-xs font-semibold">
                      {selectedLogIds.length}
                    </span>
                  )}
                </Button>
                <Button
                  onClick={() => fetchLogs(currentPage)}
                  disabled={loading}
                  variant="outline"
                  className="border-gray-300 text-gray-700 hover:bg-gray-50"
                >
                  {loading ? 'Refreshing...' : 'Refresh'}
                </Button>
              </div>
          </div>
            <div className="flex gap-2">
              <div className="relative flex-1">
                <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-gray-400" />
                <Input
                  type="text"
                  placeholder="Search logs by ID, car, driver, event type, notes..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="pl-10 bg-white border-gray-300"
                />
              </div>
            </div>
            <div className="flex flex-wrap items-end gap-2 mt-3">
              <div className="flex flex-col gap-1">
                <Label className="text-xs text-gray-500">From</Label>
                <Input
                  type="date"
                  value={filterStartDate}
                  onChange={(e) => { setFilterStartDate(e.target.value); setCurrentPage(1); }}
                  className="w-[130px] bg-white border-gray-300"
                />
              </div>
              <div className="flex flex-col gap-1">
                <Label className="text-xs text-gray-500">To</Label>
                <Input
                  type="date"
                  value={filterEndDate}
                  onChange={(e) => { setFilterEndDate(e.target.value); setCurrentPage(1); }}
                  className="w-[130px] bg-white border-gray-300"
                />
              </div>
              <div className="flex flex-col gap-1">
                <Label className="text-xs text-gray-500">Car</Label>
                <Select value={filterCarId || 'all'} onValueChange={(v) => { setFilterCarId(v === 'all' ? '' : v); setCurrentPage(1); }}>
                  <SelectTrigger className="w-[140px] bg-white border-gray-300">
                    <SelectValue placeholder="All" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All</SelectItem>
                    {cars.map((c) => (
                      <SelectItem key={c.id} value={String(c.id)}>{c.name}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="flex flex-col gap-1">
                <Label className="text-xs text-gray-500">Event type</Label>
                <Select value={filterEventTypeId || 'all'} onValueChange={(v) => { setFilterEventTypeId(v === 'all' ? '' : v); setCurrentPage(1); }}>
                  <SelectTrigger className="w-[140px] bg-white border-gray-300">
                    <SelectValue placeholder="All" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All</SelectItem>
                    {eventTypes.map((e) => (
                      <SelectItem key={e.id} value={String(e.id)}>{e.name}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="flex flex-col gap-1">
                <Label className="text-xs text-gray-500">Driver</Label>
                <Select value={filterDriverId || 'all'} onValueChange={(v) => { setFilterDriverId(v === 'all' ? '' : v); setCurrentPage(1); }}>
                  <SelectTrigger className="w-[140px] bg-white border-gray-300">
                    <SelectValue placeholder="All" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All</SelectItem>
                    {drivers.map((d) => (
                      <SelectItem key={d.id} value={String(d.id)}>{d.name}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="flex flex-col gap-1">
                <Label className="text-xs text-gray-500">Tag</Label>
                <Select value={filterTag || 'all'} onValueChange={(v) => { setFilterTag(v === 'all' ? '' : v); setCurrentPage(1); }}>
                  <SelectTrigger className="w-[160px] bg-white border-gray-300">
                    <SelectValue placeholder="All" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All</SelectItem>
                    {tagNames.map((t) => (
                      <SelectItem key={t} value={t}>{t}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="flex flex-col gap-1">
                <Label className="text-xs text-gray-500">Channel</Label>
                <Select value={filterChannel || 'all'} onValueChange={(v) => { setFilterChannel(v === 'all' ? '' : v); setCurrentPage(1); }}>
                  <SelectTrigger className="w-[180px] bg-white border-gray-300">
                    <SelectValue placeholder="All" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All</SelectItem>
                    {channelNames.map((c) => (
                      <SelectItem key={c} value={c}>{c}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="flex flex-col gap-1">
                <Label className="text-xs text-gray-500">Location (bbox)</Label>
                <Input
                  type="text"
                  placeholder="min_lon,min_lat,max_lon,max_lat"
                  value={filterLocationBbox}
                  onChange={(e) => { setFilterLocationBbox(e.target.value); setCurrentPage(1); }}
                  className="w-[200px] bg-white border-gray-300 text-sm"
                />
              </div>
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="border-gray-300 text-gray-700"
                onClick={() => clearFilters()}
              >
                Clear filters
              </Button>
            </div>
          </CardHeader>
          <CardContent>

          {loading && logs.length === 0 ? (
            <div className="text-center py-8">
              <p className="text-gray-600">Loading logs...</p>
            </div>
          ) : logs.length === 0 ? (
            <div className="text-center py-8">
              <p className="text-gray-600">
                {searchQuery ? `No logs found matching "${searchQuery}"` : 'No logs found. Upload a file to get started.'}
              </p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full table-clean">
                <thead>
                  <tr>
                    <th className="py-3 px-2 w-10">
                      <input
                        type="checkbox"
                        aria-label="Select all"
                        checked={
                          logs.length > 0 &&
                          logs.every((log) => selectedLogIds.includes(log.id))
                        }
                        onChange={toggleSelectAll}
                      />
                    </th>
                    <th>ID</th>
                    <th>Map Preview</th>
                    <th>Date</th>
                    <th>Time</th>
                    <th>Duration</th>
                    <th>Channels</th>
                    <th>Status</th>
                    <th>Car</th>
                    <th>Driver</th>
                    <th>Event</th>
                    <th>Tags</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {logs.map((log) => (
                    <tr
                      key={log.id}
                      className="hover:bg-gray-50 transition-colors"
                    >
                      <td className="py-3 px-2">
                        <input
                          type="checkbox"
                          aria-label={`Select log ${log.id}`}
                          checked={selectedLogIds.includes(log.id)}
                          onChange={() => toggleSelectLog(log.id)}
                          className="rounded border-gray-300 text-purple-600 focus:ring-purple-500"
                        />
                      </td>
                      <td className="text-sm text-gray-900 font-medium">{log.id}</td>
                      <td>
                        <MapPreview 
                          logId={log.id} 
                          apiBaseUrl={API_BASE_URL} 
                          onMapClick={fetchGeoJson}
                        />
                      </td>
                      <td className="text-sm text-gray-700">
                        {log.captured_at
                          ? new Date(log.captured_at).toLocaleDateString()
                          : 'N/A'}
                      </td>
                      <td className="text-sm text-gray-700">
                        {log.captured_at
                          ? new Date(log.captured_at).toLocaleTimeString()
                          : 'N/A'}
                      </td>
                      <td className="text-sm text-gray-700">
                        {log.duration_seconds
                          ? `${log.duration_seconds.toFixed(1)}s`
                          : 'N/A'}
                      </td>
                      <td className="text-sm text-gray-700">
                        {log.channel_count ?? 'N/A'}
                      </td>
                      <td>
                        <div className="flex flex-col gap-1">
                          {log.recovery_status && (
                            <span
                              className={`inline-block px-2 py-1 rounded text-xs ${
                                log.recovery_status === 'completed' || log.recovery_status === 'success'
                                  ? 'bg-green-100 text-green-800'
                                  : log.recovery_status === 'pending'
                                  ? 'bg-yellow-100 text-yellow-800'
                                  : 'bg-red-100 text-red-800'
                              }`}
                            >
                              Recovery: {log.recovery_status}
                            </span>
                          )}
                          {log.parse_status && (
                            <span
                              className={`inline-block px-2 py-1 rounded text-xs ${
                                log.parse_status === 'completed' || log.parse_status === 'success'
                                  ? 'bg-green-100 text-green-800'
                                  : log.parse_status === 'pending'
                                  ? 'bg-yellow-100 text-yellow-800'
                                  : log.parse_status?.startsWith('error')
                                  ? 'bg-red-100 text-red-800'
                                  : 'bg-blue-100 text-blue-800'
                              }`}
                            >
                              Parse: {log.parse_status}
                            </span>
                          )}
                        </div>
                      </td>
                      <td className="text-sm text-gray-700">
                        {getName(log.car)}
                      </td>
                      <td className="text-sm text-gray-700">
                        {getName(log.driver)}
                      </td>
                      <td className="text-sm text-gray-700">
                        {getName(log.event_type)}
                      </td>
                      <td className="text-sm text-gray-700 max-w-[180px]">
                        {log.tags && log.tags.length > 0 ? (
                          <span className="flex flex-wrap gap-1">
                            {log.tags.map((t) => (
                              <span key={t} className="inline-flex px-1.5 py-0.5 rounded bg-gray-100 text-gray-700 text-xs border border-gray-200">
                                {t}
                              </span>
                            ))}
                          </span>
                        ) : (
                          '—'
                        )}
                      </td>
                      <td>
                        <div className="flex gap-2 flex-wrap">
                          <Button
                            onClick={() => handleViewLog(log.id)}
                            size="sm"
                            className="text-xs bg-purple-600 hover:bg-purple-700 text-white"
                          >
                            View
                          </Button>
                          <Button
                            onClick={() => fetchGeoJson(log.id)}
                            disabled={loadingGeoJson}
                            size="sm"
                            className="text-xs bg-gray-100 hover:bg-gray-200 text-gray-700 border border-gray-300"
                          >
                            Map
                          </Button>
                          <Button
                            onClick={() => handleDownload(log.id)}
                            disabled={downloading === log.id}
                            size="sm"
                            className="text-xs border border-gray-300 text-gray-700 hover:bg-gray-50"
                            title="Download MCAP file"
                          >
                            <Download className="h-3 w-3 mr-1" />
                            {downloading === log.id ? 'Downloading...' : 'Download'}
                          </Button>
                          <Button
                            onClick={() => handleEditLog(log.id)}
                            size="sm"
                            className="text-xs bg-green-600 hover:bg-green-700 text-white"
                          >
                            Edit
                          </Button>
                          <Button
                            onClick={() => openDeleteConfirm(log.id)}
                            size="sm"
                            className="text-xs bg-red-600 hover:bg-red-700 text-white"
                          >
                            Delete
                          </Button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>

              {/* Pagination */}
              <div className="mt-4 flex flex-col sm:flex-row items-center justify-between gap-3">
                <div className="text-sm text-gray-600">
                  Page <span className="font-medium text-gray-900">{currentPage}</span> of{' '}
                  <span className="font-medium text-gray-900">{totalPages}</span> •{' '}
                  <span className="font-medium text-gray-900">{totalCount}</span> total logs
                </div>
                <div className="flex items-center gap-1 flex-wrap justify-end">
                  <Button
                    variant="outline"
                    className="border-gray-300 text-gray-700 hover:bg-gray-50"
                    disabled={currentPage <= 1 || loading}
                    onClick={() => goToPage(currentPage - 1)}
                  >
                    Prev
                  </Button>

                  {(() => {
                    const pages: (number | 'dots')[] = [];
                    const maxButtons = 7;
                    if (totalPages <= maxButtons) {
                      for (let p = 1; p <= totalPages; p++) pages.push(p);
                    } else {
                      const start = Math.max(2, currentPage - 2);
                      const end = Math.min(totalPages - 1, currentPage + 2);
                      pages.push(1);
                      if (start > 2) pages.push('dots');
                      for (let p = start; p <= end; p++) pages.push(p);
                      if (end < totalPages - 1) pages.push('dots');
                      pages.push(totalPages);
                    }

                    return pages.map((p, idx) => {
                      if (p === 'dots') {
                        return (
                          <span key={`dots-${idx}`} className="px-2 text-gray-400">
                            …
                          </span>
                        );
                      }
                      const active = p === currentPage;
                      return (
                        <Button
                          key={`page-${p}`}
                          variant="outline"
                          className={
                            active
                              ? 'border-purple-400 bg-purple-50 text-purple-900 hover:bg-purple-100'
                              : 'border-gray-300 text-gray-700 hover:bg-gray-50'
                          }
                          disabled={loading}
                          onClick={() => goToPage(p)}
                        >
                          {p}
                        </Button>
                      );
                    });
                  })()}

                  <Button
                    variant="outline"
                    className="border-gray-300 text-gray-700 hover:bg-gray-50"
                    disabled={currentPage >= totalPages || loading}
                    onClick={() => goToPage(currentPage + 1)}
                  >
                    Next
                  </Button>
                </div>
              </div>
            </div>
          )}
          </CardContent>
        </Card>

        {/* Bulk Download Format Dialog */}
        <Dialog
          open={isDownloadDialogOpen}
          onOpenChange={(open) => {
            setIsDownloadDialogOpen(open);
            if (!open) setBulkDownloadError(null);
          }}
        >
          <DialogContent className="bg-white border border-gray-200">
            <DialogHeader>
              <DialogTitle className="text-gray-900">Select download format</DialogTitle>
              <DialogDescription className="text-gray-600">
                {selectedLogIds.length} log{selectedLogIds.length === 1 ? '' : 's'} selected
              </DialogDescription>
            </DialogHeader>

            <div className="space-y-3">
              <Label className="text-gray-700">Format</Label>
              <Select
                value={downloadFormat}
                onValueChange={(val) => setDownloadFormat(val as 'mcap' | 'csv_omni' | 'csv_tvn' | 'ld')}
              >
                <SelectTrigger className="w-full bg-white border-gray-300">
                  <SelectValue placeholder="Select format" />
                </SelectTrigger>
                <SelectContent className="bg-white border border-gray-200">
                  <SelectItem value="mcap">MCAP (original)</SelectItem>
                  <SelectItem value="csv_omni">CSV (omni)</SelectItem>
                  <SelectItem value="csv_tvn">CSV (tvn)</SelectItem>
                  <SelectItem value="ld">LD (i2)</SelectItem>
                </SelectContent>
              </Select>

              {bulkDownloadError && (
                <p className="text-sm text-red-600">{bulkDownloadError}</p>
              )}

              {bulkDownloading && (
                <div className="flex items-center gap-3 rounded-md border border-purple-200 bg-purple-50 px-4 py-3 text-sm text-purple-900">
                  <span
                    className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-purple-400 border-t-transparent"
                    aria-hidden
                  />
                  <span>
                    {downloadFormat === 'mcap'
                      ? 'Preparing ZIP…'
                      : `Converting to ${downloadFormat.replace('csv_', '').toUpperCase()} and preparing ZIP…`}
                  </span>
                </div>
              )}
            </div>

            <DialogFooter className="gap-2">
              <Button 
                variant="outline" 
                onClick={() => setIsDownloadDialogOpen(false)}
                className="border-gray-300 text-gray-700 hover:bg-gray-50"
              >
                Cancel
              </Button>
              <Button 
                onClick={handleBulkDownload} 
                disabled={bulkDownloading}
                className="bg-purple-600 hover:bg-purple-700 text-white disabled:opacity-50"
              >
                {bulkDownloading ? 'Preparing...' : 'Download'}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>

        {/* View Modal */}
        <Dialog open={isViewModalOpen} onOpenChange={(open) => {
          setIsViewModalOpen(open);
          if (!open) setSelectedLog(null);
        }}>
          {selectedLog && (
            <DialogContent className="max-w-3xl max-h-[90vh] overflow-y-auto bg-white border border-gray-200">
              <DialogHeader>
                <DialogTitle className="text-gray-900">Log Details - ID: {selectedLog.id}</DialogTitle>
              </DialogHeader>
                {loadingLog ? (
                  <div className="text-center py-8">
                    <p className="text-gray-600">Loading log details...</p>
                  </div>
                ) : (
                  <div className="space-y-4">
                    <div className="grid grid-cols-2 gap-4">
                      <div>
                        <label className="text-sm font-medium text-gray-600">Recovery Status</label>
                        <p className="text-gray-900">{selectedLog.recovery_status || 'N/A'}</p>
                      </div>
                      <div>
                        <label className="text-sm font-medium text-gray-600">Parse Status</label>
                        <p className="text-gray-900">{selectedLog.parse_status || 'N/A'}</p>
                      </div>
                      <div>
                        <label className="text-sm font-medium text-gray-600">Captured At</label>
                        <p className="text-gray-900">
                          {selectedLog.captured_at ? new Date(selectedLog.captured_at).toLocaleString() : 'N/A'}
                        </p>
                      </div>
                      <div>
                        <label className="text-sm font-medium text-gray-600">Duration</label>
                        <p className="text-gray-900">
                          {selectedLog.duration_seconds ? `${selectedLog.duration_seconds.toFixed(1)}s` : 'N/A'}
                        </p>
                      </div>
                      <div>
                        <label className="text-sm font-medium text-gray-600">Channel Count</label>
                        <p className="text-gray-900">{selectedLog.channel_count ?? 'N/A'}</p>
                      </div>
                      <div>
                        <label className="text-sm font-medium text-gray-600">Rough Point</label>
                        <p className="text-gray-900">{selectedLog.rough_point || 'N/A'}</p>
                      </div>
                      <div>
                        <label className="text-sm font-medium text-gray-600">Car</label>
                        <p className="text-gray-900">{getName(selectedLog.car)}</p>
                      </div>
                      <div>
                        <label className="text-sm font-medium text-gray-600">Driver</label>
                        <p className="text-gray-900">{getName(selectedLog.driver)}</p>
                      </div>
                      <div>
                        <label className="text-sm font-medium text-gray-600">Event Type</label>
                        <p className="text-gray-900">{getName(selectedLog.event_type)}</p>
                      </div>
                      <div>
                        <label className="text-sm font-medium text-gray-600">Created At</label>
                        <p className="text-gray-900">
                          {selectedLog.created_at ? new Date(selectedLog.created_at).toLocaleString() : 'N/A'}
                        </p>
                      </div>
                      <div>
                        <label className="text-sm font-medium text-gray-600">Updated At</label>
                        <p className="text-gray-900">
                          {selectedLog.updated_at ? new Date(selectedLog.updated_at).toLocaleString() : 'N/A'}
                        </p>
                      </div>
                    </div>
                    {selectedLog.channels && selectedLog.channels.length > 0 && (
                      <div className="bg-gray-50 p-4 rounded-lg border border-gray-200">
                        <div className="flex justify-between items-center mb-3">
                          <label className="text-base font-semibold text-gray-900">
                            Channels
                          </label>
                          <span className="text-sm text-gray-600">
                            Count: {selectedLog.channel_count ?? selectedLog.channels.length}
                          </span>
                        </div>
                        <div className="max-h-64 overflow-y-auto border border-gray-200 rounded-lg bg-white">
                          <table className="w-full border-collapse">
                            <thead className="sticky top-0 bg-gray-100">
                              <tr>
                                <th className="text-left py-2 px-4 text-sm font-semibold text-gray-700 border-b border-gray-200">
                                  #
                                </th>
                                <th className="text-left py-2 px-4 text-sm font-semibold text-gray-700 border-b border-gray-200">
                                  Channel Name
                                </th>
                              </tr>
                            </thead>
                            <tbody>
                              {selectedLog.channels.map((channel, idx) => (
                                <tr
                              key={idx}
                                  className="border-b border-gray-100 hover:bg-gray-50 transition-colors"
                            >
                                  <td className="py-2 px-4 text-sm text-gray-600">
                                    {idx + 1}
                                  </td>
                                  <td className="py-2 px-4 text-sm text-gray-900 font-mono">
                              {channel}
                                  </td>
                                </tr>
                          ))}
                            </tbody>
                          </table>
                        </div>
                      </div>
                    )}
                    {selectedLog.notes && (
                      <div>
                        <label className="text-sm font-medium text-gray-600">Notes</label>
                        <p className="text-gray-900 mt-1">{selectedLog.notes}</p>
                      </div>
                    )}
                    <div className="pt-4">
                      <Button
                        onClick={() => fetchGeoJson(selectedLog.id)}
                        disabled={loadingGeoJson}
                        className="w-full bg-gray-100 hover:bg-gray-200 text-gray-700 border border-gray-300"
                      >
                        {loadingGeoJson ? 'Loading Map...' : 'View on Map'}
                      </Button>
                    </div>
                  </div>
                )}
            </DialogContent>
        )}
        </Dialog>

        {/* Map Modal */}
        <Dialog open={isMapModalOpen} onOpenChange={(open) => {
          setIsMapModalOpen(open);
          if (!open) setGeoJsonData(null);
        }}>
          {geoJsonData && (
            <DialogContent className="max-w-6xl w-full h-[90vh] flex flex-col p-0 bg-white border border-gray-200">
              <div className="p-4 border-b border-gray-200 flex justify-between items-center">
                <DialogTitle>Map View - Log ID: {selectedLog?.id}</DialogTitle>
              </div>
              <div className="flex-1 relative">
                <MapComponent geoJsonData={geoJsonData} />
              </div>
            </DialogContent>
        )}
        </Dialog>

        {/* Edit Modal */}
        <Dialog open={isEditModalOpen} onOpenChange={(open) => {
          setIsEditModalOpen(open);
          if (!open) setSelectedLog(null);
        }}>
          {selectedLog && (
            <DialogContent className="max-w-2xl bg-white border border-gray-200">
              <DialogHeader>
                <DialogTitle className="text-gray-900">Edit Log - ID: {selectedLog.id}</DialogTitle>
              </DialogHeader>
                <div className="space-y-4">
                  <div>
                  <div className="flex items-center justify-between mb-1">
                    <Label htmlFor="car" className="text-gray-700">Car</Label>
                    {editForm.car && (
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        className="h-6 px-2 text-xs text-gray-600 hover:text-gray-900"
                        onClick={() => setEditForm({ ...editForm, car: '' })}
                      >
                        Clear
                      </Button>
                    )}
                  </div>
                  {loadingLookups ? (
                    <Input
                      id="car"
                      type="text"
                      value="Loading..."
                      disabled
                      className="bg-gray-100 border-gray-300"
                    />
                  ) : (
                    <Select
                      value={editForm.car || undefined}
                      onValueChange={(value) => {
                        console.log('Car selected:', value);
                        setEditForm({ ...editForm, car: value });
                      }}
                    >
                      <SelectTrigger id="car" className="bg-white border-gray-300">
                        <SelectValue placeholder="Select a car" />
                      </SelectTrigger>
                      <SelectContent className="bg-white border border-gray-200 z-[100]">
                        {cars.length === 0 ? (
                          <div className="px-2 py-1.5 text-sm text-gray-500">No cars available</div>
                        ) : (
                          cars.map((car) => (
                            <SelectItem key={car.id} value={car.id.toString()}>
                              {car.name}
                            </SelectItem>
                          ))
                        )}
                      </SelectContent>
                    </Select>
                  )}
                  </div>
                  <div>
                  <div className="flex items-center justify-between mb-1">
                    <Label htmlFor="driver" className="text-gray-700">Driver</Label>
                    {editForm.driver && (
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        className="h-6 px-2 text-xs text-gray-600 hover:text-gray-900"
                        onClick={() => setEditForm({ ...editForm, driver: '' })}
                      >
                        Clear
                      </Button>
                    )}
                  </div>
                  {loadingLookups ? (
                    <Input
                      id="driver"
                      type="text"
                      value="Loading..."
                      disabled
                      className="bg-gray-100 border-gray-300"
                    />
                  ) : (
                    <Select
                      value={editForm.driver || undefined}
                      onValueChange={(value) => {
                        console.log('Driver selected:', value);
                        setEditForm({ ...editForm, driver: value });
                      }}
                    >
                      <SelectTrigger id="driver" className="bg-white border-gray-300">
                        <SelectValue placeholder="Select a driver" />
                      </SelectTrigger>
                      <SelectContent className="bg-white border border-gray-200 z-[100]">
                        {drivers.length === 0 ? (
                          <div className="px-2 py-1.5 text-sm text-gray-500">No drivers available</div>
                        ) : (
                          drivers.map((driver) => (
                            <SelectItem key={driver.id} value={driver.id.toString()}>
                              {driver.name}
                            </SelectItem>
                          ))
                        )}
                      </SelectContent>
                    </Select>
                  )}
                  </div>
                  <div>
                  <div className="flex items-center justify-between mb-1">
                    <Label htmlFor="event_type" className="text-gray-700">Event Type</Label>
                    {editForm.event_type && (
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        className="h-6 px-2 text-xs text-gray-600 hover:text-gray-900"
                        onClick={() => setEditForm({ ...editForm, event_type: '' })}
                      >
                        Clear
                      </Button>
                    )}
                  </div>
                  {loadingLookups ? (
                    <Input
                      id="event_type"
                      type="text"
                      value="Loading..."
                      disabled
                      className="bg-gray-100 border-gray-300"
                    />
                  ) : (
                    <Select
                      value={editForm.event_type || undefined}
                      onValueChange={(value) => {
                        console.log('Event type selected:', value);
                        setEditForm({ ...editForm, event_type: value });
                      }}
                    >
                      <SelectTrigger id="event_type" className="bg-white border-gray-300">
                        <SelectValue placeholder="Select an event type" />
                      </SelectTrigger>
                      <SelectContent className="bg-white border border-gray-200 z-[100]">
                        {eventTypes.length === 0 ? (
                          <div className="px-2 py-1.5 text-sm text-gray-500">No event types available</div>
                        ) : (
                          eventTypes.map((eventType) => (
                            <SelectItem key={eventType.id} value={eventType.id.toString()}>
                              {eventType.name}
                            </SelectItem>
                          ))
                        )}
                      </SelectContent>
                    </Select>
                  )}
                  </div>
                  <div>
                    <Label className="text-gray-700">Tags</Label>
                    <p className="text-xs text-gray-500 mb-1">Add custom tags for filtering (e.g. bell crank testing)</p>
                    <div className="flex flex-wrap gap-2 mb-2">
                      {(editForm.tags || []).map((tag) => (
                        <span
                          key={tag}
                          className="inline-flex items-center gap-1 px-2 py-1 rounded-md bg-gray-100 text-gray-800 text-sm border border-gray-200"
                        >
                          {tag}
                          <button
                            type="button"
                            aria-label={`Remove tag ${tag}`}
                            className="ml-0.5 text-gray-500 hover:text-red-600 focus:outline-none"
                            onClick={() => setEditForm({ ...editForm, tags: (editForm.tags || []).filter((t) => t !== tag) })}
                          >
                            ×
                          </button>
                        </span>
                      ))}
                    </div>
                    <div className="flex gap-2">
                      <Input
                        type="text"
                        placeholder="New tag"
                        value={editTagInput}
                        onChange={(e) => setEditTagInput(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter') {
                            e.preventDefault();
                            const v = editTagInput.trim();
                            if (v && !(editForm.tags || []).includes(v)) {
                              setEditForm({ ...editForm, tags: [...(editForm.tags || []), v] });
                              setEditTagInput('');
                            }
                          }
                        }}
                        className="flex-1 bg-white border-gray-300"
                      />
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        className="border-gray-300"
                        onClick={() => {
                          const v = editTagInput.trim();
                          if (v && !(editForm.tags || []).includes(v)) {
                            setEditForm({ ...editForm, tags: [...(editForm.tags || []), v] });
                            setEditTagInput('');
                          }
                        }}
                      >
                        Add
                      </Button>
                    </div>
                  </div>
                  <div>
                  <Label htmlFor="notes" className="text-gray-700">Notes</Label>
                  <Textarea
                    id="notes"
                      value={editForm.notes}
                      onChange={(e) => setEditForm({ ...editForm, notes: e.target.value })}
                      rows={4}
                      className="bg-white border-gray-300"
                    />
                  </div>
                <DialogFooter>
                  <Button
                    onClick={() => handleUpdateLog(selectedLog.id, false)}
                    disabled={saving}
                    className="bg-purple-600 hover:bg-purple-700 text-white"
                  >
                    {saving ? 'Saving...' : 'Save'}
                  </Button>
                  <Button
                    onClick={() => {
                      setIsEditModalOpen(false);
                      setSelectedLog(null);
                    }}
                    className="bg-gray-100 hover:bg-gray-200 text-gray-700 border border-gray-300"
                  >
                    Cancel
                  </Button>
                </DialogFooter>
                  </div>
            </DialogContent>
        )}
        </Dialog>

        {/* Delete Confirmation Modal */}
        <Dialog open={isDeleteModalOpen} onOpenChange={(open) => {
          setIsDeleteModalOpen(open);
          if (!open) setLogToDelete(null);
        }}>
          {logToDelete !== null && (
            <DialogContent className="max-w-md bg-white border border-gray-200">
              <DialogHeader>
                <DialogTitle className="text-gray-900">Confirm Delete</DialogTitle>
                <DialogDescription className="text-gray-600">
                  Are you sure you want to delete log ID {logToDelete}? This action cannot be undone.
                </DialogDescription>
              </DialogHeader>
              <DialogFooter>
                <Button
                    onClick={() => handleDeleteLog(logToDelete)}
                    disabled={deleting}
                    className="bg-red-600 hover:bg-red-700 text-white"
                  >
                    {deleting ? 'Deleting...' : 'Delete'}
                </Button>
                <Button
                    onClick={() => {
                      setIsDeleteModalOpen(false);
                      setLogToDelete(null);
                    }}
                    className="bg-gray-100 hover:bg-gray-200 text-gray-700 border border-gray-300"
                  >
                    Cancel
                </Button>
              </DialogFooter>
            </DialogContent>
          )}
        </Dialog>
        </div>
    </div>
  );
}
