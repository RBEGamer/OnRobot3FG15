# Start from a lightweight Python base image
FROM python:3.11-slim

# Set working directory
WORKDIR /threefg15

# Install system dependencies (for pyserial/RTU support, if needed)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libusb-1.0-0-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
    # Install dependencies
RUN pip install --no-cache-dir -r requirements.txt


# Copy project files (if building locally from source)
COPY . .

RUN pip install -e .
# Default entrypoint: run the CLI
ENTRYPOINT ["threefg15-cli"]