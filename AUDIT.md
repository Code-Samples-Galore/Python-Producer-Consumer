# 🔍 Code Audit

Audit of the threading examples in this repository. Every finding below was
reproduced against the code at `7b98264` on Python 3.11.15 with
`typer==0.27.0`, `rich`, and `loguru`.

Severity reflects impact on someone running or reading this project as a
concurrency example — a wrong pattern that a reader might copy is treated as
serious, not cosmetic.

> **18 of 19 findings are now fixed**; #17 is accepted with a rationale. Each
> entry keeps its original description — what was wrong and why — followed by
> **What was done** recording the change and the check that confirmed it. See
> [Verification](#-verification) for the numbers.

| # | Severity | Area | Finding | Status |
|---|----------|------|---------|--------|
| [1](#1-install-is-broken-requirementstxt-is-missing-typing_extensions) | 🔴 Critical | Packaging | Documented install produces `ModuleNotFoundError` | ✅ Fixed |
| [2](#2-producerconsumer-thread-crashes-are-swallowed-and-the-app-hangs-forever) | 🟠 High | Concurrency | Thread crashes swallowed, app hangs forever | ✅ Fixed |
| [3](#3-worker-counts-are-not-validated) | 🟠 High | CLI | `--producer-workers 0` hangs the app | ✅ Fixed |
| [4](#4-unbounded-queue-growth-no-backpressure) | 🟠 High | Performance | Queue grows without bound (~7× produce:consume) | ✅ Fixed |
| [5](#5-loguru-sink-and-file-descriptor-leak-on-worker-exception) | 🟠 High | Resources | Sink + fd leak when a worker raises | ✅ Fixed |
| [9](#9-signal-handler-does-real-work-before-setting-the-flag--ctrlc-can-hang-the-process-forever) | 🟠 High | Concurrency | **Ctrl+C can hang the process forever** (reproduced) | ✅ Fixed |
| [6](#6-all-tasks-completed-is-reported-when-most-tasks-were-abandoned) | 🟡 Medium | Correctness | "All tasks completed!" printed after dropping ~85% of tasks | ✅ Fixed |
| [7](#7-consumers-never-drain-the-queue-after-the-producer-stops) | 🟡 Medium | Correctness | Consumers stop instead of draining the backlog | ✅ Fixed |
| [8](#8-one-second-sleep-on-an-empty-queue-adds-pure-latency) | 🟡 Medium | Performance | Redundant `sleep(1)` on empty queue | ✅ Fixed |
| [10](#10-partially-processed-tasks-are-counted-as-completed) | 🟡 Medium | Correctness | Interrupted tasks inflate the completed count | ✅ Fixed |
| [11](#11-log-records-are-routed-to-the-wrong-file) | 🟡 Medium | Logging | "found no tasks" never reaches `worker.log` | ✅ Fixed |
| [12](#12-dead-branches-in-consumer) | 🟢 Low | Clarity | Unreachable `elif` / `else` branches | ✅ Fixed |
| [13](#13-single-worker-paths-pass-a-stop-event-nothing-ever-sets) | 🟢 Low | Concurrency | Caller's stop event ignored in single-worker mode | ✅ Fixed |
| [14](#14-timeouterror-shadows-the-builtin) | 🟢 Low | Style | `TimeoutError` import shadows builtin | ✅ Fixed |
| [15](#15-bare-except-and-a-misleading-loop-variable) | 🟢 Low | Style | Bare `except:` swallows `KeyboardInterrupt` | ✅ Fixed |
| [16](#16-mixed-result-types) | 🟢 Low | Style | `results` holds both `int` and `str` | ✅ Fixed |
| [17](#17-per-worker-sinks-are-global-and-fan-out) | 🟢 Low | Performance | O(workers) filter calls per log record | ⚪ Accepted |
| [18](#18-redundant-osmakedirs) | 🟢 Low | Clarity | `makedirs` runs after loguru already created the dir | ✅ Fixed |
| [19](#19-importing-either-module-wipes-global-loguru-handlers) | 🟢 Low | Design | Import-time `logger.remove()` side effect | ✅ Fixed |

---

## 🔴 Critical

### 1. Install is broken: `requirements.txt` is missing `typing_extensions`

**Status: ✅ Fixed**

**Files:** `requirements.txt`, `main.py:2`

`main.py` imports `from typing_extensions import Annotated`, but
`typing_extensions` is not in `requirements.txt`. Modern Typer (0.13+) no longer
declares it as a hard dependency, so the exact install flow documented in the
README fails on a clean environment:

```console
$ pip install -r requirements.txt
$ python main.py run threads
Traceback (most recent call last):
  File "main.py", line 2, in <module>
    from typing_extensions import Annotated
ModuleNotFoundError: No module named 'typing_extensions'
```

**Reproduced:** clean install of `typer rich loguru` → crash on every command.

**Fix:** `Annotated` has been in the standard library since Python 3.9, and this
project already requires 3.11+. Import it from `typing` and drop the dependency
question entirely:

```python
from typing import Annotated
```

**What was done:** `main.py` now imports `Annotated` from `typing`. Verified by uninstalling
`typing_extensions` entirely and running every documented command.

---

## 🟠 High

### 2. Producer/consumer thread crashes are swallowed, and the app hangs forever

**Status: ✅ Fixed**

**File:** `producer_consumer.py:240-257`

`main()` submits `producer` and `consumer` to a pool and then parks:

```python
producer_future = main_executor.submit(producer, ...)
consumer_future = main_executor.submit(consumer, ...)

while not shutdown_event.is_set():   # never inspects the futures
    time.sleep(0.1)
```

An exception in either thread is captured inside its `Future` and never
surfaces. `shutdown_event` is only set by SIGINT, so the app spins at 10 Hz
forever, showing an idle progress bar and no error.

**Reproduced:** running with `--producer-workers 0` raises
`ValueError: max_workers must be greater than 0` inside `producer()`; the
process printed nothing and had to be killed.

**Fix:** poll the futures in the wait loop and bail out if either finished
early:

```python
while not shutdown_event.is_set():
    for fut in (producer_future, consumer_future):
        if fut.done() and fut.exception() is not None:
            logger.error("Worker thread failed: {}", fut.exception())
            shutdown_event.set()
    time.sleep(0.1)
```

**What was done:** The wait loop in `main()` now checks `future.done() and future.exception()`
on both coordinators each tick, logs the failure, and sets `shutdown_event`.
Verified by monkeypatching `producer` to raise: the app logs
`producer thread failed: simulated producer crash` and exits in ~3 s instead of
hanging (it previously had to be killed).

### 3. Worker counts are not validated

**Status: ✅ Fixed**

**File:** `main.py:16-18`

`--producer-workers`, `--consumer-workers`, and `--thread-workers` accept `0`
and negative values. Zero falls through to
`ThreadPoolExecutor(max_workers=0)`, which raises deep inside a worker thread
and then hangs per finding #2.

**Fix:** constrain them at the CLI boundary, where the error is actionable:

```python
producer_workers: Annotated[int, typer.Option("--producer-workers", min=1, help=...)] = 1
```

**What was done:** All three options carry `min=1`, and `main()` in both modules raises
`ValueError` if called with a smaller count. `--producer-workers 0` now fails
immediately with `Invalid value for '--producer-workers': 0 is not in the range
x>=1` and exit code 2.

### 4. Unbounded queue growth (no backpressure)

**Status: ✅ Fixed**

**File:** `producer_consumer.py:202`

`task_queue = queue.Queue()` is created with no `maxsize`, and producers are far
faster than consumers by construction:

- **Producer:** ~0.125 s per cycle, 80% hit rate, 2–5 tasks per batch → **~22 tasks/s per worker**
- **Consumer:** 5–15 steps × 0.01–0.05 s sleep → ~0.3 s per task → **~3.3 tasks/s per worker**

**Reproduced** (2 producers, 2 consumers, ~20 s run, counted from the per-worker logs):

| Metric | Count |
|---|---|
| Tasks added | **922** |
| Tasks completed | **132** |
| Net queue growth | **+790** (~40 tasks/s) |

The queue grows without bound; a long run is an unbounded memory leak. This is
the single biggest performance problem in the repository, and it is also the
one a reader is most likely to copy — a producer-consumer example that omits
backpressure teaches the wrong lesson.

**Fix:** give the queue a bound so `put()` blocks and the producer self-throttles:

```python
task_queue = queue.Queue(maxsize=1000)
```

and have producers use a blocking `put` with a timeout so they stay responsive
to `stop_event`.

**What was done:** `QUEUE_MAXSIZE = 100` bounds the queue, and producers use
`task_queue.put(task, timeout=0.5)` with a `queue.Full` backoff, so a full queue
throttles production instead of growing the backlog. A bounded queue is also
what makes the drain in #7 finish in seconds rather than minutes.

Verified over a 10 s run at 2 producers / 4 consumers: **206 produced, 226
consumed** (206 + the 20 seeded tasks), queue fully drained, memory flat —
against 922 vs 132 and a 790-task backlog before.

### 5. loguru sink and file-descriptor leak on worker exception

**Status: ✅ Fixed**

**Files:** `producer_consumer.py:33-67` (consumer), `producer_consumer.py:74-100` (producer)

Each worker registers a personal sink and removes it on the way out:

```python
worker_log_id = logger.add(f"logs/consumer_worker_{worker_id}.log", ...)
...
logger.remove(worker_log_id)   # only reached on a clean loop exit
```

`logger.remove()` is not in a `finally`, so any exception raised in the body —
including from `progress.update()` — leaks the handler and its open file
descriptor for the life of the process.

**Reproduced:** injecting a failure into `progress.update()` left the loguru
handler count at 4 instead of 3 after the worker raised.

**Fix:** wrap the body in `try` / `finally`, or use loguru's context manager form.

**What was done:** Both worker bodies are wrapped in `try` / `finally` around
`logger.add(...)` / `logger.remove(...)`. Verified with the injected
`progress.update()` failure from the reproduction below: **0 handlers leaked**,
where the old code leaked 1 per failed worker.

### 9. Signal handler does real work before setting the flag — Ctrl+C can hang the process forever

**Status: ✅ Fixed**

> ⬆️ **Upgraded to High during testing.** This was written up as a theoretical
> hazard, then hit for real: a captured process sat wedged for **3 minutes**
> after Ctrl+C before being killed. It is rare — **1 hang in 33 SIGINT runs** at
> 2 producers / 4 consumers, with the other 32 exiting cleanly — but permanent
> when it lands, and it defeats the "graceful shutdown" feature the README
> advertises. The single capture below is the evidence; treat the frequency as
> a rough lower bound from one observation, not a measured rate.

**Files:** `producer_consumer.py:24-29`, `threads.py:22-27`

```python
def signal_handler(signum, frame):
    if progress_instance:
        progress_instance.console.print(...)   # I/O + rich's console lock
    logger.info("Shutdown signal received")    # loguru's sink locks
    shutdown_event.set()                       # ← the only line that matters
```

Python runs signal handlers on the main thread, between bytecodes. Two things
go wrong with doing work before `shutdown_event.set()`:

1. **Lock re-entry.** If SIGINT lands while the main thread is inside rich's
   console lock or a loguru sink lock, the handler tries to take a lock that
   same thread already holds.
2. **Escaping exceptions.** If either call raises, the exception propagates out
   of the handler into whatever the main thread was executing — and
   `shutdown_event.set()` never runs.

Case 2 is the one that was captured. The escaping exception unwinds the
`while not shutdown_event.is_set()` wait loop and exits the
`with ThreadPoolExecutor(...)` block, whose `__exit__` calls
`shutdown(wait=True)` — joining the producer and consumer threads. But those
threads are still spinning on `not shutdown_event.is_set()`, which is now
permanently false. Main waits for them; they wait for a flag nobody will ever
set.

**Captured state** (`py-spy dump` on the wedged process):

```
Thread (idle): "MainThread"
    _wait_for_tstate_lock (threading.py:1139)
    join (threading.py:1119)
    shutdown (concurrent/futures/thread.py:235)
    __exit__ (concurrent/futures/_base.py:647)
    main (producer_consumer.py:240)        ← joining, inside executor teardown

Thread (idle): "ThreadPoolExecutor-0_0"
    producer (producer_consumer.py:125)    ← still in `while not shutdown_event.is_set()`

Thread (idle): "ThreadPoolExecutor-0_1"
    consumer (producer_consumer.py:161)    ← still in `while not shutdown_event.is_set()`
```

Note what this proves: main reached executor teardown *while the producer and
consumer loops were still running*, which is unreachable via the normal exit
path — `main()` sets `producer_stop_event` and awaits both futures before
leaving the block. Only an exception escaping the wait loop gets you here, and
the signal handler is the only code that can raise there. A second Ctrl+C does
not help: `shutdown(wait=True)` is not interruptible.

**Fix:** a signal handler should only flip the flag — nothing that allocates,
locks, or does I/O:

```python
def signal_handler(signum, frame):
    shutdown_event.set()
```

Move the message to the main loop, which can observe `shutdown_event` and
report safely. As defence in depth, set the event in a `finally` around the
wait loop so no escaping exception can strand the worker threads.

**What was done:** The handler is now three lines that only flip flags — no printing, logging or
locking — so nothing there can block or raise. First Ctrl+C requests a drain,
second forces a stop. As defence in depth, `main()` and both coordinators set
their stop flags in a `finally`, so even an exception escaping a wait loop
cannot strand the worker threads.

Verified with **40 consecutive SIGINT runs** at 2 producers / 4 consumers, all
exiting cleanly, every drain completing in under 20 s (the pre-fix code wedged
once in 33 and had to be killed). Second Ctrl+C aborts in ~1 s.

---

## 🟡 Medium

### 6. "All tasks completed!" is reported when most tasks were abandoned

**Status: ✅ Fixed**

**File:** `producer_consumer.py:265`

**Reproduced:** a run producing 353 tasks and consuming 50 still logged
`All tasks completed!`, leaving ~300 tasks unprocessed in the queue.

**Fix:** report the actual outcome, including the queue remainder:

```python
logger.info("Shutdown complete - {} produced, {} consumed, {} left in queue",
            producer_result, consumer_result, task_queue.qsize())
```

**What was done:** `main()` now reports produced, consumed and `task_queue.qsize()` separately,
and logs a WARNING rather than a success when tasks are left over. A full drain
reports `Shutdown complete - queue fully drained`; an aborted run reports e.g.
`Shutdown complete - 87 tasks left unprocessed in the queue`.

### 7. Consumers never drain the queue after the producer stops

**Status: ✅ Fixed**

**File:** `producer_consumer.py:160-173`

When `producer_stop_event` fires, `consumer()` immediately sets
`worker_stop_event`, so consumers abandon the backlog rather than finishing it.
There is no drain phase — which is exactly the phase a producer-consumer example
exists to demonstrate. This is the root cause of finding #6.

Worth noting alongside this: `producer_stop_event` is only ever set *after*
`shutdown_event` (`producer_consumer.py:252`), so the intended
"producer finishes → consumers drain → clean exit" lifecycle never runs at all.
The application can only ever end via Ctrl+C.

**Fix:** after the producer stops, loop until `task_queue.join()` (or until the
queue reports empty) before signalling consumers to stop.

**What was done:** The consumer coordinator sets a `drain_event` once producers stop. Consumer
workers then keep pulling until the queue is empty and exit on their own, so the
backlog is finished rather than abandoned. A second Ctrl+C sets
`force_shutdown_event` and abandons it deliberately.

Verified: after Ctrl+C the queue drained completely in ~9 s at 2 producers /
4 consumers with exact accounting (20 seeded + 206 produced = 226 consumed).

### 8. One-second sleep on an empty queue adds pure latency

**Status: ✅ Fixed**

**File:** `producer_consumer.py:45-49`

```python
try:
    task = task_queue.get(timeout=0.1)
except queue.Empty:
    logger.debug(...)
    time.sleep(1)      # ← redundant
    continue
```

`get(timeout=0.1)` already blocks and wakes the instant a task arrives. The
extra `sleep(1)` means a consumer can sit idle for up to a second while work is
waiting, and it adds up to a second to shutdown, since `stop_event` is only
re-checked at the top of the loop.

**Fix:** delete the `time.sleep(1)` and let the blocking `get` do the waiting.

**What was done:** The `time.sleep(1)` is gone; the loop `continue`s straight back to the
blocking `get(timeout=0.1)`, which already paces it.

### 10. Partially-processed tasks are counted as completed

**Status: ✅ Fixed**

**File:** `producer_consumer.py:54-61`

When shutdown interrupts the inner work loop, control still falls through to
the accounting:

```python
for _ in range(work_steps):
    if stop_event.is_set() or shutdown_event.is_set():
        break                     # abandons the task mid-work
progress.update(rich_task_id, advance=1)   # ...but counts it anyway
completed_tasks += 1
task_queue.task_done()
```

An interrupted task inflates both the progress bar and the returned count.

**Fix:** `continue` out of the outer loop on interruption instead of falling
through, so only genuinely finished tasks are counted.

**What was done:** Both workers track an `interrupted` flag and `continue` without touching the
progress bar or the counter when work is cut short. `task_done()` moved into a
`finally` so the queue accounting stays correct either way. Visible in the
aborted-run numbers: 134 produced + 20 seeded = 154, against 65 consumed + 87
queued + 2 abandoned mid-work — the 2 are correctly excluded from the completed
count.

### 11. Log records are routed to the wrong file

**Status: ✅ Fixed**

**Files:** `producer_consumer.py:47`, `threads.py:40`

Both call the raw module-level `logger` rather than the bound
`worker_logger` / `producer_worker_logger`, so the record carries none of the
`component` / `worker_id` context that the sink filters key on.

**Reproduced:** after a `threads` run, `"found no tasks"` appears **0 times** in
`logs/worker.log` and **3 times** in `logs/app.log` — the per-component routing
the README describes silently does not apply to these lines.

**Fix:** use the bound logger:

```python
worker_logger.debug("Worker {} found no tasks in queue, waiting...", worker_id)
```

**What was done:** Both call sites now use the bound logger. Verified after a `threads` run:
`found no tasks` appears **4 times in `worker.log`** (previously 0) as well as in
`app.log`.

---

## 🟢 Low

### 12. Dead branches in `consumer()`

**Status: ✅ Fixed**

**File:** `producer_consumer.py:167-170`

The wait loop exits only when `producer_stop_event` or `shutdown_event` is set,
and both are tested first — so the `elif task_queue.empty()` and trailing
`else` branches are unreachable.

**What was done:** Gone — the consumer coordinator's wait loop now has a single exit path
followed by the drain phase from #7.

### 13. Single-worker paths pass a stop event nothing ever sets

**Status: ✅ Fixed**

**File:** `producer_consumer.py:112-114`, `producer_consumer.py:148-150`

The `num_workers == 1` branches hand the worker a freshly created
`producer_worker_stop_event` / `worker_stop_event` that is never set on that
path, and the caller's own `stop_event` is dropped on the floor. The worker can
only ever be stopped by the global `shutdown_event`. It happens to work today
purely because `shutdown_event` always fires first.

Related: both branches log `"using single-threaded mode"` at **WARNING** level,
even though one producer and one consumer is the documented default — a warning
on the default configuration trains readers to ignore warnings.

**What was done:** The `num_workers == 1` special case is removed from both coordinators; they
always use a `ThreadPoolExecutor`, so there is one lifecycle path to reason
about. Worker stop events are set in a `finally`, so the caller's `stop_event` is
honoured. The spurious WARNING on the default configuration is gone too.

### 14. `TimeoutError` shadows the builtin

**Status: ✅ Fixed**

**File:** `threads.py:1`

`from concurrent.futures import ThreadPoolExecutor, TimeoutError` shadows the
builtin. Harmless on Python 3.11+, where the two are the same object, but it
misleads anyone reading the `except TimeoutError` clause.

**What was done:** `TimeoutError` is no longer imported; `threads.py` collects results with
`as_completed` and needs no timeout juggling.

### 15. Bare `except:` and a misleading loop variable

**Status: ✅ Fixed**

**File:** `threads.py:143-149`

```python
for future in worker_futures:            # iterates keys → these are worker IDs
    try:
        result = worker_futures[future].result(timeout=0.1)
    except:                              # also swallows KeyboardInterrupt
        pass
```

The loop variable named `future` is actually a worker ID, and the bare `except`
catches `KeyboardInterrupt` and `SystemExit` — inside the handler for a
*second* Ctrl+C, which is precisely when the user wants out.

**Fix:** `for worker_id, future in worker_futures.items():` and catch
`Exception`.

**What was done:** Replaced with `for future in as_completed(worker_futures)` over a
`{future: worker_id}` map and a targeted `except Exception`, so the loop
variable means what it says and `KeyboardInterrupt` is no longer swallowed.

### 16. Mixed result types

**Status: ✅ Fixed**

**File:** `threads.py:125`

`results[worker_id] = "Worker timed out during shutdown"` puts a `str` into a
dict that otherwise holds `int` counts, so the summary line can print either a
number or a sentence.

**What was done:** `results` now holds only `int`; a failed worker is logged and recorded as `0`.

### 17. Per-worker sinks are global and fan out

**Status: ⚪ Accepted**

**Files:** `producer_consumer.py:33`, `producer_consumer.py:74`

`logger.add()` installs a **process-global** sink, so every record emitted by
any thread is evaluated against every worker's filter — O(workers) filter calls
per log line, all serialised behind loguru's lock. With DEBUG-level logging on
every task this is a measurable hot path at higher worker counts.

**Fix:** one sink with a `{extra[worker_id]}` component in the filename, or
filter at a single sink instead of registering one per worker.

**What was done:** **Not fixed — accepted.** The fan-out is inherent to the per-worker log files
the README documents as a feature: loguru file sinks take a fixed path, so one
file per worker means one sink per worker. Removing it would mean either
dropping those files or hand-rolling a dispatching sink, which adds more
machinery than a teaching example warrants. The cost is a handful of cheap
equality checks per record at the worker counts this project is run at, and #5
now guarantees the sinks are released. Revisit only if worker counts grow by an
order of magnitude.

### 18. Redundant `os.makedirs`

**Status: ✅ Fixed**

**Files:** `producer_consumer.py:199`, `threads.py:73`

`os.makedirs("logs", exist_ok=True)` runs inside `main()`, long after the
module-level `logger.add("logs/app.log")` at line 14 already created the
directory — loguru creates parent directories for file sinks automatically. The
call is a no-op that implies an ordering requirement that does not exist.

**What was done:** `os.makedirs("logs", exist_ok=True)` moved into `setup_logging()`, where it
runs before the first `logger.add()` and the ordering is real rather than
implied.

### 19. Importing either module wipes global loguru handlers

**Status: ✅ Fixed**

**Files:** `producer_consumer.py:13`, `threads.py:13`

`logger.remove()` at module scope deletes **all** loguru handlers process-wide
as an import side effect. Fine for a script, surprising for anything that
imports these modules — including `main.py`, where importing one architecture
silently reconfigures logging for the whole process.

**Fix:** move sink configuration into a `setup_logging()` function called from
`main()`.

**What was done:** Sink configuration moved into `setup_logging()`, called from `main()`.
Importing either module no longer touches global logging state — which also
means `main.py`'s lazy import no longer reconfigures logging as a side effect.

---

## 📚 Documentation accuracy

Checked `README.md` against observed behaviour. Every documented command was
executed. The "Original" column records what the audit found; the "Now" column
records the state after the fixes and the README rewrite.

| Claim | Original | Now |
|---|---|---|
| `pip install -r requirements.txt` then run | ❌ Broken — finding #1 | ✅ Works |
| `python main.py run threads [--thread-workers N]` | ✅ Verified | ✅ Verified |
| `python main.py run producer-consumer [...]` | ✅ Verified | ✅ Verified |
| `python main.py list-variants` | ✅ Verified | ✅ Verified |
| `python threads.py` / `python producer_consumer.py` | ✅ Verified | ✅ Verified |
| Log files listed under `logs/` | ⚠️ Routing buggy — finding #11 | ✅ Routed correctly |
| "Python 3.12 or higher" | ⚠️ Overstated — `StrEnum` needs 3.11 | ✅ Says 3.11+ |
| "Use multiple thread workers for CPU-intensive tasks" | ❌ Wrong — the GIL prevents it | ✅ Says I/O-bound, explains why |
| "Graceful Shutdown: Ctrl+C handling for clean termination" | ❌ Not always — finding #9 | ✅ True, and the drain is described |
| Producer-consumer runs until Ctrl+C | ❌ Not documented | ✅ Documented |

---

## 🧭 Scope

**18 of 19 findings are fixed.** #17 is accepted with a rationale recorded in
its entry — the sink fan-out is inherent to the per-worker log files the README
documents as a feature, and removing it would cost more clarity than it buys at
these worker counts.

The fixes change shutdown semantics deliberately, and that is the one thing to
review with care:

- **Ctrl+C now drains rather than abandoning.** The first Ctrl+C stops the
  producers and lets consumers finish the queued backlog; a second Ctrl+C
  abandons it. Previously the first Ctrl+C dropped everything still queued.
- **Drain time scales with the backlog.** With `QUEUE_MAXSIZE = 100` and one
  consumer, a full queue takes ~30 s to drain; with four consumers, ~9 s. The
  progress bars keep moving throughout, and the second Ctrl+C is the escape
  hatch. Lower `QUEUE_MAXSIZE` if a shorter worst case matters more than
  throughput.
- **A failed coordinator now exits non-zero** with the real traceback, instead
  of hanging silently.

No behaviour was changed in `threads.py` beyond honest reporting and not
counting interrupted tasks — it still drains its pre-populated queue and exits.

---

## ✅ Verification

Everything below was run against the fixed code on Python 3.11.15.

| Check | Result |
|---|---|
| `threads` end to end | 50/50 tasks completed, exits on its own |
| Producer/consumer accounting, full drain | 20 seeded + 206 produced = **226 consumed**, queue empty |
| Producer/consumer accounting, forced abort | 134 + 20 = 154 vs 65 consumed + 87 queued + 2 abandoned mid-work |
| Backpressure | 206 produced in 10 s (was 922 in 20 s unbounded); queue never exceeds 100 |
| SIGINT shutdown | **40/40 consecutive runs exited cleanly** (2 producers / 4 consumers) |
| Second SIGINT | Aborts in ~1 s |
| Coordinator crash | Logged and exits in ~3 s (previously hung indefinitely) |
| Sink leak on worker exception | **0 handlers leaked** (was 1 per failure) |
| Log routing | `found no tasks` → 4 hits in `worker.log` (was 0) |
| `--producer-workers 0` / `-2` | Rejected at the CLI, exit code 2 |
| Every README command | Executed, all succeed |

## 🔬 Reproduction (against the original code)

These commands reproduce the findings on `7b98264`, before the fixes.

```bash
pip install -r requirements.txt

```bash
pip install -r requirements.txt

# #1  — check out 7b98264 in a clean env, install, and run any command
# #3  — hangs instead of reporting a usable error
python main.py run producer-consumer --producer-workers 0

# #4  — run ~20s, Ctrl+C, then compare the tallies
python main.py run producer-consumer --producer-workers 2 --consumer-workers 2
grep -ch 'Added task'     logs/producer_worker_*.log | paste -sd+ | bc
grep -ch 'Completed task' logs/consumer_worker_*.log | paste -sd+ | bc

# #5  — leaks a loguru handler when a worker raises
python - <<'EOF'
import queue, threading, producer_consumer as pc
from loguru import logger
class Boom:
    def update(self, *a, **k): raise RuntimeError("boom")
q = queue.Queue(); q.put("t1")
before = len(logger._core.handlers)
try: pc.consumer_worker(1, q, Boom(), 0, threading.Event())
except RuntimeError: pass
print("leaked handlers:", len(logger._core.handlers) - before)   # -> 1
EOF

# #9  — rare; loop until it wedges, then inspect. 1 hit in 33 runs here.
pip install py-spy
for i in $(seq 1 40); do
  timeout -s INT --kill-after=15 5 python main.py run producer-consumer \
      --producer-workers 2 --consumer-workers 4 >/dev/null 2>&1 || echo "run $i: signalled"
done
# while one is wedged, in another shell:
py-spy dump --pid "$(pgrep -f 'main.py run producer-consumer' | head -1)"
# MainThread in ThreadPoolExecutor.__exit__/join while producer+consumer
# are still looping on shutdown_event == unset

# #11 — routing check: 0 hits in worker.log, non-zero in app.log
python main.py run threads --thread-workers 3
grep -c 'found no tasks' logs/worker.log logs/app.log
```
