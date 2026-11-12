import pytest

from rdt.vcp import MAX_LINE, VcpError, VcpReader, clean_line


def test_robot_vcp_is_refused():
    with pytest.raises(VcpError):
        VcpReader("robot", {"probe_serial": "X", "log_port": None}, lambda *a: None, 0.0)


def test_clean_line_escapes_control_and_caps():
    assert clean_line(b"[tx] ok\x1b[31m\r\n") == "[tx] ok�[31m"
    assert len(clean_line(b"a" * 5000)) == MAX_LINE
    assert "�" in clean_line(b"\xff\xfe")
