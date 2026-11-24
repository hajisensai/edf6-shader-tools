English | [简体中文](CONTRIBUTING.zh-CN.md)

# Contributing

This repository holds **tools only**. PRs that improve the tool are welcome: new checks, better error messages, support for more of the format, another decompiler backend, documentation, and tests.

## What may and may not be committed

| May be committed | Reason |
| --- | --- |
| Tool code (`*.py`) and tests | The tools contain no game content |
| Documentation, including what you learned about the SGO / DXBC layout, written in your own words | Our own descriptions |
| Small synthetic test shaders written inline in a test, like `tests/test_shader_sgo.py` | Written from scratch, compiled at test time |

| Must not be committed | Reason |
| --- | --- |
| SGO, CPK, DXBC / CSO files, or any file that starts with their magic bytes | Game data |
| Disassembly or decompiled HLSL of game shaders, whether edited or not | Mechanically derived from the game; amounts to redistributing game code |
| Shader source files (`.hlsl`, `.hlsli`, `.fx`, `.asm` …), even ones you wrote yourself | A decompiled game shader is hard to tell from an original one, so the repository takes none |
| `manifest.json` / `provenance.json` from `extract`, screenshots of game assets, large binaries | Tool output and game content |

To share an edited shader, release it yourself the way mods are released, and point people at this tool to apply it.

`tools/lint_repo.py` blocks these automatically:

- **By name**: suffix, plus the output file names `manifest.json` and `provenance.json`.
- **By content**: file magic, binary content, and any file over 512 KiB.
- **By generator text**: the banners and declarations that shader disassemblers and decompilers write.

On PRs, CI also checks every commit with `--history`, so a file added and deleted again inside the PR is still caught. When something is blocked, do not work around it.

> **The lint and the install check record provenance; they are not a security boundary.** They catch accidental commits and record which files an output came from. Both can be bypassed on purpose. Whether something may be committed is decided in the end by the tables above and by the reviewer.

## Registering a new game build

When the game updates, `DX11.cpk` changes and the install check reports it as unregistered or unofficial. Once you have confirmed through Steam that the new file is official, open a PR that adds a row to [known-builds.tsv](known-builds.tsv) with its SHA-256, SHA1, size, Steam buildid, depot and manifest ID. The SHA1 and IDs come from Steam's depot manifest, and `verify_install.py --json` prints them. Also check whether the tests and the README still describe the new build correctly.

## Before submitting

```powershell
python -B tools/lint_repo.py
python -B -m unittest discover -s tests
```

The repack tests compile small shaders with `d3dcompiler_47.dll`, so they run only on Windows. CI runs them on a Windows runner as well.

If your change affects how SGOs are read or written, also run it on your own copy of the game: export a file, repack it without replacements, and confirm the output is byte-identical to the source. Say in the PR which files you tried.
