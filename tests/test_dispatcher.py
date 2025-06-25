import importlib
import os
import pytest
import types

import agents.dispatcher as dispatcher
from agents.figgie_interface import FiggieInterface

class DummyAgent(FiggieInterface):
    def __init__(self, server_url, name, polling_rate, foo=None):
        self.server_url = server_url
        self.name = name
        self.polling_rate = polling_rate
        self.foo = foo

def dummy_factory_kw(server_url, name, polling_rate, foo=None):
    return DummyAgent(server_url=server_url, name=name, polling_rate=polling_rate, foo=foo)

def dummy_factory_pos(name, server_url, polling_rate):
    # only positional
    return DummyAgent(server_url=server_url, name=name, polling_rate=polling_rate, foo="pos")

def test_make_agent_class(monkeypatch):
    # create a fake module with DummyAgent
    mod = types.SimpleNamespace(DummyAgent=DummyAgent)
    monkeypatch.setattr(importlib, "import_module", lambda path: mod)
    entry = ("dummy_module", "DummyAgent", {"foo": 42})
    inst = dispatcher.make_agent(entry, "X", "http://u", 0.1)
    assert isinstance(inst, DummyAgent)
    assert inst.foo == 42

def test_make_agent_factory_pos_fallback(monkeypatch):
    # Test fallback for a factory that only accepts positional args
    mod = types.SimpleNamespace(pos_factory=dummy_factory_pos)
    monkeypatch.setattr(importlib, "import_module", lambda path: mod)
    # First attempt factory(**kwargs) will raise TypeError; fallback to positional args should succeed
    entry = ("dummy_module", "pos_factory", {})
    inst = dispatcher.make_agent(entry, "Z", "http://u", 0.3)
    assert isinstance(inst, DummyAgent)
    assert inst.foo == "pos"

def test_make_agent_invalid(monkeypatch):
    mod = types.SimpleNamespace(not_callable=123)
    monkeypatch.setattr(importlib, "import_module", lambda path: mod)
    entry = ("dummy_module", "not_callable", {})
    with pytest.raises(ValueError):
        dispatcher.make_agent(entry, "Bad", "http://u", 0.1)