# Runtime journal

`MemoryJournal` and `SQLiteJournal(path)` share append, cursor-based read and
callback replay. A cursor is the last processed sequence, starting at zero.
Read returns detached lists of `(sequence, immutable Event)` pairs; replay calls
`consume(sequence, event)` in sequence order. It does not execute commands.

Event IDs are unique. Reappending identical canonical content returns its
original sequence; a conflicting payload raises `JournalError`. Each SQLite
append is a transaction, with full synchronous durability. Reopening preserves
ordering, correlation and dispatch suppression, including an interrupted
command with only its started event committed. Exactly-once external effects
are not promised: interrupted work requires reconciliation, never blind retry.

Create the database in an existing, owned directory not writable by others.
New databases are mode 0600. Existing nonprivate files, symlinks, hard links and
nonregular files are refused. An exclusive nonblocking file lock persists for
the adapter's lifetime; a second owner is refused. Use the context manager or
close explicitly. Inherited adapters and dispatch locks reject use in a forked
child before acquiring locks or touching SQLite; open adapters in their owning
process, and do not fork with a live journal. Do not rename/replace an open database or edit it outside this
adapter. SQLite file ownership and a shared dispatch lock enforce the initial
single-process runtime model; this is not a distributed event store.

Application ID and schema version must match before opening an existing
database for writes. Unknown versions and foreign/empty files are refused, not
migrated or overwritten. Future migrations require a separately reviewed
operation and backup. Invalid stored events fail reads instead of being skipped.
The journal contains runtime events, not LIT work records; it never accesses
LIT storage. Tests create only temporary databases, and no service is installed.
