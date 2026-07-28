# CLAUDE.md

Guidance for Claude Code when working in this repository.

## What this project is

A small, self-contained teaching example of two Python threading patterns. It
has no tests, no build step, and no package metadata — it is three scripts plus
a CLI. Treat it as sample code whose purpose is to be *read*, not as a library
with consumers. Clarity of the concurrency patterns matters more than feature
count.

## Commands

```bash
pip install -r requirements.txt

python main.py run threads                     # 4 workers, drains 50 tasks, exits
python main.py run threads --thread-workers 8
python main.py run producer-consumer           # 1 producer / 1 consumer — runs until Ctrl+C
python main.py run producer-consumer --producer-workers 2 --consumer-workers 4
python main.py list-variants

python threads.py           # equivalent to `run threads` with defaults
python producer_consumer.py # equivalent to `run producer-consumer` with defaults
```

There is no test suite and no linter configured. Verify changes by running the
commands above and reading `logs/`.

**`producer-consumer` never terminates on its own.** Always run it under a
timeout, or it will hang the session. Include `--kill-after`, because SIGINT
alone is not reliable here (see below):

```bash
timeout -s INT --kill-after=15 20 python main.py run producer-consumer --producer-workers 2 --consumer-workers 2
```

**Ctrl+C sometimes fails to stop it** — seen once in 33 runs at 2 producers /
4 consumers. The signal handler prints and logs *before* setting
`shutdown_event`; if that work raises, the exception escapes the handler, the
flag is never set, and `main()` blocks forever in `ThreadPoolExecutor.__exit__`
joining threads that are still polling it. A second Ctrl+C will not help —
`shutdown(wait=True)` is not interruptible. Diagnose with
`py-spy dump --pid <pid>` rather than guessing, then `kill -9` the PID.

Kill by PID, not `pkill -f 'main.py run ...'` — that pattern also matches the
shell running the command and will kill your own session.

## Architecture

Two independent implementations sharing no code. `main.py` is a Typer CLI that
lazily imports whichever one you select — the import is inside the command body
on purpose, since each module reconfigures global logging at import time.

**`threads.py`** — pull model. `main()` pre-populates a queue with 50 tasks,
starts N workers in a `ThreadPoolExecutor`, and each worker loops
`queue.get(timeout=0.1)` until the queue is empty, then breaks and returns its
completed count. Finite and self-terminating.

**`producer_consumer.py`** — push model, three levels deep:

```
main()
├── producer()   → N × producer_worker()   generate tasks → queue
└── consumer()   → M × consumer_worker()   queue → simulated work
```

`producer()` and `consumer()` are *coordinators*: each runs on the top-level
2-slot executor, owns a nested `ThreadPoolExecutor` of its own workers, parks
until told to stop, then sets its private stop event and aggregates worker
return values.

Three separate `threading.Event`s control shutdown, and the distinction matters:

| Event | Set by | Stops |
|---|---|---|
| `shutdown_event` (module-global) | SIGINT handler | everything |
| `producer_stop_event` | `main()` | the producer coordinator |
| `producer_worker_stop_event` / `worker_stop_event` | each coordinator | that coordinator's own workers |

Note that `num_workers == 1` takes a **different code path** in both
coordinators — it calls the worker function inline instead of using an
executor. Any change to worker lifecycle must be applied to both branches.

## Logging

`loguru`, configured at **module import time**, with routing by bound context
rather than by logger instance:

- `logger.bind(component="producer"|"consumer"|"worker")` → routes to `producer.log` / `consumer.log` / `worker.log`
- `logger.bind(worker_id=N)` / `logger.bind(producer_worker_id=N)` → routes to that worker's own file
- Everything at DEBUG and above also goes to `app.log`
- The console sink is added in `main()` and filters *out* anything carrying worker or component context, so only main-thread messages reach stderr

**Use the bound logger inside workers**, not the module-level `logger`. Calling
bare `logger.debug(...)` in a worker silently drops the record from its
component and per-worker files — an existing bug, see `AUDIT.md` finding #11.

Log sinks are added and removed *per worker at runtime*. Every `logger.add()`
must have a matching `logger.remove()`, or the handler and its file descriptor
leak.

`logs/` is gitignored and safe to delete between runs.

## Before changing concurrency code

`AUDIT.md` catalogues 19 known defects with reproductions. Read it first — an
odd-looking construct here is more likely an already-documented bug than
something to preserve. Notably: the queue is unbounded and grows ~7× faster
than consumers drain it, worker-thread exceptions are swallowed and leave
`main()` spinning, and the signal handler can strand the process on Ctrl+C.

If you fix something listed there, update its entry rather than leaving the
audit stale.

## Conventions

- Loguru brace-style lazy formatting — `logger.info("Worker {} done", n)`, never f-strings in log calls
- Type hints on function signatures
- All progress reporting goes through the single shared `rich` `Progress`
  instance created in `main()`; workers receive a `TaskID` and only ever call
  `progress.update(task_id, advance=1)`
- Prefer the standard library — the dependency list is deliberately three
  entries long, and `main.py` imports `Annotated` from `typing` (not
  `typing_extensions`) to keep it that way
