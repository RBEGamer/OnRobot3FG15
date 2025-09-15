#!/usr/bin/env python3
from typing import Optional, List, Union
from dataclasses import dataclass
from enum import Enum
from abc import ABC, abstractmethod
import time
import random

# Handle both package import and direct execution
try:
    # When imported as a package
    from .ThreeFG15Modbus import ThreeFG15Modbus
    from .ThreeFG15Simulator import ThreeFG15Simulator
    from .GripperBase import GripperBase, GripType
    from .status import ThreeFG15Status
except ImportError:
    # When run directly as a script
    from ThreeFG15Modbus import ThreeFG15Modbus
    from ThreeFG15Simulator import ThreeFG15Simulator
    from GripperBase import GripperBase, GripType
    from status import ThreeFG15Status


class ThreeFG15ModbusTCP(ThreeFG15Modbus):
    def __init__(self, ip: str, port: int = 502, slave_addr: int = 65, timeout: float = 1.0) -> None:
        super().__init__(mode="tcp", ip=ip, port=port, slave_addr=slave_addr, timeout=timeout)
    
    
class ThreeFG15ModbusRTU(ThreeFG15Modbus):
    def __init__(self, serial_port: str, slave_addr: int = 65, timeout: float = 1.0) -> None:
        super().__init__(mode="rtu", serial_port=serial_port, slave_addr=slave_addr, timeout=timeout)


if __name__ == "__main__":
    # --- Example 1: TCP (Ethernet) ---
    #gripper = ThreeFG15ModbusTCP(ip="192.168.178.22", port=5020)
    
    # --- Example 2: RTU (USB/serial RS485) ---
    gripper = ThreeFG15ModbusRTU(serial_port="/dev/tty.usbserial-A5052NB6")
    
    # --- Example 3: Simulator ---
    #gripper = ThreeFG15Simulator(simulation_speed=2.0, enable_noise=True)

    if gripper.open_connection():
        print(f"Connected to gripper {gripper.__class__.__name__}")

        # Open gripper
        gripper.open_gripper(force_val=500)

        # Wait a bit (robot program usually checks busy flag)
        import time; time.sleep(2)

        # Close gripper
        gripper.close_gripper(force_val=700)

        # Check status
        status = gripper.get_status()
        print("Status:", status)

        gripper.close_connection()
    else:
        print("Failed to connect")