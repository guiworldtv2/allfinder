# allfinder

Uma ferramenta em Python para extrair URLs `.m3u8` e `.mpd` de sites de streaming, utilizando automação de navegador (Playwright) para simular a interação do usuário e interceptar requisições de rede.

## Funcionalidades

- **Extração de M3U8/MPD:** Captura URLs de streaming carregadas dinamicamente pelo player de vídeo.
- **Suporte a Múltiplos Navegadores:** Chrome, Microsoft Edge, Firefox e Chromium.
- **Reutilização de Sessão (Perfil):** Acessa sites que exigem login reutilizando um perfil existente do navegador — sem precisar automatizar o processo de autenticação.
- **Captura de Rede Robusta:** Filtragem avançada de URLs de rastreamento, analytics e publicidade. Normalização e priorização automática de playlists principais.
- **Sistema de Plugins:** Plugins específicos por site (ex: Globoplay) com lógica de interação personalizada. Fallback automático para o plugin genérico.
- **Suporte a yt-dlp:** Integração automática com yt-dlp para YouTube e outros sites compatíveis.
- **Modo Headless:** Suporte para execução sem interface gráfica.

## Instalação

### Sem Git (recomendado para Windows)

Não precisa ter o Git instalado. Basta rodar no terminal:

```bash
pip install https://github.com/guiworldtv2/allfinder/releases/download/v0.2.0/allfinder-0.2.0-py3-none-any.whl
```

### Com Git instalado

```bash
pip install git+https://github.com/guiworldtv2/allfinder.git
```

### Para desenvolvimento local

```bash
git clone https://github.com/guiworldtv2/allfinder.git
cd allfinder
pip install -e .
```

## Uso

### Uso básico

```bash
allfinder https://exemplo.com/video-com-streaming
```

### Escolher o navegador

```bash
# Usar o Google Chrome instalado no sistema
allfinder https://exemplo.com/live --browser chrome

# Usar o Microsoft Edge
allfinder https://exemplo.com/live --browser edge

# Usar o Firefox
allfinder https://exemplo.com/live --browser firefox
```

### Reutilizar sessão logada (perfil existente)

Esta é a funcionalidade mais poderosa para sites que exigem assinatura. O navegador deve estar previamente logado no perfil especificado. **Feche o navegador antes de rodar o comando.**

```bash
# Usar o perfil padrão do Edge (já logado no Globoplay, por exemplo)
allfinder https://globoplay.globo.com/v/7832875/ --browser edge --use-profile --no-headless

# Especificar o nome do perfil
allfinder https://globoplay.globo.com/v/7832875/ --browser edge --use-profile --profile "Pessoa 1" --no-headless

# Salvar resultado em arquivo .m3u
allfinder https://globoplay.globo.com/v/7832875/ --browser edge --use-profile --profile "Pessoa 1" --no-headless -o globo.m3u
```

### Listar perfis disponíveis

```bash
allfinder --list-profiles
```

Saída de exemplo:
```
=== Navegadores e Perfis Detectados ===

[CHROME] C:\Program Files\Google\Chrome\Application\chrome.exe
  - Perfil: 'Default' | Dir: Default

[EDGE] C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe
  - Perfil: 'Default' | Dir: Default
  - Perfil: 'Pessoa 1' | Dir: Profile 1

[FIREFOX] C:\Program Files\Mozilla Firefox\firefox.exe
  - Perfil: 'default-release' | Dir: ...

[CHROMIUM] NÃO ENCONTRADO
```

### Salvar resultado em arquivo .m3u

```bash
allfinder https://exemplo.com/live -o minha_lista.m3u
```

### Usar cookies de arquivo

```bash
# Arquivo JSON (formato do EditThisCookie)
allfinder https://exemplo.com/live --cookies cookies.json

# Arquivo Netscape (.txt, exportado pelo browser)
allfinder https://exemplo.com/live --cookies cookies.txt
```

### Múltiplas URLs

```bash
allfinder https://site1.com/live https://site2.com/stream -o lista.m3u
```

## Opções Completas

```
Opções de Navegador:
  --browser {chrome,edge,firefox,chromium}
                        Navegador a ser usado (padrão: chromium).
  --use-profile         Reutiliza um perfil existente do navegador para acessar
                        sites que exigem login.
  --profile NOME_DO_PERFIL
                        Nome do perfil do navegador a usar (ex: "Pessoa 1").
  --list-profiles       Lista todos os navegadores e perfis detectados e sai.

Opções de Execução:
  --headless            Executa o navegador em modo headless (padrão).
  --no-headless         Executa o navegador com interface gráfica.
  --timeout TIMEOUT     Tempo limite em milissegundos (padrão: 60000).

Opções de Cookies:
  --cookies-from-browser {chrome,edge}
                        Importa cookies do navegador especificado.
  --cookies COOKIES     Caminho para um arquivo de cookies (.txt ou .json).

Saída:
  --output, -o OUTPUT   Caminho para salvar o arquivo .m3u resultante.
```

## Arquitetura

```
src/allfinder/
├── core/
│   ├── extractor.py        # Extrator principal (Playwright)
│   ├── browser_profile.py  # Detecção e reutilização de perfis de navegador
│   └── network_capture.py  # Captura e filtragem de tráfego de rede
├── plugins/
│   ├── generic/
│   │   └── base.py         # BasePlugin e GenericPlugin (fallback)
│   ├── specific_sites/
│   │   └── globoplay.py    # Plugin específico para o Globoplay
│   └── manager.py          # Gerenciador de plugins
└── cli/
    └── main.py             # Interface de linha de comando
```

### Criando um Plugin Personalizado

```python
from allfinder.plugins.generic.base import BasePlugin
from playwright.async_api import Page
import asyncio

class MeuSitePlugin(BasePlugin):
    @property
    def name(self) -> str:
        return "Meu Site"

    @property
    def domain_pattern(self) -> str:
        return r"meusite\.com"

    async def interact(self, page: Page) -> None:
        # Clica no botão de play específico do site
        await page.click(".meu-botao-play")
        await asyncio.sleep(2)
```

Registre o plugin:

```python
from allfinder.plugins.manager import PluginManager
manager = PluginManager()
manager.register_plugin(MeuSitePlugin())
```

## Licença

Este projeto está licenciado sob a licença MIT.
