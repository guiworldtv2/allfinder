import re
from typing import List, Optional
from playwright.async_api import Page
from .base import BasePlugin, GenericPlugin

class PluginManager:
    def __init__(self):
        self.plugins: List[BasePlugin] = []
        self.generic_plugin = GenericPlugin()

    def register_plugin(self, plugin: BasePlugin):
        self.plugins.append(plugin)

    def get_plugin_for_url(self, url: str) -> BasePlugin:
        for plugin in self.plugins:
            if re.search(plugin.domain_pattern, url):
                return plugin
        return self.generic_plugin
