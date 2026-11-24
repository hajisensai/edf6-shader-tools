## 改了什么 / What changed

<!-- 一句话说明改动和原因。One or two sentences on the change and why. -->

## 怎么验证的 / How it was tested

<!-- 跑了哪些测试；改动影响 SGO 读写时，写明在自己的游戏上试过哪些文件、无替换回包是否逐字节相同。Which tests ran; if the change affects reading or writing SGOs, which files you tried on your own copy and whether a repack without replacements was byte-identical. -->

## 自查 / Checklist

- [ ] `python -B tools/lint_repo.py` 通过 / passes
- [ ] `python -B -m unittest discover -s tests` 通过 / passes
- [ ] 没有提交 SGO、CPK、DXBC、着色器源码、反汇编或反编译结果、`extract` 产物 / no SGO, CPK, DXBC, shader source, disassembly, decompiler output or `extract` output
