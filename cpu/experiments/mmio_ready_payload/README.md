# MMIO payload ready capture

This isolated candidate captures MMIO payload only while its pending-request register is empty. The original valid/ready MMIO acceptance rule and all ownership logic remain unchanged. It targets a measured address-decode-to-payload-CE critical path, not a speculative interface change.

Use i8.json/i9.json for parameter-only short simulations. See ../../docs/MMIO_READY_PAYLOAD.md for cycle-equivalence tests, compiled negative controls, implementation evidence and unverified boundaries. Production RTL is unchanged.
