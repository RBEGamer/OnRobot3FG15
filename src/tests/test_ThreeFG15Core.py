import pytest
from threefg15.ThreeFG15 import ThreeFG15Status, GripType, ThreeFG15Simulator


# ---------- Status parsing tests ----------
def test_status_parsing_busy_and_grip_detected():
    reg_value = int("0000000000000011", 2)  # busy=1, grip_detected=1
    status = ThreeFG15Status.from_register(reg_value)
    assert status.busy
    assert status.grip_detected
    assert not status.force_grip_detected
    assert not status.calibration_ok


def test_status_parsing_force_and_calibration():
    reg_value = int("0000000000001100", 2)  # force_grip_detected=1, calibration_ok=1
    status = ThreeFG15Status.from_register(reg_value)
    assert status.force_grip_detected
    assert status.calibration_ok
    assert not status.busy
    assert not status.grip_detected


# ---------- GripType enum tests ----------
def test_griptype_enum_values():
    assert GripType.EXTERNAL.value == 0
    assert GripType.INTERNAL.value == 1
    assert str(GripType.EXTERNAL) == "GripType.EXTERNAL"


# ---------- Core class tests with mocking ----------
def test_set_grip_type_calls_register_write(monkeypatch):
    calls = {}

    def fake_write_register(reg, value):
        calls["reg"] = reg
        calls["value"] = value

    gripper = ThreeFG15Simulator()
    gripper.client = True
    gripper.write_register = fake_write_register

    gripper.set_grip_type(GripType.INTERNAL)

    assert calls["reg"] == gripper.REG_GRIP_TYPE
    assert calls["value"] == GripType.INTERNAL.value


def test_detect_object(monkeypatch):
    gripper = ThreeFG15Simulator()

    gripper.get_status = lambda: ThreeFG15Status(
        busy=False, grip_detected=True, force_grip_detected=False, calibration_ok=True
    )
    assert gripper.detect_object()

    gripper.get_status = lambda: ThreeFG15Status(
        busy=False, grip_detected=False, force_grip_detected=False, calibration_ok=True
    )
    assert not gripper.detect_object()


def test_open_gripper(monkeypatch):
    calls = {}

    def fake_read_registers(reg, count=1):
        return [1200]  # simulate max diameter

    def fake_write_register(reg, value):
        calls.setdefault("writes", []).append((reg, value))

    gripper = ThreeFG15Simulator()
    gripper.read_registers = fake_read_registers
    gripper.write_register = fake_write_register

    gripper.open_gripper(force_val=500)

    # Force, Diameter, GripType, Control should be set
    assert any(r == gripper.REG_TARGET_FORCE for r, _ in calls["writes"])
    assert any(r == gripper.REG_TARGET_DIAMETER for r, _ in calls["writes"])
    assert any(r == gripper.REG_GRIP_TYPE for r, _ in calls["writes"])
    assert any(r == gripper.REG_CONTROL for r, _ in calls["writes"])


def test_close_gripper(monkeypatch):
    calls = {}

    def fake_read_registers(reg, count=1):
        return [200]  # simulate min diameter

    def fake_write_register(reg, value):
        calls.setdefault("writes", []).append((reg, value))

    gripper = ThreeFG15Simulator()
    gripper.read_registers = fake_read_registers
    gripper.write_register = fake_write_register

    gripper.close_gripper(force_val=700)

    assert any(r == gripper.REG_TARGET_FORCE for r, _ in calls["writes"])
    assert any(r == gripper.REG_TARGET_DIAMETER for r, _ in calls["writes"])
    assert any(r == gripper.REG_GRIP_TYPE for r, _ in calls["writes"])
    assert any(r == gripper.REG_CONTROL for r, _ in calls["writes"])


def test_flex_grip(monkeypatch):
    calls = {}

    def fake_write_register(reg, value):
        calls.setdefault("writes", []).append((reg, value))

    gripper = ThreeFG15Simulator()
    gripper.write_register = fake_write_register

    gripper.flex_grip(diameter=500, force_val=200, grip_type=GripType.EXTERNAL)

    # Force, Diameter, GripType, Control should be set
    assert any(r == gripper.REG_TARGET_FORCE for r, _ in calls["writes"])
    assert any(r == gripper.REG_TARGET_DIAMETER for r, _ in calls["writes"])
    assert any(r == gripper.REG_GRIP_TYPE for r, _ in calls["writes"])
    # last control command should be CMD_FLEXIBLE_GRIP
    assert calls["writes"][-1][1] == gripper.CMD_FLEXIBLE_GRIP