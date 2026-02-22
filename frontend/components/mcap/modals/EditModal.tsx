'use client';

import { useState, useEffect, useRef } from 'react';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { ChevronDown, X, Check } from 'lucide-react';
import type { McapLog } from '@/lib/mcap/types';

export interface EditForm {
    cars: string[];
    drivers: string[];
    event_types: string[];
    locations: string[];
    notes: string;
    tags: string[];
}

function normalizeList(v: unknown): string[] {
    if (!Array.isArray(v)) return [];
    return v.filter((x): x is string => typeof x === 'string' && x.trim() !== '');
}

// ── Fuzzy match: returns true if all chars of query appear in order in str ──
function fuzzyMatch(str: string, query: string): boolean {
    if (!query) return true;
    const s = str.toLowerCase();
    const q = query.toLowerCase().trim();
    let si = 0;
    for (let qi = 0; qi < q.length; qi++) {
        si = s.indexOf(q[qi], si);
        if (si === -1) return false;
        si++;
    }
    return true;
}

// ─────────────────────────────────────────────
//  ComboboxChipInput
//  Dropdown with fuzzy search + free-type add
// ─────────────────────────────────────────────
interface ComboboxChipInputProps {
    label: string;
    selected: string[];
    options: string[];              // from lookups
    onAdd: (value: string) => void;
    onRemove: (value: string) => void;
}

function ComboboxChipInput({ label, selected, options, onAdd, onRemove }: ComboboxChipInputProps) {
    const [query, setQuery] = useState('');
    const [open, setOpen] = useState(false);
    const containerRef = useRef<HTMLDivElement>(null);
    const inputRef = useRef<HTMLInputElement>(null);

    // Close dropdown on outside click
    useEffect(() => {
        const handler = (e: MouseEvent) => {
            if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
                setOpen(false);
            }
        };
        document.addEventListener('mousedown', handler);
        return () => document.removeEventListener('mousedown', handler);
    }, []);

    const handleAdd = (value: string) => {
        const v = value.trim();
        if (!v) return;
        if (!selected.some((s) => s.toLowerCase() === v.toLowerCase())) {
            onAdd(v);
        }
        setQuery('');
        inputRef.current?.focus();
    };

    const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
        if (e.key === 'Enter') {
            e.preventDefault();
            // Add the typed query directly (allow free entry)
            if (query.trim()) handleAdd(query);
        } else if (e.key === 'Escape') {
            setOpen(false);
        } else if (e.key === 'Backspace' && !query && selected.length > 0) {
            onRemove(selected[selected.length - 1]);
        }
    };

    // Filtered options: exclude already-selected, fuzzy-match query
    const filtered = options
        .filter((o) => !selected.some((s) => s.toLowerCase() === o.toLowerCase()))
        .filter((o) => fuzzyMatch(o, query))
        .slice(0, 12);

    // If typed query isn't in the filtered list, offer "Add <query>"
    const showAddNew =
        query.trim().length > 0 &&
        !filtered.some((o) => o.toLowerCase() === query.trim().toLowerCase()) &&
        !selected.some((s) => s.toLowerCase() === query.trim().toLowerCase());

    const slug = label.toLowerCase().replace(/\s+/g, '-');

    return (
        <div ref={containerRef} className="relative">
            {/* Selected chips */}
            <div
                className="flex flex-wrap gap-1.5 mb-2 min-h-[1.5rem]"
                role="list"
                aria-label={`Selected ${label}`}
            >
                {selected.map((item) => (
                    <span key={item} className="edit-chip" role="listitem">
                        {item}
                        <button
                            type="button"
                            aria-label={`Remove ${item}`}
                            onClick={() => onRemove(item)}
                        >
                            <X className="h-3 w-3" />
                        </button>
                    </span>
                ))}
            </div>

            {/* Input */}
            <div
                className="flex items-center gap-1.5 rounded-md px-2.5 py-1.5 cursor-text"
                style={{
                    background: 'var(--off-white)',
                    border: `1px solid ${open ? 'var(--ochre)' : 'rgba(42,38,34,0.22)'}`,
                    boxShadow: open
                        ? '0 0 0 2px rgba(195,136,34,0.2), 0 1px 3px rgba(42,38,34,0.07) inset'
                        : '0 1px 3px rgba(42,38,34,0.07) inset',
                    transition: 'border-color .14s, box-shadow .14s',
                }}
                onClick={() => { setOpen(true); inputRef.current?.focus(); }}
            >
                <input
                    ref={inputRef}
                    id={slug}
                    type="text"
                    className="flex-1 bg-transparent outline-none text-sm min-w-0"
                    style={{ color: 'var(--charcoal)', fontFamily: 'inherit' }}
                    placeholder={selected.length ? '' : `Search or add ${label.toLowerCase()}…`}
                    value={query}
                    onChange={(e) => { setQuery(e.target.value); setOpen(true); }}
                    onFocus={() => setOpen(true)}
                    onKeyDown={handleKeyDown}
                    aria-autocomplete="list"
                    aria-expanded={open}
                    aria-controls={`${slug}-listbox`}
                    role="combobox"
                />
                <ChevronDown
                    className="h-3.5 w-3.5 shrink-0 transition-transform"
                    style={{ color: 'var(--sienna)', transform: open ? 'rotate(180deg)' : 'none' }}
                />
            </div>

            {/* Dropdown */}
            {open && (filtered.length > 0 || showAddNew) && (
                <div
                    id={`${slug}-listbox`}
                    role="listbox"
                    className="absolute z-50 w-full mt-1 rounded-md shadow-lg overflow-hidden"
                    style={{
                        background: 'var(--off-white)',
                        border: '1px solid rgba(42,38,34,0.22)',
                        boxShadow: '0 4px 16px rgba(42,38,34,0.14)',
                        maxHeight: 220,
                        overflowY: 'auto',
                    }}
                >
                    {showAddNew && (
                        <button
                            type="button"
                            role="option"
                            className="w-full text-left px-3 py-2 text-sm flex items-center gap-2 hover:opacity-80"
                            style={{ background: 'rgba(195,136,34,0.08)', color: 'var(--ochre-dark)', fontWeight: 600 }}
                            onMouseDown={(e) => { e.preventDefault(); handleAdd(query); setOpen(false); }}
                        >
                            <span style={{ fontSize: '1rem' }}>+</span>
                            Add &ldquo;{query.trim()}&rdquo;
                        </button>
                    )}

                    {filtered.map((option) => {
                        const alreadySelected = selected.some((s) => s.toLowerCase() === option.toLowerCase());
                        return (
                            <button
                                key={option}
                                type="button"
                                role="option"
                                aria-selected={alreadySelected}
                                className="w-full text-left px-3 py-2 text-sm flex items-center justify-between"
                                style={{
                                    color: 'var(--charcoal)',
                                    background: alreadySelected ? 'rgba(195,136,34,0.07)' : 'transparent',
                                    transition: 'background .1s',
                                }}
                                onMouseEnter={(e) => { (e.currentTarget as HTMLElement).style.background = 'rgba(42,38,34,0.05)'; }}
                                onMouseLeave={(e) => { (e.currentTarget as HTMLElement).style.background = alreadySelected ? 'rgba(195,136,34,0.07)' : 'transparent'; }}
                                onMouseDown={(e) => {
                                    e.preventDefault();
                                    handleAdd(option);
                                    setOpen(false);
                                }}
                            >
                                {option}
                                {alreadySelected && <Check className="h-3.5 w-3.5 shrink-0" style={{ color: 'var(--ochre)' }} />}
                            </button>
                        );
                    })}
                </div>
            )}
        </div>
    );
}

// ─────────────────────────────────────────────
//  EditModal
// ─────────────────────────────────────────────
interface Props {
    log: McapLog | null;
    open: boolean;
    saving: boolean;
    lookups: {
        cars: string[];
        drivers: string[];
        eventTypes: string[];
        locations: string[];
        tags: string[];
    };
    onClose: () => void;
    onSave: (form: EditForm) => void;
}

export function EditModal({ log, open, saving, lookups, onClose, onSave }: Props) {
    const [form, setForm] = useState<EditForm>({
        cars: [], drivers: [], event_types: [], locations: [], notes: '', tags: [],
    });

    // Sync form when log/open changes
    useEffect(() => {
        if (log && open) {
            setForm({
                cars: normalizeList(log.cars),
                drivers: normalizeList(log.drivers),
                event_types: normalizeList(log.event_types),
                locations: normalizeList(log.locations),
                notes: log.notes ?? '',
                tags: normalizeList(log.tags),
            });
        }
    }, [log, open]);

    const addItem = (key: keyof Omit<EditForm, 'notes'>, value: string) => {
        const v = value.trim();
        if (v && !form[key].some((x) => x.toLowerCase() === v.toLowerCase())) {
            setForm((f) => ({ ...f, [key]: [...f[key], v] }));
        }
    };

    const removeItem = (key: keyof Omit<EditForm, 'notes'>, val: string) =>
        setForm((f) => ({ ...f, [key]: f[key].filter((x) => x !== val) }));

    const fields: {
        key: keyof Omit<EditForm, 'notes'>;
        label: string;
        options: string[];
    }[] = [
            { key: 'cars', label: 'Cars', options: lookups.cars },
            { key: 'drivers', label: 'Drivers', options: lookups.drivers },
            { key: 'event_types', label: 'Event Types', options: lookups.eventTypes },
            { key: 'locations', label: 'Locations', options: lookups.locations },
            { key: 'tags', label: 'Tags', options: lookups.tags },
        ];

    return (
        <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
            {log && (
                <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
                    <DialogHeader>
                        <DialogTitle className="font-serif text-lg" style={{ color: 'var(--charcoal)' }}>
                            Edit Log — ID {log.id}
                        </DialogTitle>
                    </DialogHeader>

                    <div className="space-y-5 mt-1">
                        {fields.map(({ key, label, options }) => (
                            <div key={key}>
                                <Label
                                    htmlFor={label.toLowerCase().replace(/\s+/g, '-')}
                                    className="text-[10px] font-semibold uppercase tracking-wide mb-1.5 block"
                                    style={{ color: 'var(--sienna)' }}
                                >
                                    {label}
                                </Label>
                                <ComboboxChipInput
                                    label={label}
                                    selected={form[key]}
                                    options={options}
                                    onAdd={(v) => addItem(key, v)}
                                    onRemove={(v) => removeItem(key, v)}
                                />
                            </div>
                        ))}

                        <div>
                            <Label
                                htmlFor="edit-notes"
                                className="text-[10px] font-semibold uppercase tracking-wide mb-1.5 block"
                                style={{ color: 'var(--sienna)' }}
                            >
                                Notes
                            </Label>
                            <Textarea
                                id="edit-notes"
                                value={form.notes}
                                onChange={(e) => setForm((f) => ({ ...f, notes: e.target.value }))}
                                rows={4}
                                style={{ background: 'var(--off-white)' }}
                            />
                        </div>
                    </div>

                    <DialogFooter className="gap-2 mt-4">
                        <button className="skeuo-btn-ghost" onClick={onClose} disabled={saving}>
                            Cancel
                        </button>
                        <button className="skeuo-btn-primary" onClick={() => onSave(form)} disabled={saving}>
                            {saving ? 'Saving…' : 'Save'}
                        </button>
                    </DialogFooter>
                </DialogContent>
            )}
        </Dialog>
    );
}
