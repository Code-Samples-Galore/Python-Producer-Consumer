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

# Configure loguru with filters
logger.remove()  # Remove default handler
logger.add("logs/app.log", rotation="10 MB", retention="7 days", level="DEBUG")
# Remove the single worker.log - we'll add individual worker logs dynamically
logger.add("logs/producer.log", filter=lambda record: record["extra"].get("component") == "producer", level="DEBUG")
logger.add("logs/consumer.log", filter=lambda record: record["extra"].get("component") == "consumer", level="DEBUG")

# Global event for graceful shutdown
shutdown_event = threading.Event()
# Global progress instance for signal handler
progress_instance = None

def signal_handler(signum, frame):
    """Handle Ctrl+C signal for graceful shutdown"""
    if progress_instance:
        progress_instance.console.print("\n[yellow]Shutdown signal received. Gracefully shutting down...[/yellow]")
    logger.info("Shutdown signal received")
    shutdown_event.set()

def consumer_worker(worker_id: int, task_queue: queue.Queue, progress: Progress, rich_task_id: TaskID, stop_event: threading.Event):
    # Add individual log file for this worker
    worker_log_id = logger.add(f"logs/consumer_worker_{worker_id}.log",
                               filter=lambda record: record["extra"].get("worker_id") == worker_id,
                               level="DEBUG")

    # Use global logger with worker context
    worker_logger = logger.bind(worker_id=worker_id)
    worker_logger.info(f"Consumer-Worker-{worker_id} started")

    completed_tasks = 0

    while not stop_event.is_set() and not shutdown_event.is_set():
        try:
            task = task_queue.get(timeout=0.1)
        except queue.Empty:
            logger.debug(f"Worker {worker_id} found no tasks in queue, waiting...")
            time.sleep(10)
            continue

        worker_logger.debug(f"Processing task {task}")
        # Simulate work for this task
        work_steps = random.randint(5, 15)
        for _ in range(work_steps):
            if stop_event.is_set() or shutdown_event.is_set():
                break
            time.sleep(random.uniform(0.01, 0.05))

        progress.update(rich_task_id, advance=1)
        completed_tasks += 1
        task_queue.task_done()
        worker_logger.debug(f"Completed task {task}")

    worker_logger.info(f"Consumer-Worker-{worker_id} stopping after completing {completed_tasks} tasks")

    # Remove the worker's log handler when done
    logger.remove(worker_log_id)

    return f"Consumer-Worker-{worker_id} completed {completed_tasks} tasks"

def producer_worker(worker_id: int, task_queue: queue.Queue, stop_event: threading.Event, progress: Progress, rich_task_id: TaskID):
    """Producer worker thread that adds tasks to the queue"""
    # Add individual log file for this producer worker
    producer_worker_log_id = logger.add(f"logs/producer_worker_{worker_id}.log",
                                        filter=lambda record: record["extra"].get("producer_worker_id") == worker_id,
                                        level="DEBUG")

    # Use global logger with producer worker context
    producer_worker_logger = logger.bind(producer_worker_id=worker_id)
    producer_worker_logger.info(f"Producer-Worker-{worker_id} started")

    task_count = 0
    while not stop_event.is_set() and not shutdown_event.is_set():
        # Simulate checking for new tasks (e.g., from database, file system, API, etc.)
        if random.random() < 0.8:  # 80% chance of finding new tasks
            batch_size = random.randint(2, 5)
            for _ in range(batch_size):
                task_count += 1
                # Use worker_id to create unique task IDs across producer workers
                unique_task_id = f"{worker_id}-{task_count}"
                task_queue.put(unique_task_id)
                producer_worker_logger.debug(f"Added task {unique_task_id} to queue")
                progress.update(rich_task_id, advance=1)

        time.sleep(random.uniform(0.05, 0.2))  # Check interval

    producer_worker_logger.info(f"Producer-Worker-{worker_id} stopping after adding {task_count} tasks")

    # Remove the producer worker's log handler when done
    logger.remove(producer_worker_log_id)

    return f"Producer-Worker-{worker_id} added {task_count} tasks"

def producer(task_queue: queue.Queue, max_workers: int, stop_event: threading.Event, progress: Progress, producer_task_ids: list):
    """Producer thread that manages multiple producer workers"""
    # Use global logger with producer context
    producer_logger = logger.bind(component="producer")
    producer_logger.info(f"Producer started with {max_workers} workers")

    producer_worker_stop_event = threading.Event()

    producer_logger.debug("Starting producer worker threads")
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [
            executor.submit(producer_worker, i+1, task_queue, producer_worker_stop_event, progress, producer_task_ids[i])
            for i in range(max_workers)
        ]

        # Wait for stop signal
        while not stop_event.is_set() and not shutdown_event.is_set():
            time.sleep(0.1)

        producer_logger.info("Signaling producer workers to stop")
        producer_worker_stop_event.set()

        total_tasks_added = 0
        for future in as_completed(futures):
            result = future.result()
            producer_logger.debug(f"Producer worker finished: {result}")
            # Extract task count from result string
            task_count = int(result.split()[-2])
            total_tasks_added += task_count

    producer_logger.info(f"Producer finished - total {total_tasks_added} tasks added by all workers")
    return f"Producer finished after adding {total_tasks_added} tasks"

def consumer(task_queue: queue.Queue, max_workers: int, producer_stop_event: threading.Event, progress: Progress, consumer_task_ids: list):
    """Consumer thread that manages worker threads and progress display"""
    # Use global logger with consumer context
    consumer_logger = logger.bind(component="consumer")
    consumer_logger.info(f"Consumer started with {max_workers} workers")

    worker_stop_event = threading.Event()

    consumer_logger.debug("Starting worker threads")
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [
            executor.submit(consumer_worker, i + 1, task_queue, progress, consumer_task_ids[i], worker_stop_event)
            for i in range(max_workers)
        ]

        # Wait for producer to finish or shutdown signal
        while not producer_stop_event.is_set() and not shutdown_event.is_set():
            time.sleep(0.1)

        if shutdown_event.is_set():
            consumer_logger.debug("Shutdown event set, stopping workers")
        elif producer_stop_event.is_set():
            consumer_logger.debug("Producer stopped, signaling workers to stop")
        elif task_queue.empty():
            consumer_logger.debug("Task queue is empty, signaling workers to stop")
        else:
            consumer_logger.debug("Signaling workers to stop")

        # Signal workers to stop
        worker_stop_event.set()

        for future in as_completed(futures):
            result = future.result()
            consumer_logger.debug(f"Worker finished: {result}")

    consumer_logger.info("Consumer finished")
    return f"Consumer finished managing {max_workers} workers"

def main(num_producer_workers: int = 3, num_consumer_workers: int = 5):
    global progress_instance

    # Add console handler for main function only
    main_logger_id = logger.add(sys.stderr, level="INFO",
                                format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>main</cyan> | {message}",
                                filter=lambda record: "worker_id" not in record["extra"] and record["extra"].get("component") is None and "producer_worker_id" not in record["extra"])

    logger.info("Application starting")

    # Set up signal handler for graceful shutdown
    signal.signal(signal.SIGINT, signal_handler)

    # Create logs directory if it doesn't exist
    os.makedirs("logs", exist_ok=True)

    # Create task queue and stop event for producer
    task_queue = queue.Queue()
    for i in range(20):  # Reduced initial tasks since producer will add more
        task_queue.put(f"initial-{i}")
    logger.info(f"Initialized queue with 20 initial tasks")

    producer_stop_event = threading.Event()

    try:
        logger.info(f"Starting producer ({num_producer_workers} workers) and consumer ({num_consumer_workers} workers) threads")

        # Create a single shared Progress instance
        with Progress(
            TextColumn("[bold]{task.description}", justify="right"),
            BarColumn(),
            TextColumn("{task.completed} tasks"),
            TimeElapsedColumn(),
        ) as progress:
            progress_instance = progress  # Make it accessible to signal handler

            # Create progress tasks for producer workers
            producer_task_ids = []
            for i in range(num_producer_workers):
                task_id = progress.add_task(
                    description=f"[green]Producer-{i+1}",
                    total=None
                )
                producer_task_ids.append(task_id)

            # Create progress tasks for consumer workers
            consumer_task_ids = []
            for i in range(num_consumer_workers):
                task_id = progress.add_task(
                    description=f"[blue]Consumer-{i+1}",
                    total=None
                )
                consumer_task_ids.append(task_id)

            # Start producer and consumer threads using ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=2) as main_executor:
                # Start producer thread with multiple workers
                producer_future = main_executor.submit(producer, task_queue, num_producer_workers, producer_stop_event, progress, producer_task_ids)

                # Start consumer thread
                consumer_future = main_executor.submit(consumer, task_queue, num_consumer_workers, producer_stop_event, progress, consumer_task_ids)

                # Wait for shutdown signal
                while not shutdown_event.is_set():
                    time.sleep(0.1)

                # Stop producer
                producer_stop_event.set()
                logger.info("Stopping producer...")

                # Wait for both to complete
                producer_result = producer_future.result()
                consumer_result = consumer_future.result()

        # Clear the global reference
        progress_instance = None

        # Log results after Progress context exits to avoid interference
        logger.info(f"Producer result: {producer_result}")
        logger.info(f"Consumer result: {consumer_result}")
        logger.info("All tasks completed!")

    except KeyboardInterrupt:
        logger.warning("Forced shutdown...")
        shutdown_event.set()
    finally:
        progress_instance = None
        logger.info("Application shutdown complete")
        logger.remove(main_logger_id)


if __name__ == "__main__":
    main()
