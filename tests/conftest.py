import pytest
from fastapi.testclient import TestClient
from app import db, seed, main

@pytest.fixture(scope='function')
def client(tmp_path,monkeypatch):
    filepath=tmp_path/'synthetic.sqlite3'
    monkeypatch.setattr(db,'DB_PATH',filepath)
    monkeypatch.setattr(seed,'DB_PATH',filepath)
    monkeypatch.setattr(main,'DB_PATH',filepath)
    seed.seed()
    return TestClient(main.app)
