from concurrent.futures import ThreadPoolExecutor, TimeoutError
from rich.progress import Progress, BarColumn, TextColumn, TimeElapsedColumn, TaskID
import time
import random
import queue
import threading
import signal
import sys
from loguru import logger
import os

# Configure loguru with filters
logger.remove()  # Remove default handler
logger.add("logs/app.log", rotation="10 MB", retention="7 days", level="DEBUG")
logger.add("logs/worker.log", filter=lambda record: record["extra"].get("component") == "worker", level="DEBUG")

# Global event for graceful shutdown
shutdown_event = threading.Event()
# Global progress instance for signal handler
progress_instance = None

def signal_handler(signum, frame):
    """Handle Ctrl+C signal for graceful shutdown"""
    if progress_instance:
        progress_instance.console.print("\n[yellow]Shutdown signal received. Gracefully shutting down...[/yellow]")
    logger.info("Shutdown signal received. Gracefully shutting down...")
    shutdown_event.set()

def worker(worker_id: int, task_queue: queue.Queue, progress: Progress, worker_task_id: TaskID):
    """Worker thread that processes tasks from the queue"""
    worker_logger = logger.bind(component="worker")
    worker_logger.info(f"Worker {worker_id} started")

    completed_tasks = 0

    while not shutdown_event.is_set():
        try:
            task = task_queue.get(timeout=0.1)
        except queue.Empty:
            logger.debug(f"Worker {worker_id} found no tasks in queue, waiting...")
            time.sleep(10)
            continue

        worker_logger.debug(f"Worker {worker_id} processing task {task}")
        # Simulate work for this task
        work_steps = random.randint(5, 15)
        for _ in range(work_steps):
            if shutdown_event.is_set():
                break
            time.sleep(random.uniform(0.01, 0.05))

        progress.update(worker_task_id, advance=1)
        completed_tasks += 1
        task_queue.task_done()
        worker_logger.debug(f"Worker {worker_id} completed task {task}")

    worker_logger.info(f"Worker {worker_id} stopping after completing {completed_tasks} tasks")
    return f"Worker {worker_id} completed {completed_tasks} tasks"

def main(num_workers: int = 4):
    global progress_instance

    # Add console handler for main function only
    main_logger_id = logger.add(sys.stderr, level="INFO",
                                format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>main</cyan> | {message}",
                                filter=lambda record: record["extra"].get("component") is None)

    logger.info("Application starting")

    # Set up signal handler for graceful shutdown
    signal.signal(signal.SIGINT, signal_handler)

    # Create logs directory if it doesn't exist
    os.makedirs("logs", exist_ok=True)

    # Create task queue and populate with all tasks upfront
    task_queue = queue.Queue()
    total_tasks = 50  # Create 50 tasks to process
    for i in range(total_tasks):
        task_queue.put(f"task-{i+1}")
    logger.info(f"Created queue with {total_tasks} tasks")

    try:
        logger.info(f"Starting {num_workers} worker threads")

        # Create a single shared Progress instance
        with Progress(
            TextColumn("[bold]{task.description}", justify="right"),
            BarColumn(),
            TextColumn("{task.completed} tasks"),
            TimeElapsedColumn(),
        ) as progress:
            progress_instance = progress  # Make it accessible to signal handler

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
                worker_futures = []
                for i in range(num_workers):
                    future = executor.submit(worker, i+1, task_queue, progress, worker_task_ids[i])
                    worker_futures.append(future)

                # Wait for all workers to complete or shutdown signal
                results = []
                for future in worker_futures:
                    try:
                        # Use a short timeout to check for shutdown periodically
                        result = future.result(timeout=0.5)
                        results.append(result)
                    except TimeoutError:
                        # If shutdown was signaled, still try to get the result
                        if shutdown_event.is_set():
                            try:
                                result = future.result(timeout=1.0)  # Give it a bit more time
                                results.append(result)
                            except TimeoutError:
                                results.append(f"Worker timed out during shutdown")
                        else:
                            # Continue waiting if no shutdown signal
                            result = future.result()
                            results.append(result)

        # Clear the global reference
        progress_instance = None

        # Log results after Progress context exits to avoid interference
        for result in results:
            logger.info(f"Worker result: {result}")
        logger.info("All tasks completed!")

    except KeyboardInterrupt:
        logger.warning("Forced shutdown...")
        shutdown_event.set()
        # Still try to collect any available results
        if 'worker_futures' in locals():
            for future in worker_futures:
                try:
                    result = future.result(timeout=0.1)
                    logger.info(f"Worker result: {result}")
                except:
                    pass
    finally:
        progress_instance = None
        logger.info("Application shutdown complete")
        logger.remove(main_logger_id)


if __name__ == "__main__":
    main()
