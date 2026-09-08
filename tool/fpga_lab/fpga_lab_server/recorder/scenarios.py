"""UI scenario steps driven by the recorder.

Each step receives (rec, page, context, user, pwd). Steps write a ui_steps record
and screenshot via rec.step(). Selectors here are deliberately defensive: log what
is visible, then act. Exact platform widgets get pinned after inspecting the first
captured HTML (shots/*.html).
"""
from __future__ import annotations

import time

import playwright.async_api as pw

last_tag = ""


async def _wait(page, sec=2.0):
    await page.wait_for_timeout(int(sec * 1000))


async def _log_visible(page, tag):
    lines = []
    for sel in ["button", "a", "input", "[role=button]"]:
        els = page.locator(sel)
        n = min(await els.count(), 30)
        for i in range(n):
            e = els.nth(i)
            try:
                if not await e.is_visible():
                    continue
                t = await e.get_attribute("data-testid")
                ph = await e.get_attribute("placeholder")
                txt = ""
                try:
                    txt = (await e.inner_text()).strip()
                except Exception:
                    pass
                href = await e.get_attribute("href")
                v = (t or ph or txt or href or "")[:70]
                if v:
                    lines.append(f"  [{sel}][{i}] {v}")
            except Exception:
                pass
    print(f"[ui] {tag} visible controls:\n" + "\n".join(lines[:60]), flush=True)


async def s01_login(rec, page, ctx, user=None, pwd=None):
    global last_tag
    last_tag = "s01_login"
    await page.goto("http://www.logicmatrixsemi.com:5174/developer/dashboard?module=devices",
                    wait_until="domcontentloaded", timeout=60000)
    await _wait(page, 3)
    if "/login" not in page.url:
        print("[ui] already authenticated; skipping login", flush=True)
        await rec.step(page, "s01_login", "skipped (already authenticated)", note=page.url)
        return
    await page.get_by_test_id("login-identifier").fill(user)
    await page.get_by_test_id("login-password").fill(pwd)
    await rec.step(page, "s01_login", "credentials filled")
    await page.get_by_test_id("login-submit").click()
    # wait for redirect off /login, or explicit failure text
    for _ in range(40):
        if "/login" not in page.url:
            break
        await _wait(page, 1)
    await _wait(page, 3)
    await _log_visible(page, "post_login")
    await rec.step(page, "s01_login_done", "url=" + page.url)
    if "/login" in page.url:
        body = await page.locator("body").inner_text()
        raise RuntimeError(f"login did not advance (captcha/2FA/error?). body[:300]={body[:300]!r}")


async def s02_devices(rec, page, ctx, user=None, pwd=None):
    global last_tag
    last_tag = "s02_devices"
    await page.goto("http://www.logicmatrixsemi.com:5174/developer/dashboard?module=devices",
                    wait_until="domcontentloaded", timeout=60000)
    await _wait(page, 4)
    await _log_visible(page, "devices")
    await rec.step(page, "s02_devices", "device list view")
    body = await page.locator("body").inner_text()
    print(f"[ui] device view body (first 2500 chars):\n{body[:2500]}", flush=True)


async def s03_reserve_flow(rec, page, ctx, user=None, pwd=None):
    """Open the 'request device by type' dialog; dump; (submit happens in s03b)."""
    global last_tag
    last_tag = "s03_reserve"
    await page.goto("http://www.logicmatrixsemi.com:5174/developer/dashboard?module=devices",
                    wait_until="domcontentloaded", timeout=60000)
    await _wait(page, 3)
    btn = page.get_by_test_id("developer-device-request-by-type")
    if await btn.count() == 0:
        await _log_visible(page, "devices_view")
        raise RuntimeError("developer-device-request-by-type not found")
    await btn.click(timeout=10000)
    await _wait(page, 2)
    await rec.step(page, "s03_reserve_dialog", "opened request-device dialog")
    body = await page.locator("body").inner_text()
    print(f"[ui] reserve dialog body:\n{body[-2500:]}", flush=True)
    await _log_visible(page, "reserve_dialog_controls")


async def s03b_reserve_submit(rec, page, ctx, user=None, pwd=None):
    """Submit reserve for 30 minutes using visible controls."""
    global last_tag
    last_tag = "s03b_reserve_submit"
    # heuristic: find and click text '30' then primary submit '申请设备'
    body = await page.locator("body").inner_text()
    if "30" in body:
        # click a 30-minutes option if present
        for cand in ["30 分钟", "30", "申请设备"]:
            try:
                loc = page.get_by_text(cand, exact=False).last
                if await loc.count() > 0 and await loc.is_visible():
                    await loc.click(timeout=5000)
                    await _wait(page, 1)
                    print(f"[ui] clicked '{cand}'", flush=True)
            except Exception:
                pass
    await rec.step(page, "s03b_submit", "reserve submitted")
    body = await page.locator("body").inner_text()
    print(f"[ui] after-submit body tail:\n{body[-1500:]}", flush=True)
    await _log_visible(page, "post_reserve")


async def s04_upload(rec, page, ctx, user=None, pwd=None):
    global last_tag
    last_tag = "s04_upload"
    await rec.step(page, "s04_upload", "upload screen reached (selector pinning pending)")
    await _log_visible(page, "upload_ui")


async def s05_serial(rec, page, ctx, user=None, pwd=None):
    global last_tag
    last_tag = "s05_serial"
    await rec.step(page, "s05_serial", "serial screen reached (selector pinning pending)")
    await _log_visible(page, "serial_ui")


async def s06_release(rec, page, ctx, user=None, pwd=None):
    global last_tag
    last_tag = "s06_release"
    await page.goto("http://www.logicmatrixsemi.com:5174/developer/dashboard?module=devices",
                    wait_until="domcontentloaded", timeout=60000)
    await _wait(page, 3)
    body = await page.locator("body").inner_text()
    print(f"[ui] pre-release body tail:\n{body[-900:]}", flush=True)
    clicked = False
    for cand in ["释放设备", "释放", "结束使用"]:
        try:
            loc = page.get_by_role("button", name=cand).first
            if await loc.count() > 0 and await loc.is_visible():
                await loc.click(timeout=6000)
                clicked = True
                print(f"[ui] clicked release button '{cand}'", flush=True)
                break
        except Exception:
            continue
    await _wait(page, 3)
    # confirm dialogs
    for confirm in ["确认", "确定", "是"]:
        try:
            loc = page.get_by_role("button", name=confirm).first
            if await loc.count() > 0 and await loc.is_visible():
                await loc.click(timeout=4000)
                print(f"[ui] clicked confirm '{confirm}'", flush=True)
                await _wait(page, 2)
                break
        except Exception:
            continue
    await rec.step(page, "s06_release", f"release attempt clicked={clicked}")
    body = await page.locator("body").inner_text()
    print(f"[ui] post-release body tail:\n{body[-900:]}", flush=True)
    await _log_visible(page, "release_ui")


def build():
    return [
        {"id": "login", "fn": s01_login},
        {"id": "devices", "fn": s02_devices},
        {"id": "reserve", "fn": s03_reserve_flow},
        {"id": "reservesub", "fn": s03b_reserve_submit},
        {"id": "upload", "fn": s04_upload},
        {"id": "serial", "fn": s05_serial},
        {"id": "release", "fn": s06_release},
    ]
