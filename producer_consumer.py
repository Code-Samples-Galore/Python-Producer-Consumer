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

# Bound the queue so producers block instead of growing the backlog without
# limit. Producers outrun consumers by design here, so this is what keeps
# memory flat during a long run.
QUEUE_MAXSIZE = 100

# Two-stage shutdown:
#   shutdown_event       - stop producing, let consumers finish the backlog
#   force_shutdown_event - abandon queued work and stop now (second Ctrl+C)
shutdown_event = threading.Event()
force_shutdown_event = threading.Event()


def setup_logging():
    """Configure loguru sinks. Called from main() so that importing this
    module does not reconfigure logging for the whole process."""
    os.makedirs("logs", exist_ok=True)
    logger.remove()  # Remove default handler
    logger.add("logs/app.log", rotation="10 MB", retention="7 days", level="DEBUG")
    logger.add("logs/producer.log", filter=lambda record: record["extra"].get("component") == "producer", level="DEBUG")
    logger.add("logs/consumer.log", filter=lambda record: record["extra"].get("component") == "consumer", level="DEBUG")

def signal_handler(signum, frame):
    """Handle Ctrl+C. Signal handlers run on the main thread between
    bytecodes, so this only flips flags - no logging, printing or locking.
    Anything that can block or raise here would strand the worker threads."""
    if shutdown_event.is_set():
        force_shutdown_event.set()
    else:
        shutdown_event.set()

def consumer_worker(worker_id: int, task_queue: queue.Queue, progress: Progress, rich_task_id: TaskID, drain_event: threading.Event):
    """Consumer worker thread that processes tasks from the queue.

    Runs until forced to stop, or until `drain_event` is set and the queue has
    been emptied - that second condition is what lets the backlog finish
    cleanly after the producers have stopped.
    """
    # Add individual log file for this worker
    worker_log_id = logger.add(f"logs/consumer_worker_{worker_id}.log",
                               filter=lambda record: record["extra"].get("worker_id") == worker_id,
                               level="DEBUG")

    try:
        # Use global logger with worker context
        worker_logger = logger.bind(worker_id=worker_id)
        worker_logger.info("Consumer-Worker-{} started", worker_id)

        completed_tasks = 0

        while not force_shutdown_event.is_set():
            try:
                task = task_queue.get(timeout=0.1)
            except queue.Empty:
                if drain_event.is_set():
                    worker_logger.debug("Queue drained, Consumer-Worker-{} finishing", worker_id)
                    break
                # The blocking get above already paced us - no extra sleep.
                continue

            try:
                worker_logger.debug("Processing task {}", task)
                # Simulate work for this task
                interrupted = False
                work_steps = random.randint(5, 15)
                for _ in range(work_steps):
                    if force_shutdown_event.is_set():
                        interrupted = True
                        break
                    time.sleep(random.uniform(0.01, 0.05))

                if interrupted:
                    # Abandoned part-way through - do not count it as done.
                    worker_logger.debug("Abandoned task {} during shutdown", task)
                    continue

                progress.update(rich_task_id, advance=1)
                completed_tasks += 1
                worker_logger.debug("Completed task {}", task)
            finally:
                task_queue.task_done()

        worker_logger.info("Consumer-Worker-{} stopping after completing {} tasks", worker_id, completed_tasks)
        return completed_tasks
    finally:
        # Remove the worker's log handler even if the body raised, otherwise
        # the handler and its open file descriptor leak.
        logger.remove(worker_log_id)

def producer_worker(worker_id: int, task_queue: queue.Queue, stop_event: threading.Event, progress: Progress, rich_task_id: TaskID):
    """Producer worker thread that adds tasks to the queue"""
    # Add individual log file for this producer worker
    producer_worker_log_id = logger.add(f"logs/producer_worker_{worker_id}.log",
                                        filter=lambda record: record["extra"].get("producer_worker_id") == worker_id,
                                        level="DEBUG")

    try:
        # Use global logger with producer worker context
        producer_worker_logger = logger.bind(producer_worker_id=worker_id)
        producer_worker_logger.info("Producer-Worker-{} started", worker_id)

        task_count = 0
        while not stop_event.is_set() and not shutdown_event.is_set():
            # Simulate checking for new tasks (e.g. from database, file system, API, etc.)
            if random.random() < 0.8:  # 80% chance of finding new tasks
                batch_size = random.randint(2, 5)
                for _ in range(batch_size):
                    if stop_event.is_set() or shutdown_event.is_set():
                        break
                    # Use worker_id to create unique task IDs across producer workers
                    unique_task_id = f"{worker_id}-{task_count + 1}"
                    try:
                        # Blocking put with a timeout: this is the backpressure.
                        # A full queue slows the producer down instead of
                        # letting the backlog grow without bound.
                        task_queue.put(unique_task_id, timeout=0.5)
                    except queue.Full:
                        producer_worker_logger.debug("Queue full, backing off")
                        break
                    task_count += 1
                    producer_worker_logger.debug("Added task {} to queue", unique_task_id)
                    progress.update(rich_task_id, advance=1)

            time.sleep(random.uniform(0.05, 0.2))  # Check interval

        producer_worker_logger.info("Producer-Worker-{} stopping after adding {} tasks", worker_id, task_count)
        return task_count
    finally:
        # Remove the producer worker's log handler even if the body raised.
        logger.remove(producer_worker_log_id)

def producer(task_queue: queue.Queue, num_workers: int, stop_event: threading.Event, progress: Progress, producer_task_ids: list):
    """Producer thread that manages multiple producer workers"""
    # Use global logger with producer context
    producer_logger = logger.bind(component="producer")
    producer_logger.info("Producer started with {} workers", num_workers)

    producer_worker_stop_event = threading.Event()
    total_tasks_added = 0

    with ThreadPoolExecutor(max_workers=num_workers) as executor:
        futures = {}
        try:
            for i in range(num_workers):
                future = executor.submit(producer_worker, i + 1, task_queue, producer_worker_stop_event, progress, producer_task_ids[i])
                futures[future] = i + 1  # Store future with worker ID

            # Wait for stop signal
            while not stop_event.is_set() and not shutdown_event.is_set():
                time.sleep(0.1)
        finally:
            # Always release the workers, even if the wait above raised -
            # otherwise the executor's shutdown would join threads that are
            # still waiting to be told to stop.
            producer_logger.info("Signaling producer workers to stop")
            producer_worker_stop_event.set()

        for future in as_completed(futures):
            worker_id = futures[future]
            result = future.result()
            producer_logger.debug("Producer worker {} finished: {}", worker_id, result)
            total_tasks_added += result

    producer_logger.info("Producer finished - total {} tasks added by all workers", total_tasks_added)
    return total_tasks_added

def consumer(task_queue: queue.Queue, num_workers: int, producer_stop_event: threading.Event, progress: Progress, consumer_task_ids: list):
    """Consumer thread that manages worker threads and progress display"""
    # Use global logger with consumer context
    consumer_logger = logger.bind(component="consumer")
    consumer_logger.info("Consumer started with {} workers", num_workers)

    drain_event = threading.Event()
    total_tasks_completed = 0

    with ThreadPoolExecutor(max_workers=num_workers) as executor:
        futures = {}
        try:
            for i in range(num_workers):
                future = executor.submit(consumer_worker, i + 1, task_queue, progress, consumer_task_ids[i], drain_event)
                futures[future] = i + 1  # Store future with worker ID

            # Wait for the producers to finish or for a shutdown signal
            while (not producer_stop_event.is_set()
                   and not shutdown_event.is_set()
                   and not force_shutdown_event.is_set()):
                time.sleep(0.1)
        finally:
            # Tell the workers to finish the backlog and then exit. They stop
            # on their own once the queue is empty, so the remaining tasks get
            # processed rather than abandoned.
            if force_shutdown_event.is_set():
                consumer_logger.warning("Forced stop - abandoning {} queued tasks", task_queue.qsize())
            else:
                consumer_logger.info("Producers stopped - draining {} queued tasks", task_queue.qsize())
            drain_event.set()

        for future in as_completed(futures):
            worker_id = futures[future]
            result = future.result()
            consumer_logger.debug("Consumer worker {} finished: {}", worker_id, result)
            total_tasks_completed += result

    consumer_logger.info("Consumer finished - total {} tasks completed by all workers", total_tasks_completed)
    return total_tasks_completed

def main(num_producer_workers: int = 1, num_consumer_workers: int = 1):
    if num_producer_workers < 1 or num_consumer_workers < 1:
        raise ValueError("Worker counts must be at least 1")

    setup_logging()

    # Add console handler for main function only
    main_logger_id = logger.add(sys.stderr, level="INFO",
                                format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>main</cyan> | {message}",
                                filter=lambda record: "worker_id" not in record["extra"] and record["extra"].get("component") is None and "producer_worker_id" not in record["extra"])

    logger.info("Application starting")

    # Set up signal handler for graceful shutdown
    signal.signal(signal.SIGINT, signal_handler)

    # Create task queue and stop event for producer
    task_queue = queue.Queue(maxsize=QUEUE_MAXSIZE)
    initial_tasks = 20  # Reduced initial tasks since producer will add more
    for i in range(initial_tasks):
        task_queue.put(f"initial-{i}")
    logger.info("Initialized queue with {} initial tasks (max size {})", initial_tasks, QUEUE_MAXSIZE)

    producer_stop_event = threading.Event()
    producer_result = consumer_result = 0

    try:
        logger.info("Starting producer ({}) workers and consumer ({}) workers threads", num_producer_workers, num_consumer_workers)
        logger.info("Press Ctrl+C to stop producing and drain the queue")

        # Create a single shared Progress instance
        with Progress(
            TextColumn("[bold]{task.description}", justify="right"),
            BarColumn(),
            TextColumn("{task.completed} tasks"),
            TimeElapsedColumn(),
        ) as progress:
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

                try:
                    # Wait for shutdown signal, watching for a thread that died
                    # early - an exception in either future is otherwise
                    # invisible and would leave this loop spinning forever.
                    while not shutdown_event.is_set():
                        for future, name in ((producer_future, "producer"), (consumer_future, "consumer")):
                            if future.done() and future.exception() is not None:
                                logger.error("{} thread failed: {}", name, future.exception())
                                shutdown_event.set()
                        time.sleep(0.1)
                finally:
                    # Make sure both coordinators are released no matter how we
                    # leave the loop, so the executor below can never block on
                    # threads waiting for a flag nobody set.
                    shutdown_event.set()
                    producer_stop_event.set()

                if not force_shutdown_event.is_set():
                    logger.info("Stopping producer, draining queue (Ctrl+C again to abort)...")

                # Wait for both to complete
                producer_result = producer_future.result()
                consumer_result = consumer_future.result()

        # Log results after Progress context exits to avoid interference
        remaining = task_queue.qsize()
        logger.info("Producer result: {} tasks produced", producer_result)
        logger.info("Consumer result: {} tasks consumed", consumer_result)
        if remaining:
            logger.warning("Shutdown complete - {} tasks left unprocessed in the queue", remaining)
        else:
            logger.info("Shutdown complete - queue fully drained")

    except KeyboardInterrupt:
        logger.warning("Forced shutdown...")
        shutdown_event.set()
        force_shutdown_event.set()
    finally:
        logger.info("Application shutdown complete")
        logger.remove(main_logger_id)


if __name__ == "__main__":
    main()
