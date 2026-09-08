"""FPGA LAB recorder — CDP/Playwright HTTP+WS capture harness.

Drives the real SPA through UI scenarios and records every XHR/fetch request,
response, and WebSocket frame to captures/<run>/ for offline contract authoring.

Run:  python -m fpga_lab_server.recorder --headed [--scenario login] [--run NAME]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import pathlib
import time

from playwright.async_api import async_playwright

HERE = pathlib.Path(__file__).resolve().parents[1]
PROJECT = HERE.parent  # D:/0000/111/001/Pango/tool/fpga_lab
ACCOUNT = PROJECT.parent / "account.txt"
BASE = "http://www.logicmatrixsemi.com:5174"

# resource types we care about for bodies (ignore images/css/fonts/media)
API_RESOURCE_TYPES = {"xhr", "fetch"}


class Recorder:
    def __init__(self, run_dir: pathlib.Path, headed: bool = True):
        self.run_dir = run_dir
        self.shots = run_dir / "shots"
        self.shots.mkdir(parents=True, exist_ok=True)
        self.headed = headed
        self.http_jsonl = open(run_dir / "http_requests.jsonl", "a", encoding="utf-8")
        self.http_body_jsonl = open(run_dir / "http_bodies.jsonl", "a", encoding="utf-8")
        self.ws_jsonl = open(run_dir / "ws_frames.jsonl", "a", encoding="utf-8")
        self.steps_jsonl = open(run_dir / "ui_steps.jsonl", "a", encoding="utf-8")
        self._body_tasks: list[asyncio.Task] = []

    def close(self):
        self.http_jsonl.close()
        self.http_body_jsonl.close()
        self.ws_jsonl.close()
        self.steps_jsonl.close()

    # ---- logging helpers -------------------------------------------------
    def _redact(self, headers: dict) -> dict:
        out = {}
        for k, v in (headers or {}).items():
            kl = k.lower()
            if kl in {"authorization", "cookie", "set-cookie", "x-csrf-token", "proxy-authorization"}:
                out[k] = "<redacted>"
            else:
                out[k] = v
        return out

    def _jl(self, fh, obj: dict):
        fh.write(json.dumps(obj, ensure_ascii=False, default=str) + "\n")
        fh.flush()

    async def step(self, page, tag: str, action: str, note: str = ""):
        info = {"ts": time.time(), "tag": tag, "action": action, "url": page.url, "note": note}
        try:
            info["dom"] = (await page.locator("body").inner_text())[:800]
        except Exception:
            pass
        self._jl(self.steps_jsonl, info)
        try:
            await page.screenshot(path=str(self.shots / f"{tag}.png"))
            (self.shots / f"{tag}.html").write_text(await page.content(), encoding="utf-8")
        except Exception:
            pass
        print(f"[rec] {tag} :: {action} :: {page.url}", flush=True)

    # ---- CDP wiring ------------------------------------------------------
    async def wire(self, context, page):
        async def on_request(req):
            if req.resource_type in API_RESOURCE_TYPES or "/auth/" in req.url or req.url.startswith(BASE):
                self._jl(self.http_jsonl, {
                    "dir": "req", "ts": time.time(), "method": req.method,
                    "url": req.url, "resource_type": req.resource_type,
                    "headers": self._redact(req.headers),
                    "post_data": (req.post_data or "")[:4000],
                })

        async def on_response(resp):
            if resp.request.resource_type in API_RESOURCE_TYPES or "/auth/" in resp.url or resp.url.startswith(BASE):
                self._jl(self.http_jsonl, {
                    "dir": "resp", "ts": time.time(), "status": resp.status,
                    "url": resp.url, "headers": self._redact(resp.headers),
                })
                if resp.request.resource_type in API_RESOURCE_TYPES:
                    self._body_tasks.append(asyncio.create_task(self._save_body(resp)))

        context.on("request", lambda r: asyncio.create_task(on_request(r)))
        context.on("response", lambda r: asyncio.create_task(on_response(r)))

        async def on_ws(ws):
            self._jl(self.ws_jsonl, {"event": "open", "ts": time.time(), "url": ws.url})
            print(f"[rec] WS open: {ws.url}", flush=True)

            async def frame(direction, payload, is_binary):
                if isinstance(payload, bytes):
                    self._jl(self.ws_jsonl, {"event": "frame", "dir": direction,
                                             "ts": time.time(), "url": ws.url,
                                             "binary_hex": payload.hex()[:4000]})
                else:
                    self._jl(self.ws_jsonl, {"event": "frame", "dir": direction,
                                             "ts": time.time(), "url": ws.url,
                                             "text": str(payload)[:4000]})

            ws.on("framesent", lambda p: asyncio.create_task(frame("send", p, isinstance(p, bytes))))
            ws.on("framereceived", lambda p: asyncio.create_task(frame("recv", p, isinstance(p, bytes))))

        page.on("websocket", on_ws)

    async def _save_body(self, resp):
        try:
            body = await resp.body()
            if len(body) <= 200000:
                self._jl(self.http_body_jsonl, {"ts": time.time(), "url": resp.url,
                                                "status": resp.status,
                                                "body_b64": body.decode("utf-8", "replace")[:100000]})
        except Exception:
            pass

    async def finish(self):
        if self._body_tasks:
            await asyncio.gather(*self._body_tasks, return_exceptions=True)


async def run_recorder(headed: bool, scenario_filter: str | None, run_name: str | None,
                       reuse_state: str | None = None) -> int:
    cred = [ln.strip() for ln in ACCOUNT.read_text(encoding="utf-8").splitlines() if ln.strip()]
    if len(cred) != 2:
        print(f"[rec] account file must be 2 lines: {ACCOUNT}")
        return 2
    user, pwd = cred[0], cred[1]

    from fpga_lab_server.recorder import scenarios  # local import to avoid cycle

    run_dir = pathlib.Path(__file__).resolve().parents[2] / "captures"
    run_dir = run_dir / (run_name or time.strftime("run_%Y%m%d_%H%M%S"))
    run_dir.mkdir(parents=True, exist_ok=True)
    rec = Recorder(run_dir, headed=headed)
    print(f"[rec] capture dir: {run_dir}")

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=not headed)
        kw = {"viewport": {"width": 1560, "height": 920}}
        if reuse_state and pathlib.Path(reuse_state).exists():
            kw["storage_state"] = reuse_state
            print(f"[rec] reusing auth state: {reuse_state}")
        ctx = await browser.new_context(**kw)
        page = await ctx.new_page()
        await rec.wire(ctx, page)

        steps = scenarios.build()
        wanted = [s for s in (scenario_filter or "").split(",") if s.strip()]
        try:
            for step in steps:
                if wanted and not any(w in step["id"] for w in wanted):
                    continue
                await step["fn"](rec, page, ctx, user=user, pwd=pwd)
        except Exception as e:  # noqa: BLE001
            await rec.step(page, f"FAIL_{scenarios.last_tag}", f"exception {e!r}")
            print(f"[rec] ABORT at step: {e!r}", flush=True)
            try:
                await page.screenshot(path=str(rec.shots / "abort.png"))
            except Exception:
                pass
            await rec.finish()
            rec.close()
            await browser.close()
            return 1
        await rec.step(page, "s99_finish", "harness teardown")
        await rec.finish()
        # persist browser state for reuse
        (run_dir / "storage_state.json").write_text(
            json.dumps(await ctx.storage_state()), encoding="utf-8")
        rec.close()
        await browser.close()
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--headed", action="store_true", help="show browser (default headless)")
    ap.add_argument("--scenario", default=None, help="run only steps whose id contains this")
    ap.add_argument("--run", default=None, help="custom capture dir name")
    ap.add_argument("--reuse-state", default=None, help="storage_state.json to reuse (skip login)")
    args = ap.parse_args()
    raise SystemExit(asyncio.run(run_recorder(args.headed, args.scenario, args.run, args.reuse_state)))


if __name__ == "__main__":
    main()
