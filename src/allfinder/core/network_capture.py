"""
network_capture.py
==================
Módulo responsável por interceptar e filtrar URLs de mídia (M3U8, MPD, etc.)
capturadas durante a navegação automatizada com Playwright.

Inspirado na técnica de monitoramento de logs de performance do script do
Globoplay, mas generalizado para funcionar com qualquer site de streaming.

Funcionalidades:
- Filtragem de URLs de rastreamento, analytics e publicidade (blacklist).
- Normalização de URLs (remoção de query strings de rastreamento).
- Priorização de playlists principais (master, index, playlist).
- Suporte a múltiplos formatos: HLS (.m3u8) e MPEG-DASH (.mpd).
- Extração de URLs embutidas em parâmetros de redirecionamento.
"""

import re
import urllib.parse
from typing import List, Optional, Set
from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Constantes de filtragem
# ---------------------------------------------------------------------------

# Domínios e palavras-chave associados a rastreamento, analytics e publicidade.
# URLs que contenham qualquer um desses termos serão descartadas.
BLACKLIST_KEYWORDS: List[str] = [
    # Analytics e rastreamento
    "youbora", "youboranqs", "chartbeat", "analytics", "telemetry",
    "metrics", "heartbeat", "omtrdc", "hotjar", "scorecardresearch",
    "segment.io", "mixpanel", "amplitude", "newrelic", "datadog",
    "sentry.io", "bugsnag", "loggly", "splunk",
    # Publicidade
    "doubleclick", "googleads", "amazon-adsystem", "casalemedia",
    "adnxs", "advertising", "moatads", "krxd", "fwmrm.net",
    "ads.yahoo", "adform", "pubmatic", "openx", "rubiconproject",
    "spotxchange", "springserve", "yieldmo", "sharethrough",
    # Redes sociais (tracking pixels)
    "facebook.com/tr", "connect.facebook", "twitter.com/i/adsct",
    # Específicos do Globo que não são streams
    "horizon.globo.com",
    # Logs e diagnóstico
    "log.", "/log/", "logging", "beacon", "ping",
]

# Palavras-chave que indicam que a URL é provavelmente uma playlist principal.
# Essas URLs são priorizadas e inseridas no início da lista de resultados.
PRIORITY_KEYWORDS: List[str] = [
    "master", "index", "playlist", "chunklist", "manifest",
    "live", "stream", "hls", "dash",
]

# Parâmetros de query string que podem conter a URL real do stream embutida.
REDIRECT_PARAMS: List[str] = [
    "ep.URL", "url", "link", "target", "redir", "redirect", "src",
]

# Extensões de mídia suportadas
MEDIA_EXTENSIONS: List[str] = [".m3u8", ".mpd"]


# ---------------------------------------------------------------------------
# Estrutura de resultado
# ---------------------------------------------------------------------------

@dataclass
class CapturedStream:
    """Representa uma URL de stream capturada e classificada."""
    url: str
    format: str        # "hls" | "dash" | "unknown"
    is_priority: bool  # True se for uma playlist principal (master/index/etc.)
    raw_url: str       # URL original antes da normalização


# ---------------------------------------------------------------------------
# Funções de filtragem e normalização
# ---------------------------------------------------------------------------

def _detect_format(url: str) -> str:
    """Detecta o formato do stream com base na extensão ou padrão da URL."""
    url_lower = url.lower()
    if ".m3u8" in url_lower:
        return "hls"
    if ".mpd" in url_lower or "dash" in url_lower:
        return "dash"
    return "unknown"


def _is_blacklisted(url: str) -> bool:
    """Retorna True se a URL contiver alguma palavra-chave da blacklist."""
    url_lower = url.lower()
    return any(keyword in url_lower for keyword in BLACKLIST_KEYWORDS)


def _is_media_url(url: str) -> bool:
    """Retorna True se a URL contiver uma extensão de mídia suportada."""
    url_lower = url.lower()
    return any(ext in url_lower for ext in MEDIA_EXTENSIONS)


def _is_priority(url: str) -> bool:
    """Retorna True se a URL for provavelmente uma playlist principal."""
    url_lower = url.lower()
    return any(kw in url_lower for kw in PRIORITY_KEYWORDS)


def normalize_stream_url(url: str) -> str:
    """
    Normaliza uma URL de stream removendo parâmetros de query string que não
    fazem parte do endereço do recurso (ex: tokens de rastreamento, timestamps).

    Mantém apenas o esquema, domínio e caminho da URL.
    Inspirado na função normalize_m3u8_url() do script do Globoplay.
    """
    try:
        parsed = urllib.parse.urlparse(url)
        # Remove completamente a query string e o fragmento
        return urllib.parse.urlunparse((
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            "",  # params
            "",  # query
            "",  # fragment
        ))
    except Exception:
        return url


def extract_embedded_url(url: str) -> Optional[str]:
    """
    Verifica se a URL contém uma URL de stream embutida em seus parâmetros de
    query string (ex: URLs de redirecionamento do Google Analytics).

    Retorna a URL embutida se encontrada e válida, caso contrário None.
    """
    try:
        parsed = urllib.parse.urlparse(url)
        params = urllib.parse.parse_qs(parsed.query)
        for param in REDIRECT_PARAMS:
            if param in params:
                candidate = params[param][0]
                if _is_media_url(candidate):
                    return candidate
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# Classe principal: NetworkCapture
# ---------------------------------------------------------------------------

class NetworkCapture:
    """
    Gerenciador de captura de URLs de mídia durante a navegação com Playwright.

    Uso típico
    ----------
    >>> capture = NetworkCapture()
    >>> page.on("request", capture.handle_request)
    >>> # ... navegar e interagir com a página ...
    >>> streams = capture.get_streams()
    """

    def __init__(self, deduplicate: bool = True, normalize: bool = True):
        """
        Parâmetros
        ----------
        deduplicate : bool
            Se True (padrão), URLs duplicadas (após normalização) são ignoradas.
        normalize : bool
            Se True (padrão), remove query strings das URLs capturadas.
        """
        self.deduplicate = deduplicate
        self.normalize = normalize
        self._streams: List[CapturedStream] = []
        self._seen_urls: Set[str] = set()

    def reset(self):
        """Limpa todas as URLs capturadas. Útil ao processar múltiplas páginas."""
        self._streams.clear()
        self._seen_urls.clear()

    def handle_request(self, request) -> None:
        """
        Callback para o evento 'request' do Playwright.
        Deve ser registrado via: page.on("request", capture.handle_request)

        Parâmetros
        ----------
        request : playwright.async_api.Request
            Objeto de requisição do Playwright.
        """
        url = request.url
        self._process_url(url)

    async def handle_request_async(self, request) -> None:
        """Versão assíncrona do handle_request (para uso com async/await)."""
        url = request.url
        self._process_url(url)

    def _process_url(self, raw_url: str) -> None:
        """Processa uma URL bruta, verificando se é um stream válido."""
        # Verifica se há uma URL embutida nos parâmetros de redirecionamento
        embedded = extract_embedded_url(raw_url)
        url_to_check = embedded if embedded else raw_url

        # Verifica se é uma URL de mídia
        if not _is_media_url(url_to_check):
            return

        # Verifica se está na blacklist
        if _is_blacklisted(url_to_check):
            return

        # Normaliza a URL
        final_url = normalize_stream_url(url_to_check) if self.normalize else url_to_check

        # Deduplicação
        if self.deduplicate and final_url in self._seen_urls:
            return

        self._seen_urls.add(final_url)

        stream = CapturedStream(
            url=final_url,
            format=_detect_format(final_url),
            is_priority=_is_priority(final_url),
            raw_url=raw_url,
        )

        # URLs prioritárias vão para o início da lista
        if stream.is_priority:
            self._streams.insert(0, stream)
        else:
            self._streams.append(stream)

    def get_streams(self) -> List[CapturedStream]:
        """Retorna a lista de streams capturados, ordenada por prioridade."""
        return list(self._streams)

    def get_urls(self) -> List[str]:
        """Retorna apenas as URLs dos streams capturados."""
        return [s.url for s in self._streams]

    def get_best_url(self) -> Optional[str]:
        """
        Retorna a melhor URL de stream disponível.

        Prioridade:
        1. Primeira URL prioritária que contenha "playlist.m3u8"
        2. Primeira URL prioritária (master/index/etc.)
        3. Primeira URL disponível
        """
        streams = self.get_streams()
        if not streams:
            return None

        # Prioridade máxima: playlist.m3u8
        for s in streams:
            if "playlist.m3u8" in s.url.lower():
                return s.url

        # Segunda prioridade: qualquer URL prioritária
        for s in streams:
            if s.is_priority:
                return s.url

        # Fallback: primeira disponível
        return streams[0].url

    def has_streams(self) -> bool:
        """Retorna True se pelo menos um stream foi capturado."""
        return len(self._streams) > 0

    def has_priority_stream(self) -> bool:
        """Retorna True se pelo menos uma URL prioritária foi capturada."""
        return any(s.is_priority for s in self._streams)

    def __len__(self) -> int:
        return len(self._streams)

    def __repr__(self) -> str:
        return f"NetworkCapture(streams={len(self._streams)})"
