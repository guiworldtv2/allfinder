import pytest
from allfinder.plugins.manager import PluginManager
from allfinder.plugins.generic.base import GenericPlugin, BasePlugin

class MockPlugin(BasePlugin):
    @property
    def name(self) -> str:
        return "Mock Plugin"

    @property
    def domain_pattern(self) -> str:
        return r"mock\.com"

    async def interact(self, page) -> None:
        pass

def test_plugin_manager_registration():
    manager = PluginManager()
    mock_plugin = MockPlugin()
    manager.register_plugin(mock_plugin)
    assert mock_plugin in manager.plugins

def test_plugin_manager_get_plugin_for_url():
    manager = PluginManager()
    mock_plugin = MockPlugin()
    manager.register_plugin(mock_plugin)
    
    # Deve retornar o mock_plugin para o domínio mock.com
    plugin = manager.get_plugin_for_url("https://mock.com/video")
    assert plugin == mock_plugin
    
    # Deve retornar o GenericPlugin para outros domínios
    plugin = manager.get_plugin_for_url("https://outro.com/video")
    assert isinstance(plugin, GenericPlugin)
