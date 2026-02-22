'use client';

import { useState, useEffect } from 'react';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog';
import { Label } from '@/components/ui/label';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
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

interface ChipListProps {
    items: string[];
    onRemove: (v: string) => void;
    placeholder: string;
    inputValue: string;
    onInputChange: (v: string) => void;
    onAdd: () => void;
}

function ChipList({ items, onRemove, placeholder, inputValue, onInputChange, onAdd }: ChipListProps) {
    return (
        <div>
            <div className="flex flex-wrap gap-1.5 mb-2 min-h-[1.5rem]">
                {items.map((item) => (
                    <span key={item} className="edit-chip">
                        {item}
                        <button type="button" aria-label={`Remove ${item}`} onClick={() => onRemove(item)}>×</button>
                    </span>
                ))}
            </div>
            <div className="flex gap-2">
                <Input
                    type="text"
                    placeholder={placeholder}
                    value={inputValue}
                    onChange={(e) => onInputChange(e.target.value)}
                    onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); onAdd(); } }}
                    className="flex-1 text-sm"
                    style={{ background: 'var(--off-white)' }}
                />
                <button type="button" className="skeuo-btn-ghost text-xs px-3" onClick={onAdd}>Add</button>
            </div>
        </div>
    );
}

interface Props {
    log: McapLog | null;
    open: boolean;
    saving: boolean;
    onClose: () => void;
    onSave: (form: EditForm) => void;
}

export function EditModal({ log, open, saving, onClose, onSave }: Props) {
    const [form, setForm] = useState<EditForm>({
        cars: [], drivers: [], event_types: [], locations: [], notes: '', tags: [],
    });
    const [carInput, setCarInput] = useState('');
    const [driverInput, setDriverInput] = useState('');
    const [eventInput, setEventInput] = useState('');
    const [locationInput, setLocationInput] = useState('');
    const [tagInput, setTagInput] = useState('');

    // Sync form when log changes (i.e. each time the modal opens for a new log)
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
            setCarInput(''); setDriverInput(''); setEventInput('');
            setLocationInput(''); setTagInput('');
        }
    }, [log, open]);

    const addItem = (
        key: keyof Omit<EditForm, 'notes'>,
        input: string,
        setInput: (v: string) => void,
    ) => {
        const v = input.trim();
        if (v && !form[key].some((x) => x.toLowerCase() === v.toLowerCase())) {
            setForm((f) => ({ ...f, [key]: [...f[key], v] }));
        }
        setInput('');
    };

    const removeItem = (key: keyof Omit<EditForm, 'notes'>, val: string) =>
        setForm((f) => ({ ...f, [key]: f[key].filter((x) => x !== val) }));

    const fields: {
        key: keyof Omit<EditForm, 'notes'>;
        label: string;
        input: string;
        setInput: (v: string) => void;
    }[] = [
            { key: 'cars', label: 'Cars', input: carInput, setInput: setCarInput },
            { key: 'drivers', label: 'Drivers', input: driverInput, setInput: setDriverInput },
            { key: 'event_types', label: 'Event Types', input: eventInput, setInput: setEventInput },
            { key: 'locations', label: 'Locations', input: locationInput, setInput: setLocationInput },
            { key: 'tags', label: 'Tags', input: tagInput, setInput: setTagInput },
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
                        {fields.map(({ key, label, input, setInput }) => (
                            <div key={key}>
                                <Label
                                    className="text-[10px] font-semibold uppercase tracking-wide mb-1.5 block"
                                    style={{ color: 'var(--sienna)' }}
                                >
                                    {label}
                                </Label>
                                <ChipList
                                    items={form[key]}
                                    onRemove={(v) => removeItem(key, v)}
                                    placeholder={`Add ${label.toLowerCase().replace(/s$/, '')}`}
                                    inputValue={input}
                                    onInputChange={setInput}
                                    onAdd={() => addItem(key, input, setInput)}
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
