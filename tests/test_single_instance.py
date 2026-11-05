import uuid

from PySide6.QtCore import QCoreApplication

from leaguephd_shell.single_instance import InstanceServer, ask_running_copy_to_show, channel_name


def app():
    return QCoreApplication.instance() or QCoreApplication([])


def test_channel_name_is_per_user_and_safe():
    name = channel_name()
    assert name.startswith("unofficial-leaguephd-shell-")
    assert all(c.isalnum() or c in "-_" for c in name)


def test_second_copy_finds_the_first_and_asks_it_to_show():
    qapp = app()
    name = f"leaguephd-shell-test-{uuid.uuid4().hex}"  # never the real app's channel
    assert ask_running_copy_to_show(name, timeout_ms=200) is False, "nothing running yet"

    server = InstanceServer(name)
    assert server.listen()
    shown = []
    server.show_requested.connect(lambda: shown.append(True))

    assert ask_running_copy_to_show(name, timeout_ms=1000) is True
    for _ in range(50):  # let the server's event loop accept the connection
        qapp.processEvents()
        if shown:
            break
    assert shown == [True]
