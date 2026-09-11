    wire [16:0] address_low={1'b0,forwarded_a[15:0]}+{1'b0,ex_decode.immediate[15:0]};
    (* syn_keep=1 *) wire [15:0] address_high_zero=forwarded_a[31:16]+ex_decode.immediate[31:16];
    (* syn_keep=1 *) wire [15:0] address_high_one=forwarded_a[31:16]+ex_decode.immediate[31:16]+16'd1;
    wire [31:0] effective_address={address_low[16] ? address_high_one : address_high_zero,address_low[15:0]};

