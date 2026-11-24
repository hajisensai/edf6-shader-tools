[English](CONTRIBUTING.md) | 简体中文

# 参与贡献

本仓库**只放工具**。欢迎改进工具的 PR：新的检查、更好的报错信息、支持更多格式内容、换一个反编译后端、文档和测试。

## 能提交什么、不能提交什么

| 可以提交 | 原因 |
| --- | --- |
| 工具代码（`*.py`）和测试 | 工具本身不含游戏内容 |
| 文档，包括你对 SGO / DXBC 布局的理解，用自己的话写 | 我们自己的描述 |
| 像 `tests/test_shader_sgo.py` 那样直接写在测试里的小型合成测试着色器 | 从零写的，测试时才编译 |

| 不能提交 | 原因 |
| --- | --- |
| SGO、CPK、DXBC / CSO 文件，或任何以它们的文件头开头的文件 | 游戏数据 |
| 游戏着色器的反汇编或反编译 HLSL，无论改没改过 | 由游戏机械转换而来，等于重新分发游戏代码 |
| 着色器源文件（`.hlsl`、`.hlsli`、`.fx`、`.asm` 等），即使是你自己写的 | 反编译出的游戏着色器很难和原创的区分开，所以仓库一律不收 |
| `extract` 写出的 `manifest.json` / `provenance.json`、游戏素材截图、大型二进制文件 | 工具产物和游戏内容 |

想分享改好的着色器，请像发布 mod 一样自己发布，并告诉大家用本工具来应用。

`tools/lint_repo.py` 会自动拦截这些内容：

- **按文件名**：后缀，以及产物文件名 `manifest.json` 和 `provenance.json`。
- **按内容**：文件头、二进制内容，以及超过 512 KiB 的文件。
- **按生成器文字**：着色器反汇编器和反编译器写出的标题与声明。

PR 上 CI 还会用 `--history` 逐个检查每个提交，所以在 PR 中途加上又删掉的文件也会被拦下。被拦截时不要想办法绕过。

> **lint 和安装校验只用来记录来源，不是安全边界。** 它们能拦住无意的提交，并记录产物来自哪些文件，但都可以被故意绕过。最终能不能提交，由上面两张表和审核人判断。

## 登记新的游戏版本

游戏更新后 `DX11.cpk` 会变，安装校验会报告它未登记或非官方。通过 Steam 确认新文件是官方原版后，开一个 PR，在 [known-builds.tsv](known-builds.tsv) 加一行，写明 SHA-256、SHA1、大小、Steam buildid、depot 和 manifest ID。SHA1 和这些 ID 来自 Steam 的 depot 清单，`verify_install.py --json` 会输出它们。同时检查测试和 README 对新版本的描述是否仍然正确。

## 提交前

```powershell
python -B tools/lint_repo.py
python -B -m unittest discover -s tests
```

回包测试用 `d3dcompiler_47.dll` 编译小型着色器，所以只在 Windows 上运行。CI 也会在 Windows runner 上跑它们。

如果你的改动影响 SGO 的读写，还要在自己的游戏上试一遍：导出一个文件，不做替换直接回包，确认输出与源文件逐字节相同。在 PR 里写明试了哪些文件。
