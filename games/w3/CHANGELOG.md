# Changelog: The Witcher 3: Wild Hunt on the Zelda-line runtime

Each entry says what was found, what was done and how it was checked. Version 4.04b (update 0100E67012924800 of the
American release 0100E67012924000: main build ID b151a224…, sdk d5a1029a…; `assets/expected-4.04b.json`).

## 2026-11-24 — self-contained app (Mac)

- **Found**: the first `The Witcher 3.app` was a launcher shell over the external `~/w3_local` work folder
  (`MNGWorkFolder` in Info.plist), so Finder and Storage reported ~1.8 MB for the app while the game's 20 GB of data
  lived outside it — unlike the other ports, whose apps carry the game files.
- **Fix**: `scripts/package_app.py` now APFS-clones the runtime, `rewritten/local` and the three RomFS files into
  `Contents/Resources/game` (zero extra space on the same volume); `app/launcher.c` finds that folder from its own
  executable path and chdirs there, instead of reading `MNGWorkFolder`. Player saves/cache stay in
  `~/Library/Application Support/MacNativeGames/W3`, so the app is self-contained but the save folder is unaffected.
- **Checked**: a 20 GB `cp -c` completed in 0.002 s with ~48 KB of metadata used; app builds to ~20 GB, passes
  `codesign --verify --deep --strict` and `--check`, and launches to the title from Finder.

## 2026-11-24 — the eShop applet crash (Mac)

- **Found**: a windowed session with scripted A/B/A presses ran ~117 s / 3600 frames, then SIGSEGV (signal 0xb,
  fault 0x0). Symbolising the guest stack from `runtime_tables.h` gave the exact chain:
  `nn::ec::ShowShopAddOnContentList` (sdk+0x2e8c40) → `ShowShopAddOnContentListImpl` (+0x2eb670) →
  `nn::ec::detail::ShowShopPage` (+0x2ef470) → `nn::applet::CreateLibraryApplet` (+0x1c5cd0) →
  `StartLibraryAppletImmediately` (+0x1c62a0), whose `LDR X8,[X0]` read a null `LibraryAppletHandle`. Decoded at
  +0x1c6430: `0xf9400008` = `ldr x8,[x0]`, x0=0. The game's title/menu eShop (DLC) entry tries to start a shop
  library applet; the host has no applet proxy, and `CreateLibraryApplet` reported success with an empty handle.
- **Fix**: as the other ports' `ShowShop` no-ops do, answer "the applet could not start" so the SDK's own failure path
  returns the player to the menu. The `ShowShop*` entry points are SDK-internal (not in the GOT, so a symbol override
  cannot reach them), but `nn::applet::CreateLibraryApplet` is a GOT import (kind 1026). `applet_host.c` now overrides
  it: log the applet id/mode, zero the handle and return a failed `nn::Result` (0xc4400000). W3's software keyboard is
  its own implementation (`swkbd_host.c`), so no input path depends on this applet.
- **Checked**: `[totk] CreateLibraryApplet: host stub bound at GOT resolution` at startup confirms the GOT entry resolves
  to the host stub; 14 W3 unit tests pass; headless and windowed runs pass frame 3900 with no signal. The crash is
  timing/path dependent and was not re-triggered in the verification runs, so the stub is verified at the binding
  level, not by reproducing the original crash.

## 2026-11-24 — macOS 27: the 48 GiB VAMM region above the 39-bit line (Mac)

- **Startup crash**: `main`+0x5d70's constructor called `AllocateAddressRegion(0xc00000000)`, but macOS 27 leaves only
  9 + 10 + 20 GiB of fragmented free space below 2^39. The SDK returned 0x1803, then `AllocateMemoryPages(NULL)` 0xe03
  and SIGTRAP before the first frame; shrinking the request only moved the crash to the game's own 48 GiB address
  arithmetic (`AllocateMemoryPages(0x7c40000000, 0x6e900000)`). Clamping the SDK result is not enough.
- **Fix**: as `games/pla` does for its 32 GiB region, host this game's VAMM region above the 39-bit line as a 64 GiB
  lazy-commit mapping at 0x100_0000_0000. `GetInfo(2/3)` now reports VAMM, not the small alias region;
  `MapPhysicalMemory`, `QueryMemory`, permission ops and scoped-stack sources route VAMM addresses to the new
  `vamm_map`/`vamm_pages`, while stack, heap and alias keep their normal low addresses. Physical-memory calls book
  against a wide lazy-commit budget (16 GiB); heap commits still use the retail pool (`GetInfo(6/21)`).
- **IPC**: HIPC descriptors carry only 39 address bits, so an audio buffer in VAMM reached the host as 0x690000000
  and faulted. `shared/runtime/ipc.c` now has a weak `runtime_ipc_address` hook (identity by default, so other
  games are unchanged); W3's strong hook restores the high bits of addresses in the VAMM mirror window.
- **Checked**: the constructor gets `AllocateAddressRegion size=c00000000 result=0 address=10040000000`, reaches the
  title/menu, and runs 600 frames at frame p50 33.33 ms / p95 33.52 ms (GPU p50 0.41 ms) with no SIGTRAP/SIGBUS,
  no failed `AllocateMemoryPages`/`MapPhysicalMemory`; 14 W3 unit tests pass.

## 2026-11-23 — from nothing to the first in-engine scene (Mac)

- **Inputs**: the player's base NSP (3.7) and 4.04b update; the update's ExeFS (games/pla `extract_exefs.py`), the merged
  RomFS (games/eow `merge_romfs.py`: 21.4 GB, 795 files, every IVFC block verified). Modules main and sdk only.
- **The rewrite** (`third_party/d2r/patch_nso.py`): two dispatch forms of this compiler. A plain move scheduled between the
  `add x18` and the `br x18` (main+0x135eaec); a table base hoisted out of its loop 50 instructions before the dispatch
  (main+0x13b6f94): the search window is 96 instructions. An unknown form now prints the instructions before it.
- **The runtime**: Persona 5 Royal's (`GAME_W3`), with
  - the NPDM's 4 MB system resource (GetInfo 16): `nn::os` then enables virtual address memory, which a constructor of main
    uses at once (0 left the VammManager uninitialised: a null read in AllocateAddressRegion);
  - `EnableGlobalFileDataCache` / `DisableGlobalFileDataCache` (no-ops, as games/xc3);
  - `nvnQueueBuilderSetQueuePriority` (no-op, as games/totk);
  - nn::hid `BindNpadStyleSetUpdateEvent`, `GetNpadJoyHoldType` (as games/eow), `InitializeGesture`, `GetGestureStates`
    (none, as games/ori); nn::aoc `CheckAddOnContentMountStatus` (mounted: the host's add-on content is files);
  - `nn::account::OpenUser` (shared `account.c`, now for Mario Kart 8 Deluxe and this game);
  - `nn::time::StandardUserSystemClock::now`, `nn::vi::ListFrameHistory` (none, as games/xc3);
  - the shared `audio_out.c`: the audio service never reads AudioOutBuffer's data_offset and this game leaves it
    uninitialised, so the host no longer reads it either;
  - the NVN control section copy reads the section's own size (+0x20) instead of 0x880: one ends at the last byte of an
    address region (the read faulted in `nvnProgramSetShaders`);
  - the crash handler waits up to 10 s for the GPU before exiting (a crash mid-frame had left the GPU busy) and names the
    host function the crash was in.
- **Shaders**: Tears of the Kingdom's translator (`prebuilt` links it; chain `w3-native-v1`). The reflection parser reads
  its packed-bank names for textures and samplers whose handles sit in user constant buffers (`fp_t_cb720898_2000405CSmplr`:
  sampler handle in c10 word 1). The translator and the host judge driver-data reads per word read (`word_offsets`), not
  per vec4: `c2[22].z` is texture handle slot 0 (0x168), next to the image handles; the old rule refused the shader.
- **Checked**: the Saber Interactive logo, the title, the main menu (both expansions), a new game's comic intro, its CGI
  movie and the first in-engine scene with Chinese subtitles; no GPU hang, the GPU idle after every run.
- **The black room**: the game writes render targets as images (compute kernels: its four 1x1 R32F exposure values,
  640x360 R32F / RGBA16F / RGBA8 targets) although they were made without NVN_TEXTURE_FLAGS_IMAGE; the console does not
  check, Metal dropped the writes of textures without ShaderWrite, so exposure and the lit scene stayed black. Every
  uncompressed 2D colour texture of this game is made shader-writable. An image binding to an unwritable texture logs the
  texture's description ([img-unwritable]). Checked: the room, its walls, bed and lights drawn; 30 fps in the scene (frame
  p50 33.33 ms, GPU p50 16 ms).

## 2026-11-23 — gameplay at Kaer Morhen; tessellated terrain as compute (Mac)

- **Gameplay**: the first save (Kaer Morhen, "使用猎魔感官能力寻找卧室钥匙") loads and plays at 30 fps.
- **A tessellated program ended the game** (NVN stage 3, `unsupported NVN stage`): the terrain (mountains, valleys,
  the ground) is drawn with quad tessellation. Metal 4's render encoders have no tessellator (no drawPatches), so a
  tessellated draw now runs as compute (`third_party/d2r_gfx/gfx/nvn/nvn_tess_rt.inc`):
  1. the vertex shader's capture entry (games/totk's geometry capture) writes one 144-word record per vertex;
  2. the control stage runs as a kernel over every patch (Tears of the Kingdom's translator, new `TessService.cs`:
     SPIRV-Cross's multi-patch control kernel, its inputs read from the records);
  3. a tessellator kernel partitions each quad patch from its levels (integer partitioning: the spacing's levels rounded
     up, each edge split by its own level, so neighbouring patches share their edge points exactly);
  4. the evaluation stage runs as an ordinary vertex function over the domain points with the program's fragment shader,
     drawn indirectly (vertex count from the GPU; render stream packet `RS_INDIRECT`).
  The mode comes from the evaluation stage's NVN control section (+0x738 GL_QUADS, +0x73c GL_FRACTIONAL_EVEN, +0x744
  GL_CW); `nvnCommandBufferSetPatchSize` is recorded (OP_PATCH_SIZE). The two stages' interface structs are laid out by
  SPIR-V location on both sides (each declares only what it writes or reads). Found on the way: the capture info block's
  `uint4` is 16-byte aligned in Metal (`tess_capture.pad`; a probe, `W3_TESS_PROBE=<frame>`, showed one record written);
  a tessellation evaluation function's varyings are its `main0_out`; `g_red_once` was 128 entries.
- **Shader-writable textures**: 2D array and 3D colour textures too (a 64x64x5 2D array texture written as an image).
- **Checked** (headless, the Kaer Morhen save): the mountains, valleys, clouds and the tower drawn, no cracks between
  patches; 30 fps (frame p50 33.33 ms, p95 33.5 ms), GPU p50 17 ms (16 ms before tessellation was drawn); about 3,500
  patches a frame through the tessellator; no GPU hang, the GPU idle after the run.
- **Not yet**: triangle and isoline domains, fractional spacing's level blending, indirect tessellated draws; Geralt's
  shirt showed coloured noise once in a window session (not reproduced in four runs since).
