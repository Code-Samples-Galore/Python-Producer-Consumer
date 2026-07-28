# 🧵 Python Producer-Consumer Example

## 📝 Overview
This project demonstrates different approaches to multithreading in Python, focusing on producer-consumer patterns and worker threads. It includes two main architectures: a thread-based worker system and a producer-consumer system with configurable workers.

## 📁 Project Structure
- `main.py`: Entry point for running the project with CLI interface.
- `threads.py`: Thread-based worker architecture that processes tasks from a pre-populated queue.
- `producer_consumer.py`: Producer-consumer architecture with configurable producer and consumer workers.
- `logs/`: Contains log files for each worker and process (created at runtime, not tracked by git).
- `requirements.txt`: Python dependencies.
- `AUDIT.md`: Code audit — known bugs and performance issues.
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

> ⚠️ Worker counts must be **1 or greater**. The CLI does not currently reject
> `0`, and passing it hangs the application. See `AUDIT.md`.

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
- **Graceful Shutdown**: Ctrl+C handling for clean termination ⚠️ *see below*
- **Configurable Workers**: Adjust the number of workers for different architectures
- **Comprehensive Logging**: Separate log files for different components and workers
- **Signal Handling**: Proper cleanup on shutdown signals ⚠️ *see below*

> ⚠️ **Ctrl+C occasionally hangs the producer-consumer run.** The signal handler
> prints and logs before setting the shutdown flag; if that work raises, the
> flag is never set and the process waits forever on threads that will never
> stop. Rare — seen once in about 30 runs with 2 producers / 4 consumers — but
> a second Ctrl+C will not help; kill the process with `SIGKILL`. Details and
> fix in `AUDIT.md`.

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

> 📌 Producers currently outpace consumers by roughly 7×, and the task queue is
> unbounded — so the backlog grows for as long as the run continues. See
> `AUDIT.md`.

## 🔍 Known Issues
This repository is a teaching example, and its concurrency code has known
defects — including unbounded queue growth, swallowed worker exceptions, and a
signal handler that can leave the process hung after Ctrl+C. `AUDIT.md`
documents 19 of them, each with a reproduction and a suggested fix. Read it
before treating any pattern here as a reference implementation.

## 📄 License

MIT License
