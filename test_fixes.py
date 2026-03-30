"""Quick regression tests for the fixed bugs."""
import json
from pathlib import Path


def test_llm_response_has_tool_calls():
    from tinyagent.provider import LLMResponse, ToolCallRequest

    empty = LLMResponse(content="hi")
    assert empty.has_tool_calls is False

    with_tools = LLMResponse(
        content=None,
        tool_calls=[ToolCallRequest(id="1", name="bash", arguments={"cmd": "ls"})],
    )
    assert with_tools.has_tool_calls is True


def test_llm_response_thinking_blocks():
    from tinyagent.provider import LLMResponse

    r = LLMResponse(content="hi", thinking_blocks=[{"type": "thinking", "thinking": "..."}])
    assert r.thinking_blocks is not None


def test_skills_loader_builtin_skills_attr():
    from tinyagent.skills_loader import SkillsLoader

    loader = SkillsLoader(Path("/tmp/fake"))
    assert hasattr(loader, "builtin_skills")
    assert loader.builtin_skills is None


def test_skills_loader_xml_format():
    from tinyagent.skills_loader import SkillsLoader

    class FakeSkillsLoader(SkillsLoader):
        def list_skills(self):
            return [{"name": "test-skill", "path": "/tmp/fake/skills/test-skill/SKILL.md"}]

        def _get_skill_description(self, name):
            return "A test skill"

    loader = FakeSkillsLoader(Path("/tmp/fake"))
    xml = loader.build_skills_summary()
    assert "<skill>" in xml
    assert "</skill>" in xml
    assert xml.count("<skill>") == xml.count("</skill>")


def test_parse_tinyagent_metadata_key():
    from tinyagent.skills_loader import SkillsLoader

    loader = SkillsLoader(Path("/tmp/fake"))
    raw = json.dumps({"tinyagent": {"always": True}})
    result = loader._parse_tinyagent_metadata(raw)
    assert result.get("always") is True


if __name__ == "__main__":
    test_llm_response_has_tool_calls()
    test_llm_response_thinking_blocks()
    test_skills_loader_builtin_skills_attr()
    test_skills_loader_xml_format()
    test_parse_tinyagent_metadata_key()
    print("All tests passed!")
