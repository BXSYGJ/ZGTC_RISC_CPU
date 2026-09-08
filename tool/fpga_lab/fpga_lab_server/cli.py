"""remote-lab CLI — thin wrapper over the fpga-lab-bridge REST/WS API.

Usage examples:
    remote-lab health
    remote-lab devices
    remote-lab reserve --minutes 10
    remote-lab current
    remote-lab bitstream path/to/blink_top.sbit
    remote-lab release
    remote-lab serial-send --hex A5 --timeout 6
"""
from __future__ import annotations

import json
import sys
import time

import click
import httpx

from fpga_lab_server.app import create_app, state
from fpga_lab_server.paths import BASE

BASE_URL = "http://127.0.0.1:8600"


def _client() -> httpx.Client:
    return httpx.Client(base_url=BASE_URL, timeout=600)


def _p(resp: httpx.Response, j: dict | None = None):
    j = j if j is not None else (resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {"text": resp.text})
    click.echo(json.dumps(j, ensure_ascii=False, indent=2, default=str))
    if resp.status_code >= 400:
        sys.exit(1)


@click.group()
def cli():
    """fpga-lab bridge CLI."""


@cli.command("health")
def health():
    r = httpx.get(f"{BASE_URL}/api/v1/health", timeout=10)
    _p(r)


@cli.command()
@click.option("--json-out", "as_json", is_flag=True, help="output raw json array")
def devices(as_json: bool):
    r = httpx.get(f"{BASE_URL}/api/v1/devices", timeout=30)
    if as_json:
        _p(r)
        return
    j = r.json()
    rows = j.get("boxes") or []
    click.echo(f"fetched {len(rows)} boxes")
    for b in rows:
        click.echo(f"  {b['id']:>4}  {b['name']:<20} {b['device'] or '?':<10} "
                   f"{b['status']:<8} {b['hardware_profile'] or ''}")


@cli.command("current")
def current():
    r = httpx.get(f"{BASE_URL}/api/v1/current", timeout=30)
    _p(r)


@cli.command()
@click.option("--minutes", default=10, type=int, help="reservation minutes (platform: up to 30)")
def reserve(minutes: int):
    r = httpx.post(f"{BASE_URL}/api/v1/devices/reserve", json={"minutes": minutes}, timeout=60)
    _p(r)


@cli.command()
def release():
    r = httpx.post(f"{BASE_URL}/api/v1/devices/release", timeout=60)
    _p(r)


@cli.command("bitstream")
@click.argument("sbit", type=click.Path(exists=True, dir_okay=False))
def bitstream(sbit: str):
    """Upload + program the current reserved device with an .sbit file."""
    with open(sbit, "rb") as f:
        r = httpx.post(f"{BASE_URL}/api/v1/bitstream", files={"file": (sbit.split("/")[-1], f)},
                       timeout=600)
    _p(r)


@cli.command("serial-send")
@click.option("--baud", default=115200)
@click.option("--hex", "hex_data", default=None, help="hex bytes to send, e.g. A5")
@click.option("--text", default=None, help="ascii text to send")
@click.option("--timeout", "wait_s", default=6.0, type=float, help="seconds to wait for rx")
def serial_send(baud: int, hex_data: str | None, text: str | None, wait_s: float):
    """Open serial on the current box, send one payload, print received bytes."""
    try:
        from websockets.sync.client import connect
    except Exception:
        click.echo("websockets (sync) not available; run: pip install websockets", err=True)
        sys.exit(2)
    url = f"ws://127.0.0.1:8600/ws/serial?baud={baud}"
    if not hex_data and not text:
        click.echo("provide --hex or --text", err=True)
        sys.exit(2)
    mode, data = ("hex", hex_data) if hex_data else ("text", text)
    seen = []
    try:
        with connect(url, open_timeout=20) as ws:
            deadline = time.time() + wait_s + 10.0
            sent = False
            while True:
                try:
                    m = json.loads(ws.recv(timeout=10))
                except Exception:
                    break
                t = m.get("type")
                if t == "status":
                    if m.get("state") == "connected":
                        click.echo(f"connected box {m.get('box_id')}")
                        if not sent:
                            ws.send(json.dumps({"type": "tx", "mode": mode, "data": data}))
                            sent = True
                    else:
                        click.echo(f"status: {m.get('state')} {m.get('reason')}")
                elif t == "ack":
                    click.echo(f"sent bytes: {m.get('bytesSent')}")
                    if wait_s <= 0.1:
                        break
                elif t == "rx":
                    seen.append((m.get("hex"), m.get("data_text")))
                    click.echo(f"rx hex={m.get('hex')} text={m.get('data_text')!r}")
                elif t == "diagnostic":
                    click.echo(f"diag: {m.get('message')}")
                if time.time() > deadline:
                    break
            try:
                ws.send(json.dumps({"type": "close"}))
            except Exception:
                pass
    except Exception as e:
        click.echo(f"serial error: {e}", err=True)
        sys.exit(1)
    if not seen:
        click.echo("no rx data received")


@cli.command("serve")
def serve():
    """Run the bridge server in this process (Ctrl-C to stop)."""
    app = create_app()
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8600, log_level="info")


if __name__ == "__main__":
    cli()
