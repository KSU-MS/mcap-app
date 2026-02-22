'use client';

import { useState, useRef, useEffect } from 'react';
import { CalendarDays, ChevronLeft, ChevronRight, X } from 'lucide-react';

interface Props {
    value: string;           // ISO date string "YYYY-MM-DD" or ""
    onChange: (v: string) => void;
    placeholder?: string;
    width?: string;
}

const DAYS = ['Su', 'Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa'];
const MONTHS = [
    'January', 'February', 'March', 'April', 'May', 'June',
    'July', 'August', 'September', 'October', 'November', 'December',
];

function parseLocal(iso: string): Date | null {
    if (!iso) return null;
    const [y, m, d] = iso.split('-').map(Number);
    if (!y || !m || !d) return null;
    return new Date(y, m - 1, d);
}

function toIso(date: Date): string {
    const y = date.getFullYear();
    const m = String(date.getMonth() + 1).padStart(2, '0');
    const d = String(date.getDate()).padStart(2, '0');
    return `${y}-${m}-${d}`;
}

function formatDisplay(iso: string): string {
    const d = parseLocal(iso);
    if (!d) return '';
    return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
}

/** Parse a user-typed string into a Date — handles many formats. */
function parseUserInput(raw: string): Date | null {
    const s = raw.trim();
    if (!s) return null;
    // ISO: YYYY-MM-DD (avoid timezone shift)
    if (/^\d{4}-\d{2}-\d{2}$/.test(s)) {
        const [y, m, d] = s.split('-').map(Number);
        return new Date(y, m - 1, d);
    }
    // Try native parse (handles "Feb 14 2026", "February 14, 2026", etc.)
    const native = new Date(s);
    if (!isNaN(native.getTime())) return native;
    // Slash/dot-separated: try M/D/YY, D/M/YY, YYYY/M/D
    const parts = s.split(/[\/\-\.]/).map(Number);
    if (parts.length === 3 && parts.every((n) => !isNaN(n))) {
        const [a, b, c] = parts;
        if (a > 31) return new Date(a, b - 1, c);          // YYYY/M/D
        if (a > 12) return new Date(c < 100 ? 2000 + c : c, b - 1, a); // D/M/YY
        return new Date(c < 100 ? 2000 + c : c, a - 1, b); // M/D/YY
    }
    return null;
}

export function DatePickerInput({
    value,
    onChange,
    placeholder = 'mm/dd/yyyy',
    width = 'w-[140px]',
}: Props) {
    const [open, setOpen] = useState(false);
    const [inputVal, setInputVal] = useState(value ? formatDisplay(value) : '');
    const [inputError, setInputError] = useState(false);

    const selectedDate = parseLocal(value);
    const today = new Date();

    const [viewYear, setViewYear] = useState(selectedDate?.getFullYear() ?? today.getFullYear());
    const [viewMonth, setViewMonth] = useState(selectedDate?.getMonth() ?? today.getMonth());

    const containerRef = useRef<HTMLDivElement>(null);
    const inputRef = useRef<HTMLInputElement>(null);

    // Sync display when value changes externally (e.g. Clear All)
    useEffect(() => {
        setInputVal(value ? formatDisplay(value) : '');
        setInputError(false);
    }, [value]);

    // Close popover on outside click
    useEffect(() => {
        if (!open) return;
        const handler = (e: MouseEvent) => {
            if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
                setOpen(false);
                // Revert stale text to last confirmed value on close
                setInputVal(value ? formatDisplay(value) : '');
                setInputError(false);
            }
        };
        document.addEventListener('mousedown', handler);
        return () => document.removeEventListener('mousedown', handler);
    }, [open, value]);

    const openCalendar = () => {
        const base = selectedDate ?? today;
        setViewYear(base.getFullYear());
        setViewMonth(base.getMonth());
        setOpen((prev) => !prev);
    };

    const commitTyped = (raw: string) => {
        if (!raw.trim()) {
            onChange('');
            setInputError(false);
            return;
        }
        const parsed = parseUserInput(raw);
        if (!parsed || isNaN(parsed.getTime())) {
            setInputError(true);
            return;
        }
        setInputError(false);
        setViewYear(parsed.getFullYear());
        setViewMonth(parsed.getMonth());
        onChange(toIso(parsed));
        setInputVal(formatDisplay(toIso(parsed)));
        setOpen(false);
    };

    const selectDay = (date: Date) => {
        onChange(toIso(date));
        setInputVal(formatDisplay(toIso(date)));
        setInputError(false);
        setOpen(false);
    };

    const clearValue = (e: React.MouseEvent) => {
        e.stopPropagation();
        onChange('');
        setInputVal('');
        setInputError(false);
        setOpen(false);
        inputRef.current?.focus();
    };

    // Calendar grid
    const firstDay = new Date(viewYear, viewMonth, 1).getDay();
    const daysInMonth = new Date(viewYear, viewMonth + 1, 0).getDate();
    const daysInPrev = new Date(viewYear, viewMonth, 0).getDate();
    type Cell = { date: Date; currentMonth: boolean };
    const cells: Cell[] = [];
    for (let i = firstDay - 1; i >= 0; i--)
        cells.push({ date: new Date(viewYear, viewMonth - 1, daysInPrev - i), currentMonth: false });
    for (let d = 1; d <= daysInMonth; d++)
        cells.push({ date: new Date(viewYear, viewMonth, d), currentMonth: true });
    let nxt = 1;
    while (cells.length < 42)
        cells.push({ date: new Date(viewYear, viewMonth + 1, nxt++), currentMonth: false });

    const isSameDay = (a: Date, b: Date) =>
        a.getFullYear() === b.getFullYear() &&
        a.getMonth() === b.getMonth() &&
        a.getDate() === b.getDate();

    const prevMonth = (e: React.MouseEvent) => {
        e.stopPropagation();
        setViewMonth((m) => { if (m === 0) { setViewYear((y) => y - 1); return 11; } return m - 1; });
    };
    const nextMonth = (e: React.MouseEvent) => {
        e.stopPropagation();
        setViewMonth((m) => { if (m === 11) { setViewYear((y) => y + 1); return 0; } return m + 1; });
    };

    return (
        <div ref={containerRef} className={`relative ${width}`}>
            {/* ── Inline text input with icon ── */}
            <div className={`cal-input-wrap${inputError ? ' cal-input-wrap-error' : ''}`}>
                <input
                    ref={inputRef}
                    type="text"
                    value={inputVal}
                    placeholder={placeholder}
                    className="cal-inline-input"
                    onChange={(e) => { setInputVal(e.target.value); setInputError(false); }}
                    onKeyDown={(e) => {
                        if (e.key === 'Enter') { commitTyped(inputVal); }
                        if (e.key === 'Escape') { setOpen(false); setInputVal(value ? formatDisplay(value) : ''); }
                        if (e.key === 'ArrowDown') { e.preventDefault(); if (!open) openCalendar(); }
                    }}
                    onBlur={(e) => {
                        // Don't commit if focus moved inside the container (e.g. clicking a calendar day)
                        if (containerRef.current?.contains(e.relatedTarget as Node)) return;
                        commitTyped(inputVal);
                    }}
                    aria-label="Date"
                    autoComplete="off"
                />

                {/* Clear button */}
                {value && (
                    <button
                        type="button"
                        className="cal-inline-clear"
                        onClick={clearValue}
                        tabIndex={-1}
                        aria-label="Clear date"
                    >
                        <X size={9} strokeWidth={2.5} />
                    </button>
                )}

                {/* Calendar toggle */}
                <button
                    type="button"
                    className={`cal-inline-icon${open ? ' cal-inline-icon-active' : ''}`}
                    onClick={openCalendar}
                    tabIndex={-1}
                    aria-label="Open calendar"
                >
                    <CalendarDays size={13} strokeWidth={1.8} />
                </button>
            </div>

            {/* Error hint */}
            {inputError && (
                <p className="cal-type-error-msg">Try m/d/yy or Mon DD YYYY</p>
            )}

            {/* ── Calendar popover ── */}
            {open && (
                <div className="cal-popover" role="dialog" aria-label="Calendar">
                    {/* Month / Year navigation */}
                    <div className="cal-header">
                        <button type="button" className="cal-nav-btn" onClick={prevMonth} aria-label="Previous month">
                            <ChevronLeft size={14} strokeWidth={2.5} />
                        </button>
                        <span className="cal-month-label">{MONTHS[viewMonth]} {viewYear}</span>
                        <button type="button" className="cal-nav-btn" onClick={nextMonth} aria-label="Next month">
                            <ChevronRight size={14} strokeWidth={2.5} />
                        </button>
                    </div>

                    {/* Weekday labels */}
                    <div className="cal-weekdays">
                        {DAYS.map((d) => <div key={d} className="cal-weekday">{d}</div>)}
                    </div>

                    {/* Day grid */}
                    <div className="cal-grid">
                        {cells.map(({ date, currentMonth }, i) => {
                            const isSelected = selectedDate ? isSameDay(date, selectedDate) : false;
                            const isToday = isSameDay(date, today);
                            return (
                                <button
                                    key={i}
                                    type="button"
                                    onMouseDown={(e) => e.preventDefault()} // prevent blur on input
                                    onClick={() => selectDay(date)}
                                    className={[
                                        'cal-day',
                                        !currentMonth && 'cal-day-other',
                                        isToday && !isSelected && 'cal-day-today',
                                        isSelected && 'cal-day-selected',
                                    ].filter(Boolean).join(' ')}
                                >
                                    {date.getDate()}
                                </button>
                            );
                        })}
                    </div>

                    {/* Footer */}
                    <div className="cal-footer">
                        <button type="button" className="cal-footer-btn"
                            onMouseDown={(e) => e.preventDefault()}
                            onClick={() => selectDay(today)}>
                            Today
                        </button>
                        <button type="button" className="cal-footer-btn cal-footer-clear"
                            onMouseDown={(e) => e.preventDefault()}
                            onClick={() => { onChange(''); setInputVal(''); setOpen(false); }}>
                            Clear
                        </button>
                    </div>
                </div>
            )}
        </div>
    );
}
