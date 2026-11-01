# Experimental activation row store

Not connected to mainline RTL or any PDS build set. No synthesis, routing or board evidence.

Run from instrec_fpga:

    python sim/experiments/activation_store/protocol_model.py
    python sim/experiments/activation_store/run.py

Python model passes complete real geometries (H,W,C): (32,129,48), (16,64,96), (8,32,192). RTL Verilator passes small geometry (2,3,48), 10 writes + 10 reads, 288 bytes exact; the preceding C32 version passed 6 writes + 6 reads, 192 bytes.

Producer order is row/group/column/lane. Storage and replay order is row/column/channel. DDR row stride is ceil(W*C/32)*32, with deterministic zero padding. Commands are abstract byte addresses, one 32-byte beat per command. Writes have separate command and data acceptance. R has no ready port: a read command reserves a complete beat in the row RAM; only one command is outstanding. Whole-row credit gates the next row fetch. It must be generated from consumer line-bank ownership, which is not implemented here. Output supports ready and holds data stable when stalled.

One row RAM blocks input while flushing DDR, so producer MUST honor in_ready. The existing pool producer has no ready and cannot be connected directly. No bridge to native ddr3_ctrl_axi, dummy-write protocol, real 37-bit command packing, shared weight arbiter or DDR error recovery is implemented. Native adapter must translate byte addresses consistently and wait for transaction completion at the specified native handshake.

Memory is expressed as 32 independent 8-bit lane banks with synchronous reads and one write per lane/cycle; the read port is shared between DDR output prefetch and canonical replay. This removes the original wide asynchronous RAM read structure but DOES NOT prove physical DRM inference or efficient packing. That requires compile/synthesis after the current unique PDS process finishes. Geometry requires CHANNELS a multiple of 16, HEIGHT/WIDTH positive, 32-byte aligned BASE, and a valid reserved DDR range.

TB checks command/data stalls, delayed R, output stalls, no read before credit, padded row boundary, transaction counts and exact canonical bytes. It does not prove integration, large-geometry RTL, zero-latency R, arbitrary DDR fault response, or repeated inference sequencing.
