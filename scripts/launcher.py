"""打包入口。

- 默认启动图形界面
- `SubDrop.exe --cli ...` 走命令行，方便脚本化，也方便验证打包后的引擎是否正常
"""

import sys


def main() -> int:
    if "--cli" in sys.argv:
        from subdrop.cli import main as cli_main

        index = sys.argv.index("--cli")
        return cli_main(sys.argv[index + 1 :])

    from subdrop.app import run

    return run()


if __name__ == "__main__":
    sys.exit(main())
