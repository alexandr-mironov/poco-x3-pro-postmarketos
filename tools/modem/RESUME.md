# RESUME — cellular / QLINK reverse (pick-up point)

Last worked: 2026-08-20. Goal unchanged: make cellular work on vayu/pmOS.

## Where we are (one line)
Second crash is a **QLINK high-gear (8.5 Gbps) SerDes link failure** — known
sm8150-wide wall. To see the failure mode we must read the paged RFLM code,
which is **q6zip-compressed** in the modem. We are pinning the leaf
`q6zip_uncompress` so we can decompress it with the working Ghidra emulator.

## What is RUNNING on the build host (survives session end, nohup)
- `~node1/find5.py` -> writes `~node1/find5-results.txt` incrementally.
  Scans the CUB3D-analysed project for functions **called with 5 args**
  (the q6zip ABI). When done, the tail of that file lists candidate targets;
  the decompressor is among the leaf ones. Log: `~node1/find5.log` (ends "DONE").
  Check first on resume: `ssh node1 'tail -40 ~/find5-results.txt'`.

## Validated this session (big: the emulator works)
- Ghidra emulation ported to **PyGhidra** (Jython is dead in Ghidra 12):
  `~node1/emu_test.py` runs real Hexagon code (memscpy) under `EmulatorHelper`,
  skips unimplemented `CALLOTHER` (dcache_fetch/l2fetch/isync) by advancing PC
  past the packet, and copies bytes correctly. So: **any decompressor candidate
  can be run and its output checked** for valid Hexagon.
  - Note: JPype (CPython) cannot subclass `BreakCallBack` (abstract class), so we
    skip callother packets instead of registering no-op callbacks. Fine for the
    pure-compute decompressor; if it corrupts output, compile a tiny Java no-op
    `BreakCallBack` and load it via JPype.

## Known q6zip facts (from CUB3D q6zip_emu.py, our RE)
- ABI: `decompress(r0=out, r1=&out_size, r2=block_ptr, r3=block_size, r4=dict)`.
  Section: `[u16 nb][dict 0x5000][index nb*4 absolute ptrs][blocks]`.
- Region 1 (`in_buf=c8cef000`, nb=37 -> `d0000000..d04fa000`) is memscpy-copied,
  i.e. **uncompressed here** — NOT a q6zip test block.
- RFLM code lives in the **`d8000000..da000000`** paged space (resident thunks
  `jump ##0xd95fd950` etc.); its compressed source + section header + decompressor
  entry are the missing pieces. seg23 (`c6f20000`, 30MB, entropy 7.73) is the
  likely compressed blob.

## Next steps (in order)
1. Read `~node1/find5-results.txt`; take the leaf 5-arg-called targets.
2. Find a real q6zip section (in_buf) — a `[u16 nb][0x5000 dict][abs-ptr index]`
   layout, index pointers into the blocks. Search for the driver (reads u16 nb,
   uses `+0x5000`, calls a 5-arg fn in a loop).
3. For each (decompressor, block) pair, emulate with the harness (base on
   `emu_test.py`) and check output = valid Hexagon packets -> that IS the
   decompressor. Then port `q6zip_emu.py` fully and dump the section.
4. Load the decompressed image at its VA in Ghidra, read `rflm_qlnk` / `qsf_hl_seq`
   to get the failure mode (timeout vs mis-alignment) -> points at the AP resource
   or the EFS/gear knob.

## Staged infra on build host `node1@192.168.1.248` (`sudo` nopasswd)
- `~node1/bin/qemu-hexagon` (v9.1.0, built), `~node1/qemu-src`
- `~node1/llvm-build/bin/` clang+lld+llvm-mc with **Hexagon** target (proven:
  `clang --target=hexagon-unknown-linux-musl -nostdlib -static -ffreestanding
  -fuse-ld=lld` + qemu-hexagon runs, trap0 write() works)
- Ghidra 12.1.3 at `~node1/ghidra-inst`, PyGhidra venv `~node1/pgvenv`
- Native-Hexagon project: `~node1/ghidra-proj` (name `modemproj`)
- **CUB3D** project: `~node1/cubproj` (name `cub`, QDSP6 language, 25607 funcs,
  relocations applied) + plugin in `~node1/.config/ghidra/.../Extensions/Hexagon_U`
- `~node1/modem.mbn` (the image), `~node1/qualcomm-q6zip`, `~node1/qbb`,
  `~node1/ghidra-hexagon-sleigh` (CUB3D scripts incl q6zip_emu.py / dlpager_emu.py)

## Phone / device state (safe to leave)
- Modem firmware **reverted to stock** (`modem.mbn.vayu-orig` restored; the
  cross-device OnePlus swap failed auth `-22`, reverted). Modem `running`.
- rmtfs is writable (`-P -s`, no `-r`) for EFS experiments; stand installed.
- A stale wrong-sized `/rflm_debug/rflm_qlnk_debug.dat` may be present (ignored).

## Blackbox tracks tried (dead-ended, for the record)
- Firmware swap: cross-device fails PAS auth; a vayu-specific version would need
  sourcing and is environmentally likely the same.
- EFS: no gear-force knob exists; `rflm_qlnk_debug.dat` (cdr_retrain) tried at
  3 and 12 bytes, no effect (gated or ineffective).
- AP resources: all identifiable ones (pins, LDOs, rf_clk1/2/3, CX/MSS pd, AOSS
  QMP, memory) already match stock.
