"""
threefg15
---------

Python driver for the OnRobot 3FG15 gripper using Modbus TCP/RTU.
"""

from .ThreeFG15 import ThreeFG15Modbus, ThreeFG15ModbusTCP, ThreeFG15ModbusRTU, ThreeFG15Status, GripType
from .ThreeFG15Simulator import ThreeFG15Simulator

__all__ = [
    "GripperBase",
    "ThreeFG15Modbus",
    "ThreeFG15ModbusTCP",
    "ThreeFG15ModbusRTU",
    "ThreeFG15Status",
    "GripType",
    "ThreeFG15Simulator",
]