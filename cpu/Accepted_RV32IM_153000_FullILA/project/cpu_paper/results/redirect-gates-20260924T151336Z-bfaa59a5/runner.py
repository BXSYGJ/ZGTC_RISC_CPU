"""Run frontend transaction tests and independently checked architecture programs."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
from uuid import uuid4
import run_embench as h
from create_redirect_optimization import replace_once
from run_priming_directed_tests import adapted_bench
from redirect_speculative_overlap_tests import adapt as adapt_speculative_overlap, INVARIANTS as SPECULATIVE_OVERLAP_INVARIANTS
from redirect_prediction_mismatch_tests import adapt as adapt_prediction_mismatch


REQUEST_ADDRESS_INVARIANTS = r'''
`ifdef REQUEST_ADDRESS_FACTORING
    // Miter against the unmodified parent's address selection on all valid
    // requests, including requests stalled by the cache. Invalid addresses are
    // intentionally not constrained by the bus contract.
    wire [31:0] parent_request_address=core.redirect_launch ? core.redirect_pc :
        core.fetch_sent ? (core.fetch_late_prediction ? core.fetch_prediction_now : core.next_pc) : core.fetch_address;
    always @(posedge clk) if(rst_n && core.i_req_valid)
        if(core.i_req_address !== parent_request_address)
            $fatal(1,"Valid request address differs from parent selection");
`endif
'''

COMPARE_INVARIANTS = r'''
    // Independent checks of live operand metadata, including stalls and interrupts.
    always @(posedge clk) if(rst_n) begin
        if(!core.frontend_flush && !core.frontend_barrier)
            if((core.id_valid && core.ex_ready)!==core.id_fire)
                $fatal(1,"ID lookahead differs without a squash");
        if(core.ex_valid) begin
            for(integer cb=0;cb<4;cb=cb+1) begin
                if(core.wb_a_byte_equal[cb] !== (core.ex_operand_a[cb*8+:8]==core.wb_data[cb*8+:8]) ||
                   core.wb_a_byte_less[cb] !== (core.ex_operand_a[cb*8+:8]<core.wb_data[cb*8+:8]) ||
                   core.wb_b_byte_equal[cb] !== (core.wb_data[cb*8+:8]==core.ex_operand_b[cb*8+:8]) ||
                   core.wb_b_byte_less[cb] !== (core.wb_data[cb*8+:8]<core.ex_operand_b[cb*8+:8]))
                    $fatal(1,"Live EX WB comparison metadata differs from operands");
            end
        end
    end
'''

RECOVERY_INVARIANTS = r'''
`ifdef REGISTERED_PREDICTION_MISMATCH
    always @(posedge clk) if(rst_n && core.ex_valid) begin
        if(core.ex_taken_prediction_mismatch !== (core.ex_relative_target!=core.ex_prediction) ||
           core.ex_fallthrough_prediction_mismatch !== ((core.ex_pc+32'd4)!=core.ex_prediction))
            $fatal(1,"Registered mismatch differs from live EX PC/target/prediction");
        if(core.raw_redirect_prediction_mismatch !== (core.raw_redirect_next!=core.ex_prediction))
            $fatal(1,"Selected mismatch differs from parent 32-bit comparison");
    end
`endif
`ifdef RAW_LAUNCH_FACTORED
    always @(posedge clk) if(rst_n) begin
        if(core.raw_redirect_event && !core.fetch_accept_space)
            $fatal(1,"Raw EX redirect no longer implies response space");
        if(core.redirect_launch !== (core.raw_redirect_event && !core.frontend_barrier &&
                (!core.fetch_active || core.fetch_complete)))
            $fatal(1,"Factored raw launch differs from parent eligibility");
    end
`endif
`ifdef RESPONSE_READY_FACTORED
    // Compare with the parent's full expression, including real MEM/EX priority.
    always @(posedge clk) if(rst_n) begin
        if(core.ex_redirect && !core.ex_fire)
            $fatal(1,"EX redirect no longer implies EX admission");
        if(core.i_rsp_ready !== (core.fetch_active && core.fetch_sent &&
                (core.fetch_accept_space || core.frontend_flush || core.frontend_barrier)))
            $fatal(1,"Factored instruction response readiness differs from parent");
    end
`endif
`ifdef RAW_OPERAND_RECOVERY
    // The original architectural redirect decision uses the complete forwarded
    // operand network. Compare the restricted shortcut against that reference.
    always @(posedge clk) if(rst_n) begin
        if(core.raw_redirect_event !== (core.ex_redirect &&
                (core.ex_decode.is_jal || core.raw_redirect_operands)))
            $fatal(1,"Raw-operand request decision differs from architectural redirect subset");
        if(core.raw_redirect_event && (core.mem_flush || core.raw_redirect_next!==core.early_next))
            $fatal(1,"Raw-operand request lost MEM priority or resolved target");
    end
`endif
`ifdef WB_MATCH
    always @(posedge clk) if(rst_n && core.ex_valid && core.wb_valid) begin
        if(core.wb_match_a !== (core.ex_instruction[19:15]==core.wb_rd) ||
           core.wb_match_b !== (core.ex_instruction[24:20]==core.wb_rd))
            $fatal(1,"Registered WB match differs from live architectural registers");
    end
`endif
`ifdef DIRECT_MEM_COMPARE
    reg previous_ex_admission;
    reg [31:0] previous_execute_result;
    always @(posedge clk) begin
        if(!rst_n) begin previous_ex_admission<=0; previous_execute_result<=0; end
        else begin
            if(core.early_mem_forward && (!previous_ex_admission || core.mem_result!==previous_execute_result))
                $fatal(1,"Live MEM forward did not follow an EX result admission");
            previous_ex_admission<=core.ex_fire && !core.mem_flush;
            previous_execute_result<=core.execute_result;
        end
    end
`endif
`ifdef MEM_COMPARE
    always @(posedge clk) if(rst_n && core.ex_valid && core.early_mem_forward) begin
        if(core.early_pair_result[1] !== {core.mem_result==core.ex_operand_b,
                core.mem_result<core.ex_operand_b,$signed(core.mem_result)<$signed(core.ex_operand_b)})
            $fatal(1,"Live MEM-to-EX comparison differs from direct operand relation");
        if(core.early_pair_result[3] !== {core.ex_operand_a==core.mem_result,
                core.ex_operand_a<core.mem_result,$signed(core.ex_operand_a)<$signed(core.mem_result)})
            $fatal(1,"Live EX-to-MEM comparison differs from direct operand relation");
        if(core.early_pair_result[5] !== {core.mem_result==core.wb_data,
                core.mem_result<core.wb_data,$signed(core.mem_result)<$signed(core.wb_data)})
            $fatal(1,"Live MEM-to-WB comparison differs from direct operand relation");
    end
`endif
`ifdef PRECOMPUTED_RECOVERY
    always @(posedge clk) if(rst_n) begin
        if(core.ex_valid) begin
            if(core.ex_recovery_known !== (core.ex_decode.is_jal || core.ex_prediction==core.ex_pc+32'd4 || core.ex_prediction==core.ex_relative_target))
                $fatal(1,"Recovery classification does not match live EX prediction");
            if(core.ex_recovery_relative !== (core.ex_decode.is_jal || core.ex_prediction==core.ex_pc+32'd4))
                $fatal(1,"Recovery selection does not match live EX prediction");
        end
        if(core.redirect_launch && core.i_req_address !== core.redirect_pc)
            $fatal(1,"Early recovery request differs from resolved architectural PC");
    end
`endif
'''

BUFFER_LOOKUP_INVARIANTS = r'''
`ifdef HYBRID_BUFFER
    always @(posedge clk) if(rst_n) begin
        if(core.redirect_launch && (core.target_buffer_hit || core.i_req_address !== core.redirect_pc))
            $fatal(1,"Hybrid miss request conflicts with buffer hit or resolved PC");
        if(core.frontend_flush && !core.frontend_barrier && (!core.fetch_active || core.fetch_complete) &&
                core.target_buffer_hit && core.i_req_valid)
            $fatal(1,"Hybrid buffer hit issued a redundant external request");
    end
`endif
`ifdef FAST_BUFFER
    always @(posedge clk) if(rst_n && core.target_prediction_pending) begin
`ifdef BUFFER_DRAIN
        if((core.fetch_active || core.fetch_sent) && !core.buffer_drain_pending)
            $fatal(1,"Buffered target pending without tracked old transaction");
        if(core.buffer_drain_pending && (!core.fetch_active || !core.fetch_discard || core.target_successor_launch))
            $fatal(1,"Buffered drain lost old transaction or issued successor early");
        if((core.frontend_flush || core.frontend_barrier) && core.i_req_valid &&
                !(core.fetch_active && !core.fetch_sent))
            $fatal(1,"Squashed buffered successor issued an external request");
`else
        if(core.fetch_active || core.fetch_sent)
            $fatal(1,"Buffered target pending with an outstanding fetch");
        if((core.frontend_flush || core.frontend_barrier) && core.i_req_valid)
            $fatal(1,"Buffered successor requested while squashed");
`endif
    end
`endif
`ifdef BUFFER_DRAIN
    reg drain_hold_expected;
    reg [31:0] drain_old_address;
    always @(posedge clk) begin
        if(!rst_n) begin drain_hold_expected<=0; drain_old_address<=0; end
        else begin
            if(drain_hold_expected && (!core.fetch_active || !core.fetch_discard || core.fetch_address!==drain_old_address))
                $fatal(1,"Cached target cancelled or changed an old external transaction");
            if(core.buffer_drain_pending && (!core.fetch_active || !core.fetch_discard))
                $fatal(1,"Pending buffer drain lacks an outstanding discarded fetch");
            if(core.buffer_drain_pending && !core.fetch_sent &&
                    (!core.i_req_valid || core.i_req_address!==core.fetch_address))
                $fatal(1,"Buffered target changed a stalled old request");
            drain_hold_expected<=core.buffer_drain_pending && !core.fetch_complete;
            drain_old_address<=core.fetch_address;
        end
    end
`endif
`ifdef PRECOMPUTED_BUFFER
    always @(posedge clk) if(rst_n) begin
        if(core.ex_valid) begin
            if(core.ex_recovery_known !== (core.ex_decode.is_jal || core.ex_prediction==core.ex_pc+32'd4 || core.ex_prediction==core.ex_relative_target))
                $fatal(1,"Buffer lookup classification differs from live prediction");
            if(core.ex_recovery_relative !== (core.ex_decode.is_jal || core.ex_prediction==core.ex_pc+32'd4))
                $fatal(1,"Buffer lookup selection differs from live prediction");
        end
        if(core.frontend_flush && (core.mem_flush || core.ex_recovery_known) && core.target_lookup_pc!==core.redirect_pc)
            $fatal(1,"Buffered instruction lookup differs from resolved PC");
    end
`endif
'''

BUFFER_LOOKUP_TASK = r'''
    reg buffer_mem_mode=1;
    wire buffer_mem_flush=flush && buffer_mem_mode;
    task automatic buffer_lookup_addresses;
        begin
            for(integer known=0;known<2;known=known+1)
                for(integer relative_pc=0;relative_pc<2;relative_pc=relative_pc+1) begin
                    buffer_mem_mode=1; reset_core();
                    flush=1; redirect=32'h100; step(); check_primed(32'h100);
                    accept_primed(32'h100,0,0); request_ready=1; step();
                    buffer_mem_mode=0;
                    dut.ex_recovery_known=known; dut.ex_recovery_relative=relative_pc;
                    dut.ex_pc=32'hfc; dut.ex_relative_target=32'h100;
                    response_valid=1; flush=1; redirect=32'h100; step();
                    flush=0; response_valid=0; request_ready=0; #1;
                    if(known)
                        check(dut.if_valid && dut.if_pc===32'h100 && dut.if_instruction===32'h00000013 && !dut.fetch_active,"recognized EX lookup missed cached instruction");
                    else begin
                        check(!dut.if_valid,"unrecognized prediction bypassed fallback");
                        check_primed(32'h100); accept_primed(32'h100,0,0);
                    end
                end
            buffer_mem_mode=1;
        end
    endtask
'''

MEM_LOOKUP_TASK = r'''
    reg [11:0] lookup_flags=0;
    wire lookup_valid=lookup_flags[0],lookup_load=lookup_flags[1],lookup_store=lookup_flags[2];
    wire lookup_sent=lookup_flags[3],lookup_exception=lookup_flags[4],lookup_mret=lookup_flags[5];
    wire lookup_fence=lookup_flags[6],lookup_early=lookup_flags[7];
    wire lookup_rsp_valid=lookup_flags[9],lookup_rsp_error=lookup_flags[10],lookup_maintenance=lookup_flags[11];
    wire [31:0] lookup_prediction=lookup_flags[8] ? 32'h504 : 32'h500;
    task automatic mem_lookup_boundary;
        reg expected_access,expected_fire,expected_fault,expected_flush;
        begin
            // End-of-test combinational boundary sweep with controlled MEM inputs;
            // no clock edges or architectural execution occur during this sweep.
            // Stale error without response, FENCE waiting, early-resolved branches,
            // traps and MRET are included in all 4096 flag combinations.
            release dut.mem_flush; release dut.mem_fault; release dut.redirect_pc;
            force dut.mem_valid=lookup_valid;
            force dut.mem_load=lookup_load; force dut.mem_store=lookup_store;
            force dut.mem_sent=lookup_sent; force dut.mem_exception=lookup_exception;
            force dut.mem_mret=lookup_mret; force dut.mem_fence_i=lookup_fence;
            force dut.mem_early_redirect=lookup_early;
            force dut.mem_next_pc=32'h500; force dut.mem_prediction=lookup_prediction;
            force dut.d_rsp_valid=lookup_rsp_valid; force dut.d_rsp_error=lookup_rsp_error;
            force dut.maintenance_ready=lookup_maintenance;
            force dut.trap_target=32'h200;
            force dut.ex_recovery_relative=1'b1; force dut.ex_relative_target=32'h100;
            for(integer flags=0;flags<4096;flags=flags+1) begin
                lookup_flags=flags; #1;
                expected_access=(lookup_flags[1] || lookup_flags[2]) && !lookup_flags[4];
                expected_fire=lookup_flags[0] && (expected_access ?
                    (lookup_flags[3] && lookup_flags[9]) :
                    (!lookup_flags[6] || lookup_flags[4] || lookup_flags[11]));
                expected_fault=lookup_flags[4] || (expected_access && lookup_flags[3] && lookup_flags[9] && lookup_flags[10]);
                expected_flush=expected_fire && (expected_fault || lookup_flags[5] || lookup_flags[6] ||
                    (!lookup_flags[7] && lookup_flags[8]));
                check(dut.mem_flush===expected_flush,"MEM redirect boundary differs from independent expectation");
                if(expected_flush)
                    check(dut.target_lookup_pc===(expected_fault ? 32'h200 : 32'h500),"speculative MEM lookup wrong on consumption");
                if((!lookup_flags[0] || expected_fire) && !expected_flush)
                    check(dut.target_lookup_pc===32'h100,"completed nonredirecting MEM suppressed younger EX lookup");
            end
        end
    endtask
'''

SEQUENTIAL_TARGET_TASK = r'''
    task automatic sequential_target_stall;
        reg [31:0] saved_prediction;
        begin
            reset_core(); prediction_taken=1; request_ready=1;
            flush=1; redirect=32'h100; step(); flush=0; request_ready=0;
            for(integer wait_cycle=0;wait_cycle<5;wait_cycle=wait_cycle+1) begin
                step();
                check(dut.fetch_sent && dut.fetch_address===32'h100 && !dut.if_valid,"early target changed while response delayed");
            end
            saved_prediction=prediction(32'h104);
            response_valid=1; step(); response_valid=0; #1;
            check(dut.if_valid && dut.if_pc===32'h100 && dut.if_prediction===32'h104,"target did not predict sequential successor");
            check(dut.fetch_prediction===saved_prediction && !dut.fetch_redirect_pending && !dut.fetch_late_prediction,"successor prediction not captured before stall");
            for(integer delay=0;delay<7;delay=delay+1) begin
                prediction_taken=delay[0]; step();
                check(dut.i_req_valid && dut.i_req_address===32'h104 && !dut.fetch_sent,"unaccepted successor address changed");
                check(dut.fetch_prediction===saved_prediction,"stalled successor prediction changed with BTB output");
            end
            request_ready=1; step(); request_ready=0; response_valid=1; step();
            check(dut.if_valid && dut.if_pc===32'h104 && dut.if_prediction===saved_prediction,"successor response lost its prediction");
            response_valid=0;
        end
    endtask
'''

RECOVERY_TASK = r'''
    reg recovery_mem_mode=1;
    wire recovery_mem_flush=flush && recovery_mem_mode;
    task automatic recovery_addresses;
        begin
            for(integer known=0;known<2;known=known+1)
                for(integer relative_pc=0;relative_pc<2;relative_pc=relative_pc+1) begin
                    reset_core();
                    recovery_mem_mode=0;
                    dut.ex_recovery_known=known;
                    dut.ex_recovery_relative=relative_pc;
                    dut.ex_pc=32'h80; dut.ex_relative_target=32'h100;
                    redirect=relative_pc ? 32'h100 : 32'h84;
                    flush=1; request_ready=1; #1;
                    if(known) begin
                        check(dut.i_req_valid && dut.i_req_address===redirect,"preselected recovery address");
                        step(); finish_early(redirect,0);
                    end else begin
                        check(!dut.i_req_valid,$sformatf("unknown prediction bypassed fallback active=%b sent=%b known=%b mem_flush=%b launch=%b",dut.fetch_active,dut.fetch_sent,dut.ex_recovery_known,dut.mem_flush,dut.redirect_launch));
                        step(); request_ready=0;
                        check_primed(redirect); accept_primed(redirect,0,0);
                    end
                end
            recovery_mem_mode=1;
        end
    endtask
'''

FAST_BUFFER_TASK = r'''
    task automatic buffered_successor(input integer taken,input integer stalled,input integer chained);
        reg [31:0] address,expected;
        begin
            reset_core(); prediction_taken=taken;
            flush=1; redirect=32'h100; step(); check_primed(32'h100);
            accept_primed(32'h100,0,0);
            request_ready=1; step();
            response_valid=1; flush=1; redirect=32'h100; step();
            flush=0; response_valid=0; request_ready=!stalled;
            address=prediction(32'h100); #1;
            check(dut.if_valid && dut.if_pc===32'h100 && !dut.fetch_active,"missing buffered target");
            check(dut.i_req_valid && dut.i_req_address===address && !dut.i_rsp_ready,"buffer successor not launched on fresh prediction");
            step();
            check(dut.id_valid && dut.id_pc===32'h100 && dut.id_prediction===address,"buffered target ID prediction mismatch");
            if(stalled) begin
                for(integer n=0;n<7;n=n+1) begin
                    check(dut.i_req_valid && dut.i_req_address===address && dut.fetch_redirect_pending && !dut.fetch_sent,"stalled buffered successor changed");
                    step();
                end
                accept_primed(address,0,0);
            end else if(!chained) begin
                finish_early(address,1);
            end else begin
                for(integer n=0;n<4;n=n+1) begin
                    address=dut.fetch_address; expected=prediction(address);
                    response_valid=1; #1;
                    if(FETCH_OVERLAP!=0)
                        check(dut.i_req_valid && dut.i_req_address===expected,"buffer successor chain address mismatch");
                    step();
                    check(dut.if_valid && dut.if_pc===address && dut.if_prediction===expected,"buffer successor chain metadata mismatch");
                    if(FETCH_OVERLAP==0) begin response_valid=0; step(); end
                end
                response_valid=0; barrier=1; step();
                response_valid=1; response_error=1; step();
                check(!dut.if_valid && !dut.fetch_active && !dut.fetch_redirect_pending,"buffer successor survived barrier drain");
            end
        end
    endtask
'''

EX_ONLY_RECOVERY_TASK = r'''
    task automatic ex_only_transactions;
        begin
            recovery_mem_mode=0;
            force dut.ex_recovery_known=1'b1;
            force dut.ex_recovery_relative=1'b1;
            force dut.ex_relative_target=redirect;
            for(integer taken=0;taken<2;taken=taken+1) begin
                early_idle(taken,0); early_idle(taken,1); early_chain(taken);
                reset_core(); prediction_taken=taken; request_ready=0;
                flush=1; redirect=32'h100; #1;
                check(dut.i_req_valid && dut.i_req_address===redirect,"EX request not offered under backpressure");
                step(); check_primed(32'h100);
                for(integer delay=0;delay<7;delay=delay+1) begin
                    step();
                    check(dut.i_req_valid && dut.i_req_address===32'h100 && !dut.fetch_sent,"stalled EX request changed");
                end
                accept_primed(32'h100,0,0);
            end
            // An older MEM redirect must use ordinary priming even with a known
            // younger EX alternative. No same-cycle request is accepted here.
            reset_core(); recovery_mem_mode=1; request_ready=1;
            flush=1; redirect=32'h200; #1;
            check(!dut.redirect_launch && !dut.i_req_valid,"MEM redirect bypassed ordinary priming");
            step(); request_ready=0; check_primed(32'h200); accept_primed(32'h200,0,0);
            release dut.ex_recovery_known; release dut.ex_recovery_relative; release dut.ex_relative_target;
            reset_core();
        end
    endtask
'''

COMPACT_BUFFER_TASK = r'''
    task automatic compact_region_alias;
        begin
            reset_core();
            flush=1; redirect=32'h100; step(); check_primed(32'h100); accept_primed(32'h100,0,0);
            request_ready=1; step();
            // Same retained low tag/index, different upper address: must miss.
            response_valid=1; flush=1; redirect=32'h10100; step();
            request_ready=0; check_primed(32'h10100); accept_primed(32'h10100,0,0);
            request_ready=1; step();
            response_valid=1; flush=1; redirect=32'h100; step();
            flush=0; response_valid=0; request_ready=0; #1;
            check(dut.if_valid && dut.if_pc===32'h100 && !dut.fetch_active,"high address filled or evicted compact entry");
            step(); request_ready=1; step(); response_valid=1; step(); response_valid=0;
            request_ready=1; step();
            response_valid=1; flush=1; redirect=32'hffff0100; step();
            request_ready=0; check_primed(32'hffff0100); accept_primed(32'hffff0100,0,1);
        end
    endtask
'''

CAPACITY_BUFFER_TASK = r'''
    task automatic full_buffer_capacity;
        reg [31:0] address;
        begin
            buffer_mem_mode=1; reset_core();
            flush=1; redirect=32'h100; step();
            // Fill every distinct index through accepted external responses.
            for(integer entry=0;entry<dut.TARGET_BUFFER_ENTRIES;entry=entry+1) begin
                address=32'h100+entry*4;
                response_instruction=(entry<<20)|32'h13;
                request_ready=0; check_primed(address); accept_primed(address,0,0);
                request_ready=1; step();
                response_valid=1; flush=1;
                redirect=entry+1<dut.TARGET_BUFFER_ENTRIES ? address+4 : 32'h100;
                step();
            end
            // All entries must hit with their distinct instruction words.
            response_valid=0; request_ready=0;
            for(integer entry=0;entry<dut.TARGET_BUFFER_ENTRIES;entry=entry+1) begin
                address=32'h100+entry*4;
                flush=1; redirect=address; step();
                check(dut.if_valid && dut.if_pc===address && !dut.fetch_active,
                    "capacity sweep target miss or PC alias");
                check(dut.if_instruction===((entry<<20)|32'h13),"capacity sweep instruction alias");
            end
            response_instruction=32'h13; reset_core();
        end
    endtask
'''

RAW_DIRECT_TASK = r'''
    reg raw_mem_mode=1, raw_request_allowed=1;
    wire raw_forced_redirect=flush && !raw_mem_mode && raw_request_allowed;
    task automatic raw_direct_transactions;
        begin
            raw_mem_mode=0; raw_request_allowed=1;
            for(integer taken=0;taken<2;taken=taken+1) begin
                early_idle(taken,0); early_idle(taken,1); early_chain(taken);
                reset_core(); prediction_taken=taken; request_ready=0;
                flush=1; redirect=32'h180; #1;
                check(dut.redirect_launch && dut.i_req_valid && dut.i_req_address===redirect,"raw direct request not offered under backpressure");
                step(); check_primed(32'h180);
                repeat(7) begin
                    step();
                    check(dut.i_req_valid && dut.i_req_address===32'h180 && !dut.fetch_sent,"raw direct stalled request changed");
                end
                accept_primed(32'h180,0,0);
            end
            // Excluded EX operands and older MEM redirects retain ordinary priming.
            for(integer mem_source=0;mem_source<2;mem_source=mem_source+1) begin
                raw_mem_mode=mem_source; raw_request_allowed=mem_source;
                reset_core(); request_ready=1; flush=1; redirect=32'h200; #1;
                check(!dut.redirect_launch && !dut.i_req_valid,"excluded raw direct request bypassed ordinary priming");
                step(); request_ready=0; check_primed(32'h200); accept_primed(32'h200,0,0);
            end
            raw_mem_mode=1; raw_request_allowed=1; reset_core();
        end
    endtask
'''

RAW_OPERAND_TASK = r'''
    reg raw_request_allowed=1;
    wire raw_forced_redirect=flush && !recovery_mem_mode && raw_request_allowed;
    task automatic raw_operand_fallback;
        begin
            // The existing transaction fixture forces redirect decisions. The
            // architectural suite independently checks the real operand predicate.
            recovery_mem_mode=0; raw_request_allowed=0;
            force dut.ex_recovery_known=1'b1;
            force dut.ex_recovery_relative=1'b1;
            force dut.ex_relative_target=redirect;
            reset_core(); request_ready=1; flush=1; redirect=32'h100; #1;
            check(!dut.redirect_launch && !dut.i_req_valid,"excluded operand class issued an early request");
            step(); request_ready=0; check_primed(32'h100); accept_primed(32'h100,0,0);
            release dut.ex_recovery_known; release dut.ex_recovery_relative; release dut.ex_relative_target;
            recovery_mem_mode=1; raw_request_allowed=1; reset_core();
        end
    endtask
'''

BUFFER_DRAIN_TASK = r'''
    task automatic cached_head_drain(input integer sent,input integer taken,input integer delayed,input integer ready,input integer error,input integer replacement);
        reg [31:0] old_address,expected,head;
        begin
            buffer_mem_mode=1; reset_core(); prediction_taken=taken;
            response_instruction=32'h00700013; request_ready=1;
            flush=1; redirect=32'h100; step(); finish_early(32'h100,0);
            old_address=dut.fetch_address;
            request_ready=sent; step(); request_ready=0;
            flush=1; redirect=32'h100; #1;
            check(dut.target_buffer_hit && !dut.redirect_launch,"cached drain fixture did not hit");
            if(!sent) check(dut.i_req_valid && dut.i_req_address===old_address,"hit changed old unaccepted request");
            else check(!dut.i_req_valid,"hit issued request while old response pending");
            step(); flush=0; #1;
            check(dut.fetch_active && dut.fetch_discard && dut.fetch_address===old_address && dut.buffer_drain_pending,
                "hit cancelled old transaction");
            check(dut.if_valid && dut.if_pc===32'h100 && dut.if_instruction===32'h00700013 && !dut.if_error,
                "cached head was not delivered before old response");
            head=32'h100; expected=prediction(head);
            if(replacement!=0) begin
                // A second hit replaces the queued head; a miss kills its held
                // successor. In both cases the same old bus request must survive.
                flush=1; redirect=replacement==1 ? 32'h100 : 32'h300; step(); flush=0; #1;
                head=redirect; expected=prediction(head);
                check(dut.fetch_active && dut.fetch_discard && dut.fetch_address===old_address,"repeat redirect changed old transaction");
                check(dut.buffer_drain_pending===(replacement==1),"repeat redirect retained wrong drain state");
                check(dut.if_valid===(replacement==1),"repeat redirect retained wrong cached head");
            end
            if(delayed!=0) begin
                for(integer wait_cycle=0;wait_cycle<7;wait_cycle=wait_cycle+1) begin
                    step();
                    // Training can change the live predictor while the external
                    // fetch waits. The cached head must keep its captured result;
                    // prediction of its successor is obtained afresh later.
                    if(wait_cycle==0 && replacement!=2) begin prediction_taken=!taken; #1; end
                    check(dut.fetch_address===old_address && dut.fetch_discard,"old request changed while waiting");
                    if(!sent) check(dut.i_req_valid && dut.i_req_address===old_address,"stalled request address changed");
                    if(replacement!=2) check(dut.resolved_if_prediction===expected,"held successor prediction changed");
                end
            end
            if(!sent) begin request_ready=1; step(); end
            request_ready=ready; response_valid=1; response_error=error; response_instruction=32'h00b00013; #1;
            if(FETCH_OVERLAP!=0) check(dut.i_req_valid && dut.i_req_address===(replacement==2 ? head : expected),"drain overlap address wrong");
            else check(!dut.i_req_valid,"drain issued successor with overlap disabled");
            step(); response_valid=0; response_error=0; #1;
            check(!dut.buffer_drain_pending && !dut.fetch_discard && dut.fetch_address===(replacement==2 ? head : expected),
                "drain did not allocate resolved successor");
            check(!dut.if_valid || dut.if_instruction!==32'h00b00013,"stale response leaked into IF");
            if(replacement!=2) begin
                if(FETCH_OVERLAP!=0 && ready!=0) begin
                    check(dut.fetch_sent && dut.fetch_late_prediction && !dut.fetch_redirect_pending,"overlapped successor acceptance wrong");
                    finish_early(expected,0);
                end else begin
                    request_ready=0; check_primed(expected); accept_primed(expected,0,0);
                end
            end
            response_instruction=32'h13; reset_core();
        end
    endtask

    task automatic cached_head_barrier(input integer sent,input integer accept_barrier);
        reg [31:0] old_address;
        begin
            buffer_mem_mode=1; reset_core(); request_ready=1;
            flush=1; redirect=32'h100; step(); finish_early(32'h100,0);
            old_address=dut.fetch_address; request_ready=sent; step(); request_ready=0;
            flush=1; redirect=32'h100; step(); flush=0;
            barrier=1; request_ready=accept_barrier; step();
            check(!dut.buffer_drain_pending && !dut.target_prediction_pending && !dut.if_valid && dut.target_buffer_valid==0,
                "barrier retained cached head or successor");
            check(dut.fetch_active && dut.fetch_discard && dut.fetch_address===old_address,"barrier cancelled old fetch");
            if(!dut.fetch_sent) begin request_ready=1; step(); end
            request_ready=0; response_valid=1; response_error=1; step(); response_valid=0;
            check(!dut.fetch_active && !dut.if_valid,"barrier drain exposed stale response");
            rst_n=0; #1;
            check(!dut.buffer_drain_pending && dut.target_buffer_valid==0,"reset retained drain or buffer state");
            reset_core();
        end
    endtask
'''

HYBRID_BUFFER_TASK = r'''
    task automatic hybrid_miss_then_reuse(input integer ready,input integer error);
        begin
            buffer_mem_mode=1; reset_core(); response_instruction=32'h00700013;
            request_ready=ready; flush=1; redirect=32'h100; #1;
            check(!dut.target_buffer_hit && dut.redirect_launch && dut.i_req_valid && dut.i_req_address===redirect,
                "hybrid cold miss was not offered immediately");
            step();
            if(ready) finish_early(32'h100,error);
            else begin check_primed(32'h100); accept_primed(32'h100,0,error); end
            request_ready=1; response_valid=0; step();
            response_valid=1; response_error=0; flush=1; redirect=32'h100; #1;
            if(error) begin
                check(!dut.target_buffer_hit && dut.redirect_launch && dut.i_req_valid,
                    "hybrid error response was cached or missed early retry");
                step(); finish_early(32'h100,0);
            end else begin
                check(dut.target_buffer_hit && !dut.redirect_launch && !dut.i_req_valid,
                    "hybrid hit issued an external request");
                step(); flush=0; response_valid=0; request_ready=0; #1;
                check(dut.if_valid && dut.if_pc===32'h100 && dut.if_instruction===32'h00700013 && !dut.if_error,
                    "hybrid hit lost verified instruction data");
                check(!dut.fetch_active && dut.target_prediction_pending,"hybrid hit lost successor phase");
            end
            response_instruction=32'h13; reset_core();
        end
    endtask

    task automatic hybrid_hit_while_draining(input integer sent);
        reg [31:0] old_address;
        begin
            buffer_mem_mode=1; reset_core(); request_ready=1;
            flush=1; redirect=32'h100; step(); finish_early(32'h100,0);
            old_address=dut.fetch_address;
            request_ready=sent; step(); request_ready=0;
            flush=1; redirect=32'h100; #1;
            check(dut.target_buffer_hit && !dut.redirect_launch,"occupied slot consumed hybrid hit");
            if(!sent) check(dut.i_req_valid && dut.i_req_address===old_address,"hybrid hit changed stalled request");
            else check(!dut.i_req_valid,"hybrid hit bypassed an outstanding response");
            step(); flush=0; #1;
            check(dut.fetch_active && dut.fetch_discard && dut.fetch_address===old_address && !dut.if_valid,
                "hybrid hit cancelled an older transaction");
            if(!sent) begin request_ready=1; step(); end
            request_ready=0; response_valid=1; step(); response_valid=0; #1;
            check(!dut.if_valid && !dut.fetch_discard && dut.fetch_address===32'h100,
                "hybrid drain lost resolved target or exposed stale response");
            reset_core();
        end
    endtask

    task automatic hybrid_unknown_ex;
        begin
            buffer_mem_mode=0; reset_core();
            force dut.ex_recovery_known=1'b0;
            request_ready=1; flush=1; redirect=32'h180; #1;
            check(!dut.target_buffer_hit && dut.redirect_launch && dut.i_req_address===32'h180,
                "unknown EX buffer lookup lost resolved early miss address");
            step(); finish_early(32'h180,0);
            release dut.ex_recovery_known;
            buffer_mem_mode=1; reset_core();
        end
    endtask
'''

TASKS = r'''
    task automatic target_collision;
        begin
            reset_core();
            flush=1; redirect=32'h100; step(); check_primed(32'h100);
            accept_primed(32'h100,0,0);
            request_ready=1; step();
            // 0x100 and 0x500 share the direct index in every tested buffer size.
            response_valid=1; flush=1; redirect=32'h500; step();
            request_ready=0; check_primed(32'h500); accept_primed(32'h500,0,0);
            request_ready=1; step();
            response_valid=1; flush=1; redirect=32'h100; step();
            request_ready=0; check_primed(32'h100); accept_primed(32'h100,0,0);
        end
    endtask

    task automatic target_reuse(input integer taken,input integer error);
        reg [31:0] expected;
        begin
            reset_core(); prediction_taken=taken;
            flush=1; redirect=32'h100; step(); check_primed(32'h100);
            accept_primed(32'h100,0,error);
            request_ready=1; step();
            response_valid=1; response_error=0; flush=1; redirect=32'h100; step();
            flush=0; response_valid=0; request_ready=0; #1;
            if(error==0) begin
                expected=prediction(32'h100);
                check(dut.if_valid && dut.if_pc===32'h100 && dut.if_instruction===32'h00000013 && !dut.fetch_active,"buffer did not reuse verified target");
                step();
                check(dut.id_valid && dut.id_pc===32'h100 && dut.id_prediction===expected,"buffer used stale target prediction");
                check(dut.fetch_address===expected && dut.fetch_redirect_pending,"buffer successor was not deferred correctly");
                barrier=1; request_ready=1; step();
                request_ready=0; response_valid=1; step(); response_valid=0;
                barrier=0; flush=1; redirect=32'h100; step();
                check(!dut.if_valid && dut.fetch_active && dut.fetch_redirect_pending,"barrier failed to invalidate buffered code");
            end else begin
                check(!dut.if_valid && dut.fetch_active && dut.fetch_redirect_pending,"instruction error was cached as valid code");
            end
        end
    endtask

    task automatic finish_early(input [31:0] address,input integer error);
        reg [31:0] expected;
        begin
            flush=0; request_ready=0; response_valid=1; response_error=error;
            expected=prediction(address); #1;
            check(dut.fetch_active && dut.fetch_sent && !dut.fetch_redirect_pending,"early request not accepted exactly once");
            check(dut.i_rsp_ready,"early response blocked"); step();
            check(dut.if_valid && dut.if_pc===address && dut.if_prediction===expected && dut.if_error===error[0],"early target response metadata");
            response_valid=0; #1;
            check(dut.fetch_address===expected && dut.next_pc===expected && dut.fetch_redirect_pending,"successor recovery after overlap stall");
            accept_primed(expected,0,0);
        end
    endtask

    task automatic early_idle(input integer taken,input integer error);
        begin
            reset_core(); prediction_taken=taken; request_ready=1;
            flush=1; redirect=32'h100; #1;
            check(dut.i_req_valid && dut.i_req_address===32'h100,"no request in redirect cycle");
            step(); finish_early(32'h100,error);
        end
    endtask

    task automatic early_chain(input integer taken);
        reg [31:0] address,expected;
        begin
            reset_core(); prediction_taken=taken; request_ready=1;
            flush=1; redirect=32'h100; step(); flush=0;
            for(integer n=0;n<4;n=n+1) begin
                address=dut.fetch_address; expected=prediction(address);
                response_valid=1; #1;
                if(FETCH_OVERLAP!=0) check(dut.i_req_valid && dut.i_req_address===expected,"early successor request repeated target or used stale prediction");
                step();
                check(dut.if_valid && dut.if_pc===address && dut.if_prediction===expected,"early chain response metadata");
                if(FETCH_OVERLAP==0) begin
                    response_valid=0; step();
                end
            end
            response_valid=0;
            barrier=1; step();
            response_valid=1; response_error=1; step();
            check(!dut.if_valid && !dut.fetch_active && !dut.fetch_redirect_pending,"late prediction survived barrier drain");
        end
    endtask
'''


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--variants",type=Path,default=h.ROOT/"variants/redirect-optimization-v27-r1")
    parser.add_argument("--modes",nargs="+",default=["priming_off","priming_on","early_issue"])
    parser.add_argument("--directed-only",action="store_true")
    args=parser.parse_args(); variants=args.variants.resolve()
    vm=json.loads((variants/"manifest.json").read_text())
    if any(mode not in vm['variants'] for mode in args.modes): raise ValueError('Unknown variant')
    run=h.ROOT/"results"/("redirect-gates-"+datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")+"-"+uuid4().hex[:8])
    run.mkdir(exist_ok=False)
    record=dict(protocol='v27',status='running',variant_manifest_sha256=h.sha(variants/'manifest.json'),variants=str(variants),runs=[])
    def save(): h.write_json(run/'manifest.json',record)
    h.snapshot(__file__,run/'runner.py'); save(); print('RUN '+str(run),flush=True)
    try:
        bench=adapted_bench()
        bench=replace_once(bench,'parameter integer PRIMING=1,','parameter integer BUFFER=0,\n    parameter integer EARLY=0,\n    parameter integer PRIMING=1,')
        bench=replace_once(bench,"request_ready=0; check_primed(32'h200); accept_primed(32'h200,1,0);",
                           "if(EARLY!=0 && accept_on_flush!=0) finish_early(32'h200,0);\n                else begin request_ready=0; check_primed(32'h200); accept_primed(32'h200,1,0); end")
        bench=replace_once(bench,'    initial begin',TASKS+'\n    initial begin')
        bench=replace_once(bench,'        repeat_redirect(0); repeat_redirect(1);',
                           '        if(BUFFER!=0) begin\n            target_collision();\n            target_reuse(0,0); target_reuse(1,0); target_reuse(0,1); target_reuse(1,1);\n        end\n        if(EARLY!=0) begin\n            for(integer t=0;t<2;t=t+1) begin\n                early_idle(t,0); early_idle(t,1); early_chain(t);\n            end\n        end\n        repeat_redirect(0); repeat_redirect(1);')
        (run/'redirect_prime_tb.sv').write_text(bench,encoding='utf-8')
        record['bench_sha256']=h.sha(run/'redirect_prime_tb.sv'); save()
        modules=['rv32_core','rv32_machine','rv32_decode','rv32_alu','rv32_btb','rv32_muldiv']
        for mode in args.modes:
            target=run/mode; target.mkdir()
            mode_bench=run/'redirect_prime_tb.sv'
            if vm['variants'][mode].get('precomputed_recovery'):
                # Existing synthetic redirects exercise MEM priority. Separate
                # cases exercise recognized EX alternatives and unknown fallback.
                mode_text=replace_once(bench,'        force dut.redirect_pc=redirect;',
                    "        force dut.redirect_pc=redirect;\n        force dut.mem_flush=recovery_mem_flush;\n"
                    "        force dut.mem_fault=1'b0;\n        force dut.mem_next_pc=redirect;")
                mode_text=replace_once(mode_text,'    initial begin',RECOVERY_TASK+'\n    initial begin')
                mode_text=replace_once(mode_text,'        repeat_redirect(0); repeat_redirect(1);',
                    '        recovery_addresses();\n        repeat_redirect(0); repeat_redirect(1);')
                mode_bench=target/'redirect_prime_tb.sv'; mode_bench.write_text(mode_text,encoding='utf-8')
                record.setdefault('variant_bench_hashes',{})[mode]=h.sha(mode_bench)
            if vm['variants'][mode].get('ex_only_recovery') and not vm['variants'][mode].get('raw_direct_recovery'):
                mode_text=mode_bench.read_text()
                mode_text=replace_once(mode_text,'    initial begin',EX_ONLY_RECOVERY_TASK+'\n    initial begin')
                mode_text=replace_once(mode_text,'        recovery_addresses();',
                    '        recovery_addresses();\n        ex_only_transactions();')
                mode_bench=target/'redirect_prime_tb.sv'; mode_bench.write_text(mode_text,encoding='utf-8')
                record.setdefault('variant_bench_hashes',{})[mode]=h.sha(mode_bench)
            if vm['variants'][mode].get('fast_buffer_handoff'):
                mode_text=mode_bench.read_text()
                mode_text=replace_once(mode_text,'    initial begin',FAST_BUFFER_TASK+'\n    initial begin')
                mode_text=replace_once(mode_text,'        repeat_redirect(0); repeat_redirect(1);',
                    '        for(integer t=0;t<2;t=t+1) begin\n'
                    '            buffered_successor(t,0,0); buffered_successor(t,0,1); buffered_successor(t,1,0);\n'
                    '        end\n        repeat_redirect(0); repeat_redirect(1);')
                mode_bench=target/'redirect_prime_tb.sv'; mode_bench.write_text(mode_text,encoding='utf-8')
                record.setdefault('variant_bench_hashes',{})[mode]=h.sha(mode_bench)
            if vm['variants'][mode].get('precomputed_buffer_lookup'):
                mode_text=mode_bench.read_text()
                mode_text=replace_once(mode_text,'        force dut.redirect_pc=redirect;',
                    "        force dut.redirect_pc=redirect;\n        force dut.mem_flush=buffer_mem_flush;\n"
                    "        force dut.mem_fault=1'b0;\n        force dut.mem_next_pc=redirect;")
                mode_text=replace_once(mode_text,'    initial begin',BUFFER_LOOKUP_TASK+'\n    initial begin')
                mode_text=replace_once(mode_text,'        repeat_redirect(0); repeat_redirect(1);',
                    '        buffer_lookup_addresses();\n        repeat_redirect(0); repeat_redirect(1);')
                mode_bench=target/'redirect_prime_tb.sv'; mode_bench.write_text(mode_text,encoding='utf-8')
                record.setdefault('variant_bench_hashes',{})[mode]=h.sha(mode_bench)
            if vm['variants'][mode].get('compact_buffer_tags'):
                mode_text=mode_bench.read_text()
                mode_text=replace_once(mode_text,'    initial begin',COMPACT_BUFFER_TASK+'\n    initial begin')
                mode_text=replace_once(mode_text,'        repeat_redirect(0); repeat_redirect(1);',
                    '        compact_region_alias();\n        repeat_redirect(0); repeat_redirect(1);')
                mode_bench=target/'redirect_prime_tb.sv'; mode_bench.write_text(mode_text,encoding='utf-8')
                record.setdefault('variant_bench_hashes',{})[mode]=h.sha(mode_bench)
            if vm['variants'][mode].get('early_mem_buffer_lookup'):
                mode_text=mode_bench.read_text()
                # Existing forced MEM redirects must also present a pending MEM
                # instruction to the speculative selector. The exhaustive sweep
                # below releases these synthetic redirect outputs.
                mode_text=replace_once(mode_text,"        force dut.mem_fault=1'b0;",
                    "        force dut.mem_fault=1'b0;\n"
                    "        force dut.mem_valid=buffer_mem_flush;\n"
                    "        force dut.mem_mret=buffer_mem_flush;\n"
                    "        force dut.mem_exception=1'b0;\n"
                    "        force dut.mem_load=1'b0; force dut.mem_store=1'b0;")
                mode_text=replace_once(mode_text,'    initial begin',MEM_LOOKUP_TASK+'\n    initial begin')
                mode_text=replace_once(mode_text,'        $display("PASS redirect_prime',
                    '        mem_lookup_boundary();\n        $display("PASS redirect_prime')
                mode_bench=target/'redirect_prime_tb.sv'; mode_bench.write_text(mode_text,encoding='utf-8')
                record.setdefault('variant_bench_hashes',{})[mode]=h.sha(mode_bench)
            if vm['variants'][mode].get('sequential_redirect_target'):
                mode_text=mode_bench.read_text()
                mode_text=replace_once(mode_text,"wire [31:0] synthetic_target=dut.next_pc+32'h80;",
                    "wire [31:0] synthetic_target=dut.prediction_lookup_pc+32'h80;")
                mode_text=replace_once(mode_text,'            expected=prediction(address); #1;',
                    "            expected=address+32'd4; #1;")
                mode_text=replace_once(mode_text,'check(dut.fetch_address===expected && dut.next_pc===expected && dut.fetch_redirect_pending,"successor recovery after overlap stall");',
                    'check(dut.fetch_address===expected && dut.next_pc===prediction(expected) && !dut.fetch_redirect_pending,"successor prediction after overlap stall");')
                mode_text=replace_once(mode_text,'                address=dut.fetch_address; expected=prediction(address);',
                    "                address=dut.fetch_address; expected=n==0 ? address+32'd4 : prediction(address);")
                mode_text=replace_once(mode_text,'    initial begin',SEQUENTIAL_TARGET_TASK+'\n    initial begin')
                mode_text=replace_once(mode_text,'        repeat_redirect(0); repeat_redirect(1);',
                    '        sequential_target_stall();\n        repeat_redirect(0); repeat_redirect(1);')
                if vm['variants'][mode].get('ex_only_recovery'):
                    # This policy applies to accepted EX early requests. Keep the
                    # ordinary MEM fallback tests intact and drive the independent
                    # EX address fixture only around this delayed-response case.
                    mode_text=replace_once(mode_text,'        sequential_target_stall();',
                        "        recovery_mem_mode=0;\n"
                        "        force dut.ex_recovery_known=1'b1;\n"
                        "        force dut.ex_recovery_relative=1'b1;\n"
                        "        force dut.ex_relative_target=redirect;\n"
                        '        sequential_target_stall();\n'
                        '        release dut.ex_recovery_known; release dut.ex_recovery_relative; release dut.ex_relative_target;\n'
                        '        recovery_mem_mode=1; reset_core();')
                mode_bench=target/'redirect_prime_tb.sv'; mode_bench.write_text(mode_text,encoding='utf-8')
                record.setdefault('variant_bench_hashes',{})[mode]=h.sha(mode_bench)
            if vm['variants'][mode].get('full_buffer_capacity_check'):
                mode_text=mode_bench.read_text()
                begin=mode_text.index('    task automatic target_collision;')
                end=mode_text.index('    endtask',begin)+len('    endtask')
                task=mode_text[begin:end]
                if task.count("32'h500")!=3: raise ValueError('Collision task changed')
                collision=0x100+4*vm['variants'][mode]['target_buffer_entries']
                task=task.replace("32'h500",f"32'h{collision:x}").replace(
                    '// 0x100 and 0x500 share the direct index in every tested buffer size.',
                    '// Collision address is derived independently from the configured capacity.')
                mode_text=mode_text[:begin]+task+mode_text[end:]
                mode_text=replace_once(mode_text,"    reg [31:0] redirect=0;",
                    "    reg [31:0] redirect=0, response_instruction=32'h13;")
                mode_text=replace_once(mode_text,".i_rsp_data(32'h00000013)",'.i_rsp_data(response_instruction)')
                mode_text=replace_once(mode_text,'    initial begin',CAPACITY_BUFFER_TASK+'\n    initial begin')
                mode_text=replace_once(mode_text,'        repeat_redirect(0); repeat_redirect(1);',
                    '        full_buffer_capacity();\n        repeat_redirect(0); repeat_redirect(1);')
                mode_bench=target/'redirect_prime_tb.sv'; mode_bench.write_text(mode_text,encoding='utf-8')
                record.setdefault('variant_bench_hashes',{})[mode]=h.sha(mode_bench)
            if vm['variants'][mode].get('hybrid_buffer_early'):
                if not vm['variants'][mode].get('full_buffer_capacity_check'):
                    raise ValueError('Hybrid directed fixture requires explicit capacity coverage')
                mode_text=mode_bench.read_text()
                # Existing buffer-only cases intentionally stall misses. Preserve
                # their fill/tag/error checks; separate hybrid cases below accept
                # misses immediately and verify hit suppression under ready=1.
                def rewrite_task(name,old,new,count=1):
                    nonlocal mode_text
                    begin=mode_text.index('    task automatic '+name)
                    end=mode_text.index('    endtask',begin)+len('    endtask')
                    task=mode_text[begin:end]
                    if task.count(old)!=count: raise ValueError('Hybrid fixture anchor changed: '+name)
                    mode_text=mode_text[:begin]+task.replace(old,new)+mode_text[end:]
                rewrite_task('target_collision;', 'response_valid=1; flush=1; redirect=',
                    'request_ready=0; response_valid=1; flush=1; redirect=',2)
                rewrite_task('target_reuse(', 'response_valid=1; response_error=0; flush=1;',
                    'request_ready=error==0; response_valid=1; response_error=0; flush=1;')
                rewrite_task('buffer_lookup_addresses;', "response_valid=1; flush=1; redirect=32'h100;",
                    "request_ready=known; response_valid=1; flush=1; redirect=32'h100;")
                for address in ('10100','ffff0100'):
                    rewrite_task('compact_region_alias;', 'response_valid=1; flush=1; redirect=32\'h'+address+';',
                        'request_ready=0; response_valid=1; flush=1; redirect=32\'h'+address+';')
                rewrite_task('full_buffer_capacity;', 'response_valid=1; flush=1;',
                    'request_ready=0; response_valid=1; flush=1;')
                mode_text=replace_once(mode_text,'    initial begin',HYBRID_BUFFER_TASK+'\n    initial begin')
                mode_text=replace_once(mode_text,'        repeat_redirect(0); repeat_redirect(1);',
                    '        hybrid_miss_then_reuse(0,0); hybrid_miss_then_reuse(0,1);\n'
                    '        hybrid_miss_then_reuse(1,0); hybrid_miss_then_reuse(1,1);\n'
                    '        hybrid_hit_while_draining(0); hybrid_hit_while_draining(1);\n'
                    '        hybrid_unknown_ex();\n        repeat_redirect(0); repeat_redirect(1);')
                mode_bench=target/'redirect_prime_tb.sv'; mode_bench.write_text(mode_text,encoding='utf-8')
                record.setdefault('variant_bench_hashes',{})[mode]=h.sha(mode_bench)
            if vm['variants'][mode].get('raw_operand_recovery'):
                mode_text=mode_bench.read_text()
                task=RAW_DIRECT_TASK if vm['variants'][mode].get('raw_direct_recovery') else RAW_OPERAND_TASK
                mode_text=replace_once(mode_text,'    initial begin',task+'\n    initial begin')
                mode_text=replace_once(mode_text,'        force dut.frontend_flush=flush;',
                    '        force dut.frontend_flush=flush;\n        force dut.raw_redirect_event=raw_forced_redirect;')
                if vm['variants'][mode].get('raw_direct_recovery'):
                    mode_text=replace_once(mode_text,'        force dut.redirect_pc=redirect;',
                        '        force dut.redirect_pc=redirect;\n        force dut.raw_redirect_next=redirect;')
                call='raw_direct_transactions' if vm['variants'][mode].get('raw_direct_recovery') else 'raw_operand_fallback'
                mode_text=replace_once(mode_text,'        repeat_redirect(0); repeat_redirect(1);',
                    '        '+call+'();\n        repeat_redirect(0); repeat_redirect(1);')
                mode_bench=target/'redirect_prime_tb.sv'; mode_bench.write_text(mode_text,encoding='utf-8')
                record.setdefault('variant_bench_hashes',{})[mode]=h.sha(mode_bench)
            if vm['variants'][mode].get('buffer_hit_during_drain'):
                mode_text=mode_bench.read_text()
                mode_text=replace_once(mode_text,'        hybrid_hit_while_draining(0); hybrid_hit_while_draining(1);',
                    '        for(integer sent=0;sent<2;sent=sent+1)\n'
                    '            for(integer taken=0;taken<2;taken=taken+1)\n'
                    '                for(integer delayed=0;delayed<2;delayed=delayed+1)\n'
                    '                    for(integer ready=0;ready<2;ready=ready+1)\n'
                    '                        for(integer error=0;error<2;error=error+1)\n'
                    '                            for(integer replacement=0;replacement<3;replacement=replacement+1)\n'
                    '                                cached_head_drain(sent,taken,delayed,ready,error,replacement);\n'
                    '        cached_head_barrier(0,0); cached_head_barrier(0,1);\n'
                    '        cached_head_barrier(1,0); cached_head_barrier(1,1);')
                mode_text=replace_once(mode_text,'    initial begin',BUFFER_DRAIN_TASK+'\n    initial begin')
                mode_bench=target/'redirect_prime_tb.sv'; mode_bench.write_text(mode_text,encoding='utf-8')
                record.setdefault('variant_bench_hashes',{})[mode]=h.sha(mode_bench)
            if vm['variants'][mode].get('request_address_factored'):
                mode_text=mode_bench.read_text()
                invariant=REQUEST_ADDRESS_INVARIANTS.replace('core.', 'dut.')
                mode_text=replace_once(mode_text,'    initial begin',invariant+'\n    initial begin')
                mode_bench=target/'redirect_prime_tb.sv'; mode_bench.write_text(mode_text,encoding='utf-8')
                record.setdefault('variant_bench_hashes',{})[mode]=h.sha(mode_bench)
            if vm['variants'][mode].get('speculative_overlap'):
                mode_text=adapt_speculative_overlap(mode_bench.read_text(),bool(vm['variants'][mode].get('raw_direct_recovery')))
                mode_bench=target/'redirect_prime_tb.sv'; mode_bench.write_text(mode_text,encoding='utf-8')
                record.setdefault('variant_bench_hashes',{})[mode]=h.sha(mode_bench)
                helper=h.ROOT/'scripts/redirect_speculative_overlap_tests.py'
                h.snapshot(helper,run/'speculative_overlap_tests.py')
                record['speculative_overlap_tests_sha256']=h.sha(helper)
            if vm['variants'][mode].get('registered_prediction_mismatch'):
                mode_text=adapt_prediction_mismatch(mode_bench.read_text())
                mode_bench=target/'redirect_prime_tb.sv'; mode_bench.write_text(mode_text,encoding='utf-8')
                record.setdefault('variant_bench_hashes',{})[mode]=h.sha(mode_bench)
                helper=h.ROOT/'scripts/redirect_prediction_mismatch_tests.py'
                h.snapshot(helper,run/'prediction_mismatch_tests.py')
                record['prediction_mismatch_tests_sha256']=h.sha(helper)
            for name in modules:
                relative='rtl/'+name+'.sv'
                if h.sha(variants/mode/relative)!=vm['variants'][mode]['hashes'][relative]: raise ValueError('Variant changed')
                h.snapshot(variants/mode/relative,target/(name+'.sv'))
            for overlap in (0,1):
                for predictor in (0,1):
                    label=f'o{overlap}-p{predictor}'; binary=target/(label+'.vvp')
                    cmd=['/usr/bin/iverilog','-g2012','-s','redirect_prime_tb','-o',binary,
                         f'-Predirect_prime_tb.BUFFER={int(mode.startswith("target_buffer_"))}',
                         f'-Predirect_prime_tb.EARLY={int((mode=="early_issue" or mode.endswith("_early")) and not vm["variants"][mode].get("ex_only_recovery"))}',f'-Predirect_prime_tb.PRIMING={int(not mode.endswith("_off"))}',
                         f'-Predirect_prime_tb.FETCH_OVERLAP={overlap}',f'-Predirect_prime_tb.PREDICTOR={predictor}']
                    if vm['variants'][mode].get('request_address_factored'):
                        cmd += ['-DREQUEST_ADDRESS_FACTORING']
                    cmd += [target/(name+'.sv') for name in modules]+[mode_bench]
                    passed=h.command(cmd,target,label+'-compile',120)==0
                    if passed: passed=h.command(['/usr/bin/vvp',binary],target,label+'-simulation',120)==0 and 'PASS redirect_prime' in (target/(label+'-simulation.log')).read_text()
                    record['runs'].append(dict(variant=mode,name=label,passed=passed)); save()
                    print(mode+' '+label+' '+('PASS' if passed else 'FAIL'),flush=True)
        if not all(r['passed'] for r in record['runs']): raise RuntimeError('Directed gate failed')
        record['status']='directed_passed'; save()
        if not args.directed_only:
            # Reuse the existing independent instruction interpreter and randomized
            # memory/interrupt tests. Adapt only paths, variant inventory, and count.
            source=h.ROOT/'scripts/run_architecture_regressions.py'
            code=source.read_text()
            edits=[('ROOT = Path(__file__).resolve().parents[1]', 'ROOT = Path('+repr(str(h.ROOT))+')'),
                   ('VARIANTS = ROOT / "variants/redirect-priming-v1"','VARIANTS = Path('+repr(str(variants))+')'),
                   ('for mode in ("priming_off", "priming_on"):', 'for mode in '+repr(tuple(args.modes))+':'),
                   ('variant_manifest["variants"][mode]["rtl/" + original.name]["sha256"]','variant_manifest["variants"][mode]["hashes"]["rtl/" + original.name]'),
                   ('if len(manifest["runs"]) != 60:',f'if len(manifest["runs"]) != {30*len(args.modes)}:'),
                   ('Incomplete 32 architectural and 28 interrupt run matrix','Incomplete per-variant 16 architectural and 14 interrupt matrix'),
                   ('PASS 60 matched regression runs:',f'PASS {30*len(args.modes)} matched regression runs:')]
            for before,after in edits:
                if before.startswith('for mode'):
                    if code.count(before)!=2: raise ValueError('Architecture loop shape changed')
                    code=code.replace(before,after)
                else: code=replace_once(code,before,after)
            if any(vm['variants'][mode].get('relaxed_compare_lookahead') or vm['variants'][mode].get('precomputed_buffer_lookup') or vm['variants'][mode].get('fast_buffer_handoff') or vm['variants'][mode].get('request_address_factored') for mode in args.modes):
                invariants=RECOVERY_INVARIANTS+BUFFER_LOOKUP_INVARIANTS+REQUEST_ADDRESS_INVARIANTS+SPECULATIVE_OVERLAP_INVARIANTS
                if any(vm['variants'][mode].get('relaxed_compare_lookahead') for mode in args.modes):
                    invariants=COMPARE_INVARIANTS+invariants
                (run/'compare_invariants.sv').write_text(invariants,encoding='utf-8')
                code=replace_once(code,'    variant_manifest = json.loads((VARIANTS / "manifest.json").read_text())',
                    '    invariant_text = Path('+repr(str(run/'compare_invariants.sv'))+').read_text()\n'
                    '    for bench_name in ("core_tb.sv", "cached_core_tb.sv", "muldiv_core_tb.sv"):\n'
                    '        bench_path = source / bench_name\n'
                    '        bench_text = bench_path.read_text()\n'
                    '        if bench_text.count("endmodule") != 1: raise ValueError("Unexpected bench modules")\n'
                    '        bench_path.write_text(bench_text.replace("endmodule", invariant_text + "\\nendmodule"))\n'
                    '    variant_manifest = json.loads((VARIANTS / "manifest.json").read_text())')
            if any(vm['variants'][mode].get('precomputed_recovery') for mode in args.modes):
                needle='"/usr/bin/iverilog", "-g2012", "-Wall",'
                if code.count(needle)!=2: raise ValueError('Unexpected architectural compile commands')
                code=code.replace(needle,needle+' *(["-DPRECOMPUTED_RECOVERY"] if variant_manifest["variants"][mode].get("precomputed_recovery") else []),')
            if any(vm['variants'][mode].get('precomputed_buffer_lookup') for mode in args.modes):
                needle='"/usr/bin/iverilog", "-g2012", "-Wall",'
                if code.count(needle)!=2: raise ValueError('Unexpected architectural compile commands')
                code=code.replace(needle,needle+' *(["-DPRECOMPUTED_BUFFER"] if variant_manifest["variants"][mode].get("precomputed_buffer_lookup") else []),')
            if any(vm['variants'][mode].get('fast_buffer_handoff') for mode in args.modes):
                needle='"/usr/bin/iverilog", "-g2012", "-Wall",'
                if code.count(needle)!=2: raise ValueError('Unexpected architectural compile commands')
                code=code.replace(needle,needle+' *(["-DFAST_BUFFER"] if variant_manifest["variants"][mode].get("fast_buffer_handoff") else []),')
            if any(vm['variants'][mode].get('precomputed_mem_compare') for mode in args.modes):
                needle='"/usr/bin/iverilog", "-g2012", "-Wall",'
                if code.count(needle)!=2: raise ValueError('Unexpected architectural compile commands')
                code=code.replace(needle,needle+' *(["-DMEM_COMPARE"] if variant_manifest["variants"][mode].get("precomputed_mem_compare") else []),')
            if any(vm['variants'][mode].get('direct_mem_compare') for mode in args.modes):
                needle='"/usr/bin/iverilog", "-g2012", "-Wall",'
                if code.count(needle)!=2: raise ValueError('Unexpected architectural compile commands')
                code=code.replace(needle,needle+' *(["-DDIRECT_MEM_COMPARE"] if variant_manifest["variants"][mode].get("direct_mem_compare") else []),')
            if any(vm['variants'][mode].get('request_address_factored') for mode in args.modes):
                needle='"/usr/bin/iverilog", "-g2012", "-Wall",'
                if code.count(needle)!=2: raise ValueError('Unexpected architectural compile commands')
                code=code.replace(needle,needle+' *(["-DREQUEST_ADDRESS_FACTORING"] if variant_manifest["variants"][mode].get("request_address_factored") else []),')
            if any(vm['variants'][mode].get('hybrid_buffer_early') for mode in args.modes):
                needle='"/usr/bin/iverilog", "-g2012", "-Wall",'
                if code.count(needle)!=2: raise ValueError('Unexpected architectural compile commands')
                code=code.replace(needle,needle+' *(["-DHYBRID_BUFFER"] if variant_manifest["variants"][mode].get("hybrid_buffer_early") else []),')
            if any(vm['variants'][mode].get('buffer_hit_during_drain') for mode in args.modes):
                needle='"/usr/bin/iverilog", "-g2012", "-Wall",'
                if code.count(needle)!=2: raise ValueError('Unexpected architectural compile commands')
                code=code.replace(needle,needle+' *(["-DBUFFER_DRAIN"] if variant_manifest["variants"][mode].get("buffer_hit_during_drain") else []),')
            if any(vm['variants'][mode].get('raw_operand_recovery') for mode in args.modes):
                needle='"/usr/bin/iverilog", "-g2012", "-Wall",'
                if code.count(needle)!=2: raise ValueError('Unexpected architectural compile commands')
                code=code.replace(needle,needle+' *(["-DRAW_OPERAND_RECOVERY"] if variant_manifest["variants"][mode].get("raw_operand_recovery") else []),')
            if any(vm['variants'][mode].get('speculative_overlap') for mode in args.modes):
                needle='"/usr/bin/iverilog", "-g2012", "-Wall",'
                if code.count(needle)!=2: raise ValueError('Unexpected architectural compile commands')
                code=code.replace(needle,needle+' *(["-DSPECULATIVE_OVERLAP"] if variant_manifest["variants"][mode].get("speculative_overlap") else []),')
            if any(vm['variants'][mode].get('response_ready_factored') for mode in args.modes):
                needle='"/usr/bin/iverilog", "-g2012", "-Wall",'
                if code.count(needle)!=2: raise ValueError('Unexpected architectural compile commands')
                code=code.replace(needle,needle+' *(["-DRESPONSE_READY_FACTORED"] if variant_manifest["variants"][mode].get("response_ready_factored") else []),')
            if any(vm['variants'][mode].get('raw_launch_factored') for mode in args.modes):
                needle='"/usr/bin/iverilog", "-g2012", "-Wall",'
                if code.count(needle)!=2: raise ValueError('Unexpected architectural compile commands')
                code=code.replace(needle,needle+' *(["-DRAW_LAUNCH_FACTORED"] if variant_manifest["variants"][mode].get("raw_launch_factored") else []),')
            if any(vm['variants'][mode].get('registered_prediction_mismatch') for mode in args.modes):
                needle='"/usr/bin/iverilog", "-g2012", "-Wall",'
                if code.count(needle)!=2: raise ValueError('Unexpected architectural compile commands')
                code=code.replace(needle,needle+' *(["-DREGISTERED_PREDICTION_MISMATCH"] if variant_manifest["variants"][mode].get("registered_prediction_mismatch") else []),')
            if any(vm['variants'][mode].get('registered_wb_match') for mode in args.modes):
                needle='"/usr/bin/iverilog", "-g2012", "-Wall",'
                if code.count(needle)!=2: raise ValueError('Unexpected architectural compile commands')
                code=code.replace(needle,needle+' *(["-DWB_MATCH"] if variant_manifest["variants"][mode].get("registered_wb_match") else []),')
            (run/'architecture_runner.py').write_text(code,encoding='utf-8')
            h.snapshot(source,run/'original_architecture_runner.py')
            record['architecture_runner_sha256']=h.sha(run/'architecture_runner.py'); save()
            passed=h.command([sys.executable,'-B',run/'architecture_runner.py'],run,'architecture',7200)==0
            record['status']='passed' if passed else 'architecture_failed'
            if not passed: raise RuntimeError('Architecture gate failed')
    except Exception as error:
        record.update(status='failed',error=str(error)); raise
    finally: save()
    print('DONE '+str(run),flush=True)


if __name__=='__main__': main()
