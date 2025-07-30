from concurrent.futures import ThreadPoolExecutor
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

def producer(task_queue: queue.Queue, stop_event: threading.Event, progress: Progress, producer_task_id: TaskID):
    """Producer thread that adds tasks to the queue"""
    # Use global logger with producer context
    producer_logger = logger.bind(component="producer")
    producer_logger.info("Producer started")

    task_count = 0
    while not stop_event.is_set() and not shutdown_event.is_set():
        # Simulate checking for new tasks (e.g., from database, file system, API, etc.)
        if random.random() < 0.7:  # 70% chance of finding new tasks
            batch_size = random.randint(2, 5)
            for _ in range(batch_size):
                task_count += 1
                task_queue.put(f"task-{task_count}")
                producer_logger.debug(f"Added task-{task_count} to queue")
                progress.update(producer_task_id, advance=1)

        time.sleep(random.uniform(0.1, 0.5))  # Check interval

    producer_logger.info(f"Producer stopping after adding {task_count} tasks")
    return f"Producer finished after adding {task_count} tasks"

def consumer(task_queue: queue.Queue, producer_stop_event: threading.Event, progress: Progress, consumer_task_id: TaskID):
    """Consumer thread that processes tasks from the queue"""
    # Use global logger with consumer context
    consumer_logger = logger.bind(component="consumer")
    consumer_logger.info("Consumer started")

    completed_tasks = 0

    while not producer_stop_event.is_set() or not task_queue.empty():
        if shutdown_event.is_set():
            break

        try:
            task = task_queue.get(timeout=0.1)
        except queue.Empty:
            logger.debug("Consumer found no tasks in queue, waiting...")
            time.sleep(10)
            continue

        consumer_logger.debug(f"Processing task {task}")
        # Simulate work for this task
        work_steps = random.randint(5, 15)
        for _ in range(work_steps):
            if shutdown_event.is_set():
                break
            time.sleep(random.uniform(0.01, 0.05))

        progress.update(consumer_task_id, advance=1)
        completed_tasks += 1
        task_queue.task_done()
        consumer_logger.debug(f"Completed task {task}")

    consumer_logger.info(f"Consumer stopping after completing {completed_tasks} tasks")
    return f"Consumer completed {completed_tasks} tasks"

def main():
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

    # Create task queue and stop event for producer
    task_queue = queue.Queue()
    for i in range(10):  # Initial tasks
        task_queue.put(f"initial-{i}")
    logger.info(f"Initialized queue with 10 initial tasks")

    producer_stop_event = threading.Event()

    try:
        logger.info("Starting producer and consumer threads")

        # Create a single shared Progress instance
        with Progress(
            TextColumn("[bold]{task.description}", justify="right"),
            BarColumn(),
            TextColumn("{task.completed} tasks"),
            TimeElapsedColumn(),
        ) as progress:
            progress_instance = progress  # Make it accessible to signal handler

            # Create progress task for producer
            producer_task_id = progress.add_task(
                description="[green]Producer",
                total=None
            )

            # Create progress task for consumer
            consumer_task_id = progress.add_task(
                description="[blue]Consumer",
                total=None
            )

            # Start producer and consumer threads using ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=2) as main_executor:
                # Start producer thread
                producer_future = main_executor.submit(producer, task_queue, producer_stop_event, progress, producer_task_id)

                # Start consumer thread
                consumer_future = main_executor.submit(consumer, task_queue, producer_stop_event, progress, consumer_task_id)

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
