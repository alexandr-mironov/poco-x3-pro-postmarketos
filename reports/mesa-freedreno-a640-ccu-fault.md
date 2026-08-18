# Mesa bug report draft — freedreno a640: GPU translation fault from CCU

Ready to file at https://gitlab.freedesktop.org/mesa/mesa/-/issues — not submitted yet,
that needs the maintainer's own freedesktop account.

---

**Title:** freedreno/a6xx: GPU translation fault from CCU during compositor readback (Adreno 640)

## System information

| | |
|---|---|
| Device | Xiaomi POCO X3 Pro (`xiaomi-vayu`), SM8150 / Snapdragon 860 |
| GPU | Adreno 640 — `GL_RENDERER: FD640`, revision 640 (6.4.0.1) |
| Mesa | 26.1.6 |
| GL | OpenGL ES 3.2, `GL_VENDOR: freedreno` |
| Kernel | 7.0.0-sm8150 (postmarketOS SM8150 tree) |
| OS | postmarketOS edge, aarch64, systemd |
| Compositor | phoc 0.56.0 (wlroots 0.20.x), Phosh 0.56.0 |

## Description

The GPU takes a translation fault while the compositor renders a window into an
off-screen buffer. The kernel's hangcheck then resets the GPU, every texture is lost, and
the compositor has to recreate its renderer. Visually the wallpaper disappears and another
window's contents can end up drawn as the background until that window is closed.

The faulting unit is always CCU, the access is always a read, and the fault type is always
TRANSLATION:

```
*** gpu fault: ttbr0=0000000120a41000 iova=0000000102420000 dir=READ type=TRANSLATION source=CCU (0,0,0,1)
adreno 2c00000.gpu: [drm:a6xx_irq] *ERROR* gpu fault ring 0 fence 144fe status 00800005 rb 0107/0107 ib1 000000010041E000/0000 ib2 0000000100446400/0000
msm_dpu ae01000.display-controller: [drm:recover_worker] *ERROR* 6.4.0.1: hangcheck recover!
msm_dpu ae01000.display-controller: [drm:recover_worker] *ERROR* 6.4.0.1: offending task: phoc
revision: 640 (6.4.0.1)
rb 0: fence: 132145/132146
```

Occasionally the same iova faults several times in a row with `type=UNKNOWN` mixed in:

```
*** gpu fault: ttbr0=000000016279f000 iova=0000000102ed0000 dir=READ type=TRANSLATION source=CCU (0,0,0,1)
*** gpu fault: ttbr0=000000016279f000 iova=0000000102ed0000 dir=READ type=UNKNOWN     source=CCU (0,0,0,1)
```

## Reproducer

Any Phosh session on this device. Opening the overview makes the shell request window
thumbnails, which sends phoc down `phoc_renderer_render_view_to_buffer()` — it renders a
view into an shm buffer via `wlr_render_pass_add_texture()`. Doing that repeatedly,
especially right after an application starts and its first frames are still being drawn,
reproduces the fault within minutes of ordinary use.

Frequency during normal use was roughly 1.8 faults per minute over an 82 minute session
(148 faults, 5 hangcheck resets).

Note that `glmark2-es2-wayland` does **not** reproduce it — 16 runs across four scenes
produced zero faults. Whatever the trigger is, it is specific to the readback path rather
than to ordinary rendering.

## Partial workaround

`FD_MESA_DEBUG=sysmem` drops the rate by roughly an order of magnitude — 5 faults and 1
reset over the following 68 minutes, and those five all landed inside a deliberate stress
test of the overview. It does not eliminate the fault. That GMEM/tiling changes the
frequency but not the outcome may help narrow down where the bad address comes from.

Measured cost of the workaround on this device is about 2% (glmark2, four scenes, two runs
each), which is within run-to-run variance.

## Downstream note

The fault takes the whole session down, because phoc dereferences the texture without
checking it: after the reset `wlr_surface_get_texture()` returns NULL and
`wlr_render_pass_add_texture()` uses it straight away, so the compositor segfaults. That is
a separate phoc issue and is fixed downstream by
`patches/upstreamable/0003-phoc-render-skip-surfaces-without-a-texture.patch` in this
repository; with it applied the session survives the GPU reset and only the visual
corruption remains.
