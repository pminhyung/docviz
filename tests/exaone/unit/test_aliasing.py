import re

from exaone.aliasing import RandomShortAliaser


def test_alias_is_idempotent_per_provider_id():
    aliaser = RandomShortAliaser()
    first = aliaser.alias(provider_id="call_abc", tool_name="web_search")
    second = aliaser.alias(provider_id="call_abc", tool_name="web_search")
    assert first == second
    assert len(first) == 6
    assert first[:3].isalpha() and first[3:].isdigit()


def test_alias_unique_across_provider_ids():
    aliaser = RandomShortAliaser()
    a = aliaser.alias(provider_id="call_1", tool_name="t")
    b = aliaser.alias(provider_id="call_2", tool_name="t")
    assert a != b


def test_alias_format_matches_pattern():
    aliaser = RandomShortAliaser()
    alias = aliaser.alias(provider_id="p1", tool_name="web_search")
    assert re.fullmatch(r"[a-z]{3}[0-9]{3}", alias), f"Unexpected format: {alias}"


def test_alias_uniqueness_across_many_calls():
    aliaser = RandomShortAliaser()
    aliases = [aliaser.alias(provider_id=f"p{i}", tool_name="tool") for i in range(100)]
    assert len(set(aliases)) == 100
