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
timeout, or it will hang the session:

```bash
timeout -s INT --kill-after=60 10 python main.py run producer-consumer --producer-workers 2 --consumer-workers 4
```

Budget generously for the timeout: SIGINT starts a **drain**, which takes as
long as the backlog needs — about 9 s with four consumers, 30 s with one. That
is working as designed, not a hang. Send a second SIGINT to abandon the queue
and exit in about a second.

When killing stray runs, kill by PID. `pkill -f 'main.py run ...'` also matches
the shell running the command and will kill your own session.

## Architecture

Two independent implementations sharing no code. `main.py` is a Typer CLI that
lazily imports whichever one you select.

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
until told to stop, then releases its workers and aggregates their return
values. There is no separate single-worker code path — one worker uses the same
executor as many, so there is one lifecycle to reason about.

### Shutdown

Four `threading.Event`s, and the distinction between them is the heart of this
module:

| Event | Set by | Meaning |
|---|---|---|
| `shutdown_event` (module-global) | first SIGINT | stop producing, drain the backlog |
| `force_shutdown_event` (module-global) | second SIGINT | abandon queued work, stop now |
| `producer_stop_event` | `main()` | release the producer coordinator |
| `drain_event` | `consumer()` | consumers exit once the queue runs dry |

Consumer workers loop until `force_shutdown_event`, and additionally break when
`drain_event` is set *and* the queue is empty — that second condition is what
makes the backlog finish instead of being dropped.

Three invariants hold this together. Breaking any of them reintroduces a bug
that took real effort to diagnose:

1. **`signal_handler` only flips flags.** No logging, printing, or locking. It
   runs on the main thread between bytecodes; anything that can block or raise
   there will strand every worker thread. This previously hung the process
   permanently after Ctrl+C.
2. **Stop flags are set in `finally`.** `main()` and both coordinators release
   their workers on the way out no matter how they leave their wait loop, so an
   escaping exception can never leave `ThreadPoolExecutor.__exit__` joining
   threads that are waiting for a flag nobody set.
3. **`main()`'s wait loop polls both futures.** An exception in a coordinator is
   captured in its `Future` and is otherwise invisible; without the poll the
   app spins forever with no error.

If a run ever does wedge, `py-spy dump --pid <pid>` tells you which invariant
broke — far faster than reasoning about it.

### Backpressure

`QUEUE_MAXSIZE = 100` bounds the queue, and producers use
`put(task, timeout=0.5)` with a `queue.Full` backoff. Producers outrun consumers
by roughly 7× by construction, so without the bound the backlog grows without
limit. Keep the queue bounded — it is also what makes the drain finish in
seconds instead of minutes.

## Logging

`loguru`, configured in `setup_logging()` and called from `main()` — importing
either module must not touch global logging state. Routing is by bound context
rather than by logger instance:

- `logger.bind(component="producer"|"consumer"|"worker")` → routes to `producer.log` / `consumer.log` / `worker.log`
- `logger.bind(worker_id=N)` / `logger.bind(producer_worker_id=N)` → routes to that worker's own file
- Everything at DEBUG and above also goes to `app.log`
- The console sink is added in `main()` and filters *out* anything carrying worker or component context, so only main-thread messages reach stderr

**Use the bound logger inside workers**, not the module-level `logger`. A bare
`logger.debug(...)` in a worker carries no context and silently misses its
component and per-worker files.

Per-worker sinks are added and removed at runtime, inside `try` / `finally`.
Keep them that way — an unmatched `logger.add()` leaks the handler and its open
file descriptor for the life of the process.

`logs/` is gitignored and safe to delete between runs.

## Conventions

- Loguru brace-style lazy formatting — `logger.info("Worker {} done", n)`, never f-strings in log calls
- Type hints on function signatures
- All progress reporting goes through the single shared `rich` `Progress`
  instance created in `main()`; workers receive a `TaskID` and only ever call
  `progress.update(task_id, advance=1)`
- Count a task as completed only when it actually finished — work interrupted by
  shutdown is logged and skipped, never counted
- Prefer the standard library — the dependency list is deliberately three
  entries long, and `main.py` imports `Annotated` from `typing` (not
  `typing_extensions`) to keep it that way

## Before changing concurrency code

`AUDIT.md` records 19 findings against this codebase, 18 of them now fixed, each
with what was wrong and how it was addressed. Read the relevant entry before
touching shutdown, queueing, or logging — most of the non-obvious code here is
the fix for something specific, and the entry explains what.

If you change something covered there, update its entry rather than leaving the
audit stale.
