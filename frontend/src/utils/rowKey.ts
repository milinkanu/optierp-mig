// Stable client-only keys for editable grid rows, so Vue tracks row identity
// across insert/delete (index keys carry focus + child state to the wrong row).
// The key rides along on the row object (under `_rowKey`) and is ignored by the
// backend (create schemas ignore unknown fields).

let seq = 0;
export const rowKey = (): string => `r${(seq += 1)}`;
