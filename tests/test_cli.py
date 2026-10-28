"""命令行输出在无控制台环境下的健壮性。"""

from __future__ import annotations

import subdrop.cli as cli


class BrokenStream:
    name = "<broken>"

    def write(self, *args, **kwargs):
        raise OSError(22, "Invalid argument")

    def flush(self):
        raise OSError(22, "Invalid argument")


def test_safe_stream_falls_back_to_devnull(monkeypatch):
    monkeypatch.setattr(cli.sys, "stdout", BrokenStream())
    stream = cli._safe_stream("stdout")
    assert stream is not None
    assert stream.name != "<broken>"
    stream.close()


def test_out_does_not_raise_with_broken_stream(monkeypatch):
    monkeypatch.setattr(cli, "_OUT", BrokenStream())
    cli._out("你好")  # 不应该抛异常


def test_err_does_not_raise_with_broken_stream(monkeypatch):
    monkeypatch.setattr(cli, "_ERR", BrokenStream())
    cli._err("进度 10%")
