from app.pipeline.contracts import StageInput, StageOutput
from app.pipeline.registry import StageRegistry, register, default_registry


def _noop(_inp: StageInput) -> StageOutput:
    return StageOutput(status="ok")


def test_register_and_resolve_round_trip():
    reg = StageRegistry()
    reg.register("noop", _noop)
    assert reg.resolve("noop") is _noop
    assert reg.names() == ["noop"]


def test_double_register_rejected():
    reg = StageRegistry()
    reg.register("noop", _noop)
    try:
        reg.register("noop", _noop)
    except ValueError:
        return
    raise AssertionError("expected ValueError on duplicate registration")


def test_unknown_resolve_raises():
    reg = StageRegistry()
    try:
        reg.resolve("missing")
    except KeyError:
        return
    raise AssertionError("expected KeyError for missing stage")


def test_decorator_registers_into_default(tmp_name="__test_decorator_stage__"):
    @register(tmp_name)
    def _my_stage(_inp: StageInput) -> StageOutput:
        return StageOutput(status="ok")

    try:
        assert default_registry.resolve(tmp_name) is _my_stage
    finally:
        default_registry._stages.pop(tmp_name, None)
