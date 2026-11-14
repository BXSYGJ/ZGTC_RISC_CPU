// symphony_state: pixel-domain history and the single physical KEY1 controller.
// Times are result-arrival uptime milliseconds, never inferred audio onsets.
module symphony_state #(
    parameter PIXEL_HZ = 148500000,
    parameter HISTORY_DEPTH = 64,
    parameter DEBOUNCE_MS = 20,
    parameter LONG_PRESS_MS = 900,
    parameter DOUBLE_CLICK_MS = 300
) (
    input wire pix_clk,
    input wire pix_rst_n,
    input wire frame_start,
    input wire key1_n,
    input wire result_update,
    input wire [2:0] result_class,
    input wire [63:0] result_percentages,
    input wire [5:0] rd_index,
    input wire rd_all,
    output reg page_library,
    output reg [3:0] filter_class,
    output reg [5:0] selected_index,
    output reg [6:0] item_count,
    output reg [6:0] history_count,
    output reg [31:0] result_time_ms,
    output reg [31:0] result_sequence,
    output reg selected_valid,
    output wire [2:0] selected_class,
    output wire [7:0] selected_confidence,
    output wire [31:0] selected_time_ms,
    output wire [31:0] selected_sequence,
    output reg selected_bookmark,
    output reg rd_valid,
    output wire [2:0] rd_class,
    output wire [7:0] rd_confidence,
    output wire [31:0] rd_time_ms,
    output wire [31:0] rd_sequence,
    output reg rd_bookmark,
    output reg [31:0] dropped_results
);
    localparam MS_CYCLES = PIXEL_HZ / 1000;
    reg [31:0] ms_divider;
    reg [31:0] uptime_ms;
    wire ms_tick = (ms_divider == MS_CYCLES - 1);
    wire [31:0] arrival_ms = uptime_ms == 32'hffffffff ? uptime_ms : uptime_ms + (ms_tick ? 32'd1 : 32'd0);

    reg key_meta, key_sync, key_stable;
    reg [31:0] debounce_ms, held_ms, click_ms;
    reg pressed, long_sent, click_wait, second_press;
    reg event_short, event_double, event_long;

    always @(posedge pix_clk or negedge pix_rst_n) begin
        if (!pix_rst_n) begin
            ms_divider <= 0; uptime_ms <= 0;
            key_meta <= 1; key_sync <= 1; key_stable <= 1;
            debounce_ms <= 0; held_ms <= 0; click_ms <= 0;
            pressed <= 0; long_sent <= 0; click_wait <= 0; second_press <= 0;
            event_short <= 0; event_double <= 0; event_long <= 0;
        end else begin
            key_meta <= key1_n;
            key_sync <= key_meta;
            event_short <= 0; event_double <= 0; event_long <= 0;
            if (ms_tick) begin
                ms_divider <= 0;
                if (uptime_ms != 32'hffffffff) uptime_ms <= uptime_ms + 1;
                if (click_wait && !pressed) begin
                    if (click_ms >= DOUBLE_CLICK_MS - 1) begin
                        event_short <= 1; click_wait <= 0; click_ms <= 0;
                    end else click_ms <= click_ms + 1;
                end
                if (pressed && !long_sent) begin
                    if (held_ms >= LONG_PRESS_MS - 1) begin
                        event_long <= 1; long_sent <= 1;
                        click_wait <= 0; second_press <= 0;
                    end else held_ms <= held_ms + 1;
                end
                if (key_sync == key_stable) debounce_ms <= 0;
                else if (debounce_ms >= DEBOUNCE_MS - 1) begin
                    debounce_ms <= 0;
                    key_stable <= key_sync;
                    if (!key_sync) begin
                        pressed <= 1; held_ms <= 0; long_sent <= 0;
                        second_press <= click_wait;
                        click_wait <= 0;
                    end else begin
                        pressed <= 0;
                        if (!long_sent && held_ms < LONG_PRESS_MS - 1) begin
                            if (second_press) begin
                                event_double <= 1; second_press <= 0; click_wait <= 0;
                            end else begin
                                click_wait <= 1; click_ms <= 0;
                            end
                        end
                    end
                end else debounce_ms <= debounce_ms + 1;
            end else ms_divider <= ms_divider + 1;
        end
    end

    // Data payloads are never reset. Counts, pointers and flags delimit validity.
    // Payload: sequence[74:43], arrival_ms[42:11], class[10:8], percent[7:0].
    reg [74:0] history [0:HISTORY_DEPTH-1];
    reg [2:0] class_meta [0:HISTORY_DEPTH-1];
    reg [HISTORY_DEPTH-1:0] bookmarks;
    reg [5:0] write_ptr;
    reg [74:0] pending [0:3];
    reg [1:0] pending_read, pending_write;
    reg [2:0] pending_count;
    reg update_previous;
    reg [31:0] capture_sequence;
    wire incoming = result_update && !update_previous;
    wire commit = frame_start && pending_count != 0;
    wire enqueue = incoming && (pending_count < 4 || commit);
    wire [7:0] winner_percent = result_percentages[result_class * 8 +: 8];

    reg short_pending, double_pending, long_pending;
    wire do_long = long_pending || event_long;
    wire do_double = !do_long && (double_pending || event_double);
    wire do_short = !do_long && !do_double && (short_pending || event_short);
    reg next_page;
    reg [3:0] next_filter;
    reg [5:0] next_selection;
    always @* begin
        next_page = page_library;
        next_filter = filter_class;
        next_selection = selected_index;
        if (do_long) next_page = !page_library;
        else if (do_short) begin
            if (!page_library) begin
                if (filter_class == 8) next_filter = 0;
                else if (filter_class == 7) next_filter = 8;
                else next_filter = filter_class + 1;
                next_selection = 0;
            end else if (item_count != 0) begin
                if ({1'b0, selected_index} + 1 >= item_count) next_selection = 0;
                else next_selection = selected_index + 1;
            end
        end
    end

    // Rebuild the small filtered address index during vertical blanking.
    // A scan takes at most HISTORY_DEPTH clocks after frame_start. Readers
    // expose rd_valid=0 while it runs; active pixels start much later.
    reg [5:0] filtered_index [0:HISTORY_DEPTH-1];
    reg scan_active, mapping_ready, refresh_selected;
    reg [5:0] scan_ptr;
    reg [6:0] scan_position, scan_total, scan_matches;
    reg [3:0] scan_filter;
    wire scan_match = scan_filter == 8 || class_meta[scan_ptr] == scan_filter;
    wire [6:0] scan_final_count = scan_matches + (scan_match ? 7'd1 : 7'd0);
    reg [74:0] selected_payload;
    reg [74:0] read_payload;
    reg [5:0] read_address;
    reg read_allowed;
    always @* begin
        read_address = 0;
        read_allowed = 0;
        if (rd_all) begin
            if ({1'b0, rd_index} < history_count) begin
                read_address = (write_ptr + HISTORY_DEPTH - 1 - rd_index) & (HISTORY_DEPTH - 1);
                read_allowed = 1;
            end
        end else if (mapping_ready && {1'b0, rd_index} < item_count) begin
            read_address = filtered_index[rd_index];
            read_allowed = 1;
        end
    end
    assign selected_class = selected_payload[10:8];
    assign selected_confidence = selected_payload[7:0];
    assign selected_time_ms = selected_payload[42:11];
    assign selected_sequence = selected_payload[74:43];
    assign rd_class = read_payload[10:8];
    assign rd_confidence = read_payload[7:0];
    assign rd_time_ms = read_payload[42:11];
    assign rd_sequence = read_payload[74:43];

    always @(posedge pix_clk or negedge pix_rst_n) begin
        if (!pix_rst_n) begin
            page_library <= 0; filter_class <= 8; selected_index <= 0;
            item_count <= 0; history_count <= 0; write_ptr <= 0;
            result_time_ms <= 0; result_sequence <= 0; capture_sequence <= 0;
            bookmarks <= 0; dropped_results <= 0;
            pending_read <= 0; pending_write <= 0; pending_count <= 0;
            update_previous <= 0;
            short_pending <= 0; double_pending <= 0; long_pending <= 0;
            scan_active <= 0; mapping_ready <= 1; refresh_selected <= 0;
            scan_ptr <= 0; scan_position <= 0; scan_total <= 0; scan_matches <= 0; scan_filter <= 8;
            selected_valid <= 0; selected_payload <= 0; selected_bookmark <= 0;
            rd_valid <= 0; read_payload <= 0; rd_bookmark <= 0;
        end else begin
            update_previous <= result_update;
            if (event_short) short_pending <= 1;
            if (event_double) double_pending <= 1;
            if (event_long) long_pending <= 1;
            if (incoming) begin
                capture_sequence <= capture_sequence + 1;
                if (!enqueue && dropped_results != 32'hffffffff) dropped_results <= dropped_results + 1;
            end
            if (enqueue) begin
                pending[pending_write] <= {capture_sequence + 32'd1, arrival_ms, result_class, winner_percent};
                pending_write <= pending_write + 1;
            end
            case ({enqueue, commit})
                2'b10: pending_count <= pending_count + 1;
                2'b01: pending_count <= pending_count - 1;
                default: begin end
            endcase
            if (commit) begin
                history[write_ptr] <= pending[pending_read];
                class_meta[write_ptr] <= pending[pending_read][10:8];
                bookmarks[write_ptr] <= 0;
                result_time_ms <= pending[pending_read][42:11];
                result_sequence <= pending[pending_read][74:43];
                pending_read <= pending_read + 1;
                if (write_ptr == HISTORY_DEPTH - 1) write_ptr <= 0;
                else write_ptr <= write_ptr + 1;
                if (history_count < HISTORY_DEPTH) history_count <= history_count + 1;
            end
            if (frame_start) begin
                page_library <= next_page;
                filter_class <= next_filter;
                selected_index <= next_selection;
                short_pending <= 0; double_pending <= 0; long_pending <= 0;
                if (do_double) begin
                    if (!page_library && (history_count != 0 || commit)) begin
                        if (commit) bookmarks[write_ptr] <= 1;
                        else if (write_ptr == 0) bookmarks[HISTORY_DEPTH-1] <= 1;
                        else bookmarks[write_ptr-1] <= 1;
                    end else if (page_library && mapping_ready && {1'b0, selected_index} < item_count) begin
                        if (!commit || filtered_index[selected_index] != write_ptr)
                            bookmarks[filtered_index[selected_index]] <= !bookmarks[filtered_index[selected_index]];
                    end
                end
                scan_position <= 0; scan_matches <= 0; scan_filter <= next_filter;
                mapping_ready <= 0; selected_valid <= 0;
                if (commit && history_count < HISTORY_DEPTH) scan_total <= history_count + 1;
                else scan_total <= history_count;
                if (commit) scan_ptr <= write_ptr;
                else if (write_ptr == 0) scan_ptr <= HISTORY_DEPTH - 1;
                else scan_ptr <= write_ptr - 1;
                if (history_count != 0 || commit) scan_active <= 1;
                else begin
                    scan_active <= 0; item_count <= 0; selected_index <= 0; mapping_ready <= 1;
                end
            end else if (scan_active) begin
                if (scan_match) begin
                    filtered_index[scan_matches] <= scan_ptr;
                    scan_matches <= scan_matches + 1;
                end
                if (scan_position + 1 >= scan_total) begin
                    scan_active <= 0; mapping_ready <= 1;
                    item_count <= scan_final_count;
                    if ({1'b0, selected_index} >= scan_final_count) selected_index <= 0;
                    refresh_selected <= 1;
                end else begin
                    scan_position <= scan_position + 1;
                    if (scan_ptr == 0) scan_ptr <= HISTORY_DEPTH - 1;
                    else scan_ptr <= scan_ptr - 1;
                end
            end
            if (refresh_selected) begin
                refresh_selected <= 0;
                if (mapping_ready && item_count != 0) begin
                    selected_payload <= history[filtered_index[selected_index]];
                    selected_bookmark <= bookmarks[filtered_index[selected_index]];
                    selected_valid <= 1;
                end else begin
                    selected_payload <= 0; selected_bookmark <= 0; selected_valid <= 0;
                end
            end
            rd_valid <= read_allowed;
            if (read_allowed) begin
                read_payload <= history[read_address];
                rd_bookmark <= bookmarks[read_address];
            end else begin
                read_payload <= 0; rd_bookmark <= 0;
            end
        end
    end
endmodule
