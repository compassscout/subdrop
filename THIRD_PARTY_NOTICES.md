# 第三方组件声明

SubDrop 本体以 MIT 协议发布，但分发包里包含以下第三方组件，它们各有自己的许可证。

## FFmpeg（可执行文件）

- 位置：`ffmpeg/ffmpeg.exe`（单文件版内嵌，运行时释放到临时目录）
- 版本：6.1.1-essentials_build（gyan.dev 构建）
- 许可证：**GPL v3**（该构建启用了 libx264 等 GPL 组件）
- 来源与源码：https://ffmpeg.org/ 、https://www.gyan.dev/ffmpeg/builds/

SubDrop 通过子进程调用 ffmpeg，属于聚合分发（mere aggregation），不影响本项目
自身的 MIT 授权。如果你再分发本软件，请一并保留本声明，并按 GPL 要求提供
FFmpeg 对应源码的获取方式（上面的链接即可）。

## PySide6 / Qt

- 许可证：LGPL v3（动态链接，PyInstaller 打包时保持可替换）
- 源码：https://www.qt.io/ 、https://pypi.org/project/PySide6/

## Python 运行时

- 许可证：PSF License
- 源码：https://www.python.org/

## requests / urllib3 等

- 许可证：Apache-2.0 / MIT
