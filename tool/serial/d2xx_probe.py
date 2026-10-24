# -*- coding: utf-8 -*-
"""FTDI D2XX 下载器探针：读芯片型号/序列号，并对 MPSSE(JTAG 引擎) 做自检。
用法：先停掉占用下载器的 cdt_js，再 `python tool/serial/d2xx_probe.py`。
"""
import ctypes as C
from ctypes import wintypes
import sys

DLL = r"C:\Windows\System32\ftd2xx.dll"
try:
    dll = C.WinDLL(DLL)
except OSError as e:
    print("加载 ftd2xx.dll 失败:", e)
    sys.exit(2)

TYPES = {0: "FT_DEVICE_BM", 1: "FT_DEVICE_AM", 2: "FT_DEVICE_100AX", 3: "FT_DEVICE_UNKNOWN",
         4: "FT_DEVICE_2232C", 5: "FT_DEVICE_232R", 6: "FT_DEVICE_2232H", 7: "FT_DEVICE_4232H",
         8: "FT_DEVICE_232H", 9: "FT_DEVICE_X_SERIES", 10: "FT_DEVICE_4222H_0"}


class Node(C.Structure):
    _fields_ = [("Flags", wintypes.DWORD), ("Type", wintypes.DWORD), ("ID", wintypes.DWORD),
                ("LocID", wintypes.DWORD), ("SerialNumber", C.c_char * 16),
                ("Description", C.c_char * 64), ("ftHandle", C.c_void_p)]


num = wintypes.DWORD(0)
dll.FT_CreateDeviceInfoList.argtypes = [C.POINTER(wintypes.DWORD)]
dll.FT_CreateDeviceInfoList.restype = wintypes.DWORD
r = dll.FT_CreateDeviceInfoList(C.byref(num))
print(f"FT_CreateDeviceInfoList -> status={r}  D2XX 可见设备数={num.value}")
if num.value == 0:
    print("没有 D2XX 可见设备（驱动/占用问题）")
    sys.exit(0)

arr = (Node * num.value)()
n = wintypes.DWORD(num.value)
dll.FT_GetDeviceInfoList.argtypes = [C.POINTER(Node), C.POINTER(wintypes.DWORD)]
dll.FT_GetDeviceInfoList.restype = wintypes.DWORD
dll.FT_GetDeviceInfoList(arr, C.byref(n))
for i in range(n.value):
    d = arr[i]
    print(f"[{i}] type={d.Type}({TYPES.get(d.Type, '?')}) id={d.ID:08X} locid={d.LocID:08X} "
          f"serial={d.SerialNumber.decode('latin-1').strip()!r} "
          f"desc={d.Description.decode('latin-1').strip()!r} flags={d.Flags}")

# MPSSE 自检：进入 MPSSE 后发 0xAA（非法命令），正常应回 0xFA
H = wintypes.HANDLE()
dll.FT_Open.argtypes = [wintypes.DWORD, C.POINTER(wintypes.HANDLE)]
dll.FT_Open.restype = wintypes.DWORD
r = dll.FT_Open(0, C.byref(H))
print(f"\nFT_Open(0) -> status={r} handle={H.value}")
if r != 0:
    print("无法打开设备（可能被 cdt_js 占用，请先停掉 cdt_js）")
    sys.exit(0)

dll.FT_SetTimeouts.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD]
dll.FT_SetTimeouts(H, 2000, 2000)
dll.FT_SetUSBParameters.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD]
dll.FT_SetUSBParameters(H, 65536, 65536)
dll.FT_SetLatencyTimer.argtypes = [wintypes.HANDLE, C.c_ubyte]
dll.FT_SetLatencyTimer(H, 16)
dll.FT_SetBitMode.argtypes = [wintypes.HANDLE, C.c_ubyte, C.c_ubyte]
dll.FT_Purge.argtypes = [wintypes.HANDLE, wintypes.DWORD]
dll.FT_Write.argtypes = [wintypes.HANDLE, C.c_void_p, wintypes.DWORD, C.POINTER(wintypes.DWORD)]
dll.FT_Read.argtypes = [wintypes.HANDLE, C.c_void_p, wintypes.DWORD, C.POINTER(wintypes.DWORD)]

dll.FT_SetBitMode(H, 0xFF, 0x00)   # reset
dll.FT_SetBitMode(H, 0x00, 0x02)   # MPSSE
dll.FT_Purge(H, 3)                 # purge rx+tx
w = wintypes.DWORD(0)
buf = C.create_string_buffer(b"\xAA", 1)
st = dll.FT_Write(H, buf, 1, C.byref(w))
rd = wintypes.DWORD(0)
rb = C.create_string_buffer(16)
st2 = dll.FT_Read(H, rb, 16, C.byref(rd))
resp = bytes(rb.raw[:rd.value])
print(f"MPSSE 自检: write status={st} 读回 {rd.value} 字节 = {resp.hex()}")
if resp[:1] == b"\xFA":
    print(">>> 下载器 MPSSE(JTAG 引擎) 正常应答 0xFA  ==> 下载器本身是好的")
elif resp:
    print(">>> 有回包但不是 0xFA（非标准 MPSSE）")
else:
    print(">>> 无回包：MPSSE 未响应（下载器异常）")
dll.FT_Close.argtypes = [wintypes.HANDLE]
dll.FT_Close(H)
