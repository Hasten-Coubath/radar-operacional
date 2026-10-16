"""Testes da camada de LLM com provedor falso: nenhuma chamada real à API."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import anthropic
import pytest
from pydantic import BaseModel, Field

from src.config import load_config
from src.llm.cache import DiskCache
from src.llm.client import CacheMissError, LLMClient, RoleSettings
from src.llm.cost import ModelPricing, PriceTable, UsageLogger, summarize_usage
from src.llm.providers import AnthropicProvider
from src.llm.types import LLMRequest, LLMResponse, LLMUsage

MODEL = "modelo-teste"
PRICES = PriceTable({MODEL: ModelPricing(input=1.0, output=10.0)})


class FakeProvider:
    """Devolve respostas roteirizadas e registra cada requisição recebida."""

    name = "fake"

    def __init__(self, texts: list[str], *, input_tokens: int = 100, output_tokens: int = 20):
        self.texts = list(texts)
        self.calls: list[LLMRequest] = []
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens

    def generate(self, request: LLMRequest) -> LLMResponse:
        self.calls.append(request)
        text = self.texts[min(len(self.calls), len(self.texts)) - 1]
        return LLMResponse(
            content=[{"type": "text", "text": text}],
            stop_reason="end_turn",
            model=request.model,
            usage=LLMUsage(input_tokens=self.input_tokens, output_tokens=self.output_tokens),
            latency_s=0.5,
        )


def make_client(tmp_path: Path, provider: FakeProvider, mode: str = "live") -> LLMClient:
    return LLMClient(
        provider=provider,
        cache=DiskCache(tmp_path / "cache"),
        prices=PRICES,
        usage_logger=UsageLogger(tmp_path / "usage.jsonl"),
        mode=mode,  # type: ignore[arg-type]
        roles={"classifier": RoleSettings(model=MODEL, max_tokens=256, effort="low")},
    )


def req(text: str = "entrega atrasou", *, model: str = MODEL, system: str = "p1") -> LLMRequest:
    return LLMRequest(
        model=model, max_tokens=256, system=system, messages=[{"role": "user", "content": text}]
    )


class Classe(BaseModel):
    causa: str
    confianca: float = Field(ge=0, le=1)


# --- cache ---


def test_cache_hit_avoids_second_call(tmp_path: Path) -> None:
    provider = FakeProvider(["ok"])
    client = make_client(tmp_path, provider)
    first = client.generate(req())
    second = client.generate(req())
    assert len(provider.calls) == 1
    assert not first.cached and second.cached
    assert second.response.text == "ok"
    assert second.cache_key == first.cache_key


def test_cache_key_depends_on_model_prompt_and_input() -> None:
    base = req().cache_key("fake")
    assert req().cache_key("fake") == base
    assert req(model="outro").cache_key("fake") != base
    assert req(system="p2").cache_key("fake") != base
    assert req(text="outra entrada").cache_key("fake") != base
    assert req().cache_key("outro-provedor") != base


def test_cache_key_ignores_dict_key_order() -> None:
    a = LLMRequest(model=MODEL, max_tokens=10, messages=[{"role": "user", "content": "x"}])
    b = LLMRequest(model=MODEL, max_tokens=10, messages=[{"content": "x", "role": "user"}])
    assert a.cache_key("fake") == b.cache_key("fake")


def test_cache_persists_across_client_instances(tmp_path: Path) -> None:
    make_client(tmp_path, FakeProvider(["ok"])).generate(req())
    provider = FakeProvider(["diferente"])
    result = make_client(tmp_path, provider).generate(req())
    assert result.cached and result.response.text == "ok"
    assert provider.calls == []


def test_cache_entry_stores_request_for_audit(tmp_path: Path) -> None:
    client = make_client(tmp_path, FakeProvider(["ok"]))
    result = client.generate(req())
    entry = client.cache.get(result.cache_key)
    assert entry is not None
    assert entry["request"]["system"] == "p1"
    assert entry["response"]["content"][0]["text"] == "ok"


def test_cache_only_mode_raises_on_miss_without_calling_provider(tmp_path: Path) -> None:
    provider = FakeProvider(["ok"])
    client = make_client(tmp_path, provider, mode="cache_only")
    with pytest.raises(CacheMissError):
        client.generate(req())
    assert provider.calls == []


def test_invalid_mode_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        make_client(tmp_path, FakeProvider(["ok"]), mode="talvez")


# --- custo e registro de uso ---


def test_cost_and_usage_log(tmp_path: Path) -> None:
    client = make_client(tmp_path, FakeProvider(["ok"], input_tokens=1000, output_tokens=200))
    live = client.generate(req(), tag="teste")
    cached = client.generate(req(), tag="teste")
    expected = (1000 * 1.0 + 200 * 10.0) / 1_000_000
    assert live.cost_usd_live == pytest.approx(expected)
    assert live.cost_usd_spent == pytest.approx(expected)
    assert cached.cost_usd_live == pytest.approx(expected)
    assert cached.cost_usd_spent == 0.0

    records = [
        json.loads(line) for line in (tmp_path / "usage.jsonl").read_text("utf-8").splitlines()
    ]
    assert [r["cached"] for r in records] == [False, True]
    assert records[0]["input_tokens"] == 1000 and records[0]["latency_s"] == 0.5

    summary = summarize_usage(tmp_path / "usage.jsonl")
    assert summary["calls_live"] == 1 and summary["calls_cached"] == 1
    assert summary["cost_usd_spent"] == pytest.approx(expected)
    assert summary["by_tag"]["teste"]["calls_live"] == 1


def test_unknown_model_has_no_price(tmp_path: Path) -> None:
    client = make_client(tmp_path, FakeProvider(["ok"]))
    result = client.generate(req(model="sem-preco"))
    assert result.cost_usd_live is None
    assert summarize_usage(tmp_path / "usage.jsonl")["calls_without_price"] == 1


def test_cache_tokens_default_to_input_price() -> None:
    pricing = ModelPricing(input=2.0, output=10.0, cache_read=0.5)
    usage = LLMUsage(cache_read_input_tokens=1_000_000, cache_creation_input_tokens=1_000_000)
    assert pricing.cost(usage) == pytest.approx(0.5 + 2.0)


# --- saída estruturada ---


def test_structured_valid_on_first_attempt(tmp_path: Path) -> None:
    provider = FakeProvider(['{"causa": "atraso_entrega", "confianca": 0.9}'])
    out = make_client(tmp_path, provider).generate_structured(req(), Classe)
    assert out.parsed == Classe(causa="atraso_entrega", confianca=0.9)
    assert len(out.attempts) == 1 and not out.needs_review
    assert provider.calls[0].output_schema == Classe.model_json_schema()


def test_structured_retries_with_validation_error_then_succeeds(tmp_path: Path) -> None:
    provider = FakeProvider(
        [
            '{"causa": "atraso_entrega", "confianca": 7}',
            '{"causa": "atraso_entrega", "confianca": 0.7}',
        ]
    )
    out = make_client(tmp_path, provider).generate_structured(req(), Classe, max_attempts=2)
    assert out.parsed is not None and out.parsed.confianca == 0.7
    assert len(provider.calls) == 2 and len(out.errors) == 1
    retry_messages = provider.calls[1].messages
    assert retry_messages[1] == {
        "role": "assistant",
        "content": '{"causa": "atraso_entrega", "confianca": 7}',
    }
    assert "confianca" in retry_messages[2]["content"]


def test_structured_gives_up_and_flags_for_review(tmp_path: Path) -> None:
    provider = FakeProvider(["não é json", "ainda não"])
    out = make_client(tmp_path, provider).generate_structured(req(), Classe, max_attempts=2)
    assert out.parsed is None and out.needs_review
    assert len(provider.calls) == 2 and len(out.errors) == 2


def test_structured_retry_chain_is_reproducible_from_cache(tmp_path: Path) -> None:
    texts = ["lixo", '{"causa": "elogio", "confianca": 0.8}']
    make_client(tmp_path, FakeProvider(texts)).generate_structured(req(), Classe)
    provider = FakeProvider(["nunca usado"])
    out = make_client(tmp_path, provider, mode="cache_only").generate_structured(req(), Classe)
    assert out.parsed == Classe(causa="elogio", confianca=0.8)
    assert provider.calls == [] and all(a.cached for a in out.attempts)


def test_request_for_uses_role_settings(tmp_path: Path) -> None:
    client = make_client(tmp_path, FakeProvider(["ok"]))
    r = client.request_for("classifier", [{"role": "user", "content": "x"}], system="s")
    assert (r.model, r.max_tokens, r.effort, r.system) == (MODEL, 256, "low", "s")


# --- provedor Anthropic (SDK simulada, sem rede) ---


class _FakeMessages:
    def __init__(self) -> None:
        self.kwargs: dict[str, Any] = {}

    def create(self, **kwargs: Any) -> anthropic.types.Message:
        self.kwargs = kwargs
        return anthropic.types.Message.model_validate(
            {
                "id": "msg_teste",
                "type": "message",
                "role": "assistant",
                "model": kwargs["model"],
                "content": [{"type": "text", "text": '{"causa": "outro", "confianca": 0.5}'}],
                "stop_reason": "end_turn",
                "stop_sequence": None,
                "usage": {"input_tokens": 50, "output_tokens": 12},
            }
        )


class _FakeSDK:
    def __init__(self) -> None:
        self.messages = _FakeMessages()


def test_anthropic_provider_builds_params_and_parses_response() -> None:
    sdk = _FakeSDK()
    provider = AnthropicProvider(client=sdk)
    request = req().model_copy(
        update={"effort": "low", "output_schema": Classe.model_json_schema()}
    )
    response = provider.generate(request)

    sent = sdk.messages.kwargs
    assert sent["model"] == MODEL and sent["system"] == "p1"
    assert sent["output_config"]["effort"] == "low"
    schema = sent["output_config"]["format"]["schema"]
    assert sent["output_config"]["format"]["type"] == "json_schema"
    assert schema["additionalProperties"] is False
    assert "temperature" not in sent and "tools" not in sent

    assert response.text == '{"causa": "outro", "confianca": 0.5}'
    assert response.usage.input_tokens == 50 and response.usage.output_tokens == 12
    assert response.stop_reason == "end_turn"
    # a resposta precisa ser serializável para o cache
    assert LLMResponse.model_validate(json.loads(response.model_dump_json())) == response


def test_anthropic_provider_omits_optional_params() -> None:
    params = AnthropicProvider.build_params(req(system=""))
    assert set(params) == {"model", "max_tokens", "messages"}


# --- configuração ---


def test_config_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RADAR_LLM_MODE", "cache_only")
    monkeypatch.setenv("RADAR_CLASSIFIER_MODEL", "outro-modelo")
    cfg = load_config(load_env=False)
    assert cfg["llm"]["mode"] == "cache_only"
    assert cfg["llm"]["roles"]["classifier"]["model"] == "outro-modelo"


def test_client_from_config_without_api_key(tmp_path: Path) -> None:
    """Construir o cliente não exige chave nem rede (a SDK é criada sob demanda)."""
    cfg = load_config(load_env=False)
    cfg["llm"]["cache_dir"] = str(tmp_path / "c")
    cfg["llm"]["usage_log"] = str(tmp_path / "u.jsonl")
    client = LLMClient.from_config(cfg)
    assert client.provider.name == "anthropic"
    assert client.roles["classifier"].model == cfg["llm"]["roles"]["classifier"]["model"]
    for model in {r.model for r in client.roles.values()}:
        assert model in client.prices.prices, f"modelo sem preço configurado: {model}"
