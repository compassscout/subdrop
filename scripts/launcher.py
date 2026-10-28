"""打包入口。

- 默认启动图形界面
- `SubDrop.exe --cli ...` 走命令行，方便脚本化，也方便验证打包后的引擎是否正常

窗口程序本身没有控制台，--cli 模式下如果父进程是 cmd/PowerShell，就主动
附着上去，否则输出会被丢掉（甚至写句柄时报 OSError）。
"""

import sys


def _attach_parent_console() -> None:
    if sys.platform != "win32" or not getattr(sys, "frozen", False):
        return
    try:
        import ctypes

        ATTACH_PARENT_PROCESS = -1
        kernel32 = ctypes.windll.kernel32
        if not kernel32.AttachConsole(ATTACH_PARENT_PROCESS):
            return
        # 中文系统的控制台是 GBK(936)，直接写 UTF-8 会变乱码
        codepage = kernel32.GetConsoleOutputCP() or 65001
        encoding = "utf-8" if codepage == 65001 else f"cp{codepage}"
        sys.stdout = open("CONOUT$", "w", encoding=encoding, errors="replace", buffering=1)
        sys.stderr = open("CONOUT$", "w", encoding=encoding, errors="replace", buffering=1)
    except Exception:  # noqa: BLE001 - 控制台不是必需品
        pass


def main() -> int:
    if "--cli" in sys.argv:
        _attach_parent_console()
        from subdrop.cli import main as cli_main

        index = sys.argv.index("--cli")
        return cli_main(sys.argv[index + 1 :])

    from subdrop.app import run

    return run()


if __name__ == "__main__":
    sys.exit(main())
