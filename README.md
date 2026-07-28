# 🧵 Python Producer-Consumer Example

## 📝 Overview
This project demonstrates different approaches to multithreading in Python, focusing on producer-consumer patterns and worker threads. It includes two main architectures: a thread-based worker system and a producer-consumer system with configurable workers.

## 📁 Project Structure
- `main.py`: Entry point for running the project with CLI interface.
- `threads.py`: Thread-based worker architecture that processes tasks from a pre-populated queue.
- `producer_consumer.py`: Producer-consumer architecture with configurable producer and consumer workers.
- `logs/`: Contains log files for each worker and process (created at runtime, not tracked by git).
- `requirements.txt`: Python dependencies.
- `AUDIT.md`: Code audit — 19 findings, what was wrong and how each was fixed.
- `CLAUDE.md`: Orientation notes for Claude Code.

## 🏗️ Architectures

### 🧶 Threads Architecture
- **Description**: Workers process tasks from a pre-populated queue
- **Use case**: When you have a known set of tasks to process
- **Configuration**: Number of thread workers (default: 4)
- **Termination**: Exits on its own once the 50 queued tasks are drained

### 🔄 Producer-Consumer Architecture  
- **Description**: Separate producer and consumer workers with dynamic task generation
- **Use case**: When tasks are generated continuously and need to be processed in real-time
- **Configuration**: 
  - Number of producer workers (default: 1)
  - Number of consumer workers (default: 1)
- **Termination**: Runs until you press **Ctrl+C** — producers generate tasks
  indefinitely, so there is no natural end point
- **Backpressure**: The queue is capped at 100 tasks; producers block when it is
  full rather than letting the backlog grow without limit

## ▶️ Usage

### 💻 Command Line Interface
1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Run with different architectures:
   ```bash
   # Threads architecture with default 4 workers
   python main.py run threads
   
   # Threads architecture with 8 workers
   python main.py run threads --thread-workers 8
   
   # Producer-consumer with default settings (1 producer, 1 consumer)
   # Runs until Ctrl+C
   python main.py run producer-consumer
   
   # Producer-consumer with multiple workers
   python main.py run producer-consumer --producer-workers 2 --consumer-workers 4
   ```

3. List available options:
   ```bash
   python main.py list-variants
   ```

### 🏃 Direct Script Execution
You can also run the scripts directly:
```bash
python threads.py
python producer_consumer.py
```

## 🪵 Logging
Each script writes comprehensive logs to the `logs/` directory:
- `app.log`: General application logs
- `worker.log`: Thread worker logs (threads architecture)
- `producer.log`: Producer logs (producer-consumer architecture)
- `consumer.log`: Consumer logs (producer-consumer architecture)
- `producer_worker_N.log`: Individual producer worker logs
- `consumer_worker_N.log`: Individual consumer worker logs

## ✨ Features
- **Rich Progress Bars**: Real-time progress tracking for all workers
- **Two-Stage Shutdown**: First Ctrl+C drains the queue, second abandons it
- **Backpressure**: A bounded queue keeps memory flat during long runs
- **Configurable Workers**: Adjust the number of workers for different architectures
- **Comprehensive Logging**: Separate log files for different components and workers
- **Signal Handling**: Proper cleanup on shutdown signals

### ⏹️ Stopping a producer-consumer run

| Action | Effect |
|---|---|
| First **Ctrl+C** | Producers stop; consumers finish the queued backlog, then exit |
| Second **Ctrl+C** | Abandon whatever is still queued and stop now |

The drain is real work, so it takes time proportional to the backlog — roughly
9 s with four consumers, or 30 s with one, for a full 100-task queue. The
progress bars keep moving while it runs; press Ctrl+C again if you would rather
not wait. The final log line always reports what actually happened:

```
Producer result: 206 tasks produced
Consumer result: 226 tasks consumed
Shutdown complete - queue fully drained
```

## 📦 Requirements
- Python 3.11 or higher (`enum.StrEnum` was added in 3.11)
- Dependencies listed in `requirements.txt`

## 💡 Examples

### ⚡ High Throughput Processing
```bash
# Use multiple thread workers for I/O-bound tasks
python main.py run threads --thread-workers 12
```

> 📌 Python threads share one interpreter lock, so extra workers only help when
> tasks spend their time **waiting** — on network, disk, or `sleep`, as the
> simulated work here does. CPU-bound work will not speed up; that needs
> `multiprocessing`.

### ⏱️ Real-time Task Processing
```bash
# Use producer-consumer for continuous task generation and processing
python main.py run producer-consumer --producer-workers 3 --consumer-workers 6
```

> 📌 Producers generate work far faster than consumers can process it, so the
> queue sits at its 100-task cap and producers block on `put()`. That is the
> backpressure doing its job — adding consumers, not producers, is what raises
> throughput here.

## 🔍 Audit
`AUDIT.md` records a full audit of this codebase: 19 findings, each with what
was wrong, why it mattered, and what was done about it. 18 are fixed; one is
accepted with a rationale. Worth reading alongside the code — several of the
findings (backpressure, drain-before-exit, keeping signal handlers trivial) are
the points these examples exist to make.

## 📄 License

MIT License
