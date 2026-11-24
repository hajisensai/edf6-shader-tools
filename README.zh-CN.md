[English](README.md) | 简体中文

# EDF6 着色器工具（edf6-shader-tools）

导出、修改并回包**你自己的** Steam 版《地球防卫军 6》的 DX11 着色器。

游戏的着色器以编译好的 Direct3D 11 字节码（DXBC）存放在 `DX11.cpk` 中 `SHADER/DX11` 和 `MAP/SHADER/DX11` 下的 SGO 文件里。原版包内有 485 个这样的文件，共 2,237 个 `vs_5_0` 和 2,237 个 `ps_5_0` 槽位。本工具可以列出它们，把任意槽位导出为 DXBC、汇编或反编译出的 HLSL，并把你改过的槽位写成新的 SGO，同时检查每个替换是否仍符合游戏的要求。

## 本仓库包含什么、不包含什么

- **包含**：工具（`shader_sgo.py`）、它的库（`edf6shader/`）、安装校验（`verify_install.py`）和测试。
- **不包含**：任何来自游戏的内容。没有 SGO 文件、着色器字节码、汇编，也没有反编译或改过的游戏着色器。每个人从自己的正版导出，结果只留在自己电脑上。

想分享改好的着色器，请像发布 mod 一样自己发布。CI 会运行 `tools/lint_repo.py`，防止游戏衍生文件进入本仓库，详见 [CONTRIBUTING.zh-CN.md](CONTRIBUTING.zh-CN.md)。

## 环境

- **系统**：Windows。HLSL 编译和反汇编使用系统自带的 `d3dcompiler_47.dll`。
- **Python**：3.12 或更新版本。只用标准库，不需要 `pip install`。
- **导出 HLSL 和用汇编回包时**：需要 3Dmigoto 命令行发布包 [`cmd_Decompiler-1.3.16.zip`](https://github.com/bo3b/3Dmigoto/releases/tag/1.3.16)，EXE 和 DLL 要放在同一目录。只导出 DXBC、或用 HLSL 回包时不需要它。

## 游戏文件必须是官方原版

着色器槽位编号和下面的检查都绑定在某一个具体版本的 `DX11.cpk` 上。工具每次读取 CPK 前，都会先用 Steam 自己的 depot 清单（`steamapps/appmanifest_2291060.acf` 和 `depotcache/*.manifest`）核对这个文件。找不到 Steam 清单时（比如目录是拷来的），改为和 [known-builds.tsv](known-builds.tsv) 里的 SHA-256 比对。

校验不通过时，工具拒绝继续，除非加 `--allow-unofficial`。导出结果会在 `manifest.json` 和 `provenance.json` 里记录判定结果。也可以单独运行校验：

```powershell
python -B verify_install.py "D:/steam/steamapps/common/EARTH DEFENSE FORCE 6" --module DX11.cpk
```

目前已知的官方版本是 Steam buildid `17055427`。

## 导出与回包

```powershell
$cpk = 'D:/steam/steamapps/common/EARTH DEFENSE FORCE 6/DX11.cpk'
$member = 'SHADER/DX11/SND_MECH.SGO'
$decompiler = 'D:/Tools/3Dmigoto/cmd_Decompiler.exe'

python -B shader_sgo.py list $cpk
python -B shader_sgo.py inspect $member --archive $cpk
python -B shader_sgo.py extract $member work/mech-shader --archive $cpk --id 1 --asm --decompiler $decompiler
# 编辑 work/mech-shader/0001.ps_5_0.hlsl
python -B shader_sgo.py repack $member work/SND_MECH.SGO --archive $cpk --hlsl 1 work/mech-shader/0001.ps_5_0.hlsl
```

- **`list`**：列出所有着色器 SGO 在包内的路径。
- **`inspect`**：以 JSON 输出每个槽位的 ID、数组路径、阶段、字节码偏移和 SHA-256。路径如 `["Deferred", 0, 4]` 是 `Deferred` technique 第一个 pass 的像素着色器。ID 按源文件的成员顺序编号，换文件后请重新查看。
- **`extract`**：为每个槽位写出 `<ID>.<profile>.dxbc`，或只导出 `--id` 指定的槽位（可重复）。
  - 加 `--asm` 导出微软反汇编，加 `--decompiler` 导出 HLSL。
  - `manifest.json` 记录源文件哈希和导出的文件。
  - 某个槽位反编译失败时，它的 DXBC 和要求的汇编仍会导出，失败记入清单，退出码非零。
- **`repack`**：写出新的 SGO。
  - 用 `--hlsl ID FILE`、`--asm ID FILE`（需要 `--assembler` 指向 3Dmigoto 的 `cmd_Decompiler.exe`）或 `--dxbc ID FILE` 替换槽位。每个参数都可重复，一次回包可以替换多个 ID。
  - HLSL 按槽位的 profile 编译，入口默认 `main`，可用 `--entry` 修改。
  - 不给任何替换时，输出与源文件逐字节相同。
  - 工具不会覆盖已有文件；输出路径请放在游戏目录之外。
- **散装文件**：处理散装 SGO 文件时，省略 `--archive`，把文件路径作为源。这时无法核对来源，只记录它的 SHA-256。
- **换一个反编译器**：想用 [HlslDecompiler](https://github.com/AndresTraks/HlslDecompiler) 代替 3Dmigoto，加 `--decompiler PATH --decompiler-kind hlsl-decompiler`。

新 SGO 怎么放进游戏（打 CPK 补丁或用 mod 加载器）由你决定，本工具只负责生成文件。

## 回包检查什么

引擎按 SGO 的 technique 和 pass 查找着色器。原版 SGO 里多个槽位可以指向同一段 DXBC。你只改其中一个时，回包会拆开这个共享引用，其余槽位保持原样。

- **布局**：保留原有节点顺序、字符串池和填充内容，重新计算 raw 节点和字符串偏移，raw 区保持 16 字节对齐。
- **字节码**：新程序保留原来的反射区和输入输出签名，换上新的程序和统计区，并重算校验和。
- **兼容检查**：阶段、签名、资源绑定和常量缓冲区大小必须与原版一致。用汇编回包时，声明也必须一致。纹理和常量缓冲区的绑定位置由游戏决定，请保持常量的数据布局和含义。

离线检查通过不代表画面正确，一定要在游戏里看对应的 pass。

## 可靠性与限制

- 反编译出的 HLSL 是从字节码恢复的，变量名、结构和部分表达式不会与原始源码一致。看起来不对时，对照反汇编检查。
- 只支持 Steam 版 `DX11.cpk` 使用的小端 SGO 0x102 格式。

## 许可证

工具代码采用 MIT 许可证，见 [LICENSE](LICENSE)。`edf6shader/` 中的 CPK / CRILAYLA 读取代码保留原许可证（Unlicense，见 `edf6shader/LICENSE.edf6-cpk`）。SGO 布局依照 edf-tools 记录的格式。本项目与 SANDLOT、D3 PUBLISHER 无关。
