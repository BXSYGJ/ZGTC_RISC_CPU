    li s0, 0x2000
    li t0, 0xe3607173
    li t1, 0x5ffb9efb
    li t2, 0x4e624891
    li a1, 0x74988d47
    li a2, 0x95af883f
    li a3, 0x190909dc
    li a4, 0x0a074efc
    li a5, 0x96942347
    li a6, 0x8087fe28
    li a7, 0x4100fff5
    li s1, 0x99e708e4
    li s2, 0x972b8a76
    li s3, 0x034923e2
    li s4, 0xf8902202
    li s5, 0xc68acc0a
    li s6, 0x0d9e27cc
    blt a1, s4, random_forward_0
    addi s5, a1, 1
random_forward_0:
    slti t2, t1, 1319
    bge t2, s5, random_forward_2
    addi s5, t2, 1
random_forward_2:
    or t1, a2, s2
    andi a5, t2, -379
    sw t0, 228(s0)
    sra s6, s3, a5
    andi a4, a2, 1213
    srai s4, s5, 27
    sub s1, t2, s4
    bltu a5, a7, random_forward_10
    addi s2, a5, 1
random_forward_10:
    sub a6, t1, a2
    bne a1, a3, random_forward_12
    addi s1, a1, 1
random_forward_12:
    lb t2, 103(s0)
    sra a3, t0, s6
    andi t0, a1, 1994
    sb a3, 129(s0)
    bgeu t1, a1, random_forward_17
    addi s5, t1, 1
random_forward_17:
    beq t0, s5, random_forward_18
    addi s5, t0, 1
random_forward_18:
    srl s1, a4, t1
    bltu a3, a3, random_forward_20
    addi s1, a3, 1
random_forward_20:
    sltiu s3, t0, -1581
    srli t2, a3, 25
    bge s4, s6, random_forward_23
    addi a2, s4, 1
random_forward_23:
    srli t1, a7, 3
    srli s3, a6, 0
    srai a1, s4, 30
    andi a5, s5, -400
    lh s3, 214(s0)
    xori a3, a3, -1626
    lhu a7, 84(s0)
    beq s6, t1, random_forward_31
    addi a2, s6, 1
random_forward_31:
    xori a2, a7, 831
    lb a1, 192(s0)
    lh a6, 200(s0)
    sh s2, 154(s0)
    bne a3, s4, random_forward_36
    addi a2, a3, 1
random_forward_36:
    bne a5, s5, random_forward_37
    addi t1, a5, 1
random_forward_37:
    bgeu t0, s4, random_forward_38
    addi s2, t0, 1
random_forward_38:
    xori s5, s3, -554
    sb a6, 71(s0)
    andi a6, a6, -1742
    srli s3, s6, 12
    sh s3, 136(s0)
    andi a1, a1, 538
    sb a7, 51(s0)
    beq a7, s5, random_forward_46
    addi a4, a7, 1
random_forward_46:
    slli a1, a3, 15
    lhu a6, 200(s0)
    blt s6, s3, random_forward_49
    addi s3, s6, 1
random_forward_49:
    sb t0, 138(s0)
    lhu a2, 116(s0)
    or t0, a4, a5
    sb t2, 207(s0)
    addi a4, s1, -319
    srli s3, s6, 15
    lbu s6, 21(s0)
    sw s6, 48(s0)
    sb a6, 103(s0)
    lhu a4, 218(s0)
    srl s1, s5, s4
    ori s4, s3, 1091
    sh a2, 188(s0)
    andi s1, a5, -637
    lb t2, 255(s0)
    bge a6, s1, random_forward_65
    addi t0, a6, 1
random_forward_65:
    and a7, t1, a4
    sw a3, 148(s0)
    lh a3, 210(s0)
    slt s2, t2, a7
    bge s3, a6, random_forward_70
    addi t1, s3, 1
random_forward_70:
    xor s4, s2, s1
    ori a6, s2, 1504
    lhu a2, 96(s0)
    bltu a4, t1, random_forward_74
    addi t2, a4, 1
random_forward_74:
    add t2, s4, t2
    slt s1, t1, t1
    sb a2, 41(s0)
    lhu a5, 70(s0)
    sll s5, s6, a4
    ori s4, t1, 1852
    sb s2, 155(s0)
    lh a4, 34(s0)
    and a3, a5, s2
    andi t0, s5, 426
    lb s5, 165(s0)
    ori s6, s1, -925
    srl a3, a4, a3
    slli a5, a7, 29
    bne t1, s5, random_forward_89
    addi t0, t1, 1
random_forward_89:
    sw a4, 240(s0)
    bltu t1, s3, random_forward_91
    addi s3, t1, 1
random_forward_91:
    andi a2, s6, 1457
    bltu a5, s6, random_forward_93
    addi a5, a5, 1
random_forward_93:
    lbu s6, 93(s0)
    xori t2, t0, 183
    srli a7, t1, 9
    bltu a6, t1, random_forward_97
    addi t2, a6, 1
random_forward_97:
    srai a1, t1, 21
    bgeu s2, s3, random_forward_99
    addi s3, s2, 1
random_forward_99:
    sb s4, 72(s0)
    lhu a4, 66(s0)
    sw a2, 52(s0)
    srl s4, a3, s1
    blt t2, t2, random_forward_104
    addi a1, t2, 1
random_forward_104:
    xori s6, a3, 1467
    lbu t0, 47(s0)
    srli s5, a1, 20
    bge s4, s4, random_forward_108
    addi a4, s4, 1
random_forward_108:
    lw s2, 96(s0)
    sub t2, a2, a4
    and s2, t2, a2
    srli a2, a5, 8
    lbu t1, 70(s0)
    lh t1, 130(s0)
    sltiu a7, t1, 1608
    srl a6, a3, a1
    bltu a2, s1, random_forward_117
    addi s3, a2, 1
random_forward_117:
    sltu a2, s4, a2
    ori t1, a4, 816
    slli s4, s4, 23
    sw t1, 132(s0)
    srai s2, a6, 28
    addi a1, s6, 945
    srli a3, a2, 21
    lb s4, 209(s0)
    bgeu t0, s3, random_forward_126
    addi a2, t0, 1
random_forward_126:
    blt s2, a6, random_forward_127
    addi s1, s2, 1
random_forward_127:
    slti s5, s2, 918
    lw s6, 228(s0)
    slti s4, s4, -192
    blt s4, s4, random_forward_131
    addi a7, s4, 1
random_forward_131:
    bgeu s5, a3, random_forward_132
    addi a6, s5, 1
random_forward_132:
    sub s3, s1, s4
    beq s2, t0, random_forward_134
    addi t2, s2, 1
random_forward_134:
    or t1, s5, a7
    lh a2, 198(s0)
    bgeu a5, t1, random_forward_137
    addi s3, a5, 1
random_forward_137:
    sw s2, 168(s0)
    bltu a6, a1, random_forward_139
    addi s1, a6, 1
random_forward_139:
    sra s3, a3, a6
    xor a1, a3, a1
    addi s1, t0, 16
    andi s2, a7, -283
    addi a7, a2, -874
    sll s1, t1, t0
    and t2, t1, s3
    sb a2, 68(s0)
    and s3, s6, a4
    sw s6, 160(s0)
    bne s1, a1, random_forward_150
    addi t2, s1, 1
random_forward_150:
    slli a2, t1, 29
    bge a6, s5, random_forward_152
    addi a6, a6, 1
random_forward_152:
    sb a2, 153(s0)
    lbu a3, 152(s0)
    slt t1, a6, a3
    bge s3, s1, random_forward_156
    addi s6, s3, 1
random_forward_156:
    lhu a2, 74(s0)
    lh s2, 42(s0)
    lb t0, 213(s0)
    lb t1, 22(s0)
    slli s1, t2, 9
    bltu s3, a5, random_forward_162
    addi s3, s3, 1
random_forward_162:
    lh s4, 126(s0)
    lbu t2, 72(s0)
    sh s1, 240(s0)
    addi s4, a4, 1976
    sh s6, 132(s0)
    slli s3, s4, 25
    xori a3, t2, 252
    sw s5, 80(s0)
    lh a6, 52(s0)
    xor t1, t0, a7
    bge s2, s1, random_forward_173
    addi s3, s2, 1
random_forward_173:
    slli s3, a1, 5
    sll t1, a3, a7
    addi t2, s2, -1455
    lh a2, 218(s0)
    slli a1, t0, 10
    srli s3, s5, 15
    lh t0, 86(s0)
    bge a2, t0, random_forward_181
    addi s2, a2, 1
random_forward_181:
    beq a7, a2, random_forward_182
    addi a3, a7, 1
random_forward_182:
    sh a2, 44(s0)
    blt a1, t1, random_forward_184
    addi s3, a1, 1
random_forward_184:
    slli s5, a3, 18
    srli t1, a3, 17
    and s6, a4, a2
    bne a1, s3, random_forward_188
    addi t1, a1, 1
random_forward_188:
    slli s2, a3, 18
    sll a2, a2, a6
    srli t0, s6, 6
    lh t0, 192(s0)
    slli a4, s5, 20
    srl t0, a5, a1
    bne s4, a2, random_forward_195
    addi s2, s4, 1
random_forward_195:
    and s5, t1, a5
    sb a6, 239(s0)
    lb a5, 30(s0)
    blt s6, s3, random_forward_199
    addi s6, s6, 1
random_forward_199:
    lb s2, 86(s0)
    srai t2, s6, 31
    bltu s1, s2, random_forward_202
    addi s2, s1, 1
random_forward_202:
    slli a6, a7, 10
    srai s5, a5, 9
    sh s3, 192(s0)
    bgeu s2, s1, random_forward_206
    addi s2, s2, 1
random_forward_206:
    ori a5, s1, -1627
    lw s5, 24(s0)
    lw a4, 184(s0)
    xori a1, a6, 1602
    lb s4, 74(s0)
    sll a6, s5, t2
    beq t1, s2, random_forward_213
    addi a2, t1, 1
random_forward_213:
    lb t1, 65(s0)
    bltu a1, s1, random_forward_215
    addi a7, a1, 1
random_forward_215:
    bltu t1, s2, random_forward_216
    addi t0, t1, 1
random_forward_216:
    lhu a7, 192(s0)
    xor t2, a7, s4
    bge a6, s1, random_forward_219
    addi t0, a6, 1
random_forward_219:
    lbu a3, 149(s0)
    bltu a2, a2, random_forward_221
    addi a3, a2, 1
random_forward_221:
    srai s6, a1, 10
    lw t0, 24(s0)
    sh a5, 88(s0)
    lbu a7, 17(s0)
    srli s3, t1, 3
    sll a4, t1, s5
    lhu a3, 124(s0)
    sw s1, 80(s0)
    lbu t1, 251(s0)
    sb s2, 107(s0)
    slli a7, a2, 21
    sh a7, 102(s0)
    sb s1, 181(s0)
    sw t2, 236(s0)
    lb s5, 99(s0)
    slti a6, t1, 1543
    sw a6, 196(s0)
    add s4, a3, a6
    sub s3, s6, t1
    sb s3, 93(s0)
    lb a3, 43(s0)
    slti a5, s6, -483
    lbu t1, 67(s0)
    lbu a5, 222(s0)
    sb t2, 100(s0)
    addi t0, t2, -369
    slli t0, s2, 10
    sw t2, 232(s0)
    bne a3, s2, random_forward_250
    addi s3, a3, 1
random_forward_250:
    slti a5, a6, 1407
    addi t0, a1, 124
    slt s3, a1, s2
    bltu t1, a6, random_forward_254
    addi a6, t1, 1
random_forward_254:
    slli s2, s2, 17
