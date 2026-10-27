// -----------------------------------------------------------------------------
// hann_rom - 2048 x 16-bit periodic Hann window ROM, Q1.15
//            (tasks.md T-M1-01, design.md Sec. 3.1 stage S1)
// -----------------------------------------------------------------------------
// Synchronous-read ROM: present an address, the data appears on the
// NEXT core_clk edge (1-cycle read latency). Consumers must account
// for this latency when pairing ROM data with their own 1-cycle RAM
// reads (stft_framer aligns both to the same pipeline stage).
//
// Contents: periodic Hann w[k] = 0.5 - 0.5*cos(2*pi*k/2048), identical
// to librosa get_window('hann', 2048, fftbins=True), quantized to
// Q1.15 with round-half-up (peak saturates to 0x7FFF, 1 LSB below 1.0;
// endpoints quantize to 0x0000). Loaded from src/mel/hann_q15.hex
// (2048 lines of 4 hex digits, // comment header supported by
// $readmemh), which is a verbatim extraction of the hann_q15 segment
// of scripts/outputs/mel_tables.coe (bit-identical, verified). The
// .hex file travels with the RTL; the build script must copy or
// reference it so the simulator/synthesis $readmemh search path finds
// it (integration note for T-M0-09 / mel_engine integration).
//
// Resource estimate: 2048 x 16 bit = 32 Kb -> 2 DRM (matches the
// design.md Sec. 10 budget line "hann_rom 2 DRM").
//
// All logic runs in the core_clk (125 MHz) domain.
// -----------------------------------------------------------------------------
module hann_rom #(
    // ROM hex file path (relative to the simulator/synthesis working
    // directory; the build scripts arrange the search path).
    parameter HAN_HEX_FILE = "hann_q15.hex"
) (
    input  wire        clk,       // core_clk 125 MHz
    input  wire [10:0] addr,      // window phase index 0..2047
    output reg  [15:0] q          // Q1.15 coefficient, registered read
);

    // 2048 x 16-bit ROM initialized from the hex image.
    reg [15:0] rom [0:2047];

    initial begin
        q = 16'd0;
        $readmemh(HAN_HEX_FILE, rom);
    end

    always @(posedge clk) begin
        q <= rom[addr];
    end

endmodule