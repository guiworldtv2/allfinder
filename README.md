# M3U8-Extractor-Bot

Uma ferramenta em Python para extrair URLs `.m3u8` de sites de streaming, utilizando automação de navegador (Playwright) para simular a interação do usuário e interceptar requisições de rede.

## Funcionalidades

*   **Extração de M3U8:** Captura URLs `.m3u8` que são carregadas dinamicamente após a interação com a página.
*   **Automação de Navegador:** Utiliza Playwright para abrir uma instância de navegador, navegar até a URL fornecida e interagir com a página (ex: clicar no botão de play).
*   **Sistema de Plugins:** Permite a criação de plugins específicos para diferentes sites, possibilitando interações customizadas para garantir a extração do `.m3u8`.
*   **Modo Headless:** Suporte para execução em modo headless (sem interface gráfica) para ambientes de servidor.

## Instalação

1.  **Clone o repositório:**

    ```bash
    git clone https://github.com/seu-usuario/m3u8-extractor-bot.git
    cd m3u8-extractor-bot
    ```

2.  **Crie e ative um ambiente virtual (opcional, mas recomendado):**

    ```bash
    python3 -m venv venv
    source venv/bin/activate  # No Windows: .\venv\Scripts\activate
    ```

3.  **Instale as dependências:**

    ```bash
    pip install -r requirements.txt
    playwright install chromium
    ```

## Uso

Para extrair URLs `.m3u8`, execute o script `main.py` com a URL do site de streaming:

```bash
python src/cli/main.py <URL_DO_SITE>
```

**Exemplo:**

```bash
python src/cli/main.py https://exemplo.com/video-com-streaming
```

### Opções

*   `--headless`: Executa o navegador em modo headless (padrão). Para ver a interface gráfica, use `--no-headless`.
*   `--timeout <milissegundos>`: Define o tempo limite para operações do navegador (padrão: 30000ms).

## Como Adicionar Suporte a Novos Sites (Plugins)

O sistema de plugins permite estender a funcionalidade para sites específicos. Para adicionar suporte a um novo site:

1.  Crie um novo arquivo Python dentro de `src/plugins/` (ex: `meusite_plugin.py`).
2.  Neste arquivo, crie uma classe que herde de `BasePlugin` e implemente os métodos `name`, `domain_pattern` e `interact`.
    *   `name`: Um nome descritivo para o seu plugin.
    *   `domain_pattern`: Uma expressão regular que corresponda ao domínio do site que você quer suportar (ex: `r"meusite\.com"`).
    *   `interact(self, page: Page)`: Contém a lógica de interação com a página. Aqui você pode usar as funções do Playwright (ex: `page.click()`, `page.wait_for_selector()`) para simular as ações do usuário até que o vídeo comece a carregar e o `.m3u8` seja detectado.
3.  Registre seu plugin no `src/cli/main.py` importando-o e adicionando-o ao `plugin_manager`.

## Contribuição

Contribuições são bem-vindas! Sinta-se à vontade para abrir issues, enviar pull requests ou sugerir melhorias.

## Licença

Este projeto está licenciado sob a licença MIT. Veja o arquivo `LICENSE` para mais detalhes.
