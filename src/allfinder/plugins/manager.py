"""
manager.py
==========
Gerenciador de plugins do allfinder.

Responsável por registrar plugins e selecionar o mais adequado para uma URL.
Plugins específicos de sites têm prioridade sobre o plugin genérico.
"""

import re
from typing import List

from allfinder.plugins.generic.base import BasePlugin, GenericPlugin
from allfinder.plugins.specific_sites.globoplay import GloboplayPlugin


class PluginManager:
    """
    Gerencia o registro e seleção de plugins.

    Plugins são avaliados em ordem de registro. O primeiro cujo domain_pattern
    casar com a URL fornecida será utilizado. Se nenhum casar, o GenericPlugin
    é retornado como fallback.
    """

    def __init__(self):
        self.plugins: List[BasePlugin] = []
        self.generic_plugin = GenericPlugin()
        # Registra automaticamente os plugins específicos conhecidos
        self._register_defaults()

    def _register_defaults(self) -> None:
        """Registra os plugins específicos de sites incluídos no pacote."""
        self.register_plugin(GloboplayPlugin())

    def register_plugin(self, plugin: BasePlugin) -> None:
        """Registra um plugin no gerenciador."""
        self.plugins.append(plugin)

    def get_plugin_for_url(self, url: str) -> BasePlugin:
        """
        Retorna o plugin mais adequado para a URL fornecida.
        Fallback: GenericPlugin.
        """
        for plugin in self.plugins:
            if re.search(plugin.domain_pattern, url, re.IGNORECASE):
                return plugin
        return self.generic_plugin
