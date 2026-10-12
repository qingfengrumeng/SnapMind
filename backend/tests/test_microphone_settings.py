from fastapi.testclient import TestClient
from backend.tests.test_capture_processing import module

def test_open_microphone_settings_only_opens_the_fixed_windows_settings_uri(module,monkeypatch):
    opened=[]
    monkeypatch.setattr(module.os,'startfile',opened.append)
    client=TestClient(module.app)
    assert client.post('/api/settings/microphone/open').json()=={'opened':True}
    assert opened==['ms-settings:privacy-microphone']

def test_open_microphone_settings_failure_is_actionable(module,monkeypatch):
    def failure(_):raise OSError('internal fixture')
    monkeypatch.setattr(module.os,'startfile',failure)
    response=TestClient(module.app).post('/api/settings/microphone/open')
    assert response.status_code==400 and '麦克风' in response.json()['detail'] and 'internal fixture' not in response.text
