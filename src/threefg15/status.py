

from dataclasses import dataclass


@dataclass
class ThreeFG15Status:
    """
    Data class representing the status bits of the 3FG15 gripper.
    """
    busy: bool
    grip_detected: bool
    force_grip_detected: bool
    calibration_ok: bool

    @classmethod
    def from_register(cls, reg_value: int) -> "ThreeFG15Status":
        """
        Create a ThreeFG15Status instance from a 16-bit register value.

        Args:
            reg_value (int): 16-bit integer status register.

        Returns:
            ThreeFG15Status: Parsed status object.
        """
        status = format(reg_value, '016b')
        return cls(
            busy=bool(int(status[-1])),
            grip_detected=bool(int(status[-2])),
            force_grip_detected=bool(int(status[-3])),
            calibration_ok=bool(int(status[-4]))
        )