# OnRobot 3FG15 Gripper Python Package

[![Build and Test](https://github.com/RBEGamer/OnRobot3FG15/actions/workflows/main.yml/badge.svg)](https://github.com/RBEGamer/OnRobot3FG15/actions/workflows/main.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
![repo size](https://img.shields.io/github/repo-size/RBEGamer/OnRobot3FG15)

## Overview

This package provides a Python driver and command-line interface (CLI) for controlling the [OnRobot 3FG15](https://onrobot.com/en/products/3fg15) gripper. It supports communication over Modbus TCP and RTU protocols, enabling precise control over the gripper's 3-finger parallel mechanism, including external and internal gripping modes. The package also supports object detection features integrated into the gripper.


## Package Features

- Python driver for [OnRobot 3FG15](https://onrobot.com/en/products/3fg15) gripper
- Command-line interface (CLI) with subcommands for RTU and TCP communication to control all functions of the gripper
- Support for Modbus TCP and Modbus RTU protocols
- Object detection and grip force/diameter control


## Communication Modes and Pin Connections

The gripper can be controlled via two Modbus communication modes:

- **Modbus TCP**: Connect via Ethernet using the Modbus TCP protocol.
- **Modbus RTU**: Connect via serial interface (RS-485) using Modbus RTU protocol.

Pin connections for the gripper electrical interface (female M8x8 connector):

- Pin 1: RS485+
- Pin 2: RS485-
- Pin 3: GND
- Pin 7: +24V


## Requirements

### Software

- Python 3.8 or higher
- `pymodbus` library for Modbus communication
- `typer` library for CLI interface

### Hardware

- OnRobot 3FG15 Gripper
- Modbus interface (USB-RS-485 for RTU with a supported baudrate of `1 000 000`, most Modbus TCP<->RTU interface wont work with such high baudrates!)

## Installation

Install the package using pip:

```bash
$ pip install threefg15

# or for local development/usage
$ git clone https://github.com/RBEGamer/OnRobot3FG15
$ cd OnRobot3FG15
$ pip install -e .
```

## Usage

### Importing the Driver

```python
from threefg15.core import ThreeFG15
```

### Example Python Code

For further examples and minimal demo code, refer to the `src/examples` folder.

```python
from threefg15.ThreeFG15 import ThreeFG15ModbusRTU, ThreeFG15ModbusTCP, ThreeFG15Status


# Initialize gripper with Modbus TCP or RTU connection
gripper = ThreeFG15ModbusTCP(ip_address="192.168.0.10", port=502)
gripper = ThreeFG15ModbusRTU(serial_port="/dev/tty.usbserial-A5052NB6")
# Open the gripper
gripper.open()
# Gripper opened to: 143.0 mm

# Close the gripper with specified force
gripper.close(force=50)
# Gripper closed to: 148.8 mm

# Check object detection status
detected = gripper.is_object_detected()
print(f"Object detected: {detected}")

print(f"Object detected: {gripper.get_status()}")
# Final status: ThreeFG15Status(busy=False, grip_detected=True, force_grip_detected=True calibration_ok=True)
```

### Command Line Interface (CLI)

The CLI provides two subcommands for communication modes:

- `rtu`: Use Modbus RTU over serial
- `tcp`: Use Modbus TCP over Ethernet

#### CLI installation only

##### PipX
```bash
$ pipx upgrade threefg15
```

##### Docker
```bash
$ docker build -t threefg15 .
$ docker run --rm threefg15
$ docker run --rm --device=/dev/ttyUSB0 threefg15 #PASS USB<->MODBUS BRIDGE
```


#### Usage Example

```bash
threefg15-cli rtu --serial-port /dev/ttyUSB0
```

#### TCP Usage Example

```bash
threefg15-cli tcp --ip 192.168.1.10 --port 502
```

Replace parameters such as IP address, port, serial port, and baud rate according to your setup.

The cli application offers the following commands:

* open [force], close [force], move <diam_mm> [force]
* griptype <external|internal>
* stop
* flex <diam_mm> [force], flexopen [force], flexclose [force]
* limits, force
* status, detect



## License

This software is released under the MIT License, see [LICENSE](./LICENSE).

---

