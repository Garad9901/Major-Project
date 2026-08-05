// Copyright (c) 2026 Yash Garad. All rights reserved.

function PlusIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
         strokeLinecap="round" className="h-4 w-4">
      <path d="M12 5v14M5 12h14" />
    </svg>
  );
}

function TrashIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
         strokeLinecap="round" strokeLinejoin="round" className="h-3.5 w-3.5">
      <path d="M3 6h18M8 6V4h8v2M6 6l1 14h10l1-14" />
    </svg>
  );
}

function Sidebar({ conversations, activeId, onSelect, onNew, onDelete, open, onClose }) {
  return (
    <>
      {/* Backdrop, phones only — the sidebar overlays the chat there. */}
      {open && (
        <div
          onClick={onClose}
          className="fixed inset-0 z-20 bg-black/40 md:hidden"
          aria-hidden="true"
        />
      )}

      <aside
        className={`fixed inset-y-0 left-0 z-30 flex w-64 flex-col border-r border-neutral-200 bg-neutral-50
                    transition-transform duration-200 md:static md:translate-x-0
                    dark:border-neutral-800 dark:bg-neutral-900
                    ${open ? "translate-x-0" : "-translate-x-full"}`}
      >
        <div className="p-3">
          <button
            onClick={onNew}
            className="flex w-full items-center gap-2 rounded-lg border border-neutral-300 px-3 py-2 text-sm
                       font-medium text-neutral-700 transition hover:bg-neutral-200/60
                       dark:border-neutral-700 dark:text-neutral-200 dark:hover:bg-neutral-800"
          >
            <PlusIcon />
            New chat
          </button>
        </div>

        <nav className="flex-1 overflow-y-auto px-2 pb-3">
          {conversations.length === 0 ? (
            <p className="px-3 py-2 text-xs text-neutral-500 dark:text-neutral-500">
              No conversations yet.
            </p>
          ) : (
            <ul className="space-y-0.5">
              {conversations.map((c) => {
                const active = c.id === activeId;
                return (
                  <li key={c.id} className="group relative">
                    <button
                      onClick={() => onSelect(c.id)}
                      title={c.title}
                      className={`w-full truncate rounded-lg py-2 pl-3 pr-8 text-left text-sm transition
                        ${active
                          ? "bg-neutral-200 text-neutral-900 dark:bg-neutral-800 dark:text-neutral-100"
                          : "text-neutral-600 hover:bg-neutral-200/60 dark:text-neutral-400 dark:hover:bg-neutral-800/60"}`}
                    >
                      {c.title}
                    </button>
                    <button
                      onClick={() => onDelete(c.id)}
                      title="Delete conversation"
                      aria-label={`Delete conversation: ${c.title}`}
                      className="absolute right-1.5 top-1/2 -translate-y-1/2 rounded p-1 text-neutral-400
                                 opacity-0 transition group-hover:opacity-100 hover:text-red-500
                                 focus:opacity-100"
                    >
                      <TrashIcon />
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </nav>
      </aside>
    </>
  );
}

export default Sidebar;
