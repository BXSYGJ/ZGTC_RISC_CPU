# Moderate clock tradeoff candidates

Standalone clock preparation only; no active CPU build or accepted baseline changes. The revised goal permits lower clock only while preserving absolute CoreMark and execution/resource efficiency. These are candidate configurations, not routed or hardware-qualified frequencies.

| Requested CPU Hz | Input divide | Multiplier | Feedback divide | Output divide | VCO MHz | PFD MHz |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 153000000 | 1 | 1 | 34 | 6 | 918 | 27 |
| 154285714 | 1 | 2 | 20 | 7 | 1080 | 27 |
| 155250000 | 2 | 1 | 69 | 6 | 931.5 | 13.5 |

The middle setting generates exactly 1080000000/7 Hz; the integer configuration rounds down by 2/7 Hz. This sub-hertz representation difference is explicit, not an oscillator measurement. Native vendor model tests verify frequency and reset/relock. The installed vendor divider algorithm states GPLL VCO 600-1200 MHz and PFD 10-450 MHz. Physical implementation and matching rebuilt firmware are still mandatory.

## September 10 native simulation

WSL Icarus 11.0 passes all four test methods, including 153 MHz, 154.285714 MHz, 155.25 MHz and unchanged 157.5 MHz frequency/relock checks, three wrong-divider runtime rejections, exact source delta, and static bounds. The selected final CPU-stage PLL also passes native 154.285714 MHz frequency/relock testing.

The initial Windows Icarus 12.0 development build reports mismatches for three frequencies, including an independent run of the unchanged accepted 157.5 MHz PLL. WSL passes that same unchanged source. The Windows failure log is retained; it is not reclassified as a passing test, and the underlying simulator/model interaction has not been diagnosed. No RTL divider was changed to mask that failure. WSL is the qualified local simulation workflow.

