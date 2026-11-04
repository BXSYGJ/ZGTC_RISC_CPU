`timescale 1ns/10fs

module pll (

    output wire clkout0,

    output wire clkout1,

    input wire clkin1,

    output wire lock
    );

    localparam real    CLKIN_FREQ       = 27.0;

    localparam         LOCK_MODE        = 0;

    localparam integer STATIC_RATIOI    = 1;

    localparam integer STATIC_RATIOM    = 2;

    localparam real    STATIC_RATIO0    = 7.0;

    localparam integer STATIC_RATIO1    = 100;

    localparam integer STATIC_RATIO2    = 104;

    localparam integer STATIC_RATIO3    = 21;

    localparam integer STATIC_RATIO4    = 21;

    localparam integer STATIC_RATIO5    = 21;

    localparam integer STATIC_RATIO6    = 21;

    localparam real    STATIC_RATIOF    = 19.25;

    localparam integer STATIC_RATIOPHY  = 36;

    localparam integer STATIC_DUTY0     = 7;

    localparam integer STATIC_DUTY1     = 100;

    localparam integer STATIC_DUTY2     = 104;

    localparam integer STATIC_DUTY3     = 21;

    localparam integer STATIC_DUTY4     = 21;

    localparam integer STATIC_DUTY5     = 21;

    localparam integer STATIC_DUTY6     = 21;

    localparam integer STATIC_DUTYF     = 19;

    localparam integer STATIC_DUTYPHY   = 2;

    localparam integer STATIC_PHASE     = 0;

    localparam integer STATIC_PHASE0    = 0;

    localparam integer STATIC_PHASE1    = 0;

    localparam integer STATIC_PHASE2    = 0;

    localparam integer STATIC_PHASE3    = 0;

    localparam integer STATIC_PHASE4    = 0;

    localparam integer STATIC_PHASE5    = 0;

    localparam integer STATIC_PHASE6    = 0;

    localparam integer STATIC_PHASEF    = 0;

    localparam integer STATIC_PHASEPHY  = 0;

    localparam integer STATIC_CPHASE0   = 0;

    localparam integer STATIC_CPHASE1   = 0;

    localparam integer STATIC_CPHASE2   = 0;

    localparam integer STATIC_CPHASE3   = 0;

    localparam integer STATIC_CPHASE4   = 0;

    localparam integer STATIC_CPHASE5   = 0;

    localparam integer STATIC_CPHASE6   = 0;

    localparam integer STATIC_CPHASEF   = 0;

    localparam integer STATIC_CPHASEPHY = 0;

    localparam         CLK_DPS0_EN      = "FALSE";

    localparam         CLK_DPS1_EN      = "FALSE";

    localparam         CLK_DPS2_EN      = "FALSE";

    localparam         CLK_DPS3_EN      = "FALSE";

    localparam         CLK_DPS4_EN      = "FALSE";

    localparam         CLK_DPS5_EN      = "FALSE";

    localparam         CLK_DPS6_EN      = "FALSE";

    localparam         CLK_DPSF_EN      = "FALSE";

    localparam         CLK_CAS5_EN      = "FALSE";

    localparam         CLKOUT0_SYN_EN   = "FALSE";

    localparam         CLKOUT1_SYN_EN   = "FALSE";

    localparam         CLKOUT2_SYN_EN   = "FALSE";

    localparam         CLKOUT3_SYN_EN   = "FALSE";

    localparam         CLKOUT4_SYN_EN   = "FALSE";

    localparam         CLKOUT5_SYN_EN   = "FALSE";

    localparam         CLKOUT6_SYN_EN   = "FALSE";

    localparam         CLKOUTF_SYN_EN   = "FALSE";

    localparam         CLKOUTPHY_SYN_EN = "FALSE";

    localparam         SSC_MODE         = "DISABLE";

    localparam real    SSC_FREQ         = 25;

    localparam         INTERNAL_FB      = "CLKOUTF";

    localparam         EXTERNAL_FB      = "DISABLE";

    localparam         BANDWIDTH        = "OPTIMIZED";

    wire clkin2;
    assign clkin2 = 1'b0;

    wire clkfb;
    assign clkfb = 1'b0;

    wire clkin_sel;
    assign clkin_sel = 1'b0;

    wire dps_clk;
    wire dps_en;
    wire dps_dir;
    assign dps_clk = 1'b0;
    assign dps_en = 1'b0;
    assign dps_dir = 1'b0;

    wire clkout0_syn;
    assign clkout0_syn = 1'b0;

    wire clkout1_syn;
    assign clkout1_syn = 1'b0;

    wire clkout2_syn;
    assign clkout2_syn = 1'b0;

    wire clkout3_syn;
    assign clkout3_syn = 1'b0;

    wire clkout4_syn;
    assign clkout4_syn = 1'b0;

    wire clkout5_syn;
    assign clkout5_syn = 1'b0;

    wire clkout6_syn;
    assign clkout6_syn = 1'b0;

    wire clkoutf_syn;
    assign clkoutf_syn = 1'b0;

    wire pll_pwd;
    assign pll_pwd = 1'b0;

    wire rst;
    assign rst = 1'b0;

    wire apb_clk;
    wire apb_rst_n;
    wire [4:0] apb_addr;
    wire apb_sel;
    wire apb_en;
    wire apb_write;
    wire [15:0] apb_wdata;

    assign apb_clk = 1'd0;
    assign apb_rst_n = 1'd0;
    assign apb_addr [4:0] = 5'd0;
    assign apb_sel = 1'd0;
    assign apb_en = 1'd0;
    assign apb_write = 1'd0;
    assign apb_wdata [15:0] = 16'd0;

    GTP_GPLL #(

    .CLKIN_FREQ      (CLKIN_FREQ    ),
    .LOCK_MODE       (LOCK_MODE     ),
    .STATIC_RATIOI   (STATIC_RATIOI ),
    .STATIC_RATIOM   (STATIC_RATIOM ),

    .STATIC_RATIO0   (STATIC_RATIO0 ),
    .STATIC_RATIO1   (STATIC_RATIO1 ),
    .STATIC_RATIO2   (STATIC_RATIO2 ),
    .STATIC_RATIO3   (STATIC_RATIO3 ),
    .STATIC_RATIO4   (STATIC_RATIO4 ),

    .STATIC_RATIO5   (STATIC_RATIO5 ),
    .STATIC_RATIO6   (STATIC_RATIO6 ),

    .STATIC_RATIOF   (STATIC_RATIOF ),

    .STATIC_DUTY0    (STATIC_DUTY0  ),
    .STATIC_DUTY1    (STATIC_DUTY1  ),
    .STATIC_DUTY2    (STATIC_DUTY2  ),
    .STATIC_DUTY3    (STATIC_DUTY3  ),
    .STATIC_DUTY4    (STATIC_DUTY4  ),

    .STATIC_DUTY5    (STATIC_DUTY5  ),
    .STATIC_DUTY6    (STATIC_DUTY6  ),

    .STATIC_DUTYF    (STATIC_DUTYF  ),

    .STATIC_PHASE    (STATIC_PHASE  ),

    .STATIC_PHASE0   (STATIC_PHASE0 ),
    .STATIC_PHASE1   (STATIC_PHASE1 ),
    .STATIC_PHASE2   (STATIC_PHASE2 ),
    .STATIC_PHASE3   (STATIC_PHASE3 ),
    .STATIC_PHASE4   (STATIC_PHASE4 ),

    .STATIC_PHASE5   (STATIC_PHASE5 ),
    .STATIC_PHASE6   (STATIC_PHASE6 ),

    .STATIC_PHASEF   (STATIC_PHASEF ),

    .STATIC_CPHASE0  (STATIC_CPHASE0),
    .STATIC_CPHASE1  (STATIC_CPHASE1),
    .STATIC_CPHASE2  (STATIC_CPHASE2),
    .STATIC_CPHASE3  (STATIC_CPHASE3),
    .STATIC_CPHASE4  (STATIC_CPHASE4),

    .STATIC_CPHASE5  (STATIC_CPHASE5),
    .STATIC_CPHASE6  (STATIC_CPHASE6),

    .STATIC_CPHASEF  (STATIC_CPHASEF),

    .CLK_DPS0_EN     (CLK_DPS0_EN   ),
    .CLK_DPS1_EN     (CLK_DPS1_EN   ),
    .CLK_DPS2_EN     (CLK_DPS2_EN   ),
    .CLK_DPS3_EN     (CLK_DPS3_EN   ),
    .CLK_DPS4_EN     (CLK_DPS4_EN   ),
    .CLK_DPS5_EN     (CLK_DPS5_EN   ),
    .CLK_DPS6_EN     (CLK_DPS6_EN   ),
    .CLK_DPSF_EN     (CLK_DPSF_EN   ),
    .CLK_CAS5_EN     (CLK_CAS5_EN   ),

    .CLKOUT0_SYN_EN  (CLKOUT0_SYN_EN),
    .CLKOUT1_SYN_EN  (CLKOUT1_SYN_EN),
    .CLKOUT2_SYN_EN  (CLKOUT2_SYN_EN),
    .CLKOUT3_SYN_EN  (CLKOUT3_SYN_EN),
    .CLKOUT4_SYN_EN  (CLKOUT4_SYN_EN),

    .CLKOUT5_SYN_EN  (CLKOUT5_SYN_EN),
    .CLKOUT6_SYN_EN  (CLKOUT6_SYN_EN),

    .CLKOUTF_SYN_EN  (CLKOUTF_SYN_EN),

    .SSC_MODE       (SSC_MODE       ),
    .SSC_FREQ       (SSC_FREQ       ),

    .INTERNAL_FB    (INTERNAL_FB    ),
    .EXTERNAL_FB    (EXTERNAL_FB    ),
    .BANDWIDTH      (BANDWIDTH      )

    ) u_gpll (

    .CLKOUT0        (clkout0        ),

    .CLKOUT0N       (               ),

    .CLKOUT1        (clkout1        ),

    .CLKOUT1N       (               ),

    .CLKOUT2        (               ),

    .CLKOUT2N       (               ),

    .CLKOUT3        (               ),

    .CLKOUT3N       (               ),

    .CLKOUT4        (               ),

    .CLKOUT5        (               ),

    .CLKOUT6        (               ),

    .CLKOUTF        (               ),

    .CLKOUTFN       (               ),

    .LOCK           (lock           ),

    .DPS_DONE       (               ),

    .DPS_CLK        (dps_clk        ),
    .DPS_EN         (dps_en         ),
    .DPS_DIR        (dps_dir        ),

    .CLKIN1         (clkin1         ),

    .CLKIN2         (clkin2         ),

    .CLKFB          (clkfb          ),
    .CLKIN_SEL      (clkin_sel      ),
    .CLKOUT0_SYN    (clkout0_syn    ),
    .CLKOUT1_SYN    (clkout1_syn    ),
    .CLKOUT2_SYN    (clkout2_syn    ),
    .CLKOUT3_SYN    (clkout3_syn    ),
    .CLKOUT4_SYN    (clkout4_syn    ),

    .CLKOUT5_SYN    (clkout5_syn    ),
    .CLKOUT6_SYN    (clkout6_syn    ),

    .CLKOUTF_SYN    (clkoutf_syn    ),
    .PLL_PWD        (pll_pwd        ),
    .RST            (rst            ),

    .APB_RDATA      (               ),
    .APB_READY      (               ),

    .APB_CLK        (apb_clk        ),
    .APB_RST_N      (apb_rst_n      ),
    .APB_ADDR       (apb_addr[4:0]  ),
    .APB_SEL        (apb_sel        ),
    .APB_EN         (apb_en         ),
    .APB_WRITE      (apb_write      ),
    .APB_WDATA      (apb_wdata[15:0])
);

endmodule
