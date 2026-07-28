from concurrent.futures import ThreadPoolExecutor, as_completed
from rich.progress import Progress, BarColumn, TextColumn, TimeElapsedColumn, TaskID
import time
import random
import queue
import threading
import signal
import sys
from loguru import logger
import os

# Global event for graceful shutdown
shutdown_event = threading.Event()


def setup_logging():
    """Configure loguru sinks. Called from main() so that importing this
    module does not reconfigure logging for the whole process."""
    os.makedirs("logs", exist_ok=True)
    logger.remove()  # Remove default handler
    logger.add("logs/app.log", rotation="10 MB", retention="7 days", level="DEBUG")
    logger.add("logs/worker.log", filter=lambda record: record["extra"].get("component") == "worker", level="DEBUG")

def signal_handler(signum, frame):
    """Handle Ctrl+C. Signal handlers run on the main thread between
    bytecodes, so this only flips the flag - no logging, printing or locking.
    Anything that can block or raise here would strand the worker threads."""
    shutdown_event.set()

def worker(worker_id: int, task_queue: queue.Queue, progress: Progress, worker_task_id: TaskID):
    """Worker thread that processes tasks from the queue"""
    worker_logger = logger.bind(component="worker")
    worker_logger.info("Worker {} started", worker_id)

    completed_tasks = 0

    while not shutdown_event.is_set():
        try:
            task = task_queue.get(timeout=0.1)
        except queue.Empty:
            # The queue is populated up front, so an empty queue means the
            # work is done.
            worker_logger.debug("Worker {} found no tasks in queue...", worker_id)
            break

        try:
            worker_logger.debug("Worker {} processing task {}", worker_id, task)
            # Simulate work for this task
            interrupted = False
            work_steps = random.randint(5, 15)
            for _ in range(work_steps):
                if shutdown_event.is_set():
                    interrupted = True
                    break
                time.sleep(random.uniform(0.01, 0.05))

            if interrupted:
                # Abandoned part-way through - do not count it as done.
                worker_logger.debug("Worker {} abandoned task {} during shutdown", worker_id, task)
                continue

            progress.update(worker_task_id, advance=1)
            completed_tasks += 1
            worker_logger.debug("Worker {} completed task {}", worker_id, task)
        finally:
            task_queue.task_done()

    worker_logger.info("Worker {} stopping after completing {} tasks", worker_id, completed_tasks)
    return completed_tasks

def main(num_workers: int = 4):
    if num_workers < 1:
        raise ValueError("Worker count must be at least 1")

    setup_logging()

    # Add console handler for main function only
    main_logger_id = logger.add(sys.stderr, level="INFO",
                                format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>main</cyan> | {message}",
                                filter=lambda record: record["extra"].get("component") is None)

    logger.info("Application starting")

    # Set up signal handler for graceful shutdown
    signal.signal(signal.SIGINT, signal_handler)

    # Create task queue and populate with all tasks upfront
    task_queue = queue.Queue()
    total_tasks = 50  # Create 50 tasks to process
    for i in range(total_tasks):
        task_queue.put(f"task-{i+1}")
    logger.info("Created queue with {} tasks", total_tasks)

    results = {}

    try:
        logger.info("Starting {} worker threads", num_workers)

        # Create a single shared Progress instance
        with Progress(
            TextColumn("[bold]{task.description}", justify="right"),
            BarColumn(),
            TextColumn("{task.completed} tasks"),
            TimeElapsedColumn(),
        ) as progress:
            # Create progress tasks for each worker
            worker_task_ids = []
            for i in range(num_workers):
                worker_task_id = progress.add_task(
                    description=f"[cyan]Worker {i+1}",
                    total=None
                )
                worker_task_ids.append(worker_task_id)

            # Start worker threads using ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=num_workers) as executor:
                # Start all worker threads
                worker_futures = {}
                for i in range(num_workers):
                    future = executor.submit(worker, i+1, task_queue, progress, worker_task_ids[i])
                    worker_futures[future] = i + 1

                # Workers stop on their own once the queue is empty or a
                # shutdown is signalled, so simply collect their counts.
                for future in as_completed(worker_futures):
                    worker_id = worker_futures[future]
                    try:
                        results[worker_id] = future.result()
                    except Exception as exc:
                        logger.error("Worker {} failed: {}", worker_id, exc)
                        results[worker_id] = 0

        # Log results after Progress context exits to avoid interference
        for worker_id in sorted(results):
            logger.info("Worker {} result: {} tasks", worker_id, results[worker_id])

        remaining = task_queue.qsize()
        if remaining:
            logger.warning("Stopped early - {} of {} tasks left unprocessed", remaining, total_tasks)
        else:
            logger.info("All tasks completed!")

    except KeyboardInterrupt:
        logger.warning("Forced shutdown...")
        shutdown_event.set()
    finally:
        logger.info("Application shutdown complete")
        logger.remove(main_logger_id)


if __name__ == "__main__":
    main()
