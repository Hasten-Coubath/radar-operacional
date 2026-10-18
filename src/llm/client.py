"""Cliente de LLM do projeto: cache em disco, registro de uso/custo e saída estruturada validada.

Todo o código do projeto chama o LLM por aqui; nenhum módulo importa a SDK do provedor
diretamente.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Generic, Literal, TypeVar

from pydantic import BaseModel, ValidationError

from src.llm.cache import DiskCache
from src.llm.cost import PriceTable, UsageLogger
from src.llm.providers import LLMProvider, make_provider
from src.llm.types import Effort, LLMRequest, LLMResponse, LLMResult

Mode = Literal["live", "cache_only"]
T = TypeVar("T", bound=BaseModel)

MAX_ERROR_CHARS = 1500


class CacheMissError(RuntimeError):
    """Requisição ausente do cache em modo `cache_only`."""


@dataclass(frozen=True)
class RoleSettings:
    model: str
    max_tokens: int
    effort: Effort | None = None
    think: bool | None = None
    options: dict[str, Any] | None = None


@dataclass
class StructuredResult(Generic[T]):
    """Resultado de `generate_structured`. `parsed is None` significa: revisão humana."""

    parsed: T | None
    attempts: list[LLMResult] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def needs_review(self) -> bool:
        return self.parsed is None

    @property
    def cost_usd_live(self) -> float:
        return sum(a.cost_usd_live or 0.0 for a in self.attempts)

    @property
    def latency_s(self) -> float:
        """Tempo de processamento somado das tentativas (o original, mesmo em cache hit)."""
        return sum(a.response.latency_s for a in self.attempts)


class LLMClient:
    def __init__(
        self,
        provider: LLMProvider,
        cache: DiskCache,
        prices: PriceTable,
        *,
        usage_logger: UsageLogger | None = None,
        mode: Mode = "live",
        roles: dict[str, RoleSettings] | None = None,
    ) -> None:
        if mode not in ("live", "cache_only"):
            raise ValueError(f"Modo de LLM inválido: {mode!r}")
        self.provider = provider
        self.cache = cache
        self.prices = prices
        self.usage_logger = usage_logger
        self.mode = mode
        self.roles = roles or {}

    @classmethod
    def from_config(
        cls, cfg: dict[str, Any] | None = None, *, provider: LLMProvider | None = None
    ) -> LLMClient:
        from src.config import load_config, resolve_path

        llm = (cfg or load_config())["llm"]
        return cls(
            provider=provider
            or make_provider(llm["provider"], llm.get("providers", {}).get(llm["provider"])),
            cache=DiskCache(resolve_path(llm["cache_dir"])),
            prices=PriceTable.from_config(llm["pricing_usd_per_mtok"]),
            usage_logger=UsageLogger(resolve_path(llm["usage_log"])),
            mode=llm["mode"],
            roles={name: RoleSettings(**r) for name, r in llm["roles"].items()},
        )

    def request_for(
        self,
        role: str,
        messages: list[dict[str, Any]],
        *,
        system: str | None = None,
        tools: list[dict[str, Any]] | None = None,
    ) -> LLMRequest:
        """Cria uma requisição com o modelo e parâmetros configurados para o papel."""
        r = self.roles[role]
        return LLMRequest(
            model=r.model,
            max_tokens=r.max_tokens,
            effort=r.effort,
            think=r.think,
            options=r.options,
            messages=messages,
            system=system,
            tools=tools,
        )

    def generate(self, request: LLMRequest, *, tag: str | None = None) -> LLMResult:
        """Devolve a resposta do cache ou chama o provedor (só em modo `live`)."""
        key = request.cache_key(self.provider.name)
        entry = self.cache.get(key)
        if entry is not None:
            response = LLMResponse.model_validate(entry["response"])
            cached = True
        elif self.mode == "cache_only":
            raise CacheMissError(f"Sem cache para a chave {key} (modo cache_only)")
        else:
            response = self.provider.generate(request)
            self.cache.put(
                key,
                {
                    "key": key,
                    "provider": self.provider.name,
                    "created_at": _now(),
                    "request": request.model_dump(mode="json"),
                    "response": response.model_dump(mode="json"),
                },
            )
            cached = False
        result = LLMResult(
            response=response,
            cache_key=key,
            cached=cached,
            cost_usd_live=self.prices.estimate(request.model, response.usage),
        )
        self._log(request, result, tag)
        return result

    def generate_structured(
        self,
        request: LLMRequest,
        schema: type[T],
        *,
        max_attempts: int = 2,
        tag: str | None = None,
    ) -> StructuredResult[T]:
        """Pede saída no formato de `schema` e valida com Pydantic.

        Em JSON inválido, reenvia a conversa com a resposta anterior e o erro de validação
        (até `max_attempts` chamadas). Cada tentativa é uma requisição distinta, logo também
        fica em cache e é reproduzível. Se nenhuma tentativa validar, `parsed` é None.
        """
        req = request.model_copy(update={"output_schema": schema.model_json_schema()})
        messages = list(req.messages)
        out: StructuredResult[T] = StructuredResult(parsed=None)
        for _ in range(max_attempts):
            result = self.generate(req.model_copy(update={"messages": messages}), tag=tag)
            out.attempts.append(result)
            if result.response.stop_reason == "refusal":
                out.errors.append("refusal")
                break
            text = result.response.text
            try:
                out.parsed = schema.model_validate_json(text)
                return out
            except ValidationError as e:
                error = str(e)[:MAX_ERROR_CHARS]
            out.errors.append(error)
            messages = [
                *messages,
                {"role": "assistant", "content": text or "(resposta vazia)"},
                {
                    "role": "user",
                    "content": "A resposta anterior não é válida para o schema pedido. "
                    f"Erro de validação:\n{error}\n\nResponda apenas com o JSON corrigido.",
                },
            ]
        return out

    def _log(self, request: LLMRequest, result: LLMResult, tag: str | None) -> None:
        if self.usage_logger is None:
            return
        u = result.response.usage
        self.usage_logger.log(
            {
                "ts": _now(),
                "tag": tag,
                "provider": self.provider.name,
                "model": request.model,
                "cache_key": result.cache_key,
                "cached": result.cached,
                "stop_reason": result.response.stop_reason,
                "input_tokens": u.input_tokens,
                "output_tokens": u.output_tokens,
                "cache_read_input_tokens": u.cache_read_input_tokens,
                "cache_creation_input_tokens": u.cache_creation_input_tokens,
                "latency_s": round(result.response.latency_s, 4),
                "timings": result.response.timings,
                "cost_usd_live": result.cost_usd_live,
                "cost_usd_spent": result.cost_usd_spent,
            }
        )


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")
