"""Leitura do catálogo do Bling: paginação, normalização e hash de conteúdo (spec 006).

Todo formato do Bling (nomes de campos, estrutura de mídia, saldos) fica isolado aqui; o
restante do sistema só conhece as dataclasses internas. Comportamento real observado em
research.md (R1, R2, R7).
Nunca registra token nem corpo de resposta.
"""

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Optional
from urllib.parse import parse_qsl, urlencode, urlsplit

from src.integrations.bling.client import BlingClient
from src.integrations.bling.errors import BlingError

PAGE_SIZE = 100
BALANCE_BATCH_SIZE = 100  # tamanho do lote em /estoques/saldos (R1)

CATEGORIES_PATH = "/categorias/produtos"
PRODUCTS_PATH = "/produtos"
BALANCES_PATH = "/estoques/saldos"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

INCOMPLETE_WEIGHT = "incompleto_peso"
INCOMPLETE_DIMENSIONS = "incompleto_medidas"
INCOMPLETE_PRICE = "incompleto_preco"  # preço vigente do site ausente ou <= 0


class BlingCatalogFormatError(BlingError):
    """Resposta do Bling fora do formato esperado."""

    def __init__(self, message: str = "Resposta do catálogo do Bling inesperada.") -> None:
        super().__init__(message)


@dataclass(frozen=True)
class BlingCategory:
    id: int
    name: str
    parent_id: Optional[int] = None


@dataclass(frozen=True)
class BlingListItem:
    """Item da varredura (`GET /produtos`). Variações (com `idProdutoPai`) são descartadas."""

    id: int
    active: bool


@dataclass(frozen=True)
class BlingProductPage:
    items: tuple[BlingListItem, ...]
    has_more: bool


@dataclass(frozen=True)
class BlingVariant:
    bling_id: int
    sku: str
    name: str
    price: Decimal
    active: bool
    gtin: Optional[str]
    weight_kg: Optional[float]
    height_cm: Optional[float]
    width_cm: Optional[float]
    length_cm: Optional[float]
    images: tuple[str, ...]

    @property
    def block_reason(self) -> Optional[str]:
        """Motivo de a variação não poder ir à venda por dado incompleto (R8)."""
        if not self.weight_kg or self.weight_kg <= 0:
            return INCOMPLETE_WEIGHT
        if not all(d and d > 0 for d in (self.width_cm, self.height_cm, self.length_cm)):
            return INCOMPLETE_DIMENSIONS
        return None

    @property
    def sellable(self) -> bool:
        return self.active and self.block_reason is None


@dataclass(frozen=True)
class BlingProduct:
    bling_id: int
    code: Optional[str]
    name: str
    description: Optional[str]
    complementary_description: Optional[str]
    brand: Optional[str]
    unit: Optional[str]
    condition: Optional[int]
    format: Optional[str]
    status: str
    active: bool
    category_id: Optional[int]
    variants: tuple[BlingVariant, ...]
    updated_at: Optional[datetime]
    content_hash: str

    @property
    def sellable(self) -> bool:
        return self.active and any(v.sellable for v in self.variants)

    @property
    def blocked_reasons(self) -> list[str]:
        """Motivos únicos de variações ativas bloqueadas (para o relatório de erros)."""
        reasons = [v.block_reason for v in self.variants if v.active and v.block_reason]
        return sorted(set(reasons))


def available_stock(balance: int, pending: int) -> int:
    """Estoque da loja = saldo do Bling menos vendas pagas ainda não refletidas nele (R5)."""
    return max(0, balance - pending)


# ------------------------------------------------------------------ normalização


def _clean(value: Any, limit: Optional[int] = None) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return text[:limit] if limit else text


def _decimal(value: Any) -> Decimal:
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return Decimal("0.00")
    if not number.is_finite() or number < 0:
        return Decimal("0.00")
    return number.quantize(Decimal("0.01"))


def _float(value: Any) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _int(value: Any) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _datetime(value: Any) -> Optional[datetime]:
    text = _clean(value)
    if not text:
        return None
    try:
        return datetime.strptime(text[:19].replace("T", " "), _DATE_FORMAT)
    except ValueError:
        return None


def _is_active(raw: dict[str, Any], default: bool = True) -> bool:
    situation = _clean(raw.get("situacao"))
    return default if situation is None else situation.upper() == "A"


def _images(media: Any) -> tuple[str, ...]:
    """Links de imagens: externas primeiro, depois internas (links S3 assinados, R7)."""
    images = media.get("imagens") if isinstance(media, dict) else None
    if not isinstance(images, dict):
        return ()
    links: list[str] = []
    for group in ("externas", "internas"):
        for entry in images.get(group) or []:
            link = _clean(entry.get("link") if isinstance(entry, dict) else None, 1000)
            if link and link not in links:
                links.append(link)
    return tuple(links)


def _dimensions(raw: dict[str, Any]) -> tuple[Optional[float], Optional[float], Optional[float]]:
    box = raw.get("dimensoes")
    box = box if isinstance(box, dict) else {}
    return _float(box.get("altura")), _float(box.get("largura")), _float(box.get("profundidade"))


def _variant(
    raw: dict[str, Any],
    *,
    bling_id: int,
    name: str,
    parent_active: bool,
    parent_weight: Optional[float],
    parent_dims: tuple[Optional[float], Optional[float], Optional[float]],
    parent_images: tuple[str, ...],
) -> BlingVariant:
    own_dims = _dimensions(raw)
    height, width, length = (own or inherited for own, inherited in zip(own_dims, parent_dims))
    return BlingVariant(
        bling_id=bling_id,
        sku=_clean(raw.get("codigo"), 100) or f"BLING-{bling_id}",
        name=name[:100],
        price=_decimal(raw.get("preco")),
        active=parent_active and _is_active(raw),
        gtin=_clean(raw.get("gtin"), 50),
        weight_kg=_float(raw.get("pesoBruto")) or parent_weight,
        height_cm=height,
        width_cm=width,
        length_cm=length,
        images=_images(raw.get("midia")) or parent_images,
    )


def normalize_product(raw: dict[str, Any]) -> BlingProduct:
    """Converte o detalhe de `GET /produtos/{id}`; variação herda peso/medidas/imagens do pai."""
    bling_id = _int(raw.get("id"))
    name = _clean(raw.get("nome"), 200)
    if bling_id is None or name is None:
        raise BlingCatalogFormatError()
    active = _is_active(raw)
    weight = _float(raw.get("pesoBruto"))
    dims = _dimensions(raw)
    images = _images(raw.get("midia"))
    raw_variations = [v for v in raw.get("variacoes") or [] if isinstance(v, dict)]
    variants: list[BlingVariant] = []
    for entry in raw_variations:
        variation_id = _int(entry.get("id"))
        if variation_id is None:
            raise BlingCatalogFormatError()
        detail = entry.get("variacao")
        label = _clean(detail.get("nome") if isinstance(detail, dict) else None)
        variants.append(
            _variant(
                entry,
                bling_id=variation_id,
                name=label or _clean(entry.get("nome")) or name,
                parent_active=active,
                parent_weight=weight,
                parent_dims=dims,
                parent_images=images,
            )
        )
    if not variants:
        variants.append(
            _variant(
                raw,
                bling_id=bling_id,
                name="Padrão",
                parent_active=active,
                parent_weight=weight,
                parent_dims=dims,
                parent_images=images,
            )
        )
    category = raw.get("categoria")
    product: dict[str, Any] = {
        "bling_id": bling_id,
        "code": _clean(raw.get("codigo"), 100),
        "name": name,
        "description": _clean(raw.get("descricaoCurta")),
        "complementary_description": _clean(raw.get("descricaoComplementar")),
        "brand": _clean(raw.get("marca"), 100),
        "unit": _clean(raw.get("unidade"), 10),
        "condition": _int(raw.get("condicao")),
        "format": _clean(raw.get("formato"), 10),
        "status": "A" if active else "I",
        "active": active,
        # O Bling devolve {"id": 0} para produto sem categoria: tratar como ausência.
        "category_id": (_int(category.get("id")) or None) if isinstance(category, dict) else None,
    }
    return BlingProduct(
        **product,
        variants=tuple(variants),
        updated_at=_datetime(raw.get("dataAlteracao")),
        content_hash=content_hash(product, variants),
    )


# Parâmetros de URL pré-assinada (S3 v2/v4) que mudam a cada leitura do Bling (R7).
_SIGNATURE_PARAMS = {"awsaccesskeyid", "expires", "signature"}


def image_identity(url: str) -> str:
    """Identidade da imagem = URL sem os parâmetros de assinatura S3 (mudam a cada leitura e
    expiram em 7 dias, R7); demais parâmetros da query são mantidos."""
    parts = urlsplit(url)
    kept = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if key.lower() not in _SIGNATURE_PARAMS and not key.lower().startswith("x-amz-")
    ]
    query = f"?{urlencode(kept)}" if kept else ""
    return f"{parts.scheme}://{parts.netloc}{parts.path}{query}" if parts.netloc else url


def content_hash(product: dict[str, Any], variants: list[BlingVariant]) -> str:
    """SHA-256 estável do conteúdo normalizado; exclui preço e saldo (R2, R6)."""
    payload = {
        "product": product,
        "variants": [
            {
                "id": v.bling_id,
                "sku": v.sku,
                "name": v.name,
                "active": v.active,
                "gtin": v.gtin,
                "weight": v.weight_kg,
                "height": v.height_cm,
                "width": v.width_cm,
                "length": v.length_cm,
                "images": [image_identity(u) for u in v.images],
            }
            for v in sorted(variants, key=lambda v: v.bling_id)
        ],
    }
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode()).hexdigest()


def _balance(entry: dict[str, Any]) -> Optional[tuple[int, int]]:
    """(id do produto, saldo). R1: usa o saldo virtual, com o físico como alternativa."""
    product = entry.get("produto")
    product_id = _int(product.get("id") if isinstance(product, dict) else None)
    raw = entry.get("saldoVirtualTotal")
    if raw is None:
        raw = entry.get("saldoFisicoTotal")
    try:
        balance = int(Decimal(str(raw)))
    except (InvalidOperation, ValueError):
        return None
    return None if product_id is None else (product_id, balance)


# ------------------------------------------------------------------ cliente


def _data(body: dict[str, Any]) -> Any:
    return body.get("data")


class BlingCatalogClient:
    """Leituras do catálogo sobre o `BlingClient` (limitador, retry e erros já tratados)."""

    def __init__(self, client: BlingClient) -> None:
        self.client = client

    async def list_categories_page(self, page: int) -> tuple[list[BlingCategory], bool]:
        body = await self.client.request(
            "GET", CATEGORIES_PATH, params={"pagina": page, "limite": PAGE_SIZE}
        )
        rows = _rows(body)
        categories = []
        for row in rows:
            category_id = _int(row.get("id"))
            name = _clean(row.get("descricao"), 100)
            if category_id is not None and name:
                categories.append(BlingCategory(category_id, name, _int(row.get("idCategoriaPai"))))
        return categories, len(rows) >= PAGE_SIZE

    async def list_products_page(
        self, page: int, *, changed_since: Optional[datetime] = None
    ) -> BlingProductPage:
        params: dict[str, Any] = {"pagina": page, "limite": PAGE_SIZE}
        if changed_since is not None:
            params["dataAlteracaoInicial"] = changed_since.strftime(_DATE_FORMAT)
        rows = _rows(await self.client.request("GET", PRODUCTS_PATH, params=params))
        items = []
        for row in rows:
            product_id = _int(row.get("id"))
            if product_id is None or row.get("idProdutoPai"):
                continue  # R1: variações listadas com idProdutoPai pertencem ao pai
            items.append(BlingListItem(product_id, _is_active(row)))
        return BlingProductPage(tuple(items), len(rows) >= PAGE_SIZE)

    async def get_product(self, bling_id: int) -> BlingProduct:
        body = await self.client.request("GET", f"{PRODUCTS_PATH}/{bling_id}")
        data = _data(body)
        if not isinstance(data, dict):
            raise BlingCatalogFormatError()
        return normalize_product(data)

    async def get_balances(self, bling_ids: list[int]) -> dict[int, int]:
        """Saldos de até `BALANCE_BATCH_SIZE` ids; ids sem saldo na resposta ficam de fora."""
        body = await self.client.request(
            "GET", BALANCES_PATH, params={"idsProdutos[]": [str(i) for i in bling_ids]}
        )
        balances: dict[int, int] = {}
        for row in _rows(body):
            parsed = _balance(row)
            if parsed is not None:
                balances[parsed[0]] = parsed[1]
        return balances


def _rows(body: dict[str, Any]) -> list[dict[str, Any]]:
    data = _data(body)
    if data is None:
        return []
    if not isinstance(data, list):
        raise BlingCatalogFormatError()
    return [row for row in data if isinstance(row, dict)]
