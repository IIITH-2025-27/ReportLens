"""Second model family (results/run_log.md, section I): lazy loading, the chart-to-CSV table tool, the registry."""
from __future__ import annotations

import pytest

from chart_claim_verifier.models.vlm import LazyLLM, ScriptedLLM
from chart_claim_verifier.schemas import Figure, PointQuery
from chart_claim_verifier.tools.base import ToolError
from chart_claim_verifier.tools.registry import build_tools
from chart_claim_verifier.tools.vlm2_table import Vlm2TableTool, parse_csv_table


def test_lazy_llm_loads_on_first_call_only():
    made = []

    def factory():
        made.append(1)
        return ScriptedLLM(lambda p, i, k: '{"value": 1}', name="m")

    llm = LazyLLM("some/model", factory=factory)
    assert llm.name == "some/model" and not llm.loaded and not made
    assert llm.generate("q") == ['{"value": 1}']
    llm.generate("q")
    assert made == [1] and llm.loaded


def test_csv_in_a_fence_with_percent_signs():
    ans = "```csv\nEpoch,ResNet-18,ViT-S\n0,10.5%,12\n5,40,\"41.5\"\n10,60.2,n/a\n```"
    t = parse_csv_table(ans)
    assert t == {"ResNet-18": {"0": 10.5, "5": 40.0, "10": 60.2}, "ViT-S": {"0": 12.0, "5": 41.5}}


def test_answer_cut_off_inside_the_fence_keeps_its_complete_rows():
    t = parse_csv_table("```csv\nEpoch,A,B\n2,45,50\n4,50,55\n6,55,")
    assert t == {"A": {"2": 45.0, "4": 50.0, "6": 55.0}, "B": {"2": 50.0, "4": 55.0}}


def test_markdown_table_and_bad_answers():
    t = parse_csv_table("| Dataset | A | B |\n|---|---|---|\n| MNIST | 99.1 | 98 |\n| SVHN | 90 | 91.5 |")
    assert t == {"A": {"MNIST": 99.1, "SVHN": 90.0}, "B": {"MNIST": 98.0, "SVHN": 91.5}}
    for bad in ("I cannot read this chart.", "x\n1"):
        with pytest.raises(ToolError):
            parse_csv_table(bad)


def test_series_written_as_rows_is_looked_up_transposed(tmp_path):
    img = tmp_path / "c.png"
    img.write_bytes(b"png")
    llm = ScriptedLLM(lambda p, i, k: "Model,MNIST,SVHN\nResNet-50,99.1,90.0\nVGG-16,98.0,88.5", name="g")
    tool = Vlm2TableTool(llm)
    fig = Figure(report_id="r", figure_id="fig1", image_path=str(img))
    r = tool.read(fig, PointQuery(series="VGG-16", x="SVHN"))
    assert r.ok and r.value == 88.5
    assert llm.calls == 1                       # one table per figure


def test_registry_builds_the_second_family_tools():
    llm2 = ScriptedLLM(lambda p, i, k: '{"value": 3}', name="granite")
    tools = build_tools(["vlm2_crop", "vlm2_table"], llm2=llm2)
    assert tools["vlm2_crop"].name == "vlm2_crop" and "granite" in tools["vlm2_crop"].version
    assert tools["vlm2_table"].version.startswith("v1:granite")
    with pytest.raises(ValueError):
        build_tools(["vlm2_crop"])
