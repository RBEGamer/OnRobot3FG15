from threefg15.core import ThreeFG15RTU, ThreeFG15TCP, ThreeFG15Status
import time


def main() -> None:
    """
    Example for using the ThreeFG15 package.

    By default, this connects over RTU (USB/serial).
    To use TCP instead, replace the RTU instance with:

        gripper = ThreeFG15TCP(ip="192.168.1.10", port=502)

    Make sure the IP and port match your gripper’s Modbus TCP settings.
    """

    # --- Choose connection mode ---
    # RTU (USB/serial)
    gripper = ThreeFG15RTU(serial_port="/dev/tty.usbserial-A5052NB6")

    # TCP (Ethernet) -> uncomment to use
    # gripper = ThreeFG15TCP(ip="192.168.1.10", port=502)

    if not gripper.open_connection():
        print("Failed to connect to gripper")
        return

    # Read limits
    min_d: float = gripper.read_registers(gripper.REG_MIN_DIAMETER, 1)[0] / 10.0
    max_d: float = gripper.read_registers(gripper.REG_MAX_DIAMETER, 1)[0] / 10.0

    # Read current diameter
    current_diameter: float = gripper.get_raw_diameter() or 0.0
    print(f"Current gripper opening: {current_diameter:.1f} mm")

    midpoint: float = (min_d + max_d) / 2.0

    if current_diameter < midpoint:
        # Start by opening
        print("Opening gripper...")
        gripper.open_gripper(force_val=300)
        time.sleep(2)
        print(f"Gripper opened to: {gripper.get_raw_diameter():.1f} mm")

        print("Closing gripper...")
        gripper.close_gripper(force_val=500)
        time.sleep(2)
        print(f"Gripper closed to: {gripper.get_raw_diameter():.1f} mm")

    else:
        # Start by closing
        print("Closing gripper...")
        gripper.close_gripper(force_val=500)
        time.sleep(2)
        print(f"Gripper closed to: {gripper.get_raw_diameter():.1f} mm")

        print("Opening gripper...")
        gripper.open_gripper(force_val=300)
        time.sleep(2)
        print(f"Gripper opened to: {gripper.get_raw_diameter():.1f} mm")

    # Final status
    status: ThreeFG15Status | None = gripper.get_status()
    print("Final status:", status)

    gripper.close_connection()


if __name__ == "__main__":
    main()