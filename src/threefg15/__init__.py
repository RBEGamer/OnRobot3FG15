"""
threefg15
---------

Python driver for the OnRobot 3FG15 gripper using Modbus TCP/RTU.
"""

from .core import ThreeFG15, ThreeFG15TCP, ThreeFG15RTU, ThreeFG15Status, GripType

__all__ = [
    "ThreeFG15",
    "ThreeFG15TCP",
    "ThreeFG15RTU",
    "ThreeFG15Status",
    "GripType",
]