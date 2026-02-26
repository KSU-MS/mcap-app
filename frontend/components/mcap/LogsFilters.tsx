'use client';

import { useCallback, useEffect, useRef, useTransition } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Search } from 'lucide-react';
import { DatePickerInput } from './DatePickerInput';

interface Lookups {
    cars: string[];
    drivers: string[];
    eventTypes: string[];
    locations: string[];
    tags: string[];
    channels: string[];
}

interface Props {
    lookups: Lookups;
}

const FILTER_KEYS = ['search', 'start_date', 'end_date', 'car', 'event_type', 'driver', 'location', 'channel', 'tag'] as const;

export function LogsFilters({ lookups }: Props) {
    const router = useRouter();
    const params = useSearchParams();
    const [isPending, startTransition] = useTransition();
    const searchDebounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

    const update = useCallback(
        (key: string, value: string) => {
            const next = new URLSearchParams(params.toString());
            if (value && value !== 'all') {
                next.set(key, value);
            } else {
                next.delete(key);
            }
            // Reset to page 1 when filters change
            next.delete('page');
            startTransition(() => {
                router.push(`?${next.toString()}`, { scroll: false });
            });
        },
        [params, router],
    );

    const clearAll = () => {
        startTransition(() => {
            router.push('?', { scroll: false });
        });
    };

    const hasFilters = FILTER_KEYS.some((k) => params.has(k));

    const handleSearchChange = (value: string) => {
        if (searchDebounceRef.current) {
            clearTimeout(searchDebounceRef.current);
        }
        searchDebounceRef.current = setTimeout(() => update('search', value), 300);
    };

    useEffect(() => {
        return () => {
            if (searchDebounceRef.current) clearTimeout(searchDebounceRef.current);
        };
    }, []);

    return (
        <div>
            {/* Search — full width */}
            <div className="relative mb-3">
                <Search
                    className="absolute left-3 top-1/2 -translate-y-1/2 h-3.5 w-3.5 pointer-events-none"
                    style={{ color: 'var(--sienna)' }}
                />
                <input
                    type="text"
                    placeholder="Search by ID, car, driver, event type, notes…"
                        defaultValue={params.get('search') ?? ''}
                    className="skeuo-input w-full"
                    style={{ paddingLeft: '2.25rem' }}
                    onChange={(e) => handleSearchChange(e.target.value)}
                />
            </div>

            {/* Filter rows */}
            <div className="flex flex-col gap-2">
                {/* Row 1: dates + main dropdowns */}
                <div className="flex flex-wrap items-end gap-2">
                    <FilterGroup label="From">
                        <DatePickerInput
                            key={`start-date-${params.get('start_date') ?? ''}`}
                            value={params.get('start_date') ?? ''}
                            onChange={(v) => update('start_date', v)}
                            placeholder="Start date"
                            width="w-[140px]"
                        />
                    </FilterGroup>

                    <FilterGroup label="To">
                        <DatePickerInput
                            key={`end-date-${params.get('end_date') ?? ''}`}
                            value={params.get('end_date') ?? ''}
                            onChange={(v) => update('end_date', v)}
                            placeholder="End date"
                            width="w-[140px]"
                        />
                    </FilterGroup>

                    <FilterGroup label="Car">
                        <DropdownFilter
                            value={params.get('car') ?? ''}
                            options={lookups.cars}
                            onChange={(v) => update('car', v)}
                            width="w-[110px]"
                        />
                    </FilterGroup>

                    <FilterGroup label="Event type">
                        <DropdownFilter
                            value={params.get('event_type') ?? ''}
                            options={lookups.eventTypes}
                            onChange={(v) => update('event_type', v)}
                            width="w-[130px]"
                        />
                    </FilterGroup>

                    <FilterGroup label="Driver">
                        <DropdownFilter
                            value={params.get('driver') ?? ''}
                            options={lookups.drivers}
                            onChange={(v) => update('driver', v)}
                            width="w-[110px]"
                        />
                    </FilterGroup>

                    <FilterGroup label="Tag">
                        <DropdownFilter
                            value={params.get('tag') ?? ''}
                            options={lookups.tags}
                            onChange={(v) => update('tag', v)}
                            width="w-[110px]"
                        />
                    </FilterGroup>

                    <FilterGroup label="Channel">
                        <DropdownFilter
                            value={params.get('channel') ?? ''}
                            options={lookups.channels}
                            onChange={(v) => update('channel', v)}
                            width="w-[130px]"
                        />
                    </FilterGroup>

                    <FilterGroup label="Location">
                        <DropdownFilter
                            value={params.get('location') ?? ''}
                            options={lookups.locations}
                            onChange={(v) => update('location', v)}
                            width="w-[130px]"
                        />
                    </FilterGroup>

                    {hasFilters && (
                        <button
                            className="skeuo-btn-ghost text-xs h-[34px] self-end"
                            onClick={clearAll}
                        >
                            Clear filters
                        </button>
                    )}
                </div>
            </div>

            {isPending && (
                <div className="mt-1 text-xs" style={{ color: 'var(--sienna)' }}>Updating…</div>
            )}
        </div>
    );
}

function FilterGroup({ label, children }: { label: string; children: React.ReactNode }) {
    return (
        <div className="flex flex-col gap-1">
            <span className="text-[10px] font-semibold uppercase tracking-wide" style={{ color: 'var(--sienna)' }}>
                {label}
            </span>
            {children}
        </div>
    );
}

function DropdownFilter({
    value, options, onChange, width,
}: {
    value: string;
    options: string[];
    onChange: (v: string) => void;
    width: string;
}) {
    return (
        <Select value={value || 'all'} onValueChange={onChange}>
            <SelectTrigger className={`${width} h-[34px] text-xs`} style={{ background: 'var(--off-white)', borderColor: 'rgba(42,38,34,0.22)' }}>
                <SelectValue placeholder="All" />
            </SelectTrigger>
            <SelectContent style={{ background: 'var(--off-white)' }}>
                <SelectItem value="all">All</SelectItem>
                {options.map((o) => (
                    <SelectItem key={o} value={o}>{o}</SelectItem>
                ))}
            </SelectContent>
        </Select>
    );
}
