import pytest
from backend.app.local_storage import home,migrate_storage_root


def test_hidden_home_default(monkeypatch,tmp_path):
    from backend.app import local_storage
    for key in ('SNAPMIND_HOME','SNAPMIND_DATA_DIR'):monkeypatch.delenv(key,raising=False)
    monkeypatch.setattr(local_storage,'PROJECT',tmp_path)
    assert home()==tmp_path/'.snapmind'
    monkeypatch.setenv('SNAPMIND_DATA_DIR',str(tmp_path/'isolated'))
    assert home()==tmp_path/'isolated/snapmind'
    monkeypatch.setenv('SNAPMIND_HOME',str(tmp_path/'explicit'))
    assert home()==tmp_path/'explicit'


def test_directory_rename_preserves_bytes_and_is_repeatable(tmp_path):
    old=tmp_path/'snapmind';(old/'sessions/2026/10/10').mkdir(parents=True)
    (old/'models.json').write_bytes(b'{"synthetic":true}')
    (old/'sessions/2026/10/10/rollout-test.jsonl').write_bytes(b'{"type":"response_item"}\n')
    new=migrate_storage_root(tmp_path)
    assert new==tmp_path/'.snapmind' and not old.exists()
    assert (new/'models.json').read_bytes()==b'{"synthetic":true}'
    assert (new/'sessions/2026/10/10/rollout-test.jsonl').read_bytes()==b'{"type":"response_item"}\n'
    assert migrate_storage_root(tmp_path)==new


def test_conflicting_directories_are_never_merged(tmp_path):
    for name in ('snapmind','.snapmind'):
        (tmp_path/name).mkdir();(tmp_path/name/'marker').write_text(name)
    with pytest.raises(RuntimeError):migrate_storage_root(tmp_path)
    assert (tmp_path/'snapmind/marker').read_text()=='snapmind'
    assert (tmp_path/'.snapmind/marker').read_text()=='.snapmind'
