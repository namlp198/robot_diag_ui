import json
import struct

import pytest

from rdt import exprs, settings

CFG = {"flash_range": [0x08000000, 0x080FFFFF]}


def build(text, allow=False, **kw):
    return exprs.build("robot", CFG, {"id": "e1", "text": text, **kw}, None, allow)


def test_raw_address_types_and_decode():
    e = build("0x20000000", type="u16", count=2)
    assert (e.address, e.size) == (0x20000000, 4)
    assert e.decode(struct.pack("<HH", 7, 65535)) == [7, 65535]
    assert build("0x20000000", type="i32").decode(struct.pack("<i", -5)) == -5
    assert build("0x20000000", type="f32").decode(struct.pack("<f", 1.5)) == 1.5


def test_regions():
    build("0x08000000")
    build("0x24000000")
    build("0xE000ED28")                       # SCB CFSR: core register, always readable
    with pytest.raises(exprs.ExprError, match="peripheral"):
        build("0x40011004")
    assert build("0x40011004", allow=True).address == 0x40011004
    for bad in ("0x60000000", "0x00000000", "0xA0000000"):
        with pytest.raises(exprs.ExprError):
            build(bad, allow=True)


def test_size_alignment_and_garbage():
    with pytest.raises(exprs.ExprError, match="aligned"):
        build("0x20000002", type="u32")
    with pytest.raises(exprs.ExprError):
        build("0x20000000", type="u8", count=2000)
    with pytest.raises(exprs.ExprError):
        build("0x20000000", type="u128")
    with pytest.raises(exprs.ExprError):
        build("")
    with pytest.raises(exprs.ExprError, match="bad id"):
        exprs.build("robot", CFG, {"id": "../x", "text": "0x20000000"}, None, False)
    with pytest.raises(exprs.ExprError, match="no ELF"):
        build("s_some_variable")


def test_core_register_table_is_inside_allowed_regions():
    for name, addr, typ, _m in exprs.CORE_REGISTERS:
        e = build(hex(addr), type=typ)
        assert e.size == 4, name


def test_settings_validation_and_persistence(tmp_path):
    st = settings.Store(tmp_path / "settings.json")
    assert st.current.effort is None and st.current.allow_peripheral_reads is False
    new = st.update({"model": "claude-opus-5-5", "effort": "high", "max_usd": 1.5})
    assert new.model == "claude-opus-5-5" and new.effort == "high"
    again = settings.Store(tmp_path / "settings.json")
    assert again.current.model == "claude-opus-5-5" and again.current.max_usd == 1.5
    for bad in ({"model": "x"}, {"model": "bad model!"}, {"effort": "ultra"}, {"max_usd": 0}, {"max_usd": "abc"}, {"allow_peripheral_reads": "yes"}):
        with pytest.raises(settings.SettingsError):
            st.update(bad)
    assert st.current.model == "claude-opus-5-5"          # a rejected change stores nothing
    assert st.update({"effort": ""}).effort is None


def test_damaged_settings_file_falls_back_to_defaults(tmp_path):
    p = tmp_path / "settings.json"
    p.write_text("{not json", encoding="utf-8")
    assert settings.Store(p).current.model
    p.write_text(json.dumps({"model": "!!"}), encoding="utf-8")
    assert settings.Store(p).current.model != "!!"
