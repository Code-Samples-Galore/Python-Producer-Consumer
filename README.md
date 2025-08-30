# 🧵 Python Producer-Consumer Example

## 📝 Overview
This project demonstrates different approaches to multithreading in Python, focusing on producer-consumer patterns and worker threads. It includes two main architectures: a thread-based worker system and a producer-consumer system with configurable workers.

## 📁 Project Structure
- `main.py`: Entry point for running the project with CLI interface.
- `threads.py`: Thread-based worker architecture that processes tasks from a pre-populated queue.
- `producer_consumer.py`: Producer-consumer architecture with configurable producer and consumer workers.
- `logs/`: Contains log files for each worker and process.
- `requirements.txt`: Python dependencies.

## 🏗️ Architectures

### 🧶 Threads Architecture
- **Description**: Workers process tasks from a pre-populated queue
- **Use case**: When you have a known set of tasks to process
- **Configuration**: Number of thread workers (default: 4)

### 🔄 Producer-Consumer Architecture  
- **Description**: Separate producer and consumer workers with dynamic task generation
- **Use case**: When tasks are generated continuously and need to be processed in real-time
- **Configuration**: 
  - Number of producer workers (default: 1)
  - Number of consumer workers (default: 1)

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
- **Graceful Shutdown**: Ctrl+C handling for clean termination
- **Configurable Workers**: Adjust the number of workers for different architectures
- **Comprehensive Logging**: Separate log files for different components and workers
- **Signal Handling**: Proper cleanup on shutdown signals

## 📦 Requirements
- Python 3.12 or higher
- Dependencies listed in `requirements.txt`

## 💡 Examples

### ⚡ High Throughput Processing
```bash
# Use multiple thread workers for CPU-intensive tasks
python main.py run threads --thread-workers 12
```

### ⏱️ Real-time Task Processing
```bash
# Use producer-consumer for continuous task generation and processing
python main.py run producer-consumer --producer-workers 3 --consumer-workers 6
```

## 📄 License

MIT License
