import asyncio
import json
import os
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Optional
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from playwright.async_api import async_playwright


_DOTENV_PARSE_ERROR: Optional[str] = None


def _load_dotenv() -> None:
    global _DOTENV_PARSE_ERROR
    base_dir = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(base_dir, ".env")
    if not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8") as f:
        raw = f.read()

    content = raw.strip()
    if not content:
        return

    if content.startswith("{"):
        try:
            data = json.loads(content)
            if isinstance(data, dict):
                for k, v in data.items():
                    if isinstance(k, str) and isinstance(v, str) and k:
                        cur = os.environ.get(k)
                        if not cur or cur.strip() in {"<seu cookie completo>", "<seu cookie>"}:
                            os.environ[k] = v
                return
        except Exception as e:
            _DOTENV_PARSE_ERROR = str(e)

    for raw_line in raw.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if (
            len(value) >= 2
            and ((value[0] == value[-1] == '"') or (value[0] == value[-1] == "'"))
        ):
            value = value[1:-1]
        if key:
            cur = os.environ.get(key)
            if not cur or cur.strip() in {"<seu cookie completo>", "<seu cookie>"}:
                os.environ[key] = value


_load_dotenv()


@dataclass(frozen=True)
class Link:
    url: str
    category: str
    item_quantity: int


@dataclass(frozen=True)
class Product:
    name: str
    price: Optional[float]
    old_price: Optional[float]
    discount: Optional[str]
    url: str
    origin_url: str
    url_image: Optional[str]
    category: str


@dataclass(frozen=True)
class Cupom:
    url: str
    category: str


_BLOCKED_TITLE_TERMS = {"hot", "cavalo", "pau", "gel", "excitante"}


def _should_skip_product_title(name: str) -> bool:
    words = set(re.findall(r"\b\w+\b", name.lower()))
    return any(term in words for term in _BLOCKED_TITLE_TERMS)


def _load_affiliate_cookie_from_local_file() -> Optional[str]:
    base_dir = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(base_dir, "secrets.local.json")
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    cookie = data.get("ML_AFFILIATE_COOKIE") if isinstance(data, dict) else None
    return cookie.strip() if isinstance(cookie, str) and cookie.strip() else None


def _load_affiliate_tag_from_local_file() -> Optional[str]:
    base_dir = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(base_dir, "secrets.local.json")
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    tag = data.get("ML_AFFILIATE_TAG") if isinstance(data, dict) else None
    return tag.strip() if isinstance(tag, str) and tag.strip() else None


def _normalize_cookie_header(cookie_header: str) -> str:
    raw = cookie_header.strip()
    if raw.lower().startswith("cookie:"):
        raw = raw.split(":", 1)[1].strip()

    parts = []
    for chunk in raw.split(";"):
        c = chunk.strip()
        if not c:
            continue
        if "=" not in c:
            parts.append(c)
            continue
        name, value = c.split("=", 1)
        name = name.strip()
        value = value.strip()
        if len(value) >= 2 and ((value[0] == value[-1] == "'") or (value[0] == value[-1] == '"')):
            value = value[1:-1]
        parts.append(f"{name}={value}")
    return "; ".join(parts)


def _cookie_cache_path() -> str:
    base_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_dir, "ml_cookie.current.json")


def _load_cached_affiliate_cookie() -> Optional[str]:
    path = _cookie_cache_path()
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        cookie = data.get("cookie") if isinstance(data, dict) else None
        if isinstance(cookie, str) and cookie.strip():
            return cookie.strip()
    except Exception:
        return None
    return None


def _looks_authenticated(cookie_header: str) -> bool:
    d = _cookie_header_to_dict(cookie_header)
    if "NSESSIONID_pampa_session" in d:
        return True
    if "ssid" in d and "orguserid" in d:
        return True
    if "ssid" in d and "orguseridp" in d:
        return True
    return False


def _save_cached_affiliate_cookie(cookie_header: str) -> None:
    if not _looks_authenticated(cookie_header):
        return
    path = _cookie_cache_path()
    payload = {
        "cookie": cookie_header,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)


def _cookie_header_to_playwright_cookies(cookie_header: str) -> list[dict[str, Any]]:
    normalized = _normalize_cookie_header(cookie_header)
    cookies: list[dict[str, Any]] = []
    for chunk in normalized.split(";"):
        c = chunk.strip()
        if not c or "=" not in c:
            continue
        name, value = c.split("=", 1)
        name = name.strip()
        value = value.strip()
        if not name:
            continue
        cookies.append(
            {
                "name": name,
                "value": value,
                "domain": ".mercadolivre.com.br",
                "path": "/",
            }
        )
    return cookies


def _cookie_header_to_dict(cookie_header: str) -> dict[str, str]:
    normalized = _normalize_cookie_header(cookie_header)
    out: dict[str, str] = {}
    for chunk in normalized.split(";"):
        c = chunk.strip()
        if not c or "=" not in c:
            continue
        name, value = c.split("=", 1)
        name = name.strip()
        value = value.strip()
        if name:
            out[name] = value
    return out


def _dict_to_cookie_header(values: dict[str, str]) -> str:
    parts: list[str] = []
    for k, v in values.items():
        if k and v is not None:
            parts.append(f"{k}={v}")
    return "; ".join(parts)


def _playwright_cookies_to_header(cookies: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for c in cookies:
        name = c.get("name")
        value = c.get("value")
        if isinstance(name, str) and name and isinstance(value, str):
            parts.append(f"{name}={value}")
    return "; ".join(parts)


async def _refresh_affiliate_cookie(playwright, browser, cookie_seed: str) -> str:
    cookie_seed = _normalize_cookie_header(cookie_seed)
    context = await browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        locale="pt-BR",
        timezone_id="America/Sao_Paulo",
        extra_http_headers={
            "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
            "DNT": "1",
            "Upgrade-Insecure-Requests": "1",
        },
    )
    try:
        seed_cookies = _cookie_header_to_playwright_cookies(cookie_seed)
        if seed_cookies:
            await context.add_cookies(seed_cookies)
        page = await context.new_page()
        await page.add_init_script(
            """() => {
  Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
  Object.defineProperty(navigator, 'languages', { get: () => ['pt-BR', 'pt', 'en-US', 'en'] });
  Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
}""",
        )
        await page.goto("https://www.mercadolivre.com.br/", wait_until="networkidle")
        await page.wait_for_timeout(2000)
        cookies = await context.cookies("https://www.mercadolivre.com.br/")
        refreshed = _playwright_cookies_to_header(cookies)
        seed_map = _cookie_header_to_dict(cookie_seed)
        refreshed_map = _cookie_header_to_dict(refreshed)
        seed_map.update(refreshed_map)
        merged = _dict_to_cookie_header(seed_map)
        return merged or cookie_seed
    finally:
        await context.close()


def _get_cookie_value(cookie_header: str, name: str) -> Optional[str]:
    m = re.search(rf"(?:^|;\s*){re.escape(name)}=([^;]+)", cookie_header)
    return m.group(1) if m else None


def _normalize_url(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    v = value.strip()
    if len(v) >= 2 and v[0] == "`" and v[-1] == "`":
        v = v[1:-1].strip()
    return v or None


def _canonicalize_url(value: Optional[str]) -> Optional[str]:
    v = _normalize_url(value)
    if not v:
        return None
    if not v.startswith("http"):
        v = "https://" + v.lstrip("/")
    parts = urlsplit(v)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, parts.query, ""))


def _normalize_category(value: str) -> str:
    v = (value or "").strip().lower()
    if v in {"geral", "roupas", "academia", "eletronicos", "beleza", "eletrodomesticos"}:
        return v
    if "roup" in v:
        return "roupas"
    if "academ" in v:
        return "academia"
    if "elet" in v or "eletr" in v or "alet" in v:
        return "eletronicos"
    if "belez" in v:
        return "beleza"
    if "domestic" in v:
        return "eletrodomesticos"
    return "geral"


def _discount_percent(value: Optional[str]) -> Optional[int]:
    if not value:
        return None
    m = re.search(r"(\d+)\s*%", value)
    if not m:
        return None
    try:
        return int(m.group(1))
    except ValueError:
        return None


def _passes_product_rules(p: Product) -> bool:
    if p.price is not None and p.price > 75:
        return True
    pct = _discount_percent(p.discount)
    return pct is not None and pct > 60


def _with_offset(url: str, offset: int) -> str:
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    if offset > 0:
        query["offset"] = str(offset)
    else:
        query.pop("offset", None)
    new_query = urlencode(query, doseq=True)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, new_query, parts.fragment))


def _extract_paging(data: dict[str, Any]) -> dict[str, Any]:
    candidates = [
        ("appProps", "pageProps", "data", "paging"),
        ("pageProps", "data", "paging"),
        ("data", "paging"),
        ("paging",),
    ]
    for path in candidates:
        cur: Any = data
        ok = True
        for k in path:
            if not isinstance(cur, dict) or k not in cur:
                ok = False
                break
            cur = cur[k]
        if ok and isinstance(cur, dict):
            return cur
    return {}


def _extract_json_from_nordic_ctx(script_text: str) -> dict[str, Any]:
    m = re.search(r"_n\.ctx\.r\s*=\s*", script_text)
    if not m:
        raise ValueError("Não encontrei '_n.ctx.r =' dentro do script __NORDIC_RENDERING_CTX__")

    start = script_text.find("{", m.end())
    if start == -1:
        raise ValueError("Não encontrei '{' após '_n.ctx.r ='")

    depth = 0
    end = -1
    in_string = False
    escape = False
    for i in range(start, len(script_text)):
        ch = script_text[i]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue

        if ch == '"':
            in_string = True
            continue

        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break

    if end == -1:
        raise ValueError("Não consegui fechar o objeto JSON do _n.ctx.r")

    raw = script_text[start:end].strip()
    raw = re.sub(r",\s*([}\]])", r"\1", raw)
    return json.loads(raw)


def _extract_first_json_object(text: str) -> dict[str, Any]:
    start = text.find("{")
    if start == -1:
        raise ValueError("Não encontrei nenhum objeto JSON no texto")

    depth = 0
    end = -1
    in_string = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue

        if ch == '"':
            in_string = True
            continue

        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break

    if end == -1:
        raise ValueError("Não consegui fechar o objeto JSON do texto")

    raw = text[start:end].strip()
    raw = re.sub(r",\s*([}\]])", r"\1", raw)
    return json.loads(raw)


def _extract_data_from_text(text: str) -> dict[str, Any]:
    if "_n.ctx.r" in text:
        return _extract_json_from_nordic_ctx(text)

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return _extract_first_json_object(text)


def _extract_items(data: dict[str, Any]) -> list[dict[str, Any]]:
    paths = [
        ("appProps", "pageProps", "data", "items"),
        ("pageProps", "data", "items"),
        ("data", "items"),
        ("items",),
    ]
    for path in paths:
        cur: Any = data
        ok = True
        for k in path:
            if not isinstance(cur, dict) or k not in cur:
                ok = False
                break
            cur = cur[k]
        if ok and isinstance(cur, list):
            return [x for x in cur if isinstance(x, dict)]
    return []


async def _create_affiliate_links(
    playwright,
    urls: list[str],
    tag: str,
    cookie_header: str,
) -> dict[str, str]:
    cookie_header = _normalize_cookie_header(cookie_header)
    csrf = _get_cookie_value(cookie_header, "_csrf")
    headers: dict[str, str] = {
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json",
        "Cookie": cookie_header,
        "Origin": "https://www.mercadolivre.com.br",
        "Referer": "https://www.mercadolivre.com.br/",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
        "X-Requested-With": "XMLHttpRequest",
    }
    if csrf:
        headers["x-csrf-token"] = csrf

    api = await playwright.request.new_context(extra_http_headers=headers)
    try:
        resp = await api.post(
            "https://www.mercadolivre.com.br/affiliate-program/api/v2/affiliates/createLink",
            data=json.dumps({"urls": urls, "tag": tag}),
        )
        body_text = await resp.text()
        if not resp.ok:
            raise ValueError(f"createLink falhou (HTTP {resp.status}): {body_text[:500]}")

        payload = json.loads(body_text) if body_text else {}
        mapping: dict[str, str] = {(_canonicalize_url(u) or u): u for u in urls}

        candidates = []
        if isinstance(payload, dict):
            if isinstance(payload.get("urls"), list):
                candidates = payload["urls"]
            elif isinstance(payload.get("links"), list):
                candidates = payload["links"]
            elif isinstance(payload.get("data"), dict) and isinstance(payload["data"].get("links"), list):
                candidates = payload["data"]["links"]
            elif isinstance(payload.get("results"), list):
                candidates = payload["results"]

        for entry in candidates:
            if not isinstance(entry, dict):
                continue
            original = (
                entry.get("origin_url")
                or entry.get("originUrl")
                or entry.get("original_url")
                or entry.get("originalUrl")
                or entry.get("url_original")
                or entry.get("urlOriginal")
            )
            affiliate = (
                entry.get("url")
                or entry.get("affiliate_url")
                or entry.get("affiliateUrl")
                or entry.get("short_url")
                or entry.get("shortUrl")
                or entry.get("long_url")
                or entry.get("longUrl")
                or entry.get("link")
            )
            original_n = _canonicalize_url(original) if isinstance(original, str) else None
            affiliate_n = _normalize_url(affiliate) if isinstance(affiliate, str) else None
            if original_n and affiliate_n:
                mapping[original_n] = affiliate_n

        return mapping
    finally:
        await api.dispose()


def _first_component(card: dict[str, Any], component_type: str) -> Optional[dict[str, Any]]:
    for c in card.get("components", []) or []:
        if c.get("type") == component_type:
            return c
    return None


def _to_float(v: Any) -> Optional[float]:
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        try:
            return float(v.replace(".", "").replace(",", "."))
        except ValueError:
            return None
    return None


def _extract_previous_price(price: dict[str, Any]) -> Optional[float]:
    direct = _to_float((price.get("previous_price") or {}).get("value"))
    if direct is not None:
        return direct

    labels = price.get("price_labels")
    if not isinstance(labels, list):
        return None
    for label in labels:
        if not isinstance(label, dict):
            continue
        for v in label.get("values") or []:
            if isinstance(v, dict) and v.get("key") == "previous_price":
                value = _to_float((v.get("price") or {}).get("value"))
                if value is not None:
                    return value
    return None


def _extract_discount_text(price: dict[str, Any]) -> Optional[str]:
    direct = (price.get("discount_label") or {}).get("text")
    if isinstance(direct, str) and direct.strip():
        return direct.strip()

    polylabel = price.get("discount_polylabel") or {}
    for v in polylabel.get("values") or []:
        if isinstance(v, dict):
            text = ((v.get("pill") or {}).get("text"))
            if isinstance(text, str) and text.strip():
                return text.strip()
    return None


def _build_product(item: dict[str, Any], category: str) -> Optional[Product]:
    card = item.get("card") or {}
    metadata = card.get("metadata") or {}

    title_comp = _first_component(card, "title") or {}
    price_comp = _first_component(card, "price") or {}

    name = (((title_comp.get("title") or {}).get("text")) or "").strip()
    if not name:
        return None
    if _should_skip_product_title(name):
        return None

    price_dict = price_comp.get("price") or {}
    price = _to_float((price_dict.get("current_price") or {}).get("value"))
    old_price = _extract_previous_price(price_dict)
    discount = _extract_discount_text(price_dict)

    url = _canonicalize_url(metadata.get("url"))
    if not url:
        return None

    pictures = (card.get("pictures") or {}).get("pictures") or []
    pic_id = (pictures[0].get("id") if pictures else None) if isinstance(pictures, list) else None
    url_image = None
    if pic_id:
        url_image = f"https://http2.mlstatic.com/D_{pic_id}-F.jpg"

    return Product(
        name=name,
        price=price,
        old_price=old_price,
        discount=discount,
        url=url,
        origin_url=url,
        url_image=url_image,
        category=_normalize_category(category),
    )


def _build_product_from_dom(item: dict[str, Any], category: str) -> Optional[Product]:
    name = (item.get("name") or "").strip() if isinstance(item, dict) else ""
    url = _canonicalize_url(item.get("url") if isinstance(item, dict) else None)
    if not name or not url:
        return None
    if _should_skip_product_title(name):
        return None

    price_raw = item.get("price") if isinstance(item, dict) else None
    price: Optional[float]
    if isinstance(price_raw, (int, float)):
        price = float(price_raw)
    else:
        price = _to_float(price_raw)

    url_image = item.get("url_image") if isinstance(item, dict) else None
    if not isinstance(url_image, str) or not url_image.strip():
        url_image = None

    discount = item.get("discount") if isinstance(item, dict) else None
    if not isinstance(discount, str) or not discount.strip():
        discount = None

    old_price_raw = item.get("old_price") if isinstance(item, dict) else None
    old_price: Optional[float]
    if isinstance(old_price_raw, (int, float)):
        old_price = float(old_price_raw)
    else:
        old_price = _to_float(old_price_raw)

    return Product(
        name=name,
        price=price,
        old_price=old_price,
        discount=discount,
        url=url,
        origin_url=url,
        url_image=url_image,
        category=_normalize_category(category),
    )


async def _scrape_products_from_dom(page) -> list[dict[str, Any]]:
    try:
        for _ in range(2):
            try:
                items = await page.evaluate(
                    """() => {
  const pickAmount = (amount) => {
    const fraction = amount?.querySelector?.('.andes-money-amount__fraction')?.textContent?.trim() || '';
    const cents = amount?.querySelector?.('.andes-money-amount__cents')?.textContent?.trim() || '';
    const f = fraction.replace(/\\./g, '');
    const v = f ? parseInt(f, 10) : NaN;
    const c = cents ? parseInt(cents, 10) : 0;
    if (Number.isFinite(v)) {
      const cc = Number.isFinite(c) ? c : 0;
      return v + (cc / 100);
    }
    return null;
  };

  const pickPrice = (root) => {
    const amount = root?.querySelector?.('.poly-price__current .andes-money-amount') || null;
    return pickAmount(amount);
  };

  const pickOldPrice = (root) => {
    const amount = root?.querySelector?.('.poly-price__labels .andes-money-amount--previous') || null;
    return pickAmount(amount);
  };

  const anchors = Array.from(document.querySelectorAll('a.poly-component__title'));
  const out = [];
  for (const a of anchors) {
    const name = (a.textContent || '').trim();
    const url = a.href || '';
    if (!name || !url) continue;

    const card = a.closest('li, article, div');
    const img = card?.querySelector?.('img.poly-component__picture') || null;
    const url_image = (img && (img.currentSrc || img.src)) ? (img.currentSrc || img.src) : null;

    const discountEl = card?.querySelector?.('.poly-price__discount-polylabel .polylabel-pill, span.poly-coupons__pill') || null;
    const discount = (discountEl?.textContent || '').trim() || null;

    const price = pickPrice(card);
    const old_price = pickOldPrice(card);

    out.push({ name, url, url_image, discount, price, old_price });
  }
  return out;
}""",
                )
                if isinstance(items, list):
                    return [x for x in items if isinstance(x, dict)]
                return []
            except Exception as e:
                if "Execution context was destroyed" in str(e):
                    await page.wait_for_load_state("domcontentloaded")
                    await page.wait_for_timeout(500)
                    continue
                raise
    except Exception:
        return []
    return []


async def _scrape_items_for_url(page, url: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    payload: dict[str, str] = {"text": ""}

    async def handle_response(resp) -> None:
        if payload["text"]:
            return
        try:
            ct = (resp.headers or {}).get("content-type", "")
            if not any(x in ct for x in ("json", "javascript", "text", "html")):
                return
            body = await resp.text()
        except Exception:
            return

        if "_n.ctx.r" in body or ('"items"' in body and '"card"' in body):
            payload["text"] = body

    page.on("response", lambda resp: asyncio.create_task(handle_response(resp)))

    response = await page.goto(url, wait_until="domcontentloaded")
    await page.wait_for_load_state("networkidle", timeout=30000)
    await page.wait_for_timeout(2000)
    script_text = ""
    for _ in range(2):
        try:
            script_text = await page.evaluate(
                """() => {
  const byId = document.querySelector('script#__NORDIC_RENDERING_CTX__');
  if (byId && byId.textContent) return byId.textContent;
  for (const s of document.scripts) {
    const t = s.textContent || '';
    if (t.includes('_n.ctx.r')) return t;
  }
  return '';
}""",
            )
            break
        except Exception as e:
            if "Execution context was destroyed" in str(e):
                await page.wait_for_load_state("domcontentloaded")
                await page.wait_for_timeout(500)
                continue
            raise
    if (not script_text) and response:
        html = await response.text()
        m = re.search(
            r'<script[^>]*id="__NORDIC_RENDERING_CTX__"[^>]*>(.*?)</script>',
            html,
            re.IGNORECASE | re.DOTALL,
        )
        if m:
            script_text = m.group(1)
        else:
            m2 = re.search(
                r"<script[^>]*>(?:(?!</script>).)*_n\.ctx\.r(?:(?!</script>).)*</script>",
                html,
                re.IGNORECASE | re.DOTALL,
            )
            if m2:
                m3 = re.search(
                    r"<script[^>]*>(.*?)</script>",
                    m2.group(0),
                    re.IGNORECASE | re.DOTALL,
                )
                if m3:
                    script_text = m3.group(1)
    raw_text = script_text or payload["text"]
    if not raw_text:
        dom_items = await _scrape_products_from_dom(page)
        if dom_items:
            return {"_dom_fallback": True}, dom_items
        return {}, []

    try:
        data = _extract_data_from_text(raw_text)
        items = _extract_items(data)
        if not items and isinstance(data.get("appProps"), dict):
            items = _extract_items(data.get("appProps"))
        if items:
            return data, items
    except Exception:
        data = {}

    dom_items = await _scrape_products_from_dom(page)
    if dom_items:
        return {"_dom_fallback": True, **(data if isinstance(data, dict) else {})}, dom_items
    return data if isinstance(data, dict) else {}, []


async def _scrape_products_page(playwright, browser, link: Link, offset: int) -> tuple[list[Product], dict[str, Any]]:
    context = await browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        locale="pt-BR",
        timezone_id="America/Sao_Paulo",
        extra_http_headers={
            "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
            "DNT": "1",
            "Upgrade-Insecure-Requests": "1",
        },
    )
    page = await context.new_page()
    await page.add_init_script(
        """() => {
  Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
  Object.defineProperty(navigator, 'languages', { get: () => ['pt-BR', 'pt', 'en-US', 'en'] });
  Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
}""",
    )

    try:
        url = _with_offset(link.url, offset)
        data, items = await _scrape_items_for_url(page, url)
        products: list[Product] = []
        if isinstance(data, dict) and data.get("_dom_fallback"):
            for item in items:
                if not isinstance(item, dict):
                    continue
                pdt = _build_product_from_dom(item, link.category)
                if pdt:
                    products.append(pdt)
            return products, {}
        for item in items:
            if not isinstance(item, dict):
                continue
            pdt = _build_product(item, link.category)
            if pdt:
                products.append(pdt)
        return products, _extract_paging(data)
    finally:
        await context.close()


def _http_json(method: str, url: str, headers: dict[str, str], body: Optional[dict[str, Any]] = None) -> Any:
    data = None
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = Request(url, data=data, method=method.upper())
    for k, v in headers.items():
        req.add_header(k, v)
    try:
        with urlopen(req, timeout=60) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            if not raw:
                return None
            return json.loads(raw)
    except HTTPError as e:
        raw = ""
        try:
            raw = e.read().decode("utf-8", errors="replace")
        except Exception:
            pass
        raise ValueError(f"HTTP {e.code} ao chamar {url}: {raw[:500]}") from e
    except URLError as e:
        host = urlsplit(url).hostname
        hint = ""
        reason = getattr(e, "reason", None)
        reason_txt = str(reason) if reason is not None else str(e)
        if "getaddrinfo failed" in reason_txt or "Name or service not known" in reason_txt:
            hint = (
                " (falha de DNS). Verifique se SUPABASE_URL está correto (sem aspas/crases), "
                "se há internet/proxy e se o domínio resolve."
            )
        elif "timed out" in reason_txt.lower():
            hint = " (timeout). Verifique sua conexão/rede e liberação para *.supabase.co."
        raise ValueError(f"Falha de rede ao chamar {url} (host={host}): {reason_txt}{hint}") from e


def _supabase_headers() -> dict[str, str]:
    key = os.environ.get("SUPABASE_ANON_KEY") or os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or ""
    if not key:
        raise ValueError("SUPABASE_ANON_KEY (ou SUPABASE_SERVICE_ROLE_KEY) não está configurado no .env")
    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def _supabase_base_url() -> str:
    raw = os.environ.get("SUPABASE_URL")
    url = _normalize_url(raw)
    if not url:
        raise ValueError("SUPABASE_URL não está configurado no .env")
    if "://" not in url:
        url = f"https://{url}"
    parts = urlsplit(url)
    if parts.scheme not in {"https", "http"} or not parts.netloc:
        raise ValueError(f"SUPABASE_URL inválido: {url}")
    path = (parts.path or "").rstrip("/")
    if "/rest/v1" in path:
        path = path.split("/rest/v1", 1)[0].rstrip("/")
    normalized = urlunsplit((parts.scheme, parts.netloc, path, "", "")).rstrip("/")
    return normalized


def _supabase_table() -> str:
    return (os.environ.get("SUPABASE_TABLE_PRODUCTS") or "products").strip()


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return int(str(raw).strip())
    except ValueError:
        return default


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    v = str(raw).strip().lower()
    if v in {"1", "true", "t", "yes", "y", "on"}:
        return True
    if v in {"0", "false", "f", "no", "n", "off"}:
        return False
    return default


def _supabase_fetch_existing_origin_urls(origin_urls: list[str]) -> set[str]:
    if not origin_urls:
        return set()
    base = _supabase_base_url()
    table = _supabase_table()
    headers = _supabase_headers()

    encoded = [quote(u, safe="") for u in origin_urls]
    query = f"select=origin_url&origin_url=in.({','.join(encoded)})"
    url = f"{base}/rest/v1/{table}?{query}"
    try:
        rows = _http_json("GET", url, headers) or []
    except Exception as e:
        raise ValueError(f"Falha ao consultar Supabase (tabela {table}): {e}") from e

    existing = set()
    if isinstance(rows, list):
        for r in rows:
            if isinstance(r, dict) and isinstance(r.get("origin_url"), str):
                existing.add(r["origin_url"])
    return existing


def _supabase_links_table() -> str:
    return (os.environ.get("SUPABASE_TABLE_LINKS") or "scrape_links").strip()


def _supabase_fetch_links() -> list[Link]:
    base = _supabase_base_url()
    table = _supabase_links_table()
    headers = _supabase_headers()
    query = "select=url,category,item_quantity&active=eq.true&order=created_at.asc"
    url = f"{base}/rest/v1/{table}?{query}"
    try:
        rows = _http_json("GET", url, headers) or []
    except Exception as e:
        raise ValueError(f"Falha ao consultar links no Supabase (tabela {table}): {e}") from e

    default_item_quantity = _env_int("ML_DESIRED_NEW", 6)
    links: list[Link] = []
    if isinstance(rows, list):
        for r in rows:
            if not isinstance(r, dict):
                continue
            url_value = r.get("url")
            category_value = r.get("category")
            if not (isinstance(url_value, str) and url_value.strip() and isinstance(category_value, str) and category_value.strip()):
                continue
            item_quantity = r.get("item_quantity")
            if not isinstance(item_quantity, int) or item_quantity <= 0:
                item_quantity = default_item_quantity
            links.append(Link(url=url_value.strip(), category=category_value.strip(), item_quantity=item_quantity))
    return links


def _supabase_insert_product(record: dict[str, Any]) -> None:
    base = _supabase_base_url()
    table = _supabase_table()
    headers = _supabase_headers()
    headers["Prefer"] = "return=minimal"
    url = f"{base}/rest/v1/{table}"
    try:
        _http_json("POST", url, headers, record)
    except Exception as e:
        raise ValueError(f"Falha ao inserir no Supabase (tabela {table}): {e}") from e


def _post_webhook(url: str, payload: dict[str, Any]) -> None:
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    _http_json("POST", url, headers, payload)


async def main() -> None:
    affiliate_cookie = os.environ.get("ML_AFFILIATE_COOKIE") or _load_affiliate_cookie_from_local_file()
    affiliate_tag = (
        os.environ.get("ML_AFFILIATE_TAG")
        or _load_affiliate_tag_from_local_file()
        or "souzadaniel20220815093912"
    )
    if not affiliate_cookie:
        if os.path.exists(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")) and _DOTENV_PARSE_ERROR:
            raise ValueError(
                "ML_AFFILIATE_COOKIE não está configurado. Seu arquivo .env parece estar em JSON inválido "
                f"({_DOTENV_PARSE_ERROR}). Ajuste para KEY=VALUE ou JSON válido."
            )
        raise ValueError(
            "ML_AFFILIATE_COOKIE não está configurado. "
            "Defina a variável de ambiente ML_AFFILIATE_COOKIE ou preencha secrets.local.json para habilitar links de afiliado."
        )

    cached = _load_cached_affiliate_cookie()
    affiliate_cookie_seed = affiliate_cookie
    affiliate_cookie_current = cached if cached and _looks_authenticated(cached) else affiliate_cookie_seed

    try:
        links = _supabase_fetch_links()
    except Exception as e:
        raise ValueError(f"Falha ao carregar links cadastrados: {e}") from e
    if not links:
        raise ValueError(
            f"Nenhum link ativo cadastrado na tabela {_supabase_links_table()}. "
            "Cadastre pelo menos um link pelo painel admin (ou diretamente no Supabase)."
        )

    webhook_url = "https://n8n-n8n.wtw36t.easypanel.host/webhook/c4ab90b7-7cfb-49e5-95db-cf8909da04ff"
    desired_batch = _env_int("ML_DESIRED_BATCH", 15)
    max_page_fetches = _env_int("ML_MAX_PAGE_FETCHES", 20)
    webhook_delay_seconds = _env_int("ML_WEBHOOK_DELAY_SECONDS", 300)
    max_links = _env_int("ML_MAX_LINKS", len(links))
    continue_on_supabase_error = _env_bool("SUPABASE_CONTINUE_ON_ERROR", True)
    supabase_available = True
    try:
        _supabase_base_url()
        _supabase_headers()
        _supabase_table()
    except Exception as e:
        supabase_available = False
        print(f"Supabase indisponível (seguindo sem Supabase): {e}")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--disable-blink-features=AutomationControlled"])
        try:
            for link in links[: max_links if max_links > 0 else 0]:
                offset = 0
                page_fetches = 0
                seen_origin_urls: set[str] = set()
                candidates_new: list[Product] = []
                link_desired_new = link.item_quantity

                current_filtered: list[Product] = []
                cursor = 0
                current_limit = 48

                skip_link = False
                while len(candidates_new) < link_desired_new and page_fetches < max_page_fetches:
                    if cursor >= len(current_filtered):
                        try:
                            products_page, paging = await _scrape_products_page(p, browser, link, offset)
                        except Exception:
                            skip_link = True
                            break
                        current_limit = paging.get("limit") if isinstance(paging.get("limit"), int) else 48
                        if not isinstance(current_limit, int) or current_limit <= 0:
                            current_limit = 48

                        seen_before = len(seen_origin_urls)
                        current_filtered = [
                            x
                            for x in products_page
                            if _passes_product_rules(x) and x.origin_url not in seen_origin_urls
                        ]
                        for x in current_filtered:
                            seen_origin_urls.add(x.origin_url)
                        cursor = 0
                        page_fetches += 1

                        if not current_filtered:
                            if len(seen_origin_urls) == seen_before:
                                break
                            offset += current_limit
                            continue

                    batch = current_filtered[cursor : cursor + desired_batch]
                    cursor += desired_batch
                    if not batch:
                        offset += current_limit
                        continue

                    existing: set[str] = set()
                    if supabase_available:
                        try:
                            existing = _supabase_fetch_existing_origin_urls([x.origin_url for x in batch])
                        except Exception as e:
                            print(f"Falha ao consultar Supabase (seguindo sem Supabase): {e}")
                            if not continue_on_supabase_error:
                                raise
                            supabase_available = False
                    for x in batch:
                        if x.origin_url not in existing:
                            candidates_new.append(x)
                            if len(candidates_new) >= link_desired_new:
                                break

                    if cursor >= len(current_filtered):
                        offset += current_limit

                if skip_link or len(candidates_new) < link_desired_new:
                    continue

                to_send = candidates_new[:link_desired_new]
                origin_urls = [x.origin_url for x in to_send]
                try:
                    affiliate_map = await _create_affiliate_links(
                        p,
                        origin_urls,
                        affiliate_tag,
                        affiliate_cookie_current,
                    )
                except Exception as e:
                    msg = str(e)
                    if "HTTP 403" in msg or "HTTP 401" in msg:
                        refreshed = await _refresh_affiliate_cookie(p, browser, affiliate_cookie_seed)
                        if _looks_authenticated(refreshed):
                            affiliate_cookie_current = refreshed
                            _save_cached_affiliate_cookie(affiliate_cookie_current)
                        affiliate_map = await _create_affiliate_links(
                            p,
                            origin_urls,
                            affiliate_tag,
                            affiliate_cookie_current,
                        )
                    else:
                        raise
                missing = [u for u in origin_urls if affiliate_map.get(u) in (None, u)]
                if missing:
                    raise ValueError(
                        "Falha ao gerar link de afiliado para ao menos 1 URL. "
                        "Verifique se o cookie está válido e se o endpoint createLink está respondendo como esperado."
                    )

                for i, pdt in enumerate(to_send):
                    now = datetime.now(timezone.utc).isoformat()
                    record = {
                        "name": pdt.name,
                        "price": pdt.price,
                        "old_price": pdt.old_price,
                        "discount": pdt.discount,
                        "url": affiliate_map[pdt.origin_url],
                        "origin_url": pdt.origin_url,
                        "url_image": pdt.url_image,
                        "category": pdt.category,
                        "scraped_at": now,
                    }
                    if supabase_available:
                        try:
                            _supabase_insert_product(record)
                        except Exception as e:
                            print(f"Falha ao inserir no Supabase (seguindo sem Supabase): {e}")
                            if not continue_on_supabase_error:
                                raise
                            supabase_available = False
                    _post_webhook(webhook_url, record)
                    print(json.dumps(record, ensure_ascii=False))
                    if i < len(to_send) - 1:
                        await asyncio.sleep(webhook_delay_seconds)
        finally:
            await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
