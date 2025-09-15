#!/usr/bin/env python3
import time
import typer
from threefg15 import ThreeFG15Simulator
from threefg15.ThreeFG15 import ThreeFG15ModbusRTU, ThreeFG15ModbusTCP, GripType, ThreeFG15Status
from threefg15.server import run_gripper_server

app = typer.Typer(add_completion=False)


def wait_until_done(gripper) -> ThreeFG15Status | None:
    """Poll until gripper finishes motion and return status."""
    while True:
        status = gripper.get_status()
        if status and not status.busy:
            return status
        time.sleep(0.1)


def monitor_detection(gripper) -> None:
    """Continuously print grip detection state until Ctrl+C."""
    print("Monitoring object detection... (Ctrl+C to stop)")
    try:
        while True:
            status = gripper.get_status()
            if status:
                if status.force_grip_detected:
                    print("Object firmly held")
                elif status.grip_detected:
                    print("Object detected")
                else:
                    print("No object detected")
            else:
                print("Could not read status")
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("Stopped detection monitor")


def interactive_loop(gripper):
    """Run the interactive REPL-style CLI for gripper control."""
    print("Connected to 3FG15 gripper")
    print("Commands: open [force], close [force], move <diam_mm> [force], "
          "griptype <external|internal>, stop, flex <diam_mm> [force], "
          "flexopen [force], flexclose [force], limits, force, status, "
          "detect, exit")

    while True:
        try:
            cmd = input("3FG15> ").strip().split()
            if not cmd:
                continue

            if cmd[0] in ("exit", "quit"):
                print("Exiting...")
                break

            elif cmd[0] == "status":
                status = gripper.get_status()
                print(f"Status: {status}")
                print(f"Force: {gripper.get_force_applied()} %")
                print(f"Diameter: {gripper.get_raw_diameter()} mm")

            elif cmd[0] == "open":
                force = int(cmd[1]) if len(cmd) > 1 else 500
                gripper.open_gripper(force_val=force)
                wait_until_done(gripper)

            elif cmd[0] == "close":
                force = int(cmd[1]) if len(cmd) > 1 else 500
                gripper.close_gripper(force_val=force)
                wait_until_done(gripper)

            elif cmd[0] == "move":
                if len(cmd) < 2:
                    print("Usage: move <diameter_mm> [force]")
                    continue
                diam = int(float(cmd[1]) * 10)
                force = int(cmd[2]) if len(cmd) > 2 else 500
                gripper.move_gripper(diameter=diam, force_val=force, grip_type=GripType.EXTERNAL)
                wait_until_done(gripper)

            elif cmd[0] == "griptype":
                if len(cmd) < 2 or cmd[1] not in ("external", "internal"):
                    print("Usage: griptype <external|internal>")
                    continue
                gt = GripType.EXTERNAL if cmd[1] == "external" else GripType.INTERNAL
                gripper.set_grip_type(gt)
                print(f"Grip type set to {gt.name}")

            elif cmd[0] == "stop":
                gripper.set_control(gripper.CMD_STOP)

            elif cmd[0] == "flex":
                if len(cmd) < 2:
                    print("Usage: flex <diam_mm> [force]")
                    continue
                diam = int(float(cmd[1]) * 10)
                force = int(cmd[2]) if len(cmd) > 2 else 100
                gripper.flex_grip(diameter=diam, force_val=force, grip_type=GripType.EXTERNAL)
                wait_until_done(gripper)

            elif cmd[0] == "flexopen":
                force = int(cmd[1]) if len(cmd) > 1 else 100
                max_d = gripper.read_registers(gripper.REG_MAX_DIAMETER, 1)[0]
                gripper.flex_grip(diameter=max_d, force_val=force, grip_type=GripType.EXTERNAL)
                wait_until_done(gripper)

            elif cmd[0] == "flexclose":
                force = int(cmd[1]) if len(cmd) > 1 else 100
                min_d = gripper.read_registers(gripper.REG_MIN_DIAMETER, 1)[0]
                gripper.flex_grip(diameter=min_d, force_val=force, grip_type=GripType.EXTERNAL)
                wait_until_done(gripper)

            elif cmd[0] == "limits":
                min_d = gripper.read_registers(gripper.REG_MIN_DIAMETER, 1)[0] / 10.0
                max_d = gripper.read_registers(gripper.REG_MAX_DIAMETER, 1)[0] / 10.0
                print(f"Limits: Min {min_d:.1f} mm, Max {max_d:.1f} mm")

            elif cmd[0] == "force":
                print(f"Force: {gripper.get_force_applied()} %")

            elif cmd[0] == "detect":
                monitor_detection(gripper)

            else:
                print("Unknown command")

        except KeyboardInterrupt:
            print("\nExiting...")
            break
        except Exception as e:
            print(f"Error: {e}")

    gripper.close_connection()


@app.command()
def rtu(
    serial_port: str = typer.Option("/dev/tty.usbserial-A5052NB6", help="Serial port for RTU mode"),
    timeout: float = typer.Option(1.0, help="Communication timeout in seconds"),
):
    """Connect to gripper via RTU (USB/serial)."""
    gripper = ThreeFG15ModbusRTU(serial_port=serial_port, timeout=timeout)
    if not gripper.open_connection():
        print("Failed to connect to gripper (RTU)")
        raise typer.Exit(code=1)
    interactive_loop(gripper)


@app.command()
def tcp(
    ip: str = typer.Option("192.168.1.10", help="IP address for TCP mode"),
    port: int = typer.Option(502, help="TCP port"),
    timeout: float = typer.Option(1.0, help="Communication timeout in seconds"),
):
    """Connect to gripper via TCP (Ethernet)."""
    gripper = ThreeFG15ModbusTCP(ip=ip, port=port, timeout=timeout)
    if not gripper.open_connection():
        print("Failed to connect to gripper (TCP)")
        raise typer.Exit(code=1)
    interactive_loop(gripper)






@app.command()
def server(
    listen: str = typer.Option("0.0.0.0", help="Listen address"),
    port: int = typer.Option(5020, help="Port for Modbus TCP server"),
    mode: str = typer.Option("rtu", help="Gripper connection mode: rtu tcp sim"),
    serial_port: str = typer.Option("/dev/tty.usbserial-A5052NB6", help="Serial port for RTU"),
    ip: str = typer.Option("192.168.1.10", help="Gripper IP for TCP mode"),
    gripper_port: int = typer.Option(502, help="Gripper TCP port"),
):
    """Expose the gripper as a Modbus TCP server with simple register map."""
    if mode == "tcp":
        gripper = ThreeFG15ModbusTCP(ip=ip, port=gripper_port)
    elif mode == "rtu":
        gripper = ThreeFG15ModbusRTU(serial_port=serial_port)
    elif mode == "sim":
        gripper = ThreeFG15Simulator()

    if not gripper.open_connection():
        print("Failed to connect to gripper")
        raise typer.Exit(code=1)

    run_gripper_server(gripper, listen=listen, port=port)

if __name__ == "__main__":
    app()