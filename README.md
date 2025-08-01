# Python Producer-Consumer Example

## Overview
This project demonstrates different approaches to multithreading and multiprocessing in Python, focusing on producer-consumer patterns and worker threads. It includes several scripts for single-threaded, multi-threaded, and multi-process execution, as well as logging for each worker and process.

## Project Structure
- `main.py`: Entry point for running the project.
- `single_threaded.py`: Single-threaded implementation of both producer and consumer.
- `multi_threaded.py`: Multi-threaded implementation of both producer and consumer.
- `only_workers.py`: Worker-only threading example.
- `producer_multi_threaded.py`: Multi-threaded producer and single threaded consumer example.
- `consumer_multi_threaded.py`: Multi-threaded consumer and single threaded producer example.
- `logs/`: Contains log files for each worker and process.
- `requirements.txt`: Python dependencies.

## Usage
1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
2. Run any of the scripts, for example:
   ```bash
   python main.py run multi-threaded
   ```
   or
   ```bash
   python multi_threaded.py
   ```

## Logging
Each script writes logs to the `logs/` directory, with separate log files for each worker and process.

## Requirements
- Python 3.12 or higher
