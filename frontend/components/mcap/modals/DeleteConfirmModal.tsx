'use client';

import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from '@/components/ui/dialog';

interface Props {
    ids: number[];
    open: boolean;
    deleting: boolean;
    onClose: () => void;
    onConfirm: () => void;
}

export function DeleteConfirmModal({ ids, open, deleting, onClose, onConfirm }: Props) {
    return (
        <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
            <DialogContent className="max-w-md">
                <DialogHeader>
                    <DialogTitle className="font-serif text-lg" style={{ color: 'var(--charcoal)' }}>
                        Confirm Delete
                    </DialogTitle>
                    <DialogDescription style={{ color: 'var(--sienna)' }}>
                        {ids.length === 1
                            ? `Are you sure you want to delete log ID ${ids[0]}? This cannot be undone.`
                            : `Are you sure you want to delete ${ids.length} logs? This cannot be undone.`}
                    </DialogDescription>
                </DialogHeader>
                <DialogFooter className="gap-2">
                    <button className="skeuo-btn-ghost" onClick={onClose} disabled={deleting}>Cancel</button>
                    <button className="skeuo-btn-danger" onClick={onConfirm} disabled={deleting}>
                        {deleting ? 'Deleting…' : `Delete ${ids.length > 1 ? `${ids.length} logs` : 'log'}`}
                    </button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}
