"use client";

const PAGE_SIZE_OPTIONS = [10, 25, 50];

export type PaginationState = {
  page: number;
  pageSize: number;
};

/** Compute the slice of items for the current page. */
export function paginate<T>(items: T[], state: PaginationState): T[] {
  const start = state.page * state.pageSize;
  return items.slice(start, start + state.pageSize);
}

/** Total number of pages given item count and page size. */
export function pageCount(total: number, pageSize: number): number {
  return Math.max(1, Math.ceil(total / pageSize));
}

/**
 * Reusable pagination controls.
 * Works with any array — caller passes total count and current state.
 */
export function PaginationControls({
  total,
  state,
  onChange,
}: {
  total: number;
  state: PaginationState;
  onChange: (next: PaginationState) => void;
}) {
  const pages = pageCount(total, state.pageSize);
  const start = state.page * state.pageSize + 1;
  const end = Math.min(start + state.pageSize - 1, total);

  if (total === 0) return null;

  return (
    <div className="pagination-controls">
      <span className="pagination-info">
        {start}&ndash;{end} of {total}
      </span>
      <button
        type="button"
        className="button button-sm button-secondary"
        disabled={state.page <= 0}
        onClick={() => onChange({ ...state, page: state.page - 1 })}
      >
        Prev
      </button>
      <span className="pagination-page">
        {state.page + 1} / {pages}
      </span>
      <button
        type="button"
        className="button button-sm button-secondary"
        disabled={state.page >= pages - 1}
        onClick={() => onChange({ ...state, page: state.page + 1 })}
      >
        Next
      </button>
      <select
        className="pagination-size"
        value={state.pageSize}
        onChange={(e) => onChange({ page: 0, pageSize: Number(e.target.value) })}
      >
        {PAGE_SIZE_OPTIONS.map((size) => (
          <option key={size} value={size}>
            {size} / page
          </option>
        ))}
      </select>
    </div>
  );
}
