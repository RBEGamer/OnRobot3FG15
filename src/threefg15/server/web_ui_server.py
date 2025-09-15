#!/usr/bin/env python3
"""
Web API + UI for controlling the gripper via the Modbus TCP server.

Serves:
- HTTP API under /api/* to open/close/move/flex/stop and set HRs
- Static UI at / (index.html + app.js) for interactive control and live status

Depends only on the Python stdlib and pymodbus (already in project).

Run:
  PYTHONPATH=src python -m threefg15.server.web_ui_server \
    --http-host 127.0.0.1 --http-port 8080 \
    --mb-host 127.0.0.1 --mb-port 15020 --unit 1 \
    --config server_config.yaml
"""

import argparse
import json
from http import HTTPStatus
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from typing import Optional

try:
    import yaml  # type: ignore
except Exception:
    yaml = None

from pymodbus.client import ModbusTcpClient


DEFAULT_MAP = {
    'open_coil': 0,
    'close_coil': -1,  # unified OC by default
    'move_coil': -1,
    'flex_coil': -1,
    'stop_coil': -1,
    'status_coil': 2,
    'status_open_coil': 3,
    'status_closed_coil': 4,
    'status_grip_coil': 5,
    'hr_force_index': 0,
    'hr_diameter_index': 1,
    'hr_griptype_index': 2,
    'hr_cmd_index': 3,
    'ir_width_index': 0,
}


class MbClient:
    def __init__(self, host: str, port: int, unit: int, mapping: dict):
        self.host = host
        self.port = port
        self.unit = int(unit)
        self.map = {**DEFAULT_MAP, **(mapping or {})}
        self.client = ModbusTcpClient(host=self.host, port=self.port)
        if not self.client.connect():
            raise SystemExit(f"Could not connect to Modbus server at {host}:{port}")

    # Helpers with slave/unit fallback
    def wr_hr(self, addr: int, val: int):
        try:
            return self.client.write_register(addr, int(val) & 0xFFFF, slave=self.unit)
        except TypeError:
            return self.client.write_register(addr, int(val) & 0xFFFF, unit=self.unit)

    def rd_hr(self, addr: int, count: int = 1):
        try:
            return self.client.read_holding_registers(addr, count=count, slave=self.unit)
        except TypeError:
            return self.client.read_holding_registers(addr, count=count, unit=self.unit)

    def wr_coil(self, addr: int, val: bool):
        try:
            return self.client.write_coil(addr, bool(val), slave=self.unit)
        except TypeError:
            return self.client.write_coil(addr, bool(val), unit=self.unit)

    def rd_coils(self, addr: int, count: int = 1):
        try:
            return self.client.read_coils(addr, count=count, slave=self.unit)
        except TypeError:
            return self.client.read_coils(addr, count=count, unit=self.unit)

    def rd_ir(self, addr: int, count: int = 1):
        try:
            return self.client.read_input_registers(addr, count=count, slave=self.unit)
        except TypeError:
            return self.client.read_input_registers(addr, count=count, unit=self.unit)

    # High-level operations using mapping
    def set_force(self, val: int):
        return self.wr_hr(self.map['hr_force_index'], val)

    def set_diameter(self, val: int):
        return self.wr_hr(self.map['hr_diameter_index'], val)

    def set_griptype(self, val: int):
        return self.wr_hr(self.map['hr_griptype_index'], val)

    def open(self):
        if self.map.get('close_coil', -1) < 0:
            return self.wr_coil(self.map['open_coil'], True)
        return self.wr_coil(self.map['open_coil'], True)

    def close(self):
        if self.map.get('close_coil', -1) < 0:
            return self.wr_coil(self.map['open_coil'], False)
        return self.wr_coil(self.map['close_coil'], True)

    def move(self):
        mc = self.map.get('move_coil', -1)
        if mc is not None and mc >= 0:
            return self.wr_coil(mc, True)
        # Fallback to command register if configured
        ci = self.map.get('hr_cmd_index', -1)
        if ci is None or ci < 0:
            raise RuntimeError("MOVE not available: configure move_coil or hr_cmd_index")
        return self.wr_hr(ci, 1)  # 1 = MOVE

    def flex(self):
        fc = self.map.get('flex_coil', -1)
        if fc is not None and fc >= 0:
            return self.wr_coil(fc, True)
        # Fallback to command register if configured
        ci = self.map.get('hr_cmd_index', -1)
        if ci is None or ci < 0:
            raise RuntimeError("FLEX not available: configure flex_coil or hr_cmd_index")
        return self.wr_hr(ci, 2)  # 2 = FLEX

    def stop(self):
        sc = self.map.get('stop_coil', -1)
        if sc is not None and sc >= 0:
            return self.wr_coil(sc, True)
        ci = self.map.get('hr_cmd_index', -1)
        if ci is None or ci < 0:
            raise RuntimeError("STOP not available: configure stop_coil or hr_cmd_index")
        return self.wr_hr(ci, 3)  # 3 = STOP

    def status(self) -> dict:
        # Coils
        ready = self.rd_coils(self.map['status_coil'], 1)
        is_open = self.rd_coils(self.map['status_open_coil'], 1)
        is_closed = self.rd_coils(self.map['status_closed_coil'], 1)
        gripped = self.rd_coils(self.map['status_grip_coil'], 1)
        # IR width
        width = self.rd_ir(self.map['ir_width_index'], 1)
        # HRs
        force = self.rd_hr(self.map['hr_force_index'], 1)
        diam = self.rd_hr(self.map['hr_diameter_index'], 1)
        gtype = self.rd_hr(self.map['hr_griptype_index'], 1)
        def b(resp):
            return bool(resp.bits[0]) if resp and hasattr(resp, 'bits') else None
        def r(resp):
            return int(resp.registers[0]) if resp and hasattr(resp, 'registers') else None
        return {
            'ready': b(ready),
            'open': b(is_open),
            'closed': b(is_closed),
            'gripped': b(gripped),
            'width_01mm': r(width),
            'force': r(force),
            'diameter_01mm': r(diam),
            'grip_type': r(gtype),
        }


APP_ROOT = Path(__file__).with_name('webui')


class Handler(SimpleHTTPRequestHandler):
    mb: MbClient = None  # type: ignore

    def _send_json(self, code: int, data: dict):
        body = json.dumps(data).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict:
        length = int(self.headers.get('Content-Length', '0'))
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode('utf-8'))
        except Exception:
            return {}

    def do_GET(self):  # noqa: N802
        if self.path == '/' or self.path == '/index.html':
            return self._serve_file(APP_ROOT / 'index.html')
        if self.path == '/static/app.js':
            return self._serve_file(APP_ROOT / 'app.js', 'application/javascript')
        if self.path == '/static/style.css':
            return self._serve_file(APP_ROOT / 'style.css', 'text/css')
        if self.path == '/api/status':
            try:
                st = self.mb.status()
                return self._send_json(HTTPStatus.OK, {'ok': True, 'status': st})
            except Exception as e:
                return self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {'ok': False, 'error': str(e)})
        return self._send_json(HTTPStatus.NOT_FOUND, {'ok': False, 'error': 'Not found'})

    def do_POST(self):  # noqa: N802
        if self.path == '/api/set_force':
            data = self._read_json()
            v = int(data.get('value', 0))
            try:
                self.mb.set_force(v)
                return self._send_json(HTTPStatus.OK, {'ok': True})
            except Exception as e:
                return self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {'ok': False, 'error': str(e)})
        if self.path == '/api/set_diameter':
            data = self._read_json()
            v = int(data.get('value', 0))
            try:
                self.mb.set_diameter(v)
                return self._send_json(HTTPStatus.OK, {'ok': True})
            except Exception as e:
                return self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {'ok': False, 'error': str(e)})
        if self.path == '/api/set_griptype':
            data = self._read_json()
            v = int(data.get('value', 0))
            try:
                self.mb.set_griptype(v)
                return self._send_json(HTTPStatus.OK, {'ok': True})
            except Exception as e:
                return self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {'ok': False, 'error': str(e)})
        if self.path == '/api/open':
            try:
                self.mb.open()
                return self._send_json(HTTPStatus.OK, {'ok': True})
            except Exception as e:
                return self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {'ok': False, 'error': str(e)})
        if self.path == '/api/close':
            try:
                self.mb.close()
                return self._send_json(HTTPStatus.OK, {'ok': True})
            except Exception as e:
                return self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {'ok': False, 'error': str(e)})
        if self.path == '/api/move':
            try:
                self.mb.move()
                return self._send_json(HTTPStatus.OK, {'ok': True})
            except Exception as e:
                return self._send_json(HTTPStatus.BAD_REQUEST, {'ok': False, 'error': str(e)})
        if self.path == '/api/flex':
            try:
                self.mb.flex()
                return self._send_json(HTTPStatus.OK, {'ok': True})
            except Exception as e:
                return self._send_json(HTTPStatus.BAD_REQUEST, {'ok': False, 'error': str(e)})
        if self.path == '/api/stop':
            try:
                self.mb.stop()
                return self._send_json(HTTPStatus.OK, {'ok': True})
            except Exception as e:
                return self._send_json(HTTPStatus.BAD_REQUEST, {'ok': False, 'error': str(e)})
        return self._send_json(HTTPStatus.NOT_FOUND, {'ok': False, 'error': 'Not found'})

    def _serve_file(self, path: Path, content_type: Optional[str] = None):
        if not path.exists():
            return self._send_json(HTTPStatus.NOT_FOUND, {'ok': False, 'error': 'Not found'})
        data = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Content-Type', content_type or 'text/html; charset=utf-8')
        self.end_headers()
        self.wfile.write(data)


def parse_args():
    p = argparse.ArgumentParser(description='Web UI for Modbus gripper server')
    p.add_argument('--http-host', default='127.0.0.1', help='HTTP bind host (default: 127.0.0.1)')
    p.add_argument('--http-port', type=int, default=8080, help='HTTP bind port (default: 8080)')
    p.add_argument('--mb-host', default='127.0.0.1', help='Modbus server host (default: 127.0.0.1)')
    p.add_argument('--mb-port', type=int, default=15020, help='Modbus server port (default: 15020)')
    p.add_argument('--unit', type=int, default=1, help='Modbus unit/slave id (default: 1)')
    p.add_argument('--config', help='Optional YAML config to load mapping (same structure as server_config.yaml)')
    return p.parse_args()


def load_mapping(config_path: Optional[str]) -> dict:
    if not config_path:
        return DEFAULT_MAP.copy()
    path = Path(config_path)
    if not path.exists() or yaml is None:
        return DEFAULT_MAP.copy()
    try:
        cfg = yaml.safe_load(path.read_text()) or {}
        mapping = cfg.get('mapping', {}) if isinstance(cfg, dict) else {}
        return {**DEFAULT_MAP, **(mapping or {})}
    except Exception:
        return DEFAULT_MAP.copy()


def main():
    args = parse_args()
    mapping = load_mapping(args.config)
    mb = MbClient(args.mb_host, args.mb_port, args.unit, mapping)
    Handler.mb = mb
    server = ThreadingHTTPServer((args.http_host, args.http_port), Handler)
    print(f"Web UI: http://{args.http_host}:{args.http_port}  (Modbus {args.mb_host}:{args.mb_port} unit={args.unit})")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down")
    finally:
        try:
            server.server_close()
        except Exception:
            pass


if __name__ == '__main__':
    main()
